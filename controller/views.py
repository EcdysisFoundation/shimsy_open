from .models import ScanSettings, ScanConfiguration, ScanRecord, UnstitchedRun, RescanRequest
from .utils import convert_sample_type_abbrev_to_full

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import zipfile
import shutil
import json
import subprocess
from django.utils.encoding import smart_str
from datetime import datetime

import csv
import os
from django.http import HttpResponse, FileResponse
from django.conf import settings
from django.http import Http404
import time
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import requests
from pathlib import Path
import tempfile
from PIL import Image
from django.utils import timezone

def create_or_update_unstitched_run(run_folder, run_path, total_subfolders):
    
    try:
        unstitched_run, created = UnstitchedRun.objects.get_or_create(
            run_folder=run_folder,
            defaults={
                'run_path': run_path,
                'total_subfolders': total_subfolders,
                'stitched_subfolders': 0,
                'is_complete': False
            }
        )
        if not created:
            unstitched_run.run_path = run_path
            unstitched_run.total_subfolders = total_subfolders
            unstitched_run.last_updated = timezone.now()
            unstitched_run.save()
        return unstitched_run
    except Exception as e:
        print(f"[ERROR] Failed to create/update unstitched run record: {e}")
        return None

def update_stitching_progress(run_folder, stitched_folder_name):
    
    try:
        unstitched_run = UnstitchedRun.objects.get(run_folder=run_folder)
        stitched_folders = unstitched_run.get_stitched_folders()
        if stitched_folder_name not in stitched_folders:
            stitched_folders.append(stitched_folder_name)
            import json
            unstitched_run.stitched_folder_names = json.dumps(stitched_folders)
            unstitched_run.stitched_subfolders = len(stitched_folders)
            unstitched_run.is_complete = unstitched_run.stitched_subfolders >= 6
            unstitched_run.last_updated = timezone.now()
            unstitched_run.save()
            print(f"[DEBUG] Updated stitching progress for {run_folder}: {len(stitched_folders)}/{unstitched_run.total_subfolders} folders stitched")
            print(f"[DEBUG] Run completion status: {unstitched_run.is_complete} (6+ folders = complete)")
        return unstitched_run
    except UnstitchedRun.DoesNotExist:
        print(f"[WARNING] UnstitchedRun record not found for {run_folder}")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to update stitching progress: {e}")
        return None

def control_page(request):
    return render(request, "controller/control.html")

def home(request):
    return render(request, 'controller/home.html')

active_process = None

RETURN_HOME_SCRIPT = "/home/ecdysis/shimmsy/shimsy/controller/scripts/return_home.py"

@csrf_exempt
def stop_scan(request):
    global active_process
    if active_process and active_process.poll() is None:
        active_process.terminate()
        time.sleep(1)

        subprocess.run(["python3", RETURN_HOME_SCRIPT])

        return JsonResponse({'status': 'success', 'message': 'Scan stopped and returned to origin'})
    return JsonResponse({'status': 'error', 'message': 'No running scan'})

