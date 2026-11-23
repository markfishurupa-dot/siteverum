
"""StreetView adapter for the supplied electrical pole detection workflow."""
from argparse import Namespace
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import pandas as pd

from detector import COLUMNS, detect, observation_bearing, progress
from geometry import (add_path_metrics, build_path_line, build_rays, cluster_candidates,
                      exclude_duplicate_poles, filter_detections_by_class, filter_roadside_candidates,
                      intersect_ray_pairs, local_projector)
from processor.module_exports import write_layer_geopackage


def write_json(path, data):
    path.write_text(json.dumps(data, allow_nan=False, ensure_ascii=False), encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError, OverflowError):
        return None


def select_frames(inputs, manifest, limit):
    frames = []
    skipped = Counter()
    for raw in manifest["frames"]:
        image = raw.get("image_path", "")
        lat, lon, bearing = (finite(raw.get(key)) for key in ("lat", "lon", "bearing"))
        if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
            skipped["invalid_coordinates"] += 1
            continue
        if not isinstance(image, str) or not re.fullmatch(r"images/[0-9]{6}\.jpg", image) or not (inputs / image).is_file():
            skipped["invalid_image"] += 1
            continue
        if bearing is None:
            skipped["missing_bearing"] += 1
        accuracy = finite(raw.get("accuracy_m"))
        frames.append({**raw, "lat": lat, "lon": lon, "bearing": bearing,
                       "accuracy_m": accuracy if accuracy is not None and accuracy >= 0 else None,
                       "recording_number": raw.get("recording_number", 1)})
    if limit:
        frames = frames[:limit]
    return frames, dict(skipped)


def attach_geometry(args, detections, frames):
    used = []
    for row in detections.to_dict("records"):
        frame = frames[int(row["sequence"])]
        bearing = frame["bearing"]
        if bearing is None:
            continue
        width, height = row["x2"] - row["x1"], row["y2"] - row["y1"]
        if width <= 0 or height <= 0:
            continue
        if args.shape_filter and (
            height / row["image_height"] < args.min_height_ratio or not args.min_aspect <= width / height <= args.max_aspect
        ):
            continue
        observed = observation_bearing(bearing, args.camera_heading_offset_deg, (row["x1"] + row["x2"]) / 2,
                                       row["image_width"], args.horizontal_fov_deg, args.projection)
        used.append({**row, "frame_index": frame["sequence"], "lat": frame["lat"], "lon": frame["lon"],
                     "recording_number": frame["recording_number"], "detection_bearing": observed})
    return filter_detections_by_class(pd.DataFrame(used), args.class_filter)


def feature_collection(features):
    return {"type": "FeatureCollection", "features": features}


def geographic(x, y, unproject):
    lat, lon = unproject(x, y)
    return [lon, lat]


def point(coordinates):
    return {"type": "Point", "coordinates": coordinates}


def make_feature(row, ray_rows, frames, execution, segment):
    stable = f"recording{segment}-{row['pole_id']}"
    observations = []
    for ray_id in row["source_ray_ids"].split(";"):
        ray = ray_rows.iloc[int(ray_id)]
        sequence = int(ray["sequence"])
        frame = frames[sequence]
        w, h = ray["image_width"], ray["image_height"]
        observations.append({
            "sequence": sequence, "source_frame_index": frame.get("source_frame_index"),
            "image_path": frame["image_path"], "recording_number": segment,
            "bbox": [ray["x1"] / w, ray["y1"] / h, ray["x2"] / w, ray["y2"] / h],
            "detection_confidence": ray["confidence"], "gps_accuracy_m": frame["accuracy_m"],
            "bearing": ray["detection_bearing"], "class": ray["class_name"],
        })
    raw = [row["raw_lon"], row["raw_lat"]]
    display = [row["lon"], row["lat"]]
    classes = json.loads(row["class_counts"])
    accuracy = [obs["gps_accuracy_m"] for obs in observations if obs["gps_accuracy_m"] is not None]
    props = {key: row[key] for key in ("mean_detection_confidence", "max_detection_confidence", "road_side",
                                      "distance_to_path_m", "raw_distance_to_path_m", "position_adjustment_m",
                                      "pair_angular_separation_deg", "mean_ray_distance_m", "mean_pair_line_gap_m",
                                      "support_ray_count", "support_frame_count", "candidate_pair_count")}
    props.update(class_counts=classes, pole_class=sorted(classes, key=lambda label: (-classes[label], label))[0],
                 recording_number=int(segment), model_sha256=execution["model"]["sha256"],
                 model_version=execution["model"].get("name", "pole-yolo11s-best"), module_version=execution["version"], execution=execution["execution"],
                 review_state="pending", gps_accuracy_mean_m=sum(accuracy) / len(accuracy) if accuracy else None,
                 source_frames=sorted({obs["sequence"] for obs in observations}),
                 source_images=sorted({obs["image_path"] for obs in observations}),
                 raw_coordinates=raw, estimated_coordinates=display)
    return {"type": "Feature", "id": stable, "geometry": point(display), "original_geometry": point(raw),
            "properties": props, "evidence": observations}


