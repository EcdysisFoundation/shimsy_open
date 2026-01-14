import time
import logging
import signal
import sys
import os
from datetime import datetime
from nas_utils import NASManager, NASError


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('shimsy-nas-monitor')

class NASMonitor:
    def __init__(self):
        self.nas = NASManager()
        self.running = True
        self.check_interval = 60
        self.max_consecutive_failures = 5
        self.consecutive_failures = 0
        self.last_successful_check = datetime.now()
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    def check_and_mount(self):
        try:
            mounted, message = self.nas.is_nas_mounted()
            if mounted:
                self.consecutive_failures = 0
                self.last_successful_check = datetime.now()
                logger.debug(f"NAS check passed: {message}")
                return True
            else:
                self.consecutive_failures += 1
                logger.warning(f"NAS check failed (attempt {self.consecutive_failures}): {message}")
                try:
                    success = self.nas.ensure_nas_mounted()
                    if success:
                        logger.info("NAS successfully remounted")
                        self.consecutive_failures = 0
                        self.last_successful_check = datetime.now()
                        return True
                    else:
                        logger.error("Failed to remount NAS")
                        return False
                except NASError as e:
                    logger.error(f"NAS remount failed: {e}")
                    return False
        except Exception as e:
            self.consecutive_failures += 1
            logger.error(f"Unexpected error during NAS check: {e}")
            return False
    def run(self):
        logger.info("Starting NAS monitoring service...")
        logger.info(f"Check interval: {self.check_interval} seconds")
        logger.info(f"Max consecutive failures before alert: {self.max_consecutive_failures}")
        try:
            mounted, message = self.nas.is_nas_mounted()
            if not mounted:
                logger.warning(f"Initial NAS check failed: {message}")
                logger.info("Attempting initial mount...")
                self.nas.ensure_nas_mounted()
        except Exception as e:
            logger.error(f"Initial NAS setup failed: {e}")
        while self.running:
            try:
                success = self.check_and_mount()
                if (datetime.now().minute % 10 == 0 and datetime.now().second < 5) or \
                   (self.consecutive_failures == 1) or \
                   (success and self.consecutive_failures > 0):
                    if success:
                        logger.info(f"NAS monitoring (last check: {self.last_successful_check.strftime('%H:%M:%S')})")
                    else:
                        time_since_success = datetime.now() - self.last_successful_check
                        logger.warning(f"NAS monitoring Issues detected for {time_since_success}")
                if self.consecutive_failures >= self.max_consecutive_failures:
                    time_since_success = datetime.now() - self.last_successful_check
                    logger.error(
                        f"ALERT: NAS has been unavailable for {time_since_success} "
                        f"({self.consecutive_failures} consecutive failures)"
                    )
                    alert_file = "/home/ecdysis/shimsy/controller/nas_alert.flag"
                    try:
                        with open(alert_file, 'w') as f:
                            f.write(f"NAS_UNAVAILABLE_SINCE={self.last_successful_check.isoformat()}\n")
                            f.write(f"CONSECUTIVE_FAILURES={self.consecutive_failures}\n")
                            f.write(f"LAST_CHECK={datetime.now().isoformat()}\n")
                    except Exception as e:
                        logger.error(f"Failed to write alert file: {e}")
                else:
                    alert_file = "/home/ecdysis/shimsy/controller/nas_alert.flag"
                    if os.path.exists(alert_file):
                        try:
                            os.remove(alert_file)
                        except Exception:
                            pass
                for _ in range(self.check_interval):
                    if not self.running:
                        break
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Unexpected error in monitor loop: {e}")
                time.sleep(10)
        logger.info("NAS monitoring service stopped")

def main():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        monitor = NASMonitor()
        monitor.run()
    except KeyboardInterrupt:
        logger.info("Monitor interrupted by user")
    except Exception as e:
        logger.error(f"Monitor failed with unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
