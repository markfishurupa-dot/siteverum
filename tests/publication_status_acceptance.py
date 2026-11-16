"""Verify publication indicators, pinned map revisions, and dialogs in Edge."""
import json
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from compose_acceptance import base, cleanup_surveys, fixture, password, request


def main():
    label = "Publication test " + uuid4().hex[:10]
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge")
            context = browser.new_context(http_credentials={"username": "admin", "password": password})
            page = context.new_page()
            page.goto(base)
            page.locator("#label").fill(label)
            page.get_by_role("button", name="Create survey").click()
            expect(page.locator("#title")).to_have_text(label)
            entry = page.locator("#catalog button").filter(has_text=label)
            dot = entry.locator(".publication-dot")
            expect(dot).to_be_hidden()
            page.get_by_role("button", name="Supported recording files").click()
            help_dialog = page.get_by_role("dialog", name="Supported recording files")
            expect(help_dialog).to_contain_text("ZIP exported from the StreetView mobile app")
            expect(help_dialog).to_contain_text("matching MP4 video and GPS LOG")
            help_dialog.get_by_role("button", name="Close").click()
            expect(help_dialog).to_be_hidden()

            page.locator("#files").set_input_files(fixture)
            page.get_by_role("button", name="Upload", exact=True).click()
            expect(page.locator("#message")).to_have_text("Sources staged")
            page.get_by_role("button", name="Validate sources").click()
            expect(page.get_by_role("link", name="Download report")).to_be_visible(timeout=60000)
            page.get_by_role("button", name="Process survey").click()
            expect(page.locator("#caption")).to_contain_text("of 7", timeout=120000)
            expect(dot).to_be_hidden()

            page.get_by_role("button", name="Publish locally", exact=True).click()
            expect(dot).to_have_attribute("data-state", "current")
            expect(dot).to_have_attribute("aria-label", "Published")
            expect(entry.locator(".survey-name")).to_have_text(label)
            url = page.get_by_role("link", name="Open published map").get_attribute("href")
            metadata_path = "/api/v2/published" + url
            first_job = json.loads(request(metadata_path))["job"]

            page.locator("#rotation").select_option("90")
            page.get_by_role("button", name="Process survey").click()
            expect(dot).to_have_attribute("data-state", "outdated", timeout=120000)
            expect(dot).to_have_attribute("aria-label", "Changes pending publication")
            assert json.loads(request(metadata_path))["job"] == first_job
            page.get_by_role("button", name="Republish map").click()
            expect(dot).to_have_attribute("data-state", "current")
            assert json.loads(request(metadata_path))["job"] != first_job

            published_job = json.loads(request(metadata_path))["job"]
            page.get_by_role("button", name="Add recording").click()
            page.locator("#files").set_input_files(fixture)
            page.get_by_role("button", name="Upload", exact=True).click()
            expect(dot).to_have_attribute("data-state", "outdated")
            expect(page.get_by_role("button", name="Republish map")).to_be_disabled()
            assert json.loads(request(metadata_path))["job"] == published_job

            page.get_by_role("button", name="Delete survey", exact=True).click()
            deletion = page.get_by_role("dialog", name="Delete survey?")
            expect(deletion).to_contain_text(label)
            deletion.get_by_role("button", name="Cancel", exact=True).click()
            expect(deletion).to_be_hidden()
            expect(entry).to_be_visible()
            assert request(url)
            page.get_by_role("button", name="Delete survey", exact=True).click()
            deletion.get_by_role("button", name="Delete survey", exact=True).click()
            expect(deletion).to_be_hidden()
            expect(entry).to_have_count(0)
            request(url, expected=404)
        print("Upload help, publication dot transitions, pinned map, and delete confirmation passed.")
    finally:
        cleanup_surveys([label])


if __name__ == "__main__":
    main()
