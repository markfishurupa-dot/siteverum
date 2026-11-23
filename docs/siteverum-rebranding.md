# SiteVerum rebranding and compatibility guide

**Status:** The public repository and documentation use the SiteVerum name. The original repository URL redirects to the renamed repository.

## Name and project history

**SiteVerum**, formerly **StreetView v2.0**, is a self-hosted geospatial imagery application. The abbreviation **SV** remains intentional.

## Compatibility

The Android application ID, existing recording filenames, environment variables, Docker volumes, database, API headers and module contract identifiers remain in use so that existing installations and survey data continue to work. Historical release tags and APK filenames retain their original names.

GitHub redirects the original repository URL to the renamed repository. Legacy documentation URLs are handled by the account Pages site, which forwards browsers to the corresponding path under `/siteverum/`.

## Build and release verification

- Run Python unit and Compose integration suites using an isolated Compose project and test data.
- Run `npm ci --prefix site`, `npm run build --prefix site`, and the documentation Playwright tests.
- Verify README, internal docs links, demo, screenshots and site base-path deployment.
- Build the Android APK in a controlled environment; confirm unchanged `applicationId`, signing certificate, filenames, camera and ZIP-export behavior.
- Verify existing installed Android 1.3.0 can upgrade from a *newly signed* rebranded APK using the same signing key and a higher `versionCode` before publishing that new APK.
- Ensure existing running Docker installations retain their DB/media volumes. Never use `docker compose down -v` as part of rebranding.
- Inspect icons/screenshots for embedded old branding. Visual assets may need separately produced replacements, without changing app identity.
- Prepare a new SiteVerum release only after tests and permission to publish. Preserve all historical releases unchanged.

This migration is a branding change, not an API/data format migration.
