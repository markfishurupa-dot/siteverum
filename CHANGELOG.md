# Unreleased - SiteVerum rebranding

- Adopt **SiteVerum** as the public product and documentation identity (formerly StreetView v2.0).
- Keep existing `SV_` recording filenames, `SV_*` environment variables, Android application ID, survey APIs, database schema, and existing Docker Compose identity for compatibility.
- Keep historical `StreetView.apk` and release `v2.0.0-alpha.6` unchanged. This branch does not distribute a new signed APK.
- Prepare for the GitHub repository rename and documentation project-path migration. See `docs/siteverum-rebranding.md`.

# Changelog

## Unreleased

- Include Android 1.3.0 capture source and debug build instructions.
- Prepare a documentation site and release checks.
- Add a read-only synthetic demo, visual portal walkthrough, and Windows and Linux setup scripts.

## 2.0.0-alpha.6

- Configure published map access and the default basemap per survey.
- Expand the published viewer to use available window height.
- Correct photo point positions and bearings, or delete points while preserving route continuity.
