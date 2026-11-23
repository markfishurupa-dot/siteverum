"""Exercise validation, cancellation and coordinate corrections in the local app."""
import csv
import io
import json
import re
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile

import pyogrio
from playwright.sync_api import expect, sync_playwright
from portal_browser import sign_in

from compose_acceptance import base, cleanup_surveys, fixture, password, request


def photo_prefix(page):
    return page.locator("#photo").get_attribute("src").split("/images/")[0]


def verify_revision(prefix, original, sequence, coordinates, folder):
    assert request(original + f"/images/{sequence:06d}.jpg") == request(prefix + f"/images/{sequence:06d}.jpg")
    old = json.loads(request(original + "/points.geojson"))["features"][sequence]["geometry"]["coordinates"]
    with ZipFile(io.BytesIO(request(prefix + "/survey.zip"))) as archive:
        points = json.loads(archive.read("points.geojson"))["features"]
        assert points[sequence]["geometry"]["coordinates"] == coordinates
        assert points[sequence]["properties"]["original_coordinates"] == old
        route = json.loads(archive.read("route.geojson"))
        assert route["features"][0]["geometry"]["coordinates"][sequence] == coordinates
        rows = list(csv.DictReader(io.StringIO(archive.read("points.csv").decode())))
        assert [float(rows[sequence]["lon"]), float(rows[sequence]["lat"])] == coordinates
        gpkg = folder / "edited.gpkg"
        gpkg.write_bytes(archive.read("points.gpkg"))
        assert pyogrio.read_info(gpkg, layer="points")["features"] == len(points)
        db = sqlite3.connect(gpkg)
        try:
            assert list(db.execute("select lon,lat from points where frame_index=?", (sequence,)).fetchone()) == coordinates
        finally:
            db.close()


