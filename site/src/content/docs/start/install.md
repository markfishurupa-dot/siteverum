---
title: Install the portal
description: Start StreetView locally with Docker on Windows or Linux.
---

StreetView runs as three Docker Compose services: **web/API**, **processing worker**, and **PostgreSQL/PostGIS**. Original recordings and generated survey files use a persistent Docker volume.

:::note[Supported platforms]
The verified target is **Linux amd64 containers on Windows Docker Desktop**. A Linux installer exists and has been exercised in a Linux CLI container, but a clean native-Linux host installation has not yet been accepted. ARM64 is not a verified target. The current portal supports one administrator and one processing worker.
:::

## Windows: Docker Desktop

### 1. Install the prerequisites

- [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) with its **Linux containers** engine running.
- [Git for Windows](https://git-scm.com/downloads/win).
- Enough free disk space for Docker images, the uploaded MP4 videos, and extracted photographs. Storage depends on survey length and image sampling.

In PowerShell, verify that Docker responds:

```powershell
docker info
docker compose version
```

### 2. Download and start StreetView

```powershell
git clone https://github.com/markfishurupa-dot/streetview-v2.git
cd streetview-v2
.\setup.ps1
```

The installer generates `deploy/.env` with two random passwords **only if the file does not exist**. It builds the containers and waits for the API health check.

If PowerShell blocks local scripts, review `setup.ps1` before making any policy change. Alternatively, use the [manual setup](#manual-setup-for-advanced-users) below.

### 3. Sign in

Open **http://127.0.0.1:18080/** (or the address printed by the setup script).

Use username `admin` and the value of **`SV_ADMIN_PASSWORD`** stored in your local `deploy/.env` file. This file also contains the **database password**: keep it private, do not commit or share it, and preserve it when upgrading.

You can now follow [Process your first survey](/streetview-v2/guide/first-survey/).

## Linux: Docker Engine

You need Linux with **amd64** architecture, Git, OpenSSL, Docker Engine, and the Docker Compose plugin. The Docker daemon must be running and accessible to your user account.

```bash
docker info
docker compose version
git clone https://github.com/markfishurupa-dot/streetview-v2.git
cd streetview-v2
bash ./setup.sh
```

The script creates the same local `deploy/.env` credential file, starts the Compose stack and prints a local address. Visit **http://127.0.0.1:18080/** on the Linux host. If you are accessing it from a different computer, the default loopback binding will not accept that connection; see [Publish a map](/streetview-v2/guide/publishing/) before configuring networking.

:::caution[Linux acceptance status]
The Bash installer has been tested in a Linux container with the Docker Desktop engine. A clean native-Linux host and backup/restore test remain pending. Do not treat Linux support as production-certified yet.
:::

## Manual setup for advanced users

If you do not want to use `setup.ps1` or `setup.sh`, create `deploy/.env` locally using the sample field names in `deploy/.env.example`:

```dotenv
SV_DB_PASSWORD=<generate-a-strong-unique-secret>
SV_ADMIN_PASSWORD=<generate-another-strong-unique-secret>
SV_PORT=18080
```

Replace the placeholders with random secrets, never include angle brackets in the actual values, and keep the file outside Git. From the repository root:

```sh
docker compose -f deploy/compose.yaml up -d --build --wait
```

**Important:** Do not change `SV_DB_PASSWORD` against an initialized Postgres volume without an intentional database credential migration. Changing the environment file by itself does not update an existing database password.

## Everyday operations

Run these commands **from the repository root**:

| Task | Command |
| --- | --- |
| Check status | `docker compose -f deploy/compose.yaml ps` |
| Check service logs | `docker compose -f deploy/compose.yaml logs --tail=100` |
| Restart | `docker compose -f deploy/compose.yaml restart` |
| Stop without removing volumes | `docker compose -f deploy/compose.yaml down` |
| Start again | `docker compose -f deploy/compose.yaml up -d --build --wait` |

You can change the local port with `SV_PORT` in `deploy/.env`, then recreate the stack with `up -d --build --wait`. Check the current host port with `docker compose -f deploy/compose.yaml port api 8000`.

### Protect your survey data

Normal restarts and `docker compose down` preserve named Docker volumes. The database stores survey metadata and spatial records; the media volume stores source recordings and processed outputs. Your `deploy/.env` file is also required to keep access working.

**Do not run `docker compose down -v`** unless you explicitly intend to destroy the associated persistent volumes.

A fully validated backup-and-restore procedure is still a release acceptance item. Before an upgrade or migration, arrange a tested backup of both named volumes and the local environment file. Do not assume a copied volume directory is a consistent database backup while Postgres is running.

## Troubleshooting

- **Docker isn't running:** Start Docker Desktop's Linux engine or the Docker daemon, then retry `docker info`.
- **Port 18080 is already used:** Set `SV_PORT` to another available host port in `deploy/.env` and recreate the stack.
- **Sign-in fails:** Verify that you are reading the existing `SV_ADMIN_PASSWORD`, not a newly generated password in a different checkout.
- **Upload or processing fails:** Check survey validation messages and `docker compose -f deploy/compose.yaml logs --tail=100`.
- **The map has no street background:** Select OpenStreetMap in the layer control. Tiles require Internet access.
- **Another computer cannot connect:** The default Compose file deliberately binds the API to `127.0.0.1`; a separate secured network deployment is required.

For more cases, see [Troubleshooting and FAQ](/streetview-v2/reference/help/).
