


import sys
import time
import os
from datetime import datetime
from gpiozero import DigitalOutputDevice
import subprocess
import json
from PIL import Image, ImageDraw, ImageFont
import traceback
import shutil


POSITION_FILE = "/home/ecdysis/shimsy/controller/last_position.json"
delay = 0.0005

CONFIG_PATH = "/home/ecdysis/shimsy/controller/scan_config.json"

RUN_COUNTER_PATH = "/home/ecdysis/shimsy/controller/scan_run_counter.json"


STAGING_ROOT = "/mnt/shimsy_tmp"
FINAL_ROOT   = "/home/ecdysis/shimsy_scans"

def get_next_run_paths():
    if not os.path.exists(RUN_COUNTER_PATH):
        counter = 1
    else:
        with open(RUN_COUNTER_PATH) as f:
            counter = json.load(f).get("run", 0) + 1

    with open(RUN_COUNTER_PATH, "w") as f:
        json.dump({"run": counter}, f)

    run_folder = f"run_{counter:03d}"
    local_run_path = os.path.join(STAGING_ROOT, run_folder)
    final_run_path = os.path.join(FINAL_ROOT, run_folder)
    os.makedirs(local_run_path, exist_ok=True)
    return local_run_path, final_run_path, run_folder



with open(CONFIG_PATH) as f:
    config = json.load(f)

local_run_path, run_path, run_folder = get_next_run_paths()

sample_names = config.get("samples", [])
print(f"[DEBUG] Raw sample_names from config: {sample_names}")
print(f"[DEBUG] Type of sample_names: {type(sample_names)}")
print(f"[DEBUG] Length of sample_names: {len(sample_names)}")
print(f"[DEBUG] First few samples: {sample_names[:3] if len(sample_names) >= 3 else sample_names}")

sample_folder_map = {}
sample_occurrence_count = {}
sample_first_occurrence = {}
base_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")



print(f"[DEBUG] Starting first pass with {len(sample_names)} samples")
for dish_idx, sample in enumerate(sample_names, 1):
    print(f"[DEBUG] Processing dish {dish_idx}: {sample}")
    if sample.startswith(f"{dish_idx}_") or sample.startswith(f"{dish_idx}-"):
        sample_key = sample.split("_", 1)[1] if "_" in sample else sample.split("-", 1)[1]
    else:
        sample_key = sample
    print(f"[DEBUG] Sample key: {sample_key}")
    sample_occurrence_count[sample_key] = sample_occurrence_count.get(sample_key, 0) + 1
    print(f"[DEBUG] Occurrence count for {sample_key}: {sample_occurrence_count[sample_key]}")

    if sample_key not in sample_first_occurrence:
        sample_first_occurrence[sample_key] = dish_idx
        print(f"[DEBUG] First occurrence of {sample_key}: dish {dish_idx}")
    else:
        print(f"[DEBUG] First occurrence of {sample_key}: dish {sample_first_occurrence[sample_key]}")

print(f"[DEBUG] Final occurrence counts: {sample_occurrence_count}")
print(f"[DEBUG] First occurrences: {sample_first_occurrence}")


