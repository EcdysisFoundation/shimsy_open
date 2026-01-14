
"""
Staging utilities for Shimsy scanner
Provides common functions for RAM-based staging and network synchronization
"""

import os
import shutil
import subprocess
import tempfile
from datetime import datetime



STAGING_ROOT = "/mnt/shimsy_tmp"
FINAL_ROOT = "/home/ecdysis/shimsy_scans"


def ensure_staging_available():
    """
    Ensure staging directory is available and mounted
    Returns True if available, False otherwise
    """
    if not os.path.exists(STAGING_ROOT):
        print(f"[WARNING] Staging directory {STAGING_ROOT} does not exist")
        return False
    try:
        result = subprocess.run(["mountpoint", "-q", STAGING_ROOT],
                              capture_output=True, check=False)
        if result.returncode != 0:
            print(f"[WARNING] {STAGING_ROOT} is not a mount point (tmpfs not configured)")
            return False
    except Exception:
        print(f"[WARNING] Could not check mount status of {STAGING_ROOT}")
        return False
    try:
        test_file = os.path.join(STAGING_ROOT, f"test_{os.getpid()}")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True
    except Exception as e:
        print(f"[WARNING] Cannot write to staging directory: {e}")
        return False


def create_staging_dir(prefix="retake"):
    """
    Create a staging directory for temporary files
    Returns (staging_path, use_staging) tuple
    """
    use_staging = ensure_staging_available()
    if use_staging:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        staging_path = os.path.join(STAGING_ROOT, f"{prefix}_{timestamp}_{os.getpid()}")
        os.makedirs(staging_path, exist_ok=True)
        print(f"[INFO] Using RAM staging: {staging_path}")
        return staging_path, True
    else:
        staging_path = tempfile.mkdtemp(prefix=f"{prefix}_", dir="/tmp")
        print(f"[INFO] Using disk staging (tmpfs unavailable): {staging_path}")
        return staging_path, False


def sync_to_network(staging_path, final_path, cleanup_staging=True):
    """
    Sync files from staging to network drive
    Returns True on success, False on failure
    """
    try:
        print(f"[INFO] Starting sync: {staging_path} ? {final_path}")
        os.makedirs(final_path, exist_ok=True)
        rsync_cmd = [
            "rsync", "-av", "--progress", "--checksum",
            staging_path + "/", final_path + "/"
        ]
        result = subprocess.run(rsync_cmd, check=True, capture_output=True, text=True)
        staging_files = sum(len(files) for _, _, files in os.walk(staging_path))
        final_files = sum(len(files) for _, _, files in os.walk(final_path))
        if staging_files != final_files:
            raise Exception(f"File count mismatch: staging={staging_files}, final={final_files}")
        print(f"[INFO] ? Successfully synced {staging_files} files to network drive")
        if cleanup_staging:
            try:
                shutil.rmtree(staging_path)
                print(f"[INFO] ? Cleaned staging folder: {staging_path}")
            except Exception as e:
                print(f"[WARNING] Could not clean staging folder: {e}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] rsync failed with exit code {e.returncode}")
        print(f"[ERROR] stdout: {e.stdout}")
        print(f"[ERROR] stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"[ERROR] Sync operation failed: {e}")
        return False


def get_disk_usage(path):
    """Get disk usage information for a path"""
    try:
        result = subprocess.run(["df", "-h", path], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "Unknown"


def check_staging_space():
    """Check and report staging space usage"""
    if os.path.exists(STAGING_ROOT):
        usage = get_disk_usage(STAGING_ROOT)
        print(f"[INFO] Staging space usage:\n{usage}")
        return usage
    return None
