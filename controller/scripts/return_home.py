
import json
import time
from gpiozero import DigitalOutputDevice


STEP_X = DigitalOutputDevice(17)
DIR_X  = DigitalOutputDevice(27)

STEP_Y = DigitalOutputDevice(22)
DIR_Y  = DigitalOutputDevice(23)

STEP_Z = DigitalOutputDevice(24)
DIR_Z  = DigitalOutputDevice(25)

ENA    = DigitalOutputDevice(5)


DELAY = 0.0005
POSITION_FILE = "/home/ecdysis/shimsy/controller/last_position.json"

def move_steps(dir_pin, step_pin, steps, direction=True):
    dir_pin.value = direction
    for _ in range(steps):
        step_pin.on()
        time.sleep(DELAY)
        step_pin.off()
        time.sleep(DELAY)

def main():
    try:
        with open(POSITION_FILE, "r") as f:
            pos = json.load(f)
            x = pos.get("x", 0)
            y = pos.get("y", 0)
            z = pos.get("z", 0)
    except Exception:
        print("[WARNING] Could not read last_position.json. Assuming (0,0,0).")
        x, y, z = 0, 0, 0

    print(f"[INFO] Returning to origin from x={x}, y={y}, z={z}")

    ENA.off()

    if x != 0:
        move_steps(DIR_X, STEP_X, abs(x), direction=(x < 0))
    if y != 0:
        move_steps(DIR_Y, STEP_Y, abs(y), direction=(y < 0))
    if z != 0:
        move_steps(DIR_Z, STEP_Z, abs(z), direction=(z < 0))

    print("[INFO] Returned to origin (0, 0, 0)")

    ENA.on()

if __name__ == "__main__":
    main()
