"""Build an immutable export revision with one coordinate correction."""
import os
from pathlib import Path

from .coordinates import apply_correction, point_identity
from .exports import package_run, read_json, write_json, write_points


def copy_with_edit(parent: Path, target: Path, sequence, coordinates, checkpoint):
    points = read_json(parent / "points.geojson")
    manifest = read_json(parent / "manifest.json")
    feature = points["features"][sequence]
    properties = feature["properties"]
    recording_number = properties.get("recording_number", 1)
    recording = manifest["recordings"][recording_number - 1] if "recordings" in manifest else manifest
    identity = point_identity(properties, recording, feature["geometry"]["coordinates"])
    apply_correction(feature, identity, coordinates)

    target.mkdir()
    (target / "images").mkdir()
    routes = {}
    for point in points["features"]:
        photo = point["properties"]["image_path"]
        os.link(parent / photo, target / photo)
        if not point["properties"].get("manual"):
            number = point["properties"].get("recording_number", 1)
            routes.setdefault(number, []).append(point["geometry"]["coordinates"])
    checkpoint(60)
    route = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {},
         "geometry": {"type": "LineString", "coordinates": vertices}}
        for vertices in routes.values() if len(vertices) > 1
    ]}
    write_points(target, points["features"])
    write_json(target / "route.geojson", route)
    manifest["corrected_points"] = sum("original_coordinates" in p["properties"] for p in points["features"])
    write_json(target / "manifest.json", manifest)
    write_json(target / "qa_report.json", manifest)
    package_run(target)
    checkpoint(99)
    return manifest, identity
