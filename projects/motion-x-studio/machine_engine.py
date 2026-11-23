"""The weight-sorting machine for the studio: camera + PLC load cell + robot.

Same behaviour as d455_pick_place.py run() (tested on the machine), but it runs in a
background thread, sends its camera picture and status to the studio instead of an
OpenCV window, takes commands (start/stop/auto/pick/calibrate), and LEARNS the pick
height per stack layer (studio_learning.json) instead of one fixed offset.
"""
import json
import os
import queue
import re
import threading
import time
from collections import deque

import cv2
import numpy as np

import config
import sim3d

config.add_robot_path()
import d455_pick_place as d  # noqa: E402  (robot, camera, detection, calibration)

# calibration file in the robot data folder (in the exe the module itself is in a temp folder)
d.CALIB_FILE = os.path.join(config.ROBOT_DIR, "d455_calib.json")

_ANGLES = re.compile(r"Angle\(ABCDXYZ\):([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)")
_JOINTS = re.compile(r"M21 G90 G0[01] X([-\d.]+) Y([-\d.]+) Z([-\d.]+) A([-\d.]+) B([-\d.]+) C([-\d.]+)")
_CART = re.compile(r"M20 G90 G0[01] X([-\d.]+) Y([-\d.]+) Z([-\d.]+)")


class TwinMirobot(d.Mirobot):
    """The normal robot driver, plus: tells the 3D simulator what the robot does.

    Real robot: every status reply carries the joint angles -> the simulator shows them.
    Dry run: no robot answers, so each command is turned into joint angles and animated.
    """

    def __init__(self, twin, dry=False):
        self.twin = twin
        self._last_plan = np.zeros(6)
        super().__init__(dry=dry)

    def send(self, cmd, wait=True, timeout=60):
        tw = self.twin
        if cmd.startswith("M3S"):                       # suction pump
            on = cmd.strip() == "M3S1000"
            if self.dry:
                tw.planned_vacuum(on)                   # switch when the animation gets there
            else:
                tw.set_vacuum(on)                       # real robot: already there (send waits)
        q = None                                        # joints this command ends at
        if cmd.startswith("$H"):
            q = np.zeros(6)
        elif (m := _JOINTS.match(cmd)):
            q = np.array([float(v) for v in m.groups()])
        elif (m := _CART.match(cmd)):
            q = sim3d.ik([float(v) for v in m.groups()], self._last_plan)
        if q is not None:
            self._last_plan = q
            if self.dry:
                tw.planned(q)                           # animate it
            else:
                tw.commanded = q                        # real robot: limit for the smooth prediction
        super().send(cmd, wait, timeout)

    def status(self):
        s = super().status()
        m = _ANGLES.search(s or "")
        if m:
            a = [float(v) for v in m.groups()]          # A B C D X Y Z = J4 J5 J6 rail J1 J2 J3
            self.twin.measured([a[4], a[5], a[6], a[0], a[1], a[2]], moving="Idle" not in s)
        return s


def plate_from_calib():
    """(x, y, z) of the plate under the camera centre, robot frame mm - or None."""
    try:
        R, t, z_table = d.load_calib()
    except (SystemExit, Exception):
        return None
    if z_table is None:
        return None
    n, d0 = d.calib_table(R, t, z_table)
    ray = np.array([0.0, 0.0, 1.0])
    c = R @ (ray * (-d0 / (n @ ray))) + t
    return float(c[0]), float(c[1]), float(z_table)


