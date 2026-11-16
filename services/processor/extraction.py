"""Extract exact decoded frame numbers in one FFmpeg pass."""
import os
import re
import shutil
import subprocess
import tempfile
import time


def selection_expression(indices):
    """Build a balanced decision tree instead of scanning all frame indices."""
    if len(indices) == 1:
        return f"eq(n,{indices[0]})"
    middle = len(indices) // 2
    return (f"if(lt(n,{indices[middle]}),{selection_expression(indices[:middle])},"
            f"{selection_expression(indices[middle:])})")


def progress_count(path):
    if not path.is_file():
        return 0
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 4096))
        values = re.findall(rb"^frame=(\d+)\s*$", stream.read(), flags=re.M)
    return int(values[-1]) if values else 0


def run_ffmpeg(arguments, checkpoint, on_wait, timeout=7200):
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryFile() as errors:
        with subprocess.Popen(arguments, stdout=subprocess.DEVNULL, stderr=errors) as process:
            try:
                while True:
                    try:
                        code = process.wait(timeout=1)
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() >= deadline:
                            raise subprocess.TimeoutExpired(arguments, timeout)
                        on_wait(checkpoint)
            except BaseException:
                process.kill()
                process.wait()
                raise
        if code:
            errors.seek(max(0, errors.seek(0, os.SEEK_END) - 1500))
            diagnostics = errors.read().decode("utf-8", errors="replace").strip()
            raise ValueError("FFmpeg could not complete frame processing" + (f": {diagnostics}" if diagnostics else ""))


def extract_frames(video, rows, staging, rotation_filter, checkpoint):
    indices = sorted({row["source_frame_index"] for row in rows})
    batch = staging / "extraction"
    batch.mkdir()
    progress = batch / "progress.txt"
    filters = batch / "filter.txt"
    filters.write_text("select='" + selection_expression(indices) + "'" + rotation_filter, encoding="ascii")
    pattern = str(batch / "%06d.jpg")
    common = ["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-protocol_whitelist", "file", "-threads", "2"]
    run_ffmpeg(
        [*common, "-i", str(video), "-map", "0:v:0", "-filter_script:v", str(filters),
         "-fps_mode", "passthrough", "-frames:v", str(len(indices)), "-q:v", "2",
         "-start_number", "0", "-progress", str(progress), pattern],
        checkpoint, lambda report: report(8 + min(75, int(75 * progress_count(progress) / len(indices)))),
    )
    images = sorted(batch.glob("*.jpg"))
    expected = [batch / f"{position:06d}.jpg" for position in range(len(indices))]
    if images != expected:
        raise ValueError(f"Expected {len(indices)} JPEGs, received {len(images)}")
    checkpoint(85)
    run_ffmpeg(
        [*common, "-framerate", "1", "-start_number", "0", "-i", pattern, "-f", "null", "-"],
        checkpoint, lambda report: report(85),
    )
    photos = dict(zip(indices, expected))
    for row in rows:
        shutil.copyfile(photos[row["source_frame_index"]], staging / row["image_path"])
    shutil.rmtree(batch)
