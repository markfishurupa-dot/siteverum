---
title: Android capture guide
---

Use the Android app to record video and a GPS track together, then share the files with the person who will process the survey in the SiteVerum portal. Android 8.0 or later, camera access, precise location and Google Play services for location are required.

> **Rebranding note:** The historical v2.0.0-alpha.6 release includes the Android 1.3.0 APK with its original **StreetView** launcher branding and filename (`StreetView.apk`). It remains compatible with SiteVerum surveys. A new signed APK is required to update the installed launcher name.

## Install and allow permissions

**[Download the signed legacy StreetView Android 1.3.0 APK](https://github.com/markfishurupa-dot/siteverum/releases/download/v2.0.0-alpha.6/StreetView.apk)** from the [official v2.0.0-alpha.6 release](https://github.com/markfishurupa-dot/siteverum/releases/tag/v2.0.0-alpha.6). The published file is named `StreetView.apk` and its GitHub-reported SHA-256 matches the previously verified signed binary: `e0538baafce11915f1a332180ab4adcfefb7bbb6be34921a18e34fcd0ebc3aa1`. For verification details, read the [APK evidence](https://github.com/markfishurupa-dot/siteverum/blob/codex/alpha-implementation/docs/apk-v1.3.0-verification.md).

On your Android phone, download the APK, approve installation from your chosen browser/file manager if Android prompts you, install and open SiteVerum. Grant camera and precise location access, and allow notifications when requested. **If updating an already installed SiteVerum, back up recordings first:** compatibility with all previously installed signing certificates is not yet confirmed. The source and [debug-build instructions](https://github.com/markfishurupa-dot/siteverum/tree/codex/alpha-implementation/apps/android) remain available for developers.

![The Android app home screen showing settings, Start and Open Recordings](https://raw.githubusercontent.com/markfishurupa-dot/siteverum/codex/alpha-implementation/site/public/images/android/home.webp)

## Set recording quality and align the camera

1. Tap the **settings gear** at the top right.
2. Choose **Optimized (smaller files)** to reduce the size of recorded video, or leave **Standard** selected for the standard recording quality. Both modes create encoded video files.
3. Select **Camera alignment (preview)** and mount the phone securely in the vehicle. Aim the camera at the street and keep the horizon around the upper third of the preview. Press Back when the position is set.

![The Android settings menu showing Standard, Optimized and Camera alignment](https://raw.githubusercontent.com/markfishurupa-dot/siteverum/codex/alpha-implementation/site/public/images/android/settings.webp)

![The Camera alignment screen with positioning instructions](https://raw.githubusercontent.com/markfishurupa-dot/siteverum/codex/alpha-implementation/site/public/images/android/alignment.webp)

## Record the route

1. Return to the home screen and tap **Start**. The status changes to **Recording**, and the screen displays the video name, speed, GPS accuracy, point count and elapsed time.
2. You can minimize SiteVerum and use a navigation app while the survey continues in the background. Check the recording status and location accuracy when it is safe to do so.
3. At the end of the route, return to SiteVerum and tap **Stop**.

![The Android app recording a survey, with the Stop button displayed](https://raw.githubusercontent.com/markfishurupa-dot/siteverum/codex/alpha-implementation/site/public/images/android/recording.webp)

For easier transfers and to reduce heat on some phones, consider dividing a long route into shorter recordings, for example around 30 minutes each. The suitable duration depends on the device, available storage and operating conditions.

## Review and share recordings

1. Tap **Open Recordings**. Each session shows its name and available actions, including **View data**, **Open log**, and **Share**.
2. Tap **Share** to share the available MP4 and LOG files separately. Choose a destination available on the device, such as Google Drive, a messaging app, or a file manager.
3. To send a single archive, open the session's three-dot menu and choose **Archive (ZIP)**. Wait for archiving to finish, then use **Share ZIP** from the menu and choose a destination.
4. In the portal, upload the ZIP or the matching MP4 and LOG with the same base name, then validate and process the survey.

![The Android Recordings screen with session cards and share options](https://raw.githubusercontent.com/markfishurupa-dot/siteverum/codex/alpha-implementation/site/public/images/android/recordings.webp)

The app does not offer individual survey deletion, helping field teams avoid deleting recordings accidentally. After confirming that all recordings have been safely transferred, Android's app settings can be used to clear the app's stored data. Clearing cache alone may not remove recordings, and Android versions and devices can handle app-specific files differently. Verify that the recordings are gone and retain copies in the chosen destination before clearing data.

The complete workflow was tested in two field tests: six survey sessions (routes) were recorded and processed. The project owner reports that the mobile app and portal worked as expected. A test report tying those tests to the exact published APK SHA-256 and compatibility with previously installed signing certificates remain unverified. See the [release checklist](https://github.com/markfishurupa-dot/siteverum/blob/codex/alpha-implementation/docs/public-release-checklist.md) for other verification items.
