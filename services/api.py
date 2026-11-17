import csv
import hashlib
import hmac
import json
import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from processor import preflight
from runtime import ROOT, connect, migrate, run_path, source_groups
from version import VERSION
from validation_report import original_track, report_zip

WEB = Path(__file__).resolve().parents[1] / "apps/web"
LIMITS = {"video": 1024**3, "track": 16 * 1024**2, "zip": 1024**3}
EXTENSIONS = {".mp4": "video", ".log": "track", ".csv": "track", ".zip": "zip"}
DOWNLOADS = {"survey.zip", "points.geojson", "route.geojson", "points.csv", "points.gpkg",
             "manifest.json", "qa_report.json"}


@asynccontextmanager
async def lifespan(app):
    if len(os.environ.get("SV_ADMIN_PASSWORD", "")) < 16:
        raise RuntimeError("Set SV_ADMIN_PASSWORD to at least 16 characters")
    migrate()
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
basic = HTTPBasic()


def authenticate(request: Request, credentials: HTTPBasicCredentials = Depends(basic)):
    if not (hmac.compare_digest(credentials.username.encode(), b"admin")
            and hmac.compare_digest(credentials.password.encode(), os.environ["SV_ADMIN_PASSWORD"].encode())):
        raise HTTPException(401, "Sign in as admin", headers={"WWW-Authenticate": "Basic"})
    if request.method not in {"GET", "HEAD"} and request.headers.get("X-StreetView-Request") != "1":
        raise HTTPException(403, "Missing request protection header")


PUBLICATION_STATE = """CASE
    WHEN NOT s.published OR s.published_job IS NULL THEN 'unpublished'
    WHEN s.published_job IS DISTINCT FROM latest.id OR s.source_revision <> latest.source_revision THEN 'outdated'
    ELSE 'current' END"""
LATEST_COMPLETED = """LEFT JOIN LATERAL (
    SELECT id,source_revision FROM jobs WHERE survey=s.id AND state='completed'
    ORDER BY created DESC,id DESC LIMIT 1
) latest ON true"""


def survey_row(db, survey, lock=False):
    sql = f"""SELECT s.id,s.label,s.created,s.validation,s.published,s.slug,s.map_layers,s.source_revision,
        {PUBLICATION_STATE} AS publication_state,
        COALESCE(latest.source_revision=s.source_revision, false) AS can_publish
        FROM surveys s {LATEST_COMPLETED} WHERE s.id=%s AND NOT s.deleted"""
    row = db.execute(sql + (" FOR UPDATE OF s" if lock else ""), (survey,)).fetchone()
    if not row:
        raise HTTPException(404, "Survey not found")
    return row


def idle(db, survey):
    if db.execute("SELECT 1 FROM jobs WHERE survey=%s AND state IN ('queued','running')", (survey,)).fetchone():
        raise HTTPException(409, "A job is active for this survey")


class SurveyCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)


class ManualPoint(BaseModel):
    video_elapsed_ms: int = Field(ge=0, le=7_200_000)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    bearing: float | None = Field(default=None, ge=0, lt=360)


class Settings(BaseModel):
    rotation: Literal[0, 90, 180, 270] = 0
    manual_points: list[ManualPoint] = Field(default_factory=list, max_length=1000)
    sampling: str = Field(default="gps_fix", pattern="^(gps_fix|time|distance)$")
    interval: float = Field(default=1.0, ge=0.1, le=10000)
    max_accuracy: float | None = Field(default=None, gt=0, le=10000)


@app.get("/api/v2/version", dependencies=[Depends(authenticate)])
def version():
    return {"version": VERSION}


@app.get("/health")
def health():
    with connect() as db:
        db.execute("SELECT 1 FROM surveys LIMIT 1")
    return {"status": "ok"}


@app.get("/license")
def license_text():
    return FileResponse(WEB.parents[1] / "LICENSE", media_type="text/plain; charset=utf-8")


@app.get("/", dependencies=[Depends(authenticate)])
def index():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/v2/surveys", dependencies=[Depends(authenticate)])
def catalog():
    with connect() as db:
        return db.execute(f"""SELECT s.id,s.label,s.created,{PUBLICATION_STATE} AS publication_state
            FROM surveys s {LATEST_COMPLETED} WHERE NOT s.deleted ORDER BY s.created DESC""").fetchall()


