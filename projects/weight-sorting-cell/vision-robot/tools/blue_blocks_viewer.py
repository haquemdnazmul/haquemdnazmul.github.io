"""
D455 blue block detector  (single file - works in VS Code)

Finds blue blocks with an Intel RealSense D455 and shows, for each block:
  size (length x width x height, mm), angle (deg), position from camera (X, Y, Z mm)

Requirements (Python 3.12 64-bit - pyrealsense2 does not support 3.14 yet):
    py -3.12 -m pip install pyrealsense2 opencv-contrib-python numpy
    (opencv-python also works - but don't install both opencv packages together)

Run:
    py -3.12 d455_blue_blocks.py          live window   (q = quit, s = save snapshot)
    py -3.12 d455_blue_blocks.py --once   one capture, save result, exit

Camera: mount ~55-65 cm above the table, pointing down. Closer than ~45 cm the
depth is invalid: boxes turn orange, height shows "?" and size is a rough estimate.
"""
import argparse
import json
import os
import time
import warnings

import cv2
import numpy as np
try:
    import pyrealsense2 as rs
except ModuleNotFoundError:
    # Wrong Python (e.g. 3.14 or 32-bit): re-run this script with Python 3.12 64-bit automatically.
    import os
    import subprocess
    import sys
    if os.environ.get("D455_RELAUNCHED") != "1":
        print(f"pyrealsense2 not found in {sys.executable} - switching to Python 3.12 64-bit...")
        env = dict(os.environ, D455_RELAUNCHED="1")
        try:
            sys.exit(subprocess.call(["py", "-3.12", os.path.abspath(__file__), *sys.argv[1:]], env=env))
        except FileNotFoundError:
            pass  # no "py" launcher - fall through to the message below
    raise SystemExit(
        "pyrealsense2 is not installed for this Python:\n  " + sys.executable +
        f"\n  (version {sys.version.split()[0]}, {'64' if sys.maxsize > 2**32 else '32'}-bit)\n"
        "Use Python 3.12 64-bit: in VS Code press Ctrl+Shift+P > 'Python: Select Interpreter'\n"
        "and pick ...\\Programs\\Python\\Python312\\python.exe (NOT Python312-32 or Python314).")

# ------------------------------------------------------------------ settings
BLUE_LO, BLUE_HI = (95, 120, 50), (130, 255, 255)   # HSV range for "blue"
MIN_AREA_PX = 800                                    # ignore smaller blue blobs
MAX_RANGE_MM = 1500                                  # ignore depth beyond this for the table fit
# (depth w,h,fps), (color w,h,fps) - tried in order; the 2nd one also works on USB 2
MODES = [((640, 480, 15), (640, 480, 15)), ((480, 270, 15), (424, 240, 15))]


# ------------------------------------------------------------------ camera
class Camera:
    def __init__(self):
        for (dw, dh, df), (cw, ch, cf) in MODES:
            self.pipe, cfg = rs.pipeline(), rs.config()
            cfg.enable_stream(rs.stream.depth, dw, dh, rs.format.z16, df)
            cfg.enable_stream(rs.stream.color, cw, ch, rs.format.bgr8, cf)
            try:
                prof = self.pipe.start(cfg)
                print(f"Camera started: depth {dw}x{dh}, color {cw}x{ch} @ {df} fps")
                break
            except RuntimeError as e:
                print(f"Mode {dw}x{dh}/{cw}x{ch} not available: {e}")
        else:
            raise SystemExit("Could not start the D455. Is it plugged in?")
        self.scale_mm = prof.get_device().first_depth_sensor().get_depth_scale() * 1000.0
        self.intr = prof.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
        self.align = rs.align(rs.stream.color)          # depth pixels line up with color pixels
        self.spatial, self.temporal = rs.spatial_filter(), rs.temporal_filter()
        for _ in range(30):                              # let auto-exposure settle
            self.pipe.wait_for_frames(5000)

    def grab(self):
        """Returns (color BGR image, depth in mm as float32, NaN = no data)."""
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

    def stop(self):
        self.pipe.stop()


# ------------------------------------------------------------------ geometry
def deproject(depth, intr):
    """Depth image (mm) -> HxWx3 points in camera coordinates (mm)."""
    h, w = depth.shape
    u, v = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return np.dstack([(u - intr.ppx) / intr.fx * depth, (v - intr.ppy) / intr.fy * depth, depth])


def fit_table(P, iters=300, thr=4.0):
    """RANSAC plane fit of the table. Returns (normal n, d, distance camera->table in mm).
    For any point p:  n.p + d = height above the table (mm)."""
    pts = P.reshape(-1, 3)
    pts = pts[np.isfinite(pts[:, 2]) & (pts[:, 2] < MAX_RANGE_MM)]
    if len(pts) < 500:
        raise RuntimeError("Not enough depth data to find the table.")
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
    if d < 0:
        n, d = -n, -d
    return n, d, float(d)


