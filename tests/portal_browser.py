"""Sign in to the portal through the same form as a browser user."""

from playwright.sync_api import expect


def sign_in(page, base, password):
    page.goto(base)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page.get_by_role("button", name="Log out", exact=True)).to_be_visible()
