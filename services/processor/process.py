"""Local GPS-fix-aligned survey exporter. Not a job worker or upload service."""
from __future__ import annotations
import argparse
from bisect import bisect_left
import csv
import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
if __package__:
    from . import preflight
    from .coordinates import apply_correction, point_identity
    from .exports import package_run, write_json, write_points
    from .extraction import extract_frames
else:
    import preflight
    from coordinates import apply_correction, point_identity
    from exports import package_run, write_json, write_points
    from extraction import extract_frames

MAX_SNAP_SECONDS = 0.10

def frame_times(video):
    proc = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-select_streams", "v:0",
        "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", str(video)],
        capture_output=True, text=True, check=True, timeout=600)
    frames = json.loads(proc.stdout)["frames"]
    times = [float(x["best_effort_timestamp_time"]) for x in frames]
    if not times or not all(math.isfinite(t) for t in times) or any(b < a for a,b in zip(times,times[1:])):
        raise ValueError("Video frame timestamps are missing or not ordered")
    return times

def sampled_fixes(fixes, mode, interval, max_accuracy):
    usable = [r for r in fixes if int(r["video_elapsed_ms"]) >= 0 and
              (max_accuracy is None or (r.get("accuracy_m") and float(r["accuracy_m"]) <= max_accuracy))]
    if not usable or mode == "gps_fix":
        return usable
    result = [usable[0]]
    next_step = interval
    cumulative = 0.0
    start = int(usable[0]["video_elapsed_ms"])
    for previous, following in zip(usable, usable[1:]):
        a, b = int(previous["video_elapsed_ms"]), int(following["video_elapsed_ms"])
        if mode == "time":
            end = (b - start) / 1000
        else:
            end = cumulative + preflight.haversine(float(previous["lat"]), float(previous["lon"]),
                                                  float(following["lat"]), float(following["lon"]))
        while next_step <= end:
            if len(result) >= 10000:
                raise ValueError("Sampling exceeds 10,000 images")
            fraction = (next_step - cumulative) / (end - cumulative)
            sample = dict(previous)
            sample["video_elapsed_ms"] = round(a + fraction * (b - a))
            sample["interpolated"] = True
            sample["fix_gap_ms"] = b - a
            delta = (float(following["lon"]) - float(previous["lon"]) + 180) % 360 - 180
            sample["lon"] = (float(previous["lon"]) + delta * fraction + 180) % 360 - 180
            sample["lat"] = float(previous["lat"]) + fraction * (float(following["lat"]) - float(previous["lat"]))
            # Avoid interpolating across long outages or clear position jumps.
            distance = preflight.haversine(float(previous["lat"]), float(previous["lon"]),
                                           float(following["lat"]), float(following["lon"]))
            if b - a <= 10000 and distance / ((b - a) / 1000) <= 40:
                result.append(sample)
            else:
                next_step = (math.floor(end / interval) + 1) * interval
                break
            next_step += interval
        cumulative = end
    return result