def main():
    label = "Correction test " + uuid4().hex[:10]
    try:
        with TemporaryDirectory() as tmp, sync_playwright() as pw:
            folder = Path(tmp)
            browser = pw.chromium.launch(channel="msedge")
            context = browser.new_context(http_credentials={"username": "admin", "password": password})
            page = context.new_page()
            sign_in(page, base, password)
            page.locator("#label").fill(label)
            page.get_by_role("button", name="Create survey").click()
            expect(page.locator("#title")).to_have_text(label)
            page.locator("#files").set_input_files(fixture)
            page.get_by_role("button", name="Upload", exact=True).click()
            expect(page.locator("#message")).to_have_text("Sources staged")
            page.locator("#accuracy").fill("30")
            deferred = []
            page.route("**/validate", lambda route: deferred.append(route))
            page.get_by_role("button", name="Validate sources").click()
            expect(page.locator("#validation-busy")).to_be_visible()
            assert deferred
            deferred[0].continue_()
            expect(page.get_by_role("link", name="Download report")).to_be_visible(timeout=60000)
            expect(page.locator("#validate")).to_be_hidden()
            expect(page.locator("#validation-busy")).to_be_hidden()
            with page.expect_download() as downloaded:
                page.get_by_role("link", name="Download report").click()
            with ZipFile(downloaded.value.path()) as archive:
                rejected = list(csv.DictReader(io.StringIO(archive.read("excluded_records.csv").decode())))
                assert len(rejected) == 2 and all(float(row["accuracy_m"]) > 30 for row in rejected)
                assert b"GPS_LOW_ACCURACY" in archive.read("report.csv")
                assert b"30 m" in archive.read("report.csv")
            page.get_by_role("button", name="Process survey").click()
            expect(page.get_by_role("button", name="Cancel processing")).to_be_visible()
            expect(page.locator("#start")).to_be_hidden()
            expect(page.get_by_role("progressbar", name="Processing progress")).to_be_visible()
            expect(page.locator("#job-percent")).to_have_text(re.compile(r"^[0-9]+%$"))
            page.get_by_role("button", name="Cancel processing").click()
            expect(page.locator("#job")).to_have_text("Processing cancelled")
            expect(page.get_by_role("button", name="Process survey")).to_be_visible()
            page.get_by_role("button", name="Process survey").click()
            expect(page.locator("#caption")).to_contain_text("of 5", timeout=120000)

            original = photo_prefix(page)
            page.evaluate("viewer.map.setView(viewer.location(viewer.points[0]), 18, {animate:false})")
            page.locator('[title="Photo 1"]').click()
            expect(page.locator(".point-popup")).to_contain_text("Speed")
            expect(page.locator(".point-popup")).to_contain_text("m/s")
            expect(page.locator(".point-popup")).to_contain_text("Bearing")
            page.get_by_role("button", name="Edit", exact=True).click()
            old = json.loads(request(original + "/points.geojson"))["features"][0]["geometry"]["coordinates"]
            updated = [round(old[0] + .0002, 7), round(old[1] + .0002, 7)]
            page.get_by_label("New latitude").fill(str(updated[1]))
            page.get_by_label("New longitude").fill(str(updated[0]))
            page.get_by_role("button", name="Save changes").click()
            expect(page.locator("#job")).to_have_text("Point edit saved", timeout=120000)
            expect(page.locator("#photo")).not_to_have_attribute("src", original + "/images/000000.jpg")
            revised = photo_prefix(page)
            verify_revision(revised, original, 0, updated, folder)

            page.locator('[title="Photo 1"]').click()
            expect(page.locator(".point-popup")).to_contain_text("Original GPS")
            page.get_by_role("button", name="Edit", exact=True).click()
            page.wait_for_function("""() => {
                if (viewer.map._panAnim?._inProgress) return false;
                const marker = document.querySelector(".edit-handle");
                if (!marker) return false;
                const bounds = marker.getBoundingClientRect();
                return marker.contains(document.elementFromPoint(
                    bounds.x + bounds.width / 2, bounds.y + bounds.height / 2));
            }""")
            marker = page.locator(".edit-handle").bounding_box()
            x, y = marker["x"] + marker["width"] / 2, marker["y"] + marker["height"] / 2
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + 32, y + 15, steps=7)
            page.mouse.up()
            new_position = [float(page.get_by_label("New longitude").input_value()),
                            float(page.get_by_label("New latitude").input_value())]
            assert new_position != updated
            page.get_by_role("button", name="Save changes").click()
            expect(page.locator("#job")).to_have_text("Point edit saved", timeout=120000)
            expect(page.locator("#photo")).not_to_have_attribute("src", revised + "/images/000000.jpg")
            revised = photo_prefix(page)
            verify_revision(revised, original, 0, new_position, folder)

            page.locator("#rotation").select_option("180")
            page.get_by_role("button", name="Process survey").click()
            expect(page.locator("#job")).to_have_text("Processing complete", timeout=120000)
            expect(page.locator("#photo")).not_to_have_attribute("src", revised + "/images/000000.jpg")
            edited_points = json.loads(request(photo_prefix(page) + "/points.geojson"))["features"]
            assert edited_points[0]["geometry"]["coordinates"] == new_position

            parent = photo_prefix(page)
            page.evaluate("viewer.map.setView(viewer.location(viewer.points[0]), 19, {animate:false})")
            page.locator('[title="Photo 1"]').click()
            page.get_by_role("button", name="Edit", exact=True).click()
            page.get_by_label("Bearing (degrees)", exact=True).fill("123")
            expect(page.locator(".edit-bearing")).to_have_attribute("style", "transform: rotate(123deg);")
            page.get_by_role("button", name="Save changes").click()
            expect(page.locator("#job")).to_have_text("Point edit saved", timeout=120000)
            expect(page.locator("#photo")).not_to_have_attribute("src", parent + "/images/000000.jpg")
            rotated = photo_prefix(page)
            rotated_points = json.loads(request(rotated + "/points.geojson"))["features"]
            assert rotated_points[0]["properties"]["bearing"] == 123
            assert request(rotated + "/route.geojson") == request(parent + "/route.geojson")

            page.evaluate("viewer.map.setView(viewer.location(viewer.points[1]), 18, {animate:false})")
            page.locator('[title="Photo 2"]').click()
            page.get_by_role("button", name="Edit", exact=True).click()
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="Delete point").click()
            expect(page.locator("#caption")).to_contain_text("of 4", timeout=120000)
            revised = photo_prefix(page)
            remaining = [feature["geometry"]["coordinates"] for i, feature in enumerate(rotated_points) if i != 1]
            route = json.loads(request(revised + "/route.geojson"))
            assert route["features"][0]["geometry"]["coordinates"] == remaining
            assert request(revised + "/images/000001.jpg") == request(rotated + "/images/000002.jpg")

            page.locator("#rotation").select_option("0")
            page.get_by_role("button", name="Process survey").click()
            expect(page.locator("#job")).to_have_text("Processing complete", timeout=120000)
            expect(page.locator("#photo")).not_to_have_attribute("src", revised + "/images/000001.jpg")
            rerun = json.loads(request(photo_prefix(page) + "/points.geojson"))["features"]
            assert [point["geometry"]["coordinates"] for point in rerun] == remaining
            assert rerun[0]["properties"]["bearing"] == 123

            page.get_by_role("button", name="Publish locally", exact=True).click()
            link = page.get_by_role("link", name="Open published map")
            expect(link).to_be_visible()
            published = context.new_page()
            published.goto(base + link.get_attribute("href"))
            expect(published.locator("#caption")).to_contain_text("of 4")
            published.locator('[title="Photo 1"]').click()
            expect(published.locator(".point-popup")).to_contain_text("Bearing")
            expect(published.get_by_role("button", name="Edit", exact=True)).to_have_count(0)
            expect(page.get_by_text("Add a photo point", exact=True)).to_have_count(0)
        print("Validation report, progress/cancel, point movement, bearing, deletion, exports, reprocessing and publication passed.")
    finally:
        cleanup_surveys([label])


if __name__ == "__main__":
    main()
