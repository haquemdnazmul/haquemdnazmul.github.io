"""
Load cell test: when the load cell (PLC D00400) is EMPTY, the robot picks the block
at the taught pick pose and puts it on the load cell. No camera needed.

Cycle:
  1. wait until the load cell is empty for EMPTY_STABLE_SEC
  2. pick the block at PICK_JOINTS (suction on)
  3. place it on the load cell at PLACE_JOINTS (release)
  4. wait until the load cell shows the block, print the weight
  5. you take the block off the load cell and put a new block on the pick spot -> back to 1

Close WLKATA Studio first (COM4 must be free).

Usage:
    py -3.12 load_cell_pick_test.py            # robot + PLC
    py -3.12 load_cell_pick_test.py --dry      # PLC only, robot commands are only printed
    py -3.12 load_cell_pick_test.py --once     # one cycle, then stop
Ctrl+C = stop (pump off, robot goes to zero pose).
"""
import sys
import time

import serial

import plc_cnet

# ---------------------------------------------------------------- settings ---
ROBOT_PORT = "COM4"
ROBOT_BAUD = 115200
SPEED = 2000

PICK_JOINTS = (55, 40, 10, 0, -35, -45)    # block pick spot (from the teaching program)
PLACE_JOINTS = (-70, 37, 15, 0, -50, 0)    # over the load cell (drop-off pose)
SAFE_JOINTS = (0, 0, 0, 0, 0, 0)           # travel / wait pose

EMPTY_STABLE_SEC = 1.0    # load cell must stay empty this long before the robot picks
LOAD_WAIT_SEC = 10.0      # after placing: the block must show on the load cell within this time
SUCTION_SEC = 1.0         # time to build up vacuum at the pick spot


# ------------------------------------------------------------------- robot ---
class Mirobot:
    def __init__(self, dry=False):
        self.dry = dry
        if dry:
            print("DRY RUN: robot commands are only printed")
            return
        port = plc_cnet.find_port("1A86:7523", ROBOT_PORT)    # robot's CH340, any COM number
        print(f"Robot on {port}")
        self.ser = serial.Serial(port, ROBOT_BAUD, timeout=0.2)
        time.sleep(2)                      # robot resets when the port opens
        self.ser.reset_input_buffer()

    def send(self, cmd, wait=True, timeout=60):
        print("   >>", cmd)
        if self.dry:
            time.sleep(0.3 if wait else 0)
            return
        self.ser.write((cmd + "\r\n").encode())
        if wait:
            time.sleep(0.4)
            self.wait_idle(timeout)

    def status(self):
        self.ser.reset_input_buffer()
        self.ser.write(b"?\r\n")
        end = time.time() + 2
        while time.time() < end:
            line = self.ser.readline().decode(errors="ignore").strip()
            if line.startswith("<"):
                return line
        return ""

    def wait_idle(self, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            s = self.status()
            if "Idle" in s:
                return
            if "Alarm" in s:
                raise RuntimeError("Robot is in ALARM state: " + s)
            time.sleep(0.2)
        raise TimeoutError("Robot did not finish the move")

    def home(self):
        self.send("$H", timeout=90)

    def joints(self, j):
        self.send(f"M21 G90 G00 X{j[0]} Y{j[1]} Z{j[2]} A{j[3]} B{j[4]} C{j[5]} F{SPEED}")

    def suction_on(self):
        self.send("M3S1000", wait=False)

    def blow(self):
        self.send("M3S500", wait=False)

    def pump_off(self):
        self.send("M3S0", wait=False)

    def close(self):
        self.pump_off()
        if not self.dry:
            self.ser.close()


# --------------------------------------------------------------- load cell ---
def read_weight(plc):
    n = 2 if plc_cnet.WEIGHT_DWORD else 1
    return plc_cnet.to_weight(plc.read_words(plc_cnet.WEIGHT_DEVICE, n))


def wait_empty(plc):
    """Block until the load cell has been empty for EMPTY_STABLE_SEC."""
    since, last_print = None, 0
    while True:
        try:
            w = read_weight(plc)
        except Exception as e:
            print("   PLC error:", e)
            since = None
            time.sleep(0.5)
            continue
        now = time.time()
        if w < plc_cnet.EMPTY_BELOW:
            since = since or now
            if now - since >= EMPTY_STABLE_SEC:
                print(f"   load cell EMPTY ({w:g} g)")
                return
        else:
            since = None
            if now - last_print > 2:
                print(f"   waiting: load cell has {w:g} g - take the block off")
                last_print = now
        time.sleep(0.2)


def wait_loaded(plc):
    """After placing: wait until the weight is stable on the load cell. Returns grams or None."""
    end, prev, same = time.time() + LOAD_WAIT_SEC, None, 0
    while time.time() < end:
        try:
            w = read_weight(plc)
        except Exception as e:
            print("   PLC error:", e)
            time.sleep(0.3)
            continue
        if w >= plc_cnet.EMPTY_BELOW:
            same = same + 1 if prev is not None and abs(w - prev) <= 1 else 0
            if same >= 3:                    # 4 reads in a row within 1 g = settled
                return w
        prev = w
        time.sleep(0.2)
    return None


# -------------------------------------------------------------------- main ---
def main():
    dry, once = "--dry" in sys.argv, "--once" in sys.argv
    plc = plc_cnet.XGTCnet(plc_cnet.PLC_PORT)
    print(f"PLC: {plc_cnet.WEIGHT_DEVICE} on {plc_cnet.PLC_PORT} = {read_weight(plc):g} g")
    robot = Mirobot(dry)
    cycle = 0
    try:
        print("Homing...")
        robot.home()
        robot.joints(SAFE_JOINTS)
        while True:
            cycle += 1
            print(f"\n--- cycle {cycle}: waiting for an empty load cell ---")
            wait_empty(plc)

            print("PICK")
            robot.joints(PICK_JOINTS)
            robot.suction_on()
            time.sleep(SUCTION_SEC)
            robot.joints(SAFE_JOINTS)

            print("PLACE on load cell")
            robot.joints(PLACE_JOINTS)
            robot.blow()
            time.sleep(0.5)
            robot.pump_off()
            robot.joints(SAFE_JOINTS)

            w = wait_loaded(plc)
            if w is None:
                print(f"STOP: no weight on the load cell after {LOAD_WAIT_SEC:.0f} s "
                      "(block not picked / dropped?)")
                break
            print(f"WEIGHT on load cell: {w:g} g")
            if once:
                break
            print("Take the block off the load cell and put the next block on the pick spot.")
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        robot.pump_off()
        try:
            robot.joints(SAFE_JOINTS)
        finally:
            robot.close()
            plc.close()
        print("Done.")


if __name__ == "__main__":
    main()
