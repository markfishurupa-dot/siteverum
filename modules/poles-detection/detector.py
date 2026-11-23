
"""Stream source JPEGs through one YOLO model, retaining pixel-space detections."""
import math
import os
from pathlib import Path
import time

import pandas as pd


COLUMNS = ["detection_id", "sequence", "image_width", "image_height", "x1", "y1", "x2", "y2",
           "confidence", "class_id", "class_name", "device"]


def observation_bearing(heading, offset, x, width, fov, projection):
    position = x / width - 0.5
    angle = position * fov
    if projection == "rectilinear":
        angle = math.degrees(math.atan(2 * position * math.tan(math.radians(fov / 2))))
    return (heading + offset + angle) % 360


def progress(percent):
    location = os.environ.get("SV_MODULE_PROGRESS")
    if location:
        path = Path(location)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(str(percent), encoding="ascii")
        temporary.replace(path)


def choose_device(preferred):
    import torch

    if preferred == "auto" and os.getenv("SV_MODULE_ENABLE_GPU") == "1":
        try:
            if torch.cuda.is_available():
                probe = torch.ones((8, 8), device="cuda:0")
                (probe @ probe).sum().item()
                return "0"
        except (RuntimeError, OSError) as exc:
            print(f"CUDA runtime check failed, using CPU: {exc}")
    return "cpu"


def detect(args, path, frames, model_path, labels):
    from ultralytics import YOLO

    device = choose_device(args.device)
    model = YOLO(str(model_path))
    canonical = {"pole_beton", "pole_generic", "pole_metal", "pole_wood"}
    if model.task != "detect":
        raise ValueError("The checkpoint must be an Ultralytics object detection model")
    names = model.names
    if labels.keys() - set(names.values()):
        raise ValueError("A label mapping refers to a class absent from the checkpoint")
    classes = {index: labels.get(name, name) for index, name in names.items()}
    classes = {index: name for index, name in classes.items() if name in canonical}
    if not classes:
        raise ValueError("Map at least one checkpoint label to a supported pole class")
    rows = []
    started = time.monotonic()
    for ordinal, frame in enumerate(frames, 1):
        image = path / frame["image_path"]
        try:
            results = model.predict(str(image), conf=args.conf, imgsz=args.imgsz, verbose=False, device=device)
        except (RuntimeError, OSError, NotImplementedError) as exc:
            if device == "cpu":
                raise
            print(f"CUDA inference failed, retrying on CPU: {exc}")
            device = "cpu"
            model.to("cpu")
            results = model.predict(str(image), conf=args.conf, imgsz=args.imgsz, verbose=False, device=device)
        for result in results:
            if result.boxes is None:
                continue
            height, width = result.orig_shape
            for box in result.boxes:
                x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
                if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                    continue
                index = int(box.cls[0])
                if index not in classes:
                    continue
                rows.append([len(rows), frame["sequence"], width, height, x1, y1, x2, y2, float(box.conf[0]),
                             index, classes[index], device])
                if len(rows) > 60000:
                    raise ValueError("Too many pole boxes. Use a higher confidence threshold or a smaller frame limit.")
        if ordinal == 1 or ordinal % 10 == 0 or ordinal == len(frames):
            print(f"{ordinal}/{len(frames)} frames, {len(rows)} boxes, {time.monotonic()-started:.1f}s, device={device}")
            progress(3 + int(62 * ordinal / len(frames)))
    return pd.DataFrame(rows, columns=COLUMNS), device
