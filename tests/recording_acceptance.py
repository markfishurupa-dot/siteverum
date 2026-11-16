"""Exercise multi-recording surveys and publication in the local Docker app."""
import csv
import io
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright
import pyogrio

from compose_acceptance import base, browser_import, fixture, password, request


def make_second_recording(folder):
    """Derive a private test capture with a different position, time and source digest."""
    with ZipFile(fixture) as archive:
        video = next(name for name in archive.namelist() if name.lower().endswith(".mp4"))
        log = next(name for name in archive.namelist() if name.lower().endswith(".log"))
        original = folder / "source.mp4"
        original.write_bytes(archive.read(video))
        source = csv.DictReader(io.StringIO(archive.read(log).decode("utf-8-sig")))
        track = folder / "second.log"
        with track.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=source.fieldnames)
            writer.writeheader()
            for row in source:
                row["lat"] = float(row["lat"]) + 0.01
                for field in ("timestamp_utc", "recording_start_utc_ms"):
                    row[field] = int(row[field]) + 60_000
                writer.writerow(row)
    remuxed = folder / "second.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(original), "-c", "copy",
                    "-metadata", "comment=StreetView local acceptance segment", str(remuxed)], check=True)
    return remuxed, track


def main():
    label = "Recording test " + uuid4().hex[:10]
    try:
        with TemporaryDirectory() as tmp, sync_playwright() as pw:
            folder = Path(tmp)
            browser = pw.chromium.launch(channel="msedge")
            context = browser.new_context(http_credentials={"username": "admin", "password": password})
            page = context.new_page()
            page.goto(base)
            browser_import(page, label, fixture, folder / "original.gpkg")
            old_photo = page.locator("#photo").get_attribute("src")
            old_photo_bytes = request(old_photo)

            video, track = make_second_recording(folder)
            page.get_by_role("button", name="Add recording", exact=True).click()
            expect(page.locator("#upload")).to_be_visible()
            page.locator("#files").set_input_files(track)
            page.get_by_role("button", name="Upload", exact=True).click()
            expect(page.locator("#message")).to_have_text("Waiting for matching video")
            expect(page.locator("#start")).to_be_disabled()
            page.locator("#files").set_input_files(video)
            page.get_by_role("button", name="Upload", exact=True).click()
            expect(page.locator("#message")).to_have_text("Sources staged")
            page.get_by_role("button", name="Validate sources").click()
            expect(page.locator("#validation")).to_contain_text("Recording 2", timeout=60000)
            page.get_by_role("button", name="Process survey").click()
            expect(page.locator("#caption")).to_contain_text("of 14", timeout=180000)
            expect(page.locator("#catalog").get_by_role("button").filter(has_text=label)).to_have_count(1)
            assert request(old_photo) == old_photo_bytes
            prefix = page.locator("#photo").get_attribute("src").split("/images/")[0]
            bundle = request(prefix + "/survey.zip")
            with ZipFile(io.BytesIO(bundle)) as export:
                points = json.loads(export.read("points.geojson"))["features"]
                routes = json.loads(export.read("route.geojson"))["features"]
                assert len(routes) == 2
                assert len(points) == 14 and len({p["properties"]["image_path"] for p in points}) == 14
                assert [p["properties"]["recording_number"] for p in points] == [1]*7 + [2]*7
                assert all(export.read(p["properties"]["image_path"]).startswith(b"\xff\xd8") for p in points)
                gpkg = folder / "combined.gpkg"
                gpkg.write_bytes(export.read("points.gpkg"))
                assert pyogrio.read_info(gpkg, layer="points")["features"] == 14

            page.locator("#publish-layers").select_option("route")
            page.get_by_role("button", name="Publish locally", exact=True).click()
            link = page.get_by_role("link", name="Open published map")
            expect(link).to_be_visible()
            url = link.get_attribute("href")
            published = context.new_page()
            published.goto(base + url)
            expect(published.locator(".leaflet-overlay-pane path")).to_have_count(2)
            expect(published.locator("figure")).to_be_hidden()
            expect(published.locator(".photo-marker")).to_have_count(0)

            page.locator("#publish-layers").select_option("points")
            page.get_by_role("button", name="Update published map").click()
            expect(page.locator("#message")).to_have_text("Published map updated.")
            published.reload()
            expect(published.locator("#caption")).to_contain_text("of 14")
            expect(published.locator(".leaflet-overlay-pane path")).to_have_count(0)

            page.locator("#publish-layers").select_option("both")
            page.get_by_role("button", name="Update published map").click()
            expect(page.locator("#message")).to_have_text("Published map updated.")
            published.reload()
            expect(published.locator(".leaflet-overlay-pane path")).to_have_count(2)
            expect(published.locator("#caption")).to_contain_text("of 14")

            page.get_by_role("button", name="Version 2.0.0-alpha.3").click()
            dialog = page.get_by_role("dialog", name="About StreetView")
            expect(dialog).to_be_visible()
            expect(dialog.get_by_role("link", name="Mark Urupa")).to_have_attribute(
                "href", "https://www.linkedin.com/in/mark-urupa/")
            page.keyboard.press("Escape")
            expect(dialog).to_be_hidden()
        print("Appended recording, 14-photo export, all publication modes and About passed.")
    finally:
        for survey in json.loads(request("/api/v2/surveys")):
            if survey["label"] == label:
                request("/api/v2/surveys/" + survey["id"], "DELETE")


if __name__ == "__main__":
    main()
