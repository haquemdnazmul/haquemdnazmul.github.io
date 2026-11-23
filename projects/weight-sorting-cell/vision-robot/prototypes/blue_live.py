"""
Live blue-block display for the D455.

Finds blue blocks by color, and shows size / angle / position on screen.
Height comes from depth when the depth on the block is valid; otherwise the
block is sized using the table distance (rough, shown as "~").

Keys: q = quit, s = save snapshot (blue_live.png + blue_live.json)
Run:  py -3.12 -I blue_live.py
"""
import json
import time

import cv2
import numpy as np

import block_detect as bd

BLUE_LO, BLUE_HI = (95, 120, 50), (130, 255, 255)   # HSV range for blue
MIN_AREA_PX = 800


def find_blue(img, depth, intr, plane):
    n, d = plane[0], plane[1]
    P = bd.deproject(depth, intr)
    H = P @ n + d
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
        h_med = z_med = None
        if sel.sum() > 30:
            h_med = float(np.median(H[sel]))
            z_med = float(np.median(depth[sel]))
            if not (3 < h_med < 200):          # bogus depth (camera too close, etc.)
                h_med = z_med = None
        measured = h_med is not None
        z_top = z_med if measured else float(d)
        (cx, cy), (w, h), ang = cv2.minAreaRect(c)
        mm_px = z_top / intr.fx
        L, W = max(w, h) * mm_px, min(w, h) * mm_px
        yaw = ang if w >= h else ang + 90.0
        yaw = (yaw + 90.0) % 180.0 - 90.0
        X = (cx - intr.ppx) / intr.fx * z_top
        Y = (cy - intr.ppy) / intr.fy * z_top
        blocks.append(dict(id=i, measured=measured, rect=((cx, cy), (w, h), ang),
                           size_mm=[round(L, 1), round(W, 1), None if h_med is None else round(h_med, 1)],
                           yaw_deg=round(yaw, 1),
                           center_cam_mm=[round(X, 1), round(Y, 1), round(z_top, 1)],
                           pixel=[int(cx), int(cy)]))
    return blocks, mask


def draw(img, blocks, plane, valid_pct):
    out = img.copy()
    for b in blocks:
        color = (0, 255, 0) if b["measured"] else (0, 200, 255)
        box = cv2.boxPoints(b["rect"]).astype(np.int32)
        cv2.drawContours(out, [box], -1, color, 2)
        px, py = b["pixel"]
        cv2.circle(out, (px, py), 4, (0, 0, 255), -1)
        L, W, Hh = b["size_mm"]
        x, y, z = b["center_cam_mm"]
        pre = "" if b["measured"] else "~"
        hs = f"{Hh:.0f}" if Hh is not None else "?"
        lines = [f"Blue #{b['id']}  {pre}{L:.0f} x {W:.0f} x {hs} mm",
                 f"angle {b['yaw_deg']:.0f} deg",
                 f"X {x:.0f}  Y {y:.0f}  Z {z:.0f} mm"]
        for j, t in enumerate(lines):
            org = (max(px - 85, 2), min(py + 15 + 16 * j, out.shape[0] - 30))
            cv2.putText(out, t, org, cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
            cv2.putText(out, t, org, cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    status = f"table {plane[3]:.0f} mm | depth valid {valid_pct:.0f}% | blue blocks: {len(blocks)}"
    cv2.putText(out, status, (5, out.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
    cv2.putText(out, status, (5, out.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    if any(not b["measured"] for b in blocks):
        cv2.putText(out, "orange = no valid depth on block, size is rough (~)", (5, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)
    return out


def main():
    cam = bd.Grabber()
    try:
        img, depth = cam.grab_avg(10)
        plane = bd.fit_table_plane(bd.deproject(depth, cam.intr))
        print(f"Table at {plane[3]:.0f} mm. Window open: q = quit, s = save")
        frame_no, last_print = 0, 0
        win = "D455 blue blocks  (q = quit, s = save)"
        while True:
            img, depth = cam.grab()
            frame_no += 1
            if frame_no % 5 == 0:
                try:
                    plane = bd.fit_table_plane(bd.deproject(depth, cam.intr))
                except RuntimeError:
                    pass
            valid_pct = np.isfinite(depth).mean() * 100
            blocks, mask = find_blue(img, depth, cam.intr, plane)
            view = draw(img, blocks, plane, valid_pct)
            dv = cv2.applyColorMap(cv2.convertScaleAbs(np.nan_to_num(depth, nan=0), alpha=255 / 1000),
                                   cv2.COLORMAP_JET)
            dv[~np.isfinite(depth)] = 0
            cv2.putText(dv, "depth (black = no data)", (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (255, 255, 255), 1)
            if dv.shape != view.shape:
                dv = cv2.resize(dv, (view.shape[1], view.shape[0]))
            cv2.imshow(win, np.hstack([view, dv]))

            if time.time() - last_print > 2:
                for b in blocks:
                    print(f"Blue #{b['id']}: size {b['size_mm']} mm, yaw {b['yaw_deg']} deg, "
                          f"pos {b['center_cam_mm']} mm, depth_ok={b['measured']}")
                last_print = time.time()

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord("s"):
                cv2.imwrite("blue_live.png", view)
                with open("blue_live.json", "w") as f:
                    json.dump([{k: v for k, v in b.items() if k != "rect"} for b in blocks], f,
                              indent=2, default=float)
                print("Saved blue_live.png and blue_live.json")
    finally:
        cam.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
