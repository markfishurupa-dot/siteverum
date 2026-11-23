# SiteVerum Capture (Android)

This directory contains the SiteVerum Capture Android source (original 1.3.0 release branded StreetView). It records video and GPS data for import into the SiteVerum portal. It requires Android 8.0 (API 26) or newer, camera and precise location permissions, and Google Play services for location.

For the illustrated recording and sharing workflow, see the [Android capture guide](../../site/src/content/docs/start/android.md).

Open this directory in Android Studio with an Android SDK containing API 36 and a JDK compatible with Android Gradle Plugin 8.13.2. Let Gradle sync and run the app on a device, or build a debug APK with `./gradlew assembleDebug` (Windows: `gradlew.bat assembleDebug`). The output is `app/build/outputs/apk/debug/app-debug.apk`.

Use the app to start and stop a recording, then export the session ZIP. Upload the ZIP to the portal, or upload the matching MP4 and LOG separately. Confirm GPS accuracy and camera orientation before recording.

Debug builds use the local debug signing key. The original release signing key is private and is not included. Release signing, APK distribution, update compatibility and device testing require separate verification.
