"""
Mirobot + Intel RealSense D455 : camera-guided pick and place (blue blocks).

The D455 finds a blue block and gives the PICK position.
The PLACE position is the SAME spot, but PLACE_UP_MM higher: the robot picks the
block up, lifts it, comes back down over the same spot and releases it a little
above where it was picked.

Close WLKATA Studio before running (COM4 must be free).

Install (Python 3.12 64-bit):
    py -3.12 -m pip install pyrealsense2 opencv-contrib-python numpy pyserial

Usage:
    py -3.12 d455_pick_place.py auto          # FULLY AUTOMATIC: self-calibrates (first time),
                                              #   then picks + places every blue block it sees
    py -3.12 d455_pick_place.py auto --recal  # same, but redo the automatic calibration
    py -3.12 d455_pick_place.py calibrate     # manual calibration (click + jog), optional
    py -3.12 d455_pick_place.py run           # detect + pick + place
    py -3.12 d455_pick_place.py run --dry     # same, but only PRINT robot commands (no robot)

Camera: fixed ~55-65 cm above the table, looking down at the work area.
"""
import json
import os
import re
import sys
import time
import warnings

# --- if VS Code started a Python without the camera library, switch to 3.12 64-bit
try:
    import pyrealsense2 as rs
    import serial
except ModuleNotFoundError:
    import subprocess
    if os.environ.get("D455_RELAUNCHED") != "1":
        print(f"Missing library in {sys.executable} - switching to Python 3.12 64-bit...")
        env = dict(os.environ, D455_RELAUNCHED="1")
        try:
            sys.exit(subprocess.call(["py", "-3.12", os.path.abspath(__file__), *sys.argv[1:]], env=env))
        except FileNotFoundError:
            pass
    raise SystemExit("Install with:  py -3.12 -m pip install pyrealsense2 opencv-contrib-python numpy pyserial")

import cv2
import numpy as np

# ---------------------------------------------------------------- settings ---
PORT = "COM4"               # used only if the robot's USB chip is not found below
ROBOT_USB_ID = "1A86:7523"  # CH340 in the Mirobot: found on whatever COM number Windows gives it
BAUD = 115200


def find_port(usb_id, fallback):
    """COM port of the USB device with this VID:PID (COM numbers change when re-plugged)."""
    import serial.tools.list_ports
    for p in serial.tools.list_ports.comports():
        if usb_id.upper() in (p.hwid or "").upper():
            return p.device
    return fallback
SPEED = 2000

HERE = os.path.dirname(os.path.abspath(__file__))
CALIB_FILE = os.path.join(HERE, "d455_calib.json")

PARK_JOINTS = (0, 0, 0, 0, 0, 0)    # arm waits here (out of the camera view) while it looks

APPROACH_HEIGHT = 40   # mm above the block top before going down / after lifting
PRESS_DEPTH = 2        # mm to push the suction cup into the block top
PLACE_UP_MM = 15       # used only when PLACE_MODE = "same_spot"
# "taught"    = every block goes to PLACE_JOINTS (your drop-off pose from the teaching program)
# "same_spot" = put the block back where it was, PLACE_UP_MM higher
PLACE_MODE = "taught"
PLACE_JOINTS = (-70, 37, 15, 0, -50, 0)    # exact drop-off from WLKATA Studio (MOVJ, speed 2000)

# Wait before picking: nothing may move in the camera view (e.g. your hand putting a
# block down) and the block must stay in the same place for STABLE_SEC seconds.
STABLE_SEC = 2.0
STABLE_MM = 5          # block may move less than this while waiting
MOTION_FRACTION = 0.003  # more than this share of changed pixels = something is moving

# PLC load cell (RS-485, D00400 - port/baud/station/empty threshold are in plc_cnet.py).
# The robot only picks when the load cell has been EMPTY for EMPTY_STABLE_SEC.
# After a place it waits until the load cell shows the block (or LOAD_WAIT_SEC passes).
USE_PLC = True               # False or "--no-plc" = pick without asking the PLC
EMPTY_STABLE_SEC = 1.0
LOAD_WAIT_SEC = 10.0
AUTO_LOWER_MM = 3            # no weight after a place -> next pick this much lower
AUTO_LOWER_MAX = 15          # ...but never more than this below TIP_VISIBLE_OFFSET

# HSV colour range for "blue"
BLUE_LO, BLUE_HI = (95, 120, 50), (130, 255, 255)
MIN_AREA_PX = 800

# Safety limits for targets (mm, robot frame)
REACH_MIN, REACH_MAX = 120, 270     # horizontal distance from robot base
Z_MAX = 250
MAX_RANGE_MM = 1500

# (depth w,h,fps), (color w,h,fps) - tried in order; the last ones also work on USB 2
MODES = [((848, 480, 30), (848, 480, 30)),
         ((640, 480, 15), (640, 480, 15)),
         ((480, 270, 15), (424, 240, 15))]


# ------------------------------------------------------------------- robot ---
class MoveError(RuntimeError):
    """The robot refused a move (position out of its reach)."""