# --------------------------------------------------------------- block tracking ---
class BlockTracker:
    """Keeps each detected block from frame to frame and smooths its measurements, so boxes,
    numbers and the 3D view do not flicker from camera noise. Small changes (noise) are
    damped strongly, real movement (a block moved by hand) is followed quickly.
    The pick itself still re-measures the block precisely (averaged frames) before going down."""

    MATCH_MM = 25          # same block if its top moved less than this between frames
    KEEP_FRAMES = 6        # forget a block not seen for this many frames

    def __init__(self):
        self.tracks = []

    @staticmethod
    def _blend(old, new, small):
        """Noise (change below 'small') -> slow; real movement -> fast."""
        old, new = np.asarray(old, float), np.asarray(new, float)
        a = 0.07 if np.linalg.norm(new - old) < small else 0.6
        return old + a * (new - old)

    @staticmethod
    def _rect(rect):
        (cx, cy), (w, h), ang = rect
        if ang > 45:                                   # same box, one angle convention
            ang, w, h = ang - 90, h, w
        return np.array([cx, cy, w, h, ang], float)

    def update(self, blocks):
        for tr in self.tracks:
            tr["seen"] = False
        for b in blocks:
            if b["p_cam"] is None:
                continue
            best = None
            for tr in self.tracks:
                dist = np.linalg.norm(tr["p"] - b["p_cam"])
                if not tr["seen"] and dist < self.MATCH_MM and (best is None or dist < best[0]):
                    best = (dist, tr)
            r = self._rect(b["rect"])
            if best is None:
                tr = dict(p=np.array(b["p_cam"], float), h=float(b["height"]), r=r, miss=0, seen=True)
                self.tracks.append(tr)
            else:
                tr = best[1]
                tr["p"] = self._blend(tr["p"], b["p_cam"], 6.0)
                tr["h"] = float(self._blend([tr["h"]], [b["height"]], 6.0)[0])
                rr = r.copy()
                if abs(rr[4] - tr["r"][4]) > 45:       # angle wrapped: keep the old convention
                    rr[4] += 90 if rr[4] < tr["r"][4] else -90
                    rr[2], rr[3] = rr[3], rr[2]
                tr["r"] = self._blend(tr["r"], rr, 6.0)
                tr["miss"], tr["seen"] = 0, True
            b["p_cam"], b["height"] = tr["p"].copy(), tr["h"]
            cx, cy, w, h, ang = tr["r"]
            b["rect"] = ((float(cx), float(cy)), (float(w), float(h)), float(ang))
        for tr in self.tracks:
            if not tr["seen"]:
                tr["miss"] += 1
        self.tracks = [tr for tr in self.tracks if tr["miss"] <= self.KEEP_FRAMES]