def triangulate(args, detections, frames, execution):
    features, ray_features = [], []
    diagnostics = {name: [] for name in ("intersections_all", "intersections_roadside", "clustered", "dedupe_audit")}
    warnings = []
    if detections.empty:
        return features, ray_features, diagnostics, warnings
    for segment, group in detections.groupby("recording_number"):
        segment_frames = pd.DataFrame([dict(frame, frame_index=frame["sequence"]) for frame in frames.values()
                                       if frame["recording_number"] == segment])
        project, unproject, _ = local_projector(float(group.lat.median()), float(group.lon.median()))
        rays, lines, crs = build_rays(args, group)
        for ray, line in zip(rays.to_dict("records"), lines):
            ray_features.append({"type": "Feature", "id": f"recording{segment}-ray{ray['ray_id']}",
                                 "geometry": {"type": "LineString",
                                              "coordinates": [geographic(x, y, unproject) for x, y in line.coords]},
                                 "properties": {key: ray[key] for key in ("sequence", "class_name", "confidence",
                                                                          "detection_bearing", "recording_number")}})
        try:
            path = build_path_line(segment_frames, project)
        except RuntimeError:
            warnings.append(f"Recording {segment} has insufficient distinct route positions")
            continue
        intersections = add_path_metrics(intersect_ray_pairs(args, rays, lines), path)
        roadside = filter_roadside_candidates(args, intersections)
        clustered = cluster_candidates(args, roadside, rays, crs)
        poles, audit = exclude_duplicate_poles(args, clustered)
        for key, table in zip(diagnostics, (intersections, roadside, clustered, audit)):
            diagnostics[key].append(table.assign(recording_number=int(segment)))
        features.extend(make_feature(pole, rays, frames, execution, segment) for pole in poles.to_dict("records"))
    return features, ray_features, diagnostics, warnings


def main(inputs, output, execution_path):
    execution = read_json(execution_path)
    args = Namespace(**execution["parameters"])
    if args.min_road_distance_m > args.max_road_distance_m or args.min_aspect > args.max_aspect:
        raise ValueError("Minimum distance and aspect settings must not exceed their maximum")
    if args.min_range_m >= args.ray_length_m:
        raise ValueError("Minimum ray range must be below the ray length")
    if not args.roadside_snap:
        args.snap_roadside_offset_m = 0
    frames, skipped = select_frames(inputs, read_json(inputs / "manifest.json"), args.limit)
    identifiable = [frame for frame in frames if frame["bearing"] is not None]
    model = execution_path.parent / "package" / execution["model"]["path"]
    model_hash = execution["model"]["sha256"]
    with model.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != model_hash:
            raise ValueError("Model checksum mismatch")
    cache = inputs / "cache.dat"
    device, cache_used = "none", cache.is_file()
    if cache_used:
        raw = pd.read_csv(cache, dtype={"device": str}, float_precision="round_trip")
        device = "cpu" if "cpu" in set(raw.device) else ("0" if len(raw) else "cached")
        print(f"Reused {len(raw)} detections")
    elif identifiable:
        raw, device = detect(args, inputs, identifiable, model, execution["model"].get("labels", {}))
    else:
        raw = pd.DataFrame(columns=COLUMNS)
    raw.to_csv(output / "pole_detections.csv", index=False)
    progress(70)
    frame_map = {frame["sequence"]: frame for frame in frames}
    detections = attach_geometry(args, raw, frame_map)
    features, rays, diagnostics, warnings = triangulate(args, detections, frame_map, execution)
    if skipped:
        warnings.append(f"Frame checks: {skipped}")
    if not features:
        warnings.append("No poles met the configured multi-observation thresholds")
    progress(90)
    write_json(output / "poles.geojson", feature_collection(features))
    write_json(output / "pole_rays.geojson", feature_collection(rays))
    write_json(output / "pole_evidence.json", {feature["id"]: feature["evidence"] for feature in features})
    write_layer_geopackage(output / "poles.gpkg", "poles", "Point", features)
    rows = [{"id": item["id"], "lon": item["geometry"]["coordinates"][0], "lat": item["geometry"]["coordinates"][1],
             **item["properties"]} for item in features]
    table = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["id", "lon", "lat", "pole_class", "review_state"])
    table.to_csv(output / "poles.csv", index=False)
    stats = {"frames_used": len(identifiable), "detections_raw": len(raw), "detections_used": len(detections),
             "rays": len(rays), "poles": len(features), "device": device, "cache_used": cache_used,
             "skipped": skipped}
    for name, items in diagnostics.items():
        combined = pd.concat(items, ignore_index=True) if items else pd.DataFrame()
        combined.to_csv(output / f"{name}.csv", index=False)
        stats[name] = len(combined)
    write_json(output / "qa_summary.json", {"statistics": stats, "warnings": warnings})
    files = {}
    categories = {"poles.geojson": "vector", "poles.gpkg": "vector", "poles.csv": "table",
                  "qa_summary.json": "report", "pole_detections.csv": "table"}
    for path in output.iterdir():
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        files[path.name] = {"category": categories.get(path.name, "diagnostic"), "sha256": checksum}
    write_json(output / "result.json", {"contract": "streetview-module-output/v1", "status": "completed",
               **{key: execution[key] for key in ("module", "version", "execution")}, "files": files,
               "statistics": stats, "warnings": warnings,
               "layers": [{"id": "poles", "path": "poles.geojson", "crs": "EPSG:4326",
                           "geometry": "Point", "count": len(features)}]})
    print(f"Saved {len(features)} poles from {len(identifiable)} georeferenced frames")


if __name__ == "__main__":
    main(*map(Path, sys.argv[1:]))
