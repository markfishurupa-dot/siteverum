
"""Validate an isolated execution's output before any API-visible registration."""
import json
import re
import shutil
import stat
import subprocess
from uuid import uuid5

from psycopg.types.json import Jsonb

from module_processing import contracts as c

DEPTH = {"Point": 0, "MultiPoint": 1, "LineString": 1, "MultiLineString": 2, "Polygon": 2, "MultiPolygon": 3}


def geometry(value, kind):
    c.require(isinstance(value, dict) and value.get("type") == kind and "crs" not in value, "Unexpected geometry type")

    def coordinates(items, depth):
        c.require(isinstance(items, list) and bool(items), "Empty or malformed coordinates")
        if depth:
            for item in items:
                coordinates(item, depth - 1)
        else:
            c.require(len(items) == 2 and all(c.number(item) for item in items)
                      and abs(items[0]) <= 180 and abs(items[1]) <= 90, "Expected WGS84 longitude and latitude")

    coordinates(value.get("coordinates"), DEPTH[kind])
    return json.dumps(value, allow_nan=False)


def copy_output(source, destination):
    c.require(stat.S_ISDIR(source.lstat().st_mode), "Missing output directory")
    destination.mkdir()
    inventory = {}
    total = 0
    for path in source.rglob("*"):
        name = path.relative_to(source).as_posix()
        c.relative(name)
        summary = path.lstat()
        if stat.S_ISDIR(summary.st_mode):
            continue
        c.require(stat.S_ISREG(summary.st_mode) and summary.st_nlink == 1, "Output must contain only regular files")
        total += summary.st_size
        c.require(total <= c.OUTPUT_LIMIT and len(inventory) < 25000, "Output exceeds storage limits")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        inventory[name] = (target, c.digest(target), target.stat().st_size)
    return inventory


def image_derivative(path, source_sha):
    c.require(path.suffix.lower() == ".jpg" and c.digest(path) != source_sha, "Expected a distinct derived JPEG")
    with path.open("rb") as stream:
        c.require(stream.read(2) == b"\xff\xd8", "Invalid derivative JPEG")
    checked = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-nostdin", "-f", "mjpeg",
                              "-i", str(path), "-frames:v", "1", "-f", "null", "-"],
                             capture_output=True, timeout=10)
    c.require(checked.returncode == 0, "Derived JPEG could not be decoded")