@app.post("/api/v2/surveys", status_code=201, dependencies=[Depends(authenticate)])
def create(data: SurveyCreate):
    survey = uuid4()
    with connect() as db:
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", data.label).strip("-") or "survey"
        db.execute("SELECT pg_advisory_xact_lock(183003)")
        if slug.lower() in {"api", "static", "health"} or db.execute(
            "SELECT 1 FROM surveys WHERE lower(slug)=lower(%s)", (slug,)
        ).fetchone():
            slug += f"~{survey}"
        db.execute("INSERT INTO surveys (id,label,slug) VALUES (%s,%s,%s)", (survey, data.label, slug))
    return {"id": survey}


@app.get("/api/v2/surveys/{survey}", dependencies=[Depends(authenticate)])
def detail(survey: UUID):
    with connect() as db:
        row = survey_row(db, survey)
        row["sources"] = [
            {**{key: value for key, value in item.items() if key != "storage"}, "recording": recording}
            for recording, items in source_groups(db, survey).items() for item in items.values()
        ]
        row["jobs"] = db.execute(
            "SELECT id,state,progress,error,metadata,settings,coordinate_edit IS NOT NULL AS is_edit FROM jobs WHERE survey=%s ORDER BY created DESC", (survey,)
        ).fetchall()
        return row


@app.put("/api/v2/surveys/{survey}/assets/{filename}", dependencies=[Depends(authenticate)])
async def upload(survey: UUID, filename: str, request: Request, recording: UUID | None = None):
    recording_id = str(recording) if recording else "primary"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,150}", filename):
        raise HTTPException(400, "Invalid source basename")
    kind = EXTENSIONS.get(Path(filename).suffix.lower())
    if kind is None:
        raise HTTPException(415, "Use MP4, LOG, CSV or ZIP")
    length = request.headers.get("Content-Length", "")
    if length.isdecimal() and int(length) > LIMITS[kind]:
        raise HTTPException(413, "UPLOAD_LIMIT")
    with connect() as db:
        survey_row(db, survey)
    if shutil.disk_usage(ROOT).free < max(128 * 1024**2, int(length) if length.isdecimal() else 0):
        raise HTTPException(507, "DISK_LOW")
    stage = ROOT / str(survey) / "sources"
    stage.mkdir(parents=True, exist_ok=True)
    asset = stage / str(uuid4())
    asset.mkdir()
    path = asset / filename
    keep = False
    try:
        digest = hashlib.sha256()
        size = 0
        with path.open("xb") as stream:
            async for chunk in request.stream():
                size += len(chunk)
                if size > LIMITS[kind]:
                    raise HTTPException(413, "UPLOAD_LIMIT")
                if shutil.disk_usage(ROOT).free < 128 * 1024**2:
                    raise HTTPException(507, "DISK_LOW")
                stream.write(chunk)
                digest.update(chunk)
        if not size:
            raise HTTPException(400, "Empty upload")
        checksum = digest.hexdigest()
        with connect() as db:
            survey_row(db, survey, True)
            idle(db, survey)
            groups = source_groups(db, survey)
            current = groups.get(recording_id, {})
            if not current and len(groups) >= 20:
                raise HTTPException(409, "A survey can contain up to 20 recordings")
            old = current.get(kind)
            if old and old["sha256"] == checksum and old["filename"] == filename:
                return {"kind": kind, "bytes": size, "duplicate": True}
            if (kind == "zip" and set(current) - {"zip"}) or (kind != "zip" and "zip" in current):
                raise HTTPException(409, "Each recording accepts one ZIP or a matching MP4 and LOG. Use Add recording for another capture.")
            db.execute(
                """INSERT INTO sources (survey,kind,filename,storage,sha256,bytes,recording) VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (survey,recording,kind) DO UPDATE SET filename=excluded.filename,
                storage=excluded.storage,sha256=excluded.sha256,bytes=excluded.bytes""",
                (survey, kind, filename, str(path.relative_to(ROOT)), checksum, size, recording_id),
            )
            db.execute("UPDATE surveys SET validation=NULL,source_revision=source_revision+1 WHERE id=%s", (survey,))
        keep = True
        return {"kind": kind, "bytes": size, "duplicate": False}
    finally:
        if not keep:
            path.unlink(missing_ok=True)
            asset.rmdir()


