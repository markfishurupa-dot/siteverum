
import csv
import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from uuid import UUID, uuid4
from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from module_processing import contracts as c
from module_processing.storage import PACKAGES, POLE_MODELS, TEMP_SECONDS, package_path, result_root
from runtime import connect
from processor.module_exports import write_layer_geopackage

router = APIRouter(prefix="/api/v2")

RUN_QUERY = f"""
    SELECT r.*,m.sha256,p.name AS model_name,p.sha256 AS model_sha256,j.fingerprint AS source_fingerprint,m.manifest->>'stage' AS stage,
    CASE WHEN r.temporary AND r.state='completed' THEN
      r.finished + {TEMP_SECONDS} * interval '1 second' END AS expires_at,
    (r.temporary AND r.state='completed' AND r.finished <= now() - {TEMP_SECONDS} * interval '1 second') AS expired,
    (r.source_job IS DISTINCT FROM (SELECT id FROM jobs WHERE survey=r.survey AND state='completed'
      ORDER BY created DESC,id DESC LIMIT 1) OR j.source_revision <> s.source_revision
      OR EXISTS (SELECT 1 FROM module_runs newer WHERE newer.survey=r.survey AND newer.module_id=r.module_id
        AND NOT newer.temporary AND newer.state='completed' AND (newer.created,newer.id)>(r.created,r.id))) AS stale
    FROM module_runs r JOIN modules m USING(module_id,version)
    JOIN surveys s ON s.id=r.survey JOIN jobs j ON j.id=r.source_job
    LEFT JOIN pole_models p ON p.id=r.pole_model
    WHERE NOT s.deleted
"""


def get_run(db, run, completed=False):
    row = db.execute(RUN_QUERY + " AND r.id=%s", (run,)).fetchone()
    if not row or (completed and row["state"] != "completed"):
        raise HTTPException(404, "Module result unavailable")
    hydrate_temporary_run(row)
    if completed and row["expired"]:
        raise HTTPException(410, "Temporary results have expired. Run the module again to regenerate them.")
    return row


def hydrate_temporary_run(row):
    if row["temporary"] and row["state"] == "completed" and not row["expired"]:
        path = result_root(row) / str(row["id"]) / "summary.json"
        try:
            row["summary"] = c.read_json(path)
        except FileNotFoundError:
            row["expired"] = True
    return row


@router.get("/modules")
def modules():
    with connect() as db:
        return db.execute("SELECT * FROM modules ORDER BY module_id,installed DESC").fetchall()


@router.post("/modules/install", status_code=201)
async def install(request: Request):
    PACKAGES.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=PACKAGES, delete=False) as file:
        pending = PACKAGES / os.path.basename(file.name)
        try:
            size = 0
            async for block in request.stream():
                size += len(block)
                if size > c.PACKAGE_LIMIT:
                    raise HTTPException(413, "Module ZIP exceeds upload limit")
                file.write(block)
            file.close()
            manifest, checksum = await inspect_upload(pending)
            with connect() as db:
                db.execute("SELECT pg_advisory_xact_lock(183010)")
                existing = db.execute("SELECT * FROM modules WHERE module_id=%s AND version=%s",
                                      (manifest["id"], manifest["version"])).fetchone()
                if existing:
                    if existing["sha256"] != checksum:
                        raise HTTPException(409, "This module version already has a different package")
                    return existing
                target = package_path(checksum)
                os.replace(pending, target)
                return db.execute(
                    """INSERT INTO modules(module_id,version,manifest,sha256) VALUES (%s,%s,%s,%s) RETURNING *""",
                    (manifest["id"], manifest["version"], Jsonb(manifest), checksum),
                ).fetchone()
        finally:
            file.close()
            pending.unlink(missing_ok=True)


async def inspect_upload(path):
    from starlette.concurrency import run_in_threadpool

    def inspect():
        return c.inspect_package(path), c.digest(path)

    try:
        return await run_in_threadpool(inspect)
    except (ValueError, TypeError, UnicodeError, zipfile.BadZipFile, yaml.YAMLError, RuntimeError) as exc:
        raise HTTPException(422, f"Invalid module package: {exc}") from exc


@router.get("/modules/{module_id}")
def module_versions(module_id: str):
    with connect() as db:
        rows = db.execute("SELECT * FROM modules WHERE module_id=%s ORDER BY installed DESC", (module_id,)).fetchall()
        if not rows:
            raise HTTPException(404, "Module not found")
        return rows


