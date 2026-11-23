
"""Exercise the modules and publication UI through Microsoft's installed Edge."""
import argparse
import csv
import json
import subprocess
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright
from portal_browser import sign_in
import pyogrio

from module_acceptance import BASE, SETTINGS, make_survey, request
from module_fixtures import fixture_zip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path)
    parser.add_argument("--temporary", action="store_true")
    args = parser.parse_args()
    survey, source = make_survey(args.sample)
    module = "browser-poles-" + uuid4().hex[:6]
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge")
            context = browser.new_context(http_credentials={"username": "admin", "password": SETTINGS["SV_ADMIN_PASSWORD"]})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            sign_in(page, BASE, SETTINGS["SV_ADMIN_PASSWORD"])
            page.get_by_role("button", name="Modules", exact=True).click()
            page.locator("#module-zip").set_input_files({"name": "fixture.zip", "mimeType": "application/zip",
                                                        "buffer": fixture_zip(module)})
            page.get_by_role("button", name="Install ZIP").click()
            expect(page.locator("#module-manager-status")).to_contain_text("Fixture poles 1.0.0 installed")
            page.locator("#module-manager").get_by_role("button", name="Close", exact=True).click()
            page.locator(f'[data-survey="{survey.rsplit("/", 1)[-1]}"]').click()
            expect(page.get_by_role("heading", name="Additional Processing")).to_be_visible()
            page.locator("#module-choice").select_option(module + "/1.0.0")
            page.locator('#module-parameters input[name=delay]').fill("4")
            expect(page.locator("#module-parameters > li")).to_have_count(2)
            if not args.temporary:
                page.get_by_role("checkbox", name="Keep results temporary").uncheck()
            page.get_by_role("button", name="Run module").click()
            expect(page.get_by_label("Module progress")).to_be_visible()
            page.get_by_role("button", name="Open results").click(timeout=75000)
            if args.temporary:
                expect(page.locator("#module-temporary-notice")).to_contain_text("Download GeoJSON")
                expect(page.locator(".module-pin")).to_have_count(0)
                page.get_by_label("Add temporary layer to map").check()
            else:
                expect(page.locator(".module-pin")).to_have_count(1)
                page.get_by_label("Show layer on map").uncheck()
                expect(page.locator(".module-pin")).to_have_count(0)
                page.get_by_label("Show layer on map").check()
            page.locator(".module-pin").click()
            expect(page.locator("#module-feature")).to_contain_text("Source photo evidence")
            expect(page.locator(".module-bounding-box")).to_have_count(1)
            expect(page.locator(".edit-handle")).to_be_visible()
            latitude = page.locator("#module-feature").get_by_label("Y", exact=True)
            original_lat = float(latitude.input_value())
            grab = page.locator(".edit-handle").bounding_box()
            assert grab
            x, y = grab["x"] + grab["width"] / 2, grab["y"] + grab["height"] / 2
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + 12, y + 8, steps=5)
            page.mouse.up()
            assert float(latitude.input_value()) != original_lat
            page.get_by_label("Feature review state").select_option("approved")
            latitude.fill(str(original_lat + .0001))
            if args.temporary:
                check_temporary_review(page, survey, source, module, original_lat)
                assert not errors, errors
                browser.close()
                print(f"Temporary map, browser-only review, GeoJSON export and zero persisted results passed ({module})")
                return
            page.get_by_role("button", name="Save review").click()
            expect(page.locator("#module-status")).to_have_text("Review saved.")
            page.get_by_label("Export approved only").check()
            with page.expect_download() as download:
                page.get_by_role("link", name="GPKG", exact=True).click()
            with TemporaryDirectory() as folder:
                path = Path(folder) / "poles.gpkg"
                download.value.save_as(path)
                info = pyogrio.read_info(path, layer="poles")
                assert info["features"] == 1 and info["crs"] == "EPSG:4326", info
            run = next(row for row in request(survey + "/module-runs") if row["module_id"] == module)
            api = f"/api/v2/module-runs/{run['id']}"
            item = request(api + "/features")["features"][0]
            assert abs(item["geometry"]["coordinates"][1] - original_lat - .0001) < 1e-9
            geojson = request(api + "/export?layer=poles&format=geojson&approved=true")
            assert geojson["features"] == [item]
            table = request(api + "/export?layer=poles&format=csv&approved=true", binary=True).decode()
            row = next(csv.DictReader(StringIO(table)))
            assert [float(row["lon"]), float(row["lat"])] == item["geometry"]["coordinates"]
            page.locator(".module-pin").click()
            page.get_by_label("Feature review state").select_option("rejected")
            page.get_by_role("button", name="Reset location").click()
            expect(page.locator("#module-feature")).to_be_hidden()
            item = request(f"/api/v2/module-runs/{run['id']}/features")["features"][0]
            assert item["geometry"] == item["properties"]["original_geometry"]
            assert item["properties"]["review_state"] == "rejected"
            assert not errors, errors
            browser.close()
        print(f"Browser module ZIP, form, progress, layer, evidence, review, coordinates and GeoPackage download passed ({module})")
    finally:
        request(survey, "DELETE")


def check_temporary_review(page, survey, source, module, original_lat):
    page.get_by_role("button", name="Keep review in this tab").click()
    expect(page.locator("#module-status")).to_contain_text("Download GeoJSON")
    page.get_by_label("Export approved only").check()
    with page.expect_download() as downloaded:
        page.get_by_role("button", name="Download GeoJSON").click()
    features = json.loads(downloaded.value.path().read_text(encoding="utf-8"))["features"]
    assert len(features) == 1 and features[0]["properties"]["review_state"] == "approved"
    assert abs(features[0]["geometry"]["coordinates"][1] - original_lat - .0001) < 1e-9
    run = next(row for row in request(survey + "/module-runs") if row["module_id"] == module)
    assert run["temporary"] and run["expires_at"]
    api = f"/api/v2/module-runs/{run['id']}"
    feature = request(api + "/features")["features"][0]
    assert feature["properties"]["review_state"] == "pending"
    assert abs(feature["geometry"]["coordinates"][1] - original_lat) < 1e-9
    assert feature["evidence"][0]["url"].startswith(survey + "/runs/" + source + "/images/")
    assert request(api + "/artifacts")
    request(survey + "/publication/publish", "POST",
            {"module_layers": [{"run": run["id"], "layer": "poles"}]}, 409)
    sql = f"""SELECT
        (SELECT count(*) FROM module_features WHERE run='{run["id"]}'),
        (SELECT count(*) FROM module_artifacts WHERE run='{run["id"]}'),
        (SELECT summary IS NULL FROM module_runs WHERE id='{run["id"]}');"""
    command = ["docker", "exec", "streetview-v2-modules-dev-db-1", "psql", "-U", "streetview", "-d", "streetview", "-Atc"]
    assert subprocess.check_output([*command, sql], text=True).strip() == "0|0|t"
    subprocess.run([*command, f"""UPDATE module_runs SET finished=now()-interval '25 hours' WHERE id='{run["id"]}'"""],
                   check=True, capture_output=True)
    request(api + "/features", status=410)
    request(api + "/artifacts", status=410)


if __name__ == "__main__":
    main()
