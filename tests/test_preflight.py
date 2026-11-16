import importlib.util
import tempfile
import stat
import unittest
import zipfile
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "services/processor/preflight.py"
spec = importlib.util.spec_from_file_location("preflight", MODULE)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class PreflightTests(unittest.TestCase):
    def test_prerecording_fix(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "sample.log"
            f.write_text("timestamp_utc,video_elapsed_ms,recording_start_utc_ms,lat,lon\n1000,-1,-1,1,2\n2000,1000,1000,1,2\n")
            warnings, errors = [], []
            report = p.validate_log(f, warnings, errors, 20)
            self.assertEqual(errors, [])
            self.assertEqual(report["pre_recording_rows"], 1)

    def test_extreme_timestamp_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "sample.log"
            f.write_text("timestamp_utc,video_elapsed_ms,recording_start_utc_ms,lat,lon\n999999999999999999999,0,999999999999999999999,1,2\n")
            warnings, errors = [], []
            p.validate_log(f, warnings, errors, 20)
            self.assertIn("LOG_RECORDING_START_OUT_OF_RANGE", errors)

    def test_missing_pair(self):
        self.assertFalse(p.validate(None, None, None, 20, False)["can_process"])

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("../escape.mp4", "not video")
                z.writestr("escape.log", "not log")
            report = p.validate(None, None, archive, 20, False)
            self.assertFalse(report["can_process"])
            self.assertTrue(any("ZIP_UNSAFE_PATH" in e for e in report["errors"]))

    def test_archive_ambiguity(self):
        self.assert_archive_error(
            [("a.mp4", b"v"), ("a.log", b"t"), ("nested/a.mp4", b"v")],
            "PAIR_AMBIGUOUS",
        )

    def test_archive_expansion_limit(self):
        self.assert_archive_error(
            [("a.mp4", b"0" * 500000), ("a.log", b"track")],
            "ZIP_UNSAFE_SIZE",
        )

    def test_archive_symlink(self):
        info = zipfile.ZipInfo("a.mp4")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.assert_archive_error([(info, b"target"), ("a.log", b"track")], "ZIP_SYMLINK")

    def assert_archive_error(self, entries, code):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "survey.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
                for entry, payload in entries:
                    output.writestr(entry, payload)
            report = p.validate(None, None, archive, 20, False)
            self.assertFalse(report["can_process"])
            self.assertTrue(any(error.startswith(code) for error in report["errors"]), report)

    def test_mismatched_basenames(self):
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("a.mp4", "not video")
                z.writestr("b.log", "not log")
            report = p.validate(None, None, archive, 20, False)
            self.assertTrue(any("STEMS_DIFFER" in e for e in report["errors"]))

if __name__ == "__main__":
    unittest.main()
