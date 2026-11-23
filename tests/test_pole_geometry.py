
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules/poles-detection"))
sys.path.insert(0, str(ROOT / "services"))

HAS_GEOMETRY = all(importlib.util.find_spec(package) for package in ("pandas", "numpy", "shapely", "pyproj", "sklearn"))

if HAS_GEOMETRY:
    from argparse import Namespace
    import pandas as pd
    from detector import observation_bearing
    from geometry import angular_delta_degrees, intersect_ray_pairs, local_projector
    from main import triangulate


@unittest.skipUnless(HAS_GEOMETRY, "Optional pole runtime dependencies are unavailable")
class PoleGeometryTests(unittest.TestCase):
    def setUp(self):
        self.project, self.unproject, _ = local_projector(6.4, 2.3)
        self.x, self.y = self.project(6.4, 2.3)
        self.args = Namespace(ray_length_m=150, ray_buffer_m=1, max_frame_gap=35, min_baseline_m=2,
                              min_angle_deg=1, min_range_m=3, min_road_distance_m=3, max_road_distance_m=60,
                              cluster_distance_m=10, min_support_rays=2, snap_roadside_offset_m=12,
                              dedupe_station_m=22, dedupe_lateral_m=14, horizontal_fov_deg=70)
        self.execution = {"model": {"sha256": "0"*64}, "version": "1.0.0", "execution": "example"}

    def observed(self, baseline=10, bearing=45, segments=(1, 1)):
        frames, detection_rows = {}, []
        for seq, (offset, segment, direction) in enumerate(zip([0, baseline], segments, [bearing, 90])):
            lat, lon = self.unproject(self.x, self.y + offset)
            frames[seq] = {"sequence": seq, "lat": lat, "lon": lon, "recording_number": segment,
                           "image_path": f"images/{seq:06d}.jpg", "accuracy_m": 2}
            detection_rows.append(dict(frame_index=seq, sequence=seq, detection_id=seq, lat=lat, lon=lon,
                                       recording_number=segment, detection_bearing=direction, confidence=.8,
                                       class_name="pole_wood", x1=30, x2=40, y1=10, y2=80,
                                       image_width=100, image_height=100))
        return frames, pd.DataFrame(detection_rows)

    def test_heading_and_projection(self):
        self.assertEqual(observation_bearing(350, 10, 50, 100, 70, "linear"), 0)
        self.assertEqual(observation_bearing(0, 0, 75, 100, 70, "linear"), 17.5)
        self.assertGreater(observation_bearing(0, 0, 75, 100, 70, "rectilinear"), 17.5)
        self.assertEqual(observation_bearing(0, 0, 100, 100, 70, "rectilinear"), 35)
        self.assertEqual(angular_delta_degrees(359, 1), 2)

    def test_intersection_and_snapped_original(self):
        frames, detections = self.observed()
        features, rays, audits, _ = triangulate(self.args, detections, frames, self.execution)
        self.assertEqual((len(features), len(rays)), (1, 2))
        feature = features[0]
        raw_lon, raw_lat = feature["original_geometry"]["coordinates"]
        x, y = self.project(raw_lat, raw_lon)
        self.assertAlmostEqual(x - self.x, 10, places=3)
        self.assertAlmostEqual(y - self.y, 10, places=3)
        self.assertNotEqual(feature["original_geometry"], feature["geometry"])
        self.assertAlmostEqual(feature["properties"]["distance_to_path_m"], 12)
        self.assertEqual(len(feature["evidence"]), 2)
        self.assertEqual(len(audits["dedupe_audit"][0]), 1)
        self.assertAlmostEqual(rays[0]["geometry"]["coordinates"][0][0], 2.3, places=5)

    def test_rejects_parallel_baseline_and_cross_recording_pairs(self):
        for kwargs in ({"baseline": 1}, {"bearing": 89.75}, {"bearing": 225}, {"segments": (1, 2)}):
            with self.subTest(kwargs=kwargs):
                frames, detections = self.observed(**kwargs)
                features, _, _, _ = triangulate(self.args, detections, frames, self.execution)
                self.assertEqual(features, [])

    def test_close_station_candidate_is_audited(self):
        from geometry import exclude_duplicate_poles

        candidates = pd.DataFrame([dict(pole_id=f"p{i}", road_station_m=2 + i * 18, road_side="right",
                                        distance_to_path_m=12, signed_distance_to_path_m=-12,
                                        support_frame_count=3-i, support_ray_count=3-i, candidate_pair_count=2,
                                        confidence=.85) for i in range(2)])
        kept, audit = exclude_duplicate_poles(self.args, candidates)
        self.assertEqual(len(kept), 1)
        self.assertEqual(audit["dedupe_status"].tolist(), ["kept", "duplicate"])
        self.assertEqual(audit["duplicate_of"].iloc[1], kept["pole_id"].iloc[0])
