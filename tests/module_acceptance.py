
"""Integration checks against the isolated modular development Compose project."""
import argparse
import base64
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = dict(line.split("=", 1) for line in (ROOT / "deploy/.env.modules-dev").read_text().splitlines()
                if line and not line.startswith("#"))
BASE = f"http://127.0.0.1:{SETTINGS['SV_PORT']}"


def request(path, method="GET", data=None, status=200, auth=True, binary=False):
    headers = {"X-StreetView-Request": "1"}
    if auth:
        token = base64.b64encode(f"admin:{SETTINGS['SV_ADMIN_PASSWORD']}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    if data is not None:
        headers["Content-Type"] = "application/octet-stream" if isinstance(data, bytes) else "application/json"
        if not isinstance(data, bytes):
            data = json.dumps(data).encode()
    try:
        with urlopen(Request(BASE + path, method=method, headers=headers, data=data), timeout=90) as result:
            payload = result.read()
            assert result.status == status, (path, result.status, payload)
    except HTTPError as error:
        payload = error.read()
        assert error.code == status, (path, error.code, payload)
    return payload if binary or not payload else json.loads(payload)


def wait(path, state, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        item = request(path)
        if item["state"] == state:
            return item
        if item["state"] in {"failed", "cancelled", "completed"}:
            break
        time.sleep(0.5)
    raise AssertionError((path, state, item))


def make_survey(sample, label=None):
    label = label or "Module acceptance " + uuid4().hex[:8]
    survey = request("/api/v2/surveys", "POST", {"label": label}, 201)["id"]
    path = f"/api/v2/surveys/{survey}"
    request(path + "/assets/survey.zip", "PUT", sample.read_bytes())
    report = request(path + "/validate", "POST", {})
    assert report["can_process"], report
    job = request(path + "/process", "POST", {}, 202)["id"]
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        current = next(row for row in request(path)["jobs"] if row["id"] == job)
        if current["state"] == "completed":
            return path, job
        assert current["state"] not in {"failed", "cancelled"}, current
        time.sleep(1)
    raise AssertionError("Core processing timed out")


def run_module(path, module, parameters=None, request_key=None, *, version="1.0.0"):
    run = request(f"{path}/modules/{module}/runs", "POST", {
        "version": version, "parameters": parameters or {}, "request_key": request_key,
    }, 202)
    return f"/api/v2/module-runs/{run['id']}"


def install(module, version="1.0.0"):
    package = (ROOT / f"dist/streetview-{module}-{version}.zip").read_bytes()
    request("/api/v2/modules/install", "POST", package, 401, auth=False)
    result = request("/api/v2/modules/install", "POST", package, 201)
    assert request("/api/v2/modules/install", "POST", package, 201)["sha256"] == result["sha256"]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, default=os.getenv("STREETVIEW_SAMPLE_ZIP"), required=not os.getenv("STREETVIEW_SAMPLE_ZIP"))
    parser.add_argument("--poles", action="store_true")
    parser.add_argument("--keep-survey", action="store_true")
    args = parser.parse_args()
    path, source = make_survey(args.sample, "Electrical Poles CPU verification" if args.keep_survey else None)
    try:
        install("survey-qa")
        version = "/api/v2/modules/survey-qa/versions/1.0.0"
        request(version, "PATCH", {"enabled": False})
        request(path + "/modules/survey-qa/runs", "POST", {"version": "1.0.0"}, 409)
        request(version, "PATCH", {"enabled": True})
        request(path + "/modules/survey-qa/runs", "POST",
                {"version": "1.0.0", "parameters": {"include_recordings": "true"}}, 422)
        key = uuid4().hex
        run = run_module(path, "survey-qa", request_key=key)
        assert run_module(path, "survey-qa", request_key=key) == run
        result = wait(run, "completed")
        assert result["source_job"] == source and result["progress"] == 100, result
        report = request(run + "/artifacts/qa_summary.json")
        assert report["frames"] > 0 and report["recordings"] == {"1": report["frames"]}, report
        assert "Checked" in request(run + "/logs")["tail"]
        assert request(run + "/features")["features"] == []
        request(version, "DELETE", status=409)
        updated = run_module(path, "survey-qa", {"include_recordings": False})
        assert updated != run
        wait(updated, "completed")
        assert request(run)["stale"] is True
        assert "recordings" not in request(updated + "/artifacts/qa_summary.json")
        print("Survey QA install, duplicate, enablement, validation, idempotency, queue, artifacts and history passed")
        if args.poles:
            install("poles-detection", "1.1.0")
            run = run_module(path, "poles-detection", version="1.1.0")
            poles = wait(run, "completed", 900)
            result = request(run + "/artifacts/result.json")
            assert result["statistics"]["frames_used"] > 0 and result["statistics"]["device"] == "cpu", result
            available = {item["path"] for item in request(run + "/artifacts")}
            assert {"poles.geojson", "poles.csv", "poles.gpkg", "pole_detections.csv", "pole_rays.geojson",
                    "pole_evidence.json", "qa_summary.json", "result.json"} <= available
            cached = run_module(path, "poles-detection", {"roadside_snap": False}, version="1.1.0")
            replay = wait(cached, "completed", 120)
            assert replay["summary"]["statistics"]["cache_used"], replay
            assert replay["summary"]["statistics"]["detections_raw"] == result["statistics"]["detections_raw"]
            for feature in request(cached + "/features")["features"]:
                assert feature["geometry"] == feature["properties"]["original_geometry"]
            print("Pole CPU inference, artifact registration and inference reuse passed", poles["summary"])
    finally:
        if args.keep_survey:
            print("Private verification survey", path.rsplit("/", 1)[-1])
        else:
            request(path, "DELETE")


if __name__ == "__main__":
    main()
