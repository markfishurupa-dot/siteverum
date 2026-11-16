"""Downloadable preflight report and bounded access to validated GPS tracks."""
import csv
import hashlib
import io
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from processor import preflight
from runtime import ROOT


@contextmanager
def original_track(sources, checksum):
    if "track" in sources:
        path = ROOT / sources["track"]["storage"]
        yield path if sources["track"]["sha256"] == checksum else None
        return
    if "zip" not in sources:
        yield None
        return
    # Read only the previously verified GPS member. Archive names never become output paths.
    with tempfile.TemporaryDirectory(prefix="streetview-report-") as tmp:
        path = Path(tmp) / "gps.log"
        matches = False
        try:
            with ZipFile(ROOT / sources["zip"]["storage"]) as archive:
                tracks = [info for info in archive.infolist() if not info.is_dir() and
                          PurePosixPath(info.filename.replace("\\", "/")).suffix.lower() in {".csv", ".log"}]
                if len(tracks) == 1 and tracks[0].file_size <= preflight.MAX_TRACK_BYTES:
                    with archive.open(tracks[0]) as source:
                        data = source.read(preflight.MAX_TRACK_BYTES + 1)
                    matches = hashlib.sha256(data).hexdigest() == checksum
                    if matches:
                        path.write_bytes(data)
        except (BadZipFile, OSError, RuntimeError, NotImplementedError):
            pass
        yield path if matches else None


TRACK_FIELDS = ["timestamp_utc", "video_elapsed_ms", "recording_start_utc_ms",
                "lat", "lon", "accuracy_m", "speed_mps", "bearing", "alt_m"]


def csv_cell(value):
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@")):
        try:
            float(value)
        except ValueError:
            return "'" + value
    return value


def write_report(archive, validation, groups):
    recordings = validation.get("recordings", {"primary": validation})
    limit = validation.get("accuracy_limit")
    records = [
        ("Survey", "Result", "Ready" if validation["can_process"] else "Cannot process"),
        ("Survey", "Accuracy filter", f"{limit:g} m" if limit is not None else "None"),
        ("Survey", "Warning threshold", "20 m (review only)"),
        ("Survey", "Exclusions", "GPS record numbers start at 1 after the header. Warnings alone do not exclude a record."),
        ("Survey", "Scope", "Source validation. Sampling and frame-selection skips are in the processing QA report."),
    ]
    count = 0
    # Stream CSV rows and compress them as they are written.
    with archive.open("excluded_records.csv", "w") as stream:
        with io.TextIOWrapper(stream, encoding="utf-8", newline="") as text:
            writer = csv.writer(text)
            writer.writerow(["recording", "record_number", "reason", *TRACK_FIELDS, "source_fields"])
            for number, (key, sources) in enumerate(groups.items(), 1):
                result = recordings.get(key, {})
                name = f"Recording {number}"
                gps = result.get("gps", {})
                video = result.get("video", {})
                records.extend((name, kind, message) for field, kind in
                               (("errors", "Error"), ("warnings", "Warning")) for message in result.get(field, []))
                for category, metrics in (("GPS", gps), ("Video", video), ("Timing", result.get("timing", {}))):
                    for metric, value in metrics.items():
                        if isinstance(value, list):
                            value = json.dumps(value)
                        records.append((name, f"{category}: {metric.replace('_', ' ')}", value))
                for asset in sources.values():
                    records.append((name, f"Source {asset['kind']}", asset["filename"]))
                if not gps.get("sha256"):
                    records.append((name, "GPS records", "No readable GPS track in this validation result"))
                    continue
                with original_track(sources, gps["sha256"]) as track:
                    if track is None:
                        records.append((name, "GPS records", "Original track unavailable"))
                        continue

                    def excluded(record, reason, values):
                        nonlocal count
                        count += 1
                        safe_fields = {str(key): value for key, value in values.items()}
                        writer.writerow([number, record, reason, *(csv_cell(values.get(key)) for key in TRACK_FIELDS),
                                         json.dumps(safe_fields, ensure_ascii=True)])

                    preflight.validate_log(track, [], [], 20, exclude=excluded,
                                           accuracy_limit=limit, video_duration=video.get("duration_seconds"))
    if not groups:
        records.extend(("Survey", kind, message) for field, kind in
                       (("errors", "Error"), ("warnings", "Warning")) for message in validation.get(field, []))
    records.append(("Survey", "Excluded GPS records", count))
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["section", "detail", "value"])
    writer.writerows(tuple(csv_cell(cell) for cell in row) for row in records)
    archive.writestr("report.csv", stream.getvalue())


def report_zip(validation, groups):
    stream = tempfile.SpooledTemporaryFile(max_size=2 * 1024**2)
    try:
        with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
            write_report(archive, validation, groups)
        stream.seek(0)
        return stream
    except BaseException:
        stream.close()
        raise