@app.delete("/api/v2/surveys/{survey}/recordings/{recording}", dependencies=[Depends(authenticate)])
def discard_recording(survey: UUID, recording: UUID):
    with connect() as db:
        survey_row(db, survey, True)
        idle(db, survey)
        completed = db.execute(
            """SELECT 1 FROM jobs WHERE survey=%s AND state='completed'
            AND metadata->'recordings' @> %s""", (survey, Jsonb([{"recording": str(recording)}])),
        ).fetchone()
        if completed:
            raise HTTPException(409, "This recording is already part of a completed run")
        db.execute("DELETE FROM sources WHERE survey=%s AND recording=%s", (survey, str(recording)))
        db.execute("UPDATE surveys SET validation=NULL,source_revision=source_revision+1 WHERE id=%s", (survey,))
    return {"discarded": True}


def source_paths(rows):
    return {kind: ROOT / row["storage"] for kind, row in rows.items()}


class ValidationSettings(BaseModel):
    max_accuracy: float | None = Field(default=None, gt=0, le=10000)


@app.post("/api/v2/surveys/{survey}/validate", dependencies=[Depends(authenticate)])
def validate(survey: UUID, settings: ValidationSettings | None = None):
    with connect() as db:
        survey_row(db, survey, True)
        idle(db, survey)
        groups = source_groups(db, survey) or {"primary": {}}
        reports = {}
        seen = set()
        for recording, items in groups.items():
            paths = source_paths(items)
            result = preflight.validate(paths.get("video"), paths.get("track"), paths.get("zip"), 20, True)
            if result["can_process"]:
                hashes = (result["video"]["sha256"], result["gps"]["sha256"])
                if hashes in seen:
                    result["errors"].append("This recording duplicates another recording in the survey")
                    result["can_process"] = False
                seen.add(hashes)
            reports[recording] = result
        if tuple(reports) == ("primary",):
            report = reports["primary"]
        else:
            report = {
                "can_process": all(r["can_process"] for r in reports.values()),
                "recordings": reports,
                **{field: [f"Recording {i}: {m}" for i, r in enumerate(reports.values(), 1) for m in r[field]]
                   for field in ("errors", "warnings")},
            }
        report["accuracy_limit"] = settings.max_accuracy if settings else None
        db.execute("UPDATE surveys SET validation=%s WHERE id=%s", (Jsonb(report), survey))
        return report


@app.get("/api/v2/surveys/{survey}/validation-report", dependencies=[Depends(authenticate)])
def download_validation(survey: UUID):
    with connect() as db:
        row = survey_row(db, survey, True)
        if not row["validation"]:
            raise HTTPException(404, "Validate sources to download a report")
        groups = source_groups(db, survey)
        validation = row["validation"]
    stream = report_zip(validation, groups)

    def chunks():
        with stream:
            yield from iter(lambda: stream.read(65536), b"")

    return StreamingResponse(chunks(), media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="validation-report.zip"',
        "Cache-Control": "private, no-store",
    })