class Mirobot:
    """Talks to the Mirobot with G-code over the serial port."""

    def __init__(self, port=None, baud=BAUD, dry=False):
        self.dry = dry
        if dry:
            print("DRY RUN: robot commands are only printed")
            return
        port = port or find_port(ROBOT_USB_ID, PORT)
        print(f"Robot on {port}")
        self.ser = serial.Serial(port, baud, timeout=0.2)
        time.sleep(2)                      # robot resets when the port opens
        self.ser.reset_input_buffer()

    def send(self, cmd, wait=True, timeout=60):
        print(">>", cmd)
        if self.dry:
            return
        self.ser.write((cmd + "\r\n").encode())
        if wait:
            time.sleep(0.4)                # let the move start before polling
            self.wait_idle(timeout)

    def status(self):
        if self.dry:
            return "<Idle>"
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

    def position(self):
        """Current tool position (x, y, z) in mm."""
        s = self.status()
        m = re.search(r"Cartesian coordinate\(XYZ RxRyRz\):([-\d.]+),([-\d.]+),([-\d.]+)", s)
        if not m:
            raise RuntimeError("Could not read robot position from: " + s)
        return np.array([float(v) for v in m.groups()])

    def home(self):
        self.send("$H", timeout=90)

    def move_joints(self, j):
        self.send(f"M21 G90 G00 X{j[0]} Y{j[1]} Z{j[2]} A{j[3]} B{j[4]} C{j[5]} F{SPEED}")

    def move_xyz(self, x, y, z):
        """Straight-line move, suction cup pointing down.
        The Mirobot silently stays where it is when a point is out of its reach
        ("Error,A102,Soft limit"), so check that it really got there."""
        self.send(f"M20 G90 G01 X{x:.2f} Y{y:.2f} Z{z:.2f} A0 B0 C0 F{SPEED}")
        if self.dry:
            return
        pos = self.position()
        if np.linalg.norm(pos - np.array([x, y, z])) > 5:
            raise MoveError(f"robot cannot reach X{x:.0f} Y{y:.0f} Z{z:.0f} "
                            f"(it stayed at X{pos[0]:.0f} Y{pos[1]:.0f} Z{pos[2]:.0f})")

    def jog(self, dx=0, dy=0, dz=0):
        self.send(f"M20 G91 G01 X{dx} Y{dy} Z{dz} F1000")

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


# ------------------------------------------------------------------ camera ---
# Close-range mode: shifts the D455 depth window closer, so tall objects / stacks
# near the camera are measured correctly. 0 = normal. 50 = about 20-70 cm.
DISPARITY_SHIFT = 50


def set_disparity_shift(shift):
    """Enable advanced mode once (camera reboots) and set the disparity shift."""
    def device():
        for _ in range(30):
            devs = rs.context().query_devices()
            if len(devs):
                return devs[0]
            time.sleep(1)
        raise SystemExit("D455 not found after reboot.")

    adv = rs.rs400_advanced_mode(device())
    if not adv.is_enabled():
        print("Enabling camera advanced mode (camera restarts once)...")
        adv.toggle_advanced_mode(True)
        time.sleep(6)
        adv = rs.rs400_advanced_mode(device())
    table = adv.get_depth_table()
    if table.disparityShift != shift:
        table.disparityShift = shift
        adv.set_depth_table(table)
        print(f"Close-range mode: disparity shift = {shift}")


class Camera:
    def __init__(self):
        set_disparity_shift(DISPARITY_SHIFT)
        for (dw, dh, df), (cw, ch, cf) in MODES:
            self.pipe, cfg = rs.pipeline(), rs.config()
            cfg.enable_stream(rs.stream.depth, dw, dh, rs.format.z16, df)
            cfg.enable_stream(rs.stream.color, cw, ch, rs.format.bgr8, cf)
            try:
                prof = self.pipe.start(cfg)
                print(f"Camera: depth {dw}x{dh}, color {cw}x{ch} @ {df} fps")
                break
            except RuntimeError:
                continue
        else:
            raise SystemExit("Could not start the D455. Is it plugged in?")
        self.scale_mm = prof.get_device().first_depth_sensor().get_depth_scale() * 1000.0
        self.intr = prof.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
        self.align = rs.align(rs.stream.color)
        self.spatial, self.temporal = rs.spatial_filter(), rs.temporal_filter()
        for _ in range(30):
            self.pipe.wait_for_frames(5000)

    def grab(self):
        """Color BGR image, depth in mm (float32, NaN = no data)."""
        while True:
            fs = self.align.process(self.pipe.wait_for_frames(5000))
            d, c = fs.get_depth_frame(), fs.get_color_frame()
            if d and c:
                break
        d = self.temporal.process(self.spatial.process(d))
        depth = np.asanyarray(d.get_data()).astype(np.float32) * self.scale_mm
        depth[depth == 0] = np.nan
        return np.asanyarray(c.get_data()).copy(), depth

    def grab_avg(self, n=10):
        imgs, depths = zip(*(self.grab() for _ in range(n)))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return imgs[-1], np.nanmedian(np.stack(depths), axis=0)

    def flush(self, n=10):
        for _ in range(n):
            self.pipe.wait_for_frames(5000)

    def stop(self):
        self.pipe.stop()


# ---------------------------------------------------------------- geometry ---
def deproject(depth, intr):
    h, w = depth.shape
    u, v = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return np.dstack([(u - intr.ppx) / intr.fx * depth, (v - intr.ppy) / intr.fy * depth, depth])


