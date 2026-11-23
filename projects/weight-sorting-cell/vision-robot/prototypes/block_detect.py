"""
Block detection with an Intel RealSense D455.

Finds blocks on a table by their height above the table plane (works for any
block color), and reports for each block:
  - center of the top face in camera coordinates (mm)
  - length x width x height (mm)
  - yaw angle on the table (deg)

Usage:
  py -3.12 block_detect.py            live window  (q = quit, s = save, t = re-fit table)
  py -3.12 block_detect.py --once     capture once, save block_result.png + blocks.json, exit

Camera setup: mount the D455 about 55-70 cm above the table, pointing down.
The table must be the largest flat surface in view.
"""
import argparse
import json
import time
import warnings

import cv2
import numpy as np
import pyrealsense2 as rs

# (depth w, h, fps), (color w, h, fps) - tried in order; the 2nd works on USB 2
MODES = [((640, 480, 15), (640, 480, 15)), ((480, 270, 15), (424, 240, 15))]

MIN_HEIGHT_MM = 8      # anything lower than this above the table is ignored
MAX_HEIGHT_MM = 200    # anything taller is ignored (arms, robot, etc.)
MIN_AREA_PX = 120      # smallest blob (in pixels) counted as a block
MAX_RANGE_MM = 1500    # ignore depth beyond this when fitting the table


# ---------------------------------------------------------------- camera
def start_camera():
    for (dw, dh, df), (cw, ch, cf) in MODES:
        pipe, cfg = rs.pipeline(), rs.config()
        cfg.enable_stream(rs.stream.depth, dw, dh, rs.format.z16, df)
        cfg.enable_stream(rs.stream.color, cw, ch, rs.format.bgr8, cf)
        try:
            prof = pipe.start(cfg)
            print(f"Streaming depth {dw}x{dh} + color {cw}x{ch} @ {df} fps")
            return pipe, prof
        except RuntimeError as e:
            print(f"Mode depth {dw}x{dh} / color {cw}x{ch} not available: {e}")
    raise SystemExit("Could not start the camera in any mode.")


class Grabber:
    def __init__(self):
        self.pipe, prof = start_camera()
        self.scale_mm = prof.get_device().first_depth_sensor().get_depth_scale() * 1000.0
        self.align = rs.align(rs.stream.color)
        self.spatial = rs.spatial_filter()
        self.temporal = rs.temporal_filter()
        self.intr = prof.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
        for _ in range(30):  # let auto-exposure settle
            self.pipe.wait_for_frames(5000)

    def grab(self):
        """Returns (color BGR image, depth in mm as float32 with NaN for no data)."""
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
        imgs, depths = [], []
        for _ in range(n):
            img, dep = self.grab()
            imgs.append(img)
            depths.append(dep)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # pixels with no depth in any frame
            return imgs[-1], np.nanmedian(np.stack(depths), axis=0)

    def stop(self):
        self.pipe.stop()


# ---------------------------------------------------------------- geometry
def deproject(depth, intr):
    """Depth image (mm) -> HxWx3 points in camera coordinates (mm)."""
    h, w = depth.shape
    u, v = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    x = (u - intr.ppx) / intr.fx * depth
    y = (v - intr.ppy) / intr.fy * depth
    return np.dstack([x, y, depth])


def fit_table_plane(P, iters=300, thr=4.0):
    """RANSAC plane fit. Returns unit normal n and d so that n.p + d = height
    above the table in mm (positive towards the camera)."""
    pts = P.reshape(-1, 3)
    pts = pts[np.isfinite(pts[:, 2]) & (pts[:, 2] < MAX_RANGE_MM)]
    if len(pts) < 500:
        raise RuntimeError("Not enough depth data to find the table.")
    rng = np.random.default_rng(0)
    sample = pts[rng.choice(len(pts), min(len(pts), 8000), replace=False)]
    best, best_cnt = None, 0
    for _ in range(iters):
        a, b, c = sample[rng.choice(len(sample), 3, replace=False)]
        n = np.cross(b - a, c - a)
        nn = np.linalg.norm(n)
        if nn < 1e-6:
            continue
        n /= nn
        d = -n @ a
        cnt = np.count_nonzero(np.abs(sample @ n + d) < thr)
        if cnt > best_cnt:
            best, best_cnt = (n, d), cnt
    n, d = best
    inl = sample[np.abs(sample @ n + d) < thr]
    c = inl.mean(axis=0)
    n = np.linalg.svd(inl - c)[2][2]
    d = -n @ c
    if d < 0:  # camera (origin) must be on the positive side
        n, d = -n, -d
    return n, d, len(inl) / len(sample), d  # last value = camera height above table


def plane_basis(n):
    ex = np.array([1.0, 0.0, 0.0])
    e1 = ex - (ex @ n) * n
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    return e1, e2


