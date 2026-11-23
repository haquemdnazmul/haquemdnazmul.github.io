"""
LS XGB PLC (XBM-DN32H2) over RS-485 - reads the load cell weight from D00400.

Protocol: LS "XGT Cnet dedicated protocol" (XGT server) on the CPU's built-in RS-485 port.

PLC side (XG5000, once):
    Project tree > Parameter > Basic parameter / Built-in Cnet  (XBM: "Internal Cnet")
      Channel 2 (RS-485):  Type = XGT server (dedicated)   Station = PLC_STATION below
                           Speed = PLC_BAUD below, 8 data bits, no parity, 1 stop bit
    Download the parameters and switch the PLC STOP -> RUN.

Wiring (USB-RS485 adapter -> PLC built-in RS-485 terminal):
    adapter A / D+ / 485+  ->  PLC 485+
    adapter B / D- / 485-  ->  PLC 485-
    adapter GND            ->  PLC SG / 0 V (recommended)

Test on its own (no robot, no camera):
    py -3.12 plc_cnet.py               # uses PLC_PORT below, prints D00400 every 0.5 s
    py -3.12 plc_cnet.py COM5          # other port
    py -3.12 plc_cnet.py scan          # tries every port / baud / station until the PLC answers
"""
import sys
import threading
import time

import serial
import serial.tools.list_ports

# ---------------------------------------------------------------- settings ---
PLC_PORT = "COM5"        # used only if the adapter's USB chip is not found below
PLC_USB_ID = "1A86:55D8" # CH9101 USB-RS485 adapter: found on whatever COM number Windows gives it
PLC_BAUD = 9600
PLC_STATION = 0          # Cnet station number set in XG5000 (found by scan: 0)

WEIGHT_DEVICE = "D00400"
WEIGHT_DWORD = False     # False: only the 16-bit word D00400 (up to 32767 g).
                         # True: D00400 + D00401 as one 32-bit value. Not usable now: the PLC
                         # program keeps another value in D00401 (read 6 on 2026-11-20).
WEIGHT_SIGNED = True
WEIGHT_SCALE = 1.0       # multiply the raw value by this (e.g. 0.1 if the PLC stores 0.1 g units)
EMPTY_BELOW = 5          # value (after scale) below this = load cell is EMPTY

ENQ, EOT, ACK, NAK, ETX = b"\x05", b"\x04", b"\x06", b"\x15", b"\x03"


def find_port(usb_id, fallback):
    """COM port of the USB device with this VID:PID (COM numbers change when re-plugged)."""
    for p in serial.tools.list_ports.comports():
        if usb_id.upper() in (p.hwid or "").upper():
            return p.device
    return fallback


class PLCNoAnswer(RuntimeError):
    """Port works but the PLC sent nothing back (not a reason to reopen the port)."""


class XGTCnet:
    """Minimal XGT Cnet client: continuous word read (RSB)."""

    def __init__(self, port=PLC_PORT, baud=PLC_BAUD, station=PLC_STATION, timeout=0.5):
        self.station = station
        self.port, self.baud, self.timeout = port, baud, timeout
        self.ser = None
        self.reopen()

    def reopen(self):
        """(Re)open the port - needed after the USB adapter dropped out
        (Windows then refuses every write: 'WriteFile failed, PermissionError 13').
        With the default port, the adapter is looked up by its USB ID each time, so it
        is found again even if Windows gives it a new COM number."""
        self.close()
        port = self.port
        if port == PLC_PORT:
            port = find_port(PLC_USB_ID, PLC_PORT)
        self.ser = serial.Serial(port, self.baud, bytesize=8, parity="N", stopbits=1,
                                 timeout=self.timeout)

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    @staticmethod
    def _word_name(device):
        """'D00400' -> '%DW400' (XGB D area is word addressed)."""
        area, num = device[0].upper(), int(device[1:])
        return f"%{area}W{num}"

    def read_words(self, device, count=1):
        name = self._word_name(device)
        body = f"{self.station:02X}RSB{len(name):02X}{name}{count:02X}".encode()
        self.ser.reset_input_buffer()
        self.ser.write(ENQ + body + EOT)
        resp = self.ser.read_until(ETX, 256)
        if not resp:
            raise PLCNoAnswer("PLC did not answer (check port, baud, station, A/B wiring)")
        if resp[:1] == NAK:
            code = resp[6:10].decode(errors="ignore")
            raise RuntimeError(f"PLC replied NAK, error code {code} (resp {resp!r})")
        if resp[:1] != ACK or not resp.endswith(ETX):
            raise RuntimeError(f"Bad reply from PLC: {resp!r}")
        # ACK st(2) 'R' 'SB' blocks(2) bytes(2) data ETX
        txt = resp[1:-1].decode()
        nbytes = int(txt[7:9], 16)
        data = txt[9:9 + nbytes * 2]
        return [int(data[i:i + 4], 16) for i in range(0, len(data), 4)]