print(f"[DEBUG] Starting second pass for folder creation")
for dish_idx, sample in enumerate(sample_names, 1):
    print(f"[DEBUG] Creating folder for dish {dish_idx}: {sample}")
    if sample.startswith(f"{dish_idx}_") or sample.startswith(f"{dish_idx}-"):
        sample_key = sample.split("_", 1)[1] if "_" in sample else sample.split("-", 1)[1]
    else:
        sample_key = sample

    print(f"[DEBUG] Sample key: {sample_key}")
    print(f"[DEBUG] Total occurrences: {sample_occurrence_count[sample_key]}")

    if sample.startswith(f"{dish_idx}_") or sample.startswith(f"{dish_idx}-"):
        base_folder_name = f"{sample}_{base_timestamp}"
    else:
        base_folder_name = f"{dish_idx}_{sample}_{base_timestamp}"

    print(f"[DEBUG] Base folder name: {base_folder_name}")

    if sample_occurrence_count[sample_key] > 1:
        current_occurrence = 0
        for i in range(dish_idx):
            if i < len(sample_names):
                check_sample = sample_names[i]
                if check_sample.startswith(f"{i+1}_") or check_sample.startswith(f"{i+1}-"):
                    check_key = check_sample.split("_", 1)[1] if "_" in check_sample else check_sample.split("-", 1)[1]
                else:
                    check_key = check_sample
                if check_key == sample_key:
                    current_occurrence += 1
                    if i + 1 == dish_idx:
                        break
        split_number = current_occurrence
        print(f"[DEBUG] Split number: {split_number}")
        if sample.startswith(f"{dish_idx}_") or sample.startswith(f"{dish_idx}-"):
            parts = base_folder_name.split("_")
            print(f"[DEBUG] Parts before split: {parts}")
            if len(parts) >= 4:
                timestamp_parts = parts[-2:]
                sample_parts = parts[:-2]
                sample_parts.append(f"split_{split_number}")
                sample_parts.extend(timestamp_parts)
                folder_name = "_".join(sample_parts)
                print(f"[DEBUG] Parts after split: {sample_parts}")
            else:
                folder_name = f"{base_folder_name}_split_{split_number}"
        else:
            parts = base_folder_name.split("_")
            print(f"[DEBUG] Parts before split: {parts}")
            if len(parts) >= 4:
                timestamp_parts = parts[-2:]
                sample_parts = parts[:-2]
                sample_parts.append(f"split_{split_number}")
                sample_parts.extend(timestamp_parts)
                folder_name = "_".join(sample_parts)
                print(f"[DEBUG] Parts after split: {sample_parts}")
            else:
                folder_name = f"{base_folder_name}_split_{split_number}"
    else:
        print(f"[DEBUG] Single occurrence, no split postfix")
        folder_name = base_folder_name

    print(f"[DEBUG] Final folder name: {folder_name}")

    main_folder = os.path.join(local_run_path, folder_name)
    os.makedirs(main_folder, exist_ok=True)
    if sample_key not in sample_folder_map:
        sample_folder_map[sample_key] = []
    sample_folder_map[sample_key].append(main_folder)
    folder = main_folder
    if sample_occurrence_count[sample_key] > 1:
        print(f"[INFO] Duplicate sample '{sample_key}' created with split_{split_number}: {main_folder}")
    else:
        print(f"[INFO] Sample '{sample_key}' created: {main_folder}")



def save_position(x, y, z):
    with open(POSITION_FILE, "w") as f:
        json.dump({"x": x, "y": y, "z": z}, f)



STEP_X = DigitalOutputDevice(17)
DIR_X = DigitalOutputDevice(27)
STEP_Y = DigitalOutputDevice(22)
DIR_Y = DigitalOutputDevice(23)
STEP_Z = DigitalOutputDevice(24)
DIR_Z  = DigitalOutputDevice(25)

ENA    = DigitalOutputDevice(5)


TEMPLATE_FLAG_PATH = "/home/ecdysis/shimsy/controller/template_flag.json"
try:
    with open(TEMPLATE_FLAG_PATH) as f:
        template_config = json.load(f)
        template = template_config.get("template", "default").lower()
except Exception:
    template = "default"

if template == "custom":
    MANUAL_PATH_JSON = "/home/ecdysis/shimsy/custom_path.json"
else:
    MANUAL_PATH_JSON = "/home/ecdysis/shimsy/manual_path.json"

with open(MANUAL_PATH_JSON) as f:
    path_data = json.load(f)


capture_points = path_data["capture_points"]
final_pos = path_data.get("final_position", {"x": 0, "y": 0, "z": 0})


def move_steps(dir_pin, step_pin, steps, direction=True):
    dir_pin.value = direction
    for _ in range(steps):
        step_pin.on()
        time.sleep(delay)
        step_pin.off()
        time.sleep(delay)

