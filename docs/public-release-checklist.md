# Public release checklist

- [x] Android source included without release signing material; local debug build completed.
- [ ] Verify capture, location logging, ZIP and separate sharing on a physical Android device.
- [ ] Establish Android source ownership, release signing and update compatibility.
- [x] Add portal screenshots captured with synthetic input and a static synthetic demo dataset.
- [ ] Verify a clean install and backup/restore on advertised platforms.
- [ ] Review third-party notices, container redistribution and Android dependencies.
- [ ] Complete repository, Git history, CI artifacts and image-layer security and privacy audit.
- [ ] Review the StreetView name and trademark considerations with the owner.
- [ ] Validate documentation, demo, links, accessibility and CI.
- [ ] Obtain release approval before enabling public hosting, images, APK distribution or repository visibility.

Phase 2 evidence: the static demo uses twelve crops of a generated image and invented coordinates in the Gulf of Guinea. Playwright exercised navigation, directional markers, route display and documentation navigation at desktop and mobile sizes without API calls. The screenshot capture uses an isolated Compose project and a synthetic video and GPS log. Physical Android screenshots and device tests are outstanding. Windows installer validation used fresh separate Compose projects and confirmed generated credentials survive a second run; native Linux installation and backup/restore remain unverified. Publishing workflows are disabled templates.

Google's [Street View ready branding guidelines](https://developers.google.com/streetview/ready/branding) caution against using Street View or similar names for products and assets. Their context is the Street View ready program; the project name requires a separate owner and legal review before public release. No name change has been made.

GitHub Actions currently reports no stored artifacts or releases. A limited scan of Git history and changed filenames found no common credential patterns or tracked signing keys and recordings, but is not a complete security audit. Container image history was inspected; an exhaustive layer scan and redistribution review remain outstanding.

Gitleaks 8.30.1 scanned all 21 reachable commits at the time of review and reported no leaks. The Bash installer also completed twice in a Linux CLI container using the Docker Desktop engine and preserved its generated credentials. A clean native Linux host test remains outstanding.

The owner requested use of survey `SV_20260423_114721` in the demo. Its 183-point processed result is available in an ignored, loopback-only local preview. The real imagery includes road users and vehicle details. Review faces, plates, location and distribution rights before adding it to a public release. The tracked demo still contains synthetic data; rebuilding the site removes the real local overlay until it is reapplied. The Android guide now includes owner-provided app screenshots; a signed downloadable APK and end-to-end device verification remain outstanding.