class ModuleState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


@router.patch("/modules/{module_id}/versions/{version}")
def change_version(module_id: str, version: str, data: ModuleState):
    with connect() as db:
        row = db.execute("UPDATE modules SET enabled=%s WHERE module_id=%s AND version=%s RETURNING *",
                         (data.enabled, module_id, version)).fetchone()
        if not row:
            raise HTTPException(404, "Module version not found")
        return row


@router.delete("/modules/{module_id}/versions/{version}")
def remove_version(module_id: str, version: str):
    with connect() as db:
        db.execute("SELECT pg_advisory_lock(183010)")
        identity = (module_id, version)
        row = db.execute("SELECT sha256 FROM modules WHERE module_id=%s AND version=%s FOR UPDATE", identity).fetchone()
        if not row:
            raise HTTPException(404, "Module version not found")
        if db.execute("SELECT 1 FROM module_runs WHERE module_id=%s AND version=%s LIMIT 1", identity).fetchone():
            raise HTTPException(409, "Execution history references this version")
        db.execute("DELETE FROM modules WHERE module_id=%s AND version=%s", identity)
        db.commit()
        package_path(row["sha256"]).unlink(missing_ok=True)
    return {"removed": True}


PoleClass = Literal["pole_beton", "pole_generic", "pole_metal", "pole_wood"]
POLE_CLASSES = set(PoleClass.__args__)
MODEL_LIMIT = 512 * 1024**2


@router.get("/pole-models")
def pole_models():
    with connect() as db:
        return db.execute("SELECT id,name,sha256,labels FROM pole_models ORDER BY added_at DESC,id").fetchall()


@router.post("/pole-models", status_code=201)
async def upload_pole_model(request: Request, name: str = Query(min_length=1, max_length=150),
                            labels: str = Query(default="{}", max_length=4096)):
    if not name.lower().endswith(".pt") or Path(name).name != name or "/" in name or chr(92) in name:
        raise HTTPException(422, "Choose an Ultralytics detection checkpoint ending in .pt")
    try:
        mapping = json.loads(labels)
        if not isinstance(mapping, dict) or any(not key.strip() or len(key) > 100 or
                not isinstance(value, str) or value not in POLE_CLASSES for key, value in mapping.items()):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Map each checkpoint label to a supported pole class") from exc

    POLE_MODELS.mkdir(parents=True, exist_ok=True)
    pending = None
    digest = hashlib.sha256()
    try:
        with tempfile.NamedTemporaryFile(dir=POLE_MODELS, delete=False) as stream:
            pending = Path(stream.name)
            size = 0
            async for block in request.stream():
                size += len(block)
                if size > MODEL_LIMIT:
                    raise HTTPException(413, "Checkpoint exceeds 512 MiB")
                digest.update(block)
                stream.write(block)
        # Check the checkpoint container without deserializing PyTorch data in the API.
        try:
            with zipfile.ZipFile(pending) as checkpoint:
                if not any(item.endswith("/data.pkl") for item in checkpoint.namelist()):
                    raise ValueError
        except (ValueError, zipfile.BadZipFile) as exc:
            raise HTTPException(422, "Invalid PyTorch checkpoint container") from exc
        checksum = digest.hexdigest()
        os.replace(pending, POLE_MODELS / (checksum + ".pt"))
        with connect() as db:
            return db.execute("""INSERT INTO pole_models(id,name,sha256,labels) VALUES (%s,%s,%s,%s)
                                 RETURNING id,name,sha256,labels""",
                              (uuid4(), name, checksum, Jsonb(mapping))).fetchone()
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(pattern=f"^{c.VERSION}$")
    parameters: dict = Field(default_factory=dict)
    temporary: bool = False
    pole_model: UUID | None = None
    request_key: str | None = Field(default=None, min_length=1, max_length=120)


