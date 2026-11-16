import json
import logging
import shutil
import time
import tempfile
from pathlib import Path

from psycopg.types.json import Jsonb

from processor import merge, preflight, process
from runtime import ROOT, connect, run_path, source_groups

log = logging.getLogger("streetview.worker")


def checkpoint(job, progress):
    with connect() as db:
        row = db.execute(
            "UPDATE jobs SET progress=%s WHERE id=%s AND state='running' RETURNING id",
            (progress, job),
        ).fetchone()
    if not row:
        raise InterruptedError("Job cancelled")


def process_job(row):
    job, survey = row["id"], row["survey"]
    output = run_path(survey, job)
    # On recovery, unfinished outputs are never exposed and can be rebuilt.
    output.parent.mkdir(parents=True, exist_ok=True)
    for interrupted in output.parent.glob(".streetview-run-*"):
        shutil.rmtree(interrupted)
    if output.exists():
        shutil.rmtree(output)
    staging = ROOT / str(survey) / "work"
    staging.mkdir(exist_ok=True)
    for interrupted in staging.glob("archive-*"):
        shutil.rmtree(interrupted)
    with connect() as db:
        groups = source_groups(db, survey)
    with tempfile.TemporaryDirectory(prefix="archive-", dir=staging) as temp:
        work = Path(temp)
        completed = []
        for position, (recording, items) in enumerate(groups.items()):
            paths = {kind: ROOT / item["storage"] for kind, item in items.items()}
            folder = work / str(position)
            folder.mkdir()
            if "zip" in paths:
                errors = []
                video, track = preflight.safe_zip_extract_pair(paths["zip"], folder, errors)
                if errors:
                    raise ValueError(f"Recording {position + 1} archive no longer validates")
            else:
                video, track = paths["video"], paths["track"]
            options = dict(row["settings"])
            if position:
                options.pop("manual_points", None)
            destination = output if len(groups) == 1 else folder / "output"

            def recording_progress(progress):
                checkpoint(job, int((position + progress / 100) * 94 / len(groups)))

            metadata = process.run(video, track, destination, **options,
                                   checkpoint=recording_progress, package=len(groups) == 1)
            completed.append((recording, destination, metadata))
        if len(completed) > 1:
            merged = work / "merged"
            metadata = merge.combine(completed, merged, lambda progress: checkpoint(job, progress))
            merged.rename(output)
    points = json.loads((output / "points.geojson").read_text(encoding="utf-8"))
    route = json.loads((output / "route.geojson").read_text(encoding="utf-8"))
    with connect() as db:
        updated = db.execute(
            "UPDATE jobs SET state='completed',progress=100,metadata=%s WHERE id=%s AND state='running' RETURNING id",
            (Jsonb(metadata), job),
        ).fetchone()
        if not updated:
            raise InterruptedError("Job cancelled")
        for feature in points["features"]:
            properties = feature["properties"]
            db.execute("INSERT INTO frames VALUES (%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s)",
                       (job, properties["frame_index"], json.dumps(feature["geometry"]), Jsonb(properties)))
        if route["features"]:
            geometry = {"type": "MultiLineString",
                        "coordinates": [feature["geometry"]["coordinates"] for feature in route["features"]]}
            db.execute("INSERT INTO routes VALUES (%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326))",
                       (job, json.dumps(geometry)))
        for artifact in output.rglob("*"):
            if artifact.is_file():
                db.execute("INSERT INTO artifacts VALUES (%s,%s,%s)",
                           (job, artifact.relative_to(output).as_posix(), artifact.stat().st_size))


def main():
    # Hold a session lock: only one worker may recover and process jobs.
    with connect() as owner:
        owner.autocommit = True
        while not owner.execute("SELECT pg_try_advisory_lock(183002) AS acquired").fetchone()["acquired"]:
            time.sleep(2)
        owner.execute("UPDATE jobs SET state='queued',progress=0 WHERE state='running'")
        while True:
            row = owner.execute("""
                UPDATE jobs SET state='running', progress=1
                WHERE id=(SELECT id FROM jobs WHERE state='queued' ORDER BY created
                          LIMIT 1 FOR UPDATE SKIP LOCKED)
                RETURNING *
            """).fetchone()
            if not row:
                time.sleep(1)
                continue
            try:
                process_job(row)
            except Exception as error:
                if not isinstance(error, InterruptedError):
                    log.exception("Processing failed for job %s", row["id"])
                output = run_path(row["survey"], row["id"])
                if output.exists():
                    shutil.rmtree(output)
                owner.execute("UPDATE jobs SET state='failed',error=%s WHERE id=%s AND state='running'",
                              (str(error) if isinstance(error, ValueError)
                               else "Processing failed. Check worker logs.", row["id"]))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
