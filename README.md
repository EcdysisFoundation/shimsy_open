# Shimsy

Django app for the Shimsy scanner: web UI and run control on a Raspberry Pi, with scan images stored on a NAS/server directory (typically NFS-mounted on the Pi).

---

## Repository layout

After `git clone`, the **repository root** is the Django project directory (same folder as `manage.py`, `cnccontroller/`, and `controller/`).

Some machines keep an extra parent folder (e.g. `~/shimmsy/shimsy/`). All commands below assume your **current directory is the repo root** (where `manage.py` lives). If you cloned into a parent path, `cd` into the inner directory that contains `manage.py` first.

---

## Prerequisites

- Raspberry Pi (or Linux host) with GPIO access for the CNC steppers
- Python 3 with `venv`
- **System packages:** `gphoto2` (camera capture), NFS client tools if using NAS (`nfs-common` on Debian/Raspberry Pi OS)
- Network access to your stitcher service (for upload / rescan integration)

---

## Setup (new machine)

### 1. Clone and local secrets

```bash
git clone https://github.com/EcdysisFoundation/Shimsy.git
cd Shimsy   # or cd into the directory that contains manage.py
cp shimsy_local.example.json shimsy_local.json
```

Edit **`shimsy_local.json`** (gitignored — never commit it). Required for production use:

| Key | Purpose |
|-----|---------|
| `django_secret_key` | Django session/signing secret (generate a unique value) |
| `allowed_hosts` | Hostnames/IPs allowed to access the web UI (Pi LAN IP, ZeroTier IP, `localhost`) |
| `stitcher_url` | Stitcher HTTP API base (e.g. `http://host:8090`) — used for zip upload |
| `stitcher_js_url` | Stitcher base URL if referenced from backend settings |
| `stitcher_form_url_base` | Browser link prefix after upload (e.g. `http://host:3000/core/stitcher-form`) |
| `shimsy_scans_base` | Local path where scan runs are stored (often NFS mount point) |
| `shimsy_staging` | Fast local staging dir during capture (e.g. `/mnt/shimsy_tmp`) |
| `shimsy_temp_base` | Temp workspace for NAS sync scripts |
| `nas_ip` | NFS server IP |
| `nas_export` | NFS export path (e.g. `/pool1/srv/shimsy/shimsy_scans`) |
| `repo_home` | Absolute path to this repo on the Pi |

Environment variables override JSON when set (see `shimsy_secrets.py`), including `DJANGO_SECRET_KEY`, `SHIMSY_SCANS_BASE`, `SHIMSY_STAGING`, `STITCHER_URL`, `NAS_IP`, and `DJANGO_ALLOWED_HOSTS` (comma-separated).

For a second scanner (e.g. Myrtle / `melvin` branch), use a **separate** `shimsy_local.json` on that device with that machine’s IPs and paths.

### 2. Python virtual environment

From the repo root:

```bash
python3 -m venv venv
source venv/bin/activate
pip install django gpiozero Pillow requests
```

### 3. Database

```bash
python manage.py migrate
```

Creates `db.sqlite3` in the repo root (gitignored).

### 4. Scan path files (per machine)

Create or copy at the **repo root** (gitignored):

- `manual_path.json` — default dish positions (`capture_points`, `final_position`)
- `custom_path.json` — optional custom layout
- `controller/template_flag.json` — `{"template": "default"}` or `{"template": "custom"}` (created by the UI when needed)

