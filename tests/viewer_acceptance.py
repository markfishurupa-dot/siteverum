"""Run against the local Compose stack with the private Android fixture configured."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import expect, sync_playwright

from compose_acceptance import base, browser_import, fixture, password, request


def main():
    with TemporaryDirectory() as tmp, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_context(http_credentials={"username": "admin", "password": password}).new_page()
        # Exercise the layer switch without sending automated tile traffic to OSM.
        tiles = []
        def intercept(tile):
            tiles.append(tile.request.url)
            tile.abort()
        page.route("https://tile.openstreetmap.org/**", intercept)
        page.goto(base)
        browser_import(page, "Viewer acceptance", fixture, Path(tmp) / "original.gpkg")
        page.get_by_text("OpenStreetMap", exact=True).click()
        expect(page.locator(".leaflet-control-attribution")).to_contain_text("OpenStreetMap")
        assert tiles
        page.get_by_text("Survey only", exact=True).click()
        page.evaluate("viewer.map.setView(viewer.location(viewer.points[0]), 18, {animate:false})")
        expect(page.locator(".point-marker")).to_have_count(7)
        page.evaluate("viewer.map.setView(viewer.location(viewer.points[0]), 19, {animate:false})")
        expect(page.locator(".arrow-marker").first).to_be_visible()
        assert page.locator(".arrow-marker").count() <= 7
        # Test the viewport culling independently of pixel drag distances.
        page.evaluate("viewer.map.panBy([10000, 10000], {animate:false})")
        expect(page.locator(".arrow-marker")).to_have_count(0)

        sizes = page.locator("#photo").evaluate("(img) => [img.naturalWidth, img.naturalHeight]")
        page.locator("#rotation").select_option("90")
        page.get_by_role("button", name="Process survey").click()
        expect(page.locator("#photo")).to_have_js_property("naturalWidth", sizes[1], timeout=120000)
        expect(page.locator("#photo")).to_have_js_property("naturalHeight", sizes[0])
        photo = page.locator("#photo").get_attribute("src")
        geojson = json.loads(request(photo.split("/images/")[0] + "/points.geojson"))
        longitude, latitude = geojson["features"][0]["geometry"]["coordinates"]
        page.get_by_text("Add a photo point", exact=True).click()
        page.locator("#point-lat").fill(str(latitude))
        page.locator("#point-lon").fill(str(longitude))
        page.locator("#point-time").fill("2")
        page.get_by_role("button", name="Add point and process").click()
        expect(page.locator("#caption")).to_contain_text("of 8", timeout=120000)
        photo = page.locator("#photo").get_attribute("src")
        prefix = photo.split("/images/")[0]
        data = json.loads(request(prefix + "/points.geojson"))
        manual = [feature for feature in data["features"] if feature["properties"]["manual"]]
        assert len(manual) == 1 and manual[0]["properties"]["requested_ms"] == 2000
        assert request(prefix + "/" + manual[0]["properties"]["image_path"]).startswith(b"\xff\xd8")

        page.get_by_role("button", name="Publish locally", exact=True).click()
        link = page.get_by_role("link", name="Open published map")
        expect(link).to_be_visible()
        url = link.get_attribute("href")
        published = page.context.new_page()
        published.goto(base + url)
        expect(published.locator("#title")).to_have_text("Viewer acceptance")
        expect(published.locator("#caption")).to_contain_text("Photo 1 of 8")
        expect(published.locator("#add-point")).to_have_count(0)
        request(url, auth=False, expected=401)
        page.get_by_role("button", name="Unpublish locally", exact=True).click()
        expect(link).to_be_hidden()
        request(url, expected=404)
        request(published.locator("#photo").get_attribute("src"), expected=404)
    print("Rotation, manual photo point, basemap switch, zoom markers, viewport culling and local publication passed.")


if __name__ == "__main__":
    main()