# ------------------------------------------------------------ height learning ---
class HeightLearner:
    """Pick-height offset per stack layer (1 block high, 2 blocks high, ...).

    A success (block arrived on the load cell) keeps the offset; a failure (no weight)
    lowers that layer's offset by AUTO_LOWER_MM, never more than AUTO_LOWER_MAX below the
    default. Saved to disk, so the machine starts with what it learned last time.
    """
    LAYER_MM = 32           # one block

    VERSION = 2            # 2 = per-layer CORRECTION on top of the pick model (starts at 0)

    def __init__(self, path=config.LEARN_FILE):
        self.path = path
        model = config.load_config().get("pick_model")
        self.default = 0.0 if model else float(d.TIP_VISIBLE_OFFSET)
        self.data = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.data = json.load(f)
            except (OSError, ValueError):
                self.data = {}
        if model and self.data.get("_version") != self.VERSION:
            # old file: whole offsets (-25..-31 mm) - meaningless as corrections, start again at 0
            keep = {k: v for k, v in self.data.items() if k.startswith("_")}
            self.data = dict(keep, _version=self.VERSION)
            if os.path.exists(path):
                self.save()

    def layer(self, height):
        return max(1, int(round((height or self.LAYER_MM) / self.LAYER_MM)))

    def _row(self, height):
        key = str(self.layer(height))
        return self.data.setdefault(key, {"offset": self.default, "ok": 0, "fail": 0,
                                          "updated": ""})

    def offset(self, height):
        return float(self.data.get(str(self.layer(height)), {}).get("offset", self.default))

    UP_MM = 1.0            # after a success: try this much higher next time (do not squash the cup)
    UP_LIMIT = 6.0         # ...but never more than this above the default
    fixed = {}             # layer -> taught pick Z (not learned), set by the machine from the settings

    def record(self, height, success):
        row = self._row(height)
        row["ok" if success else "fail"] += 1
        if self.layer(height) in self.fixed:   # taught height: only count, never change it
            row["updated"] = time.strftime("%Y-%m-%d %H:%M")
            self.save()
            return ""
        msg = ""
        if success and row["offset"] + self.UP_MM <= self.default + self.UP_LIMIT:
            # learning works both ways: a pick that worked is tried 1 mm higher next time, so the
            # height settles at the shallowest pick that still holds the block (no over-pressing)
            row["offset"] += self.UP_MM
            msg = f"layer {self.layer(height)}: worked - next pick {self.UP_MM:g} mm higher ({row['offset']:+.0f} mm)"
        if not success:
            low = self.default - d.AUTO_LOWER_MAX
            if row["offset"] - d.AUTO_LOWER_MM >= low:
                row["offset"] -= d.AUTO_LOWER_MM
                msg = f"layer {self.layer(height)}: next pick {d.AUTO_LOWER_MM} mm lower ({row['offset']:+.0f} mm)"
            else:
                msg = (f"layer {self.layer(height)}: already lowest allowed - check suction cup, "
                       "pump and block surface")
        row["updated"] = time.strftime("%Y-%m-%d %H:%M")
        self.save()
        return msg

    def reset(self):
        self.data = {}
        self.save()

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def rows(self):
        out = []
        for k in sorted((k for k in self.data if k.isdigit()), key=int):   # layers only ("_..." = other)
            r = self.data[k]
            n = r["ok"] + r["fail"]
            out.append(dict(layer=int(k), height=int(k) * self.LAYER_MM, offset=r["offset"],
                            ok=r["ok"], fail=r["fail"], taught=self.fixed.get(int(k)),
                            rate=(100 * r["ok"] / n) if n else 0.0, updated=r["updated"]))
        for k, z in self.fixed.items():          # taught layers not picked yet
            if str(k) not in self.data:
                out.append(dict(layer=k, height=k * self.LAYER_MM, offset=0.0, ok=0, fail=0, taught=z,
                                rate=0.0, updated=""))
        return sorted(out, key=lambda r: r["layer"])