def to_weight(words):
    if WEIGHT_DWORD:
        raw = (words[1] << 16) | words[0]          # low word = D00400, high word = D00401
        if WEIGHT_SIGNED and raw >= 0x80000000:
            raw -= 0x100000000
    else:
        raw = words[0]
        if WEIGHT_SIGNED and raw >= 0x8000:
            raw -= 0x10000
    return raw * WEIGHT_SCALE


class LoadCellMonitor(threading.Thread):
    """Reads the weight in the background so the camera loop never waits for RS-485.

    .weight  latest value (None until the first good read)
    .ok      True if the last read worked
    .empty   True if the load cell is empty AND the reading is fresh
    """

    def __init__(self, port=PLC_PORT, period=0.2):
        super().__init__(daemon=True)
        try:
            self.plc = XGTCnet(port)
        except (serial.SerialException, OSError) as e:
            # adapter not plugged in yet: start anyway, run() keeps trying to open it
            print(f"PLC: cannot open {port} yet ({e}) - will keep trying")
            self.plc = XGTCnet.__new__(XGTCnet)
            self.plc.station, self.plc.port = PLC_STATION, port
            self.plc.baud, self.plc.timeout, self.plc.ser = PLC_BAUD, 0.5, None
        self.period = period
        self.weight, self.ok, self.error, self.stamp = None, False, "", 0.0
        self._halt = threading.Event()     # (not "_stop": Thread uses that name itself)

    def run(self):
        n = 2 if WEIGHT_DWORD else 1
        while not self._halt.is_set():
            try:
                if self.plc.ser is None:
                    self.plc.reopen()
                    print("PLC: COM port reopened")
                self.weight = to_weight(self.plc.read_words(WEIGHT_DEVICE, n))
                self.ok, self.error, self.stamp = True, "", time.time()
            except (serial.SerialException, OSError) as e:
                # port itself is broken (USB adapter reset / unplugged): close it,
                # the next loop reopens it as soon as Windows has the port back
                self.plc.close()
                if self.ok or not self.error.startswith("port lost"):   # say it once, not every second
                    print("PLC: port lost -", e, "- reconnecting...")
                self.ok, self.error = False, "port lost, reconnecting (USB-RS485 adapter plugged in?)"
                self._halt.wait(1.0)
                continue
            except Exception as e:  # keep running; the robot simply waits
                self.fails = getattr(self, "fails", 0) + 1
                if self.fails < 3:      # one cut-off reply (e.g. PC busy starting the camera): just retry
                    self._halt.wait(0.05)
                    continue
                if self.ok or self.error != str(e):
                    print("PLC:", e)
                self.ok, self.error = False, str(e)
                self._halt.wait(self.period)
                continue
            self.fails = 0
            self._halt.wait(self.period)

    @property
    def empty(self):
        fresh = self.ok and time.time() - self.stamp < 2.0
        return fresh and self.weight is not None and self.weight < EMPTY_BELOW

    @property
    def loaded(self):
        """True only for a fresh reading WITH weight (no data is not 'loaded')."""
        fresh = self.ok and time.time() - self.stamp < 2.0
        return fresh and self.weight is not None and self.weight >= EMPTY_BELOW

    def stop(self):
        self._halt.set()
        self.join(2)
        self.plc.close()


# -------------------------------------------------------------------- test ---
def scan():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    print("Ports:", ports)
    for port in ports:
        for baud in (9600, 19200, 38400, 57600, 115200):
            for st in (0, 1):
                try:
                    c = XGTCnet(port, baud, st, timeout=0.3)
                except serial.SerialException as e:
                    print(f"{port}: cannot open ({e})")
                    break
                try:
                    w = c.read_words(WEIGHT_DEVICE, 2)
                    print(f"FOUND: {port} {baud} baud station {st}  D00400/1 = {w}")
                    return
                except Exception:
                    pass
                finally:
                    c.close()
            else:
                continue
            break
    print("No PLC found. Check wiring (swap A/B), XG5000 Cnet channel 2 = XGT server, PLC in RUN.")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else PLC_PORT
    if arg == "scan":
        return scan()
    plc = XGTCnet(arg)
    print(f"Reading {WEIGHT_DEVICE} on {arg} @ {PLC_BAUD} baud, station {PLC_STATION}  (Ctrl+C to stop)")
    try:
        while True:
            try:
                w = plc.read_words(WEIGHT_DEVICE, 2)
                wt = to_weight(w)
                print(f"D00400={w[0]:5d}  D00401={w[1]:5d}  ->  weight {wt:g}  "
                      f"{'EMPTY' if wt < EMPTY_BELOW else 'LOADED'}")
            except Exception as e:
                print("error:", e)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        plc.close()


if __name__ == "__main__":
    main()
