
"""Publication policy, immutable vector snapshots and derivative-only media lookup."""
from uuid import UUID

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from module_processing import contracts as c
from module_processing.routes import collection, feature_rows, router
from module_processing.storage import RESULTS
from runtime import connect


class PrivacyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_module: str | None = Field(default=None, pattern=f"^{c.ID}$")


class PublishedLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run: UUID
    layer: str = Field(pattern=f"^{c.ID}$")
    approved_only: bool = True


@router.put("/surveys/{survey}/privacy")
def configure_privacy(survey: UUID, policy: PrivacyPolicy):
    with connect() as db:
        found = db.execute("SELECT id FROM surveys WHERE id=%s AND NOT deleted FOR UPDATE", (survey,)).fetchone()
        if not found:
            raise HTTPException(404, "Survey not found")
        if policy.required_module and not db.execute(
            "SELECT 1 FROM modules WHERE module_id=%s AND manifest->>'stage'='pre_publication' LIMIT 1",
            (policy.required_module,),
        ).fetchone():
            raise HTTPException(422, "Install a pre-publication module before requiring it")
        db.execute("""UPDATE surveys SET published_derivative_run=CASE WHEN privacy_module IS DISTINCT FROM %s
                      THEN NULL ELSE published_derivative_run END,privacy_module=%s WHERE id=%s""",
                   (policy.required_module, policy.required_module, survey))
    return {"required_module": policy.required_module}


def derivative_path(run, name, checksum):
    try:
        target = RESULTS / str(run) / "output" / c.relative(name)
        if target.is_file() and not target.is_symlink() and c.digest(target) == checksum:
            return target
    except (c.ContractError, OSError) as exc:
        raise HTTPException(404, "Published derivative unavailable") from exc
    raise HTTPException(404, "Published derivative unavailable")


def choose_derivatives(db, survey, job, required, requested):
    if not required:
        if requested:
            raise HTTPException(422, "Set a survey privacy policy before selecting the derivative run")
        return None
    runs = db.execute("""SELECT r.id FROM module_runs r JOIN modules m USING(module_id,version)
                      WHERE r.survey=%s AND r.source_job=%s AND r.module_id=%s AND r.state='completed'
                        AND m.manifest->>'stage'='pre_publication' AND (%s::uuid IS NULL OR r.id=%s)
                      ORDER BY r.created DESC,r.id DESC LIMIT 1""", (survey, job, required, requested, requested)).fetchone()
    if not runs:
        raise HTTPException(409, "Complete the required privacy module against the current survey run")
    derivatives = db.execute("""SELECT f.sequence,d.path,a.sha256
        FROM frames f LEFT JOIN module_derivatives d ON d.run=%s AND d.sequence=f.sequence
        LEFT JOIN module_artifacts a ON a.run=d.run AND a.path=d.path WHERE f.job=%s""",
                             (runs["id"], job)).fetchall()
    if not derivatives or any(not item["path"] for item in derivatives):
        raise HTTPException(409, "The privacy result must contain a validated derivative for every photo")
    try:
        for item in derivatives:
            derivative_path(runs["id"], item["path"], item["sha256"])
    except (OSError, HTTPException) as exc:
        raise HTTPException(409, "A validated privacy derivative is missing or has changed") from exc
    return runs["id"]


def published_image(row, image):
    identity = row["published_derivative_run"]
    if not identity:
        raise HTTPException(404, "Photo access requires a completed privacy publication")
    with connect() as db:
        derivative = db.execute("""SELECT d.path,a.sha256
            FROM surveys s JOIN module_runs r ON r.id=s.published_derivative_run AND r.survey=s.id
            JOIN modules m USING(module_id,version)
            JOIN frames f ON f.job=s.published_job
            JOIN module_derivatives d ON d.run=r.id AND d.sequence=f.sequence
            JOIN module_artifacts a ON a.run=d.run AND a.path=d.path
            WHERE s.id=%s AND s.published AND NOT s.deleted
              AND s.published_job=%s AND s.published_derivative_run=%s AND s.privacy_module=m.module_id
              AND r.state='completed' AND r.source_job=s.published_job AND m.manifest->>'stage'='pre_publication'
              AND f.properties->>'image_path'=%s""",
                               (row["survey"], row["job"], identity, image)).fetchone()
    if not derivative:
        raise HTTPException(404, "Published derivative unavailable")
    return derivative_path(identity, derivative["path"], derivative["sha256"])


def save_layers(db, survey, job, entries):
    if entries is None:
        db.execute("""DELETE FROM published_module_layers p USING module_runs r
                      WHERE p.survey=%s AND p.run=r.id AND r.source_job<>%s""", (survey, job))
        return
    db.execute("DELETE FROM published_module_layers WHERE survey=%s", (survey,))
    seen = set()
    for item in entries:
        if (item.run, item.layer) in seen:
            raise HTTPException(422, "Duplicate published layer")
        seen.add((item.run, item.layer))
        source = db.execute("""SELECT r.summary,m.manifest->'public_properties' AS properties
            FROM module_runs r JOIN modules m USING(module_id,version)
            WHERE r.id=%s AND r.survey=%s AND r.source_job=%s AND r.state='completed'
              AND NOT r.temporary AND m.manifest->>'stage'='post_processing'""", (item.run, survey, job)).fetchone()
        if not source or not any(spec["id"] == item.layer for spec in source["summary"]["layers"]):
            raise HTTPException(409, "Choose a completed layer from the current survey run")
        rows = feature_rows(db, item.run, item.layer, item.approved_only, 20001, 0)
        if len(rows) > 20000:
            raise HTTPException(413, "Published layer exceeds 20,000 features")
        snapshot = collection(rows)
        allowed = set(source["properties"] or []) - {"source_images", "source_frames", "image_path"}
        for feature in snapshot["features"]:
            feature["properties"] = {key: value for key, value in feature["properties"].items()
                                     if key in allowed and (type(value) in (bool, int, float)
                                                            or c.matches(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,69}", value))}
        db.execute("INSERT INTO published_module_layers VALUES (%s,%s,%s,%s)",
                   (survey, item.run, item.layer, Jsonb(snapshot)))