@router.post("/surveys/{survey}/modules/{module_id}/runs", status_code=202)
def enqueue(survey: UUID, module_id: str, data: RunRequest):
    with connect() as db:
        current = db.execute("SELECT source_revision FROM surveys WHERE id=%s AND NOT deleted FOR UPDATE",
                             (survey,)).fetchone()
        if not current:
            raise HTTPException(404, "Survey not found")
        package = db.execute("SELECT * FROM modules WHERE module_id=%s AND version=%s FOR SHARE",
                             (module_id, data.version)).fetchone()
        if not package:
            raise HTTPException(404, "Module version not found")
        if data.pole_model is not None:
            if module_id != "poles-detection" or not package["manifest"].get("custom_checkpoint"):
                raise HTTPException(422, "This module version does not support custom checkpoints")
            if not db.execute("SELECT 1 FROM pole_models WHERE id=%s", (data.pole_model,)).fetchone():
                raise HTTPException(404, "Custom checkpoint not found")
        if data.temporary and package["manifest"]["stage"] != "post_processing":
            raise HTTPException(422, "Publication preparation requires retained results")
        try:
            config = c.parameters(package["manifest"], data.parameters)
        except c.ContractError as exc:
            raise HTTPException(422, str(exc)) from exc
        if data.request_key:
            previous = db.execute("SELECT id,version,configuration,temporary,pole_model FROM module_runs WHERE survey=%s AND module_id=%s AND requested_key=%s",
                                  (survey, module_id, data.request_key)).fetchone()
            if previous:
                if previous["version"] != data.version or previous["configuration"] != config or previous["temporary"] != data.temporary or previous["pole_model"] != data.pole_model:
                    raise HTTPException(409, "Request key already used with different settings")
                return get_run(db, previous["id"])
        if not package["enabled"]:
            raise HTTPException(409, "Module version is disabled")
        job = db.execute("""SELECT id,source_revision FROM jobs WHERE survey=%s AND state='completed'
                          ORDER BY created DESC,id DESC LIMIT 1""", (survey,)).fetchone()
        if not job or job["source_revision"] != current["source_revision"]:
            raise HTTPException(409, "Process the current survey sources first")
        fingerprint_parts = [str(job["id"]), package["sha256"], config]
        if data.pole_model is not None:
            fingerprint_parts.append(str(data.pole_model))
        if data.temporary:
            fingerprint_parts.append("temporary")
        fingerprint = hashlib.sha256(json.dumps(fingerprint_parts, sort_keys=True).encode()).hexdigest()
        active = db.execute("SELECT id FROM module_runs WHERE fingerprint=%s AND state IN ('queued','running')",
                            (fingerprint,)).fetchone()
        if active:
            if data.request_key:
                raise HTTPException(409, "An identical job is already active")
            return get_run(db, active["id"])
        run = uuid4()
        db.execute("""INSERT INTO module_runs(id,module_id,version,survey,source_job,configuration,
                       fingerprint,state,requested_key,temporary,pole_model) VALUES (%s,%s,%s,%s,%s,%s,%s,'queued',%s,%s,%s)""",
                   (run, module_id, data.version, survey, job["id"], Jsonb(config), fingerprint, data.request_key, data.temporary, data.pole_model))
        return get_run(db, run)


@router.get("/surveys/{survey}/module-runs")
def survey_runs(survey: UUID, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                source_job: UUID | None = None):
    conditions = " AND r.survey=%s"
    parameters = [survey]
    if source_job is not None:
        conditions += " AND r.source_job=%s"
        parameters.append(source_job)
    with connect() as db:
        rows = db.execute(RUN_QUERY + conditions + " ORDER BY r.created DESC,r.id DESC LIMIT %s OFFSET %s",
                          (*parameters, limit, offset)).fetchall()
        return [hydrate_temporary_run(row) for row in rows]


@router.get("/module-runs/{run}")
def run_detail(run: UUID):
    with connect() as db:
        return get_run(db, run)


@router.post("/module-runs/{run}/cancel")
def cancel(run: UUID):
    with connect() as db:
        get_run(db, run)
        db.execute("""UPDATE module_runs SET state='cancelled',finished=now()
                    WHERE id=%s AND state IN ('queued','running')""", (run,))
        return get_run(db, run)


@router.get("/module-runs/{run}/logs")
def logs(run: UUID):
    from module_processing.storage import OUTBOX

    with connect() as db:
        row = get_run(db, run)
    history = result_root(row) / str(run) / "execution.log"
    path = history if history.is_file() else OUTBOX / str(run) / "execution.log"
    entries = ""
    if path.is_file() and not path.is_symlink() and not path.parent.is_symlink():
        try:
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 65536))
                entries = stream.read(65536).decode(errors="replace")
        except FileNotFoundError:
            pass
    return {"state": row["state"], "error": row["error"], "tail": entries}


def temporary_json(run, filename, limit=32 * 1024**2):
    try:
        return c.read_json(result_root(run) / str(run["id"]) / filename, limit)
    except FileNotFoundError as exc:
        raise HTTPException(410, "Temporary results are no longer available") from exc


