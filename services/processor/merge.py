"""Combine separately timed recording outputs into one survey export."""
import shutil

from .exports import package_run, read_json, write_json, write_points


def combine(recordings, output, checkpoint):
    (output / "images").mkdir(parents=True)
    points, routes, manifests = [], [], []
    for number, (recording, folder, manifest) in enumerate(recordings, 1):
        manifests.append({"recording": recording, **manifest})
        for feature in read_json(folder / "points.geojson")["features"]:
            properties = feature["properties"]
            filename = f"images/{len(points):06d}.jpg"
            shutil.move(folder / properties["image_path"], output / filename)
            properties.update(frame_index=len(points), image_path=filename, recording_number=number)
            points.append(feature)
        routes.extend(read_json(folder / "route.geojson")["features"])
    checkpoint(95)
    if not points:
        raise ValueError("No video frames were selected")
    write_points(output, points)
    write_json(output / "route.geojson", {"type": "FeatureCollection", "features": routes})
    report = {
        "schema_version": "2.0-draft", "frame_count": len(points),
        "manual_points_added": sum(r["manual_points_added"] for r in manifests),
        "recordings": manifests,
        "corrected_points": sum(r["corrected_points"] for r in manifests),
    }
    write_json(output / "manifest.json", report)
    write_json(output / "qa_report.json", report)
    package_run(output)
    checkpoint(99)
    return report
