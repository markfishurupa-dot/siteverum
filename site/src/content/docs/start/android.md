---
title: Android capture
---

Open `apps/android` in Android Studio, install Android SDK 36 and use a compatible JDK. Run on an Android 8.0 or newer device, or use `gradlew.bat assembleDebug` on Windows and `./gradlew assembleDebug` on Linux. Install the debug APK from `app/build/outputs/apk/debug/` with Android Studio or `adb install -r app/build/outputs/apk/debug/app-debug.apk`.

Allow camera and precise location access. Start a recording, stop it when finished, then use Recordings to create and share a ZIP or share the matching MP4 and LOG. The ZIP may take time to finish. The portal checks that both files exist and share a base name.

The debug build uses a local debug key. A signed release APK is not distributed yet. Recording and sharing on a physical device still require release validation.