@csrf_exempt
def return_home(request):
    try:
        command = ['python3', '/home/ecdysis/shimmsy/shimsy/controller/scripts/return_home.py']
        proc = subprocess.run(command, capture_output=True, text=True)
        return JsonResponse({
            'status': 'success' if proc.returncode == 0 else 'error',
            'stdout': proc.stdout,
            'stderr': proc.stderr
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@csrf_exempt
def run_full_scan(request):
    global active_process
    if request.method == "POST":
        try:
            payload = json.loads(request.body)
            samples = payload.get("samples", [])
            if not isinstance(samples, list):
                return JsonResponse({'status': 'error', 'message': 'Expected a list of samples'}, status=400)

            sample_map = {str(i + 1): s for i, s in enumerate(samples)}

            scan_config_path = "/home/ecdysis/shimmsy/shimsy/controller/scan_config.json"
            sample_names_ordered = [
                sample_map.get(str(i), f"UnknownSample{i}") if sample_map.get(str(i), "").strip() not in ["", "--"] else f"UnknownSample{i}"
                for i in range(1, 7)
            ]

            with open(scan_config_path, "w") as f:
                json.dump({"samples": sample_names_ordered}, f, indent=4)

            template = payload.get("template", "default").lower()
            template_flag_path = "/home/ecdysis/shimmsy/shimsy/controller/template_flag.json"
            with open(template_flag_path, "w") as f:
                json.dump({"template": template}, f)

            command = ['python3', '/home/ecdysis/shimmsy/shimsy/controller/scripts/run_scan.py']
            active_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = active_process.communicate()
            success = active_process.returncode == 0

            RUN_COUNTER_PATH = "/home/ecdysis/shimmsy/shimsy/controller/scan_run_counter.json"
            try:
                with open(RUN_COUNTER_PATH) as f:
                    run_number = json.load(f).get("run", 1)
            except Exception:
                run_number = 1

            if success:
                print(f"[DEBUG] Scan successful, creating records for run {run_number}")
                rescan_request_keys = set(
                    (req.site_number, req.sample_type, req.transect)
                    for req in RescanRequest.objects.all()
                )
                sample_occurrence_count = {}
                for sample in sample_names_ordered:
                    if "_" in sample:
                        sample_key = sample.split("_", 1)[1]
                    else:
                        sample_key = sample
                    sample_occurrence_count[sample_key] = sample_occurrence_count.get(sample_key, 0) + 1
                print(f"[DEBUG] Sample occurrence counts: {sample_occurrence_count}")
                for sample in sample_names_ordered:
                    print(f"[DEBUG] Processing sample: {sample}")
                    core = sample.split("_", 1)[1] if "_" in sample else sample
                    parts = core.split("-")
                    print(f"[DEBUG] Sample parts: {parts}")

                    if len(parts) == 4:
                        site, _year, sample_type, transect = parts
                    elif len(parts) == 3:
                        site, sample_type, transect = parts
                    else:
                        print(f"[DEBUG] Malformed sample name '{sample}', skipping")
                        continue

                    site = site[:4]
                    sample_type_full = convert_sample_type_abbrev_to_full(sample_type)
                    is_stitcher_retake = (site, sample_type_full, transect) in rescan_request_keys

                    name = payload.get("name", "Unknown")
                    name2 = payload.get("name2", "")
                    is_splitted = sample_occurrence_count.get(core, 1) > 1
                    print(f"[DEBUG] Creating record: name={name}, site={site}, type={sample_type}, transect={transect}, run={run_number}, is_splitted={is_splitted}, stitcher_retake={is_stitcher_retake}")
                    record = ScanRecord.objects.create(
                        name=name,
                        name2=name2,
                        site_number=site,
                        sample_type=sample_type,
                        transect=transect,
                        run_number=run_number,
                        is_splitted=is_splitted,
                        stitcher_retake=is_stitcher_retake,
                    )
                    print(f"[DEBUG] Created record ID: {record.id}")
                run_folder = f"run_{run_number:03d}"
                scans_base = getattr(settings, 'SHIMSY_SCANS_BASE', '/home/ecdysis/shimsy_scans')
                run_path = os.path.join(scans_base, run_folder)
                try:
                    total_stitchable = get_all_stitchable_folders(run_path)
                    main_subfolders = get_run_subfolders(run_path)
                    retake_count = total_stitchable - len(main_subfolders)
                    create_or_update_unstitched_run(run_folder, run_path, total_stitchable)
                    print(f"[DEBUG] Created unstitched run record for {run_folder} with {total_stitchable} stitchable folders ({len(main_subfolders)} main + {retake_count} retakes)")
                except Exception as e:
                    print(f"[ERROR] Failed to create unstitched run record: {e}")
            else:
                print("[DEBUG] Scan failed, no records created")

            if not success:
                print("[run_full_scan] Script failed")
                print("[STDOUT]\n", stdout)
                print("[STDERR]\n", stderr)

            return JsonResponse({
                'status': 'success' if success else 'error',
                'message': 'Scan finished' if success else 'Scan failed'
            })

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

def scan_history(request):
    from django.core.paginator import Paginator
    from django.db.models import Q, Count
    from django.utils import timezone
    from datetime import datetime, timedelta
    search_query = request.GET.get('search', '').strip()
    page_number = request.GET.get('page', 1)
    records = ScanRecord.objects.all()
    if search_query:
        try:
            run_number = int(search_query)
            records = records.filter(
                Q(site_number__icontains=search_query) |
                Q(run_number=run_number)
            )
        except ValueError:
            records = records.filter(site_number__icontains=search_query)
    records = records.order_by('-timestamp')
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)
    daily_stats = {
        'today': ScanRecord.objects.filter(
            timestamp__date=today
        ).values('run_number').distinct().count(),
        'yesterday': ScanRecord.objects.filter(
            timestamp__date=yesterday
        ).values('run_number').distinct().count(),
        'this_week': ScanRecord.objects.filter(
            timestamp__date__gte=week_ago
        ).values('run_number').distinct().count(),
        'total_runs': ScanRecord.objects.values('run_number').distinct().count()
    }
    paginator = Paginator(records, 50)
    try:
        page_obj = paginator.page(page_number)
    except:
        page_obj = paginator.page(1)
    context = {
        'records': page_obj,
        'search_query': search_query,
        'page_obj': page_obj,
        'paginator': paginator,
        'daily_stats': daily_stats,
        'today': today,
        'yesterday': yesterday
    }
    return render(request, "controller/history.html", context)

def unstitched_runs(request):
    
    unstitched_runs = UnstitchedRun.objects.filter(is_complete=False).order_by('-created_at')
    for run in unstitched_runs:
        try:
            import json
            stitched_folders = json.loads(run.stitched_folder_names) if run.stitched_folder_names else []
            run_path = run.run_path
            if os.path.exists(run_path):
                all_folders = [f.name for f in os.scandir(run_path) if f.is_dir()]
                remaining_folders = [folder for folder in all_folders if folder not in stitched_folders]
                run.remaining_folders = remaining_folders[:10]
            else:
                run.remaining_folders = []
        except Exception as e:
            print(f"Error processing remaining folders for {run.run_folder}: {e}")
            run.remaining_folders = []
    return render(request, "controller/unstitched_runs.html", {"unstitched_runs": unstitched_runs})

@csrf_exempt
def export_csv(request):
    if request.method == 'POST':
        from django.db.models import Count
        from collections import defaultdict
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="scan_history.csv"'

        writer = csv.writer(response)
        writer.writerow(['Timestamp', 'Name', 'Name 2', 'Site Number', 'Sample Type', 'Transect', 'Run Number', 'Shimsy-Retake', 'Stitcher-Rescan', 'Stitched', 'Splitted', 'Runs on Date'])

        runs_per_date = defaultdict(set)
        for record in ScanRecord.objects.all():
            date_str = record.timestamp.date().strftime('%Y-%m-%d')
            runs_per_date[date_str].add(record.run_number)
        runs_per_date_counts = {date: len(runs) for date, runs in runs_per_date.items()}

        for record in ScanRecord.objects.all().order_by('-timestamp'):
            date_str = record.timestamp.date().strftime('%Y-%m-%d')
            runs_on_date = runs_per_date_counts.get(date_str, 0)
            writer.writerow([
                record.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                record.name,
                record.name2 or '-',
                record.site_number,
                record.sample_type,
                record.transect,
                record.run_number,
                'Yes' if record.retake else 'No',
                'Yes' if record.stitcher_retake else 'No',
                'Yes' if record.stitched else 'No',
                'Yes' if record.is_splitted else 'No',
                runs_on_date
            ])

        return response
    return HttpResponse("Invalid request method.", status=405)

@csrf_exempt
def retake_sample(request):
    if request.method == "POST":
        try:
            body = json.loads(request.body)
            sample = body.get("sample")
            if not sample:
                return JsonResponse({"status": "error", "message": "Sample not provided"})

            subprocess.Popen(["python3", "/home/ecdysis/shimmsy/shimsy/controller/scripts/retake_sample.py", str(sample)])

            SCAN_CONFIG = "/home/ecdysis/shimmsy/shimsy/controller/scan_config.json"
            try:
                with open(SCAN_CONFIG) as f:
                    cfg = json.load(f)
                sample_idx = int(sample) - 1
                sample_name = cfg.get("samples", [])[sample_idx]
            except Exception:
                sample_name = None

            if not sample_name:
                return JsonResponse({"status": "error", "message": "Could not resolve sample name from config."}, status=400)

            sample_name_noprefix = sample_name.split("_", 1)[1] if "_" in sample_name else sample_name

            parts = sample_name_noprefix.split("-")
            site = sample_type = transect = None
            if len(parts) == 4:
                site, _year, sample_type, transect = parts
            elif len(parts) == 3:
                site, sample_type, transect = parts

            if site:
                site = site[:4]

            RUN_COUNTER_PATH = "/home/ecdysis/shimmsy/shimsy/controller/scan_run_counter.json"
            try:
                with open(RUN_COUNTER_PATH) as f:
                    run_number = json.load(f).get("run", 1)
            except Exception:
                run_number = 1

            if sample_name and site and sample_type and transect:
                print(f"[DEBUG] Looking for record to mark as retake:")
                print(f"[DEBUG] site={site}, sample_type={sample_type}, transect={transect}, run_number={run_number}")
                matching_records = ScanRecord.objects.filter(
                    site_number=site,
                    sample_type=sample_type,
                    transect=transect,
                    run_number=run_number
                ).order_by("-timestamp")
                print(f"[DEBUG] Found {matching_records.count()} matching records")
                for record in matching_records[:3]:
                    print(f"[DEBUG] Record: {record.site_number}-{record.sample_type}-{record.transect} (retake={record.retake})")
                updated_count = matching_records.update(retake=True)
                print(f"[DEBUG] Updated {updated_count} records to retake=True")
            else:
                print(f"[DEBUG] Missing required fields for retake update: sample_name={sample_name}, site={site}, sample_type={sample_type}, transect={transect}")

            return JsonResponse({"status": "success", "message": f"Retake for sample {sample} started."})

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    return JsonResponse({"status": "error", "message": "Invalid request method"})

def create_run_folder_zip(run_folder_path, output_zip_path):
    
    with ZipFile(output_zip_path, 'w', ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(run_folder_path):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp')):
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, run_folder_path)
                    zipf.write(file_path, arcname)

def get_latest_run_folder():
    
    scans_base = getattr(settings, 'SHIMSY_SCANS_BASE', '/home/ecdysis/shimsy_scans')
    if not os.path.exists(scans_base):
        print(f"[DEBUG] Scans base directory does not exist: {scans_base}")
        local_test_path = os.path.join(settings.BASE_DIR, 'test_shimsy_scans')
        if os.path.exists(local_test_path):
            print(f"[DEBUG] Using local test data: {local_test_path}")
            scans_base = local_test_path
        else:
            return None
    last_scan_file = os.path.join(scans_base, "LAST_SCAN.txt")
    if os.path.exists(last_scan_file):
        try:
            with open(last_scan_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        if not os.path.isabs(line):
                            run_path = os.path.join(scans_base, line)
                        else:
                            run_path = line
                        if os.path.isdir(run_path):
                            print(f"[DEBUG] Found run folder from LAST_SCAN.txt: {run_path}")
                            return run_path
                        else:
                            print(f"[DEBUG] Run folder from LAST_SCAN.txt does not exist: {run_path}")
        except Exception as e:
            print(f"[DEBUG] Error reading LAST_SCAN.txt: {e}")
    try:
        all_items = os.listdir(scans_base)
        run_folders = []
        for item in all_items:
            item_path = os.path.join(scans_base, item)
            if os.path.isdir(item_path) and item.startswith('run_'):
                run_folders.append(item_path)
        if run_folders:
            latest_folder = max(run_folders, key=os.path.getctime)
            print(f"[DEBUG] Found latest run folder: {latest_folder}")
            return latest_folder
        else:
            print(f"[DEBUG] No run_XXX folders found in {scans_base}")
            print(f"[DEBUG] Available items: {all_items}")
    except Exception as e:
        print(f"[DEBUG] Error scanning for run folders: {e}")
    return None

def get_run_subfolders(run_folder_path):
    
    try:
        subfolders = []
        for item in os.listdir(run_folder_path):
            item_path = os.path.join(run_folder_path, item)
            if os.path.isdir(item_path):
                subfolders.append(item_path)
        subfolders.sort(key=lambda x: os.path.basename(x))
        return subfolders
    except Exception:
        return []

def get_all_stitchable_folders(run_folder_path):
    
    try:
        main_subfolders = get_run_subfolders(run_folder_path)
        total_stitchable = len(main_subfolders)
        for main_subfolder in main_subfolders:
            try:
                for item in os.listdir(main_subfolder):
                    item_path = os.path.join(main_subfolder, item)
                    if os.path.isdir(item_path):
                        total_stitchable += 1
            except Exception:
                continue
        return total_stitchable
    except Exception:
        return 0

def parse_stitcher_zip_name(folder_name):
    
    try:
        print(f"[DEBUG] Parsing folder name: '{folder_name}'")
        parts = folder_name.split('_')
        print(f"[DEBUG] Split parts: {parts}")
        base_name = folder_name
        if len(parts) >= 5:
            if (parts[-4] == 'split' and parts[-3].isdigit() and
                len(parts[-2]) == 8 and parts[-2].isdigit() and
                len(parts[-1]) == 6 and parts[-1].isdigit()):
                base_name = '_'.join(parts[:-2])
                print(f"[DEBUG] Removed timestamp, kept split, base_name: '{base_name}'")
            elif (len(parts[-2]) == 8 and parts[-2].isdigit() and
                  len(parts[-1]) == 6 and parts[-1].isdigit()):
                base_name = '_'.join(parts[:-2])
                print(f"[DEBUG] Removed timestamp, base_name: '{base_name}'")
            else:
                print(f"[DEBUG] No valid timestamp pattern found")
        elif len(parts) >= 2:
            if (len(parts[-2]) == 8 and parts[-2].isdigit() and
                len(parts[-1]) == 6 and parts[-1].isdigit()):
                base_name = '_'.join(parts[:-2])
                print(f"[DEBUG] Removed timestamp, base_name: '{base_name}'")
            else:
                print(f"[DEBUG] No valid timestamp pattern found")
        if base_name == folder_name and '_split_' in folder_name:
            parts = folder_name.split('_')
            for i in range(len(parts) - 1):
                if parts[i] == 'split' and i + 1 < len(parts) and parts[i + 1].isdigit():
                    base_name = '_'.join(parts[:i])
                    print(f"[DEBUG] Found split in middle, base_name: '{base_name}'")
                    break
            if base_name != folder_name:
                parts = base_name.split('_')
                if len(parts) >= 1:
                    if len(parts[-1]) == 8 and parts[-1].isdigit():
                        base_name = '_'.join(parts[:-1])
                        print(f"[DEBUG] Removed date from base_name: '{base_name}'")
                    elif len(parts) >= 2 and (len(parts[-2]) == 8 and parts[-2].isdigit() and
                        len(parts[-1]) == 6 and parts[-1].isdigit()):
                        base_name = '_'.join(parts[:-2])
                        print(f"[DEBUG] Removed timestamp from base_name: '{base_name}'")
        if '_' in base_name:
            dish_part, rest = base_name.split('_', 1)
            print(f"[DEBUG] Dish part: '{dish_part}', rest: '{rest}'")
            split_postfix = ""
            if '_split_' in rest:
                parts = rest.split('_')
                for i in range(len(parts) - 1):
                    if parts[i] == 'split' and i + 1 < len(parts) and parts[i + 1].isdigit():
                        split_postfix = f"_{parts[i]}_{parts[i + 1]}"
                        rest = '_'.join(parts[:i] + parts[i + 2:])
                        print(f"[DEBUG] Found split postfix: '{split_postfix}', rest after removal: '{rest}'")
                        break
            else:
                if '_split_' in folder_name:
                    original_parts = folder_name.split('_')
                    for i in range(len(original_parts) - 1):
                        if original_parts[i] == 'split' and i + 1 < len(original_parts) and original_parts[i + 1].isdigit():
                            split_postfix = f"_{original_parts[i]}_{original_parts[i + 1]}"
                            print(f"[DEBUG] Reconstructed split postfix: '{split_postfix}'")
                            break
            if '-' in rest:
                rest_parts = rest.split('-')
                print(f"[DEBUG] Rest parts: {rest_parts}")
                if len(rest_parts) >= 4:
                    site = rest_parts[0]
                    sample_type = rest_parts[2]
                    transect = rest_parts[3]
                    if sample_type == "VegetationSweep":
                        sample_type = "sw"
                    elif sample_type == "Quadrat":
                        sample_type = "qu"
                    result = f"{site}_{sample_type}_{transect}{split_postfix}"
                    print(f"[DEBUG] Parsed result: '{result}'")
                    return result
                elif len(rest_parts) == 3:
                    site, sample_type, transect = rest_parts
                    if sample_type == "VegetationSweep":
                        sample_type = "sw"
                    elif sample_type == "Quadrat":
                        sample_type = "qu"
                    result = f"{site}_{sample_type}_{transect}{split_postfix}"
                    print(f"[DEBUG] Legacy format result: '{result}'")
                    return result
        print(f"[DEBUG] Could not parse folder name '{folder_name}' for stitcher ZIP naming")
        return folder_name
    except Exception as e:
        print(f"[DEBUG] Error parsing folder name '{folder_name}': {e}")
        return folder_name

def apply_image_rotations(folder_path, rotation_data):
    
    if not rotation_data:
        print("[DEBUG] No rotation data provided, using original folder")
        return folder_path
    print(f"[DEBUG] Applying rotations to images in: {folder_path}")
    print(f"[DEBUG] Rotation data keys: {list(rotation_data.keys())}")
    print(f"[DEBUG] Rotation data values: {list(rotation_data.values())}")
    temp_dir = tempfile.mkdtemp()
    print(f"[DEBUG] Created temporary directory: {temp_dir}")
    try:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp')):
                    original_path = os.path.join(root, file)
                    relative_path = os.path.relpath(original_path, folder_path)
                    print(f"[DEBUG] Processing image: {file}")
                    print(f"[DEBUG] Original path: {original_path}")
                    print(f"[DEBUG] Relative path: {relative_path}")
                    rotation = 0
                    for rotation_path, rotation_degrees in rotation_data.items():
                        if rotation_path == original_path:
                            rotation = rotation_degrees
                            print(f"[DEBUG] Found rotation {rotation} for image (exact path): {file}")
                            break
                        elif rotation_path.endswith(file):
                            rotation = rotation_degrees
                            print(f"[DEBUG] Found rotation {rotation} for image (filename match): {file}")
                            break
                        elif relative_path in rotation_path or rotation_path.endswith(relative_path):
                            rotation = rotation_degrees
                            print(f"[DEBUG] Found rotation {rotation} for image (relative path): {file}")
                            break
                        elif file in rotation_path:
                            rotation = rotation_degrees
                            print(f"[DEBUG] Found rotation {rotation} for image (filename in path): {file}")
                            break
                    output_path = os.path.join(temp_dir, relative_path)
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    if rotation and rotation % 360 != 0:
                        print(f"[DEBUG] Applying {rotation} degrees rotation to: {file}")
                        try:
                            with Image.open(original_path) as img:
                                pil_rotation = -rotation
                                rotated_img = img.rotate(pil_rotation, expand=True)
                                if img.format == 'JPEG':
                                    rotated_img.save(output_path, 'JPEG', quality=95)
                                else:
                                    rotated_img.save(output_path, img.format or 'PNG')
                                print(f"[DEBUG] Successfully rotated and saved: {file}")
                        except Exception as e:
                            print(f"[ERROR] Failed to rotate image {file}: {e}")
                            shutil.copy2(original_path, output_path)
                    else:
                        shutil.copy2(original_path, output_path)
                        print(f"[DEBUG] Copied without rotation: {file}")
        print(f"[DEBUG] Image rotation processing complete, temp folder: {temp_dir}")
        return temp_dir
    except Exception as e:
        print(f"[ERROR] Failed during image rotation processing: {e}")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return folder_path

def upload_to_stitcher(zip_file_path, confidence_threshold=0.6, zip_filename=None):
    
    api_url = f"{settings.STITCHER_URL}/upload-zip-images/"
    print(f"[DEBUG] Uploading to: {api_url}")
    print(f"[DEBUG] ZIP file: {zip_file_path}")
    print(f"[DEBUG] ZIP filename: {zip_filename}")
    try:
        with open(zip_file_path, 'rb') as zip_file:
            filename = zip_filename or 'run_images.zip'
            files = {'file': (filename, zip_file, 'application/zip')}
            data = {'confidence_threshold': confidence_threshold}
            print(f"[DEBUG] Making request with confidence_threshold: {confidence_threshold}")
            response = requests.post(api_url, files=files, data=data, timeout=300)
            print(f"[DEBUG] Response status: {response.status_code}")
            print(f"[DEBUG] Response text: {response.text[:500]}")
            if response.status_code == 200:
                return {'success': True, 'data': response.json()}
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                print(f"[ERROR] Stitcher API error: {error_msg}")
                return {'success': False, 'error': error_msg}
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Connection error: Cannot connect to stitcher service at {api_url}. Check if the service is running."
        print(f"[ERROR] Connection error: {error_msg}")
        return {'success': False, 'error': error_msg}
    except requests.exceptions.Timeout as e:
        error_msg = f"Timeout error: Stitcher service took too long to respond (timeout: 300s)"
        print(f"[ERROR] Timeout error: {error_msg}")
        return {'success': False, 'error': error_msg}
    except requests.exceptions.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        print(f"[ERROR] Request exception: {error_msg}")
        return {'success': False, 'error': error_msg}
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"[ERROR] Unexpected error: {error_msg}")
        return {'success': False, 'error': error_msg}

@csrf_exempt
def upload_latest_run_to_stitcher(request):
    
    print(f"[DEBUG] upload_latest_run_to_stitcher called with method: {request.method}")
    if request.method == 'POST':
        try:
            print(f"[DEBUG] Request body: {request.body}")
            body = json.loads(request.body)
            print(f"[DEBUG] Parsed body: {body}")
            confidence_threshold = float(body.get('confidence_threshold', 0.6))
            subfolder_index = body.get('subfolder_index', 'all')
            requested_run = body.get('run_folder')
            nested_index = body.get('nested_index', -1)
            image_rotations = body.get('image_rotations', {})
            print(f"[DEBUG] Extracted parameters:")
            print(f"  - confidence_threshold: {confidence_threshold}")
            print(f"  - subfolder_index: {subfolder_index}")
            print(f"  - requested_run: {requested_run}")
            print(f"  - nested_index: {nested_index}")
            print(f"  - image_rotations: {image_rotations}")
            if not (0.1 <= confidence_threshold <= 0.9):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Confidence threshold must be between 0.1 and 0.9'
                }, status=400)
            scans_base = getattr(settings, 'SHIMSY_SCANS_BASE', '/home/ecdysis/shimsy_scans')
            if not os.path.exists(scans_base):
                print(f"[DEBUG] Scans base not found: {scans_base}")
                local_test_path = os.path.join(settings.BASE_DIR, 'test_shimsy_scans')
                if os.path.exists(local_test_path):
                    print(f"[DEBUG] Using local test data: {local_test_path}")
                    scans_base = local_test_path
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Scans directory not found: {scans_base}',
                        'debug_info': f'Tried local test path: {local_test_path}'
                    }, status=404)
            if requested_run:
                target_run_path = os.path.join(scans_base, requested_run)
                if not os.path.exists(target_run_path):
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Requested run folder not found: {requested_run}'
                    }, status=404)
            else:
                target_run_path = get_latest_run_folder()
            if not target_run_path:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No latest run folder found. Please ensure a scan has been completed.'
                }, status=404)
            subfolders_paths = get_run_subfolders(target_run_path)
            if not subfolders_paths:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No subfolders found in the run folder'
                }, status=404)
            subfolders = []
            for i, subfolder_path in enumerate(subfolders_paths):
                subfolder_name = os.path.basename(subfolder_path)
                nested_folders = []
                main_image_count = 0
                try:
                    for file in os.listdir(subfolder_path):
                        file_path = os.path.join(subfolder_path, file)
                        if os.path.isfile(file_path) and file.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp')):
                            main_image_count += 1
                        elif os.path.isdir(file_path):
                            nested_image_count = 0
                            try:
                                for nested_root, nested_dirs, nested_files in os.walk(file_path):
                                    for nested_file in nested_files:
                                        if nested_file.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp')):
                                            nested_image_count += 1
                            except Exception:
                                nested_image_count = 0
                            nested_folders.append({
                                'name': file,
                                'path': file_path,
                                'image_count': nested_image_count,
                                'parent_index': i
                            })
                except Exception:
                    main_image_count = 0
                subfolders.append({
                    'index': i,
                    'name': subfolder_name,
                    'path': subfolder_path,
                    'image_count': main_image_count,
                    'nested_folders': nested_folders,
                    'has_nested': len(nested_folders) > 0
                })
            print(f"[DEBUG] Processing subfolder_index: {subfolder_index}")
            if subfolder_index == 'all':
                print("[DEBUG] Bulk upload requested - returning error")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Bulk upload not supported with nested folder selection. Please select individual folders.'
                }, status=400)
            try:
                idx = int(subfolder_index)
                print(f"[DEBUG] Converted subfolder_index to int: {idx}")
                print(f"[DEBUG] Total subfolders available: {len(subfolders)}")
                if 0 <= idx < len(subfolders):
                    parent_folder = subfolders[idx]
                    print(f"[DEBUG] Selected parent folder: {parent_folder}")
                    if nested_index >= 0:
                        nested_folders = parent_folder.get('nested_folders', [])
                        if nested_index < len(nested_folders):
                            target_folder_path = nested_folders[nested_index]['path']
                            folder_display_name = f"{parent_folder['name']} > {nested_folders[nested_index]['name']}"
                            upload_description = f"nested folder: {folder_display_name}"
                        else:
                            return JsonResponse({
                                'status': 'error',
                                'message': f'Invalid nested folder index: {nested_index}'
                            }, status=400)
                    else:
                        target_folder_path = parent_folder['path']
                        folder_display_name = parent_folder['name']
                        upload_description = f"main folder: {folder_display_name}"
                    folders_to_zip = [target_folder_path]
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Invalid subfolder index. Must be 0-{len(subfolders)-1}'
                    }, status=400)
            except ValueError:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid subfolder index format'
                }, status=400)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
                temp_zip_path = temp_zip.name
            try:
                processed_folders = []
                temp_rotation_dirs = []
                for folder_path in folders_to_zip:
                    if image_rotations:
                        print(f"[DEBUG] Applying rotations to folder: {folder_path}")
                        rotated_folder_path = apply_image_rotations(folder_path, image_rotations)
                        processed_folders.append(rotated_folder_path)
                        if rotated_folder_path != folder_path:
                            temp_rotation_dirs.append(rotated_folder_path)
                    else:
                        processed_folders.append(folder_path)
                with ZipFile(temp_zip_path, 'w', ZIP_DEFLATED) as zipf:
                    for folder_path in processed_folders:
                        folder_name = os.path.basename(folder_path)
                        for root, dirs, files in os.walk(folder_path):
                            for file in files:
                                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp')):
                                    file_path = os.path.join(root, file)
                                    if len(processed_folders) == 1:
                                        arcname = file
                                    else:
                                        arcname = os.path.join(folder_name, os.path.relpath(file_path, folder_path))
                                    zipf.write(file_path, arcname)
                with ZipFile(temp_zip_path, 'r') as zipf:
                    if len(zipf.namelist()) == 0:
                        return JsonResponse({
                            'status': 'error',
                            'message': f'No image files found in {upload_description}'
                        }, status=400)
                if len(folders_to_zip) == 1:
                    folder_name = os.path.basename(folders_to_zip[0])
                    stitcher_name = parse_stitcher_zip_name(folder_name)
                    zip_filename = f"{stitcher_name}.zip"
                    print(f"[DEBUG] ZIP filename: {folder_name} -> {zip_filename}")
                else:
                    zip_filename = f"{os.path.basename(target_run_path)}_complete.zip"
                result = upload_to_stitcher(temp_zip_path, confidence_threshold, zip_filename)
                if result['success']:
                    run_folder_name = os.path.basename(target_run_path)
                    try:
                        folder_name = os.path.basename(folders_to_zip[0])
                        update_stitching_progress(run_folder_name, folder_name)
                        
                        
                        parsed_info = parse_folder_name_for_database(folder_name)
                        if parsed_info:
                            
                            matching_records = ScanRecord.objects.filter(
                                site_number=parsed_info['site'],
                                sample_type=parsed_info['sample_type'],
                                transect=parsed_info['transect']
                            )
                            updated_count = matching_records.update(stitched=True)
                            if updated_count > 0:
                                print(f"[DEBUG] Marked {updated_count} ScanRecord(s) as stitched for {parsed_info['site']}-{parsed_info['sample_type']}-{parsed_info['transect']}")
                            
                            
                            deleted_count, _ = RescanRequest.objects.filter(
                                site_number=parsed_info['site'],
                                sample_type=parsed_info['sample_type'],
                                transect=parsed_info['transect']
                            ).delete()
                            
                            rescan_deleted = deleted_count > 0
                            if rescan_deleted:
                                print(f"[DEBUG] Removed {deleted_count} RescanRequest(s) for {parsed_info['site']}-{parsed_info['sample_type']}-{parsed_info['transect']} (sample uploaded successfully)")
                        else:
                            from .utils import parse_stitcher_sample_name
                            parsed_underscore = parse_stitcher_sample_name(folder_name)
                            if parsed_underscore:
                                deleted_count, _ = RescanRequest.objects.filter(
                                    site_number=parsed_underscore['site_number'],
                                    sample_type=parsed_underscore['sample_type'],
                                    transect=parsed_underscore['transect']
                                ).delete()
                                rescan_deleted = deleted_count > 0
                                if rescan_deleted:
                                    print(f"[DEBUG] Removed {deleted_count} RescanRequest(s) for {parsed_underscore['site_number']}-{parsed_underscore['sample_type']}-{parsed_underscore['transect']} (sample uploaded successfully, parsed from underscore format)")
                            else:
                                rescan_deleted = False
                    except Exception as e:
                        print(f"[WARNING] Could not update stitching progress or mark as stitched: {e}")
                        rescan_deleted = False
                    return JsonResponse({
                        'status': 'success',
                        'message': f'Successfully uploaded {upload_description} to stitcher',
                        'stitcher_response': result['data'],
                        'run_folder': run_folder_name,
                        'uploaded_folders': upload_description,
                        'confidence_threshold': confidence_threshold,
                        'total_subfolders': len(subfolders),
                        'rescan_deleted': rescan_deleted  
                    })
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Failed to upload to stitcher',
                        'error': result['error']
                    }, status=500)
            finally:
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
                for temp_dir in temp_rotation_dirs:
                    if os.path.exists(temp_dir):
                        try:
                            shutil.rmtree(temp_dir)
                            print(f"[DEBUG] Cleaned up temp rotation directory: {temp_dir}")
                        except Exception as e:
                            print(f"[WARNING] Failed to cleanup temp dir {temp_dir}: {e}")
        except ValueError as e:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid confidence threshold value'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
