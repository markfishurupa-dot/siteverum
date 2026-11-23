---
title: Publish a read-only map
description: Decide who can view a survey and understand the difference between publishing and internet access.
---

Publishing creates a **read-only snapshot** of a selected completed survey run. Visitors can explore the chosen layers and photographs, but cannot use the administrator's editing or processing tools.

## Publish from the workspace

1. Open a processed survey in your authenticated SiteVerum workspace.
2. Select **Published map layers**: **Route and photo points**, **Route only**, or **Photo points only**.
3. Choose **Default basemap**: **Survey only** (no online street tiles) or **OpenStreetMap** (tiles requested from its servers).
4. Decide whether to enable **Publicly available**.
5. Select **Publish locally**, then **Open published map**.

The published page is tied to the selected processed run. It does **not** silently update when you edit the workspace. Use **Update published map** or **Republish map** to apply edits and settings to visitors.

## Understand access modes

| Setting | Who can view the published map? |
| --- | --- |
| **Publicly available** off (default) | An authenticated administrator who can reach SiteVerum |
| **Publicly available** on | Anyone who can reach the SiteVerum server at its published URL, without signing in |

**Important:** `Publicly available` changes the map's authentication requirements, **not its network reachability**. The default Docker Compose configuration binds the API to `127.0.0.1` on the host. Enabling public availability alone does not make the map visible to the wider Internet.

If you deliberately expose SiteVerum through a reverse proxy or network tunnel, use HTTPS, review authentication and deployment security, and make sure the route and photographs are suitable for everyone who can reach the URL. Avoid exposing the administrator workspace inadvertently.

## Updating and unpublishing

- **Green publication indicator:** the published run matches the current completed survey revision.
- **Yellow publication indicator:** workspace sources or results changed; republish to update the snapshot.
- **Unpublish:** revokes the published map route through this application.
- **Delete survey:** currently performs a **soft deletion**: it hides the survey and revokes access through SiteVerum, but the original stored media is retained in the Docker volumes. It is not secure erasure.

Survey photographs can include faces, vehicle plates and sensitive locations. Obtain permission and review privacy before enabling anonymous access. Sharing an authenticated map with colleagues is different from making it public to all network visitors.

## External map sharing is an advanced deployment

To let users on another computer view the map, you must intentionally configure network routing to your SiteVerum host. This is not included in the default local setup. See [portal installation](/streetview-v2/start/install/) and your reverse proxy's documentation.

Selecting **OpenStreetMap** requests basemap tiles from external tile servers and requires connectivity; the survey-only backdrop works without online map tiles.
