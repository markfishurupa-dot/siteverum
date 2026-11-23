"""Verify browser logout and session revocation against the development portal."""

import base64

from playwright.sync_api import expect, sync_playwright

from module_acceptance import BASE, SETTINGS, request


def main():
    password = SETTINGS["SV_ADMIN_PASSWORD"]
    basic = base64.b64encode(f"admin:{password}".encode()).decode()
    api = BASE + "/api/v2/surveys"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        context = browser.new_context(viewport={"width": 390, "height": 850})
        page = context.new_page()
        page.goto(BASE)
        expect(page).to_have_title("Sign in | SiteVerum")
        page.get_by_label("Password", exact=True).fill("invalid-password")
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page.locator("#login-status")).to_have_text("Username or password is incorrect.")
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Sign in", exact=True).click()
        logout = page.get_by_role("button", name="Log out", exact=True)
        expect(logout).to_be_visible()
        assert context.request.get(api).ok
        assert context.request.post(BASE + "/api/v2/session/logout").status == 403

        issued = next(cookie for cookie in context.cookies() if cookie["name"].startswith("siteverum_session"))
        assert issued["httpOnly"] and issued["sameSite"] == "Lax"
        second = context.new_page()
        second.goto(BASE)
        expect(second.get_by_role("button", name="Log out", exact=True)).to_be_visible()
        logout.click()
        for tab in (page, second):
            expect(tab).to_have_title("Sign in | SiteVerum")
        assert context.request.get(api, headers={"Authorization": f"Basic {basic}"}).status == 401

        replay = browser.new_context()
        replay.add_cookies([issued])
        assert replay.request.get(api).status == 401
        replay.close()
        page.goto(BASE)
        expect(page).to_have_title("Sign in | SiteVerum")
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(logout).to_be_visible()
        assert context.request.get(api).ok
        browser.close()
    assert isinstance(request("/api/v2/surveys"), list)
    print("Portal sign-in, multi-tab logout, revoked session replay, and Basic API access passed")


if __name__ == "__main__":
    main()
