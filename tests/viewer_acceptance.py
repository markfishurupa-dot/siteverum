"""Run against the local Compose stack with the private Android fixture configured."""
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright
from portal_browser import sign_in

from compose_acceptance import base, browser_import, cleanup_surveys, fixture, password, request


def main():
    label = "Viewer acceptance " + uuid4().hex[:10]
    try:
        run_acceptance(label)
    finally:
        cleanup_surveys([label])


def run_acceptance(label):
    with TemporaryDirectory() as tmp, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_context(http_credentials={"username": "admin", "password": password}).new_page()
        # Exercise the layer switch without sending automated tile traffic to OSM.
        tiles = []
        def intercept(tile):
            tiles.append(tile.request.url)
            tile.abort()
        page.route("https://tile.openstreetmap.org/**", intercept)
        sign_in(page, base, password)
        browser_import(page, label, fixture, Path(tmp) / "original.gpkg")
        page.locator(".leaflet-control-layers").get_by_text("OpenStreetMap", exact=True).click()
        expect(page.locator(".leaflet-control-attribution")).to_contain_text("OpenStreetMap")
        assert tiles
        page.locator(".leaflet-control-layers").get_by_text("Survey only", exact=True).click()
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
        page.get_by_role("button", name="Publish locally", exact=True).click()
        link = page.get_by_role("link", name="Open published map")
        expect(link).to_be_visible()
        url = link.get_attribute("href")
        published = page.context.new_page()
        published.goto(base + url)
        expect(published.locator("#title")).to_have_text(label)
        expect(published.locator("#caption")).to_contain_text("Photo 1 of 7")
        for viewport in ({"width": 1440, "height": 850}, {"width": 390, "height": 844}):
            published.set_viewport_size(viewport)
            published.wait_for_function("""() => {
                const map = document.querySelector("#map").getBoundingClientRect();
                return map.width > 0 && map.height > 0 &&
                    document.documentElement.scrollHeight <= innerHeight + 1 &&
                    document.querySelector(".photo-controls").getBoundingClientRect().bottom <= innerHeight + 1;
            }""")
            expect(published.locator("#photo")).to_be_visible()
            expect(published.get_by_role("button", name="Next photo")).to_be_visible()
        published.get_by_role("button", name="Next photo").click()
        expect(published.locator("#caption")).to_contain_text("Photo 2 of 7")
        expect(published.locator("#add-point")).to_have_count(0)
        request(url, auth=False, expected=401)
        page.get_by_role("button", name="Unpublish locally", exact=True).click()
        expect(link).to_be_hidden()
        request(url, expected=404)
        request(published.locator("#photo").get_attribute("src"), expected=404)
    print("Rotation, basemap switch, zoom markers, viewport culling and local publication passed.")


if __name__ == "__main__":
    main()
