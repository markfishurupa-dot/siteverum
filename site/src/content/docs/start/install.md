---
title: Install the portal
---

Install Git and Docker Desktop with Linux containers, then clone the repository and enter the checkout. Run these commands in PowerShell:

```powershell
git clone https://github.com/markfishurupa-dot/streetview-v2.git
cd streetview-v2
.\setup.ps1
```

The installer creates credentials if needed and starts the services. For the manual setup, install Python 3 and run:

The Bash installer is available as `bash ./setup.sh`. Testing from a clean native Linux host is pending.

```powershell
git clone https://github.com/markfishurupa-dot/streetview-v2.git
cd streetview-v2
python -c "import secrets; from pathlib import Path; p=Path('deploy/.env'); f=p.open('x'); f.write('SV_DB_PASSWORD='+secrets.token_urlsafe(24)+'\nSV_ADMIN_PASSWORD='+secrets.token_urlsafe(24)+'\n'); f.close()"
docker compose -f deploy/compose.yaml up -d --build --wait
```

Open `http://127.0.0.1:18080/` and sign in as `admin` using `SV_ADMIN_PASSWORD` in `deploy/.env`. Keep the file private and preserve the database password. Set `SV_PORT` in the file to use another port. The default binding accepts connections from the host only.

To stop while preserving data, run `docker compose -f deploy/compose.yaml down`. Docker volumes hold the database and media. Removing them removes survey data. Native Linux installation is not yet verified.