@app.post("/api/v2/surveys/{survey}/process", status_code=202, dependencies=[Depends(authenticate)])
def enqueue(survey: UUID, settings: Settings):
    with connect() as db:
        row = survey_row(db, survey, True)
        if not (row["validation"] or {}).get("can_process"):
            raise HTTPException(409, "Validate a complete input pair first")
        groups = source_groups(db, survey)
        rows = groups["primary"] if tuple(groups) == ("primary",) else groups
        config = settings.model_dump()
        validation = row["validation"]
        first_recording = validation.get("recordings", {"primary": validation})[next(iter(groups))]
        duration_ms = first_recording["video"]["duration_seconds"] * 1000
        if any(point.video_elapsed_ms > duration_ms for point in settings.manual_points):
            raise HTTPException(422, "A photo point is beyond the end of the video")
        # Cache compatibility with completed jobs created before these settings existed.
        if not config["rotation"]:
            config.pop("rotation")
        if not config["manual_points"]:
            config.pop("manual_points")
        corrections = db.execute(
            "SELECT identity,longitude,latitude FROM point_corrections WHERE survey=%s ORDER BY identity", (survey,),
        ).fetchall()
        fingerprint_data = [rows, config, corrections] if corrections else [rows, config]
        fingerprint = hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True).encode()).hexdigest()
        existing = db.execute(
            """SELECT id,state FROM jobs WHERE survey=%s AND fingerprint=%s AND source_revision=%s
            AND state IN ('queued','running','completed') ORDER BY created DESC LIMIT 1""",
            (survey, fingerprint, row["source_revision"]),
        ).fetchone()
        latest = db.execute(
            "SELECT id FROM jobs WHERE survey=%s AND state='completed' ORDER BY created DESC LIMIT 1",
            (survey,),
        ).fetchone()
        if existing and (existing["state"] != "completed" or existing["id"] == latest["id"]):
            return existing
        idle(db, survey)
        job = uuid4()
        db.execute(
            "INSERT INTO jobs (id,survey,fingerprint,state,settings,source_revision) VALUES (%s,%s,%s,'queued',%s,%s)",
            (job, survey, fingerprint, Jsonb(config), row["source_revision"]),
        )
        return {"id": job, "state": "queued"}