def create_rescan_request(request):
    
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)
    
    try:
        from .utils import parse_stitcher_sample_name
        
        body = json.loads(request.body)
        sample_name = body.get('sample_name')
        
        if not sample_name:
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required field: sample_name'
            }, status=400)
        
        parsed = parse_stitcher_sample_name(sample_name)
        if not parsed:
            return JsonResponse({
                'status': 'error',
                'message': f'Invalid sample_name format: {sample_name}'
            }, status=400)
        
        rescan_request, created = RescanRequest.objects.get_or_create(
            site_number=parsed['site_number'],
            sample_type=parsed['sample_type'],
            transect=parsed['transect']
        )
        
        return JsonResponse({
            'status': 'success',
            'message': 'Rescan request created' if created else 'Rescan request already exists',
            'created': created,
            'rescan_request': {
                'id': rescan_request.id,
                'display_name': rescan_request.display_name,
                'requested_at': rescan_request.requested_at.isoformat()
            }
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

def rescan_samples(request):
    
    rescan_requests = RescanRequest.objects.all().order_by('-requested_at')

    return render(request, 'controller/rescan_samples.html', {
        'rescan_requests': rescan_requests
    })

@csrf_exempt
def get_rescan_requests(request):
    
    if request.method == 'GET':
        rescan_requests = RescanRequest.objects.all().order_by('-requested_at')
        from django.utils import timezone
        requests_data = [
            {
                'id': req.id,
                'display_name': req.display_name,
                'site_number': req.site_number,
                'sample_type': req.sample_type,
                'transect': req.transect,
                'requested_at': req.requested_at.isoformat() if req.requested_at else None
            }
            for req in rescan_requests
        ]
        return JsonResponse({
            'status': 'success',
            'rescan_requests': requests_data
        })
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

@csrf_exempt
def trigger_rescan_for_dish(request):
    
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)
    
    try:
        from .utils import filter_capture_points_by_dish
        import shutil
        
        body = json.loads(request.body)
        rescan_request_id = body.get('rescan_request_id')
        dish_number = body.get('dish_number')
        name = body.get('name', '').strip()  
        name2 = body.get('name2', '').strip()  
        
        
        if not rescan_request_id or not dish_number:
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required fields: rescan_request_id, dish_number'
            }, status=400)
        
        dish_number = int(dish_number)
        if not (1 <= dish_number <= 6):
            return JsonResponse({
                'status': 'error',
                'message': 'dish_number must be between 1 and 6'
            }, status=400)
        
        
        try:
            rescan_req = RescanRequest.objects.get(id=rescan_request_id)
        except RescanRequest.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': f'Rescan request {rescan_request_id} not found'
            }, status=404)
        
        
        
        from datetime import datetime
        from .utils import convert_sample_type_abbrev_to_full
        year = datetime.now().year
        
        full_sample_type = convert_sample_type_abbrev_to_full(rescan_req.sample_type)
        sample_name = f"{rescan_req.site_number}-{year}-{full_sample_type}-{rescan_req.transect}"
        
        
        sample_names_ordered = [f"UnknownSample{i}" for i in range(1, 7)]
        sample_names_ordered[dish_number - 1] = sample_name
        
        scan_config_path = "/home/ecdysis/shimmsy/shimsy/controller/scan_config.json"
        with open(scan_config_path, "w") as f:
            json.dump({"samples": sample_names_ordered}, f, indent=4)
        
        
        filtered_path_data = filter_capture_points_by_dish(dish_number)
        
        
        custom_path_file = "/home/ecdysis/shimmsy/shimsy/custom_path.json"
        custom_path_backup = "/home/ecdysis/shimmsy/shimsy/custom_path.json.backup"
        
        if os.path.exists(custom_path_file):
            shutil.copy(custom_path_file, custom_path_backup)
        
        
        with open(custom_path_file, "w") as f:
            json.dump(filtered_path_data, f, indent=2)
        
        
        template_flag_path = "/home/ecdysis/shimmsy/shimsy/controller/template_flag.json"
        with open(template_flag_path, "w") as f:
            json.dump({"template": "custom"}, f)
        
        
        command = [
            'python3',
            '/home/ecdysis/shimmsy/shimsy/controller/scripts/run_scan.py'
        ]
        
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()
        
        
        if os.path.exists(custom_path_backup):
            shutil.move(custom_path_backup, custom_path_file)
        elif os.path.exists(custom_path_file):
            os.remove(custom_path_file)
        
        
        with open(template_flag_path, "w") as f:
            json.dump({"template": "default"}, f)
        
        if process.returncode == 0:
            
            RUN_COUNTER_PATH = "/home/ecdysis/shimmsy/shimsy/controller/scan_run_counter.json"
            try:
                with open(RUN_COUNTER_PATH) as f:
                    run_number = json.load(f).get("run", 1)
            except Exception:
                run_number = 1
            
            
            
            parts = sample_name.split("-")
            if len(parts) == 4:
                site, _year, sample_type, transect = parts
            elif len(parts) == 3:
                site, sample_type, transect = parts
            else:
                site = rescan_req.site_number
                sample_type = rescan_req.sample_type
                transect = rescan_req.transect
            
            site = site[:4]
            
            
            
            record_name = name if name else "Rescan"
            record = ScanRecord.objects.create(
                name=record_name,
                name2=name2,  
                site_number=site,
                sample_type=sample_type,
                transect=transect,
                run_number=run_number,
                stitcher_retake=True,  
                retake=False,  
                stitched=False,  
                is_splitted=False
            )
            print(f"[DEBUG] Created rescan ScanRecord ID: {record.id} with stitcher_retake=True")
            
            return JsonResponse({
                'status': 'success',
                'message': f'Rescan started for {rescan_req.display_name} on dish {dish_number}',
                'sample_name': f"{dish_number}_{sample_name}",
                'dish_number': dish_number
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Scan failed: {stderr}',
                'stdout': stdout
            }, status=500)
            
    except Exception as e:
        import traceback
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }, status=500)

