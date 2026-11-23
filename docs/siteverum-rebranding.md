# SiteVerum rebranding and compatibility guide

**Status:** Prepared in `feature/siteverum-rebranding`. Repository rename, Pages deployment, tests, new signed APK, and release are not performed by this branch.

## Name and project history

**SiteVerum**, formerly **StreetView v2.0**, is the same self-hosted open-source geospatial imagery application. The name was changed in November 2026 to establish an independent identity and reflect additional survey analysis and modular processing capabilities. The abbreviation **SV** remains intentional.

## What stays compatible

- Android `applicationId` and source package: `com.example.streetview`; do not change without an explicit Android migration strategy.
- Recording basenames: `SV_YYYYMMDD_HHMMSS.mp4`, matching `.log` / ZIP; keep old and new recordings readable.
- Android on-disk storage and preference names (`StreetView`, `streetview_prefs`): remain to preserve local recordings and user preferences.
- API request header `X-StreetView-Request`, API routes, database schema and existing auth.
- Deployment environment variables `SV_*`, existing Postgres database, Docker Compose project identity and volume names.
- Release tag `v2.0.0-alpha.6` and existing asset `StreetView.apk`: historical, not renamed or rebuilt.
- Historical release reports and verification documents retain the original name as an accurate record.

## GitHub repository rename (manual after approval)

1. Validate that `siteverum` is available under `markfishurupa-dot`. Do not create a fresh repository.
2. Review and merge the rebranding PR after the acceptance tests below pass.
3. On GitHub: **Settings → General → Repository name**: `streetview-v2` → `siteverum`.
4. Update local Git clones:

   ```powershell
   git remote set-url origin https://github.com/markfishurupa-dot/siteverum.git
   git remote -v
   ```

5. Verify old repository and clone links redirect. Do not recreate a new repository at `streetview-v2`, as this could break redirects.

GitHub Pages project sites are **not redirected** on repository rename. The docs are configured for `https://markfishurupa-dot.github.io/siteverum/`; publish/reconfigure Pages from the new repository, verify routes, and update any external links and QR codes. If legacy Pages links are in circulation, consider a dedicated redirect/static forwarding project without reusing the renamed repository path.

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
