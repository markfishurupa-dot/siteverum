"""Triangulation adapted from the supplied standalone Poles Detection workflow."""
from __future__ import annotations

from argparse import Namespace
import json
import math
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
from shapely.strtree import STRtree
from sklearn.cluster import DBSCAN


def normalize_bearing(degrees: float) -> float:
    return float(degrees) % 360.0


def bearing_to_unit(degrees: float) -> tuple[float, float]:
    radians = math.radians(normalize_bearing(degrees))
    return math.sin(radians), math.cos(radians)


def angular_delta_degrees(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def local_projector(lat0: float, lon0: float):
    zone = min(60, int((lon0 + 180.0) // 6.0) + 1)
    epsg = (32600 if lat0 >= 0.0 else 32700) + zone
    crs_ll = CRS.from_epsg(4326)
    crs_xy = CRS.from_epsg(epsg) if -80 <= lat0 <= 84 else CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m")
    crs_name = crs_xy.to_authority()
    crs_name = ":".join(crs_name) if crs_name else "local azimuthal equidistant"
    to_xy = Transformer.from_crs(crs_ll, crs_xy, always_xy=True)
    to_ll = Transformer.from_crs(crs_xy, crs_ll, always_xy=True)

    def project(lat: float, lon: float) -> tuple[float, float]:
        x, y = to_xy.transform(lon, lat)
        return float(x), float(y)

    def unproject(x: float, y: float) -> tuple[float, float]:
        lon, lat = to_ll.transform(x, y)
        return float(lat), float(lon)

    return project, unproject, crs_name


def class_filter_values(raw_value: str) -> set[str]:
    return {value.strip() for value in raw_value.split(",") if value.strip()}


def filter_detections_by_class(detections: pd.DataFrame, class_filter: str) -> pd.DataFrame:
    selected_classes = class_filter_values(class_filter)
    if not selected_classes or detections.empty:
        return detections.copy()
    return detections[detections["class_name"].astype(str).isin(selected_classes)].copy()


def build_path_line(points: pd.DataFrame, project) -> LineString:
    coords: list[tuple[float, float]] = []
    previous: tuple[float, float] | None = None
    for _, row in points.sort_values("frame_index").iterrows():
        coord = project(float(row["lat"]), float(row["lon"]))
        if previous is None or math.hypot(coord[0] - previous[0], coord[1] - previous[1]) > 0.05:
            coords.append(coord)
            previous = coord
    if len(coords) < 2:
        raise RuntimeError("Not enough path coordinates to build a road control line.")
    return LineString(coords)


def path_metrics_for_point(path_line: LineString, x: float, y: float) -> dict[str, Any]:
    point = Point(x, y)
    station = float(path_line.project(point))
    nearest = path_line.interpolate(station)
    tangent_half_window = min(5.0, max(0.5, path_line.length / 2.0))
    before = path_line.interpolate(max(0.0, station - tangent_half_window))
    after = path_line.interpolate(min(float(path_line.length), station + tangent_half_window))
    tx = float(after.x - before.x)
    ty = float(after.y - before.y)
    vx = float(point.x - nearest.x)
    vy = float(point.y - nearest.y)
    cross = tx * vy - ty * vx
    distance = float(point.distance(path_line))
    if abs(cross) < 1e-9 or distance < 0.01:
        side = "center"
        signed_distance = 0.0
    elif cross > 0.0:
        side = "left"
        signed_distance = distance
    else:
        side = "right"
        signed_distance = -distance
    return {
        "road_station_m": station,
        "distance_to_path_m": distance,
        "signed_distance_to_path_m": signed_distance,
        "road_side": side,
        "nearest_path_x_m": float(nearest.x),
        "nearest_path_y_m": float(nearest.y),
    }


def add_path_metrics(candidates: pd.DataFrame, path_line: LineString) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    metrics = [
        path_metrics_for_point(path_line, float(row["x_m"]), float(row["y_m"]))
        for _, row in candidates.iterrows()
    ]
    return pd.concat([candidates.reset_index(drop=True), pd.DataFrame(metrics)], axis=1)


def filter_roadside_candidates(args: Namespace, candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    mask = (
        (candidates["distance_to_path_m"] >= args.min_road_distance_m)
        & (candidates["distance_to_path_m"] <= args.max_road_distance_m)
    )
    return candidates[mask].copy().reset_index(drop=True)


def build_rays(args: Namespace, detections: pd.DataFrame) -> tuple[pd.DataFrame, list[LineString], str]:
    project, _unproject, crs_name = local_projector(float(detections["lat"].median()), float(detections["lon"].median()))
    ray_rows: list[dict[str, Any]] = []
    lines: list[LineString] = []

    for _, detection in detections.iterrows():
        origin_x, origin_y = project(float(detection["lat"]), float(detection["lon"]))
        dx, dy = bearing_to_unit(float(detection["detection_bearing"]))
        end_x = origin_x + dx * args.ray_length_m
        end_y = origin_y + dy * args.ray_length_m
        line = LineString([(origin_x, origin_y), (end_x, end_y)])
        lines.append(line)
        out = detection.to_dict()
        out.update(
            {
                "ray_id": len(ray_rows),
                "origin_x_m": origin_x,
                "origin_y_m": origin_y,
                "end_x_m": end_x,
                "end_y_m": end_y,
                "ray_dx": dx,
                "ray_dy": dy,
                "ray_length_m": args.ray_length_m,
                "ray_buffer_m": args.ray_buffer_m,
                "projection": crs_name,
            }
        )
        ray_rows.append(out)

    return pd.DataFrame(ray_rows), lines, crs_name


def projected_along(ray: pd.Series, x: float, y: float) -> tuple[float, float]:
    vx = x - float(ray["origin_x_m"])
    vy = y - float(ray["origin_y_m"])
    along = vx * float(ray["ray_dx"]) + vy * float(ray["ray_dy"])
    cross = abs(vx * float(ray["ray_dy"]) - vy * float(ray["ray_dx"]))
    return along, cross


def representative_pair_point(line_a: LineString, line_b: LineString) -> tuple[Point, float]:
    intersection = line_a.intersection(line_b)
    if not intersection.is_empty:
        if intersection.geom_type == "Point":
            point = intersection
        else:
            point = intersection.representative_point()
        return Point(float(point.x), float(point.y)), 0.0

    nearest_a, nearest_b = nearest_points(line_a, line_b)
    gap = nearest_a.distance(nearest_b)
    return Point((nearest_a.x + nearest_b.x) / 2.0, (nearest_a.y + nearest_b.y) / 2.0), float(gap)


def intersect_ray_pairs(args: Namespace, rays: pd.DataFrame, lines: list[LineString]) -> pd.DataFrame:
    buffers = [line.buffer(args.ray_buffer_m, cap_style=2) for line in lines]
    tree = STRtree(buffers)
    candidates: list[dict[str, Any]] = []

    for i, buffer_i in enumerate(buffers):
        matches = tree.query(buffer_i, predicate="intersects")
        for raw_j in matches:
            j = int(raw_j)
            if j <= i:
                continue

            ray_i = rays.iloc[i]
            ray_j = rays.iloc[j]
            frame_gap = abs(int(ray_i["frame_index"]) - int(ray_j["frame_index"]))
            if args.max_frame_gap > 0 and frame_gap > args.max_frame_gap:
                continue
            if int(ray_i["frame_index"]) == int(ray_j["frame_index"]):
                continue

            origin_gap = math.hypot(float(ray_i["origin_x_m"]) - float(ray_j["origin_x_m"]), float(ray_i["origin_y_m"]) - float(ray_j["origin_y_m"]))
            if origin_gap < args.min_baseline_m:
                continue

            angle_delta = angular_delta_degrees(float(ray_i["detection_bearing"]), float(ray_j["detection_bearing"]))
            if angle_delta < args.min_angle_deg or angle_delta > (180.0 - args.min_angle_deg):
                continue

            point, line_gap = representative_pair_point(lines[i], lines[j])
            if line_gap > args.ray_buffer_m * 2.0 + 1e-6:
                continue

            along_i, cross_i = projected_along(ray_i, point.x, point.y)
            along_j, cross_j = projected_along(ray_j, point.x, point.y)
            if min(along_i, along_j) < args.min_range_m:
                continue
            if max(along_i, along_j) > args.ray_length_m:
                continue
            if max(cross_i, cross_j) > args.ray_buffer_m * 2.0 + 1e-6:
                continue

            if len(candidates) >= 100000:
                raise ValueError("Too many ray-pair candidates. Reduce the frame or ray search limits.")
            candidates.append(
                {
                    "candidate_id": len(candidates),
                    "x_m": float(point.x),
                    "y_m": float(point.y),
                    "ray_a": int(ray_i["ray_id"]),
                    "ray_b": int(ray_j["ray_id"]),
                    "detection_a": int(ray_i["detection_id"]),
                    "detection_b": int(ray_j["detection_id"]),
                    "frame_a": int(ray_i["frame_index"]),
                    "frame_b": int(ray_j["frame_index"]),
                    "frame_gap": int(frame_gap),
                    "origin_gap_m": round(origin_gap, 3),
                    "ray_angle_delta_deg": round(angle_delta, 3),
                    "line_gap_m": round(line_gap, 3),
                    "range_a_m": round(along_i, 3),
                    "range_b_m": round(along_j, 3),
                    "cross_a_m": round(cross_i, 3),
                    "cross_b_m": round(cross_j, 3),
                    "mean_detection_confidence": round((float(ray_i["confidence"]) + float(ray_j["confidence"])) / 2.0, 5),
                }
            )

    return pd.DataFrame(candidates)


def support_for_point(
    x: float,
    y: float,
    ray_arrays: dict[str, Any],
    buffer_m: float,
    ray_length_m: float,
) -> tuple[list[int], float]:
    vx = x - ray_arrays["origin_x"]
    vy = y - ray_arrays["origin_y"]
    along = vx * ray_arrays["dx"] + vy * ray_arrays["dy"]
    cross = np.abs(vx * ray_arrays["dy"] - vy * ray_arrays["dx"])
    mask = (along >= 0.0) & (along <= ray_length_m) & (cross <= buffer_m + 1e-9)
    if not bool(mask.any()):
        return [], float("nan")
    return ray_arrays["ray_id"][mask].astype(int).tolist(), float(cross[mask].mean())


def cluster_candidates(
    args: Namespace,
    candidates: pd.DataFrame,
    rays: pd.DataFrame,
    crs_name: str,
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()

    if len(candidates) > 20000:
        raise ValueError("Too many roadside candidates to cluster. Reduce the frame or ray search limits.")
    labels = DBSCAN(eps=args.cluster_distance_m, min_samples=1).fit_predict(candidates[["x_m", "y_m"]].to_numpy())
    candidates = candidates.copy()
    candidates["cluster_id"] = labels
    _project, unproject, _crs_name = local_projector(float(rays["lat"].median()), float(rays["lon"].median()))
    ray_arrays = {
        "ray_id": rays["ray_id"].to_numpy(),
        "origin_x": rays["origin_x_m"].to_numpy(dtype=float),
        "origin_y": rays["origin_y_m"].to_numpy(dtype=float),
        "dx": rays["ray_dx"].to_numpy(dtype=float),
        "dy": rays["ray_dy"].to_numpy(dtype=float),
    }
    pole_rows: list[dict[str, Any]] = []

    for cluster_id, group in candidates.groupby("cluster_id"):
        best: dict[str, Any] | None = None
        for _, candidate in group.iterrows():
            supported_ray_ids, mean_ray_distance = support_for_point(
                float(candidate["x_m"]),
                float(candidate["y_m"]),
                ray_arrays,
                args.ray_buffer_m,
                args.ray_length_m,
            )
            if len(supported_ray_ids) < args.min_support_rays:
                continue
            supported = rays[rays["ray_id"].isin(supported_ray_ids)]
            distinct_frames = int(supported["frame_index"].nunique())
            if distinct_frames < 2:
                continue
            score = (
                len(supported_ray_ids),
                distinct_frames,
                int(len(group)),
                -float(mean_ray_distance),
                float(candidate["mean_detection_confidence"]),
            )
            if best is None or score > best["score"]:
                best = {
                    "candidate": candidate,
                    "supported_ray_ids": supported_ray_ids,
                    "supported": supported,
                    "mean_ray_distance": mean_ray_distance,
                    "score": score,
                }

        if best is None:
            continue

        candidate = best["candidate"]
        supported = best["supported"]
        raw_x = float(candidate["x_m"])
        raw_y = float(candidate["y_m"])
        raw_distance_to_path = float(candidate["distance_to_path_m"])
        final_x = raw_x
        final_y = raw_y
        final_distance_to_path = raw_distance_to_path
        final_signed_distance_to_path = float(candidate["signed_distance_to_path_m"])
        position_adjustment_m = 0.0
        if args.snap_roadside_offset_m > 0.0 and raw_distance_to_path > 1e-9:
            nearest_x = float(candidate["nearest_path_x_m"])
            nearest_y = float(candidate["nearest_path_y_m"])
            scale = args.snap_roadside_offset_m / raw_distance_to_path
            final_x = nearest_x + (raw_x - nearest_x) * scale
            final_y = nearest_y + (raw_y - nearest_y) * scale
            final_distance_to_path = args.snap_roadside_offset_m
            final_signed_distance_to_path = math.copysign(args.snap_roadside_offset_m, float(candidate["signed_distance_to_path_m"]))
            position_adjustment_m = math.hypot(final_x - raw_x, final_y - raw_y)

        lat, lon = unproject(final_x, final_y)
        class_counts = Counter(str(value) for value in supported["class_name"].tolist())
        frame_values = sorted(int(value) for value in supported["frame_index"].unique())
        confidence = min(
            0.99,
            float(supported["confidence"].mean()) * (1.0 + min(len(frame_values), 6) * 0.04),
        )

        pole_rows.append(
            {
                "pole_id": f"pole_{len(pole_rows) + 1:04d}",
                "lat": lat,
                "raw_lat": unproject(raw_x, raw_y)[0],
                "raw_lon": unproject(raw_x, raw_y)[1],
                "pair_angular_separation_deg": float(candidate["ray_angle_delta_deg"]),
                "lon": lon,
                "confidence": round(confidence, 5),
                "support_ray_count": int(len(best["supported_ray_ids"])),
                "support_frame_count": int(len(frame_values)),
                "candidate_pair_count": int(len(group)),
                "first_frame": int(min(frame_values)),
                "last_frame": int(max(frame_values)),
                "support_frames": ";".join(str(value) for value in frame_values),
                "mean_detection_confidence": round(float(supported["confidence"].mean()), 5),
                "max_detection_confidence": round(float(supported["confidence"].max()), 5),
                "mean_ray_distance_m": round(float(best["mean_ray_distance"]), 3),
                "mean_pair_line_gap_m": round(float(group["line_gap_m"].mean()), 3),
                "road_station_m": round(float(candidate["road_station_m"]), 3),
                "distance_to_path_m": round(final_distance_to_path, 3),
                "signed_distance_to_path_m": round(final_signed_distance_to_path, 3),
                "raw_distance_to_path_m": round(raw_distance_to_path, 3),
                "position_adjustment_m": round(position_adjustment_m, 3),
                "road_side": str(candidate["road_side"]),
                "ray_buffer_m": float(args.ray_buffer_m),
                "ray_length_m": float(args.ray_length_m),
                "horizontal_fov_deg": float(args.horizontal_fov_deg),
                "snap_roadside_offset_m": float(args.snap_roadside_offset_m),
                "projection": crs_name,
                "class_counts": json.dumps(dict(class_counts), sort_keys=True),
                "position_method": "buffered_ray_pair_intersection",
                "review_status": "auto" if len(frame_values) >= 3 and len(group) >= 2 else "two_ray_candidate",
                "x_m": final_x,
                "y_m": final_y,
                "raw_x_m": raw_x,
                "raw_y_m": raw_y,
                "source_ray_ids": ";".join(str(value) for value in sorted(best["supported_ray_ids"])),
            }
        )

    if not pole_rows:
        return pd.DataFrame()
    return pd.DataFrame(pole_rows).sort_values(["first_frame", "pole_id"]).reset_index(drop=True)


def dedupe_score(row: pd.Series) -> tuple[float, float, float, float]:
    return (
        float(row["support_frame_count"]),
        float(row["support_ray_count"]),
        float(row["candidate_pair_count"]),
        float(row["confidence"]),
    )


def exclude_duplicate_poles(args: Namespace, poles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if poles.empty or args.dedupe_station_m <= 0.0:
        kept = poles.copy()
        kept["duplicate_of"] = ""
        kept["dedupe_status"] = "kept"
        return kept, kept.copy()

    working = poles.copy().reset_index(drop=True)
    working["duplicate_of"] = ""
    working["dedupe_status"] = "kept"
    ordered = sorted(working.index.tolist(), key=lambda idx: dedupe_score(working.loc[idx]), reverse=True)
    kept_indices: list[int] = []

    for idx in ordered:
        candidate = working.loc[idx]
        duplicate_of: int | None = None
        for kept_idx in kept_indices:
            kept = working.loc[kept_idx]
            if str(candidate["road_side"]) != str(kept["road_side"]):
                continue
            station_gap = abs(float(candidate["road_station_m"]) - float(kept["road_station_m"]))
            lateral_gap = abs(float(candidate["signed_distance_to_path_m"]) - float(kept["signed_distance_to_path_m"]))
            if station_gap <= args.dedupe_station_m and lateral_gap <= args.dedupe_lateral_m:
                duplicate_of = kept_idx
                break
        if duplicate_of is None:
            kept_indices.append(idx)
        else:
            working.loc[idx, "dedupe_status"] = "duplicate"
            working.loc[idx, "duplicate_of"] = str(working.loc[duplicate_of, "pole_id"])

    kept = working.loc[kept_indices].copy()
    kept = kept.sort_values(["road_station_m", "road_side", "distance_to_path_m"]).reset_index(drop=True)
    kept["source_pole_id"] = kept["pole_id"]
    kept["pole_id"] = [f"pole_{idx + 1:04d}" for idx in range(len(kept))]
    id_map = dict(zip(kept["source_pole_id"], kept["pole_id"]))
    kept["duplicate_of"] = kept["duplicate_of"].map(lambda value: id_map.get(value, value))

    full = working.copy()
    full["source_pole_id"] = full["pole_id"]
    full["pole_id"] = full["pole_id"].map(lambda value: id_map.get(value, value))
    full["duplicate_of"] = full["duplicate_of"].map(lambda value: id_map.get(value, value))
    return kept, full