def register(db, run, inventory, frames, pending):
    c.require("result.json" in inventory, "Missing result.json")
    result = c.read_json(inventory["result.json"][0], 8 * 1024**2)
    c.require(isinstance(result, dict) and result.get("contract") == c.OUTPUT
              and result.get("module") == run["module_id"] and result.get("version") == run["version"]
              and result.get("execution") == str(run["id"]) and result.get("status") == "completed",
              "Invalid output contract or execution identity")
    c.require(isinstance(result.get("statistics", {}), dict), "Invalid result statistics")
    warnings = result.get("warnings", [])
    c.require(isinstance(warnings, list) and len(warnings) <= 1000 and
              all(isinstance(item, str) and len(item) <= 500 for item in warnings), "Invalid result warnings")
    c.require(not result.get("errors"), "A completed result cannot contain processing errors")
    declared = result.get("files")
    c.require(isinstance(declared, dict) and set(declared) == set(inventory) - {"result.json"},
              "Result file inventory does not match output")
    for name, item in declared.items():
        c.require(isinstance(item, dict) and item.get("category") in run["manifest"]["outputs"]
                  and item.get("sha256") == inventory[name][1], f"Invalid category or checksum: {name}")
    artifacts = {**declared, "result.json": {"category": "report"}}
    artifact_rows = [{"path": name, "category": item["category"], "sha256": inventory[name][1],
                      "bytes": inventory[name][2]} for name, item in sorted(artifacts.items())]
    temporary = run["temporary"]
    if temporary:
        c.write_json(pending / "artifacts.json", artifact_rows)
    else:
        with db.cursor() as cursor:
            cursor.executemany("INSERT INTO module_artifacts VALUES (%s,%s,%s,%s,%s)",
                               [(run["id"], item["path"], item["category"], item["sha256"], item["bytes"])
                                for item in artifact_rows])
    layers = result.get("layers")
    c.require(isinstance(layers, list) and len(layers) <= 24, "Invalid result layers")
    layer_ids = set()
    total = 0
    review_bytes = 0
    for layer in layers:
        c.require(isinstance(layer, dict) and c.matches(c.ID, layer.get("id"))
                  and layer["id"] not in layer_ids and layer.get("geometry") in c.GEOMETRIES
                  and layer.get("crs") == "EPSG:4326" and type(layer.get("count")) is int, "Invalid result layer declaration")
        layer_ids.add(layer["id"])
        name = str(c.relative(layer.get("path")))
        c.require(declared.get(name, {}).get("category") == "vector", "Layer must reference a vector artifact")
        collection = c.read_json(inventory[name][0])
        c.require(isinstance(collection, dict) and collection.get("type") == "FeatureCollection"
                  and "crs" not in collection and isinstance(collection.get("features"), list)
                  and layer.get("count") == len(collection["features"]), "Invalid layer feature collection")
        total += len(collection["features"])
        c.require(total <= 100000, "Too many vector features")
        feature_rows = []
        evidence_rows = []
        temporary_features = []
        seen = set()
        for feature in collection["features"]:
            c.require(isinstance(feature, dict) and feature.get("type") == "Feature"
                      and c.matches(r"[A-Za-z0-9_.-]{1,120}", feature.get("id"))
                      and feature["id"] not in seen and isinstance(feature.get("properties"), dict),
                      "Invalid or duplicate feature")
            source_id = feature["id"]
            seen.add(source_id)
            identity = uuid5(run["id"], f"{layer['id']}/{source_id}")
            estimate = geometry(feature.get("geometry"), layer["geometry"])
            original = geometry(feature.get("original_geometry", feature["geometry"]), layer["geometry"])
            feature_rows.append((identity, run["id"], layer["id"], source_id, original, estimate, Jsonb(feature["properties"])))
            photos = []
            observations = feature.get("evidence", [])
            c.require(isinstance(observations, list) and len(observations) <= 1000, "Invalid feature evidence")
            for obs in observations:
                c.require(isinstance(obs, dict) and type(obs.get("sequence")) is int and obs["sequence"] in frames,
                          "Evidence references an unknown frame")
                bbox = obs.get("bbox")
                c.require(isinstance(bbox, list) and len(bbox) == 4
                          and all(c.number(value) and 0 <= value <= 1 for value in bbox)
                          and bbox[0] < bbox[2] and bbox[1] < bbox[3], "Invalid normalized evidence box")
                if temporary:
                    image = frames[obs["sequence"]]["image_path"]
                    url = f"/api/v2/surveys/{run['survey']}/runs/{run['source_job']}/{image}"
                    photos.append({"sequence": obs["sequence"], "bbox": bbox, "url": url})
                else:
                    evidence_rows.append((identity, obs["sequence"], Jsonb(bbox), Jsonb(obs)))
            if temporary:
                temporary_features.append({
                    "type": "Feature", "id": str(identity), "geometry": feature["geometry"],
                    "properties": {**feature["properties"], "source_id": source_id, "layer": layer["id"],
                                   "review_state": "pending", "original_geometry": json.loads(original),
                                   "estimated_geometry": feature["geometry"], "updated": None},
                    "evidence": photos,
                })
        if temporary:
            shapes = [shape for row in feature_rows for shape in row[4:6]]
            for offset in range(0, len(shapes), 1000):
                invalid = db.execute("""SELECT 1 FROM unnest(%s::text[]) AS input(geojson)
                    CROSS JOIN LATERAL ST_GeomFromGeoJSON(input.geojson) AS geom(shape)
                    WHERE ST_IsEmpty(shape) OR NOT ST_IsValid(shape) LIMIT 1""",
                                     (shapes[offset:offset + 1000],)).fetchone()
                c.require(not invalid, "Invalid spatial topology")
            index = pending / f"layer-{layer['id']}.json"
            c.write_json(index, sorted(temporary_features, key=lambda item: item["properties"]["source_id"]))
            review_bytes += index.stat().st_size
            c.require(review_bytes <= c.OUTPUT_LIMIT, "Temporary review data exceeds storage limits")
        else:
            with db.cursor() as cursor:
                cursor.executemany("""INSERT INTO module_features(id,run,layer,source_id,original,estimated,properties)
                        VALUES (%s,%s,%s,%s,ST_GeomFromGeoJSON(%s),ST_GeomFromGeoJSON(%s),%s)""", feature_rows)
                cursor.executemany("INSERT INTO module_evidence(feature,sequence,bbox,details) VALUES (%s,%s,%s,%s)", evidence_rows)
    if not temporary:
        c.require(not db.execute("""SELECT 1 FROM module_features WHERE run=%s AND
                                    (ST_IsEmpty(original) OR ST_IsEmpty(estimated) OR
                                     NOT ST_IsValid(original) OR NOT ST_IsValid(estimated)) LIMIT 1""",
                                 (run["id"],)).fetchone(), "Invalid spatial topology")
    derivatives = result.get("derivatives", [])
    c.require(isinstance(derivatives, list) and len(derivatives) <= len(frames), "Invalid derivative inventory")
    if derivatives:
        c.require(not temporary and run["manifest"]["stage"] == "pre_publication", "Unexpected image derivatives")
    sequences = set()
    paths = set()
    for derivative in derivatives:
        c.require(isinstance(derivative, dict) and type(derivative.get("sequence")) is int,
                  "Invalid derivative source reference")
        sequence = derivative["sequence"]
        name = str(c.relative(derivative.get("path")))
        c.require(sequence in frames and sequence not in sequences and name not in paths
                  and derivative.get("source_sha256") == frames[sequence]["sha256"]
                  and declared.get(name, {}).get("category") == "image"
                  and isinstance(derivative.get("metadata"), dict), "Invalid derivative mapping")
        sequences.add(sequence)
        paths.add(name)
        image_derivative(inventory[name][0], frames[sequence]["sha256"])
        db.execute("INSERT INTO module_derivatives VALUES (%s,%s,%s,%s)",
                   (run["id"], sequence, name, Jsonb(derivative["metadata"])))
    return {key: result[key] for key in ("layers", "statistics", "warnings") if key in result}
