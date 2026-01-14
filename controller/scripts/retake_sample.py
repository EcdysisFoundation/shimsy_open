
import sys
import os
import json
import time
import glob
from datetime import datetime
from gpiozero import DigitalOutputDevice
import subprocess
from PIL import Image, ImageDraw, ImageFont


from staging_utils import create_staging_dir, sync_to_network, check_staging_space


DIR_X = DigitalOutputDevice(27)
STEP_X = DigitalOutputDevice(17)
DIR_Y = DigitalOutputDevice(23)
STEP_Y = DigitalOutputDevice(22)
DIR_Z = DigitalOutputDevice(25)
STEP_Z = DigitalOutputDevice(24)
ENA = DigitalOutputDevice(5)


DELAY = 0.0005
SCAN_CONFIG_PATH = "/home/ecdysis/shimsy/controller/scan_config.json"
MANUAL_PATH = "/home/ecdysis/shimsy/manual_path.json"
MEDIA_ROOT = "/home/ecdysis/shimsy_scans"

def move_axis(dir_pin, step_pin, steps, direction=True):
    dir_pin.value = direction
    for _ in range(abs(steps)):
        step_pin.on()
        time.sleep(DELAY)
        step_pin.off()
        time.sleep(DELAY)

def move_to(dx, dy, dz):
    if dz != 0:
        move_axis(DIR_Z, STEP_Z, dz, dz > 0)
    if dx != 0:
        move_axis(DIR_X, STEP_X, dx, dx > 0)
    if dy != 0:
        move_axis(DIR_Y, STEP_Y, dy, dy > 0)