def copy_label_to_duplicates(sample_name, first_occurrence_folder, all_folders):
    """Copy the label from first occurrence to all duplicate folders"""
    print(f"[DEBUG] copy_label_to_duplicates called for sample: {sample_name}")
    print(f"[DEBUG] First occurrence folder: {first_occurrence_folder}")
    print(f"[DEBUG] All folders: {all_folders}")
    if len(all_folders) <= 1:
        print(f"[DEBUG] No duplicates to copy to (only {len(all_folders)} folder(s))")
        return
    first_label_path = os.path.join(first_occurrence_folder, "label_r_001.jpg")
    print(f"[DEBUG] Looking for first label at: {first_label_path}")
    print(f"[DEBUG] First label exists: {os.path.exists(first_label_path)}")
    if not os.path.exists(first_label_path):
        print(f"[WARNING] First occurrence label not found: {first_label_path}")
        return
    print(f"[INFO] Copying label from first occurrence to {len(all_folders) - 1} duplicate folders")
    for i, folder in enumerate(all_folders[1:], 1):
        duplicate_label_path = os.path.join(folder, "label_r_001.jpg")
        print(f"[DEBUG] Copying to duplicate {i}: {duplicate_label_path}")
        try:
            shutil.copy2(first_label_path, duplicate_label_path)
            print(f"[INFO] Copied label to: {duplicate_label_path}")
        except Exception as e:
            print(f"[ERROR] Failed to copy label to {duplicate_label_path}: {e}")

