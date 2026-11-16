#!/usr/bin/env python3
"""StreetView 2.0 survey input preflight prototype (standard library + ffprobe).

This is a standalone preflight validator, not a production upload API or frame processor.
Usage:
  python streetview_ingest_validator.py --video SV_....mp4 --log SV_....log
  python streetview_ingest_validator.py --zip survey.zip
  python streetview_ingest_validator.py --log SV_....log  # diagnostics only

Exit code 0 means ready for processing; 2 means rejected/incomplete.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

CORE_FIELDS = {"timestamp_utc", "video_elapsed_ms", "recording_start_utc_ms", "lat", "lon"}
OPTIONAL_FIELDS = {"accuracy_m", "speed_mps", "bearing", "alt_m"}
ANDROID_PATTERN = re.compile(r"^SV_\d{8}_\d{6}$")
MAX_MEMBER = 16 * 1024 ** 3
MAX_ARCHIVE_TOTAL = 24 * 1024 ** 3
MAX_MEMBERS = 1000
MAX_RATIO = 1000


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a, b = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = b - a, math.radians(lon2 - lon1)
    s = math.sin(dphi / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlambda / 2) ** 2
    return 2 * 6371008.8 * math.asin(min(1.0, math.sqrt(s)))


def validate_log(path: Path, warnings: list[str], errors: list[str], max_accuracy_m: float) -> dict:
    result = {"file": path.name, "size_bytes": path.stat().st_size, "sha256": hash_file(path)}
    try:
        # utf-8-sig handles UTF-8 BOM; newline='' preserves csv rules.
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, strict=True)
            fields = reader.fieldnames or []
            result["columns"] = fields
            absent = sorted(CORE_FIELDS - set(fields))
            if absent:
                errors.append("LOG_MISSING_COLUMNS: " + ", ".join(absent))
                return result
            if len(set(fields)) != len(fields):
                errors.append("LOG_DUPLICATE_COLUMNS")
                return result
            parsed = []
            for n, rec in enumerate(reader, start=2):
                try:
                    if None in rec or any(not rec.get(k, "").strip() for k in CORE_FIELDS):
                        raise ValueError("wrong CSV field count or blank required value")
                    row = {
                        "timestamp_utc": int(rec["timestamp_utc"]),
                        "video_elapsed_ms": int(rec["video_elapsed_ms"]),
                        "recording_start_utc_ms": int(rec["recording_start_utc_ms"]),
                        "lat": float(rec["lat"]), "lon": float(rec["lon"]),
                    }
                    for field in OPTIONAL_FIELDS & set(fields):
                        raw = rec.get(field, "")
                        row[field] = float(raw) if raw is not None and raw.strip() else None
                    if not (-90 <= row["lat"] <= 90 and -180 <= row["lon"] <= 180):
                        raise ValueError("latitude/longitude out of range")
                    if not all(math.isfinite(v) for v in row.values() if isinstance(v, float)):
                        raise ValueError("non-finite numeric value")
                    if row["recording_start_utc_ms"] < 0 and row["video_elapsed_ms"] != -1:
                        raise ValueError("negative recording start")
                    if row["video_elapsed_ms"] < -1:
                        raise ValueError("invalid elapsed time")
                    if row.get("accuracy_m") is not None and row["accuracy_m"] < 0:
                        raise ValueError("negative GPS accuracy")
                    if row.get("speed_mps") is not None and row["speed_mps"] < 0:
                        raise ValueError("negative speed")
                    if row.get("bearing") is not None and not (0 <= row["bearing"] <= 360):
                        raise ValueError("bearing out of range")
                    parsed.append(row)
                except (ValueError, TypeError, OverflowError) as e:
                    errors.append(f"LOG_BAD_ROW_{n}: {e}")
            result["row_count"] = len(parsed)
    except (UnicodeError, csv.Error, OSError) as e:
        errors.append(f"LOG_UNREADABLE: {e}")
        return result
    if not parsed:
        errors.append("LOG_EMPTY_OR_INVALID")
        return result

    valid = [r for r in parsed if r["video_elapsed_ms"] >= 0]
    result["pre_recording_rows"] = len(parsed) - len(valid)
    result["usable_fix_count_before_accuracy_filter"] = len(valid)
    if not valid:
        errors.append("LOG_NO_VALID_ELAPSED_TIMESTAMPS")
        return result
    start_times = {r["recording_start_utc_ms"] for r in valid}
    if len(start_times) > 1:
        errors.append("LOG_MULTIPLE_RECORDING_START_TIMES")
    start = valid[0]["recording_start_utc_ms"]
    result["recording_start_utc"] = dt.datetime.fromtimestamp(start / 1000, tz=dt.timezone.utc).isoformat(timespec="milliseconds")
    result["first_elapsed_ms"] = valid[0]["video_elapsed_ms"]
    result["last_elapsed_ms"] = valid[-1]["video_elapsed_ms"]
    result["usable_fix_count_at_max_accuracy"] = sum(r.get("accuracy_m") is not None and r["accuracy_m"] <= max_accuracy_m for r in valid) if "accuracy_m" in parsed[0] else None
    if any(b["video_elapsed_ms"] <= a["video_elapsed_ms"] for a, b in zip(valid, valid[1:])):
        errors.append("LOG_ELAPSED_NOT_STRICTLY_INCREASING")
    mismatches = [abs(r["timestamp_utc"] - r["recording_start_utc_ms"] - r["video_elapsed_ms"]) for r in valid]
    result["max_wallclock_elapsed_difference_ms"] = max(mismatches)
    if max(mismatches) > 250:
        warnings.append("CLOCK_OFFSET_WARNING: wall-clock and elapsed offsets differ >250 ms; investigate sync")
    inaccurate = [i + 1 for i, r in enumerate(valid) if r.get("accuracy_m") is not None and r["accuracy_m"] > max_accuracy_m]
    if inaccurate:
        warnings.append(f"GPS_LOW_ACCURACY: {len(inaccurate)} fixes above {max_accuracy_m:g} m (fix indices: {inaccurate[:12]})")
    jumps = []
    for i, (a, b) in enumerate(zip(valid, valid[1:]), start=2):
        delta = (b["video_elapsed_ms"] - a["video_elapsed_ms"]) / 1000
        if delta <= 0:
            continue
        dist = haversine(a["lat"], a["lon"], b["lat"], b["lon"])
        implied = dist / delta
        indicated = b.get("speed_mps")
        if implied > max(25.0, (indicated or 0) * 3 + 10):
            jumps.append({"to_fix_index": i, "distance_m": round(dist, 2), "time_s": round(delta, 3), "implied_speed_mps": round(implied, 2), "reported_speed_mps": indicated})
    result["suspect_position_jumps"] = jumps
    if jumps:
        warnings.append(f"GPS_POSITION_JUMP: {len(jumps)} suspicious segment(s), review accuracy and speed")
    return result


def validate_video(path: Path, warnings: list[str], errors: list[str], full_decode: bool = False) -> dict:
    result = {"file": path.name, "size_bytes": path.stat().st_size, "sha256": hash_file(path)}
    try:
        with path.open("rb") as f:
            head = f.read(64)
        if len(head) < 12 or head[4:8] != b"ftyp":
            errors.append("VIDEO_NOT_MP4: missing ISO BMFF ftyp box")
            return result
        try:
            proc = subprocess.run([
                "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
            ], capture_output=True, text=True, timeout=60)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            errors.append(f"FFPROBE_NOT_AVAILABLE_OR_TIMEOUT: {e}")
            return result
        if proc.returncode != 0:
            errors.append("VIDEO_FFPROBE_FAILED: " + proc.stderr[-500:])
            return result
        meta = json.loads(proc.stdout)
        streams = [s for s in meta.get("streams", []) if s.get("codec_type") == "video"]
        if not streams:
            errors.append("VIDEO_NO_VIDEO_STREAM")
            return result
        stream = streams[0]
        duration = float(meta.get("format", {}).get("duration") or stream.get("duration") or 0)
        result.update({"duration_seconds": duration, "codec": stream.get("codec_name"),
                       "width": stream.get("width"), "height": stream.get("height"),
                       "frames_reported": stream.get("nb_frames")})
        if not math.isfinite(duration) or duration <= 0:
            errors.append("VIDEO_DURATION_INVALID")
        if full_decode:
            decode = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"], capture_output=True, text=True, timeout=7200)
            result["full_decode_passed"] = decode.returncode == 0
            if decode.returncode:
                errors.append("VIDEO_DECODE_FAILED: " + decode.stderr[-500:])
        else:
            warnings.append("VIDEO_FULL_DECODE_NOT_RUN: ffprobe confirms structure, not every frame")
    except (ValueError, json.JSONDecodeError, OSError, subprocess.TimeoutExpired) as e:
        errors.append(f"VIDEO_VALIDATION_FAILED: {e}")
    return result


def safe_zip_extract_pair(archive: Path, target: Path, errors: list[str]) -> tuple[Path | None, Path | None]:
    if not zipfile.is_zipfile(archive):
        errors.append("ZIP_UNREADABLE_OR_NOT_ZIP")
        return None, None
    try:
        with zipfile.ZipFile(archive, "r") as z:
            members = z.infolist()
            if len(members) > MAX_MEMBERS:
                errors.append("ZIP_TOO_MANY_MEMBERS")
                return None, None
            total = 0
            candidates = []
            seen_names: set[str] = set()
            for info in members:
                n = info.filename.replace("\\", "/")
                p = PurePosixPath(n)
                if n.lower() in seen_names:
                    errors.append("ZIP_DUPLICATE_ENTRY: " + n)
                    return None, None
                seen_names.add(n.lower())
                if p.is_absolute() or any(part in ("..", "") for part in p.parts) or re.match(r"^[A-Za-z]:", n):
                    errors.append("ZIP_UNSAFE_PATH: " + n)
                    return None, None
                mode = info.external_attr >> 16
                if stat.S_IFMT(mode) == stat.S_IFLNK:
                    errors.append("ZIP_SYMLINK_NOT_ALLOWED: " + n)
                    return None, None
                if info.is_dir():
                    continue
                total += info.file_size
                if (info.file_size > MAX_MEMBER or total > MAX_ARCHIVE_TOTAL or
                    (info.compress_size == 0 and info.file_size > 0) or
                    (info.compress_size > 0 and info.file_size / info.compress_size > MAX_RATIO)):
                    errors.append("ZIP_UNSAFE_SIZE_OR_COMPRESSION_RATIO")
                    return None, None
                if p.suffix.lower() in (".mp4", ".log", ".csv"):
                    candidates.append((p, info))
            if len(candidates) != 2 or sorted(p.suffix.lower() for p, _ in candidates) not in ([".log", ".mp4"], [".csv", ".mp4"]):
                errors.append("ZIP_REQUIRES_EXACTLY_ONE_MP4_AND_ONE_LOG_OR_CSV")
                return None, None
            if candidates[0][0].stem.lower() != candidates[1][0].stem.lower():
                errors.append("ZIP_VIDEO_LOG_STEMS_DIFFER")
                return None, None
            broken = z.testzip()  # Check CRCs for every archive member.
            if broken is not None:
                errors.append("ZIP_BAD_CRC: " + broken)
                return None, None
            outputs = {}
            for p, info in candidates:
                dest = target / ("input.mp4" if p.suffix.lower() == ".mp4" else "input" + p.suffix.lower())
                with z.open(info, "r") as src, dest.open("wb") as dst:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        dst.write(chunk)
                outputs[p.suffix.lower()] = dest
            return outputs.get(".mp4"), outputs.get(".log") or outputs.get(".csv")
    except (zipfile.BadZipFile, OSError, RuntimeError, EOFError) as e:
        errors.append("ZIP_ERROR: " + str(e))
        return None, None


def validate(video: Path | None, log: Path | None, archive: Path | None, max_accuracy: float, full_decode: bool) -> dict:
    report = {"status": "INCOMPLETE", "errors": [], "warnings": [], "input_mode": "zip" if archive else "separate"}
    errors, warnings = report["errors"], report["warnings"]
    with tempfile.TemporaryDirectory(prefix="sv_preflight_") as tmp:
        if archive:
            if not archive.is_file():
                errors.append("ZIP_MISSING")
            else:
                report["archive"] = {"name": archive.name, "bytes": archive.stat().st_size, "sha256": hash_file(archive)}
                video, log = safe_zip_extract_pair(archive, Path(tmp), errors)
                if video and log:
                    report["matched_basename"] = "matching source archive entries"
        else:
            if video and log:
                if video.stem.lower() != log.stem.lower():
                    errors.append("VIDEO_LOG_STEMS_DIFFER")
                else:
                    report["matched_basename"] = video.stem
                    if not ANDROID_PATTERN.match(video.stem):
                        warnings.append("NON_ANDROID_FILENAME: pair accepted via shared basename")
            elif video or log:
                errors.append("PAIR_INCOMPLETE: stage both MP4 and .log/.csv before processing")
            else:
                errors.append("NO_INPUTS")
        for typ, p in (("video", video), ("gps", log)):
            if p and not p.is_file():
                errors.append(typ.upper() + "_FILE_NOT_FOUND")
        if log and log.is_file():
            report["gps"] = validate_log(log, warnings, errors, max_accuracy)
        if video and video.is_file():
            report["video"] = validate_video(video, warnings, errors, full_decode=full_decode)
        if "gps" in report and "video" in report:
            max_elapsed_s = report["gps"].get("last_elapsed_ms", 0) / 1000
            video_duration = report["video"].get("duration_seconds")
            if video_duration is not None:
                report["timing"] = {"last_gps_elapsed_s": max_elapsed_s, "video_duration_s": video_duration}
                if max_elapsed_s > video_duration + 0.2:
                    errors.append("TRACK_BEYOND_VIDEO_DURATION")
                elif video_duration - max_elapsed_s > 10:
                    warnings.append("TRACK_ENDS_EARLY: video tail >10 seconds beyond last GPS fix")
        if not errors and "gps" in report and "video" in report:
            report["status"] = "READY"
        elif errors == ["PAIR_INCOMPLETE: stage both MP4 and .log/.csv before processing"]:
            report["status"] = "INCOMPLETE"
        else:
            report["status"] = "REJECTED"
        report["can_process"] = report["status"] == "READY"
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--zip", type=Path, help="Android survey ZIP containing exactly one MP4 and one LOG/CSV")
    group.add_argument("--video", type=Path, help="Video for separate-file upload")
    ap.add_argument("--log", type=Path, help="GPS log for separate-file upload or log-only QA")
    ap.add_argument("--max-accuracy", type=float, default=20, help="QA warning threshold in meters")
    ap.add_argument("--full-decode", action="store_true", help="Decode every frame to detect video corruption")
    ap.add_argument("--output", type=Path, help="Write JSON report to file")
    args = ap.parse_args()
    if args.zip and args.log:
        ap.error("--log cannot be combined with --zip")
    report = validate(args.video, args.log, args.zip, args.max_accuracy, args.full_decode)
    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["status"] == "READY" else 2


if __name__ == "__main__":
    sys.exit(main())