def capture_image(path, filename):
    os.makedirs(path, exist_ok=True)
    full_path = os.path.join(path, filename)
    for attempt in range(3):
        try:
            subprocess.run([
                "gphoto2", "--capture-image-and-download",
                "--filename", full_path, "--force-overwrite"
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError:
            time.sleep(1 + 0.5 * attempt)
    return False

def create_label_image(sample_name, path, width=800, height=600):
    """Generate label_auto_000.jpg based on sample name"""
    print(f"[DEBUG] Generating label_auto_000.jpg for sample_name = '{sample_name}'")

    try:
        clean_sample_name = sample_name
        if "_" in sample_name:
            parts_with_prefix = sample_name.split("_", 1)
            if len(parts_with_prefix) == 2 and parts_with_prefix[0].isdigit():
                clean_sample_name = parts_with_prefix[1]
        parts = clean_sample_name.split("-")
        if len(parts) == 4:
            site = parts[0]
            year = "2025"
            sample_type = parts[2].replace("Trap", " Trap").replace("Sweep", " Sweep").title()
            transect = parts[3]
        else:
            raise ValueError("Invalid format")
    except Exception:
        site = "Unknown"
        year = "2025"
        sample_type = "Unknown"
        transect = "T?"

    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)

    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font = ImageFont.truetype(font_path, 48)
    except:
        font = ImageFont.load_default()

    lines = [year, f"{sample_type} - {transect}", f"Site: {site}"]
    y_offset = height // 2 - len(lines) * 30

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (width - w) // 2
        y = y_offset + i * 60
        draw.text((x, y), line, fill="black", font=font)

    img.save(path)
    print(f"[INFO] Created label_auto_000.jpg at: {path}")

def main():
    if len(sys.argv) != 2:
        print("Usage: retake_sample.py <sample_number>")
        sys.exit(1)

    try:
        sample_number = int(sys.argv[1])
        if not (1 <= sample_number <= 6):
            raise ValueError("Sample number must be between 1 and 6")
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    with open(SCAN_CONFIG_PATH) as f:
        scan_config = json.load(f)
    with open(MANUAL_PATH) as f:
        manual_data = json.load(f)

    sample_list = scan_config.get("samples", [])
    sample_name = sample_list[sample_number - 1]

    all_points = manual_data.get("capture_points", [])
    capture_points = [pt for pt in all_points if str(pt["sample"]) == str(sample_number)]

    if not capture_points:
        print(f"[ERROR] No capture points found for sample {sample_number}")
        return

    LAST_SCAN_PATH = "/home/ecdysis/shimsy_scans/LAST_SCAN.txt"
    try:
        with open(LAST_SCAN_PATH, "r") as f:
            run_path = ""
            for line in f:
                line = line.strip()
                if line:
                    run_path = line
                    break
        if not run_path:
            raise ValueError("LAST_SCAN.txt had no non-empty lines")
        if not os.path.isdir(run_path):
            raise FileNotFoundError(f"Run folder does not exist: {run_path}")
    except Exception as e:
        print(f"[WARN] Using MEDIA_ROOT because LAST_SCAN.txt invalid: {e}")
        run_path = MEDIA_ROOT

    print(f"[DEBUG] run_path = {run_path}")

    pattern = f"{sample_number}_*"
    candidates = [p for p in glob.glob(os.path.join(run_path, pattern)) if os.path.isdir(p)]
    candidates = sorted(set(candidates))

    if candidates:
        main_folder = candidates[-1]
        main_folder_name = os.path.basename(main_folder)
        base_name = main_folder_name.rsplit("_", 2)[0]
        sub_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        retake_folder_name = f"{base_name}_{sub_ts}"
        print(f"[DEBUG] Found main folder: {main_folder_name}")
        print(f"[DEBUG] Base name (with split): {base_name}")
        print(f"[DEBUG] Retake folder name: {retake_folder_name}")
    else:
        base_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if sample_name.startswith(f"{sample_number}_") or sample_name.startswith(f"{sample_number}-"):
            main_folder = os.path.join(run_path, f"{sample_name}_{base_ts}")
            retake_folder_name = f"{sample_name}_{base_ts}"
        else:
            main_folder = os.path.join(run_path, f"{sample_number}_{sample_name}_{base_ts}")
            retake_folder_name = f"{sample_number}_{sample_name}_{base_ts}"
        os.makedirs(main_folder, exist_ok=True)

    staging_path, use_staging = create_staging_dir("retake")
    final_output_folder = os.path.join(main_folder, retake_folder_name)
    temp_output_folder = os.path.join(staging_path, retake_folder_name)
    os.makedirs(temp_output_folder, exist_ok=True)

    print(f"[INFO] Generating label_auto_000.jpg for retake folder")
    label_path = os.path.join(temp_output_folder, "label_auto_000.jpg")
    create_label_image(sample_name, label_path)

    print(f"[INFO] Retaking images for {sample_name}")
    print(f"[INFO] Staging: {temp_output_folder}")
    print(f"[INFO] Final destination: {final_output_folder}")
    ENA.off()

    current = {"x": 0, "y": 0, "z": 0}
    image_idx = 1

    try:
        for pt in capture_points:
            dx = pt["x"] - current["x"]
            dy = pt["y"] - current["y"]
            dz = pt["z"] - current["z"]

            move_to(dx, dy, dz)
            current = pt.copy()

            if image_idx == 1:
                filename = f"label_r_{str(image_idx).zfill(3)}.jpg"
            else:
                filename = f"image_r_{str(image_idx).zfill(3)}.jpg"
            if capture_image(temp_output_folder, filename):
                print(f"[*] Captured {filename}")
            else:
                print(f"[x] Failed to capture {filename}")
            image_idx += 1

        final_pos = manual_data.get("final_position", {"x": 0, "y": 0, "z": 0})
        dx = final_pos["x"] - current["x"]
        dy = final_pos["y"] - current["y"]
        dz = final_pos["z"] - current["z"]
        print("[INFO] Returning to origin...")
        move_to(dx, dy, dz)

        print(f"[INFO] Syncing retake images to network drive...")
        if sync_to_network(staging_path, main_folder, cleanup_staging=True):
            print(f"[SUCCESS] Retake images saved to: {final_output_folder}")
        else:
            print(f"[ERROR] Failed to sync to network. Images remain in: {staging_path}")

    except Exception as e:
        print(f"[ERROR] Retake operation failed: {e}")
        print(f"[INFO] Images may remain in staging: {staging_path}")
    finally:
        ENA.on()
        print("[DONE] Retake finished.")

if __name__ == "__main__":
    main()
