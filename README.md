# Shimsy

Django application for a Raspberry Pi–based sample scanner: web UI, CNC motion control, camera capture, and optional integration with an external **stitcher** service for image processing.

Licensed under the [MIT License](LICENSE).

![Shimsy demo](docs/Shimsy_Demo.gif)

---

## Features

- Web control panel to configure and run multi-dish scan sequences
- GPIO stepper control and `gphoto2` camera capture
- Local staging during scans, then copy to a configurable scans directory (local or NFS)
- Scan history, CSV export, unstitched-run tracking, and stitcher upload / rescan workflows

---

## Requirements

- Raspberry Pi or Linux host with GPIO access (Pi 5 / recent Raspberry Pi OS may need the `lgpio` Python package; see [Installation](#installation))
- Python 3.10+
- System packages: `gphoto2`, and optionally `nfs-common` if using NFS storage
- A separate **stitcher** HTTP service (URLs you configure locally — not included in this repo)

---

## Quick start

### 1. Clone this repository

```bash
git clone https://github.com/EcdysisFoundation/shimsy_open.git
cd shimsy_open
```

The default branch is **`main`**. Repository root is the folder that contains `manage.py`.

### 2. Local configuration (required)

Secrets and machine-specific paths are **not** in git. Copy the example file and edit it:

```bash
cp shimsy_local.example.json shimsy_local.json
```

| Key | Purpose |
|-----|---------|
| `django_secret_key` | Unique Django secret (generate a new one per machine) |
| `allowed_hosts` | IPs/hostnames allowed to access the web UI |
| `stitcher_url` | Stitcher API base URL (zip upload), e.g. `http://your-host:8090` |
| `stitcher_js_url` | Stitcher base URL used by backend settings |
| `stitcher_form_url_base` | Browser link prefix after upload (no trailing slash), e.g. `http://your-host:3000/core/stitcher-form` |
| `shimsy_scans_base` | Directory for completed scan runs |
| `shimsy_staging` | Fast local directory during capture (e.g. `/mnt/shimsy_tmp`) |
| `shimsy_temp_base` | Temp workspace for NAS helper scripts |
| `nas_ip` | NFS server IP (if using NAS helpers) |
| `nas_export` | NFS export path |
| `repo_home` | Absolute path to this clone on the device |

`shimsy_local.json` is listed in `.gitignore` — **never commit it**.

Environment variables can override JSON values; see `shimsy_secrets.py` (`DJANGO_SECRET_KEY`, `SHIMSY_SCANS_BASE`, `STITCHER_URL`, `NAS_IP`, `DJANGO_ALLOWED_HOSTS`, etc.).

### 3. Python environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
```

On **Raspberry Pi 5** or newer OS images, if scans fail with `ModuleNotFoundError: No module named 'lgpio'`, ensure `lgpio` is installed (`pip install lgpio` or use your OS package). The included `requirements.txt` lists `lgpio` for that backend.

### 4. Scan path files (per device)

Create at the repo root (gitignored; not shipped with the repo):

- `manual_path.json` — default dish positions (`capture_points`, `final_position`)
- `custom_path.json` — optional custom layout
- `controller/template_flag.json` — `{"template": "default"}` or `{"template": "custom"}` (the UI can create this)

### 5. Run the development server

GPIO and camera access often require root on the Pi:

```bash
sudo ./venv/bin/python manage.py runserver 0.0.0.0:8000
```

Open `http://<device-ip>:8000` (the IP must appear in `allowed_hosts` in `shimsy_local.json`).

For production deployments, use a proper WSGI/ASGI server instead of Django’s development server.

---

## Test mode (no NFS / production scans path)

```bash
export SHIMSY_SCANS_BASE="$(pwd)/test_shimsy_scans"
export SHIMSY_STAGING="$(pwd)/test_shimsy_staging"
mkdir -p test_shimsy_scans test_shimsy_staging
python manage.py migrate
sudo ./venv/bin/python manage.py runserver 0.0.0.0:8000
```

---

## Storage layout

- **During a run:** images are written to **staging** (`shimsy_staging`, or a `.staging` subdirectory under the scans base if staging is unset).
- **After the run:** data is moved under **`shimsy_scans_base`**.

Optional: install the NAS monitor from `controller/scripts/nas_monitor.service.example` (edit paths and user for your system).

---

## Web UI routes

| Path | Description |
|------|-------------|
| `/` | Main control panel |
| `/history/` | Scan history and CSV export |
| `/unstitched/` | Runs not yet sent to the stitcher |
| `/rescan-samples/` | Rescan requests from the stitcher workflow |

---

## Runtime files (gitignored)

The application writes state under `controller/` and `db.sqlite3` at the repo root. See `.gitignore` for the full list.

---

## Contributing

This repository is the **public** open-source copy. Development may occur in a private fork; contributions via pull requests to `shimsy_open` are welcome when that process is enabled by the maintainers.

---

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| `DisallowedHost` | Add your host/IP to `allowed_hosts` in `shimsy_local.json` |
| Stitcher upload fails | `stitcher_url`, network reachability, stitcher service running |
| Scan script fails (GPIO) | Run with `sudo`; install `lgpio` on Pi 5; see `requirements.txt` |
| Camera errors | `gphoto2 --auto-detect`, USB cable, permissions |
| NFS / missing scans path | `shimsy_scans_base`, mount, `nas_ip` / `nas_export` |

---

## License

Copyright (c) Ecdysis Foundation. See [LICENSE](LICENSE).
