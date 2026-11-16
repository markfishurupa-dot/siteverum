import json
import logging
import shutil
import time
import tempfile

from psycopg.types.json import Jsonb

from processor import preflight, process
from runtime import ROOT, connect, run_path

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
        paths = {r["kind"]: ROOT / r["storage"] for r in db.execute(
            "SELECT kind,storage FROM sources WHERE survey=%s", (survey,)
        )}
    with tempfile.TemporaryDirectory(prefix="archive-", dir=staging) as temp:
        if "zip" in paths:
            errors = []
            from pathlib import Path
            video, track = preflight.safe_zip_extract_pair(paths["zip"], Path(temp), errors)
            if errors:
                raise ValueError("Archive no longer validates")
        else:
            video, track = paths["video"], paths["track"]
        metadata = process.run(video, track, output, **row["settings"],
                               checkpoint=lambda progress: checkpoint(job, progress))
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
            db.execute("INSERT INTO routes VALUES (%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326))",
                       (job, json.dumps(route["features"][0]["geometry"])))
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
