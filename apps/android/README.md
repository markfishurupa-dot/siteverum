# SiteVerum Capture (Android)

This directory contains the SiteVerum Capture Android 1.3.1 source. It records video and GPS data for import into the SiteVerum portal. It requires Android 8.0 (API 26) or newer, camera and precise location permissions, and Google Play services for location.

For the illustrated recording and sharing workflow, see the [Android capture guide](../../site/src/content/docs/start/android.md).

Open this directory in Android Studio with an Android SDK containing API 36 and a JDK compatible with Android Gradle Plugin 8.13.2. Let Gradle sync and run the app on a device, or build a debug APK with `./gradlew assembleDebug` (Windows: `gradlew.bat assembleDebug`). The output is `app/build/outputs/apk/debug/app-debug.apk`.

Use the app to start and stop a recording, then export the session ZIP. Upload the ZIP to the portal, or upload the matching MP4 and LOG separately. Confirm GPS accuracy and camera orientation before recording.

Debug builds use the local debug signing key. The signed release APK is available from [SiteVerum 2.1 on GitHub](https://github.com/markfishurupa-dot/streetview-v2/releases/tag/v2.1.0). The release signing key is kept private.
