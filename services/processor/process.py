"""Local GPS-fix-aligned survey exporter. Not a job worker or upload service."""
from __future__ import annotations
import argparse
from bisect import bisect_left
import csv
import json
import math
import os
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path
if __package__:
    from . import preflight
else:
    import preflight

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

def create_gpkg(path, rows):
    con = sqlite3.connect(path)
    try:
        con.executescript("""
        PRAGMA application_id=1196444487; PRAGMA user_version=10300;
        CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY, organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT);
        INSERT INTO gpkg_spatial_ref_sys VALUES ('Undefined Cartesian',-1,'NONE',-1,'undefined','undefined');
        INSERT INTO gpkg_spatial_ref_sys VALUES ('Undefined geographic',0,'NONE',0,'undefined','undefined');
        INSERT INTO gpkg_spatial_ref_sys VALUES ('WGS 84 geodetic',4326,'EPSG',4326,'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]','longitude/latitude');
        CREATE TABLE gpkg_contents (table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL, identifier TEXT UNIQUE, description TEXT DEFAULT '', last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER, FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id));
        CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL, column_name TEXT NOT NULL, geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL, PRIMARY KEY(table_name,column_name));
        CREATE TABLE points (id INTEGER PRIMARY KEY, geom BLOB NOT NULL, frame_index INTEGER NOT NULL, image_path TEXT NOT NULL, requested_ms INTEGER NOT NULL, actual_pts REAL NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL);
        INSERT INTO gpkg_contents (table_name,data_type,identifier,srs_id) VALUES ('points','features','points',4326);
        INSERT INTO gpkg_geometry_columns VALUES ('points','geom','POINT',4326,0,0);
        """)
        for r in rows:
            geom = b'GP' + bytes([0,1]) + struct.pack('<i',4326) + struct.pack('<BIdd',1,1,r['lon'],r['lat'])
            con.execute('INSERT INTO points (geom,frame_index,image_path,requested_ms,actual_pts,lat,lon) VALUES (?,?,?,?,?,?,?)',(geom,r['frame_index'],r['image_path'],r['requested_ms'],r['actual_pts'],r['lat'],r['lon']))
        con.commit()
    finally: con.close()

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
        interval=1, max_accuracy=None, rotation=0, manual_points=(), checkpoint=lambda progress: None, package=True):
    checkpoint(2)
    report=preflight.validate(video,log,None,20,True)
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
        for position, fix in enumerate(selected):
            checkpoint(5 + int(85 * position / len(selected)))
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
            subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-protocol_whitelist','file','-threads','2','-i',str(video),'-map','0:v:0','-vf',f'select=eq(n\\,{index}){rotation_filter}','-frames:v','1','-q:v','2',str(tmp/image)],check=True,capture_output=True,timeout=300)
            subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-protocol_whitelist','file','-i',str(tmp/image),'-f','null','-'],check=True,capture_output=True,timeout=60)
            rows.append({'frame_index':len(rows),'image_path':image,'requested_ms':ms,'actual_pts':times[index],'source_frame_index':index,'lat':float(fix['lat']),'lon':float(fix['lon']),'accuracy_m':fix.get('accuracy_m',''),'bearing':fix.get('bearing',''),
                         'manual':fix.get('manual',False),'interpolated':fix.get('interpolated',False),'fix_gap_ms':fix.get('fix_gap_ms',0)})
        if not rows: raise ValueError('No valid frames within tolerance')
        with (tmp/'points.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
        features=[{'type':'Feature','geometry':{'type':'Point','coordinates':[r['lon'],r['lat']]},'properties':{k:v for k,v in r.items() if k not in ('lon','lat')}} for r in rows]
        (tmp/'points.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features}),encoding='utf-8')
        coords=[[r['lon'],r['lat']] for r in rows if not r['manual']]
        route={'type':'FeatureCollection','features':([{'type':'Feature','properties':{},'geometry':{'type':'LineString','coordinates':coords}}] if len(coords)>1 else [])}
        (tmp/'route.geojson').write_text(json.dumps(route),encoding='utf-8')
        checkpoint(92)
        create_gpkg(tmp/'points.gpkg',rows)
        manifest={'schema_version':'2.0-draft','sampling':sampling,'rotation':rotation,'manual_points_added':sum(r['manual'] for r in rows),'interval':interval,'max_accuracy':max_accuracy,'max_snap_seconds':max_snap,'video_sha256':report['video']['sha256'],'gps_sha256':report['gps']['sha256'],'frame_count':len(rows),'skipped':skipped,'warnings':report['warnings']}
        (tmp/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        (tmp/'qa_report.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        if package:
            with zipfile.ZipFile(tmp/'survey.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
                for f in sorted(tmp.rglob('*')):
                    if f.is_file() and f.name != 'survey.zip': z.write(f,f.relative_to(tmp).as_posix())
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
