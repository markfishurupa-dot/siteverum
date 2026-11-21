import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.processor.exports import create_gpkg
from services.processor.process import sampled_fixes


class SamplingAndGpkgTests(unittest.TestCase):
    def test_zero_accuracy_fix_is_not_filtered_out(self):
        fixes = [
            {"video_elapsed_ms": "1000", "lat": "24.7136", "lon": "46.6753", "accuracy_m": 0.0},
            {"video_elapsed_ms": "2000", "lat": "24.7138", "lon": "46.6753", "accuracy_m": "0.0"},
        ]
        selected = sampled_fixes(fixes, "gps_fix", 1.0, max_accuracy=5.0)
        self.assertEqual(len(selected), 2)

    def test_time_interpolation_updates_telemetry_and_wraps_bearing(self):
        fixes = [
            {
                "timestamp_utc": "1700000001000",
                "video_elapsed_ms": "1000",
                "lat": "24.713600",
                "lon": "46.675300",
                "accuracy_m": "2.0",
                "bearing": "350.0",
                "speed_mps": "4.0",
                "alt_m": "600.0",
            },
            {
                "timestamp_utc": "1700000005000",
                "video_elapsed_ms": "5000",
                "lat": "24.713960",
                "lon": "46.675300",
                "accuracy_m": "4.0",
                "bearing": "10.0",
                "speed_mps": "12.0",
                "alt_m": "620.0",
            },
        ]
        selected = sampled_fixes(fixes, "time", 2.0, max_accuracy=None)
        self.assertEqual(len(selected), 3)
        mid = selected[1]
        self.assertEqual(mid["video_elapsed_ms"], 3000)
        self.assertEqual(mid["timestamp_utc"], 1700000003000)
        self.assertAlmostEqual(mid["bearing"], 0.0, places=2)
        self.assertAlmostEqual(mid["speed_mps"], 8.0, places=4)
        self.assertAlmostEqual(mid["alt_m"], 610.0, places=4)
        self.assertAlmostEqual(mid["accuracy_m"], 3.0, places=4)

    def test_distance_sampling_handles_stationary_duplicate_coordinates(self):
        fixes = [
            {"video_elapsed_ms": "1000", "lat": "24.713600", "lon": "46.675300"},
            {"video_elapsed_ms": "2000", "lat": "24.713600", "lon": "46.675300"},
            {"video_elapsed_ms": "3000", "lat": "24.713780", "lon": "46.675300"},
        ]
        selected = sampled_fixes(fixes, "distance", 10.0, max_accuracy=None)
        self.assertGreaterEqual(len(selected), 2)

    def test_gpkg_populates_bbox_and_preserves_telemetry(self):
        with tempfile.TemporaryDirectory() as folder:
            gpkg = Path(folder) / "points.gpkg"
            create_gpkg(gpkg, [
                {
                    "frame_index": 0, "image_path": "images/000000.jpg", "requested_ms": 1000,
                    "actual_pts": 1.0, "lat": 6.367675, "lon": 2.338773, "bearing": 180.5,
                    "accuracy_m": "2.3", "speed_mps": "6.1", "alt_m": "24.5",
                    "manual": False, "interpolated": False,
                },
                {
                    "frame_index": 1, "image_path": "images/000001.jpg", "requested_ms": 2000,
                    "actual_pts": 2.0, "lat": 6.377183, "lon": 2.342107, "bearing": "",
                    "accuracy_m": "", "speed_mps": "", "alt_m": "",
                    "manual": True, "interpolated": True,
                },
            ])
            con = sqlite3.connect(gpkg)
            try:
                bbox = con.execute(
                    "SELECT min_x, min_y, max_x, max_y FROM gpkg_contents WHERE table_name='points'"
                ).fetchone()
                self.assertEqual(bbox, (2.338773, 6.367675, 2.342107, 6.377183))
                row0 = con.execute(
                    "SELECT bearing, accuracy_m, speed_mps, alt_m, manual, interpolated FROM points WHERE frame_index=0"
                ).fetchone()
                self.assertEqual(row0, (180.5, 2.3, 6.1, 24.5, 0, 0))
                row1 = con.execute(
                    "SELECT bearing, accuracy_m, speed_mps, alt_m, manual, interpolated FROM points WHERE frame_index=1"
                ).fetchone()
                self.assertEqual(row1, (None, None, None, None, 1, 1))
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()
