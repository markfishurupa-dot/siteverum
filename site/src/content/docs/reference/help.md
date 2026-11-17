---
title: Troubleshooting and FAQ
---

**Docker is unavailable:** start Docker Desktop and check `docker compose version` and `docker info`.

**Cannot sign in:** use `admin` and the value of `SV_ADMIN_PASSWORD` in `deploy/.env`. Preserve the original database password when restarting an existing volume.

**Validation cannot process the recording:** check that the MP4 and LOG have matching file names and that the ZIP contains one pair. Download the validation report for details.

**The map has no streets:** choose OpenStreetMap in the map layers control. Tiles require a network connection.

**Can other people open localhost?** Localhost refers to the device opening the address. External access needs a separately configured network route.

**How do I restart?** Run `docker compose -f deploy/compose.yaml restart`. Surveys and artifacts persist in Docker volumes.
