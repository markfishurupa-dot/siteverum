import tempfile
import unittest
from pathlib import Path

from services.processor.edits import copy_with_edit
from services.processor.exports import read_json, write_json


class CoordinateCorrectionTests(unittest.TestCase):
    def test_correction_updates_only_the_selected_recording_route(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            parent = root / "previous"
            (parent / "images").mkdir(parents=True)
            points = []
            for sequence, coordinates in enumerate([[1, 1], [2, 2], [3, 3], [4, 4]]):
                filename = f"images/{sequence:06d}.jpg"
                (parent / filename).write_bytes(f"test payload {sequence}".encode())
                points.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": coordinates},
                    "properties": {
                        "frame_index": sequence, "image_path": filename, "recording_number": 1 + sequence // 2,
                        "source_frame_index": sequence % 2, "requested_ms": sequence * 100,
                        "actual_pts": sequence * .1, "manual": False,
                    },
                })
            write_json(parent / "points.geojson", {"type": "FeatureCollection", "features": points})
            write_json(parent / "manifest.json", {"recordings": [
                {"video_sha256": "video-one", "gps_sha256": "gps-one"},
                {"video_sha256": "video-two", "gps_sha256": "gps-two"},
            ]})
            edited = root / "edited"
            report, identity = copy_with_edit(parent, edited, 2, [3.1, 3.1], lambda _: None)
            self.assertEqual(report["corrected_points"], 1)
            routes = read_json(edited / "route.geojson")["features"]
            self.assertEqual(routes[0]["geometry"]["coordinates"], [[1, 1], [2, 2]])
            self.assertEqual(routes[1]["geometry"]["coordinates"], [[3.1, 3.1], [4, 4]])
            property_data = read_json(edited / "points.geojson")["features"][2]["properties"]
            self.assertEqual(property_data["original_coordinates"], [3, 3])
            self.assertEqual(property_data["correction_identity"], identity)
            self.assertEqual(read_json(parent / "points.geojson")["features"][2]["geometry"]["coordinates"], [3, 3])
            self.assertEqual((edited / "images/000002.jpg").read_bytes(), b"test payload 2")
