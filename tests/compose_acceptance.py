"""Browser acceptance against the local Compose stack with a private fixture."""
import base64
import csv
import hashlib
import io
import json
import os
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import urllib.error
import urllib.request
import zipfile
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright
import pyogrio

root = Path(__file__).resolve().parents[1]
settings = dict(line.split("=", 1) for line in (root / "deploy/.env").read_text().splitlines()
                if line and not line.startswith("#") and "=" in line)
password = settings["SV_ADMIN_PASSWORD"]
base = "http://127.0.0.1:" + settings.get("SV_PORT", "18080")
fixture = Path(os.environ["STREETVIEW_SAMPLE_ZIP"])
authorization = "Basic " + base64.b64encode(("admin:" + password).encode()).decode()


def request(path, method="GET", data=None, auth=True, expected=200):
    headers = {"X-StreetView-Request": "1", "Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = authorization
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            assert response.status == expected, (path, response.status)
            return response.read()
    except urllib.error.HTTPError as exc:
        assert exc.code == expected, (path, exc.code, exc.read())
        return exc.read()


def verify_bundle(bundle, target):
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert archive.testzip() is None
        points = json.loads(archive.read("points.geojson"))
        assert len(points["features"]) == 7
        assert points["features"][-1]["properties"]["requested_ms"] == 7872
        assert abs(points["features"][-1]["properties"]["actual_pts"] - 7.8662) < 0.0001
        rows = list(csv.DictReader(io.StringIO(archive.read("points.csv").decode())))
        assert len(rows) == 7
        images = set()
        hashes = {}
        for feature, row in zip(points["features"], rows):
            path = feature["properties"]["image_path"]
            assert path == row["image_path"] and path.startswith("images/")
            assert [float(row["lon"]), float(row["lat"])] == feature["geometry"]["coordinates"]
            photo = archive.read(path)
            assert photo.startswith(b"\xff\xd8") and photo.endswith(b"\xff\xd9")
            images.add(path)
            hashes[path] = hashlib.sha256(photo).hexdigest()
        assert len(images) == 7
        target.write_bytes(archive.read("points.gpkg"))
        info = pyogrio.read_info(target, layer="points")
        assert info["features"] == 7 and info["crs"] == "EPSG:4326" and info["geometry_type"] == "Point", info
        route = json.loads(archive.read("route.geojson"))
        return points, route, hashes


def browser_import(page, label, files, target, loose=False):
    page.locator("#label").fill(label)
    page.get_by_role("button", name="Create survey").click()
    expect(page.locator("#title")).to_have_text(label)
    if loose:
        page.locator("#files").set_input_files(files[1])
        page.get_by_role("button", name="Upload", exact=True).click()
        expect(page.locator("#message")).to_have_text("Waiting for matching video")
        expect(page.locator("#start")).to_be_disabled()
        files = files[0]
    page.locator("#files").set_input_files(files)
    page.get_by_role("button", name="Upload", exact=True).click()
    expect(page.locator("#message")).to_have_text("Sources staged", timeout=30000)
    page.get_by_role("button", name="Validate sources").click()
    expect(page.locator("#validation")).to_contain_text("Low GPS accuracy", timeout=30000)
    page.get_by_role("button", name="Process survey").click()
    expect(page.locator("#caption")).to_contain_text("Photo 1 of 7", timeout=120000)
    expect(page.locator(".leaflet-marker-icon")).to_have_count(7)
    for step in range(2, 8):
        page.get_by_role("button", name="Next photo").click()
        expect(page.locator("#caption")).to_contain_text(f"Photo {step} of 7")
        expect(page.locator("#photo")).to_have_js_property("complete", True)
        assert page.locator("#photo").evaluate("(img) => img.naturalWidth") > 0
    with page.expect_download() as downloaded:
        page.get_by_role("link", name="survey.zip", exact=True).click()
    return verify_bundle(downloaded.value.path().read_bytes(), target), page.locator("#photo").get_attribute("src")


def cleanup_surveys(labels):
    for survey in json.loads(request("/api/v2/surveys")):
        if survey["label"] in labels:
            request("/api/v2/surveys/" + survey["id"], "DELETE")


def main():
    suffix = uuid4().hex[:10]
    labels = [f"Acceptance {case} {suffix}" for case in ("ZIP", "loose", "invalid")]
    try:
        run_acceptance(*labels)
    finally:
        cleanup_surveys(labels)


def run_acceptance(zip_label, loose_label, invalid_label):
    request("/api/v2/surveys", auth=False, expected=401)
    with TemporaryDirectory() as tmp:
        target = Path(tmp)
        with zipfile.ZipFile(fixture) as archive:
            files = []
            for suffix in (".mp4", ".log"):
                name = next(x for x in archive.namelist() if x.endswith(suffix))
                output = target / Path(name).name
                output.write_bytes(archive.read(name))
                files.append(output)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge")
            context = browser.new_context(http_credentials={"username": "admin", "password": password})
            page = context.new_page()
            page.goto(base)
            a, media = browser_import(page, zip_label, fixture, target / "zip.gpkg")
            b, _ = browser_import(page, loose_label, files, target / "loose.gpkg", loose=True)
            assert a == b
            request(media, auth=False, expected=401)
            page.get_by_role("button", name="Publish locally", exact=True).click()
            expect(page.locator("#publication")).to_have_text("Unpublish locally")
            request(media, auth=False, expected=401)
            page.get_by_role("button", name="Unpublish locally", exact=True).click()
            expect(page.locator("#publication")).to_have_text("Publish locally")
        survey = json.loads(request("/api/v2/surveys", "POST", json.dumps({"label": invalid_label}).encode(), expected=201))["id"]
        path = f"/api/v2/surveys/{survey}"
        request(path + "/process", "POST", b"{}", expected=409)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as out:
            out.writestr("../escape.mp4", b"bad")
            out.writestr("escape.log", b"bad")
        request(path + "/assets/malicious.zip", "PUT", archive.getvalue())
        validation = json.loads(request(path + "/validate", "POST"))
        assert not validation["can_process"] and any("ZIP_UNSAFE_PATH" in e for e in validation["errors"])
        request(path + "/process", "POST", b"{}", expected=409)
        request(path + "/assets/malicious.zip", "PUT", b"not ZIP")
        assert not json.loads(request(path + "/validate", "POST"))["can_process"]
        request(path, "DELETE")
    print("Browser ZIP and staged LOG/MP4 upload, photo navigation, GIS export, GDAL interoperability, equivalence, auth, publication and malformed input checks passed.")
    photo = request(media)
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "restart"], cwd=root, check=True)
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "up", "-d", "--wait"],
                   cwd=root, check=True)
    assert request(media) == photo
    survey_path = media.split("/runs/")[0]
    prior = json.loads(request(survey_path))["jobs"][0]
    repeat = json.loads(request(survey_path + "/process", "POST", b"{}", expected=202))
    assert repeat["id"] == prior["id"] and repeat["state"] == "completed"
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "stop", "worker"],
                   cwd=root, check=True)
    try:
        changed = b'{"sampling":"time","interval":2}'
        job = json.loads(request(survey_path + "/process", "POST", changed, expected=202))
        assert job["state"] == "queued"
        request("/api/v2/jobs/" + job["id"] + "/cancel", "POST")
        assert json.loads(request(survey_path))["jobs"][0]["state"] == "cancelled"
        retry = json.loads(request(survey_path + "/process", "POST", changed, expected=202))
        assert retry["id"] != job["id"]
    finally:
        subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "start", "worker"],
                       cwd=root, check=True)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        current = json.loads(request(survey_path))["jobs"][0]
        if current["state"] in {"failed", "completed"}:
            break
        time.sleep(1)
    assert current["state"] == "completed" and 0 < current["metadata"]["frame_count"] < 7, current
    print("Compose restart persistence, idempotent repeat, queued cancellation and changed-settings retry passed.")


if __name__ == "__main__":
    main()