def fit_table(depth, intr, iters=300, thr=4.0):
    """RANSAC plane of the table: n.p + d = height above table (mm). Returns (n, d)."""
    pts = deproject(depth, intr).reshape(-1, 3)
    pts = pts[np.isfinite(pts[:, 2]) & (pts[:, 2] < MAX_RANGE_MM)]
    if len(pts) < 500:
        return None
    rng = np.random.default_rng(0)
    s = pts[rng.choice(len(pts), min(len(pts), 8000), replace=False)]
    best, best_cnt = None, 0
    for _ in range(iters):
        a, b, c = s[rng.choice(len(s), 3, replace=False)]
        n = np.cross(b - a, c - a)
        nn = np.linalg.norm(n)
        if nn < 1e-6:
            continue
        n /= nn
        d = -n @ a
        cnt = np.count_nonzero(np.abs(s @ n + d) < thr)
        if cnt > best_cnt:
            best, best_cnt = (n, d), cnt
    n, d = best
    inl = s[np.abs(s @ n + d) < thr]
    c = inl.mean(axis=0)
    n = np.linalg.svd(inl - c)[2][2]
    d = -n @ c
    return (-n, -d) if d < 0 else (n, d)


def pixel_point(depth, intr, table, u, v, r=4):
    """3D camera point (mm) under pixel (u, v): from depth, or where the pixel ray hits the table."""
    patch = depth[max(v - r, 0):v + r + 1, max(u - r, 0):u + r + 1]
    patch = patch[np.isfinite(patch)]
    ray = np.array([(u - intr.ppx) / intr.fx, (v - intr.ppy) / intr.fy, 1.0])
    if patch.size:
        p = ray * float(np.median(patch))
        if table is None or -5 < table[0] @ p + table[1] < 200:   # plausible: on/above table
            return p
    if table is not None:
        n, d = table
        return ray * (-d / (n @ ray))
    return None


# ------------------------------------------------------- camera -> robot -----
def fit_transform(cam_pts, rob_pts):
    """Rigid transform so rob = R @ cam + t."""
    P, Q = np.asarray(cam_pts), np.asarray(rob_pts)
    pc, qc = P.mean(0), Q.mean(0)
    U, _, Vt = np.linalg.svd((P - pc).T @ (Q - qc))
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1] *= -1
        R = Vt.T @ U.T
    t = qc - R @ pc
    err = np.linalg.norm((P @ R.T + t) - Q, axis=1)
    return R, t, err


def load_calib():
    if not os.path.exists(CALIB_FILE):
        raise SystemExit(f"No calibration yet. Run first:  py -3.12 {os.path.basename(__file__)} calibrate")
    with open(CALIB_FILE) as f:
        c = json.load(f)
    return np.array(c["R"]), np.array(c["t"]), c.get("z_table")


# ---------------------------------------------------------------- detection ---
def find_blue_blocks(img, depth, intr, table):
    """Blue blocks with a valid top-face 3D point. Returns list of dicts."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, BLUE_LO, BLUE_HI)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    P = deproject(depth, intr)
    H = P @ table[0] + table[1] if table is not None else None
    blocks = []
    for c in cnts:
        if cv2.contourArea(c) < MIN_AREA_PX:
            continue
        blob = np.zeros(mask.shape, np.uint8)
        cv2.drawContours(blob, [c], -1, 255, -1)
        blob = cv2.erode(blob, k)                   # stay away from the block edges
        sel = (blob > 0) & np.isfinite(depth)
        b = {"contour": c, "rect": cv2.minAreaRect(c), "p_cam": None, "height": None}
        if H is not None and sel.sum() > 30:
            h = H[sel]
            top_h = float(np.percentile(h, 97))     # HIGHEST level (top of the tallest pile)
            if 3 < top_h < 200:                     # real block height above the table
                top = (sel & (np.abs(H - top_h) < 8)).astype(np.uint8)
                # touching piles merge into one blue area: keep only the largest
                # connected piece of the highest top face
                top = cv2.morphologyEx(top, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
                n, lab, stats, _ = cv2.connectedComponentsWithStats(top)
                if n > 1:
                    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
                    face = lab == i
                    if face.sum() > 15:
                        height = float(np.median(H[face]))
                        # Centre = middle of the rectangle around the top face (not the
                        # average of the depth pixels, which shifts when some are missing),
                        # projected onto the top-face plane at that height.
                        rect = cv2.minAreaRect(cv2.findNonZero(face.astype(np.uint8)))
                        u, v = rect[0]
                        ray = np.array([(u - intr.ppx) / intr.fx, (v - intr.ppy) / intr.fy, 1.0])
                        n_vec, d0 = table
                        b["p_cam"] = ray * ((height - d0) / (n_vec @ ray))
                        b["height"] = height
                        b["rect"] = rect
        blocks.append(b)
    # tallest first: never reach past a tall pile to get a low block
    blocks.sort(key=lambda b: -(b["height"] or -1))
    return blocks


def target_ok(p, z_min):
    reach = float(np.hypot(p[0], p[1]))
    return REACH_MIN <= reach <= REACH_MAX and z_min <= p[2] <= Z_MAX


def text(img, s, org, color=(255, 255, 255), scale=0.5):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1)


# --------------------------------------------------------------- calibrate ---
def calibrate(dry=False):
    print("""
