

"""
NAS Utilities for Shimsy Scanner
NFS mount validation and sync operations
"""

import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

from shimsy_secrets import get_config


class NASError(Exception):
    """Custom exception for NAS-related errors"""
    pass


class NASManager:
    def __init__(self):
        cfg = get_config()
        repo = cfg.get("repo_home") or _APP_ROOT
        scans = cfg.get("shimsy_scans_base") or os.path.join(repo, "shimsy_scans")
        temp = cfg.get("shimsy_temp_base") or os.path.join(repo, "shimsy_temp")
        self.nas_ip = cfg.get("nas_ip") or ""
        self.nas_export = cfg.get("nas_export") or "/pool1/srv/shimsy/shimsy_scans"
        self.local_mount = scans
        self.temp_base = temp
        self.marker_file = ".nas_mounted_marker"
        self.config_file = os.path.join(repo, "controller", "nas_config.json")
        os.makedirs(self.temp_base, exist_ok=True)
    def _run_command(self, cmd, check=True, timeout=30):
        """Run a shell command with timeout"""
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, timeout=timeout, check=check
            )
            return result
        except subprocess.TimeoutExpired:
            raise NASError(f"Command timed out: {cmd}")
        except subprocess.CalledProcessError as e:
            raise NASError(f"Command failed: {cmd}\nError: {e.stderr}")
    def is_nas_mounted(self):
        try:
            result = self._run_command(f"grep '{self.local_mount}' /proc/mounts", check=False)
            if result.returncode != 0:
                return False, "Mount point not found in /proc/mounts"
            if f"{self.nas_ip}:{self.nas_export}" not in result.stdout:
                return False, f"Mount point exists but not pointing to NAS ({self.nas_ip}:{self.nas_export})"
            marker_path = os.path.join(self.local_mount, self.marker_file)
            if not os.path.exists(marker_path):
                try:
                    with open(marker_path, 'w') as f:
                        f.write(f"NAS mounted at {datetime.now().isoformat()}\n")
                except Exception as e:
                    return False, f"Cannot write marker file: {e}"
            result = self._run_command(f"ping -c 1 -W 3 {self.nas_ip}", check=False)
            if result.returncode != 0:
                return False, f"NAS IP {self.nas_ip} not reachable"
            test_file = os.path.join(self.temp_base, f".write_test_{int(time.time())}")
            try:
                with open(test_file, 'w') as f:
                    f.write("write test")
                os.remove(test_file)
            except Exception as e:
                return False, f"Cannot write (local staging): {e}"
            return True, "NAS properly mounted and accessible"
        except Exception as e:
            return False, f"Mount check failed: {e}"
    def ensure_nas_mounted(self):
        """Ensure NAS is mounted, attempt remount if necessary"""
        mounted, message = self.is_nas_mounted()
        if mounted:
            print(f"[NAS] {message}")
            return True
        print(f"[NAS] {message}")
        print(f"[NAS] Attempting to mount NAS...")
        try:
            self._run_command(f"umount {self.local_mount}", check=False)
            time.sleep(2)
            os.makedirs(self.local_mount, exist_ok=True)
            if os.listdir(self.local_mount):
                raise NASError(
                    f"Mount point {self.local_mount} is not empty! "
                    "This indicates local files that would be hidden by NFS mount. "
                    "Manual intervention required."
                )
            mount_cmd = (
                f"mount -t nfs -o nfsvers=3,tcp,hard,intr,timeo=30,retrans=3 "
                f"{self.nas_ip}:{self.nas_export} {self.local_mount}"
            )
            self._run_command(mount_cmd)
            mounted, message = self.is_nas_mounted()
            if not mounted:
                raise NASError(f"Mount verification failed: {message}")
            print(f"[NAS] Successfully mounted NAS")
            return True
        except Exception as e:
            raise NASError(f"Failed to mount NAS: {e}")
    def create_temp_scan_dir(self, run_name):
        """Create temporary scan directory on local storage"""
        temp_dir = os.path.join(self.temp_base, run_name)
        os.makedirs(temp_dir, exist_ok=True)
        status_file = os.path.join(temp_dir, ".sync_status.json")
        with open(status_file, 'w') as f:
            json.dump({
                "created": datetime.now().isoformat(),
                "status": "creating",
                "target_nas_path": os.path.join(self.local_mount, run_name)
            }, f, indent=2)
        return temp_dir
    def sync_to_nas(self, temp_dir, target_nas_dir=None, remove_temp=True):
        if not os.path.exists(temp_dir):
            raise NASError(f"Temp directory does not exist: {temp_dir}")
        if not self.ensure_nas_mounted():
            raise NASError("Cannot sync: NAS not available")
        if target_nas_dir is None:
            target_nas_dir = os.path.join(self.local_mount, os.path.basename(temp_dir))
        print(f"[NAS] Syncing {temp_dir} -> {target_nas_dir}")
        try:
            status_file = os.path.join(temp_dir, ".sync_status.json")
            if os.path.exists(status_file):
                with open(status_file, 'r') as f:
                    status = json.load(f)
                status["sync_started"] = datetime.now().isoformat()
                status["status"] = "syncing"
                with open(status_file, 'w') as f:
                    json.dump(status, f, indent=2)
            temp_nas_dir = f"{target_nas_dir}.tmp_{int(time.time())}"
            shutil.copytree(temp_dir, temp_nas_dir)
            if os.path.exists(target_nas_dir):
                backup_dir = f"{target_nas_dir}.backup_{int(time.time())}"
                os.rename(target_nas_dir, backup_dir)
                print(f"[NAS] Backed up existing directory to {backup_dir}")
            os.rename(temp_nas_dir, target_nas_dir)
            if not os.path.exists(target_nas_dir):
                raise NASError("Sync verification failed: target directory not found")
            final_status_file = os.path.join(target_nas_dir, ".sync_status.json")
            if os.path.exists(final_status_file):
                with open(final_status_file, 'r') as f:
                    status = json.load(f)
                status["sync_completed"] = datetime.now().isoformat()
                status["status"] = "completed"
                with open(final_status_file, 'w') as f:
                    json.dump(status, f, indent=2)
            print(f"[NAS] Successfully synced to {target_nas_dir}")
            if remove_temp:
                shutil.rmtree(temp_dir)
                print(f"[NAS] Cleaned up temp directory {temp_dir}")
            return target_nas_dir
        except Exception as e:
            if 'temp_nas_dir' in locals() and os.path.exists(temp_nas_dir):
                try:
                    shutil.rmtree(temp_nas_dir)
                except:
                    pass
            raise NASError(f"Sync failed: {e}")
    def validate_pre_scan(self):
        try:
            result = self._run_command(f"ping -c 3 -W 5 {self.nas_ip}", check=False)
            if result.returncode != 0:
                return False, f"NAS {self.nas_ip} is not reachable"
            if not self.ensure_nas_mounted():
                return False, "Failed to mount NAS"
            result = self._run_command(f"df -h {self.local_mount}")
            df_lines = result.stdout.strip().split('\n')
            if len(df_lines) >= 2:
                fields = df_lines[1].split()
                available = fields[3]
                if 'G' not in available and 'T' not in available:
                    return False, f"Insufficient space on NAS: {available} available"
            result = self._run_command(f"df -h {self.temp_base}")
            df_lines = result.stdout.strip().split('\n')
            if len(df_lines) >= 2:
                fields = df_lines[1].split()
                available = fields[3]
                if available.endswith('M') and int(available[:-1]) < 2000:
                    return False, f"Insufficient temp space: {available} available, need 2GB+"
            return True, "Pre-scan validation passed"
        except Exception as e:
            return False, f"Pre-scan validation failed: {e}"


def main():
    import sys
    nas = NASManager()
    if len(sys.argv) < 2:
        print("Usage: nas_utils.py [check|mount|validate|sync <temp_dir>]")
        sys.exit(1)
    command = sys.argv[1]
    try:
        if command == "check":
            mounted, message = nas.is_nas_mounted()
            print(f"NAS Status: {'Nas is Mounted' if mounted else 'Nas is not Mounted'} {message}")
            sys.exit(0 if mounted else 1)
        elif command == "mount":
            success = nas.ensure_nas_mounted()
            sys.exit(0 if success else 1)
        elif command == "validate":
            success, message = nas.validate_pre_scan()
            print(f"Validation: {'Validation passed' if success else 'Validation failed'} {message}")
            sys.exit(0 if success else 1)
        elif command == "sync" and len(sys.argv) >= 3:
            temp_dir = sys.argv[2]
            target = sys.argv[3] if len(sys.argv) >= 4 else None
            nas.sync_to_nas(temp_dir, target)
            print("Sync completed successfully")
            sys.exit(0)
        else:
            print("Invalid command or missing arguments")
            sys.exit(1)
    except NASError as e:
        print(f"NAS Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