# ------------------------------------------------------------------ machine ---
class Machine(threading.Thread):
    """Runs until stop(). Read .status / .frame() from the GUI; send commands with .cmd()."""

    def __init__(self, log, dry=False, use_plc=True, auto=True):
        super().__init__(daemon=True)
        self.log, self.dry, self.use_plc = log, dry, use_plc
        self.q = queue.Queue()
        self.learner = HeightLearner()
        self._frame, self._lock = None, threading.Lock()
        self.status = dict(state="starting", text="Connecting...", auto=auto, weight=None,
                           plc_ok=False, plc_empty=False, plc_error="", blocks=0, pickable=0,
                           ok=0, fail=0, skipped=0, calib_error=None, calib_date="", can_return=False,
                           returned=0)
        self.last_pick = None             # (robot xyz where the cup picked, block height) of the last block
        self.weights = deque(maxlen=50)   # (time, grams)
        self._cancel_cal = False
        self.twin = sim3d.Twin(place_joints=d.PLACE_JOINTS)   # what the 3D simulator shows
        self.tracker = BlockTracker()                         # smooths detections between frames
        self.scene = dict(plate=None, blocks=[])              # robot-frame mm, for the simulator

    # ---- GUI side
    def cmd(self, name):
        if name == "cancel_calibration":
            self._cancel_cal = True
        self.q.put(name)

    def stop(self):
        self.q.put("stop")

    def frame(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    frame_no = 0                          # counts published camera pictures (GUI redraws on change)

    def _publish(self, view):
        with self._lock:
            self._frame = view
            self.frame_no += 1

    # ---- thread
    def run(self):
        plc = robot = cam = None
        st = self.status
        try:
            if self.use_plc:
                import plc_cnet
                plc = plc_cnet.LoadCellMonitor()
                plc.start()
                self.log(f"PLC: reading {plc_cnet.WEIGHT_DEVICE} on {plc_cnet.PLC_PORT}")
            st["text"] = "Connecting robot..."
            robot = TwinMirobot(self.twin, dry=self.dry)
            st["text"] = "Starting camera..."
            cam = d.Camera()
            st["text"] = "Homing robot..."
            robot.home()
            robot.move_joints(d.PARK_JOINTS)
            self._loop(robot, cam, plc)
        except BaseException as e:            # SystemExit from the robot code included
            st["state"] = "error"
            st["text"] = f"ERROR: {e}"
            self.log(f"ERROR: {e}")
        finally:
            for step in (lambda: robot and robot.pump_off(),
                         lambda: robot and robot.move_joints(d.PARK_JOINTS),
                         lambda: robot and robot.close(),
                         lambda: cam and cam.stop(),
                         lambda: plc and plc.stop()):
                try:
                    step()
                except Exception as e:
                    self.log(f"shutdown: {e}")
            if st["state"] != "error":
                st["state"], st["text"] = "stopped", "Stopped"
            self.log("Machine stopped (pump off, robot parked)")

    def _load_calib(self):
        if not os.path.exists(d.CALIB_FILE):
            return None
        R, t, z_table = d.load_calib()
        with open(d.CALIB_FILE) as f:
            c = json.load(f)
        self.status["calib_error"] = c.get("mean_error_mm")
        self.status["calib_date"] = time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(d.CALIB_FILE)))
        return R, t, z_table, bool(c.get("auto"))

    def _calibrate(self, robot, cam):
        """d455_pick_place.autocal, with its pictures sent to the studio."""
        st = self.status
        st["state"], st["text"] = "calibrating", "Calibrating - keep hands out of the robot area"
        self._cancel_cal = False
        self.log("Auto calibration started")

        def show(win, view, msg, color=(0, 255, 255)):
            d.text(view, msg, (10, 25), color, 0.6)
            self._publish(view)
            st["text"] = "Calibrating: " + msg
            while not self.q.empty():              # handle stop / cancel during calibration
                c = self.q.get()
                if c in ("stop", "cancel_calibration"):
                    self._cancel_cal = True
                    if c == "stop":
                        self.q.put("stop")
            return ord("q") if self._cancel_cal else -1

        old = d.show
        d.show = show
        try:
            d.autocal(robot, cam, "studio")
            self.log("Calibration saved")
            return True
        except BaseException as e:
            self.log(f"Calibration not saved: {e}")
            st["text"] = f"Calibration not saved: {e}"
            robot.pump_off()
            robot.move_joints(d.PARK_JOINTS)
            return False
        finally:
            d.show = old
            st["state"] = "running"

    def _return_block(self, robot, plc):
        """Take the block off the load cell and put it back where it was picked."""
        st = self.status
        if self.last_pick is None:
            self.log("Return block: no block picked in this session - nothing to return")
            return False
        if plc is not None and plc.ok and plc.empty and not self.dry:
            self.log("Return block: the load cell is empty - nothing to return")
            return False
        cfg = config.load_config()
        press = float(cfg.get("return_press_mm", 4))
        x, y, z = self.last_pick[0]
        # where to set it down: measured NOW by the camera (plate, or a block still on that spot)
        z_put = self._put_down_z(x, y, fallback=z)
        # flange position at the drop-off pose, in robot coordinates (same kinematics as the simulator)
        sx, sy, sz = sim3d.tool_point(d.PLACE_JOINTS) - [0, 0, sim3d.ROBOT_Z_SHIFT]
        st["text"] = f"RETURNING block to X{x:.0f} Y{y:.0f}"
        self.log(f"Return block: from the load cell back to X{x:.1f} Y{y:.1f} (set down at Z{z_put:.1f})")
        try:
            rest = plc.weight if (plc is not None and plc.ok) else None   # block weight, robot away
            self._touch_z = None
            robot.move_joints(d.PARK_JOINTS)
            robot.move_joints(d.PLACE_JOINTS)                    # over the block on the load cell
            touch = None
            if plc is not None and plc.ok and not self.dry:
                touch = self._touch_down(robot, plc, sx, sy, sz, cfg, rest)   # find the block top by weight
            if touch is None:                                    # no load cell feedback: fixed press
                touch = sz - press
                robot.move_xyz(sx, sy, touch)
            robot.suction_on()
            time.sleep(1.0)                                      # let the vacuum build up
            robot.move_xyz(sx, sy, sz + d.APPROACH_HEIGHT)       # lift it off
            if plc is not None and plc.ok and not self.dry:     # (dry run: nothing really moves)
                time.sleep(1.5)                                  # let the load cell settle
                if not plc.empty:
                    robot.pump_off()
                    robot.move_joints(d.PARK_JOINTS)
                    self.log(f"Return block: the block did not come off the load cell ({plc.weight:g} g). "
                             "Increase 'return_seal_mm' in studio_config.json (cup must press to seal).")
                    return False
            if self._touch_z is not None:                        # worked: next time go straight there
                self.learner.data["_load_cell_touch_z"] = round(float(self._touch_z), 1)
                self.learner.save()
            robot.move_joints(d.PARK_JOINTS)
            top = max(z_put, z)
            robot.move_xyz(x, y, top + d.APPROACH_HEIGHT)        # above its old spot
            robot.move_xyz(x, y, z_put)                          # block just above the surface there
            robot.blow()
            time.sleep(0.5)
            robot.pump_off()
            robot.move_xyz(x, y, top + d.APPROACH_HEIGHT)
            robot.move_joints(d.PARK_JOINTS)
        except d.MoveError as e:
            robot.pump_off()
            robot.move_joints(d.PARK_JOINTS)
            self.log(f"Return block stopped: {e}")
            return False
        self.last_pick = None
        st["can_return"] = False
        st["returned"] += 1
        self.log("Return block: done - the block is back in its place (auto is off)")
        return True

    def _touch_down(self, robot, plc, sx, sy, sz, cfg, rest_weight=None):
        """Come down onto the block on the load cell in 1 mm steps and stop as soon as the
        load cell feels the cup (weight rises). Returns the robot Z of the touch, or None."""
        step = 1.0
        rise = float(cfg.get("return_touch_g", 3))               # grams that mean "the cup touches"
        above = float(cfg.get("return_start_mm", 8))             # start this far above the drop-off pose
        deepest = sz - float(cfg.get("return_max_press_mm", 10))

        def fresh_weight():
            t0 = time.time()
            while time.time() - t0 < 2.0:                        # a reading taken after the move
                if plc.stamp > t0 + 0.05 and plc.ok:
                    return plc.weight
                time.sleep(0.03)
            return None

        known = self.learner.data.get("_load_cell_touch_z")      # where the cup felt the block last time
        if known is not None and deepest + 3 <= known <= sz + above:
            z = float(known) + 2.0                               # one normal move to just above it
            self.log(f"Return block: block was felt at Z{known:.1f} last time - going straight to Z{z:.1f}")
        else:
            z = sz + above
        robot.move_xyz(sx, sy, z)
        time.sleep(0.4)
        readings = [w for w in (fresh_weight(), fresh_weight()) if w is not None]
        if not readings:
            return None
        base = float(np.median(readings))
        if rest_weight is not None:                              # weight before the robot came: the
            base = min(base, float(rest_weight))                 # cup may already touch at the start
        self.log(f"Return block: block on the load cell weighs {base:.0f} g - coming down until the cup touches")
        seal = float(cfg.get("return_seal_mm", 3))               # press after touching: the cup must seal
        while z - step >= deepest:
            z -= step
            robot.move_xyz(sx, sy, z)
            w = fresh_weight()
            if w is None:
                return None
            if w - base < rise:
                time.sleep(0.15)                                 # load cell reading lags: go slowly
                continue
            w2 = fresh_weight()                                  # confirm: a 2nd reading must agree
            if w2 is None or w2 - base < rise:
                continue
            felt = max(w, w2) - base
            # already pressing firmly (reading came late): the cup is sealed, do not press more
            zs = z if felt >= 20 else max(z - seal, deepest)
            self._touch_z = z                                    # remembered after a successful return
            self.log(f"Return block: cup touches the block at Z{z:.1f} (+{felt:.0f} g) - "
                     f"pressing {z - zs:.0f} mm more to seal the suction cup")
            robot.suction_on()                                   # suck while pressing, like a normal pick
            robot.move_xyz(sx, sy, zs)                           # gentle press so the cup seals
            return zs
        self.log(f"Return block: no touch felt down to Z{deepest:.1f} - picking there")
        return z

    def _surface_height(self, x, y):
        """Height (mm above the plate) of whatever is at robot (x, y) in the latest camera
        depth picture - the plate (0) or a block standing there. None if it cannot be measured."""
        geo, depth, intr = getattr(self, "_geo", None), getattr(self, "_depth", None), getattr(self, "_intr", None)
        if geo is None or depth is None or intr is None:
            return None
        R, t, z_table, table, _ = geo
        pc = R.T @ (np.array([x, y, z_table]) - t)                # camera point under the spot
        if pc[2] <= 0:
            return None
        u = int(round(intr.fx * pc[0] / pc[2] + intr.ppx))
        v = int(round(intr.fy * pc[1] / pc[2] + intr.ppy))
        h, w = depth.shape
        r = 7
        if not (r <= u < w - r and r <= v < h - r):
            return None
        patch = depth[v - r:v + r + 1, u - r:u + r + 1]
        patch = patch[np.isfinite(patch)]
        if patch.size < 20:
            return None
        ray = np.array([(u - intr.ppx) / intr.fx, (v - intr.ppy) / intr.fy, 1.0])
        n, d0 = table
        return max(0.0, float(n @ (ray * float(np.median(patch))) + d0))

    def _put_down_z(self, x, y, fallback):
        """Cup height for setting the returned block down at (x, y).

        Reference = the robot's own pick: the cup was at (pick Z - PRESS_DEPTH) with the block
        sealed on it while the block stood on surface S0 (measured by the camera right after
        the pick). Now the camera measures the surface S again: put the cup at the same height
        + (S - S0) + a small drop clearance, so the block is never pushed down."""
        drop = float(config.load_config().get("return_drop_mm", 5))
        s0 = self.last_pick[2] if len(self.last_pick) > 2 else None
        s = self._surface_height(x, y)
        pick_z = fallback - d.PRESS_DEPTH                         # lowest cup point of the pick (= taught Z)
        if s is None or s0 is None:
            self.log(f"Return block: spot height not measured - setting down {drop:g} mm above the pick height")
            return pick_z + drop
        change = s - s0
        if abs(change) < 8:                                       # same spot as after the pick: exactly
            change = 0.0                                          # pick height + drop (ignore camera noise)
        self.log(f"Return block: surface at the old spot {s:.0f} mm above the plate "
                 f"(was {s0:.0f} mm right after the pick) - setting down at pick height {pick_z:.1f} "
                 f"+ {drop:g} mm" + (f" {change:+.0f} mm" if change else ""))
        return pick_z + change + drop

    def _loop(self, robot, cam, plc):
        st = self.status
        cal = self._load_calib()
        if cal is None:
            st["auto"] = False
            self.log("No calibration yet - run Auto calibration first (Calibration page)")
        st["state"] = "running"

        sel_idx, frame_no = 0, 0
        no_reach = []
        prev_gray, last_motion = None, time.time()
        stable_pos, stable_since = None, time.time()
        empty_since = placed_at = None
        placed_h = None

        def setup(cal):
            R, t, z_table, auto_cal = cal
            table = d.calib_table(R, t, z_table) if z_table is not None else None
            z_min = (z_table - 5) if z_table is not None else 0
            if table is not None:                 # plate under the camera centre, for the simulator
                n, d0 = table
                ray = np.array([0.0, 0.0, 1.0])
                c = R @ (ray * (-d0 / (n @ ray))) + t
                self.scene["plate"] = (float(c[0]), float(c[1]), float(z_table))
                self._geo = (R, t, z_table, table, auto_cal)        # for measuring heights (Return block)
            return R, t, table, z_min, auto_cal

        if cal:
            R, t, table, z_min, auto_cal = setup(cal)

        model = config.load_config().get("pick_model")

        def to_robot(b):
            p = R @ b["p_cam"] + t
            if model and auto_cal:                     # each block: its own measured height
                low = model["plate_z"] + model["scale"] * b["height"] + self.learner.offset(b["height"])
                p[2] = low + d.PRESS_DEPTH             # lowest cup point = low
                return p
            off = self.learner.offset(b["height"]) if auto_cal else 0.0
            return p + np.array([0.0, 0.0, off])

        def precise(near):
            img2, depth2 = cam.grab_avg(8)
            best = None
            for b in d.find_blue_blocks(img2, depth2, cam.intr, table):
                if b["p_cam"] is not None:
                    p = to_robot(b)
                    dist = np.linalg.norm(p - near)
                    if dist < 20 and (best is None or dist < best[0]):
                        best = (dist, p, b["height"])
            return None if best is None else best[1:]

        while True:
            # ---- commands from the studio
            pick_now = False
            while not self.q.empty():
                c = self.q.get()
                if c == "stop":
                    return
                if c == "auto_on":
                    st["auto"] = True
                elif c == "auto_off":
                    st["auto"] = False
                elif c == "pick":
                    pick_now = True
                elif c == "next":
                    sel_idx += 1
                elif c == "clear":
                    no_reach.clear()
                    self.log("Skipped blocks cleared - all blocks will be tried again")
                elif c == "calibrate":
                    st["auto"] = False
                    if self._calibrate(robot, cam):
                        cal = self._load_calib()
                        R, t, table, z_min, auto_cal = setup(cal)
                    cam.flush()
                    prev_gray = None
                elif c == "return":
                    st["auto"] = False              # do not pick the returned block again by itself
                    if self._return_block(robot, plc):
                        placed_at = empty_since = None
                    cam.flush()
                    prev_gray, last_motion, stable_pos = None, time.time(), None

            img, depth = cam.grab()
            self._depth, self._intr = depth, cam.intr     # latest depth picture (robot parked = clear view)
            if getattr(self, "_need_s0", False) and self.last_pick is not None and cal is not None:
                self._need_s0 = False                     # first picture after a pick: what is left there
                p, h = self.last_pick[:2]
                self.last_pick = (p, h, self._surface_height(p[0], p[1]))
            view = img.copy()
            if cal is None:
                d.text(view, "NOT CALIBRATED - run Auto calibration", (5, 20), (0, 0, 255), 0.6)
                st["text"] = "Not calibrated"
                self._publish(view)
                continue

            frame_no += 1
            gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
            if prev_gray is not None and (cv2.absdiff(gray, prev_gray) > 25).mean() > d.MOTION_FRACTION:
                last_motion = time.time()
            prev_gray = gray
            blocks = d.find_blue_blocks(img, depth, cam.intr, table)
            self.tracker.update(blocks)                   # steady positions/boxes (no flicker)
            pickable = []
            for b in blocks:
                if b["p_cam"] is None:
                    b["col"], b["label"] = (0, 200, 255), "no depth"
                    continue
                b["p_rob"] = to_robot(b)
                ok = d.target_ok(b["p_rob"], z_min)
                x, y, z = b["p_rob"]
                b["col"] = (0, 255, 0) if ok else (0, 0, 255)
                b["label"] = f"X{x:.0f} Y{y:.0f} Z{z:.0f} h{b['height']:.0f}" + ("" if ok else " OUT OF REACH")
                if ok and any(np.hypot(x - nx, y - ny) < 25 for nx, ny in no_reach):
                    b["col"], b["label"] = (0, 0, 255), b["label"] + " CAN'T REACH"
                elif ok:
                    pickable.append(b)
            if pickable:
                sel_idx %= len(pickable)
            target = pickable[sel_idx] if pickable else None
            self.scene["blocks"] = [tuple((R @ b["p_cam"] + t).tolist()) + (float(b["height"]), b is target)
                                    for b in blocks if b["p_cam"] is not None]

            now = time.time()
            if target is not None and stable_pos is not None \
                    and np.linalg.norm(target["p_rob"] - stable_pos) < d.STABLE_MM:
                pass
            else:
                stable_pos = None if target is None else target["p_rob"].copy()
                stable_since = now
            quiet, still = now - last_motion, now - stable_since
            ready = target is not None and quiet >= d.STABLE_SEC and still >= d.STABLE_SEC

            # ---- load cell
            lc_ok, lc_msg = True, ""
            if plc is not None:
                st["weight"], st["plc_ok"], st["plc_empty"] = plc.weight, plc.ok, plc.empty
                st["plc_error"] = plc.error
                empty_since = (empty_since or now) if plc.empty else None
                if placed_at is not None:
                    if plc.loaded:
                        st["ok"] += 1
                        self.weights.appendleft((time.strftime("%H:%M:%S"), plc.weight))
                        msg = self.learner.record(placed_h, True)
                        self.log(f"Load cell: block arrived, {plc.weight:g} g")
                        if msg:
                            self.log("  -> " + msg)
                        placed_at = empty_since = None
                    elif now - placed_at > d.LOAD_WAIT_SEC:
                        st["fail"] += 1
                        self.log("WARNING: no weight on the load cell after the place "
                                 "(block not lifted or dropped?)")
                        msg = self.learner.record(placed_h, False)
                        if msg:
                            self.log("  -> " + msg)
                        placed_at = empty_since = None
                if not plc.ok:
                    lc_ok, lc_msg = False, "WAIT: no PLC data"
                elif placed_at is not None:
                    lc_ok, lc_msg = False, "WAIT: block going onto load cell"
                elif empty_since is None:
                    lc_ok, lc_msg = False, f"WAIT: load cell not empty ({plc.weight:g} g)"
                elif now - empty_since < d.EMPTY_STABLE_SEC:
                    lc_ok, lc_msg = False, "WAIT: load cell empty, confirming"
            ready = ready and lc_ok

            if not st["auto"]:
                status = "PAUSED (auto off)" if target is not None else "PAUSED - no block"
            elif target is None:
                status = "No block to pick"
            elif not lc_ok:
                status = lc_msg
            elif quiet < d.STABLE_SEC:
                status = "WAIT: movement in view (hand?)"
            elif not ready:
                status = f"WAIT: block still {min(quiet, still):.1f}/{d.STABLE_SEC:.0f}s"
            else:
                status = "READY"
            st.update(text=status, blocks=len(blocks), pickable=len(pickable), skipped=len(no_reach))

            for b in blocks:                    # (status text is shown by the studio, translated)
                cv2.drawContours(view, [cv2.boxPoints(b["rect"]).astype(np.int32)], -1, b["col"],
                                 4 if b is target else 2)
                cx, cy = map(int, b["rect"][0])
                cv2.circle(view, (cx, cy), 4, (0, 0, 255), -1)
                d.text(view, ("> " if b is target else "") + b["label"], (max(cx - 90, 2), cy + 20))
            self._publish(view)

            if target is not None and ((pick_now and lc_ok) or (st["auto"] and ready)):
                found = precise(target["p_rob"])
                if found is None or not d.target_ok(found[0], z_min):
                    stable_since = time.time()
                    continue
                p, h = found
                st["text"] = f"PICKING at X{p[0]:.0f} Y{p[1]:.0f} Z{p[2]:.0f}"
                if d.pick_and_place(robot, p):
                    placed_at, placed_h, empty_since = time.time(), h, None
                    self.last_pick = (np.array(p, float), h)        # for "Return block"
                    self._need_s0 = True                            # measure the spot on the next picture
                    st["can_return"] = True
                    if plc is None:                 # no load cell: count it as done
                        st["ok"] += 1
                        placed_at = None
                else:
                    no_reach.append((p[0], p[1]))
                    self.log(f"Skipped block at X{p[0]:.0f} Y{p[1]:.0f}: robot cannot reach it")
                cam.flush()
                prev_gray, last_motion, stable_pos = None, time.time(), None