CALIBRATION  (teaches the program where the camera is relative to the robot)
  1. Put a small flat marker (coin / sticker) on the table.
  2. CLICK the marker centre in the camera window.
  3. Jog the robot until the suction cup tip just touches the marker:
        w/s = +X/-X   a/d = +Y/-Y   r/f = up/down     1/2/3 = step 1/5/20 mm
  4. Press SPACE to save the point pair. Lift (r), move the marker, repeat.
  5. After at least 4 points spread over the work area press ENTER to save.
     (6-8 points, some on top of a block for height, gives the best result.)
  q = quit without saving
""")
    robot, cam = Mirobot(dry=dry), Camera()
    robot.home()
    _, depth = cam.grab_avg(10)
    table = fit_table(depth, cam.intr)
    clicked, cam_pts, rob_pts, step = {}, [], [], 5

    def on_click(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN:
            clicked["uv"] = (x, y)

    win = "calibrate"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_click)
    keys = {ord("w"): (1, 0, 0), ord("s"): (-1, 0, 0), ord("a"): (0, 1, 0),
            ord("d"): (0, -1, 0), ord("r"): (0, 0, 1), ord("f"): (0, 0, -1)}
    try:
        while True:
            img, depth = cam.grab()
            view = img.copy()
            if "uv" in clicked:
                cv2.drawMarker(view, clicked["uv"], (0, 0, 255), cv2.MARKER_CROSS, 25, 2)
            text(view, f"points: {len(cam_pts)}   step: {step} mm", (10, 25), (0, 255, 0), 0.7)
            cv2.imshow(win, view)
            k = cv2.waitKey(1) & 0xFF
            if k in keys:
                robot.jog(*(step * np.array(keys[k])))
            elif k in (ord("1"), ord("2"), ord("3")):
                step = {ord("1"): 1, ord("2"): 5, ord("3"): 20}[k]
            elif k == ord(" "):
                if "uv" not in clicked:
                    print("Click the marker in the image first.")
                    continue
                p = pixel_point(depth, cam.intr, table, *clicked["uv"])
                if p is None:
                    print("No depth there - click again.")
                    continue
                cam_pts.append(p)
                rob_pts.append(robot.position() if not dry else np.zeros(3))
                print(f"Point {len(cam_pts)}: camera {cam_pts[-1].round(1)}  robot {rob_pts[-1].round(1)}")
                clicked.clear()
            elif k == 13:
                if len(cam_pts) < 4:
                    print("Need at least 4 points.")
                    continue
                R, t, err = fit_transform(cam_pts, rob_pts)
                print(f"Error per point (mm): {err.round(1)}   mean {err.mean():.1f}")
                with open(CALIB_FILE, "w") as f:
                    json.dump({"R": R.tolist(), "t": t.tolist(),
                               "z_table": float(min(p[2] for p in rob_pts))}, f, indent=2)
                print(f"Saved {CALIB_FILE}. If mean error > 5 mm, redo with more points.")
                break
            elif k == ord("q"):
                break
    finally:
        robot.move_joints(PARK_JOINTS)
        robot.close()
        cam.stop()
        cv2.destroyAllWindows()


# ------------------------------------------------------ auto calibration ---
# Fully automatic - no block, no clicking:
#   the arm moves its suction cup to the points below (robot mm); in the colour image
#   the camera finds the WHITE suction cup on the ORANGE arm end. Robot 3D points +
#   cup pixels -> solvePnP gives where the camera is -> camera->robot transform.
#   (The arm is too close to the camera for depth, so only the colour image is used.)
# Points over the work plate: around J1 = 55 deg (direction of your taught pick pose),
# given as (angle deg, radius mm) and converted to X/Y below.
_POLAR = [(55, 210), (40, 180), (40, 240), (70, 180), (70, 240), (55, 170), (55, 250), (48, 210),
          (35, 210), (62, 200), (47, 150), (65, 150)]
AUTOCAL_XY = [(round(r * np.cos(np.radians(a))), round(r * np.sin(np.radians(a)))) for a, r in _POLAR]
# suction tip heights: the low layer is near block height, so picks are not extrapolated.
# The plate MUST be empty during calibration (checked automatically).
AUTOCAL_Z = [150, 105, 65]
ORANGE_LO, ORANGE_HI = (5, 120, 120), (22, 255, 255)   # HSV: orange arm end
WHITE_LO, WHITE_HI = (0, 0, 170), (180, 70, 255)        # HSV: white suction cup top
CUP_DISC_HEIGHT = 25           # mm: first guess; the real height is corrected below
# Height reference: at your taught pick pose the suction tip rests on top of a block.
TAUGHT_PICK_JOINTS = (55, 40, 10, 0, -35, -45)   # from PY_Code_For_Robot_Controll.py
REF_BLOCK_HEIGHT = 33          # mm: height of the block picked at that pose
MAX_POINT_ERR_MM = 10          # calibration points worse than this are dropped
TIP_VISIBLE_OFFSET = -25       # mm: extra pick-Z correction (0, -5 and -15 stopped above the blocks)
                               #   (raise if it presses too hard, lower if it stops above the block)
                               #   Live in the camera window: [ = 2 mm lower, ] = 2 mm higher


def show(win, view, msg, color=(0, 255, 255)):
    text(view, msg, (10, 25), color, 0.6)
    cv2.imshow(win, view)
    cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)
    return cv2.waitKey(1) & 0xFF


def find_cup_pixel(img):
    """Pixel (u, v) of the white suction cup top on the orange arm end, or None."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    k5 = np.ones((5, 5), np.uint8)
    orange = cv2.morphologyEx(cv2.inRange(hsv, ORANGE_LO, ORANGE_HI), cv2.MORPH_OPEN, k5)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(orange)
    if n < 2:
        return None, None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[i, cv2.CC_STAT_AREA] < 1500:
        return None, None
    arm = (lab == i).astype(np.uint8) * 255
    hull = cv2.convexHull(cv2.findNonZero(arm))
    region = np.zeros_like(arm)
    cv2.fillConvexPoly(region, hull, 255)
    region = cv2.dilate(region, np.ones((21, 21), np.uint8))   # cup may stick out a little
    white = cv2.inRange(hsv, WHITE_LO, WHITE_HI) & region & ~arm
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, cents = cv2.connectedComponentsWithStats(white)
    best = None
    for j in range(1, n):
        a = stats[j, cv2.CC_STAT_AREA]
        w, h = stats[j, cv2.CC_STAT_WIDTH], stats[j, cv2.CC_STAT_HEIGHT]
        roundness = min(w, h) / max(w, h)
        if 60 <= a <= 5000 and roundness > 0.5:                 # roughly round blob
            if best is None or a > best[0]:
                best = (a, cents[j])
    if best is None:
        return None, arm
    return (float(best[1][0]), float(best[1][1])), arm