See [Template flag and path JSON files](#template-flag-and-path-json-files) below.

### 5. NFS / scans directory (production)

Mount your scans export at the path set in `shimsy_scans_base`, or use the NAS monitor (optional):

```bash
# Edit paths/user, then install (example unit file):
sudo cp controller/scripts/nas_monitor.service.example /etc/systemd/system/shimsy-nas-monitor.service
sudo nano /etc/systemd/system/shimsy-nas-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now shimsy-nas-monitor.service
```

`controller/scripts/nas_utils.py` can validate and remount using `nas_ip` and `nas_export` from `shimsy_local.json`.

### 6. Run the web app

GPIO and camera access usually require root on the Pi:

```bash
sudo ./venv/bin/python manage.py runserver 0.0.0.0:8000
```

Open `http://<pi-ip>:8000` (IP must be listed in `allowed_hosts` in `shimsy_local.json`).

---

## Test mode (no production scans directory)

To exercise the UI without writing to the real NFS tree, use env overrides (or set the same keys in `shimsy_local.json` for a dev machine):

```bash
export SHIMSY_SCANS_BASE="$(pwd)/test_shimsy_scans"
export SHIMSY_STAGING="$(pwd)/test_shimsy_staging"
mkdir -p test_shimsy_scans test_shimsy_staging
python manage.py migrate   # if not done yet
sudo ./venv/bin/python manage.py runserver 0.0.0.0:8000
```

`test_shimsy_scans/` and `test_shimsy_staging/` are gitignored. If `shimsy_staging` is unset and `/mnt/shimsy_tmp` does not exist, staging falls back to `<scans_base>/.staging`.

---

## Where scan images are stored

- **During a run:** images go to **staging** (`shimsy_staging` in config, often `/mnt/shimsy_tmp`) for speed.
- **After the run:** data is moved under **`shimsy_scans_base`** (final storage, often an NFS mount).

Example production layout:

- Server export: `/srv/shimsy/shimsy_scans` on the storage host
- Pi mount point: set via `shimsy_scans_base` (e.g. `/home/<user>/shimsy_scans`)
- NAS target: `nas_ip` + `nas_export` in `shimsy_local.json`

Paths and IPs are not hardcoded in application source; they come from `shimsy_local.json` (or env).

---

## Template flag and path JSON files

Scanning uses a **template flag** and one of two **path JSON** files:

- **`controller/template_flag.json`** — `{"template": "default"}` or `{"template": "custom"}` (gitignored; UI can update it).
- **`manual_path.json`** (repo root) — used when template is `default`.
- **`custom_path.json`** (repo root) — used when template is `custom`.

Both path files share this shape:

- **`capture_points`:** `[{ "x", "y", "z", "sample" }, ...]` (`sample` is dish number, e.g. `"1"`–`"6"`).
- **`final_position`:** `{ "x", "y", "z" }` after the last capture.

`controller/scripts/run_scan.py` reads the flag, loads the matching JSON, and runs the capture sequence.

---

## Web UI overview

| URL | Purpose |
|-----|---------|
| `/` | Main control panel — configure and start scans |
| `/history/` | Scan history and CSV export |
| `/unstitched/` | Runs not yet sent to stitcher |
| `/rescan-samples/` | Stitcher-driven rescan requests |

Stitcher upload from the home page calls `/upload-to-stitcher/` (backend uses `stitcher_url` from config).

---

## Runtime state (gitignored)

Written by the app during operation; do not commit:

- `controller/scan_config.json`, `last_position.json`, `scan_run_counter.json`
- `controller/template_flag.json`, `current_delay.json`, `rescan_path_temp.json`
- `controller/nas_alert.flag` (if NAS monitor is used)
- `db.sqlite3`

---

## Configuration changes

- **IPs, stitcher URLs, NAS, paths:** edit **`shimsy_local.json`** only (or env vars).
- **systemd NAS monitor:** edit the installed unit from `controller/scripts/nas_monitor.service.example` (the committed `nas_monitor.service` in the repo is an example for one host — copy and customize for each Pi).

---

## Troubleshooting

- **`DisallowedHost`:** add your browser’s host/IP to `allowed_hosts` in `shimsy_local.json`.
- **Stitcher upload fails:** check `stitcher_url` and that the stitcher service is reachable from the Pi.
- **Scans fail to save:** verify `shimsy_scans_base` exists and is writable; check NFS mount (`nas_utils` / NAS monitor).
- **Camera errors:** confirm `gphoto2` is installed and the camera is detected (`gphoto2 --auto-detect`).
- **GPIO / permission errors:** run the server with `sudo` as shown above.