# ------------------------------------------------------------------ detection
def find_blue_blocks(img, depth, intr, table):
    n, d, table_mm = table
    H = deproject(depth, intr) @ n + d                    # height above table per pixel
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, BLUE_LO, BLUE_HI)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted([c for c in cnts if cv2.contourArea(c) > MIN_AREA_PX],
                  key=lambda c: cv2.boundingRect(c)[0])

    blocks = []
    for i, c in enumerate(cnts, 1):
        blob = np.zeros(mask.shape, np.uint8)
        cv2.drawContours(blob, [c], -1, 255, -1)
        sel = (blob > 0) & np.isfinite(H)
        height = z_top = None
        if sel.sum() > 30:
            height, z_top = float(np.median(H[sel])), float(np.median(depth[sel]))
            if not (3 < height < 200):                    # bogus depth -> don't trust it
                height = z_top = None
        measured = height is not None
        if not measured:
            z_top = table_mm                              # fall back to table distance (rough)

        (cx, cy), (w, h), ang = cv2.minAreaRect(c)
        mm_per_px = z_top / intr.fx
        length, width = max(w, h) * mm_per_px, min(w, h) * mm_per_px
        yaw = ang if w >= h else ang + 90.0               # angle of the long side vs. image X
        yaw = (yaw + 90.0) % 180.0 - 90.0
        x = (cx - intr.ppx) / intr.fx * z_top
        y = (cy - intr.ppy) / intr.fy * z_top
        blocks.append({
            "id": i,
            "depth_ok": measured,
            "size_mm": [round(length, 1), round(width, 1), None if height is None else round(height, 1)],
            "yaw_deg": round(yaw, 1),
            "center_cam_mm": [round(x, 1), round(y, 1), round(z_top, 1)],
            "pixel": [int(cx), int(cy)],
            "_rect": ((cx, cy), (w, h), ang),
        })
    return blocks


# ------------------------------------------------------------------ display
def text(img, s, org, color=(255, 255, 255)):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)


def draw(img, depth, blocks, table):
    out = img.copy()
    for b in blocks:
        col = (0, 255, 0) if b["depth_ok"] else (0, 200, 255)   # green = measured, orange = rough
        cv2.drawContours(out, [cv2.boxPoints(b["_rect"]).astype(np.int32)], -1, col, 2)
        px, py = b["pixel"]
        cv2.circle(out, (px, py), 4, (0, 0, 255), -1)
        L, W, Hh = b["size_mm"]
        x, y, z = b["center_cam_mm"]
        pre = "" if b["depth_ok"] else "~"
        hs = "?" if Hh is None else f"{Hh:.0f}"
        for j, s in enumerate([f"Blue #{b['id']}  {pre}{L:.0f} x {W:.0f} x {hs} mm",
                               f"angle {b['yaw_deg']:.0f} deg",
                               f"X {x:.0f}  Y {y:.0f}  Z {z:.0f} mm"]):
            text(out, s, (max(px - 85, 2), min(py + 15 + 16 * j, out.shape[0] - 30)))
    valid = np.isfinite(depth).mean() * 100
    text(out, f"table {table[2]:.0f} mm | depth valid {valid:.0f}% | blue blocks: {len(blocks)}",
         (5, out.shape[0] - 10), (0, 255, 255))
    if any(not b["depth_ok"] for b in blocks):
        text(out, "orange = no valid depth on block, size is rough (~)", (5, 18), (0, 200, 255))

    dv = cv2.applyColorMap(cv2.convertScaleAbs(np.nan_to_num(depth, nan=0), alpha=255 / 1000),
                           cv2.COLORMAP_JET)
    dv[~np.isfinite(depth)] = 0
    text(dv, "depth (black = no data)", (5, 18))
    if dv.shape != out.shape:
        dv = cv2.resize(dv, (out.shape[1], out.shape[0]))
    return out, np.hstack([out, dv])


def print_blocks(blocks):
    if not blocks:
        print("No blue blocks found.")
    for b in blocks:
        print(f"Blue #{b['id']}: size {b['size_mm']} mm, angle {b['yaw_deg']} deg, "
              f"position {b['center_cam_mm']} mm, depth_ok={b['depth_ok']}")


def save(view, blocks, name="blue_blocks"):
    """Saves next to this script file (works even when the path has Korean characters)."""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    ok, png = cv2.imencode(".png", view)
    if ok:
        png.tofile(base + ".png")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in b.items() if not k.startswith("_")} for b in blocks],
                  f, indent=2, default=float)
    print(f"Saved {base}.png and .json")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="capture once, save, exit")
    args = ap.parse_args()

    cam = Camera()
    try:
        img, depth = cam.grab_avg(10)
        table = fit_table(deproject(depth, cam.intr))
        print(f"Table found {table[2]:.0f} mm from camera")

        if args.once:
            blocks = find_blue_blocks(img, depth, cam.intr, table)
            print_blocks(blocks)
            save(draw(img, depth, blocks, table)[0], blocks)
            return

        win = "D455 blue blocks  (q = quit, s = save)"
        frame_no, last_print = 0, 0.0
        while True:
            img, depth = cam.grab()
            frame_no += 1
            if frame_no % 5 == 0:                         # keep the table up to date
                try:
                    table = fit_table(deproject(depth, cam.intr))
                except RuntimeError:
                    pass
            blocks = find_blue_blocks(img, depth, cam.intr, table)
            view, both = draw(img, depth, blocks, table)
            cv2.imshow(win, both)
            if time.time() - last_print > 2:
                print_blocks(blocks)
                last_print = time.time()
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord("s"):
                save(view, blocks)
    finally:
        cam.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