def solve_pnp(rob_pts, img_pts, intr):
    """Camera pose from robot points + pixels. Drops bad points, refits.
    Returns R, t (robot = R @ camera + t) and the error per kept point in mm."""
    obj = np.array(rob_pts, np.float64)
    imgp = np.array(img_pts, np.float64)
    K = np.array([[intr.fx, 0, intr.ppx], [0, intr.fy, intr.ppy], [0, 0, 1]])
    dist = np.array(intr.coeffs[:5], np.float64)
    # RANSAC: robust against wrong detections (another white spot taken for the cup)
    ok, rvec, tvec, inl = cv2.solvePnPRansac(obj, imgp, K, dist, reprojectionError=6.0,
                                             iterationsCount=3000, confidence=0.999)
    if not ok or inl is None or len(inl) < 6:
        raise SystemExit("Calibration failed - too few consistent points.")
    keep = np.zeros(len(obj), bool)
    keep[inl.ravel()] = True
    # refine on the good points only
    ok, rvec, tvec = cv2.solvePnP(obj[keep], imgp[keep], K, dist, rvec, tvec,
                                  useExtrinsicGuess=True, flags=cv2.SOLVEPNP_ITERATIVE)
    Rc, tc = cv2.Rodrigues(rvec)[0], tvec.reshape(3)              # camera = Rc @ robot + tc
    proj, _ = cv2.projectPoints(obj, rvec, tvec, K, dist)
    err_px = np.linalg.norm(proj.reshape(-1, 2) - imgp, axis=1)
    err = err_px * (obj @ Rc.T + tc)[:, 2] / intr.fx             # pixel error -> approx. mm
    zs = obj[:, 2]
    print(f"  kept {keep.sum()}/{len(obj)} points; per height: "
          + ", ".join(f"{z - CUP_DISC_HEIGHT:.0f}mm: {int((keep & (zs == z)).sum())}"
                      for z in sorted(set(zs), reverse=True)))
    return Rc.T, -Rc.T @ tc, err[keep]


def calib_table(R, t, z_table):
    """Plate plane (camera frame) from the calibration: robot Z = z_table.
    Better than fit_table() when blocks cover most of the plate - then the
    largest flat surface the camera sees can be the desk, not the plate."""
    return R[2, :].copy(), float(t[2] - z_table)


def table_z_robot(table, R, t):
    """Robot Z of the table point under the image centre."""
    n, d = table
    ray = np.array([0.0, 0.0, 1.0])
    return float((R @ (ray * (-d / (n @ ray))) + t)[2])


