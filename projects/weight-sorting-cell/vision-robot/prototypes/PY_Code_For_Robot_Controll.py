"""
Mirobot teaching program - run from VS Code.

Same moves as the program that works in WLKATA Studio, but it talks to the
robot directly over the USB/serial port with G-code, so it needs no WLKATA library.

1. pip install pyserial
2. CLOSE WLKATA Studio (or click Disconnect) so COM4 is free
3. Run this file in VS Code (Run > Run Without Debugging, or the play button)

"""


import time
import serial

PORT = "COM4"     # same COM port as in WLKATA Studio
BAUD = 115200
SPEED = 2000
REPEAT = 2


class Mirobot:
    def __init__(self, port, baud=BAUD):
        self.ser = serial.Serial(port, baud, timeout=0.2)
        time.sleep(2)                      # robot resets when the port opens
        self.ser.reset_input_buffer()

    def send(self, cmd, wait=True, timeout=60):
        print(">>", cmd)
        self.ser.write((cmd + "\r\n").encode())
        if wait:
            time.sleep(0.4)                # let the move start
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

    def go_to_axis(self, j1, j2, j3, j4, j5, j6, speed=SPEED):
        # M21 = joint mode, G90 = absolute, X..C = J1..J6 in degrees
        self.send(f"M21 G90 G00 X{j1} Y{j2} Z{j3} A{j4} B{j5} C{j6} F{speed}")

    def suction_cup_on(self):
        self.send("M3S1000", wait=False)

    def suction_cup_blow(self):
        self.send("M3S500", wait=False)

    def suction_cup_off(self):
        self.send("M3S0", wait=False)

    def close(self):
        self.suction_cup_off()
        self.ser.close()


def main():
    api = Mirobot(PORT)
    try:
        print("Homing...")
        api.home()

        for i in range(REPEAT):
            print(f"--- Cycle {i + 1}/{REPEAT} ---")

            # Step 1: pick position, suction ON
            api.go_to_axis(55, 40, 10, 0, -35, -45)
            api.suction_cup_on()
            time.sleep(1)

            # Step 2: zero pose, suction stays ON
            api.go_to_axis(0, 0, 0, 0, 0, 0)

            # Step 3: place position, release
            api.go_to_axis(-70, 50, 5, 0, -35, -45)
            api.suction_cup_off()
            time.sleep(1)

            # Step 4: zero pose, suction OFF
            api.go_to_axis(0, 0, 0, 0, 0, 0)
    finally:
        api.close()
        print("Done.")


if __name__ == "__main__":
    main()