@router.get("/module-runs/{run}/artifacts")
def artifacts(run: UUID):
    with connect() as db:
        row = get_run(db, run, True)
        if row["temporary"]:
            return temporary_json(row, "artifacts.json")
        return db.execute("SELECT path,category,sha256,bytes FROM module_artifacts WHERE run=%s ORDER BY path",
                          (run,)).fetchall()


@router.get("/module-runs/{run}/artifacts/{filename:path}")
def download(run: UUID, filename: str):
    try:
        path = c.relative(filename)
    except c.ContractError as exc:
        raise HTTPException(404) from exc
    with connect() as db:
        row = get_run(db, run, True)
        if row["temporary"]:
            found = any(item["path"] == filename for item in temporary_json(row, "artifacts.json"))
        else:
            found = db.execute("SELECT 1 FROM module_artifacts WHERE run=%s AND path=%s", (run, filename)).fetchone()
        if not found:
            raise HTTPException(404)
    target = result_root(row) / str(run) / "output" / path
    if not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, filename=path.name, media_type="application/octet-stream",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


def collection(rows):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": str(row["id"]), "geometry": row["geometry"],
         "properties": {**row["properties"], "source_id": row["source_id"], "layer": row["layer"],
                        "review_state": row["review_state"], "original_geometry": row["original"],
                        "estimated_geometry": row["estimated"], "updated": row["updated"].isoformat() if row["updated"] else None}}
        for row in rows
    ]}


def feature_rows(db, run, layer, approved, limit, offset):
    return db.execute("""SELECT id,source_id,layer,properties,review_state,updated,
                    ST_AsGeoJSON(COALESCE(reviewed,estimated),15)::jsonb AS geometry,
                    ST_AsGeoJSON(original,15)::jsonb AS original, ST_AsGeoJSON(estimated,15)::jsonb AS estimated
                    FROM module_features WHERE run=%s AND (%s::text IS NULL OR layer=%s)
                    AND (NOT %s OR review_state='approved') ORDER BY layer,source_id LIMIT %s OFFSET %s""",
                      (run, layer, layer, approved, limit, offset)).fetchall()


@router.get("/module-runs/{run}/features")
def features(run: UUID, layer: str | None = None, approved: bool = False,
             limit: int = Query(500, ge=1, le=2000), offset: int = Query(0, ge=0)):
    with connect() as db:
        row = get_run(db, run, True)
        if row["temporary"]:
            if layer is not None and not c.matches(c.ID, layer):
                raise HTTPException(404, "Unknown result layer")
            layers = [spec["id"] for spec in row["summary"]["layers"] if layer is None or layer == spec["id"]]
            items = [item for key in sorted(layers) for item in temporary_json(row, f"layer-{key}.json", c.OUTPUT_LIMIT)]
            return {"type": "FeatureCollection", "features": [] if approved else items[offset:offset + limit]}
        payload = collection(feature_rows(db, run, layer, approved, limit, offset))
        payload["total"] = db.execute("""SELECT count(*) AS count FROM module_features
            WHERE run=%s AND (%s::text IS NULL OR layer=%s) AND (NOT %s OR review_state='approved')""",
            (run, layer, layer, approved)).fetchone()["count"]
        return payload