def autocal(robot, cam, win):
    print("AUTO CALIBRATION")
    _, depth = cam.grab_avg(10)
    table = fit_table(depth, cam.intr)
    if table is None:
        raise SystemExit("Camera has no depth of the table - mount it ~55-65 cm above the table.")
    img0, d0 = cam.grab_avg(5)
    if any(b["height"] for b in find_blue_blocks(img0, d0, cam.intr, table)):
        raise SystemExit("Blocks on the plate - remove all blocks before calibrating "
                         "(the arm goes down close to the plate).")

    # move the suction cup around, find it in the colour image
    img_pts, rob_pts = [], []
    total = len(AUTOCAL_XY) * len(AUTOCAL_Z)
    for z in AUTOCAL_Z:
        for x, y in AUTOCAL_XY:
            robot.move_xyz(x, y, z)
            time.sleep(0.8)                         # let the arm settle
            for _ in range(3):
                cam.grab()                          # drop frames taken while moving
            img, _ = cam.grab()
            uv, arm = find_cup_pixel(img)
            view = img.copy()
            if arm is not None:
                view[arm > 0] = (0.5 * view[arm > 0] + (0, 90, 0)).astype(np.uint8)
            if uv is None:
                print(f"  ({x},{y},{z}): suction cup not found - skipped")
                k = show(win, view, f"({x},{y},{z}) cup not found", (0, 0, 255))
            else:
                img_pts.append(uv)
                rob_pts.append([x, y, z + CUP_DISC_HEIGHT])   # the white top, not the tip
                cv2.drawMarker(view, tuple(int(c) for c in uv), (0, 0, 255), cv2.MARKER_CROSS, 25, 2)
                print(f"  point {len(img_pts)}: robot ({x},{y},{z})  pixel ({uv[0]:.0f},{uv[1]:.0f})")
                k = show(win, view, f"point {len(img_pts)}/{total}")
            if k == ord("q"):
                raise SystemExit("Calibration cancelled.")

    if len(img_pts) < 6:
        raise SystemExit(f"Suction cup found at only {len(img_pts)} points (need 6+). "
                         "Check that the camera sees the robot's working area.")
    R, t, err = solve_pnp(rob_pts, img_pts, cam.intr)
    print(f"Calibration error per point (mm): {err.round(1)}   mean {err.mean():.1f}")
    if err.mean() > 15:
        raise SystemExit("Calibration error too large (> 15 mm) - not saved.")

    # height fix: table Z from the taught pick pose (tip on top of a REF_BLOCK_HEIGHT block)
    robot.move_joints(TAUGHT_PICK_JOINTS)
    time.sleep(0.5)
    z_ref_table = float(robot.position()[2]) - REF_BLOCK_HEIGHT
    robot.move_joints(PARK_JOINTS)
    t = t + np.array([0.0, 0.0, z_ref_table - table_z_robot(table, R, t)])
    print(f"Height reference: table at robot Z {z_ref_table:.1f} mm")

    z_table = table_z_robot(table, R, t)
    with open(CALIB_FILE, "w") as f:
        json.dump({"R": R.tolist(), "t": t.tolist(), "z_table": z_table,
                   "mean_error_mm": float(err.mean()), "auto": True}, f, indent=2)
    print(f"Saved {CALIB_FILE}  (table at robot Z {z_table:.0f} mm)")
    robot.move_joints(PARK_JOINTS)
    return R, t, z_table


# ----------------------------------------------------------- pick & place ---
def pick_and_place(robot, p):
    """Pick at p (robot mm) and place it. Returns False if the robot cannot reach the block."""
    x, y, z = p
    print(f"PICK  at X{x:.1f} Y{y:.1f} Z{z:.1f}")
    try:
        robot.move_xyz(x, y, z + APPROACH_HEIGHT)    # above the block
        robot.suction_on()
        robot.move_xyz(x, y, z - PRESS_DEPTH)        # down onto the block
        time.sleep(1.0)                              # let the vacuum build up
        robot.move_xyz(x, y, z + APPROACH_HEIGHT)    # lift
    except MoveError as e:
        print(f"SKIP: {e}")
        robot.pump_off()
        robot.move_joints(PARK_JOINTS)
        return False
    time.sleep(0.3)
    if PLACE_MODE == "taught":
        print(f"PLACE at taught drop-off joints {PLACE_JOINTS}")
        robot.move_joints(PARK_JOINTS)               # same path as your teaching program
        robot.move_joints(PLACE_JOINTS)
        robot.blow()                                 # release
        time.sleep(0.5)
        robot.pump_off()
        robot.move_joints(PARK_JOINTS)
        return True
    print(f"PLACE at X{x:.1f} Y{y:.1f} Z{z + PLACE_UP_MM:.1f}  (same spot, {PLACE_UP_MM} mm up)")
    robot.move_xyz(x, y, z + PLACE_UP_MM)            # back down, a little above the pick height
    robot.blow()                                     # release
    time.sleep(0.5)
    robot.pump_off()
    robot.move_xyz(x, y, z + APPROACH_HEIGHT)        # move up and away
    robot.move_joints(PARK_JOINTS)                   # out of the camera view
    return True