def run(video, log, output, max_snap=MAX_SNAP_SECONDS, *, sampling="gps_fix",
        interval=1, max_accuracy=None, rotation=0, manual_points=(), checkpoint=lambda progress: None, package=True,
        corrections=None, validated=None):
    checkpoint(2)
    report = validated
    if (not report or not report.get("can_process") or not report["video"].get("full_decode_passed")
            or preflight.hash_file(video) != report["video"]["sha256"]
            or preflight.hash_file(log) != report["gps"]["sha256"]):
        report = preflight.validate(video, log, None, 20, True)
    if not report['can_process']: raise ValueError('Preflight failed: ' + ', '.join(report['errors']))
    if output.exists(): raise FileExistsError('Output already exists; choose a new run directory')
    times=frame_times(video)
    with log.open(encoding='utf-8-sig', newline='') as f: fixes=list(csv.DictReader(f))
    output.parent.mkdir(parents=True,exist_ok=True)
    tmp=Path(tempfile.mkdtemp(prefix='.streetview-run-',dir=output.parent))
    try:
        (tmp/'images').mkdir()
        rows=[]; skipped=[]
        selected = sampled_fixes(fixes, sampling, interval, max_accuracy)
        selected = sorted(
            [*selected, *({**point, "manual": True} for point in manual_points)],
            key=lambda point: int(point["video_elapsed_ms"]),
        )
        rotation_filter = {0: "", 90: ",transpose=clock", 180: ",hflip,vflip",
                           270: ",transpose=cclock"}[rotation]
        if len(selected) > 10000:
            raise ValueError("Sampling exceeds 10,000 images")
        used = set()
        for fix in selected:
            ms=int(fix['video_elapsed_ms'])
            if ms < 0: continue
            target=ms/1000 + times[0]
            upper = bisect_left(times, target)
            candidates = {max(0, upper - 1), min(upper, len(times) - 1)}
            index = min(candidates, key=lambda i: (abs(times[i] - target), i))
            delta=abs(times[index]-target)
            if delta > max_snap:
                if fix.get("manual"):
                    raise ValueError(f"No video frame within {max_snap * 1000:.0f} ms of {ms / 1000:g} s")
                skipped.append({'requested_ms':ms,'reason':'NO_FRAME_WITHIN_TOLERANCE','nearest_pts':times[index]}); continue
            if index in used and not fix.get("manual"):
                skipped.append({"requested_ms":ms,"reason":"FRAME_ALREADY_SELECTED"}); continue
            if not fix.get("manual"):
                used.add(index)
            image=f"images/{len(rows):06d}.jpg"
            rows.append({'frame_index':len(rows),'image_path':image,'requested_ms':ms,'actual_pts':times[index],'source_frame_index':index,'lat':float(fix['lat']),'lon':float(fix['lon']),'accuracy_m':fix.get('accuracy_m',''),'bearing':fix.get('bearing',''),
                         'speed_mps':fix.get('speed_mps',''),'alt_m':fix.get('alt_m',''),
                         'manual':fix.get('manual',False),'interpolated':fix.get('interpolated',False),'fix_gap_ms':fix.get('fix_gap_ms',0)})
        if not rows: raise ValueError('No valid frames within tolerance')
        extract_frames(video, rows, tmp, rotation_filter, checkpoint)
        features = [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
             "properties": {key: value for key, value in row.items() if key not in ("lon", "lat")}}
            for row in rows
        ]
        recording = {"video_sha256": report["video"]["sha256"], "gps_sha256": report["gps"]["sha256"]}
        if corrections:
            for feature in features:
                identity = point_identity(feature["properties"], recording, feature["geometry"]["coordinates"])
                if identity in corrections:
                    apply_correction(feature, identity, corrections[identity])
        coords = [feature["geometry"]["coordinates"] for feature in features if not feature["properties"]["manual"]]
        route = {"type": "FeatureCollection", "features": (
            [{"type": "Feature", "properties": {}, "geometry": {"type": "LineString", "coordinates": coords}}]
            if len(coords) > 1 else []
        )}
        checkpoint(92)
        write_points(tmp, features)
        write_json(tmp / "route.geojson", route)
        manifest = {
            "schema_version": "2.0-draft", "sampling": sampling, "rotation": rotation,
            "manual_points_added": sum(row["manual"] for row in rows),
            "corrected_points": sum("original_coordinates" in feature["properties"] for feature in features),
            "interval": interval, "max_accuracy": max_accuracy, "max_snap_seconds": max_snap,
            **recording, "frame_count": len(rows), "skipped": skipped, "warnings": report["warnings"],
        }
        write_json(tmp / "manifest.json", manifest)
        write_json(tmp / "qa_report.json", manifest)
        if package:
            package_run(tmp)
        checkpoint(99)
        os.rename(tmp,output)
        return manifest
    except BaseException:
        shutil.rmtree(tmp,ignore_errors=True)
        raise

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--video',type=Path,required=True);ap.add_argument('--log',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();print(json.dumps(run(args.video,args.log,args.output),indent=2))
if __name__=='__main__': main()