class ManualPole(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    pole_class: PoleClass = "pole_generic"


@router.post("/module-runs/{run}/poles", status_code=201)
def add_pole(run: UUID, data: ManualPole):
    with connect() as db:
        row = get_run(db, run, True)
        if row["temporary"]:
            raise HTTPException(422, "Add poles in the browser for temporary results")
        if row["module_id"] != "poles-detection" or not any(
                layer["id"] == "poles" and layer["geometry"] == "Point" for layer in row["summary"]["layers"]):
            raise HTTPException(422, "A completed electrical poles layer is required")
        source_id = f"manual-{data.id}"
        inserted = db.execute("""WITH location AS (SELECT ST_SetSRID(ST_MakePoint(%s,%s),4326) AS geom)
            INSERT INTO module_features(id,run,layer,source_id,original,estimated,properties,review_state,updated)
            SELECT %s,%s,'poles',%s,geom,geom,%s,'approved',now() FROM location
            ON CONFLICT (id) DO NOTHING RETURNING id""",
            (data.lon, data.lat, data.id, run, source_id, Jsonb({"pole_class": data.pole_class, "origin": "manual"}))).fetchone()
        if inserted:
            db.execute("""INSERT INTO module_feature_reviews(feature,state,geometry)
                          SELECT id,'approved',estimated FROM module_features WHERE id=%s""", (data.id,))
        else:
            existing = db.execute("SELECT 1 FROM module_features WHERE id=%s AND run=%s AND source_id=%s",
                                  (data.id, run, source_id)).fetchone()
            if not existing:
                raise HTTPException(409, "Pole ID already in use")
        return {"id": data.id}


@router.get("/module-runs/{run}/export")
def export(run: UUID, layer: str, format: str = "geojson", approved: bool = False):
    with connect() as db:
        row = get_run(db, run, True)
        if row["temporary"]:
            raise HTTPException(422, "Use the map review download or download the original execution files")
        spec = next((spec for spec in row["summary"]["layers"] if spec["id"] == layer), None)
        if not spec:
            raise HTTPException(404, "Unknown result layer")
        features = collection(feature_rows(db, run, layer, approved, 100001, 0))
    if len(features["features"]) > 100000:
        raise HTTPException(413, "Layer exceeds the export limit")
    if format == "geojson":
        data, media = json.dumps(features), "application/geo+json"
    elif format == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream)
        point = spec["geometry"] == "Point"
        writer.writerow(["id", "review_state", *(["lon", "lat"] if point else []), "geometry", "properties"])
        for item in features["features"]:
            writer.writerow([item["id"], item["properties"]["review_state"],
                             *(item["geometry"]["coordinates"] if point else []),
                             json.dumps(item["geometry"]), json.dumps(item["properties"])])
        data, media = stream.getvalue(), "text/csv"
    elif format == "gpkg":
        with tempfile.TemporaryDirectory() as temporary:
            from pathlib import Path

            path = Path(temporary) / "export.gpkg"
            write_layer_geopackage(path, layer, spec["geometry"], features["features"])
            data = path.read_bytes()
        media = "application/geopackage+sqlite3"
    else:
        raise HTTPException(422, "Supported formats are geojson, csv and gpkg")
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{layer}.{format}"',
                                                     "Cache-Control": "private, no-store"})


def get_feature(db, feature):
    row = db.execute("""SELECT f.*, GeometryType(f.estimated) AS geometry_type,r.survey,r.source_job
                      FROM module_features f JOIN module_runs r ON r.id=f.run JOIN surveys s ON s.id=r.survey
                      WHERE f.id=%s AND r.state='completed' AND NOT s.deleted FOR UPDATE OF f""", (feature,)).fetchone()
    if not row:
        raise HTTPException(404, "Feature not found")
    return row


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str | None = Field(default=None, pattern=r"^(pending|approved|rejected)$")
    lon: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)
    reset: bool = False


@router.patch("/module-features/{feature}")
def review(feature: UUID, data: Review):
    move = data.lon is not None or data.lat is not None
    if move and (data.lon is None or data.lat is None or data.reset):
        raise HTTPException(422, "Provide longitude and latitude together, or reset")
    with connect() as db:
        row = get_feature(db, feature)
        if move and row["geometry_type"] != "POINT":
            raise HTTPException(422, "Only point coordinates can be moved")
        updated = db.execute("""UPDATE module_features SET review_state=COALESCE(%s,review_state),updated=now(),
                    reviewed=CASE WHEN %s THEN NULL WHEN %s THEN ST_SetSRID(ST_MakePoint(%s,%s),4326)
                    ELSE reviewed END WHERE id=%s RETURNING review_state,updated""",
                             (data.state, data.reset, move, data.lon, data.lat, feature)).fetchone()
        db.execute("""INSERT INTO module_feature_reviews(feature,state,geometry)
                      SELECT id,review_state,reviewed FROM module_features WHERE id=%s""", (feature,))
        return updated


@router.get("/module-features/{feature}/evidence")
def evidence(feature: UUID):
    with connect() as db:
        row = get_feature(db, feature)
        entries = db.execute("""SELECT e.sequence,e.bbox,e.details,f.properties->>'image_path' AS photo
                  FROM module_evidence e JOIN frames f ON f.job=%s AND f.sequence=e.sequence
                  WHERE e.feature=%s ORDER BY e.id""", (row["source_job"], feature)).fetchall()
    for entry in entries:
        photo = entry.pop("photo")
        if photo and re.fullmatch(c.PHOTO, photo):
            entry["url"] = f"/api/v2/surveys/{row['survey']}/runs/{row['source_job']}/{photo}"
    return entries