# --------------------------------------------------------------------- run ---
def run(dry=False, auto_start=False, recal=False, use_plc=USE_PLC):
    print(f"""
RUN   (PLACE = {"taught drop-off " + str(PLACE_JOINTS) if PLACE_MODE == "taught" else f"same spot, {PLACE_UP_MM} mm higher"})
  a = auto mode on/off (picks every block once)
  g = pick the selected block now     n = select the next block
  c = clear the 'done' list (pick all blocks again)
  [ = pick 2 mm lower     ] = pick 2 mm higher
  q = quit
  Green = can pick.  Grey = already done.  Orange = no depth on block.  Red = out of reach.
""")
    win = "D455 pick & place  (a = auto, g = pick, n = next, c = clear, q = quit)"
    plc = None
    if use_plc:
        import plc_cnet
        plc = plc_cnet.LoadCellMonitor()
        plc.start()
        print(f"PLC: reading {plc_cnet.WEIGHT_DEVICE} on {plc_cnet.PLC_PORT}")
    robot, cam = Mirobot(dry=dry), Camera()
    robot.home()
    if recal or not os.path.exists(CALIB_FILE):
        try:
            R, t, z_table = autocal(robot, cam, win)
        except BaseException:          # cancelled / failed: pump off, park, release everything
            robot.pump_off()
            robot.move_joints(PARK_JOINTS)
            robot.close()
            cam.stop()
            cv2.destroyAllWindows()
            if plc:
                plc.stop()
            raise
    else:
        R, t, z_table = load_calib()
    z_min = (z_table - 5) if z_table is not None else 0
    with open(CALIB_FILE) as f:
        z_offset = TIP_VISIBLE_OFFSET if json.load(f).get("auto") else 0.0   # only for auto calibration
    robot.move_joints(PARK_JOINTS)
    if z_table is not None:
        table = calib_table(R, t, z_table)          # plate from the calibration (fixed)
    else:
        _, depth = cam.grab_avg(10)
        table = fit_table(depth, cam.intr)
    auto, sel_idx, frame_no = auto_start, 0, 0
    done = []          # robot X/Y of blocks already picked & placed
    no_reach = []      # robot X/Y of blocks the robot refused to go to ('c' clears)
    prev_gray, last_motion = None, time.time()
    stable_pos, stable_since = None, time.time()
    empty_since = None          # load cell empty since (time) - None = not empty
    placed_at = None            # time of the last place, while waiting to see the block on the load cell

    def to_robot(b):
        return R @ b["p_cam"] + t + np.array([0.0, 0.0, z_offset])

    def precise(near):
        """Average several frames and re-measure the block closest to 'near'."""
        img2, depth2 = cam.grab_avg(8)
        best = None
        for b in find_blue_blocks(img2, depth2, cam.intr, table):
            if b["p_cam"] is not None:
                p = to_robot(b)
                dist = np.linalg.norm(p - near)
                if dist < 20 and (best is None or dist < best[0]):
                    best = (dist, p)
        return None if best is None else best[1]

    try:
        while True:
            img, depth = cam.grab()
            frame_no += 1
            gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
            if prev_gray is not None and (cv2.absdiff(gray, prev_gray) > 25).mean() > MOTION_FRACTION:
                last_motion = time.time()               # hand / block moving in view
            prev_gray = gray
            if z_table is None and frame_no % 10 == 0:
                table = fit_table(depth, cam.intr) or table
            blocks = find_blue_blocks(img, depth, cam.intr, table)
            view = img.copy()
            pickable = []
            for b in blocks:
                if b["p_cam"] is None:
                    col, label = (0, 200, 255), "no depth"
                else:
                    b["p_rob"] = to_robot(b)
                    ok = target_ok(b["p_rob"], z_min)
                    x, y, z = b["p_rob"]
                    col = (0, 255, 0) if ok else (0, 0, 255)
                    label = f"X{x:.0f} Y{y:.0f} Z{z:.0f} h{b['height']:.0f}" + ("" if ok else " OUT OF REACH")
                    # same X/Y AND same height = the block already handled
                    # (a block lower in the same pile has the same X/Y but is lower)
                    # Only needed when blocks are put back in place ("same_spot"). In
                    # "taught" mode a picked block leaves the plate, so a block seen at
                    # that spot later is a NEW block and must be picked.
                    is_done = PLACE_MODE == "same_spot" and any(
                        np.hypot(x - dx, y - dy) < 25 and abs(z - dz) < 15 for dx, dy, dz in done)
                    if ok and any(np.hypot(x - nx, y - ny) < 25 for nx, ny in no_reach):
                        col, label = (0, 0, 255), label + " CAN'T REACH"
                    elif ok and is_done:
                        col, label = (160, 160, 160), label + " done"
                    elif ok:
                        pickable.append(b)
                b["col"], b["label"] = col, label
            if pickable:
                sel_idx %= len(pickable)
            target = pickable[sel_idx] if pickable else None

            # is the target block lying still, with nothing moving in view?
            now = time.time()
            if target is not None and stable_pos is not None \
                    and np.linalg.norm(target["p_rob"] - stable_pos) < STABLE_MM:
                pass                                    # same block, same place: keep timing
            else:
                stable_pos = None if target is None else target["p_rob"].copy()
                stable_since = now
            quiet = now - last_motion
            still = now - stable_since
            ready = target is not None and quiet >= STABLE_SEC and still >= STABLE_SEC

            # load cell (PLC D00400): pick only when it is empty
            lc_ok, lc_msg = True, ""
            if plc is not None:
                if plc.empty:
                    empty_since = empty_since or now
                else:
                    empty_since = None
                if placed_at is not None:               # just placed: wait until the PLC sees it
                    if plc.loaded:
                        print(f"Load cell: block arrived, {plc.weight:g} g   "
                              f"(pick offset {z_offset:+.0f} mm)")
                        placed_at, empty_since = None, None
                    elif now - placed_at > LOAD_WAIT_SEC:
                        print("WARNING: no weight on the load cell after the place "
                              "(block not lifted or dropped?)")
                        placed_at, empty_since = None, None
                        # most likely the cup stopped above the block: try a little lower
                        if z_offset - AUTO_LOWER_MM >= TIP_VISIBLE_OFFSET - AUTO_LOWER_MAX:
                            z_offset -= AUTO_LOWER_MM
                            print(f"  -> next pick {AUTO_LOWER_MM} mm lower "
                                  f"(offset {z_offset:+.0f} mm)")
                        else:
                            print("  -> already at the lowest allowed pick height: "
                                  "check suction cup / pump / block surface")
                if not plc.ok:
                    lc_ok, lc_msg = False, "WAIT: no PLC data (" + plc.error[:40] + ")"
                elif placed_at is not None:
                    lc_ok, lc_msg = False, "WAIT: block going onto load cell"
                elif empty_since is None:
                    lc_ok, lc_msg = False, f"WAIT: load cell not empty ({plc.weight:g})"
                elif now - empty_since < EMPTY_STABLE_SEC:
                    lc_ok, lc_msg = False, "WAIT: load cell empty, confirming"
            ready = ready and lc_ok

            if target is None:
                status = "no block to pick"
            elif not lc_ok:
                status = lc_msg
            elif quiet < STABLE_SEC:
                status = "WAIT: movement in view (hand?)"
            elif not ready:
                status = f"WAIT: block still {min(quiet, still):.1f}/{STABLE_SEC:.0f}s"
            else:
                status = "READY"
            text(view, status, (5, 20), (0, 255, 0) if ready else (0, 200, 255), 0.6)

            for b in blocks:
                thick = 4 if b is target else 2
                cv2.drawContours(view, [cv2.boxPoints(b["rect"]).astype(np.int32)], -1, b["col"], thick)
                cx, cy = map(int, b["rect"][0])
                cv2.circle(view, (cx, cy), 4, (0, 0, 255), -1)
                text(view, ("> " if b is target else "") + b["label"], (max(cx - 90, 2), cy + 20))
            lc_txt = ""
            if plc is not None:
                lc_txt = ("   LOAD CELL: --" if plc.weight is None or not plc.ok
                          else f"   LOAD CELL: {plc.weight:g}" + (" EMPTY" if plc.empty else ""))
            text(view, f"blocks: {len(blocks)}  pickable: {len(pickable)}" + lc_txt
                       + f"   Z{z_offset:+.0f}"
                       + ("   AUTO" if auto else "") + ("   DRY RUN" if dry else ""),
                 (5, view.shape[0] - 10), (0, 255, 255))
            cv2.imshow(win, view)
            k = cv2.waitKey(1) & 0xFF
            if k == ord("q") or cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
            if k == ord("a"):
                auto = not auto
            if k == ord("n"):
                sel_idx += 1
            if k == ord("c"):
                done.clear()
                no_reach.clear()
            if k in (ord("["), ord("]")):
                z_offset += -2 if k == ord("[") else 2
                print(f"Pick height offset: {z_offset:+.0f} mm  "
                      f"(set TIP_VISIBLE_OFFSET = {z_offset:.0f} to keep it)")
            if target is not None and ((k == ord("g") and lc_ok) or (auto and ready)):
                p = precise(target["p_rob"])         # averaged re-measure for an exact centre
                if p is None or not target_ok(p, z_min):
                    stable_since = time.time()       # lost it / moved: wait again
                    continue
                if pick_and_place(robot, p):
                    done.append(tuple(p))
                    placed_at, empty_since = time.time(), None
                else:
                    no_reach.append((p[0], p[1]))    # skip this block, take the next one
                cam.flush()                          # old frames still show the arm
                prev_gray, last_motion = None, time.time()   # wait again before the next pick
                stable_pos = None
    finally:
        robot.move_joints(PARK_JOINTS)
        robot.close()
        cam.stop()
        cv2.destroyAllWindows()
        if plc:
            plc.stop()