def trigger_autofocus_with_retry(max_attempts=3, initial_delay=2):
    """Trigger autofocus with retry logic to handle I/O in progress errors"""
    for attempt in range(max_attempts):
        try:
            if attempt > 0:
                time.sleep(initial_delay * (attempt + 1))
            result = subprocess.run(
                ["gphoto2", "--set-config", "autofocusdrive=1"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            return True
        except subprocess.CalledProcessError as e:
            if attempt < max_attempts - 1:
                delay = initial_delay * (attempt + 2)
                print(f"[WARNING] Autofocus attempt {attempt + 1} failed (I/O in progress). Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                print(f"[WARNING] Autofocus failed after {max_attempts} attempts. Continuing without autofocus...")
                return False
        except subprocess.TimeoutExpired:
            if attempt < max_attempts - 1:
                print(f"[WARNING] Autofocus timed out. Retrying...")
                time.sleep(initial_delay * (attempt + 2))
            else:
                print(f"[WARNING] Autofocus timed out after {max_attempts} attempts. Continuing...")
                return False
        except Exception as e:
            print(f"[WARNING] Autofocus error: {e}. Continuing...")
            return False
    return False

def create_label_image(sample_name, path, width=800, height=600):
    print(f"[DEBUG] Generating label for sample_name = '{sample_name}'")

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



try:
    print("[INFO] Scan started")
    ENA.off()
    save_position(0, 0, 0)

    scanned_folders = []

    for sample_name, folder_list in sample_folder_map.items():
        if len(folder_list) > 0:
            for folder in folder_list:
                print(f"[INFO] Creating label_auto_000.jpg for folder: {folder}")
                label_path = os.path.join(folder, "label_auto_000.jpg")
                create_label_image(sample_name, label_path)
                scanned_folders.append(folder)
            copy_label_to_duplicates(sample_name, folder_list[0], folder_list)




    current_pos = {"x": 0, "y": 0, "z": 0}
    sample_image_counters = {}
    dish_image_counters = {}

    sample_folder_assignments = {}
    for sample_num in range(1, 7):
        sample_idx = sample_num - 1
        sample_name = sample_names[sample_idx]
        if "_" in sample_name:
            sample_key = sample_name.split("_", 1)[1]
        else:
            sample_key = sample_name

        folder_list = sample_folder_map.get(sample_key, [])
        if folder_list:
            folder = folder_list.pop(0) if folder_list else None
            if folder:
                sample_folder_assignments[sample_num] = {
                    'folder': folder,
                    'sample_key': sample_key,
                    'is_duplicate': sample_first_occurrence.get(sample_key, 0) != sample_num
                }
                print(f"[DEBUG] Sample {sample_num} ({sample_key}): {folder} (duplicate: {sample_first_occurrence.get(sample_key, 0) != sample_num})")

    for sample_num in range(1, 7):
        if sample_num in sample_folder_assignments:
            sample_key = sample_folder_assignments[sample_num]['sample_key']
            if sample_key not in sample_image_counters:
                sample_image_counters[sample_key] = 0
            dish_key = f"{sample_key}_dish_{sample_num}"
            if dish_key not in dish_image_counters:
                dish_image_counters[dish_key] = 0

    print("[DEBUG] Starting first pass: Label capture for all samples")
    for idx, point in enumerate(capture_points):
        if point["z"] != 8650:
            continue
        sample_num = int(point["sample"])
        if sample_num not in sample_folder_assignments:
            print(f"[ERROR] No folder assignment for sample {sample_num}")
            continue
        assignment = sample_folder_assignments[sample_num]
        sample_key = assignment['sample_key']
        folder = assignment['folder']
        is_duplicate = assignment['is_duplicate']
        dx = point["x"] - current_pos["x"]
        dy = point["y"] - current_pos["y"]
        dz = point["z"] - current_pos["z"]
        print(f"[MOVE] Sample {sample_num} Label: ?x={dx}, ?y={dy}, ?z={dz}")

        if dx != 0:
            move_steps(DIR_X, STEP_X, abs(dx), direction=(dx > 0))
        if dy != 0:
            move_steps(DIR_Y, STEP_Y, abs(dy), direction=(dy > 0))
        if dz != 0:
            move_steps(DIR_Z, STEP_Z, abs(dz), direction=(dz > 0))
        current_pos = {"x": point["x"], "y": point["y"], "z": point["z"]}
        save_position(current_pos["x"], current_pos["y"], current_pos["z"])

        dish_key = f"{sample_key}_dish_{sample_num}"
        is_first_image = dish_image_counters[dish_key] == 0
        dish_image_counters[dish_key] += 1
        sample_image_counters[sample_key] += 1
        print(f"[DEBUG] Sample: {sample_key}, Dish: {sample_num}, Label capture")
        print(f"[DEBUG] Is first image: {is_first_image}, Is duplicate: {is_duplicate}")
        if is_first_image and not is_duplicate:
            filename = os.path.join(folder, f"label_r_{dish_image_counters[dish_key]:03d}.jpg")
            print(f"[DEBUG] Will capture label: {filename}")
            action = "CAPTURE LABEL"
        elif is_first_image and is_duplicate:
            print(f"[SKIP] Skipping label capture for duplicate dish {sample_num} of sample '{sample_key}'")
            print(f"[INFO] Label will be copied from first occurrence (dish {sample_first_occurrence[sample_key]})")
            filename = os.path.join(folder, f"label_r_{dish_image_counters[dish_key]:03d}.jpg")
            print(f"[DEBUG] Would capture label: {filename} (SKIPPED)")
            action = "SKIP LABEL CAPTURE"
        else:
            filename = os.path.join(folder, f"label_r_{dish_image_counters[dish_key]:03d}.jpg")
            action = "CAPTURE LABEL"
        print(f"[CAPTURE] {filename}")
        if is_first_image and is_duplicate:
            print(f"[SKIP] Skipping gphoto2 capture for duplicate dish label")
            time.sleep(0.5)
        else:
            autofocus_success = trigger_autofocus_with_retry(max_attempts=3, initial_delay=0.5)
            if autofocus_success:
                time.sleep(1.5)
            else:
                time.sleep(0.8)

            for attempt in range(3):
                try:
                    subprocess.run([
                        "gphoto2", "--capture-image-and-download",
                        "--filename", filename, "--force-overwrite"
                    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except subprocess.CalledProcessError:
                    if attempt < 2:
                        delay_seconds = 0.5 * (attempt + 1)
                        print(f"[WARNING] Capture attempt {attempt + 1} failed for {filename}. Retrying in {delay_seconds:.1f}s...")
                        time.sleep(delay_seconds)
                    else:
                        print(f"[ERROR] Capture failed after 3 attempts for {filename}. Skipping.")

        time.sleep(0.5)

    print("[DEBUG] Starting second pass: Dish image capture for all samples")
    for idx, point in enumerate(capture_points):
        if point["z"] != 0:
            continue
        sample_num = int(point["sample"])
        if sample_num not in sample_folder_assignments:
            print(f"[ERROR] No folder assignment for sample {sample_num}")
            continue
        assignment = sample_folder_assignments[sample_num]
        sample_key = assignment['sample_key']
        folder = assignment['folder']
        dx = point["x"] - current_pos["x"]
        dy = point["y"] - current_pos["y"]
        dz = point["z"] - current_pos["z"]
        print(f"[MOVE] Sample {sample_num} Dish: ?x={dx}, ?y={dy}, ?z={dz}")

        if dx != 0:
            move_steps(DIR_X, STEP_X, abs(dx), direction=(dx > 0))
        if dy != 0:
            move_steps(DIR_Y, STEP_Y, abs(dy), direction=(dy > 0))
        if dz != 0:
            move_steps(DIR_Z, STEP_Z, abs(dz), direction=(dz > 0))
        current_pos = {"x": point["x"], "y": point["y"], "z": point["z"]}
        save_position(current_pos["x"], current_pos["y"], current_pos["z"])

        dish_key = f"{sample_key}_dish_{sample_num}"
        dish_image_counters[dish_key] += 1
        sample_image_counters[sample_key] += 1
        print(f"[DEBUG] Sample: {sample_key}, Dish: {sample_num}, Dish image capture")
        print(f"[DEBUG] Dish counter: {dish_image_counters[dish_key]}")
        filename = os.path.join(folder, f"image_r_{dish_image_counters[dish_key]:03d}.jpg")
        print(f"[DEBUG] Will capture dish image: {filename}")
        print(f"[CAPTURE] {filename}")
        autofocus_success = trigger_autofocus_with_retry(max_attempts=3, initial_delay=0.5)
        if autofocus_success:
            time.sleep(1.5)
        else:
            time.sleep(0.8)

        for attempt in range(3):
            try:
                subprocess.run([
                    "gphoto2", "--capture-image-and-download",
                    "--filename", filename, "--force-overwrite"
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                break
            except subprocess.CalledProcessError:
                if attempt < 2:
                    delay_seconds = 0.5 * (attempt + 1)
                    print(f"[WARNING] Capture attempt {attempt + 1} failed for {filename}. Retrying in {delay_seconds:.1f}s...")
                    time.sleep(delay_seconds)
                else:
                    print(f"[ERROR] Capture failed after 3 attempts for {filename}. Skipping.")

        time.sleep(0.5)

    print("[DEBUG] Starting label copying for duplicate samples")
    for sample_num in range(1, 7):
        if sample_num not in sample_folder_assignments:
            continue
        assignment = sample_folder_assignments[sample_num]
        sample_key = assignment['sample_key']
        folder = assignment['folder']
        is_duplicate = assignment['is_duplicate']
        if is_duplicate:
            first_occurrence_dish = sample_first_occurrence.get(sample_key, 0)
            if first_occurrence_dish > 0 and first_occurrence_dish in sample_folder_assignments:
                first_occurrence_folder = sample_folder_assignments[first_occurrence_dish]['folder']
                source_label = os.path.join(first_occurrence_folder, "label_r_001.jpg")
                dest_label = os.path.join(folder, "label_r_001.jpg")
                print(f"[COPY] Copying label from {source_label} to {dest_label}")
                try:
                    import shutil
                    shutil.copy2(source_label, dest_label)
                    print(f"[SUCCESS] Label copied successfully for sample {sample_num}")
                except Exception as e:
                    print(f"[ERROR] Failed to copy label for sample {sample_num}: {e}")
            else:
                print(f"[ERROR] Could not find first occurrence folder for sample {sample_num}")

    print("[INFO] Moving to final position...")
    dx = final_pos["x"] - current_pos["x"]
    dy = final_pos["y"] - current_pos["y"]
    dz = final_pos["z"] - current_pos["z"]
    if dx != 0:
        move_steps(DIR_X, STEP_X, abs(dx), direction=(dx > 0))
    if dy != 0:
        move_steps(DIR_Y, STEP_Y, abs(dy), direction=(dy > 0))
    if dz != 0:
        move_steps(DIR_Z, STEP_Z, abs(dz), direction=(dz > 0))
    current_pos = final_pos
    save_position(current_pos["x"], current_pos["y"], current_pos["z"])

    print("\n[INFO] Returning to origin position...")
    if current_pos["x"] != 0:
        move_steps(DIR_X, STEP_X, abs(current_pos["x"]), direction=(current_pos["x"] < 0))
    if current_pos["y"] != 0:
        move_steps(DIR_Y, STEP_Y, abs(current_pos["y"]), direction=(current_pos["y"] < 0))
    if current_pos["z"] != 0:
        move_steps(DIR_Z, STEP_Z, abs(current_pos["z"]), direction=(current_pos["z"] < 0))
    print("[INFO] Copying labels to duplicate folders...")
    print(f"[DEBUG] sample_folder_map: {sample_folder_map}")
    for sample_name, folder_list in sample_folder_map.items():
        print(f"[DEBUG] Processing sample: {sample_name}, folders: {folder_list}")
        if len(folder_list) > 1:
            print(f"[DEBUG] Sample {sample_name} has {len(folder_list)} folders, calling copy_label_to_duplicates")
            copy_label_to_duplicates(sample_name, folder_list[0], folder_list)
        else:
            print(f"[DEBUG] Sample {sample_name} has only {len(folder_list)} folder(s), skipping copy")
    print(f"[INFO] Starting sync from RAM ({local_run_path}) to network drive ({run_path})...")
    try:
        os.makedirs(run_path, exist_ok=True)
        rsync_cmd = [
            "rsync", "-av", "--progress", "--checksum",
            local_run_path + "/", run_path + "/"
        ]
        print(f"[INFO] Running: {' '.join(rsync_cmd)}")
        result = subprocess.run(rsync_cmd, check=True, capture_output=True, text=True)
        local_files = sum(len(files) for _, _, files in os.walk(local_run_path))
        network_files = sum(len(files) for _, _, files in os.walk(run_path))
        if local_files != network_files:
            raise Exception(f"File count mismatch: local={local_files}, network={network_files}")
        print(f"[INFO] Successfully synced {local_files} files to network drive")
        with open(os.path.join(FINAL_ROOT, "LAST_SCAN.txt"), "w") as f:
            f.write(f"{run_path}\n")
        print("[INFO] Updated LAST_SCAN.txt")

        try:
            shutil.rmtree(local_run_path)
            print(f"[INFO] Cleaned temp folder: {local_run_path}")
            try:
                result = subprocess.run(["df", "-h", STAGING_ROOT], capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"[INFO] TMPFS space after cleanup:\n{result.stdout.strip()}")
            except Exception:
                pass
        except Exception as cleanup_err:
            print(f"[WARNING] Could not remove temp folder {local_run_path}: {cleanup_err}")

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] rsync failed with exit code {e.returncode}")
        print(f"[ERROR] stdout: {e.stdout}")
        print(f"[ERROR] stderr: {e.stderr}")
        print(f"[ERROR] Files remain in temporary storage: {local_run_path}")
    except Exception as e:
        print(f"[ERROR] Sync operation failed: {e}")
        print(f"[ERROR] Files remain in temporary storage: {local_run_path}")


    print("[SUCCESS] All samples scanned successfully.")
    print(f"[INFO] Final position reached. Returned to origin successfully.")

except Exception as e:
    traceback.print_exc()
    print(f"[ERROR] {e}", file=sys.stderr)

finally:
    ENA.on()
    print("[INFO] Motors disabled")
