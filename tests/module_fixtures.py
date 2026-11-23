
"""Build deterministic, local-only module fixtures for acceptance tests."""
from io import BytesIO
import json
import subprocess
from tempfile import TemporaryDirectory
from pathlib import Path
from zipfile import ZipFile

from module_acceptance import ROOT, request


VECTOR = """
for forbidden in (input_dir / 'manifest.json', output.parents[1] / 'unexpected.txt'):
    try:
        with forbidden.open('a'):
            pass
    except OSError:
        pass
    else:
        raise RuntimeError('Plugin can write outside its permitted workspace')
wait = execution['parameters']['delay']
for percent in (10, 30, 50):
    progress = Path(os.environ['SV_MODULE_PROGRESS'])
    progress.write_text(str(percent))
    time.sleep(wait / 3)
mode = execution['parameters']['mode']
if mode == 'fail':
    raise RuntimeError("fixture expected failure")
if mode == 'malformed':
    (output / 'result.json').write_text('{}')
    sys.exit()
layers = []
if mode == 'vector':
    frame = frames[0]
    point = {'type': 'Point', 'coordinates': [frame['lon'], frame['lat']]}
    feature = {'type': 'Feature', 'id': 'pole-fixture', 'geometry': point,
               'original_geometry': point, 'properties': {'pole_class': 'pole_wood',
               'mean_detection_confidence': .82, 'source_images': [frame['image_path']],
               'support_frame_count': 2}, 'evidence': [
               {'sequence': frame['sequence'], 'bbox': [.1,.2,.3,.7]}]}
    put('demo.geojson', {'type': 'FeatureCollection', 'features': [feature]}, 'vector')
    layers.append({'id':'poles', 'path':'demo.geojson', 'geometry':'Point','crs':'EPSG:4326','count':1})
result['layers'] = layers
"""

REDACTION = """
mode = execution['parameters']['mode']
if mode == 'fail':
    raise RuntimeError("fixture failed")
asset = (execution_file.parent / 'package/blank.jpg').read_bytes()
derivatives = []
for frame in (frames[:1] if mode == 'partial' else frames):
    name = f"redacted/{frame['sequence']:06d}.jpg"
    put(name, asset, 'image')
    derivatives.append({'sequence':frame['sequence'], 'path':name,'source_sha256':frame['sha256'],
                        'metadata':{'method':'replace-all-pixels-fixture'}})
result['derivatives'] = derivatives
"""

PROLOGUE = """
import hashlib
import json
import os
from pathlib import Path
import sys
import time
input_dir, output, execution_file = map(Path,sys.argv[1:])
execution = json.loads(execution_file.read_text())
frames = json.loads((input_dir / "manifest.json").read_text())['frames']
files = {}
result = {'contract':'streetview-module-output/v1','status':'completed','layers':[], 'files':files, **{
    key: execution[key] for key in ('module','version','execution')
}}
def put(name, data, category):
    path = output / name
    path.parent.mkdir(exist_ok=True)
    if not isinstance(data, bytes):
        data = json.dumps(data).encode()
    path.write_bytes(data)
    files[name] = {'category':category,'sha256':hashlib.sha256(data).hexdigest()}
"""

EPILOGUE = """
(output / "result.json").write_text(json.dumps(result))
print("Fixture finished")
"""


def fixture_zip(module, redaction=False, description="Deterministic local test module"):
    files = {}
    modes = ["complete", "partial", "fail"] if redaction else ["vector", "empty", "fail", "malformed"]
    if redaction:
        with TemporaryDirectory() as folder:
            image = Path(folder) / "blank.jpg"
            subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-f", "lavfi", "-i",
                            "color=c=black:s=32x24", "-frames:v", "1", "-threads", "1", str(image)], check=True)
            files["blank.jpg"] = image.read_bytes()
    manifest = {
        "api": "streetview-module-api/v1", "id": module,
        "name": "Privacy test" if redaction else "Fixture poles", "description": description,
        "version": "1.0.0", "stage": "pre_publication" if redaction else "post_processing",
        "runtime": "python", "gpu": "none", "timeout_seconds": 45,
        "inputs": ["processed_survey"], "outputs": ["image"] if redaction else ["vector"],
        "permissions": ["read_input", "write_output"], "entrypoint": "main.py",
        "parameters": {"mode": {"type": "string", "default": modes[0], "choices": modes}},
        "public_properties": ["pole_class", "mean_detection_confidence"],
    }
    if not redaction:
        manifest["parameters"]["delay"] = {"type": "integer", "min": 0, "max": 40, "default": 3}
    files.update({"main.py": PROLOGUE + (REDACTION if redaction else VECTOR) + EPILOGUE,
                  "manifest.yaml": json.dumps(manifest), "LICENSE": (ROOT / "LICENSE").read_text(), "README.md": description})
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        for path, data in sorted(files.items()):
            from zipfile import ZipInfo

            archive.writestr(ZipInfo(path), data)
    return stream.getvalue()


def install_fixture(module, redaction=False):
    return request("/api/v2/modules/install", "POST", fixture_zip(module, redaction), 201)


def disable_fixture(module):
    if any(item["module_id"] == module and item["version"] == "1.0.0"
           for item in request("/api/v2/modules")):
        request(f"/api/v2/modules/{module}/versions/1.0.0", "PATCH", {"enabled": False})