@csrf_exempt
def get_all_run_folders(request):
    
    if request.method == 'GET':
        try:
            scans_base = getattr(settings, 'SHIMSY_SCANS_BASE', '/home/ecdysis/shimsy_scans')
            if not os.path.exists(scans_base):
                print(f"[DEBUG] Scans base not found: {scans_base}")
                local_test_path = os.path.join(settings.BASE_DIR, 'test_shimsy_scans')
                if os.path.exists(local_test_path):
                    print(f"[DEBUG] Using local test data: {local_test_path}")
                    scans_base = local_test_path
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Scans directory not found: {scans_base}',
                        'debug_info': f'Tried local test path: {local_test_path}'
                    }, status=404)
            run_folders = []
            try:
                all_items = os.listdir(scans_base)
                for item in all_items:
                    item_path = os.path.join(scans_base, item)
                    if os.path.isdir(item_path) and item.startswith('run_'):
                        subfolders = get_run_subfolders(item_path)
                        run_folders.append({
                            'name': item,
                            'path': item_path,
                            'subfolder_count': len(subfolders),
                            'modified_time': os.path.getctime(item_path)
                        })
                run_folders.sort(key=lambda x: x['modified_time'], reverse=True)
                return JsonResponse({
                    'status': 'success',
                    'run_folders': run_folders,
                    'latest_run': run_folders[0]['name'] if run_folders else None
                })
            except Exception as e:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Error listing run folders: {str(e)}'
                }, status=500)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error accessing run folders: {str(e)}'
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
def get_run_subfolders_info(request):
    
    if request.method == 'GET':
        try:
            scans_base = getattr(settings, 'SHIMSY_SCANS_BASE', '/home/ecdysis/shimsy_scans')
            if not os.path.exists(scans_base):
                print(f"[DEBUG] Scans base not found: {scans_base}")
                local_test_path = os.path.join(settings.BASE_DIR, 'test_shimsy_scans')
                if os.path.exists(local_test_path):
                    print(f"[DEBUG] Using local test data: {local_test_path}")
                    scans_base = local_test_path
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Scans directory not found: {scans_base}',
                        'debug_info': f'Tried local test path: {local_test_path}'
                    }, status=404)
            requested_run = request.GET.get('run_folder')
            if requested_run:
                requested_run_path = os.path.join(scans_base, requested_run)
                if not os.path.exists(requested_run_path):
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Requested run folder not found: {requested_run}'
                    }, status=404)
                target_run_path = requested_run_path
            else:
                target_run_path = get_latest_run_folder()
            if not target_run_path:
                try:
                    available_items = os.listdir(scans_base)
                    return JsonResponse({
                        'status': 'error',
                        'message': f'No run folders found in {scans_base}',
                        'debug_info': f'Available items: {available_items}'
                    }, status=404)
                except Exception as e:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Cannot access scans directory: {scans_base}',
                        'debug_info': str(e)
                    }, status=404)
            subfolders = get_run_subfolders(target_run_path)
            subfolder_info = []
            for i, subfolder_path in enumerate(subfolders):
                subfolder_name = os.path.basename(subfolder_path)
                nested_folders = []
                main_image_count = 0
                try:
                    for file in os.listdir(subfolder_path):
                        file_path = os.path.join(subfolder_path, file)
                        if os.path.isfile(file_path) and file.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp')):
                            main_image_count += 1
                        elif os.path.isdir(file_path):
                            nested_image_count = 0
                            try:
                                for nested_root, nested_dirs, nested_files in os.walk(file_path):
                                    for nested_file in nested_files:
                                        if nested_file.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp')):
                                            nested_image_count += 1
                            except Exception:
                                nested_image_count = 0
                            nested_folders.append({
                                'name': file,
                                'path': file_path,
                                'image_count': nested_image_count,
                                'parent_index': i
                            })
                except Exception:
                    main_image_count = 0
                total_image_count = main_image_count + sum(nf['image_count'] for nf in nested_folders)
                subfolder_info.append({
                    'index': i,
                    'name': subfolder_name,
                    'path': subfolder_path,
                    'image_count': main_image_count,
                    'total_image_count': total_image_count,
                    'nested_folders': nested_folders,
                    'has_nested': len(nested_folders) > 0
                })
            return JsonResponse({
                'status': 'success',
                'run_folder': os.path.basename(target_run_path),
                'run_folder_path': target_run_path,
                'subfolders': subfolder_info,
                'total_subfolders': len(subfolder_info)
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error processing run folders: {str(e)}',
                'debug_info': f'Scans base: {scans_base}'
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
def get_folder_images(request):
    
    if request.method == 'GET':
        try:
            folder_path = request.GET.get('folder_path')
            if not folder_path:
                return JsonResponse({
                    'status': 'error',
                    'message': 'folder_path parameter is required'
                }, status=400)
            scans_base = getattr(settings, 'SHIMSY_SCANS_BASE', '/home/ecdysis/shimsy_scans')
            if not folder_path.startswith(scans_base):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Access denied - invalid folder path'
                }, status=403)
            if not os.path.exists(folder_path):
                return JsonResponse({
                    'status': 'error',
                    'message': f'Folder not found: {folder_path}'
                }, status=404)
            images = []
            try:
                for file in os.listdir(folder_path):
                    if file.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp')):
                        file_path = os.path.join(folder_path, file)
                        file_stats = os.stat(file_path)
                        images.append({
                            'name': file,
                            'path': file_path,
                            'relative_path': os.path.relpath(file_path, scans_base),
                            'size': file_stats.st_size,
                            'modified': file_stats.st_mtime,
                            'is_label': file.lower().startswith('label')
                        })
                images.sort(key=lambda x: (not x['is_label'], x['name']))
                return JsonResponse({
                    'status': 'success',
                    'folder_path': folder_path,
                    'folder_name': os.path.basename(folder_path),
                    'images': images,
                    'total_images': len(images)
                })
            except Exception as e:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Error reading folder contents: {str(e)}'
                }, status=500)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error processing request: {str(e)}'
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
def serve_image(request):
    
    if request.method == 'GET':
        try:
            image_path = request.GET.get('image_path')
            size = request.GET.get('size', 'full')
            quality = int(request.GET.get('quality', 85))
            if not image_path:
                return JsonResponse({
                    'status': 'error',
                    'message': 'image_path parameter is required'
                }, status=400)
            scans_base = getattr(settings, 'SHIMSY_SCANS_BASE', '/home/ecdysis/shimsy_scans')
            if not image_path.startswith(scans_base):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Access denied - invalid image path'
                }, status=403)
            if not os.path.exists(image_path):
                return Http404("Image not found")
            try:
                from PIL import Image as PILImage
                from io import BytesIO
                import hashlib
                cache_key = hashlib.md5(f"{image_path}_{size}_{quality}".encode()).hexdigest()
                cache_dir = os.path.join(scans_base, '.image_cache')
                os.makedirs(cache_dir, exist_ok=True)
                cache_path = os.path.join(cache_dir, f"{cache_key}.jpg")
                if os.path.exists(cache_path) and os.path.getmtime(cache_path) > os.path.getmtime(image_path):
                    with open(cache_path, 'rb') as f:
                        response = HttpResponse(f.read(), content_type='image/jpeg')
                        cache_buster = request.GET.get('t') or request.GET.get('r') or request.GET.get('rot') or request.GET.get('v')
                        if not cache_buster:
                            response['Cache-Control'] = 'public, max-age=31536000'
                            response['ETag'] = f'"{cache_key}"'
                        else:
                            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                            response['Pragma'] = 'no-cache'
                            response['Expires'] = '0'
                        return response
                with PILImage.open(image_path) as img:
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGB')
                    if size == 'thumbnail':
                        img.thumbnail((300, 300), PILImage.Resampling.LANCZOS)
                    elif size == 'medium':
                        img.thumbnail((800, 800), PILImage.Resampling.LANCZOS)
                    img.save(cache_path, 'JPEG', quality=quality, optimize=True, progressive=True)
                    output = BytesIO()
                    img.save(output, format='JPEG', quality=quality, optimize=True, progressive=True)
                    output.seek(0)
                    response = HttpResponse(output.getvalue(), content_type='image/jpeg')
                    cache_buster = request.GET.get('t') or request.GET.get('r') or request.GET.get('rot') or request.GET.get('v')
                    if not cache_buster:
                        response['Cache-Control'] = 'public, max-age=31536000'
                        response['ETag'] = f'"{cache_key}"'
                    else:
                        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                        response['Pragma'] = 'no-cache'
                        response['Expires'] = '0'
                    return response
            except ImportError:
                pass
            except Exception as e:
                print(f"Image optimization failed: {e}")
                pass
            content_type = 'image/jpeg'
            if image_path.lower().endswith('.png'):
                content_type = 'image/png'
            elif image_path.lower().endswith(('.tiff', '.tif')):
                content_type = 'image/tiff'
            elif image_path.lower().endswith('.bmp'):
                content_type = 'image/bmp'
            response = FileResponse(
                open(image_path, 'rb'),
                content_type=content_type,
                filename=os.path.basename(image_path)
            )
            cache_buster = request.GET.get('t') or request.GET.get('r') or request.GET.get('rot') or request.GET.get('v')
            if not cache_buster:
                response['Cache-Control'] = 'public, max-age=3600'
            else:
                response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response['Pragma'] = 'no-cache'
                response['Expires'] = '0'
            return response
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error serving image: {str(e)}'
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

