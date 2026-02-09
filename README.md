# Shimsy

Django app for the Shimsy scanner: web UI and run control on a Raspberry Pi, with scan images stored on the Ecdysis01 server (mounted on the Pi).

---

## Running on the Raspberry Pi

Clone the repo and use a virtual environment. From the repo root:

```bash
cd shimsy
python3 -m venv venv
source venv/bin/activate
pip install django gpiozero Pillow
```

Run the server from the inner `shimsy` directory (where `manage.py` lives). **Use `sudo`** so the process can access GPIO and any device files used by the scanner:

```bash
cd shimsy
sudo venv/bin/python manage.py runserver 0.0.0.0:8000
```

Then open the UI at `http://<pi-ip>:8000`. Allowed hosts are set in `cnccontroller/settings.py`.

---

## Where scan images are stored

Scans are written to **shimsy_scans**. On the Ecdysis01 server that directory lives under `/srv/shimsy/shimsy_scans`:

On the Raspberry Pi, that same tree is **mounted via NFS** so the app can read and write it locally:

- **On the Pi (mount point):**  
  `/home/ecdysis/shimsy_scans`  
  This is the path used in settings (`SHIMSY_SCANS_BASE` in `cnccontroller/settings.py`) and by the controller scripts. The NAS export used for the mount is `192.168.2.212:/pool1/srv/shimsy/shimsy_scans`. The `nas_utils` module can check and remount this if needed.

So: **physical storage is on the Ecdysis01 server** at `/srv/shimsy/shimsy_scans`; the Pi sees it at `/home/ecdysis/shimsy_scans`.

---

## Template flag and path JSON files

Scanning uses a **template flag** and one of two **path JSON** files to know where to move and capture.

- **`controller/template_flag.json`**  
  Not committed (in `.gitignore`). It holds either `{"template": "default"}` or `{"template": "custom"}`. The web UI can switch between default and custom; that just updates this file.

- **Default path:** `manual_path.json` (in the `shimsy` app directory, same level as `controller/`). Used when `template_flag.json` is `"default"`.

- **Custom path:** `custom_path.json` (same location). Used when `template_flag.json` is `"custom"`. We can save a per-dish path as custom and set the flag to custom or through the dropdown in the UI so runs use that path if needed.

Both path JSON files have the same shape:

- **`capture_points`:** list of `{ "x", "y", "z", "sample" }` (sample is dish number, e.g. `"1"`–`"6"`).
- **`final_position`:** `{ "x", "y", "z" }` for the position after the last capture.

`manual_path.json` and `custom_path.json` are in `.gitignore`; they are machine/shimsy- or run-specific. The scanner script (`controller/scripts/run_scan.py`) reads the template flag, then loads either `manual_path.json` or `custom_path.json` and uses that for the capture sequence.

---

## Other useful details

- **Staging:** Images are written to local staging at `/mnt/shimsy_tmp` during the scan (`STAGING_ROOT` in `run_scan.py`), then moved to `shimsy_scans` afterward (`FINAL_ROOT`). Writing to local disk during capture is much faster than writing directly to the NFS-mounted `shimsy_scans`, so staging keeps the scan itself quick; the copy to the server happens once the run is done.
- **Stitcher:** The app talks to a stitcher service; URLs are in settings (`STITCHER_URL`, `STITCHER_JS_URL`, etc.).
- **Database:** SQLite by default (`db.sqlite3` in the inner `shimsy` directory). Run `python manage.py migrate` once after cloning.
- **State files:** Several JSON files under `controller/` are runtime state (e.g. `scan_config.json`, `last_position.json`, `scan_run_counter.json`) and are gitignored.

If you add or change the Pi’s IP or the NFS server, update `cnccontroller/settings.py` (and `controller/scripts/nas_utils.py` if the NAS IP or export path changes).
