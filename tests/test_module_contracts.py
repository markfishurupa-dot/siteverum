
import importlib.util
import json
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))
if importlib.util.find_spec("yaml"):
    from module_processing import contracts as c
else:
    c = None


@unittest.skipUnless(c, "PyYAML not installed")
class PackageTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "module.zip"
        self.manifest = {
            "api": c.API, "id": "test-module", "version": "1.0.0", "name": "Test", "description": "Test module",
            "runtime": "python", "stage": "post_processing", "entrypoint": "src/main.py",
            "inputs": ["processed_survey"], "outputs": ["report"], "permissions": ["read_input", "write_output"],
            "gpu": "none", "timeout_seconds": 5,
            "parameters": {"count": {"type": "integer", "min": 1, "max": 10, "default": 4}},
        }

    def make(self, extras=(), base=""):
        with ZipFile(self.path, "w", compression=ZIP_DEFLATED) as archive:
            for name, data in [
                ("manifest.yaml", json.dumps(self.manifest)), ("LICENSE", "license"),
                ("README.md", "readme"), ("src/main.py", "raise RuntimeError()"),
            ]:
                archive.writestr(base + name, data)
            for name, data in extras:
                archive.writestr(name, data)

    def test_install_extract_and_parameters(self):
        self.make(base="test-module/")
        extracted = self.path.parent / "package"
        manifest = c.inspect_package(self.path, extracted)
        self.assertTrue((extracted / "src/main.py").is_file())
        self.assertEqual(c.parameters(manifest, {}), {"count": 4})
        for values in ({"count": True}, {"count": 11}, {"unknown": "value"}):
            with self.assertRaises(c.ContractError):
                c.parameters(manifest, values)

    def test_bad_metadata(self):
        for key, value in [
            ("api", "other/v1"), ("runtime", "shell"), ("entrypoint", "missing.py"),
            ("model", {"source": "package", "path": "model.pt", "sha256": "0"*64}),
        ]:
            with self.subTest(key=key):
                old = self.manifest.get(key)
                self.manifest[key] = value
                self.make()
                with self.assertRaises(c.ContractError):
                    c.inspect_package(self.path)
                self.manifest[key] = old

    def test_unsafe_zip_entries(self):
        link = ZipInfo("src/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for name in ("../elsewhere", "/root", "C:/drive", "SRC/MAIN.py", "src/main.py/child", link):
            with self.subTest(name=name):
                self.make([(name, "data")])
                with self.assertRaises(c.ContractError):
                    c.inspect_package(self.path)

    def test_windows_separator_in_archive(self):
        self.make([("src/elsewhere.py", "data")])
        self.path.write_bytes(self.path.read_bytes().replace(b"src/elsewhere.py", b"src\\elsewhere.py"))
        with self.assertRaises(c.ContractError):
            c.inspect_package(self.path)

    def test_expansion_and_corrupt_archive(self):
        self.make([("expansion.txt", "x" * 2 * 1024**2)])
        with self.assertRaises(c.ContractError):
            c.inspect_package(self.path)
        self.path.write_bytes(b"not a zip")
        from zipfile import BadZipFile

        with self.assertRaises(BadZipFile):
            c.inspect_package(self.path)
