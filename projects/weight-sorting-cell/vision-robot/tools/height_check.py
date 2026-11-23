"""Measure the height of every blue block (no robot). Saves height_check.png next to this file.

    py -3.12 tools\\height_check.py
"""
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import d455_pick_place as pp   # noqa: E402  (uses the same camera settings as the main program)

cam = pp.Camera()
try:
    img, depth = cam.grab_avg(15)
finally:
    cam.stop()
table = pp.fit_table(depth, cam.intr)
print(f"valid depth {np.isfinite(depth).mean() * 100:.0f}%   table {table[1]:.0f} mm from camera")
out = img.copy()
for b in pp.find_blue_blocks(img, depth, cam.intr, table):
    cx, cy = map(int, b["rect"][0])
    cv2.drawContours(out, [cv2.boxPoints(b["rect"]).astype(np.int32)], -1, (0, 255, 0), 2)
    h = "no depth" if b["height"] is None else f"{b['height']:.0f} mm"
    print(f"blue block at pixel ({cx},{cy}): height {h}")
    pp.text(out, h, (cx - 30, cy), (255, 255, 255), 0.7)
ok, png = cv2.imencode(".png", out)
png.tofile(os.path.join(HERE, "height_check.png"))
