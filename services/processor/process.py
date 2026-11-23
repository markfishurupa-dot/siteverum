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
from typing import Any
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

def _has_value(value):
    return value is not None and str(value).strip() != ""


def _interpolate_bearing(start_deg, end_deg, fraction):
    delta = (end_deg - start_deg + 180.0) % 360.0 - 180.0
    return (start_deg + delta * fraction) % 360.0


def sampled_fixes(fixes, mode, interval, max_accuracy):
    usable = [r for r in fixes if int(r["video_elapsed_ms"]) >= 0 and
              (max_accuracy is None or (_has_value(r.get("accuracy_m")) and float(r["accuracy_m"]) <= max_accuracy))]
    if not usable or mode == "gps_fix":
        return usable
    result: list[dict[str, Any]] = [dict(usable[0], interpolated=False, fix_gap_ms=0)]
    step_index = 1
    step_tolerance = 1e-9  # Only absorb floating-point roundoff, not a time or distance window.
    cumulative = 0.0
    start = int(usable[0]["video_elapsed_ms"])
    for previous, following in zip(usable, usable[1:]):
        a, b = int(previous["video_elapsed_ms"]), int(following["video_elapsed_ms"])
        distance = preflight.haversine(float(previous["lat"]), float(previous["lon"]),
                                       float(following["lat"]), float(following["lon"]))
        if mode == "time":
            end = (b - start) / 1000
        else:
            end = cumulative + distance
        if end <= cumulative:
            continue
        # Skip estimates across outages or jumps, but retain a fix on the grid.
        gap_ms = b - a
        if not (0 < gap_ms <= 10000 and distance <= 40 * (gap_ms / 1000)):
            step_index = max(step_index, math.ceil((end - step_tolerance) / interval))
        while (next_step := step_index * interval) <= end + step_tolerance:
            if len(result) >= 10000:
                raise ValueError("Sampling exceeds 10,000 images")
            step_index += 1
            if math.isclose(next_step, end, rel_tol=0, abs_tol=step_tolerance):
                result.append(dict(following, interpolated=False, fix_gap_ms=0))
                break
            fraction = (next_step - cumulative) / (end - cumulative)
            sample = dict(previous, alt_m=None, speed_mps=None, bearing=None, accuracy_m=None,
                          timestamp_utc=None, interpolated=True, fix_gap_ms=gap_ms)
            sample["video_elapsed_ms"] = round(a + fraction * (b - a))
            delta = (float(following["lon"]) - float(previous["lon"]) + 180) % 360 - 180
            sample["lon"] = (float(previous["lon"]) + delta * fraction + 180) % 360 - 180
            sample["lat"] = float(previous["lat"]) + fraction * (float(following["lat"]) - float(previous["lat"]))
            if _has_value(previous.get("timestamp_utc")) and _has_value(following.get("timestamp_utc")):
                sample["timestamp_utc"] = round(
                    int(previous["timestamp_utc"]) + fraction * (int(following["timestamp_utc"]) - int(previous["timestamp_utc"]))
                )
            for numeric_field in ("alt_m", "speed_mps"):
                if _has_value(previous.get(numeric_field)) and _has_value(following.get(numeric_field)):
                    p_val = float(previous[numeric_field])
                    f_val = float(following[numeric_field])
                    sample[numeric_field] = round(p_val + fraction * (f_val - p_val), 4)
            if _has_value(previous.get("bearing")) and _has_value(following.get("bearing")):
                sample["bearing"] = round(
                    _interpolate_bearing(float(previous["bearing"]), float(following["bearing"]), fraction), 2
                ) % 360.0
            result.append(sample)
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
            timestamp_utc = fix.get("timestamp_utc")
            accuracy_m = None if fix.get("manual") or fix.get("interpolated") else fix.get("accuracy_m")
            rows.append({
                "frame_index": len(rows), "image_path": image, "requested_ms": ms,
                "actual_pts": times[index], "source_frame_index": index,
                "lat": float(fix["lat"]), "lon": float(fix["lon"]),
                "timestamp_utc": int(str(timestamp_utc)) if _has_value(timestamp_utc) else None,
                "accuracy_m": accuracy_m if _has_value(accuracy_m) else None,
                "bearing": fix.get("bearing", ""), "speed_mps": fix.get("speed_mps", ""),
                "alt_m": fix.get("alt_m", ""), "manual": fix.get("manual", False),
                "interpolated": fix.get("interpolated", False), "fix_gap_ms": fix.get("fix_gap_ms", 0),
            })
        if not rows: raise ValueError('No valid frames within tolerance')
        features = [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
             "properties": {key: value for key, value in row.items() if key not in ("lon", "lat")}}
            for row in rows
        ]
        recording = {"video_sha256": report["video"]["sha256"], "gps_sha256": report["gps"]["sha256"]}
        deleted_points = 0
        if corrections:
            retained = []
            for row, feature in zip(rows, features):
                properties = feature["properties"]
                identity = point_identity(properties, recording, feature["geometry"]["coordinates"])
                correction = corrections.get(identity)
                if correction:
                    if correction["deleted"]:
                        deleted_points += 1
                        continue
                    apply_correction(feature, identity, [correction["longitude"], correction["latitude"]],
                                     correction["bearing"])
                index = len(retained)
                row.update(frame_index=index, image_path=f"images/{index:06d}.jpg")
                properties.update(frame_index=index, image_path=row["image_path"])
                retained.append((row, feature))
            rows = [row for row, _ in retained]
            features = [feature for _, feature in retained]
        if rows:
            extract_frames(video, rows, tmp, rotation_filter, checkpoint)
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
            "manual_points_added": sum(row["manual"] for row in rows), "deleted_points": deleted_points,
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
