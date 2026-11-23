
"""Compare the bundled adapter with an independent standalone run on identical photos.

Run from the pole runtime. The standalone run must have used the same model
and default geometry settings. Paths are local and may contain private data.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import subprocess
import sys

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--standalone-output", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, required=True)
    args = parser.parse_args()
    import yaml

    with TemporaryDirectory() as directory:
        workspace = Path(directory)
        package = workspace / "package"
        with ZipFile(args.package) as archive:
            archive.extractall(package)
        spec = yaml.safe_load((package / "manifest.yaml").read_text())
        shutil.copyfile(args.model, package / spec["model"]["path"])
        inputs = workspace / "input"
        (inputs / "images").mkdir(parents=True)
        with (args.sample / "points_with_frames.csv").open(newline="", encoding="utf-8-sig") as stream:
            frames = sorted(csv.DictReader(stream), key=lambda row: int(row["frame_index"]))
        inventory = []
        for row in frames[:args.limit]:
            sequence = int(row["frame_index"])
            name = f"images/{sequence:06d}.jpg"
            shutil.copyfile(args.sample / "frames_points" / row["frame"], inputs / name)
            inventory.append({"sequence": sequence, "image_path": name, "recording_number": 1,
                              "sha256": hashlib.sha256((inputs / name).read_bytes()).hexdigest(),
                              **{field: row[field] for field in ("lat", "lon", "bearing", "accuracy_m")}})
        (inputs / "manifest.json").write_text(json.dumps({"frames": inventory}))
        settings = {key: parameter["default"] for key, parameter in spec["parameters"].items()}
        execution = {"execution": "reference-comparison", "module": spec["id"], "version": spec["version"],
                     "model": spec["model"], "parameters": settings}
        config = workspace / "execution.json"
        config.write_text(json.dumps(execution))
        args.output.mkdir(exist_ok=True, parents=True)
        subprocess.run([sys.executable, "-u", str(package / "main.py"), str(inputs), str(args.output), str(config)],
                       check=True, env={**os.environ, "SV_MODULE_ENABLE_GPU": "0"})
    original = args.standalone_output
    stats = json.loads((args.output / "qa_summary.json").read_text())["statistics"]
    reference = json.loads((original / "run_summary.json").read_text())
    for adapter_key, original_key in (("detections_used", "detections_used"),
        ("intersections_all", "intersection_candidates_all"), ("intersections_roadside", "intersection_candidates_roadside"),
        ("clustered", "poles_before_dedupe"), ("poles", "poles")):
        assert stats[adapter_key] == reference[original_key], (adapter_key, stats[adapter_key], reference[original_key])
    old = pd.read_csv(original / "pole_detections.csv")
    new = pd.read_csv(args.output / "pole_detections.csv")
    height = new.y2 - new.y1
    new = new[(height / new.image_height >= .08) & ((new.x2 - new.x1) / height).between(.005, .55)]
    assert old.frame_index.tolist() == new.sequence.tolist()
    assert old.class_name.tolist() == new.class_name.tolist()
    assert abs(old.confidence.to_numpy() - new.confidence.to_numpy()).max() < 1e-7
    assert abs(old[["x1", "x2", "y1", "y2"]].to_numpy() - new[["x1", "x2", "y1", "y2"]].to_numpy()).max() < .001
    pairs = [("pole_intersection_candidates_all.csv", "intersections_all.csv", ["x_m", "y_m"]),
             ("poles_clustered_before_dedupe.csv", "clustered.csv", ["x_m", "y_m"]),
             ("poles.csv", "poles.csv", ["lon", "lat"])]
    for old_name, new_name, axes in pairs:
        first = pd.read_csv(original / old_name).sort_values(axes).reset_index(drop=True)
        second = pd.read_csv(args.output / new_name).sort_values(axes).reset_index(drop=True)
        pd.testing.assert_frame_equal(first[axes], second[axes], check_exact=False, rtol=0, atol=.001 if axes[0] == "x_m" else 1e-8)
    print({key: stats[key] for key in ("frames_used", "detections_raw", "detections_used", "intersections_all",
                                       "intersections_roadside", "clustered", "poles")})


if __name__ == "__main__":
    main()
