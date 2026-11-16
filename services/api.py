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
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from processor import preflight
from runtime import ROOT, connect, migrate, run_path

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


def survey_row(db, survey, lock=False):
    sql = "SELECT id,label,created,validation,published,slug FROM surveys WHERE id=%s AND NOT deleted"
    row = db.execute(sql + (" FOR UPDATE" if lock else ""), (survey,)).fetchone()
    if not row:
        raise HTTPException(404, "Survey not found")
    return row


def idle(db, survey):
    if db.execute("SELECT 1 FROM jobs WHERE survey=%s AND state IN ('queued','running')", (survey,)).fetchone():
        raise HTTPException(409, "A job is active for this survey")


def sources(db, survey):
    rows = db.execute("SELECT kind,filename,storage,sha256,bytes FROM sources WHERE survey=%s ORDER BY kind", (survey,))
    return {row["kind"]: row for row in rows}


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


@app.get("/health")
def health():
    with connect() as db:
        db.execute("SELECT 1 FROM surveys LIMIT 1")
    return {"status": "ok"}


@app.get("/", dependencies=[Depends(authenticate)])
def index():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/v2/surveys", dependencies=[Depends(authenticate)])
def catalog():
    with connect() as db:
        return db.execute("SELECT id,label,created,published FROM surveys WHERE NOT deleted ORDER BY created DESC").fetchall()


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
            {key: value for key, value in item.items() if key != "storage"}
            for item in sources(db, survey).values()
        ]
        row["jobs"] = db.execute(
            "SELECT id,state,progress,error,metadata,settings FROM jobs WHERE survey=%s ORDER BY created DESC", (survey,)
        ).fetchall()
        return row


@app.put("/api/v2/surveys/{survey}/assets/{filename}", dependencies=[Depends(authenticate)])
async def upload(survey: UUID, filename: str, request: Request):
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
            current = sources(db, survey)
            old = current.get(kind)
            if old and old["sha256"] == checksum and old["filename"] == filename:
                return {"kind": kind, "bytes": size, "duplicate": True}
            if (kind == "zip" and set(current) - {"zip"}) or (kind != "zip" and "zip" in current):
                raise HTTPException(409, "Use a new survey to switch between ZIP and separate files")
            db.execute(
                """INSERT INTO sources VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (survey,kind) DO UPDATE SET filename=excluded.filename,
                storage=excluded.storage,sha256=excluded.sha256,bytes=excluded.bytes""",
                (survey, kind, filename, str(path.relative_to(ROOT)), checksum, size),
            )
            db.execute("UPDATE surveys SET validation=NULL WHERE id=%s", (survey,))
        keep = True
        return {"kind": kind, "bytes": size, "duplicate": False}
    finally:
        if not keep:
            path.unlink(missing_ok=True)
            asset.rmdir()


def source_paths(rows):
    return {kind: ROOT / row["storage"] for kind, row in rows.items()}


@app.post("/api/v2/surveys/{survey}/validate", dependencies=[Depends(authenticate)])
def validate(survey: UUID):
    with connect() as db:
        survey_row(db, survey, True)
        idle(db, survey)
        paths = source_paths(sources(db, survey))
        report = preflight.validate(paths.get("video"), paths.get("track"), paths.get("zip"), 20, True)
        db.execute("UPDATE surveys SET validation=%s WHERE id=%s", (Jsonb(report), survey))
        return report


@app.post("/api/v2/surveys/{survey}/process", status_code=202, dependencies=[Depends(authenticate)])
def enqueue(survey: UUID, settings: Settings):
    with connect() as db:
        row = survey_row(db, survey, True)
        if not (row["validation"] or {}).get("can_process"):
            raise HTTPException(409, "Validate a complete input pair first")
        rows = sources(db, survey)
        config = settings.model_dump()
        duration_ms = row["validation"]["video"]["duration_seconds"] * 1000
        if any(point.video_elapsed_ms > duration_ms for point in settings.manual_points):
            raise HTTPException(422, "A photo point is beyond the end of the video")
        # Cache compatibility with completed jobs created before these settings existed.
        if not config["rotation"]:
            config.pop("rotation")
        if not config["manual_points"]:
            config.pop("manual_points")
        fingerprint = hashlib.sha256(json.dumps([rows, config], sort_keys=True).encode()).hexdigest()
        existing = db.execute(
            """SELECT id,state FROM jobs WHERE survey=%s AND fingerprint=%s
            AND state IN ('queued','running','completed') ORDER BY created DESC LIMIT 1""",
            (survey, fingerprint),
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
            "INSERT INTO jobs (id,survey,fingerprint,state,settings) VALUES (%s,%s,%s,'queued',%s)",
            (job, survey, fingerprint, Jsonb(config)),
        )
        return {"id": job, "state": "queued"}


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
        db.execute("UPDATE surveys SET deleted=true,published=false WHERE id=%s", (survey,))
    return {"deleted": True}


@app.post("/api/v2/surveys/{survey}/publication/{action}", dependencies=[Depends(authenticate)])
def publish(survey: UUID, action: str):
    if action not in {"publish", "unpublish"}:
        raise HTTPException(404)
    with connect() as db:
        survey_row(db, survey, True)
        if action == "publish" and not db.execute(
            "SELECT 1 FROM jobs WHERE survey=%s AND state='completed'", (survey,)
        ).fetchone():
            raise HTTPException(409, "Complete a run before publishing")
        db.execute("UPDATE surveys SET published=%s WHERE id=%s", (action == "publish", survey))
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
            """SELECT s.label, s.id AS survey, j.id AS job
            FROM surveys s JOIN jobs j ON j.survey=s.id
            WHERE lower(s.slug)=lower(%s) AND s.published AND NOT s.deleted AND j.state='completed'
            ORDER BY j.created DESC LIMIT 1""", (slug,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Published survey not found")
    return row


@app.get("/api/v2/published/{slug}", dependencies=[Depends(authenticate)])
def publication(slug: str):
    row = published_run(slug)
    return {"label": row["label"], "job": row["job"]}


@app.get("/api/v2/published/{slug}/files/{job}/{filename:path}", dependencies=[Depends(authenticate)])
def published_file(slug: str, job: UUID, filename: str):
    row = published_run(slug)
    if row["job"] != job:
        raise HTTPException(404, "Reload the survey map for the latest run")
    return artifact(row["survey"], job, filename)


app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/{slug}", dependencies=[Depends(authenticate)])
def published_page(slug: str):
    published_run(slug)
    return FileResponse(WEB / "published.html", headers={"Cache-Control": "private, no-store"})
