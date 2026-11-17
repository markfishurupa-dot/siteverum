# StreetView 2.0 release readiness

**Scope:** This checklist governs a **versioned public release with installable assets**, not whether the source repository is visible.

**Current state (17 November 2026):** The repository and GitHub Pages documentation/demo are already **public**. The portal has a locally tested Docker deployment and the Android source builds in CI. There is **no formal GitHub Release, publicly distributed signed Android APK, or approved GHCR container release**. Do not equate public source visibility with completed release acceptance.

## Verified or implemented

- [x] Android 1.3.0 source is present in `apps/android` with release signing material excluded.
- [x] Local Android debug build and GitHub Android debug-build workflow succeeded.
- [x] Docker-based portal and processing workflow are implemented; earlier Windows/Docker Desktop browser and GIS export tests passed.
- [x] Windows installer exercised in isolated Compose projects; repeated setup preserved generated credentials.
- [x] Bash installer exercised in a Linux CLI container with Docker Desktop (not a clean native-Linux host test).
- [x] Starlight documentation is built and GitHub Pages deployment has succeeded.
- [x] Static demo is available through GitHub Pages and navigation is covered by Playwright.
- [x] Actual portal screenshots were captured using synthetic test input.
- [x] Earlier targeted scans, including Gitleaks against reachable commits at that time, reported no secrets. **This does not close the complete privacy and redistribution audit.**

## Blockers for a distributable release

- [ ] **Android signed APK:** identify the exact existing release-signed binary, source revision, SHA-256, package identity, version, and signing-certificate fingerprint.
- [ ] **Android field acceptance:** provide device/version details and a test report tied to that exact APK digest, including recording, GPS logging, separate sharing, ZIP export and portal import.
- [ ] **Android upgrade path:** verify whether the signed APK upgrades existing installations without certificate or package-ID conflicts.
- [ ] **Demo imagery and route:** review the public **real** 183-photo survey for faces, plates, location sensitivity, permissions and redistribution terms. The [demo dataset license](../site/public/demo/DATASET_LICENSE.md) does **not** currently grant general reuse rights.
- [ ] **Clean install and recovery:** validate advertised platforms and demonstrate backup/restore of both PostGIS and media volumes to a separate environment.
- [ ] **Distribution license review:** audit all relevant container/base-image, FFmpeg, PostGIS, Python, Android and other transitive obligations and notices.
- [ ] **Security/privacy audit:** scan all reachable Git history, CI artifacts and container layers for credentials and private media; document findings and remedies.
- [ ] **Branding:** resolve product-name/trademark considerations before promoting a versioned release.
- [ ] **Public install assets:** prepare and verify an approved tagged release, signed APK, hashes, and any versioned GHCR images before linking downloads.
- [ ] **Final quality gate:** test documentation links, mobile/desktop demo, accessibility, Docker instructions, fresh install and upgrade instructions.
- [ ] **Owner release sign-off:** approve the exact release commit, APK checksum, container digests and publishing actions.

## Important distinction: publication vs product release

- **Source code:** public now, under AGPL-3.0-only.
- **Documentation/demo:** public now; the demo uses real survey images and coordinates, so data privacy and reuse rights still require explicit confirmation.
- **Portal:** can be built and run locally using the repository's Docker Compose file. Its default API binding is loopback-only.
- **Android:** source and debug-build capability are present, but a downloadable release-signed APK and corresponding public device-test evidence are not available from this repository.
- **Optional ML/YOLO:** not part of the current public portal release.

For the exact Android verification steps, see [Android APK release verification](android-release-verification.md).

## Documentation maintenance notes

The earlier release-preparation records describe a **synthetic** twelve-photo demo and disabled GitHub Pages workflow. Those were historical milestones; they do not describe the currently published real-photo demo or active Pages workflow. Avoid carrying their status forward as current acceptance evidence.

A clean native-Linux host test remains outstanding. The prior Windows Docker tests and Linux CLI-container tests should not be described as full cross-platform certification.

The repository's software license does not automatically license the demonstration photographs, GPS route, third-party map tiles or Android release signing materials.
