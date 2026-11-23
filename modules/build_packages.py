
"""Build reproducible installable plugin ZIPs without local model or survey data."""
import argparse
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=root.parent / "dist")
args = parser.parse_args()
args.output.mkdir(exist_ok=True, parents=True)
for name in ("survey-qa", "poles-detection"):
    base = root / name
    if not base.is_dir():
        continue
    manifest = (base / "manifest.yaml").read_text(encoding="utf-8")
    version = re.search(r'(?m)^\s*"?version"?\s*:\s*"?([0-9]+\.[0-9]+\.[0-9]+)', manifest).group(1)
    target = args.output / f"streetview-{name}-{version}.zip"
    files = {path.relative_to(base).as_posix(): path for path in base.rglob("*")
             if path.is_file() and path.suffix in {".py", ".md", ".yaml"} and "__pycache__" not in path.parts}
    if name == "poles-detection":
        for source in ("processor/exports.py", "processor/module_exports.py"):
            files[source] = root.parent / "services" / source
    files["LICENSE"] = base / "LICENSE" if (base / "LICENSE").is_file() else root.parent / "LICENSE"
    with ZipFile(target, "w") as archive:
        for label, source in sorted(files.items()):
            archive.writestr(ZipInfo(label), source.read_bytes(), compress_type=ZIP_DEFLATED)
    print(target.resolve())