class PointCoordinates(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


@app.get("/api/v2/surveys/{survey}/runs/{job}/points/{sequence}", dependencies=[Depends(authenticate)])
def point_telemetry(survey: UUID, job: UUID, sequence: int):
    with connect() as db:
        survey_row(db, survey)
        row = db.execute(
            """SELECT f.properties, j.metadata FROM frames f JOIN jobs j ON j.id=f.job
            WHERE j.survey=%s AND j.id=%s AND j.state='completed' AND f.sequence=%s""",
            (survey, job, sequence),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Photo point not found")
        groups = source_groups(db, survey)
    properties = row["properties"]
    if "speed_mps" in properties or properties.get("manual") or properties.get("interpolated"):
        return properties
    # Older runs did not export speed or altitude. Join only to the matching source checksum
    # and exact GPS timestamp. If the original fix is unavailable, keep those values blank.
    metadata = row["metadata"]
    recordings = metadata.get("recordings")
    recording = recordings[properties.get("recording_number", 1) - 1] if recordings else metadata
    checksum = recording.get("gps_sha256")
    sources = groups.get(recording.get("recording", "primary"))
    if checksum and sources:
        with original_track(sources, checksum) as track:
            if track is not None:
                with track.open(encoding="utf-8-sig", newline="") as stream:
                    for fix in csv.DictReader(stream):
                        if fix.get("video_elapsed_ms") == str(properties["requested_ms"]):
                            properties.update(speed_mps=fix.get("speed_mps"), alt_m=fix.get("alt_m"))
                            break
    return properties


@app.patch("/api/v2/surveys/{survey}/runs/{job}/points/{sequence}", status_code=202,
           dependencies=[Depends(authenticate)])
def move_point(survey: UUID, job: UUID, sequence: int, coordinates: PointCoordinates):
    with connect() as db:
        survey_row(db, survey, True)
        idle(db, survey)
        latest = db.execute(
            "SELECT id,settings,source_revision FROM jobs WHERE survey=%s AND state='completed' ORDER BY created DESC LIMIT 1",
            (survey,),
        ).fetchone()
        if not latest or latest["id"] != job:
            raise HTTPException(409, "Reload the survey to edit its latest completed run")
        if not db.execute("SELECT 1 FROM frames WHERE job=%s AND sequence=%s", (job, sequence)).fetchone():
            raise HTTPException(404, "Photo point not found")
        revision = uuid4()
        edit = {"parent": str(job), "sequence": sequence, **coordinates.model_dump()}
        db.execute(
            """INSERT INTO jobs (id,survey,fingerprint,state,settings,coordinate_edit,source_revision)
            VALUES (%s,%s,%s,'queued',%s,%s,%s)""",
            (revision, survey, f"coordinate-edit:{revision}", Jsonb(latest["settings"]), Jsonb(edit), latest["source_revision"]),
        )
        return {"id": revision, "state": "queued"}


@app.post("/api/v2/jobs/{job}/cancel", dependencies=[Depends(authenticate)])
def cancel(job: UUID):
    with connect() as db:
        result = db.execute(
            "UPDATE jobs SET state='cancelled' WHERE id=%s AND state IN ('queued','running') RETURNING id", (job,)
        ).fetchone()
        if not result:
            raise HTTPException(409, "Job is no longer active")
    return {"state": "cancelled"}


@app.delete("/api/v2/surveys/{survey}", dependencies=[Depends(authenticate)])
def delete(survey: UUID):
    with connect() as db:
        survey_row(db, survey, True)
        idle(db, survey)
        db.execute("UPDATE surveys SET deleted=true,published=false,published_job=NULL WHERE id=%s", (survey,))
    return {"deleted": True}


class PublicationSettings(BaseModel):
    layers: Literal["both", "route", "points"] = "both"


@app.post("/api/v2/surveys/{survey}/publication/{action}", dependencies=[Depends(authenticate)])
def publish(survey: UUID, action: str, settings: PublicationSettings | None = None):
    if action not in {"publish", "unpublish"}:
        raise HTTPException(404)
    with connect() as db:
        survey_data = survey_row(db, survey, True)
        current = None
        if action == "publish":
            current = db.execute(
                """SELECT id,source_revision FROM jobs WHERE survey=%s AND state='completed'
                ORDER BY created DESC,id DESC LIMIT 1""", (survey,),
            ).fetchone()
            if not current or current["source_revision"] != survey_data["source_revision"]:
                raise HTTPException(409, "Process the current survey sources before publishing")
        db.execute(
            "UPDATE surveys SET published=%s,published_job=%s,map_layers=COALESCE(%s,map_layers) WHERE id=%s",
            (current is not None, current["id"] if current else None, settings.layers if settings else None, survey),
        )
    return {"published": action == "publish"}


@app.get("/api/v2/surveys/{survey}/runs/{job}/{filename:path}", dependencies=[Depends(authenticate)])
def artifact(survey: UUID, job: UUID, filename: str):
    if filename not in DOWNLOADS and not re.fullmatch(r"images/[0-9]{6}\.jpg", filename):
        raise HTTPException(404)
    with connect() as db:
        survey_row(db, survey)
        row = db.execute("SELECT 1 FROM jobs WHERE id=%s AND survey=%s AND state='completed'", (job, survey)).fetchone()
        if not row:
            raise HTTPException(404)
    path = run_path(survey, job) / filename
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "private, no-store"})


def published_run(slug):
    with connect() as db:
        row = db.execute(
            """SELECT s.label, s.map_layers, s.id AS survey, j.id AS job
            FROM surveys s JOIN jobs j ON j.id=s.published_job AND j.survey=s.id
            WHERE lower(s.slug)=lower(%s) AND s.published AND NOT s.deleted AND j.state='completed'
            ORDER BY j.created DESC LIMIT 1""", (slug,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Published survey not found")
    return row


@app.get("/api/v2/published/{slug}", dependencies=[Depends(authenticate)])
def publication(slug: str):
    row = published_run(slug)
    return {"label": row["label"], "job": row["job"], "layers": row["map_layers"]}


@app.get("/api/v2/published/{slug}/files/{job}/{filename:path}", dependencies=[Depends(authenticate)])
def published_file(slug: str, job: UUID, filename: str):
    row = published_run(slug)
    if row["job"] != job:
        raise HTTPException(404, "Reload the survey map for the latest run")
    if row["map_layers"] == "route" and filename != "route.geojson":
        raise HTTPException(404)
    if row["map_layers"] == "points" and filename == "route.geojson":
        raise HTTPException(404)
    return artifact(row["survey"], job, filename)


app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/{slug}", dependencies=[Depends(authenticate)])
def published_page(slug: str):
    published_run(slug)
    return FileResponse(WEB / "published.html", headers={"Cache-Control": "private, no-store"})