class _Tee:
    """Print to the screen AND to run_log.txt (so a run can be checked afterwards)."""

    def __init__(self, path):
        self.f, self.out = open(path, "a", encoding="utf-8", buffering=1), sys.stdout

    def write(self, s):
        self.out.write(s)
        self.f.write(s)

    def flush(self):
        self.out.flush()
        self.f.flush()


if __name__ == "__main__":
    sys.stdout = _Tee(os.path.join(HERE, "run_log.txt"))
    print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')}  {' '.join(sys.argv[1:])} =====")
    # no argument (e.g. the VS Code Run button) = AUTO mode
    mode = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "auto"
    print(f"Mode: {mode}")
    dry = "--dry" in sys.argv
    use_plc = USE_PLC and "--no-plc" not in sys.argv
    if mode == "calibrate":
        calibrate(dry)
    elif mode == "run":
        run(dry, use_plc=use_plc)
    elif mode == "autocal":        # only the automatic calibration, then park
        robot, cam = Mirobot(dry=dry), Camera()
        try:
            robot.home()
            autocal(robot, cam, "D455 auto calibration (q = quit)")
        finally:
            robot.pump_off()
            robot.move_joints(PARK_JOINTS)
            robot.close()
            cam.stop()
            cv2.destroyAllWindows()
    elif mode == "auto":           # fully automatic: self-calibrate if needed, then pick everything
        run(dry, auto_start=True, recal="--recal" in sys.argv, use_plc=use_plc)
    else:
        print(__doc__)
