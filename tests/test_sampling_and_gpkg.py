import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.processor import process
from services.processor.edits import copy_with_edit
from services.processor.exports import create_gpkg, read_json, write_points
from services.processor.preflight import hash_file
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
        self.assertIsNone(mid["accuracy_m"])
        self.assertTrue(mid["interpolated"])
        self.assertEqual(mid["fix_gap_ms"], 4000)
        for observed, fix in zip((selected[0], selected[2]), fixes):
            self.assertEqual(observed, dict(fix, interpolated=False, fix_gap_ms=0))

    def test_interpolation_does_not_reuse_telemetry_from_either_endpoint(self):
        fixes = [
            {"video_elapsed_ms": 0, "lat": 0, "lon": 0, "bearing": "", "speed_mps": 5,
             "timestamp_utc": 1700000000000},
            {"video_elapsed_ms": 2000, "lat": 0, "lon": 0.0001, "bearing": 35, "alt_m": 100},
        ]
        mid = sampled_fixes(fixes, "time", 1, max_accuracy=None)[1]
        for key in ("alt_m", "speed_mps", "bearing", "accuracy_m", "timestamp_utc"):
            with self.subTest(key=key):
                self.assertIsNone(mid[key])

    def test_grid_retains_observed_fixes_after_outages(self):
        fixes = [
            {"video_elapsed_ms": 0, "lat": 0, "lon": 0},
            {"video_elapsed_ms": 12000, "lat": 0, "lon": 0.0001, "accuracy_m": 4},
        ]
        selected = sampled_fixes(fixes, "time", 2, max_accuracy=None)
        self.assertEqual(selected, [dict(fix, interpolated=False, fix_gap_ms=0) for fix in fixes])

    def test_distance_grid_preserves_endpoint_with_float_roundoff(self):
        fixes = [{"video_elapsed_ms": i * 1000, "lat": i, "lon": 0, "accuracy_m": i}
                 for i in range(4)]
        with patch.object(process.preflight, "haversine", return_value=0.3):
            selected = sampled_fixes(fixes, "distance", 0.3, max_accuracy=None)
        self.assertEqual(selected, [dict(fix, interpolated=False, fix_gap_ms=0) for fix in fixes])

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

    def assert_gpkg_schema(self, path):
        con = sqlite3.connect(path)
        try:
            columns = {row[1]: (row[2], row[3]) for row in con.execute("PRAGMA table_info(points)")}
            self.assertEqual(columns["geom"], ("POINT", 1))
            self.assertEqual(columns["timestamp_utc"], ("INTEGER", 0))
            self.assertEqual(columns["fix_gap_ms"], ("INTEGER", 1))
            foreign_keys = {(row[2], row[3], row[4]) for row in
                            con.execute("PRAGMA foreign_key_list(gpkg_geometry_columns)")}
            self.assertEqual(foreign_keys, {
                ("gpkg_contents", "table_name", "table_name"),
                ("gpkg_spatial_ref_sys", "srs_id", "srs_id"),
            })
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO gpkg_geometry_columns VALUES ('points','other','POINT',4326,0,0)")
        finally:
            con.close()

    def test_exported_telemetry_and_gpkg_revisions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            log = root / "track.csv"
            log.write_text(
                "video_elapsed_ms,timestamp_utc,lat,lon,accuracy_m,bearing,speed_mps,alt_m\n"
                "1000,1700000001000,24.713600,46.675300,2,359.997,4,600\n"
                "5000,1700000005000,24.713960,46.675300,4,359.999,,620\n",
                encoding="utf-8",
            )
            video = root / "video.mp4"
            video.touch()
            validated = {"can_process": True, "warnings": [], "gps": {"sha256": hash_file(log)},
                         "video": {"sha256": hash_file(video), "full_decode_passed": True}}

            def stub_extract(_video, rows, staging, _rotation, _progress):
                for row in rows:
                    (staging / row["image_path"]).touch()

            output = root / "run"
            with patch.object(process, "frame_times", return_value=list(range(6))), \
                    patch.object(process, "extract_frames", side_effect=stub_extract):
                process.run(video, log, output, sampling="time", interval=2, validated=validated,
                            manual_points=[{"video_elapsed_ms": 4000, "lat": 24.714, "lon": 46.6753,
                                            "accuracy_m": 99}], package=False)

            with (output / "points.csv").open(encoding="utf-8", newline="") as stream:
                csv_points = {int(row["requested_ms"]): row for row in csv.DictReader(stream)}
            self.assertEqual([row["timestamp_utc"] for row in csv_points.values()],
                             ["1700000001000", "1700000003000", "", "1700000005000"])
            self.assertEqual([row["accuracy_m"] for row in csv_points.values()], ["2", "", "", "4"])
            self.assertEqual(csv_points[3000]["bearing"], "0.0")
            self.assertEqual(csv_points[3000]["speed_mps"], "")

            features = read_json(output / "points.geojson")["features"]
            props = {f["properties"]["requested_ms"]: f["properties"] for f in features}
            self.assertEqual([p["timestamp_utc"] for p in props.values()],
                             [1700000001000, 1700000003000, None, 1700000005000])
            self.assertIsNone(props[3000]["accuracy_m"])
            self.assertIsNone(props[3000]["speed_mps"])
            self.assertEqual(props[3000]["bearing"], 0.0)
            self.assertTrue(props[3000]["interpolated"])
            self.assertIsNone(props[4000]["accuracy_m"])
            self.assertTrue(props[4000]["manual"])
            self.assertFalse(props[5000]["interpolated"])

            gpkg = output / "points.gpkg"
            self.assert_gpkg_schema(gpkg)
            con = sqlite3.connect(gpkg)
            try:
                self.assertEqual(con.execute("""
                    SELECT timestamp_utc, accuracy_m, interpolated, fix_gap_ms, bearing, speed_mps
                    FROM points ORDER BY frame_index
                """).fetchall(), [
                    (1700000001000, 2.0, 0, 0, 359.997, 4.0),
                    (1700000003000, None, 1, 4000, 0.0, None),
                    (None, None, 0, 0, None, None),
                    (1700000005000, 4.0, 0, 0, 359.999, None),
                ])
            finally:
                con.close()

            corrected = root / "corrected"
            copy_with_edit(output, corrected, 1, [46.6754, 24.7138], lambda _: None)
            self.assert_gpkg_schema(corrected / "points.gpkg")
            con = sqlite3.connect(corrected / "points.gpkg")
            try:
                self.assertEqual(con.execute("""
                    SELECT lon, lat, timestamp_utc, fix_gap_ms FROM points WHERE requested_ms=3000
                """).fetchone(), (46.6754, 24.7138, 1700000003000, 4000))
            finally:
                con.close()

            empty = root / "empty"
            empty.mkdir()
            write_points(empty, [])
            self.assert_gpkg_schema(empty / "points.gpkg")


if __name__ == "__main__":
    unittest.main()
