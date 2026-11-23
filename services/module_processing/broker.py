
"""Stage a single durable Postgres job for the disconnected module runner."""
import json
import logging
import os
import re
import shutil
import time

from psycopg.types.json import Jsonb

from module_processing import contracts as c
from module_processing.results import copy_output, register
from module_processing.storage import INBOX, MODELS, OUTBOX, POLE_MODELS, RESULTS, TEMP_RESULTS, TEMP_SECONDS, package_path, result_root
from runtime import connect, run_path

LOG = logging.getLogger("module-broker")


def claim(db):
    return db.execute("""
        WITH candidate AS (
            SELECT r.id FROM module_runs r JOIN surveys s ON s.id=r.survey
            WHERE r.state='queued' AND NOT s.deleted ORDER BY r.created,r.id LIMIT 1 FOR UPDATE OF r SKIP LOCKED
        )
        UPDATE module_runs r SET state='running',started=now(),progress=1
        FROM candidate, modules m, jobs j WHERE r.id=candidate.id
          AND m.module_id=r.module_id AND m.version=r.version AND j.id=r.source_job
        RETURNING r.*,m.manifest,m.sha256,j.source_revision,j.settings,j.fingerprint AS source_fingerprint
        """).fetchone()


def stage(db, run, path):
    source = run_path(run["survey"], run["source_job"])
    package = package_path(run["sha256"])
    c.require(c.digest(package) == run["sha256"], "Installed package checksum mismatch")
    manifest = c.inspect_package(package, path / "package")
    c.require(manifest == run["manifest"], "Installed manifest mismatch")
    model = manifest.get("model")
    if run["pole_model"] is not None:
        checkpoint = db.execute("SELECT name,sha256,labels FROM pole_models WHERE id=%s", (run["pole_model"],)).fetchone()
        model = {**model, **checkpoint}
        source_checkpoint = POLE_MODELS / (checkpoint["sha256"] + ".pt")
        target = path / "package" / model["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_checkpoint, target)
        c.require(c.digest(target) == model["sha256"], "Custom checkpoint checksum mismatch")
    elif model and model["source"] == "provisioned":
        provisioned = MODELS / model["path"]
        c.require(provisioned.is_file() and c.digest(provisioned) == model["sha256"],
                  "Provision the trusted model with the declared checksum before running")
        target = path / "package" / model["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(provisioned, target)
    input_path = path / "input"
    (input_path / "images").mkdir(parents=True)
    for name in ("points.geojson", "route.geojson"):
        c.require((source / name).stat().st_size <= 64 * 1024**2, "Source layer exceeds input limit")
        shutil.copyfile(source / name, input_path / name)
    frames = {}
    total = 0
    rows = db.execute("""SELECT sequence,properties,ST_X(geom) AS lon,ST_Y(geom) AS lat
                      FROM frames WHERE job=%s ORDER BY sequence LIMIT 20001""", (run["source_job"],)).fetchall()
    c.require(len(rows) <= 20000, "Module input exceeds 20,000 frames")
    for frame in rows:
        props = frame["properties"]
        image = props.get("image_path")
        c.require(c.matches(c.PHOTO, image), "Invalid source image reference")
        original = source / image
        c.require(original.is_file() and not original.is_symlink(), f"Missing source photo {image}")
        total += original.stat().st_size
        c.require(total <= c.INPUT_LIMIT, "Module image inputs exceed 2 GiB")
        target = input_path / image
        shutil.copyfile(original, target)
        frames[frame["sequence"]] = {**props, "sequence": frame["sequence"], "lon": frame["lon"],
                                     "lat": frame["lat"], "sha256": c.digest(target)}
    c.write_json(input_path / "manifest.json", {
        "contract": c.INPUT, "survey": str(run["survey"]), "source_job": str(run["source_job"]),
        "source_revision": run["source_revision"], "source_fingerprint": run["source_fingerprint"],
        "processing_parameters": run["settings"],
        "frames": list(frames.values()),
    })
    c.write_json(path / "execution.json", {
        "execution": str(run["id"]), "module": run["module_id"], "version": run["version"],
        "parameters": run["configuration"], "entrypoint": manifest["entrypoint"], "runtime": manifest["runtime"],
        "timeout_seconds": manifest["timeout_seconds"], "model": model, "gpu": manifest["gpu"],
    })
    if manifest.get("cache"):
        stage_cache(db, run, input_path, frames)
    return frames


def stage_cache(db, run, path, frames):
    import hashlib

    spec = run["manifest"]["cache"]
    settings = [run["configuration"][key] for key in spec["settings"]]
    signature = [run["sha256"], str(run["source_job"]), settings, [frame["sha256"] for frame in frames.values()]]
    if run["pole_model"] is not None:
        signature.append(str(run["pole_model"]))
    key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    c.write_json(path / "cache_key.json", key)
    candidates = db.execute("""SELECT id,summary,temporary FROM module_runs WHERE source_job=%s AND module_id=%s
                            AND version=%s AND state='completed'
                            AND (NOT temporary OR finished > now() - %s * interval '1 second')
                            ORDER BY finished DESC LIMIT 20""",
                            (run["source_job"], run["module_id"], run["version"], TEMP_SECONDS)).fetchall()
    for previous in candidates:
        directory = result_root(previous) / str(previous["id"])
        summary_path = directory / "summary.json"
        if previous["temporary"] and not summary_path.is_file():
            continue
        summary = c.read_json(summary_path) if previous["temporary"] else previous["summary"]
        if summary.get("cache_key") != key:
            continue
        if previous["temporary"]:
            index = directory / "artifacts.json"
            if not index.is_file():
                continue
            artifact = next((item for item in c.read_json(index) if item["path"] == spec["artifact"]), None)
        else:
            artifact = db.execute("SELECT sha256 FROM module_artifacts WHERE run=%s AND path=%s",
                                  (previous["id"], spec["artifact"])).fetchone()
        cache = directory / "output" / c.relative(spec["artifact"])
        if artifact and cache.is_file() and c.digest(cache) == artifact["sha256"]:
            shutil.copyfile(cache, path / "cache.dat")
            return


def copy_log(out, target):
    log = out / "execution.log"
    if out.is_dir() and not out.is_symlink() and log.is_file() and not log.is_symlink():
        with log.open("rb") as stream:
            (target / "execution.log").write_bytes(stream.read(4 * 1024**2))


def execute(run):
    name = str(run["id"])
    LOG.info("%s", json.dumps({"event": "module_started", "run": name, "module": run["module_id"],
                              "version": run["version"], "source_job": str(run["source_job"])}))
    staged = INBOX / f".{name}"
    inbox = INBOX / name
    out = OUTBOX / name
    final = result_root(run) / name
    pending = final.parent / f".{name}"
    try:
        with connect() as db:
            frames = stage(db, run, staged)
        staged.rename(inbox)
        started = time.monotonic()
        while True:
            c.require(not out.is_symlink(), "Runner output workspace is invalid")
            with connect() as db:
                row = db.execute("""SELECT r.state,s.deleted FROM module_runs r JOIN surveys s ON s.id=r.survey
                                 WHERE r.id=%s""", (run["id"],)).fetchone()
                if row["state"] != "running" or row["deleted"]:
                    db.execute("""UPDATE module_runs SET state='cancelled',finished=now()
                                  WHERE id=%s AND state='running'""", (run["id"],))
                    final.mkdir(exist_ok=True)
                    copy_log(out, final)
                    LOG.info("%s", json.dumps({"event": "module_cancelled", "run": name}))
                    return
                progress = out / "control/progress"
                if progress.is_file() and not progress.is_symlink() and not progress.parent.is_symlink():
                    with progress.open("rb") as stream:
                        value = stream.read(4).strip()
                    if value.isdigit():
                        db.execute("UPDATE module_runs SET progress=GREATEST(progress,%s) WHERE id=%s AND state='running'",
                                   (min(95, int(value)), run["id"]))
            status = out / "status.json"
            if status.is_file() and not status.is_symlink():
                outcome = c.read_json(status, 8192)
                c.require(outcome.get("exit") == 0, str(outcome.get("error", "Module process failed"))[:500])
                break
            c.require(time.monotonic() - started < run["manifest"]["timeout_seconds"] + 20, "Module runner timed out or unavailable")
            time.sleep(0.5)
        pending.mkdir()
        inventory = copy_output(out / "output", pending / "output")
        copy_log(out, pending)
        with connect() as db:
            row = db.execute("SELECT state FROM module_runs WHERE id=%s", (run["id"],)).fetchone()
            if row["state"] != "running":
                return
            summary = register(db, run, inventory, frames, pending)
            if (inbox / "input/cache_key.json").exists():
                summary["cache_key"] = c.read_json(inbox / "input/cache_key.json")
            if run["temporary"]:
                c.write_json(pending / "summary.json", summary)
            stored_summary = None if run["temporary"] else Jsonb(summary)
            updated = db.execute("""UPDATE module_runs SET state='completed',progress=100,summary=%s,finished=now()
                                  WHERE id=%s AND state='running' RETURNING id""", (stored_summary, run["id"])).fetchone()
            if not updated:
                db.rollback()
                return
            pending.rename(final)
            os.utime(final, None)
        LOG.info("%s", json.dumps({"event": "module_completed", "run": name, "artifacts": len(inventory)}))
    except Exception as exc:
        LOG.exception("Module run %s failed", name)
        if not final.exists():
            final.mkdir(exist_ok=True)
        copy_log(out, final)
        error = str(exc)[:500] if isinstance(exc, c.ContractError) else "Module preparation or output validation failed"
        with connect() as db:
            db.execute("""UPDATE module_runs SET state='failed',error=%s,finished=now() WHERE id=%s AND state='running'""",
                       (error, run["id"]))
    finally:
        for path in (staged, inbox, pending):
            shutil.rmtree(path, ignore_errors=True)
        # The runner checks for a removed inbox and terminates its process group.


def clean_temporary_results():
    cutoff = time.time() - TEMP_SECONDS - 60
    for directory in TEMP_RESULTS.iterdir():
        if not re.fullmatch(r"\.?[a-f0-9-]{36}", directory.name) or directory.is_symlink():
            continue
        if directory.stat().st_mtime < cutoff:
            shutil.rmtree(directory, ignore_errors=True)


def main():
    logging.basicConfig(level=logging.INFO)
    for path in (INBOX, OUTBOX, RESULTS, TEMP_RESULTS):
        path.mkdir(exist_ok=True, parents=True)
    with connect() as leadership:
        if not leadership.execute("SELECT pg_try_advisory_lock(183011) AS locked").fetchone()["locked"]:
            raise RuntimeError("Another module broker holds the worker lock")
        leadership.execute("""UPDATE module_runs SET state='failed',finished=now(),error='Module broker restarted'
                              WHERE state='running'""")
        leadership.commit()
        for path in INBOX.iterdir():
            if re.fullmatch(r"\.?[a-f0-9-]{36}", path.name):
                shutil.rmtree(path, ignore_errors=True)
        next_cleanup = 0
        while True:
            if time.monotonic() >= next_cleanup:
                clean_temporary_results()
                next_cleanup = time.monotonic() + 60
            leadership.execute("SELECT 1")
            leadership.commit()
            with connect() as db:
                run = claim(db)
            if run:
                execute(run)
            else:
                time.sleep(1)


if __name__ == "__main__":
    main()
