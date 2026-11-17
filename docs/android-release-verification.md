# Android APK: verification and public distribution

The StreetView Android **1.3.0 source** is at [`apps/android`](../apps/android). The repository's Android CI builds a **debug APK**. A debug build is not the final distributable, even when it compiles successfully.

The existing signed, field-tested application can be included in a GitHub Release **only after the exact APK and its testing evidence have been identified and verified**. This document is a release procedure, not a statement that these checks have passed.

## A. Identify the exact candidate

Before uploading anything to GitHub, record:

| Field | Required evidence |
| --- | --- |
| APK filename and SHA-256 | Digest of the exact APK that will be distributed |
| Source revision | Commit/tag or documented source revision used to build it |
| Android package ID | Check that the package corresponds to the source; source currently uses `com.example.streetview` |
| App version | `versionName` and `versionCode`; source currently declares `1.3.0` and `130` |
| Signing certificate | SHA-256 fingerprint (the certificate fingerprint is public; **never publish the keystore**) |
| Signing provenance | Confirmation of who built and signed this artifact |
| Device results | A field-test report for **this exact binary**, not just another debug/release build |
| Upgrade compatibility | Can an existing installed version be updated without uninstalling or losing recordings? |

A newly signed APK with a different key may **not** install as an update to an older APK with the same package ID. Do not change `applicationId`, the signing key, or the version code without first documenting the upgrade implications.

## B. Verify the APK without exposing secrets

From an Android SDK installation, verify the candidate:

```sh
apksigner verify --verbose --print-certs path/to/StreetView-Android-v1.3.0.apk
```

On Windows PowerShell, calculate the file digest:

```powershell
Get-FileHash -Algorithm SHA256 .\StreetView-Android-v1.3.0.apk
```

On Linux/macOS:

```sh
sha256sum StreetView-Android-v1.3.0.apk
```

Check the package/version using Android SDK tools (such as `aapt dump badging`) or by inspecting installed app information on the test device. Compare the signing certificate and package with the installed field-tested version.

The APK should be **signed for release**, not solely with the Android debug certificate. Retain the signing key securely outside Git, GitHub Issues, release notes, and ordinary CI logs.

## C. Field acceptance checklist

Record the actual phone model, Android version, APK SHA-256, test date, and result for every required test. Mark items PASS/FAIL/NOT TESTED rather than guessing.

| Test | Expected evidence |
| --- | --- |
| Install fresh | APK installs and launches on an eligible Android device |
| Permissions | Camera, precise location and notification flows work as intended |
| Recording | Start/stop creates matching MP4 + LOG |
| GPS contract | LOG contains `timestamp_utc,video_elapsed_ms,recording_start_utc_ms,lat,lon,accuracy_m,speed_mps,bearing,alt_m` |
| Foreground/background | Recording status and files remain consistent when switching apps or locking/unlocking where supported |
| Separate sharing | Export both original MP4 and LOG and import them through the portal |
| ZIP sharing | ZIP contains exactly the matching pair and imports through the portal |
| Media validity | FFprobe decodes MP4; portal validation succeeds or clearly reports GPS warnings |
| Video/GPS matching | First and last usable points reference correct photographs; no missing image references |
| Outdoor survey | Real-world trip produces a usable map and downloadable GeoPackage |
| Upgrade | A previous installed version upgrades with the expected signature and package without unintended data loss |
| Storage and failure | Adequate/low-storage behavior and interruption recovery documented |

Do not claim the app is field-tested in the release notes until the **released APK digest matches the tested APK digest**.

## D. Publish the Android binary

Once the owner has approved signing, testing, branding and redistribution:

1. Create a **draft GitHub Release** with a version/tag and release notes. Do not publish the release prematurely.
2. Attach the verified signed APK, e.g. `StreetView-Android-v1.3.0.apk`.
3. Record the APK SHA-256, app version and required Android version in the release notes.
4. Include clear installation steps: download the APK on Android, review the source, authorize installation from the chosen trusted installer when prompted, then open StreetView and grant the required permissions. Android may ask for permission to install an app from outside a store.
5. Explain the **update path** and certificate compatibility for users with an older StreetView installation.
6. Test the GitHub-downloaded APK once more on a device and compare its SHA-256 to the approved original.

Only then update [the Android guide](../site/src/content/docs/start/android.md) and the [README](../README.md) to link directly to the downloadable release.

**Do not place private keys, unsigned release candidates, or field-survey media in the repository.** A CI debug APK is not proof of signed-release provenance or field acceptance.

## E. Release blockers to resolve with the owner

- Identify and supply the exact existing signed/field-tested APK or build it using the approved release signing key.
- Confirm its signing certificate, package identity and upgrade compatibility.
- Supply a device-test record tied to its SHA-256.
- Complete Android dependency and branding/license approvals.

The portal's AGPL-3.0-only source license is not a substitute for checking Android dependencies and the ownership and distribution rights of the APK.