# ---------------------------------------------------------------- detection
def detect_blocks(depth, intr, plane):
    n, d = plane[0], plane[1]
    P = deproject(depth, intr)
    H = P @ n + d                                   # height above table, mm
    valid = np.isfinite(H)
    mask = (valid & (H > MIN_HEIGHT_MM) & (H < MAX_HEIGHT_MM)).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

    e1, e2 = plane_basis(n)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blocks = []
    for cnt in contours:
        if cv2.contourArea(cnt) < MIN_AREA_PX:
            continue
        blob = np.zeros_like(mask)
        cv2.drawContours(blob, [cnt], -1, 255, -1)
        blob = cv2.erode(blob, k)  # drop noisy edge pixels
        sel = (blob > 0) & valid
        if np.count_nonzero(sel) < 30:
            continue
        hs = H[sel]
        top_h = float(np.percentile(hs, 90))
        top = sel & (H > top_h - 6)            # pixels on the top face
        tp = P[top]
        if len(tp) < 20:
            continue
        # size of the top face, measured in table coordinates
        uv = np.stack([tp @ e1, tp @ e2], axis=1).astype(np.float32)
        (cu, cv_), (sw, sl), ang = cv2.minAreaRect(uv)
        length, width = max(sw, sl), min(sw, sl)
        yaw = ang if sw >= sl else ang + 90.0       # angle of the long side vs. camera X
        yaw = (yaw + 90.0) % 180.0 - 90.0
        center = tp.mean(axis=0)
        rect_px = cv2.minAreaRect(cnt)
        blocks.append({
            "center_cam_mm": [round(float(x), 1) for x in center],
            "size_mm": [round(float(length), 1), round(float(width), 1), round(top_h, 1)],
            "yaw_deg": round(float(yaw), 1),
            "pixel": [int(rect_px[0][0]), int(rect_px[0][1])],
            "_rect_px": rect_px,
        })
    blocks.sort(key=lambda b: (b["pixel"][1], b["pixel"][0]))
    for i, b in enumerate(blocks, 1):
        b["id"] = i
    return blocks, mask


def draw(img, blocks, plane):
    out = img.copy()
    for b in blocks:
        box = cv2.boxPoints(b["_rect_px"]).astype(np.int32)
        cv2.drawContours(out, [box], -1, (0, 255, 0), 2)
        px, py = b["pixel"]
        cv2.circle(out, (px, py), 3, (0, 0, 255), -1)
        L, W, Hh = b["size_mm"]
        x, y, z = b["center_cam_mm"]
        lines = [f"#{b['id']} {L:.0f}x{W:.0f}x{Hh:.0f}mm {b['yaw_deg']:.0f}deg",
                 f"X{x:.0f} Y{y:.0f} Z{z:.0f}"]
        for j, t in enumerate(lines):
            org = (max(px - 60, 2), max(py - 22 + 14 * j, 12))
            cv2.putText(out, t, org, cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 3)
            cv2.putText(out, t, org, cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    cv2.putText(out, f"table {plane[3]:.0f}mm away, blocks: {len(blocks)}", (5, out.shape[0] - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    return out


def report(blocks):
    if not blocks:
        print("No blocks found.")
    for b in blocks:
        L, W, Hh = b["size_mm"]
        x, y, z = b["center_cam_mm"]
        print(f"Block {b['id']}: size {L} x {W} x {Hh} mm, yaw {b['yaw_deg']} deg, "
              f"top center (camera) X={x} Y={y} Z={z} mm")


def save(img, blocks, mask, plane):
    cv2.imwrite("block_result.png", draw(img, blocks, plane))
    cv2.imwrite("block_mask.png", mask)
    with open("blocks.json", "w") as f:
        json.dump({"table_distance_mm": round(float(plane[3]), 1),
                   "table_normal": [round(float(v), 4) for v in plane[0]],
                   "blocks": [{k: v for k, v in b.items() if not k.startswith("_")} for b in blocks]},
                  f, indent=2)
    print("Saved block_result.png, block_mask.png, blocks.json")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="capture once, save results, exit")
    args = ap.parse_args()

    cam = Grabber()
    try:
        img, depth = cam.grab_avg(15)
        plane = fit_table_plane(deproject(depth, cam.intr))
        print(f"Table found: {plane[3]:.0f} mm from camera, {plane[2]*100:.0f}% of view is table")
        if plane[3] < 450:
            print("WARNING: table is closer than ~45 cm; the D455 is inaccurate that close.")

        if args.once:
            blocks, mask = detect_blocks(depth, cam.intr, plane)
            report(blocks)
            save(img, blocks, mask, plane)
            return

        print("Live: q = quit, s = save, t = re-fit table. Table is re-fit automatically every 5 frames.")
        last_print = 0
        frame_no = 0
        while True:
            img, depth = cam.grab()
            frame_no += 1
            if frame_no % 5 == 0:  # camera may be hand-held: keep the table plane up to date
                try:
                    plane = fit_table_plane(deproject(depth, cam.intr))
                except RuntimeError:
                    pass
            blocks, mask = detect_blocks(depth, cam.intr, plane)
            dvis = cv2.applyColorMap(cv2.convertScaleAbs(np.nan_to_num(depth, nan=0), alpha=255 / 1000),
                                     cv2.COLORMAP_JET)
            dvis[~np.isfinite(depth)] = 0
            valid_pct = np.isfinite(depth).mean() * 100
            cv2.putText(dvis, f"depth (black = no data) valid {valid_pct:.0f}%", (5, 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            view = draw(img, blocks, plane)
            if dvis.shape != view.shape:
                dvis = cv2.resize(dvis, (view.shape[1], view.shape[0]))
            cv2.imshow("D455 blocks  (q = quit, s = save)", np.hstack([view, dvis]))
            if time.time() - last_print > 2:
                report(blocks)
                last_print = time.time()
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("s"):
                save(img, blocks, mask, plane)
            if key == ord("t"):
                _, dep = cam.grab_avg(15)
                plane = fit_table_plane(deproject(dep, cam.intr))
                print(f"Table re-fit: {plane[3]:.0f} mm")
    finally:
        cam.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
