---
title: Android capture guide
---

Use the Android app to record video and a GPS track together, then share the files with the person who will process the survey in the StreetView portal. Android 8.0 or later, camera access, precise location and Google Play services for location are required.

## Install and allow permissions

A downloadable signed APK is planned for the [GitHub Releases page](https://github.com/markfishurupa-dot/streetview-v2/releases). **The repository does not currently provide a verified signed APK for general installation.** If you already have an approved, field-tested APK from the project owner, verify its version, signing certificate and checksum before distributing it. The [Android release-verification procedure](https://github.com/markfishurupa-dot/streetview-v2/blob/codex/alpha-implementation/docs/android-release-verification.md) describes those checks. Until a verified release exists, build the debug app from `apps/android` in Android Studio or follow the [source build instructions](https://github.com/markfishurupa-dot/streetview-v2/tree/codex/alpha-implementation/apps/android). Install it on the phone and open StreetView. Grant camera and precise location permission, and allow notifications if requested, so recording status can be shown.

![The Android app home screen showing settings, Start and Open Recordings](https://raw.githubusercontent.com/markfishurupa-dot/streetview-v2/codex/alpha-implementation/site/public/images/android/home.webp)

## Set recording quality and align the camera

1. Tap the **settings gear** at the top right.
2. Choose **Optimized (smaller files)** to reduce the size of recorded video, or leave **Standard** selected for the standard recording quality. Both modes create encoded video files.
3. Select **Camera alignment (preview)** and mount the phone securely in the vehicle. Aim the camera at the street and keep the horizon around the upper third of the preview. Press Back when the position is set.

![The Android settings menu showing Standard, Optimized and Camera alignment](https://raw.githubusercontent.com/markfishurupa-dot/streetview-v2/codex/alpha-implementation/site/public/images/android/settings.webp)

![The Camera alignment screen with positioning instructions](https://raw.githubusercontent.com/markfishurupa-dot/streetview-v2/codex/alpha-implementation/site/public/images/android/alignment.webp)

## Record the route

1. Return to the home screen and tap **Start**. The status changes to **Recording**, and the screen displays the video name, speed, GPS accuracy, point count and elapsed time.
2. You can minimize StreetView and use a navigation app while the survey continues in the background. Check the recording status and location accuracy when it is safe to do so.
3. At the end of the route, return to StreetView and tap **Stop**.

![The Android app recording a survey, with the Stop button displayed](https://raw.githubusercontent.com/markfishurupa-dot/streetview-v2/codex/alpha-implementation/site/public/images/android/recording.webp)

For easier transfers and to reduce heat on some phones, consider dividing a long route into shorter recordings, for example around 30 minutes each. The suitable duration depends on the device, available storage and operating conditions.

## Review and share recordings

1. Tap **Open Recordings**. Each session shows its name and available actions, including **View data**, **Open log**, and **Share**.
2. Tap **Share** to share the available MP4 and LOG files separately. Choose a destination available on the device, such as Google Drive, a messaging app, or a file manager.
3. To send a single archive, open the session's three-dot menu and choose **Archive (ZIP)**. Wait for archiving to finish, then use **Share ZIP** from the menu and choose a destination.
4. In the portal, upload the ZIP or the matching MP4 and LOG with the same base name, then validate and process the survey.

![The Android Recordings screen with session cards and share options](https://raw.githubusercontent.com/markfishurupa-dot/streetview-v2/codex/alpha-implementation/site/public/images/android/recordings.webp)

The app does not offer individual survey deletion, helping field teams avoid deleting recordings accidentally. After confirming that all recordings have been safely transferred, Android's app settings can be used to clear the app's stored data. Clearing cache alone may not remove recordings, and Android versions and devices can handle app-specific files differently. Verify that the recordings are gone and retain copies in the chosen destination before clearing data.

Physical-device checks of all recording, background and sharing flows are still part of the release checklist. No signed release APK is currently distributed.
