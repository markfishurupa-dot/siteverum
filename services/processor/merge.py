"""Combine separately timed recording outputs into one survey export."""
import csv
import json
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

from .process import create_gpkg


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def combine(recordings, output, checkpoint):
    (output / "images").mkdir(parents=True)
    rows, points, routes, manifests = [], [], [], []
    for number, (recording, folder, manifest) in enumerate(recordings, 1):
        manifests.append({"recording": recording, **manifest})
        for feature in read_json(folder / "points.geojson")["features"]:
            properties = feature["properties"]
            filename = f"images/{len(rows):06d}.jpg"
            shutil.move(folder / properties["image_path"], output / filename)
            properties.update(frame_index=len(rows), image_path=filename, recording_number=number)
            longitude, latitude = feature["geometry"]["coordinates"]
            rows.append({**properties, "lat": latitude, "lon": longitude})
            points.append(feature)
        routes.extend(read_json(folder / "route.geojson")["features"])
    checkpoint(95)
    if not rows:
        raise ValueError("No video frames were selected")
    with (output / "points.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    create_gpkg(output / "points.gpkg", rows)
    write_json(output / "points.geojson", {"type": "FeatureCollection", "features": points})
    write_json(output / "route.geojson", {"type": "FeatureCollection", "features": routes})
    report = {
        "schema_version": "2.0-draft", "frame_count": len(rows),
        "manual_points_added": sum(r["manual_points_added"] for r in manifests),
        "recordings": manifests,
    }
    write_json(output / "manifest.json", report)
    write_json(output / "qa_report.json", report)
    with ZipFile(output / "survey.zip", "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "survey.zip":
                archive.write(path, path.relative_to(output).as_posix())
    checkpoint(99)
    return report