def check_stitching_status(request):
    
    if request.method != 'GET':
        return JsonResponse({'status': 'error', 'message': 'Only GET requests allowed'}, status=405)
    run_folder = request.GET.get('run_folder')
    if not run_folder:
        return JsonResponse({'status': 'error', 'message': 'run_folder parameter required'}, status=400)
    try:
        unstitched_run = UnstitchedRun.objects.get(run_folder=run_folder)
        scans_base = getattr(settings, 'SHIMSY_SCANS_BASE', '/home/ecdysis/shimsy_scans')
        run_path = os.path.join(scans_base, run_folder)
        total_subfolders = 0
        if os.path.exists(run_path):
            total_subfolders = len([f for f in os.scandir(run_path) if f.is_dir()])
        stitched_folders = unstitched_run.get_stitched_folders()
        stitched_subfolders = len(stitched_folders)
        is_stitched = unstitched_run.is_complete or stitched_subfolders >= 6
        return JsonResponse({
            'status': 'success',
            'run_folder': run_folder,
            'is_stitched': is_stitched,
            'stitched_subfolders': stitched_subfolders,
            'total_subfolders': max(total_subfolders, unstitched_run.total_subfolders),
            'stitched_folders': stitched_folders,
            'is_complete': unstitched_run.is_complete,
            'last_updated': unstitched_run.last_updated.isoformat() if unstitched_run.last_updated else None
        })
    except UnstitchedRun.DoesNotExist:
        scans_base = getattr(settings, 'SHIMSY_SCANS_BASE', '/home/ecdysis/shimsy_scans')
        run_path = os.path.join(scans_base, run_folder)
        if os.path.exists(run_path):
            total_subfolders = len([f for f in os.scandir(run_path) if f.is_dir()])
            return JsonResponse({
                'status': 'success',
                'run_folder': run_folder,
                'is_stitched': False,
                'stitched_subfolders': 0,
                'total_subfolders': total_subfolders,
                'stitched_folders': [],
                'is_complete': False,
                'last_updated': None,
                'note': 'No stitching record found - run may not have been stitched yet'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Run folder not found: {run_folder}'
            }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error checking stitching status: {str(e)}'
        }, status=500)

