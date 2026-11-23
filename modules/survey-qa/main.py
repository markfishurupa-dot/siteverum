
"""A dependency-free StreetView module using only the public JSON contract."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

inputs, output, execution_path = map(Path, sys.argv[1:])
execution = json.loads(execution_path.read_text(encoding="utf-8"))
survey = json.loads((inputs / "manifest.json").read_text(encoding="utf-8"))
frames = survey["frames"]
report = {
    "frames": len(frames),
    "missing_bearings": sum(frame.get("bearing") is None for frame in frames),
}
if execution["parameters"]["include_recordings"]:
    report["recordings"] = dict(Counter(str(frame.get("recording_number", 1)) for frame in frames))
data = json.dumps(report, indent=2).encode()
(output / "qa_summary.json").write_bytes(data)
result = {
    "contract": "streetview-module-output/v1",
    **{key: execution[key] for key in ("module", "version", "execution")},
    "status": "completed",
    "layers": [],
    "statistics": report,
    "files": {"qa_summary.json": {"category": "report", "sha256": hashlib.sha256(data).hexdigest()}},
}
(output / "result.json").write_text(json.dumps(result), encoding="utf-8")
print(f"Checked {len(frames)} frames")
