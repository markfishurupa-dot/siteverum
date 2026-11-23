---
title: Android capture guide
description: Install SiteVerum Android 1.3.1, align the camera and share a survey recording.
---

SiteVerum Android records video and a GPS track together for processing in the portal. It requires Android 8.0 or later, camera access, precise location, and Google Play services for location.

## Install SiteVerum 1.3.1

Download the signed APK and open it on your phone. If Android prompts you, permit installation from the browser or file manager you used. Open SiteVerum and grant camera and precise location access. Allow notifications if prompted.

**[Download SiteVerum Android 1.3.1](https://github.com/markfishurupa-dot/siteverum/releases/download/v2.1.0/SiteVerum-1.3.1.apk)** · [Android source](https://github.com/markfishurupa-dot/siteverum/tree/v2.1.0/apps/android)

If you are updating the official 1.3.0 release, 1.3.1 uses the same Android package ID and signing certificate. Back up your recordings before updating. The APK SHA-256 is `73e6ea30d34283458d56cdb6797226e935d4fff01dcfd53c692da482c32c8cd8`.

![SiteVerum 1.3.1 home screen with Start recording and Open recordings](/siteverum/images/android/1.3.1/home.png)

## Set recording quality and align the camera

1. Tap the settings gear. Choose **Standard** or **Optimized (smaller files)**.
2. Choose **Camera alignment (preview)** and mount the phone securely. Set the horizon for what you want to capture.
   - **Road surface and markings.** Move the horizon higher in the frame so more of the road is visible.
   - **Poles and tall assets.** Move the horizon lower in the frame so pole tops stay in view. Check that bases remain visible if they matter to the survey.
3. Check framing with the phone in its recording orientation, then go back to the home screen.

![Recording quality options, Camera alignment preview and version 1.3.1](/siteverum/images/android/1.3.1/settings.png)

![Camera alignment preview with a horizon guide](/siteverum/images/android/1.3.1/alignment.png)

## Record the route

Tap **Start recording**. Check that the app shows **Recording** and is collecting GPS points. The status card shows speed, accuracy, point count and elapsed time. Recording can continue in the background while you use a navigation app. When the route is complete, return to SiteVerum and tap **Stop recording**.

![Active recording showing GPS accuracy, point count, elapsed time and Stop recording](/siteverum/images/android/1.3.1/recording.png)

## Review and share recordings

1. Tap **Open recordings**. Use **View data** or **Open log** to inspect a session.
2. Tap **Share** to share the MP4 and LOG separately. For a single archive, open the session's three-dot menu, choose **Archive (ZIP)**, then choose **Share ZIP** when the archive is ready.
3. [Import the recording into the portal](/siteverum/guide/first-survey/) as a ZIP or as a matching MP4 and LOG with the same base filename.

![Recordings list with session actions and the Share ZIP menu option](/siteverum/images/android/1.3.1/recordings.png)
