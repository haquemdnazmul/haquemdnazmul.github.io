"""Hole-by-hole part placement for the Uno prototype shield (blue, with strips).

Grid: columns A..N (left to right, photo orientation: RESET at top-left,
Analog In bottom-left, Digital I/O right), rows 1..22 (top to bottom).
Imported by make_schematic.py; run alone to write the two SVGs.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
P = 30                     # px per 0.1" hole pitch
X0, Y0 = 170, 110          # centre of hole A1
BL, BR = 40, X0 + 13 * P + 130   # board left/right edge (x)
BT, BB = 50, Y0 + 23 * P + 20    # board top/bottom edge (y)
W, H = BR + 40, BB + 40

RED, BLUE, GRN, ORG, BLK, GRY, PUR, MAG = "#c0392b", "#1f4fa0", "#1e7b45", "#d07a00", "#111111", "#777777", "#7a3fa0", "#c2185b"
BUTTONS = [(9, "TIMER", "A3"), (10, "AUTO", "D5"), (11, "NEXT", "D6")]   # J5 row 18 (hole row 19)
COLS = "ABCDEFGHIJKLMN"


def name(c, r):
    return f"{COLS[c]}{r + 1}"


# ---------------------------------------------------------------- board model
HSTRIPS = [(3, 5, r) for r in range(9, 18)] + [(8, 10, r) for r in range(9, 18)]
VRAILS = [(0, 10, 21, "GND", BLK), (6, 9, 20, "5V", ORG), (7, 9, 20, "GND", BLK), (13, 9, 21, "5V", ORG)]


def hole_exists(c, r):
    if c == 13:
        return 9 <= r <= 21
    if r <= 3 and c >= 7:
        return False          # DIP / SOIC / ICSP pads
    return 0 <= c <= 12 and 0 <= r <= 21


SENSE = [  # bank, terminal col, top R, node row, bottom R, cap, analog pin
    ("12V", 4, ("R7", "33k"), 10, "R10", "C1", "A0"),
    ("48V", 2, ("R8", "150k"), 13, "R11", "C2", "A1"),
    ("72V", 0, ("R9", "220k"), 16, "R12", "C3", "A2"),
]
GATES = [  # mosfet, first col, gate node row, 100R, 10k, arduino pin
    ("Q1", 10, 16, "R1", "R4", "D2", "OUT1"),
    ("Q2", 5, 13, "R2", "R5", "D3", "OUT2"),
    ("Q3", 0, 10, "R3", "R6", "D4", "OUT3"),
]
LEDS = [  # gate node row, led ref, colour, fill, resistor ref, bank, pin  (LED row = node row + 1)
    (16, "LED1", "green", "#2ecc40", "R13", "12V", "D2"),
    (13, "LED2", "yellow", "#ffd400", "R14", "48V", "D3"),
    (10, "LED3", "blue", "#2f7bff", "R15", "72V", "D4"),
]
MODE_LEDS = [  # row, led ref, colour, fill, resistor ref, mode, pin, header row
    (12, "LED4", "white", "#f7f7f2", "R16", "AUTO", "D9"),
    (15, "LED5", "red", "#e53935", "R17", "TIMER", "D8"),
]
CYAN = "#0097a7"
J2 = {"OUT3": 6, "OUT2": 8, "OUT1": 10, "GND": 12}   # row 5 (hole row 6)
HDR_L = [(8.5 + i, n) for i, n in enumerate(["NC", "IOREF", "RESET", "3V3", "5V", "GND", "GND", "VIN"])] + \
        [(17.5 + i, f"A{i}") for i in range(6)]
HDR_R = [(4.5 + i, n) for i, n in enumerate(["SCL", "SDA", "AREF", "GND", "D13", "D12", "D11", "D10", "D9", "D8"])] + \
        [(14.5 + i, f"D{7 - i}") for i in range(8)]
XL, XR = -2.4, 15.0     # header columns (grid units)


def pin_row(lst, n):
    return next(r for r, k in lst if k == n)


class Draw:
    def __init__(self, mirror):
        self.m = mirror
        self.o = []
        self.halo = True

    def X(self, c):
        x = X0 + c * P
        return BL + BR - x if self.m else x

    def Y(self, r):
        return Y0 + r * P

    def add(self, s):
        self.o.append(s)

    def text(self, c, r, s, size=11, anchor="middle", col=BLK, bold=False, dx=0, dy=0, px=False):
        x = (c if px else self.X(c)) + (dx if not self.m else -dx)
        if self.m and anchor != "middle":
            anchor = "end" if anchor == "start" else "start"
        y = (r if px else self.Y(r)) + dy
        w = ' font-weight="700"' if bold else ""
        halo = ' stroke="#12306f" stroke-width="3" paint-order="stroke"' if self.halo else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{col}"{w}{halo}>{s}</text>')

    def line(self, a, b, col, w=2, dash=None, op=1):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{self.X(a[0]):.1f}" y1="{self.Y(a[1]):.1f}" x2="{self.X(b[0]):.1f}" y2="{self.Y(b[1]):.1f}" '
                 f'stroke="{col}" stroke-width="{w}" stroke-linecap="round" opacity="{op}"{d}/>')

    def wire(self, pts, col, w=3, op=1, dash=None):
        d = "M" + " L".join(f"{self.X(c):.1f},{self.Y(r):.1f}" for c, r in pts)
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{w}" stroke-linejoin="round" '
                 f'stroke-linecap="round" opacity="{op}"{da}/>')

    def rect(self, c0, r0, c1, r1, fill, stroke=BLK, sw=1.2, rx=3, op=1):
        x0, x1 = sorted((self.X(c0), self.X(c1)))
        y0, y1 = self.Y(r0), self.Y(r1)
        self.add(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" rx="{rx}" '
                 f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{op}"/>')

    def dot(self, c, r, col, rad=5):
        self.add(f'<circle cx="{self.X(c):.1f}" cy="{self.Y(r):.1f}" r="{rad}" fill="{col}" stroke="#ffffff" stroke-width="1.2"/>')


# ---------------------------------------------------------------- common layers
def board(d):
    d.add(f'<rect x="{BL}" y="{BT}" width="{BR - BL}" height="{BB - BT}" rx="10" fill="#1d3f8f" stroke="#0e2457" stroke-width="2"/>')
    # unusable pad area
    d.rect(6.55, -0.6, 12.6, 3.45, "#294f9e", "#8fa6d6", 1, 4)
    d.text(9.6, 1.4, "DIP / SOIC / ICSP pads", 10, col="#c9d6f2")
    d.text(9.6, 2.3, "not used", 10, col="#c9d6f2")
    for c0, c1, r in HSTRIPS:
        d.rect(c0 - 0.38, r - 0.3, c1 + 0.38, r + 0.3, "#c8ccd2", "#9aa0a8", 0.8, 8)
    for c, r0, r1, lab, col in VRAILS:
        d.rect(c - 0.3, r0 - 0.38, c + 0.3, r1 + 0.38, "#c8ccd2", "#9aa0a8", 0.8, 8)
        d.text(c, r1 + 1.05, lab, 10, col="#ffffff", bold=True)
    for c in range(14):
        for r in range(22):
            if hole_exists(c, r):
                d.add(f'<circle cx="{d.X(c):.1f}" cy="{d.Y(r):.1f}" r="6.5" fill="#e9ecef" stroke="#8a929b" stroke-width="1"/>'
                      f'<circle cx="{d.X(c):.1f}" cy="{d.Y(r):.1f}" r="3.2" fill="#0b1630"/>')
    # grid labels
    d.halo = False
    for c in range(14):
        d.text(d.X(c), BT - 8, COLS[c], 11, col="#333333", bold=True, px=True)
    d.halo = True
    for r in range(22):
        d.text(-0.75, r, str(r + 1), 9, col="#c9d6f2", dy=3)
    # Arduino headers
    for xc, lst in ((XL, HDR_L), (XR, HDR_R)):
        groups = [lst[:8], lst[8:]] if xc == XL else [lst[:10], lst[10:]]
        for g in groups:
            d.rect(xc - 0.45, g[0][0] - 0.5, xc + 0.45, g[-1][0] + 0.5, "#141414", "#000", 1, 2)
            for r, n in g:
                d.add(f'<rect x="{d.X(xc) - 5:.1f}" y="{d.Y(r) - 5:.1f}" width="10" height="10" fill="#000" stroke="#555"/>')
                key = n in ("A0", "A1", "A2", "A4", "A5", "D2", "D3", "D4", "5V", "GND")
                side = -1 if xc == XL else 1
                d.text(xc + side * 0.75, r, n, 9, "end" if side < 0 else "start",
                       "#ffd37a" if key else "#c9d6f2", key, dy=3)
    # existing parts
    for c, r, lab in ((-2.4, -0.4, "RESET"), (-2.4, 2.9, "LED2/R2"), (-2.4, 5.6, "S1"), (14.3, 0.6, "ICSP"), (14.6, 3.0, "LED1/R1")):
        d.text(c, r, lab, 9, col="#9fb2dc")


# ---------------------------------------------------------------- parts (top view)
def resistor(d, a, b, lab, val, col="#e8d3a6"):
    """Resistor between holes a and b (flat if far apart, upright if adjacent)."""
    d.line(a, b, "#c0c0c0", 2.2)
    for p in (a, b):
        d.dot(*p, "#c0c0c0", 4)
    if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 1.5:      # lying flat
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        vert = a[0] == b[0]
        L = 1.0
        if vert:
            d.rect(cx - 0.22, cy - L, cx + 0.22, cy + L, col, "#7b6a45", 1, 5)
            for k, bc in ((-0.6, "#c0392b"), (-0.3, "#c0392b"), (0.0, "#d07a00")):
                d.rect(cx - 0.22, cy + k, cx + 0.22, cy + k + 0.12, bc, bc, 0, 0)
            d.text(cx + 0.45, cy - 0.15, lab, 10, "start", "#ffffff", True)
            d.text(cx + 0.45, cy + 0.45, val, 10, "start", "#ffd37a", True)
    else:                                                 # standing up on hole a
        d.add(f'<ellipse cx="{d.X(a[0]):.1f}" cy="{d.Y(a[1]):.1f}" rx="8" ry="8" fill="{col}" stroke="#7b6a45" stroke-width="1.2"/>')
    return


def upright_label(d, c, r, lab, val, side=1, col="#ffffff"):
    d.text(c, r, f"{lab} {val}", 9.5, "start" if side > 0 else "end", col, True, dx=side * 0 , dy=-11)


def cap(d, a, b, lab):
    d.line(a, b, "#c0c0c0", 2.2)
    cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    d.add(f'<ellipse cx="{d.X(cx):.1f}" cy="{d.Y(cy):.1f}" rx="8" ry="11" fill="#e0a03a" stroke="#7a4b07" stroke-width="1.2"/>')
    d.halo = False
    d.text(cx, cy, "104", 6.5, col="#3a2200", bold=True, dy=2.5)
    d.halo = True


def bridge(d, a, b):
    d.line(a, b, "#e6e6e6", 7)
    d.line(a, b, "#a7adb5", 1.4)


def terminal(d, cols, r, labels, title, col="#2f8f5a"):
    c0, c1 = min(cols) - 0.95, max(cols) + 0.95
    d.rect(c0, r - 1.35, c1, r + 0.75, col, "#0f3d24", 1.4, 3)
    for c, lab in zip(cols, labels):
        d.add(f'<circle cx="{d.X(c):.1f}" cy="{d.Y(r - 0.55):.1f}" r="7" fill="#d9d9d9" stroke="#555"/>'
              f'<line x1="{d.X(c) - 5:.1f}" y1="{d.Y(r - 0.55):.1f}" x2="{d.X(c) + 5:.1f}" y2="{d.Y(r - 0.55):.1f}" stroke="#555" stroke-width="1.5"/>')
        d.dot(c, r, "#c0c0c0", 4)
        d.text(c, r - 0.98, lab, 9, col="#ffffff", bold=True)
    tag = title.split(" ·")[0]
    if tag:
        d.text(c0 - 0.12, r - 0.3, tag, 11, "end", "#ffd37a", True)


def mosfet(d, c0, r, lab):
    d.rect(c0 - 0.6, r - 0.55, c0 + 2.6, r - 0.1, "#9aa3ad", "#444", 1, 1)     # metal tab (back)
    d.rect(c0 - 0.55, r - 0.15, c0 + 2.55, r + 0.35, "#151515", "#000", 1, 2)  # body (front)
    for i, p in enumerate("GDS"):
        d.dot(c0 + i, r, "#c0c0c0", 4)
        d.text(c0 + i, r - 0.2, p, 8, col="#ffffff", bold=True)
    d.text(c0 + 1, r + 0.18, lab, 9, col="#ffffff", bold=True, dy=3)


def led(d, a, k, fill):
    """5 mm LED standing: anode (long leg) in hole a, cathode (flat side) in hole k."""
    d.line(a, k, "#c0c0c0", 2.2)
    cx, cy = (a[0] + k[0]) / 2, (a[1] + k[1]) / 2
    d.add(f'<circle cx="{d.X(cx):.1f}" cy="{d.Y(cy):.1f}" r="12" fill="{fill}" stroke="#111" stroke-width="1.4" opacity="0.95"/>')
    xk = d.X(cx) + (d.X(k[0]) - d.X(a[0])) * 0.38
    d.add(f'<line x1="{xk:.1f}" y1="{d.Y(cy) - 10:.1f}" x2="{xk:.1f}" y2="{d.Y(cy) + 10:.1f}" stroke="#111" stroke-width="2"/>')
    d.halo = False
    d.text(cx + (a[0] - k[0]) * 0.2, cy, "+", 10, col="#111", bold=True, dy=4)
    d.halo = True


def header4(d, cols, r, labels):
    d.rect(min(cols) - 0.45, r - 0.42, max(cols) + 0.45, r + 0.42, "#151515", "#000", 1, 2)
    for c, lab in zip(cols, labels):
        d.add(f'<rect x="{d.X(c) - 3:.1f}" y="{d.Y(r) - 3:.1f}" width="6" height="6" fill="#d8b44a"/>')
        d.text(c, r + 1.0, lab, 8.5, col="#ffffff", bold=True)


# ---------------------------------------------------------------- wiring (underside)
def wires(d, op=1.0, w=3):
    # sense: top resistor low end -> node (bridged hole)
    for k, (bank, tc, (rt, v), nr, rb, cc, apin) in enumerate(SENSE):
        y1 = 6.55 + (4 - tc) * 0.12
        xv = 1.45 - (4 - tc) * 0.05
        d.wire([(tc, 6), (tc + 0.45, y1), (xv, y1), (xv, nr - 0.45), (2, nr)], PUR, w, op)
        ar = pin_row(HDR_L, apin)
        d.wire([(3, nr), (3, nr + 0.5), (-0.55, nr + 0.5), (-0.55 - 0.15 * k, ar), (XL, ar)], BLUE, w, op)
    # gates: Arduino pin -> M-hole, J-hole -> MOSFET gate
    for k, (q, c0, nr, r100, r10k, dpin, out) in enumerate(GATES):
        dr = pin_row(HDR_R, dpin)
        d.wire([(XR, dr), (13.55 + 0.15 * k, dr), (13.55 + 0.15 * k, nr + 0.5), (12, nr + 0.5), (12, nr)], GRN, w, op)
        d.wire([(9, nr), (9.5, nr - 0.5), (9.5, 8.62 + 0.14 * k), (c0, 8.62 + 0.14 * k), (c0, 8)], GRN, w, op, "7 4")
    # drains -> J2
    for k, (q, c0, nr, r100, r10k, dpin, out) in enumerate(GATES):
        d.wire([(c0 + 1, 8), (c0 + 1, 7.35 - 0.2 * k), (J2[out], 7.35 - 0.2 * k), (J2[out], 5)], RED, w, op)
    # source bus -> J2 GND
    d.wire([(2, 8), (2, 8.45), (12, 8.45), (12, 8)], BLK, w + 3, op)
    d.wire([(12, 8), (12.45, 7.6), (12.45, 5.5), (12, 5)], BLK, w + 3, op)
    # LCD header
    d.wire([(2, 21), (2, 21.5), (0, 21.5), (0, 21)], BLK, w, op)
    d.wire([(3, 21), (3, 20.5), (5.6, 20.5), (6, 20)], ORG, w, op)
    for c, apin in ((4, "A4"), (5, "A5")):
        ar = pin_row(HDR_L, apin)
        d.wire([(c, 21), (c, ar + 0.05), (XL, ar)], BLUE if apin == "A4" else GRN, w, op)
    # J5 push buttons
    for c, lab, pin in BUTTONS:
        lst = HDR_R if pin.startswith("D") else HDR_L
        pr = pin_row(lst, pin)
        if pin.startswith("D"):
            k = 11 - c                    # NEXT k=0 (inner), AUTO k=1 (outer)
            y = 18.3 + 0.25 * k
            x = 14.15 + 0.2 * k
            d.wire([(c, 18), (c, y), (x, y), (x, pr), (XR, pr)], MAG, w, op)
        else:
            d.wire([(c, 18), (c, 18.65), (6.5, 18.65), (6.5, 19.0), (-1.1, 19.0), (-1.1, pr), (XL, pr)], MAG, w, op)
    # mode LEDs: D9 -> M13, D8 -> M16
    for m, lref, cname, fill, rref, mode, pin in MODE_LEDS:
        pr = pin_row(HDR_R, pin)
        if pin == "D9":
            d.wire([(XR, pr), (12.45, pr), (12, m)], CYAN, w, op)
        else:
            d.wire([(XR, pr), (14.0, pr), (14.0, m), (12, m)], CYAN, w, op)
    # J1 power
    d.wire([(9, 21), (9, 20.5), (7.3, 20.5), (7, 20)], BLK, w, op)
    d.wire([(11, 21), (11, 21.55), (13, 21.55), (13, 21)], ORG, w, op)


def parts(d):
    # sense terminal + top resistors
    terminal(d, [0, 2, 4], 0, ["72V+", "48V+", "12V+"], "J3 · battery sense (via fuses F4/F3/F2)", "#a23a2e")
    for bank, tc, (rt, v), nr, rb, cc, apin in SENSE:
        bridge(d, (tc, 0), (tc, 2))
        resistor(d, (tc, 2), (tc, 6), rt, v)
        # node + local GND
        bridge(d, (2, nr), (3, nr))
        d.line((0, nr + 1), (3, nr + 1), "#e6e6e6", 2.6)            # bare link to GND rail
        d.dot(0, nr + 1, "#c0c0c0", 4)
        d.dot(3, nr + 1, "#c0c0c0", 4)
        resistor(d, (4, nr), (4, nr + 1), rb, "10k")
        cap(d, (5, nr), (5, nr + 1), cc)
        d.text(4.6, nr - 0.45, f"{rb} 10k · {cc}", 9, col="#ffffff", bold=True, dy=-1)
        d.text(1.0, nr + 0.45, f"{bank}", 9, col="#ffd37a", bold=True, dy=3)
    # MOSFETs + J2
    terminal(d, [6, 8, 10, 12], 5, ["OUT3", "OUT2", "OUT1", "GND"], "J2 · to relay coils (−) and control GND")
    for q, c0, nr, r100, r10k, dpin, out in GATES:
        mosfet(d, c0, 8, q)
        resistor(d, (8, nr), (7, nr), r10k, "10k")
        resistor(d, (10, nr), (11, nr), r100, "100Ω")
        bridge(d, (11, nr), (12, nr))
        d.text(9.5, nr - 0.45, f"{r10k} 10k · {r100} 100Ω", 9, col="#ffffff", bold=True, dy=-1)
    for nr, lref, cname, fill, rref, bank, pin in LEDS:
        lr = nr + 1
        bridge(d, (11, nr), (11, lr))
        resistor(d, (11, lr), (10, lr), rref, "330Ω")
        led(d, (8, lr), (7, lr), fill)
        d.text(9.85, lr + 0.42, f"{lref} {cname} · {rref} 330Ω", 8.5, col="#ffd37a", bold=True, dy=3)
    for m, lref, cname, fill, rref, mode, pin in MODE_LEDS:
        bridge(d, (11, m), (12, m))
        resistor(d, (11, m), (10, m), rref, "330Ω")
        led(d, (8, m), (7, m), fill)
        d.text(6.62, m, f"{mode} {cname}", 8.5, "end", "#ffd37a", True, dy=3)
    bridge(d, (7, 8), (7, 9))
    header4(d, [2, 3, 4, 5], 21, ["GND", "VCC", "SDA", "SCL"])
    d.text(3.5, 22.65, "J4 · LCD", 10, col="#ffd37a", bold=True)
    header4(d, [8, 9, 10, 11], 18, ["GND", "TMR", "AUTO", "NEXT"])
    bridge(d, (7, 18), (8, 18))
    d.text(6.75, 18, "J5", 10, "end", col="#ffd37a", bold=True, dy=4)
    terminal(d, [9, 11], 21, ["GND", "+5V"], "J1")
    d.text(10, 22.65, "J1 · 5 V from buck U1", 10, col="#ffd37a", bold=True)


def svg_wrap(d, title):
    body = "\n".join(d.o)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="{title}" '
            f'style="font-family:\'IBM Plex Sans\',Arial,sans-serif">\n<rect width="{W}" height="{H}" fill="#ffffff"/>\n{body}\n</svg>')


def top_svg():
    d = Draw(False)
    board(d)
    wires(d, 0.28, 2.5)
    parts(d)
    d.text(W / 2, H - 14, "TOP VIEW · parts side · faint lines = wires on the underside", 12, col=BLK, bold=True, px=True)
    return svg_wrap(d, "Shield top view, part placement")


def bottom_svg():
    d = Draw(True)
    board(d)
    # component legs as pads
    for bank, tc, (rt, v), nr, rb, cc, apin in SENSE:
        for p in ((tc, 0), (tc, 2), (tc, 6), (4, nr), (4, nr + 1), (5, nr), (5, nr + 1), (0, nr + 1), (3, nr + 1)):
            d.dot(*p, "#c0c0c0", 4.5)
        bridge(d, (tc, 0), (tc, 2))
        bridge(d, (2, nr), (3, nr))
    for q, c0, nr, r100, r10k, dpin, out in GATES:
        for i in range(3):
            d.dot(c0 + i, 8, "#c0c0c0", 4.5)
        for p in ((8, nr), (7, nr), (10, nr), (11, nr)):
            d.dot(*p, "#c0c0c0", 4.5)
        bridge(d, (11, nr), (12, nr))
        d.text(c0 + 1, 9.15, q, 9, col="#ffffff", bold=True)
    for nr, lref, cname, fill, rref, bank, pin in LEDS:
        for p in ((8, nr + 1), (7, nr + 1), (10, nr + 1), (11, nr + 1)):
            d.dot(*p, fill if p[0] in (7, 8) else "#c0c0c0", 4.5)
        bridge(d, (11, nr), (11, nr + 1))
    for m, lref, cname, fill, rref, mode, pin in MODE_LEDS:
        for p in ((8, m), (7, m), (10, m), (11, m), (12, m)):
            d.dot(*p, fill if p[0] in (7, 8) else "#c0c0c0", 4.5)
        bridge(d, (11, m), (12, m))
    bridge(d, (7, 8), (7, 9))
    for c in (6, 8, 10, 12):
        d.dot(c, 5, "#c0c0c0", 4.5)
    for c in (2, 3, 4, 5, 9, 11):
        d.dot(c, 21, "#c0c0c0", 4.5)
    for c in (8, 9, 10, 11):
        d.dot(c, 18, "#d8b44a", 4.5)
    bridge(d, (7, 18), (8, 18))
    wires(d, 1.0, 3)
    d.text(W / 2, H - 14, "BOTTOM VIEW · solder side · mirrored: flip the board left-to-right", 12, col=BLK, bold=True, px=True)
    return svg_wrap(d, "Shield bottom view, wiring")


def placement_rows():
    rows = [("J3", "3-way screw terminal, 5.08 mm", "A1 = 72V+, C1 = 48V+, E1 = 12V+ (wires come in from the top edge)")]
    for bank, tc, (rt, v), nr, rb, cc, apin in SENSE:
        rows.append((rt, f"{v} 1 % (lying flat)", f"{name(tc, 2)}–{name(tc, 6)}; bridge {name(tc, 0)}–{name(tc, 2)} to the terminal"))
    for bank, tc, (rt, v), nr, rb, cc, apin in SENSE:
        rows.append((f"{rb}, {cc}", f"10k 1 % standing + 100 nF ({bank})",
                     f"{rb} {name(4, nr)}–{name(4, nr + 1)}, {cc} {name(5, nr)}–{name(5, nr + 1)}; "
                     f"bare link {name(0, nr + 1)}–{name(3, nr + 1)}; bridge {name(2, nr)}–{name(3, nr)}; "
                     f"wire {name(tc, 6)} → {name(2, nr)}; wire {name(3, nr)} → {apin}"))
    rows.append(("Q1–Q3", "IRLZ44N standing, writing facing row 22, metal tabs must not touch",
                 "Q3 A9/B9/C9 · Q2 F9/G9/H9 · Q1 K9/L9/M9 (G/D/S)"))
    rows.append(("J2", "4-way screw terminal, 5.08 mm", "G6 = OUT3, I6 = OUT2, K6 = OUT1, M6 = GND"))
    for q, c0, nr, r100, r10k, dpin, out in GATES:
        rows.append((f"{r100}, {r10k}", f"100 Ω + 10k standing ({q})",
                     f"{r10k} {name(8, nr)}–{name(7, nr)} (GND rail), {r100} {name(10, nr)}–{name(11, nr)}; "
                     f"bridge {name(11, nr)}–{name(12, nr)}; wire {dpin} → {name(12, nr)}; wire {name(9, nr)} → {q} gate {name(c0, 8)}; "
                     f"drain {name(c0 + 1, 8)} → J2 {out}"))
    for nr, lref, cname, fill, rref, bank, pin in LEDS:
        lr = nr + 1
        rows.append((f"{lref}, {rref}", f"5 mm {cname} LED + 330 Ω standing ({bank} charging)",
                     f"bridge {name(11, nr)}–{name(11, lr)} (to the {pin} node); {rref} {name(11, lr)}–{name(10, lr)}; "
                     f"LED long leg (+) {name(8, lr)}, short leg (flat side) {name(7, lr)} on the GND rail"))
    for m, lref, cname, fill, rref, mode, pin in MODE_LEDS:
        rows.append((f"{lref}, {rref}", f"5 mm {cname} LED + 330 Ω standing ({mode} mode)",
                     f"wire {pin} → {name(12, m)}; bridge {name(12, m)}–{name(11, m)}; {rref} {name(11, m)}–{name(10, m)}; "
                     f"LED long leg (+) {name(8, m)}, short leg (flat side) {name(7, m)} on the GND rail"))
    rows.append(("—", "Source bus, thick wire 0.5 mm² or more", "C9 → H9 → M9 → M6 (J2 GND); bridge H9–H10 to the GND rail"))
    rows.append(("J4", "4-pin male header for the LCD", "C22 GND → A22 rail, D22 VCC → G21 5V rail, E22 SDA → A4, F22 SCL → A5"))
    rows.append(("J5", "4-pin male header for the push buttons",
                 "I19 GND (bridge H19–I19 to the GND rail), J19 TIMER → A3, K19 AUTO → D5, L19 NEXT → D6"))
    rows.append(("SW1–SW3", "Push buttons on the box lid (normally open)",
                 "One leg of each button to J5 AUTO / NEXT / TIMER, the other legs together to J5 GND. No resistors: the sketch uses the internal pull-ups."))
    rows.append(("J1", "2-way screw terminal, 5.08 mm", "J22 GND → H21 rail, L22 +5V → N22 5V rail"))
    return rows


if __name__ == "__main__":
    for fn, data in (("shield_top.svg", top_svg()), ("shield_bottom.svg", bottom_svg())):
        with open(os.path.join(HERE, fn), "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + data)
    print("ok")