@csrf_exempt
def get_folder_management_data(request):
    
    if request.method == 'GET':
        try:
            run_folder = request.GET.get('run_folder')
            if not run_folder:
                return JsonResponse({
                    'status': 'error',
                    'message': 'run_folder parameter is required'
                }, status=400)
            scans_base = getattr(settings, 'SHIMSY_SCANS_BASE', '/home/ecdysis/shimsy_scans')
            if not os.path.exists(scans_base):
                local_test_path = os.path.join(settings.BASE_DIR, 'test_shimsy_scans')
                if os.path.exists(local_test_path):
                    scans_base = local_test_path
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Scans directory not found: {scans_base}'
                    }, status=404)
            run_path = os.path.join(scans_base, run_folder)
            if not os.path.exists(run_path):
                return JsonResponse({
                    'status': 'error',
                    'message': f'Run folder not found: {run_folder}'
                }, status=404)
            folders = []
            try:
                all_items = os.listdir(run_path)
                for item in sorted(all_items):
                    item_path = os.path.join(run_path, item)
                    if os.path.isdir(item_path):
                        nested_folders = []
                        try:
                            nested_items = os.listdir(item_path)
                            for nested_item in sorted(nested_items):
                                nested_path = os.path.join(item_path, nested_item)
                                if os.path.isdir(nested_path):
                                    nested_folders.append({
                                        'name': nested_item,
                                        'path': nested_path,
                                        'is_nested': True
                                    })
                        except Exception as e:
                            print(f"Error reading nested folders for {item}: {e}")
                        folders.append({
                            'name': item,
                            'path': item_path,
                            'is_nested': False,
                            'nested_folders': nested_folders
                        })
            except Exception as e:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Error reading folder contents: {str(e)}'
                }, status=500)
            return JsonResponse({
                'status': 'success',
                'run_folder': run_folder,
                'folders': folders
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error getting folder management data: {str(e)}'
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

def parse_folder_name_for_database(folder_name):
    
    try:
        print(f"[DEBUG] Parsing folder name for database: '{folder_name}'")
        if '_' in folder_name:
            parts = folder_name.split('_', 1)
            if len(parts) > 1 and parts[0].isdigit():
                folder_name = parts[1]
        is_split = False
        split_number = None
        if '_split_' in folder_name:
            is_split = True
            split_parts = folder_name.split('_split_')
            if len(split_parts) > 1:
                split_number_part = split_parts[1].split('_')[0]
                if split_number_part.isdigit():
                    split_number = int(split_number_part)
            folder_name = split_parts[0]
        import re
        folder_name = re.sub(r'_\d{8}_\d{6}$', '', folder_name)
        if '-' in folder_name:
            parts = folder_name.split('-')
            if len(parts) >= 4:
                site, year, sample_type, transect = parts[:4]
            elif len(parts) == 3:
                site, sample_type, transect = parts
            else:
                print(f"[DEBUG] Could not parse folder name parts: {parts}")
                return None
            site = site[:4]
            result = {
                'site': site,
                'sample_type': sample_type,
                'transect': transect,
                'is_split': is_split,
                'split_number': split_number
            }
            print(f"[DEBUG] Parsed result: {result}")
            return result
        else:
            print(f"[DEBUG] No dashes found in folder name: {folder_name}")
            return None
    except Exception as e:
        print(f"[DEBUG] Error parsing folder name '{folder_name}': {e}")
        return None

@csrf_exempt
def rename_folder(request):
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            old_path = data.get('old_path')
            new_name = data.get('new_name')
            if not old_path or not new_name:
                return JsonResponse({
                    'status': 'error',
                    'message': 'old_path and new_name are required'
                }, status=400)
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', new_name):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Folder name can only contain letters, numbers, underscores, and hyphens'
                }, status=400)
            if not os.path.exists(old_path):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Source folder does not exist'
                }, status=404)
            parent_dir = os.path.dirname(old_path)
            new_path = os.path.join(parent_dir, new_name)
            if os.path.exists(new_path):
                return JsonResponse({
                    'status': 'error',
                    'message': 'A folder with this name already exists'
                }, status=409)
            try:
                os.rename(old_path, new_path)
                try:
                    old_folder_name = os.path.basename(old_path)
                    new_folder_name = os.path.basename(new_path)
                    print(f"[DEBUG] Updating database records for folder rename: {old_folder_name} -> {new_folder_name}")
                    for run in UnstitchedRun.objects.all():
                        if old_folder_name in run.stitched_folder_names:
                            updated_names = run.stitched_folder_names.replace(old_folder_name, new_folder_name)
                            run.stitched_folder_names = updated_names
                            run.save()
                            print(f"[DEBUG] Updated UnstitchedRun stitched folder names for {run.run_folder}")
                    old_info = parse_folder_name_for_database(old_folder_name)
                    new_info = parse_folder_name_for_database(new_folder_name)
                    if old_info and new_info:
                        print(f"[DEBUG] Old folder info: {old_info}")
                        print(f"[DEBUG] New folder info: {new_info}")
                        run_number = None
                        path_parts = old_path.split(os.sep)
                        for part in reversed(path_parts):
                            if part.startswith('run_'):
                                try:
                                    run_number = int(part.replace('run_', ''))
                                    break
                                except ValueError:
                                    continue
                        if run_number:
                            print(f"[DEBUG] Found run number: {run_number}")
                            updated_records = 0
                            matching_records = ScanRecord.objects.filter(
                                run_number=run_number,
                                site_number=old_info['site'],
                                sample_type=old_info['sample_type'],
                                transect=old_info['transect']
                            )
                            print(f"[DEBUG] Found {matching_records.count()} matching ScanRecord entries")
                            for record in matching_records:
                                if new_info['site'] != old_info['site']:
                                    record.site_number = new_info['site']
                                    print(f"[DEBUG] Updated site number: {old_info['site']} -> {new_info['site']}")
                                if new_info['is_split'] != old_info['is_split']:
                                    record.is_splitted = new_info['is_split']
                                    print(f"[DEBUG] Updated split status: {old_info['is_split']} -> {new_info['is_split']}")
                                record.save()
                                updated_records += 1
                                print(f"[DEBUG] Updated ScanRecord ID: {record.id}")
                            print(f"[DEBUG] Updated {updated_records} ScanRecord entries")
                        else:
                            print(f"[WARNING] Could not determine run number from path: {old_path}")
                    else:
                        print(f"[WARNING] Could not parse folder names for database update")
                        if not old_info:
                            print(f"[WARNING] Failed to parse old folder name: {old_folder_name}")
                        if not new_info:
                            print(f"[WARNING] Failed to parse new folder name: {new_folder_name}")
                except Exception as e:
                    print(f"Warning: Could not update database records: {e}")
                    import traceback
                    traceback.print_exc()
                return JsonResponse({
                    'status': 'success',
                    'message': f'Folder renamed from {os.path.basename(old_path)} to {new_name}',
                    'new_path': new_path
                })
            except OSError as e:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Failed to rename folder: {str(e)}'
                }, status=500)
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error renaming folder: {str(e)}'
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
def discard_unstitched_run(request):
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            run_folder = data.get('run_folder')
            if not run_folder:
                return JsonResponse({
                    'status': 'error',
                    'message': 'run_folder parameter is required'
                }, status=400)
            try:
                unstitched_run = UnstitchedRun.objects.get(run_folder=run_folder)
                run_info = {
                    'run_folder': unstitched_run.run_folder,
                    'total_subfolders': unstitched_run.total_subfolders,
                    'stitched_subfolders': unstitched_run.stitched_subfolders,
                    'created_at': unstitched_run.created_at.isoformat()
                }
                unstitched_run.delete()
                print(f"[DEBUG] Discarded unstitched run: {run_folder}")
                return JsonResponse({
                    'status': 'success',
                    'message': f'Successfully discarded run: {run_folder}',
                    'discarded_run': run_info
                })
            except UnstitchedRun.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Unstitched run not found: {run_folder}'
                }, status=404)
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error discarding run: {str(e)}'
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
def rotate_image(request):
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            image_path = data.get('image_path')
            degrees = int(data.get('degrees', 90))
            if not image_path:
                return JsonResponse({
                    'status': 'error',
                    'message': 'image_path parameter is required'
                }, status=400)
            scans_base = getattr(settings, 'SHIMSY_SCANS_BASE', '/home/ecdysis/shimsy_scans')
            image_path_normalized = os.path.normpath(image_path)
            scans_base_normalized = os.path.normpath(scans_base)
            if not os.path.exists(image_path_normalized):
                return JsonResponse({
                    'status': 'error',
                    'message': f'Image not found: {image_path}'
                }, status=404)
            degrees = degrees % 360
            if degrees not in [0, 90, 180, 270]:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Degrees must be 90, 180, 270, or 0'
                }, status=400)
            if degrees == 0:
                return JsonResponse({
                    'status': 'success',
                    'message': 'No rotation needed'
                })
            img = Image.open(image_path_normalized)
            if degrees == 90:
                rotated_img = img.rotate(-90, expand=True)
            elif degrees == 180:
                rotated_img = img.rotate(180, expand=True)
            elif degrees == 270:
                rotated_img = img.rotate(90, expand=True)
            else:
                rotated_img = img
            img_format = img.format or 'JPEG'
            rotated_img.save(image_path_normalized, format=img_format, quality=95)
            img.close()
            rotated_img.close()
            cache_dir = os.path.join(scans_base_normalized, '.image_cache')
            if os.path.exists(cache_dir):
                import hashlib
                for size in ['thumbnail', 'medium', 'full']:
                    for quality in [75, 85, 90, 95]:
                        cache_key = hashlib.md5(f"{image_path_normalized}_{size}_{quality}".encode()).hexdigest()
                        cache_path = os.path.join(cache_dir, f"{cache_key}.jpg")
                        if os.path.exists(cache_path):
                            try:
                                os.remove(cache_path)
                                print(f"Cleared cache: {cache_path}")
                            except Exception as e:
                                print(f"Cache cleanup warning: {e}")
                try:
                    import glob
                    image_basename = os.path.basename(image_path_normalized)
                    image_name = os.path.splitext(image_basename)[0]
                    cache_pattern = os.path.join(cache_dir, f"*{image_name}*")
                    for cache_file in glob.glob(cache_pattern):
                        try:
                            os.remove(cache_file)
                            print(f"Cleared additional cache: {cache_file}")
                        except:
                            pass
                except:
                    pass
            response = JsonResponse({
                'status': 'success',
                'message': f'Image rotated {degrees} degrees successfully',
                'image_path': image_path_normalized
            })
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response
        except json.JSONDecodeError as e:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error in rotate_image: {error_details}")
            return JsonResponse({
                'status': 'error',
                'message': f'Error rotating image: {str(e)}'
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)
