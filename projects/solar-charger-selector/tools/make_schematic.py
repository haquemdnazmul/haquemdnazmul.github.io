"""Generates the build drawings for the solar charger selector.

Outputs (next to this script):
  sheet1_schematic.svg   full schematic with reference designators and pin numbers
  sheet2_channel.svg     one channel drawn as physical parts (pinouts, diode stripe)
  solar_selector_wiring.html   page with both sheets, wiring list, parts and test steps
Run:  python make_schematic.py
"""
import html
import os

import make_shield_layout as shield

HERE = os.path.dirname(os.path.abspath(__file__))

RED = "#c0392b"      # PV+ and +12 V
BLUE = "#1f4fa0"     # PV-
GRN = "#1e7b45"      # gate signals
MAG = "#c2185b"
CYAN = "#0097a7"
ORG = "#d07a00"      # +5 V
BLK = "#111111"      # GND and symbols
GRY = "#666666"
FONT = "font-family:Consolas,'IBM Plex Mono',monospace"


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.o = w, h, []

    def add(self, s):
        self.o.append(s)

    def line(self, pts, col=BLK, w=2, dash=None):
        p = " ".join(f"{x},{y}" for x, y in pts)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<polyline points="{p}" fill="none" stroke="{col}" stroke-width="{w}" '
                 f'stroke-linecap="round" stroke-linejoin="round"{d}/>')

    def path(self, d, col=BLK, w=2, fill="none"):
        self.add(f'<path d="{d}" fill="{fill}" stroke="{col}" stroke-width="{w}" stroke-linejoin="round"/>')

    def rect(self, x, y, w, h, col=BLK, sw=1.6, fill="#ffffff", rx=0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
                 f'stroke="{col}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, size=12, anchor="start", bold=False, col=BLK):
        wt = "700" if bold else "400"
        self.add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{wt}" fill="{col}" '
                 f'text-anchor="{anchor}" style="{FONT}">{html.escape(s)}</text>')

    def dot(self, x, y, col=BLK):
        self.add(f'<circle cx="{x}" cy="{y}" r="4" fill="{col}"/>')

    def term(self, x, y, col=BLK):
        self.add(f'<circle cx="{x}" cy="{y}" r="3.5" fill="#ffffff" stroke="{col}" stroke-width="1.6"/>')

    def svg(self, label):
        body = "\n".join(self.o)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
                f'role="img" aria-label="{label}">\n<rect width="{self.w}" height="{self.h}" fill="#ffffff"/>\n'
                f'{body}\n</svg>')

    # ---- symbols ----
    def res_h(self, x1, x2, y, ref, val, col=BLK):
        m = (x1 + x2) / 2
        self.line([(x1, y), (m - 20, y)], col)
        self.line([(m + 20, y), (x2, y)], col)
        self.rect(m - 20, y - 7, 40, 14)
        self.text(m, y - 12, f"{ref} {val}", 11, "middle", True)

    def res_v(self, x, y1, y2, ref, val, col=BLK):
        m = (y1 + y2) / 2
        self.line([(x, y1), (x, m - 20)], col)
        self.line([(x, m + 20), (x, y2)], col)
        self.rect(x - 7, m - 20, 14, 40)
        self.text(x - 12, m - 2, ref, 11, "end", True)
        self.text(x - 12, m + 11, val, 10, "end")

    def diode_up(self, x, ytop, ybot, ref, val):
        """Diode with cathode (stripe) at the top."""
        m = (ytop + ybot) / 2
        self.line([(x, ytop), (x, m - 10)])
        self.line([(x, m + 10), (x, ybot)])
        self.path(f"M{x-9} {m+10} L{x+9} {m+10} L{x} {m-10} Z", fill=BLK, w=1)
        self.line([(x - 9, m - 10), (x + 9, m - 10)], w=2.5)
        self.text(x + 12, m - 2, ref, 11, bold=True)
        self.text(x + 12, m + 10, val, 9, col=GRY)

    def led_down(self, x, ytop, ybot, ref, colname, fill):
        """LED, anode at the top, cathode (bar) at the bottom, label on the right."""
        m = (ytop + ybot) / 2
        self.line([(x, ytop), (x, m - 9)])
        self.line([(x, m + 9), (x, ybot)])
        self.path(f"M{x-9} {m-9} L{x+9} {m-9} L{x} {m+9} Z", fill=fill, w=1.4)
        self.line([(x - 9, m + 9), (x + 9, m + 9)], w=2.5)
        for dy in (-6, 2):
            self.line([(x + 11, m + dy), (x + 20, m + dy + 7)], w=1.3)
            self.path(f"M{x+20} {m+dy+7} L{x+14} {m+dy+5} L{x+18} {m+dy+1} Z", fill=BLK, w=1)
        self.text(x + 24, m - 1, ref, 11, bold=True)
        self.text(x + 24, m + 11, colname, 10, col=GRY)

    def fuse_h(self, x1, x2, y, ref, val):
        m = (x1 + x2) / 2
        self.line([(x1, y), (m - 22, y)], RED)
        self.line([(m + 22, y), (x2, y)], RED)
        self.rect(m - 22, y - 8, 44, 16)
        self.line([(m - 22, y), (m + 22, y)], w=1.2)
        self.text(m, y - 13, f"{ref} {val}", 11, "middle", True)

    def battery_v(self, x, ytop, ybot, ref, val):
        """+ at top, - at bottom."""
        m = (ytop + ybot) / 2
        self.line([(x, ytop), (x, m - 8)], RED)
        self.line([(x, m + 8), (x, ybot)], BLK)
        self.line([(x - 18, m - 8), (x + 18, m - 8)], w=2.5)
        self.line([(x - 10, m - 2), (x + 10, m - 2)], w=4)
        self.line([(x - 18, m + 4), (x + 18, m + 4)], w=2.5)
        self.line([(x - 10, m + 10), (x + 10, m + 10)], w=4)
        self.text(x - 24, m - 10, "+", 13, "end", True, RED)
        self.text(x + 26, m - 2, ref, 12, bold=True)
        self.text(x + 26, m + 12, val, 10)

    def contact(self, x, ytop, ybot, ref, col):
        """SPST-NO relay contact, pin 30 on top, pin 87 at the bottom."""
        self.term(x, ytop)
        self.term(x, ybot)
        self.line([(x, ytop), (x + 20, ybot - 8)], BLK, 2.5)
        self.text(x - 12, (ytop + ybot) / 2 + 4, ref, 13, "end", True)
        self.text(x + 8, ytop + 3, "30", 10, col=GRY)
        self.text(x + 8, ybot + 12, "87", 10, col=GRY)

    def coil(self, x, ytop, ybot, ref):
        self.rect(x - 13, ytop, 26, ybot - ytop, sw=1.8)
        self.line([(x - 13, ybot), (x + 13, ytop)], w=1.2)
        self.text(x - 18, (ytop + ybot) / 2 + 4, ref, 13, "end", True)
        self.text(x + 16, ytop + 9, "86", 10, col=GRY)
        self.text(x + 16, ybot - 2, "85", 10, col=GRY)

    def nmos(self, cx, yd, ys, ref, part):
        """N-channel MOSFET. Drain lead enters at (cx, yd), source leaves at (cx, ys), gate at (cx-18, gy)."""
        gy = (yd + ys) / 2
        ch = cx - 8
        self.line([(cx, yd), (cx, gy - 12), (ch, gy - 12)])
        self.line([(ch, gy + 12), (cx, gy + 12), (cx, ys)])
        self.line([(ch, gy), (cx, gy), (cx, gy + 12)])
        for a, b in ((gy - 16, gy - 8), (gy - 4, gy + 4), (gy + 8, gy + 16)):
            self.line([(ch, a), (ch, b)], w=2.5)
        self.line([(cx - 16, gy - 15), (cx - 16, gy + 15)], w=2)
        self.path(f"M{ch+1} {gy} L{ch+8} {gy-4} L{ch+8} {gy+4} Z", fill=BLK, w=1)
        self.add(f'<circle cx="{cx-6}" cy="{gy}" r="21" fill="none" stroke="{BLK}" stroke-width="1.3"/>')
        self.text(cx + 20, gy - 4, ref, 13, bold=True)
        self.text(cx + 20, gy + 10, part, 10)
        self.text(cx + 4, yd + 10, "D", 9, col=GRY)
        self.text(cx + 4, ys - 3, "S", 9, col=GRY)
        self.text(cx - 26, gy - 6, "G", 9, "end", col=GRY)
        return gy

    def box(self, x, y, w, h, title, sub=None, col=BLK, dash=None):
        self.rect(x, y, w, h, col, 1.8, rx=4, dash=dash)
        self.text(x + w / 2, y + 20, title, 13, "middle", True)
        if sub:
            for i, s in enumerate(sub if isinstance(sub, list) else [sub]):
                self.text(x + w / 2, y + 36 + i * 14, s, 10, "middle", col=GRY)


CH = [
    dict(name="12 V", q="Q1", kp="K1", kn="K2", rg="R1", rp="R4", da="D1", db="D2", pin="D2", batt="12 V",
         led="LED1", lc="green", lf="#2ecc40", rl="R13"),
    dict(name="48 V", q="Q2", kp="K3", kn="K4", rg="R2", rp="R5", da="D3", db="D4", pin="D3", batt="48 V",
         led="LED2", lc="yellow", lf="#ffd400", rl="R14"),
    dict(name="72 V", q="Q3", kp="K5", kn="K6", rg="R3", rp="R6", da="D5", db="D6", pin="D4", batt="72 V",
         led="LED3", lc="blue", lf="#2f7bff", rl="R15"),
]
CX = [740, 1060, 1380]


def sheet1():
    s = Svg(1520, 1060)
    s.text(24, 34, "SOLAR CHARGER SELECTOR — SCHEMATIC", 20, bold=True)
    s.text(24, 54, "Dots are connections. Wires that cross without a dot are NOT connected.", 11, col=GRY)

    # ---------- A: PV power ----------
    s.text(24, 84, "A · PV POWER (heavy wire, sized for array current)", 12, bold=True, col=GRY)
    s.box(30, 100, 140, 100, "PV ARRAY", ["Voc ≤ relay DC rating", "and ≤ every charger"], RED)
    s.line([(170, 130), (230, 130)], RED, 3.5)
    s.line([(170, 170), (230, 170)], BLUE, 3.5)
    s.text(176, 124, "PV+", 10, bold=True, col=RED)
    s.text(176, 188, "PV−", 10, bold=True, col=BLUE)
    # 2-pole isolator
    s.rect(230, 110, 80, 80, BLK, 1.6, dash="5 4", rx=3)
    for y, col in ((130, RED), (170, BLUE)):
        s.term(244, y, col)
        s.term(296, y, col)
        s.line([(244, y), (290, y - 14)], BLK, 2.2)
    s.line([(266, 118), (266, 160)], GRY, 1.2, "3 3")
    s.text(270, 210, "Q0 DC isolator", 11, "middle", True)
    s.text(270, 224, "2-pole, recommended", 9, "middle", col=GRY)
    s.line([(296, 130), (1440, 130)], RED, 3.5)
    s.line([(296, 170), (1480, 170)], BLUE, 3.5)
    s.text(320, 122, "PV+ BUS", 10, bold=True, col=RED)
    s.text(320, 186, "PV− BUS", 10, bold=True, col=BLUE)

    for c, cx in zip(CH, CX):
        xp, xn = cx - 60, cx + 60
        # PV+ drop with a hop over the PV- bus
        s.path(f"M{xp} 130 V162 A8 8 0 0 1 {xp} 178 V232", RED, 3.5)
        s.dot(xp, 130, RED)
        s.line([(xn, 170), (xn, 232)], BLUE, 3.5)
        s.dot(xn, 170, BLUE)
        s.contact(xp, 236, 284, c["kp"], RED)
        s.contact(xn, 236, 284, c["kn"], BLUE)
        s.line([(xp, 288), (xp, 330)], RED, 3.5)
        s.line([(xn, 288), (xn, 330)], BLUE, 3.5)
        s.rect(cx - 120, 330, 240, 64, BLK, 1.8, rx=4)
        s.text(cx, 360, f"{c['name']} MPPT CHARGER", 13, "middle", True)
        s.text(xp, 346, "PV+", 9, "middle", col=RED)
        s.text(xn, 346, "PV−", 9, "middle", col=BLUE)
        s.text(xp, 388, "BAT+", 9, "middle", col=RED)
        s.text(xn, 388, "BAT−", 9, "middle", col=BLK)
        s.line([(xp, 394), (xp, 420)], RED, 2.5)
        s.line([(xn, 394), (xn, 420)], BLK, 2.5)
        s.rect(cx - 90, 420, 180, 30, BLK, 1.4, rx=3)
        s.text(cx, 440, f"{c['batt']} battery bank", 11, "middle")
        s.text(cx, 466, "BAT+ → sense divider, BAT− → control GND (sheet 3)", 9, "middle", col=GRY)
    s.add('<line x1="20" y1="478" x2="1500" y2="478" stroke="#999" stroke-width="1" stroke-dasharray="6 5"/>')

    # ---------- B: control ----------
    s.text(24, 506, "B · 12 V CONTROL (relay coils, MOSFETs, Arduino) — separate battery, shares nothing with the PV wiring", 12, bold=True, col=GRY)
    GND = 1000
    BUS = 540
    s.battery_v(70, BUS, 660, "B1", "12 V control")
    s.line([(70, 660), (70, GND)], BLK, 2.5)
    s.fuse_h(70, 180, BUS, "F1", "1 A")
    s.line([(180, BUS), (1490, BUS)], RED, 2.5)
    s.dot(180, BUS, RED)
    s.text(1490, BUS - 8, "+12 V FUSED", 11, "end", True, RED)
    s.line([(40, GND), (1490, GND)], BLK, 2.5)
    s.text(1490, GND - 8, "CONTROL GND (B1 −)", 11, "end", True)
    s.dot(70, GND)

    # buck
    s.box(200, 600, 130, 80, "U1 BUCK", ["12 V → 5 V", "≥ 1 A"])
    s.line([(220, BUS), (220, 600)], RED, 2)
    s.dot(220, BUS, RED)
    s.text(224, 594, "IN+", 9, col=GRY)
    s.line([(220, 680), (220, GND)], BLK, 2)
    s.dot(220, GND)
    s.text(224, 694, "IN−", 9, col=GRY)
    s.line([(330, 625), (400, 625)], ORG, 2)
    s.text(336, 619, "OUT+ 5 V", 9, col=ORG)
    s.line([(330, 660), (360, 660), (360, GND)], BLK, 2)
    s.text(336, 674, "OUT−", 9, col=GRY)
    s.dot(360, GND)

    # arduino
    s.rect(400, 600, 120, 330, BLK, 1.8, rx=4)
    s.text(460, 622, "U2", 13, "middle", True)
    s.text(460, 638, "ARDUINO UNO", 11, "middle", True)
    s.text(408, 629, "5V", 10, bold=True, col=ORG)
    s.line([(460, 930), (460, GND)], BLK, 2)
    s.dot(460, GND)
    s.text(466, 924, "GND", 10, bold=True)
    for k, a in enumerate(("A0", "A1", "A2")):
        y = 690 + k * 22
        s.text(512, y + 4, a, 11, "end", True, ORG)
        s.line([(520, y), (540, y)], ORG, 2)
        s.term(543, y, ORG)
        s.text(550, y + 4, "sheet 3", 9, col=GRY)
    # push buttons SW1-SW3: Arduino pin -> button -> GND (internal pull-ups, no resistors)
    xg = 250
    for k, (sw, lab, pin) in enumerate((("SW1", "AUTO", "D5"), ("SW2", "NEXT", "D6"), ("SW3", "TIMER", "A3"))):
        y = 715 + k * 45
        s.text(408, y + 4, pin, 11, bold=True, col=MAG)
        s.path(f"M400 {y} H368 A8 8 0 0 0 352 {y} H322", MAG, 2)     # hop over the buck OUT− wire
        s.term(318, y, MAG)
        s.term(278, y, BLK)
        s.line([(274, y), (xg, y)], BLK, 2)
        s.line([(312, y - 9), (284, y - 9)], BLK, 2.2)                   # contact bar
        s.line([(298, y - 9), (298, y - 19)], BLK, 1.6)                  # plunger
        s.line([(291, y - 19), (305, y - 19)], BLK, 1.6)
        s.text(298, y - 25, f"{sw} {lab}", 10, "middle", True)
        if k:
            s.dot(xg, y)
    # mode LEDs: pin -> 330R -> LED -> GND
    for y, pin, ref, cname, fill, rref, mname in ((855, "D9", "LED4", "white", "#ffffff", "R16", "AUTO"),
                                                  (900, "D8", "LED5", "red", "#e53935", "R17", "TIMER")):
        s.text(408, y + 4, pin, 11, bold=True, col=CYAN)
        s.path(f"M400 {y} H368 A8 8 0 0 0 352 {y} H340", CYAN, 2)
        s.rect(300, y - 6, 40, 12)
        s.text(320, y - 10, f"{rref} 330Ω", 10, "middle", True)
        s.line([(300, y), (292, y)])
        s.path(f"M292 {y-9} L292 {y+9} L274 {y} Z", fill=fill, w=1.4)
        s.line([(274, y - 9), (274, y + 9)], w=2.5)
        for dx in (0, 7):
            s.line([(282 + dx, y - 11), (277 + dx, y - 19)], w=1.2)
        s.line([(274, y), (xg, y)])
        s.dot(xg, y)
        s.text(258, y + 21, f"{ref} {cname} = {mname}", 9, col=GRY)
    s.line([(xg, 715), (xg, GND)], BLK, 2)
    s.dot(xg, GND)
    s.text(258, 945, "Push buttons,", 9, col=GRY)
    s.text(258, 957, "normally open.", 9, col=GRY)
    s.text(258, 969, "No resistors:", 9, col=GRY)
    s.text(258, 981, "INPUT_PULLUP", 9, col=GRY)
    lanes = [870, 890, 910]
    for c, y in zip(CH, lanes):
        s.text(512, y + 4, c["pin"], 11, "end", True, GRN)

    for c, cx, lane in zip(CH, CX, lanes):
        xp, xn = cx - 60, cx + 60
        for x, k, d in ((xp, c["kp"], c["da"]), (xn, c["kn"], c["db"])):
            s.dot(x, BUS, RED)
            s.line([(x, BUS), (x, 600)], RED, 2)
            s.coil(x, 600, 650, k)
            s.line([(x, 650), (x, 700)], BLK, 2)
            xd = x + 38
            s.line([(x, 576), (xd, 576)], BLK, 1.8)
            s.dot(x, 576)
            s.diode_up(xd, 576, 676, d, "1N4007")
            s.line([(xd, 676), (x, 676)], BLK, 1.8)
            s.dot(x, 676)
        s.line([(xp, 700), (xn, 700)], BLK, 2)
        s.dot(cx, 700)
        s.text(cx, 716, "", 9)
        s.line([(cx, 700), (cx, 730)], BLK, 2)
        gy = s.nmos(cx, 730, 790, c["q"], "IRLZ44N")
        s.line([(cx, 790), (cx, GND)], BLK, 2)
        s.dot(cx, GND)
        gx = cx - 16
        node = cx - 80
        s.line([(gx, gy), (node, gy)], GRN, 2)
        s.dot(node, gy, GRN)
        s.res_h(cx - 160, node, gy, c["rg"], "100Ω", GRN)
        s.line([(cx - 160, gy), (cx - 180, gy), (cx - 180, lane), (520, lane)], GRN, 2)
        # charging LED: pin -> 330R -> LED -> GND (lit while the gate is HIGH)
        xl = cx - 180
        s.dot(xl, lane, GRN)
        y0 = lanes[-1] + 6
        hops = "".join(f" V{ly - 7} A7 7 0 0 1 {xl} {ly + 7}" for ly in lanes if ly > lane)
        s.path(f"M{xl} {lane}{hops} V{y0}", GRN, 2)
        s.rect(xl - 6, y0, 12, 32)
        s.line([(xl, y0 + 32), (xl, y0 + 40)])
        s.text(xl + 12, y0 + 14, c["rl"], 11, bold=True)
        s.text(xl + 12, y0 + 27, "330Ω", 10)
        s.led_down(xl, y0 + 40, y0 + 68, c["led"], c["lc"], c["lf"])
        s.line([(xl, y0 + 68), (xl, GND)], BLK, 2)
        s.dot(xl, GND)
        s.res_v(node, gy, 845, c["rp"], "10k", BLK)
        s.line([(node, 845), (node, GND)], BLK, 2)
        s.dot(node, GND)
        s.text(cx + 12, 812, f"switches {c['name']} charger", 10, col=GRY)

    s.text(24, 1030, "Coil current ≈ 150 mA per relay, ≈ 300 mA per pair. Only one pair is on at a time.", 11, col=GRY)
    s.text(24, 1046, "Diode stripe (cathode) goes to pin 86 / +12 V. Every coil gets its own diode. LED1–LED3 light while their pin is HIGH = that battery charging.", 11, col=GRY)
    # title block
    s.rect(1180, 1012, 320, 40, BLK, 1.4)
    s.text(1190, 1030, "Solar charger selector · Sheet 1 of 4", 11, bold=True)
    s.text(1190, 1045, "Rev B · 2026-11-26 · sketch: solar_selector.ino", 10, col=GRY)
    return s.svg("Full schematic of the solar charger selector")


def sheet2():
    s = Svg(1200, 760)
    s.text(24, 34, "ONE CHANNEL AS REAL PARTS (12 V channel shown; 48 V and 72 V are identical)", 18, bold=True)
    s.text(24, 54, "Channel 2 uses D3, Q2, K3, K4. Channel 3 uses D4, Q3, K5, K6.", 11, col=GRY)

    # Arduino header
    s.rect(40, 110, 150, 230, BLK, 1.8, rx=6, fill="#e8f1ec")
    s.text(115, 134, "ARDUINO UNO", 12, "middle", True)
    s.text(115, 150, "digital header", 10, "middle", col=GRY)
    for i, (lab, col) in enumerate((("D2", GRN), ("D3", GRN), ("D4", GRN), ("GND", BLK), ("5V", ORG))):
        y = 180 + i * 32
        s.rect(170, y - 8, 20, 16, BLK, 1.2, fill="#222")
        s.text(162, y + 4, lab, 12, "end", True, col)

    # IRLZ44N TO-220
    x0 = 470
    s.rect(x0 - 50, 90, 100, 40, BLK, 1.6, fill="#cfd3d6", rx=2)
    s.add(f'<circle cx="{x0}" cy="110" r="9" fill="#ffffff" stroke="{BLK}" stroke-width="1.4"/>')
    s.rect(x0 - 50, 130, 100, 90, BLK, 1.8, fill="#2b2b2b", rx=2)
    s.text(x0, 168, "IRLZ44N", 12, "middle", True, "#ffffff")
    s.text(x0, 186, "Q1 · text faces you", 9, "middle", col="#dddddd")
    legs = {"G": x0 - 30, "D": x0, "S": x0 + 30}
    for k, x in legs.items():
        s.rect(x - 4, 220, 8, 70, BLK, 1, fill="#b9b9b9")
        s.text(x, 306, k, 14, "middle", True)
    s.text(x0, 322, "1=Gate  2=Drain  3=Source", 10, "middle", col=GRY)
    s.text(x0 + 56, 106, "metal tab = Drain", 10, col=GRY)

    # D2 -> 100R -> G
    gyy = 360
    s.line([(190, 180), (230, 180), (230, gyy)], GRN, 2.5)
    s.res_h(230, 400, gyy, "R1", "100 Ω", GRN)
    s.line([(400, gyy), (legs["G"], gyy), (legs["G"], 290)], GRN, 2.5)
    s.dot(legs["G"], gyy, GRN)
    # 10k G-S
    s.line([(legs["G"], gyy), (legs["G"], 400), (legs["G"] + 10, 400)], BLK, 2)
    s.rect(legs["G"] + 10, 393, 50, 14, BLK, 1.4, fill="#d9c27a")
    s.text(legs["G"] + 35, 425, "R4 10 kΩ  G→S", 10, "middle", True)
    s.line([(legs["G"] + 60, 400), (legs["S"], 400), (legs["S"], 290)], BLK, 2)
    s.dot(legs["S"], 400)
    # S -> GND bus
    s.line([(legs["S"], 400), (legs["S"], 640)], BLK, 2.5)
    s.line([(190, 276), (215, 276), (215, 640)], BLK, 2.5)
    s.line([(60, 640), (1160, 640)], BLK, 3)
    s.dot(legs["S"], 640)
    s.dot(215, 640)
    s.text(60, 660, "CONTROL GND BUS → 12 V control battery −  (also buck IN−/OUT−)", 11, bold=True)

    # drain stub with a hop over the source wire
    s.path(f"M{legs['D']} 290 V342 H{legs['S']-8} A8 8 0 0 1 {legs['S']+8} 342 H560 V470 H600", BLK, 2.5)
    s.text(606, 474, "Q1 Drain → K1 pin 85 + K2 pin 85", 11, bold=True)

    # relays: pin-side view with what each pin connects to
    def relay(x, y, ref, pv, col, d):
        s.rect(x, y, 170, 170, BLK, 1.8, fill="#f4f4f4", rx=6)
        s.text(x + 85, y + 20, f"{ref} (pin side)", 11, "middle", True)
        pins = {"30": (x + 85, y + 140), "87": (x + 85, y + 50), "85": (x + 35, y + 95), "86": (x + 135, y + 95)}
        for n, (px, py) in pins.items():
            if n in ("30", "87"):
                s.rect(px - 14, py - 4, 28, 8, BLK, 1, fill="#b9b9b9")
                s.text(px, py + 22, n, 13, "middle", True)
            else:
                s.rect(px - 4, py - 14, 8, 28, BLK, 1, fill="#b9b9b9")
                s.text(px, py - 20, n, 13, "middle", True)
        lines = [(f"87 → 12 V charger {pv}", col), (f"30 ← {pv} bus", col),
                 ("86 → +12 V fused, diode stripe", RED), ("85 → Q1 drain, diode plain end", BLK)]
        for i, (t, c) in enumerate(lines):
            s.text(x, y + 196 + i * 17, t, 11, bold=True, col=c)
        yd = y + 282
        s.text(x + 6, yd + 4, "85", 11, bold=True)
        s.line([(x + 26, yd), (x + 50, yd)], GRY, 2)
        s.rect(x + 50, yd - 8, 60, 16, BLK, 1, fill="#333", rx=2)
        s.rect(x + 98, yd - 8, 8, 16, BLK, 0, fill="#e6e6e6")
        s.line([(x + 110, yd), (x + 134, yd)], GRY, 2)
        s.text(x + 138, yd + 4, "86", 11, bold=True)
        s.text(x, yd + 24, f"{d} 1N4007, band (stripe) on 86", 10, col=GRY)

    relay(660, 110, "K1", "PV+", RED, "D1")
    relay(960, 110, "K2", "PV−", BLUE, "D2")

    s.rect(640, 520, 520, 70, "#a96a00", 1.4, fill="#fff6e3", rx=4)
    s.text(652, 542, "Relay pin POSITIONS differ between brands.", 11, "start", True, "#7a4c00")
    s.text(652, 560, "Always go by the numbers molded on the relay body:", 11, col="#7a4c00")
    s.text(652, 578, "85/86 = coil, 30 = common, 87 = normally open (87a unused).", 11, col="#7a4c00")
    s.rect(880, 712, 300, 40, BLK, 1.4)
    s.text(890, 730, "Solar charger selector · Sheet 2 of 4", 11, bold=True)
    s.text(890, 745, "Rev B · 2026-11-26", 10, col=GRY)
    return s.svg("One channel drawn with real part pinouts")


SENSE = [
    dict(name="12 V", f="F2", rt="R7", rtv="33k", rb="R10", c="C1", a="A0", ratio=4.3, vmax=15),
    dict(name="48 V", f="F3", rt="R8", rtv="150k", rb="R11", c="C2", a="A1", ratio=16.0, vmax=60),
    dict(name="72 V", f="F4", rt="R9", rtv="220k", rb="R12", c="C3", a="A2", ratio=23.0, vmax=88),
]


def sheet3():
    s = Svg(1200, 640)
    s.text(24, 34, "SHEET 3 · BATTERY VOLTAGE SENSING (automatic switching when a battery is full)", 18, bold=True)
    s.text(24, 54, "Each bank's voltage is divided down to below 5 V and read by an Arduino analog pin.", 11, col=GRY)
    GND = 520
    s.line([(40, GND), (1170, GND)], BLK, 2.5)
    s.text(40, GND + 20, "CONTROL GND — the same bus as sheet 1 (B1 −, Arduino GND, MOSFET sources)", 11, bold=True)
    for i, b in enumerate(SENSE):
        x = 200 + 360 * i
        xp, xn = x + 40, x - 40
        s.rect(x - 80, 90, 160, 50, BLK, 1.8, rx=4)
        s.text(x, 112, f"{b['name']} BANK", 13, "middle", True)
        s.text(xn, 132, "−", 14, "middle", True)
        s.text(xp, 132, "+", 14, "middle", True, RED)
        s.line([(xn, 140), (xn, GND)], BLK, 2.5)
        s.dot(xn, GND)
        s.line([(xp, 140), (xp, 160)], RED, 2)
        s.rect(xp - 8, 160, 16, 36, BLK, 1.6)
        s.line([(xp, 160), (xp, 196)], BLK, 1.2)
        s.text(xp + 14, 176, b["f"], 11, bold=True)
        s.text(xp + 14, 189, "0.5 A, at battery", 9, col=GRY)
        s.res_v(xp, 196, 300, b["rt"], b["rtv"])
        s.dot(xp, 300)
        s.res_v(xp, 300, 404, b["rb"], "10k")
        s.line([(xp, 404), (xp, GND)], BLK, 2)
        s.dot(xp, GND)
        xc = xp + 70
        s.line([(xp, 300), (xp + 160, 300)], ORG, 2)
        s.dot(xc, 300, ORG)
        s.line([(xc, 300), (xc, 346)], BLK, 2)
        s.line([(xc - 14, 346), (xc + 14, 346)], BLK, 3)
        s.line([(xc - 14, 354), (xc + 14, 354)], BLK, 3)
        s.line([(xc, 354), (xc, GND)], BLK, 2)
        s.dot(xc, GND)
        s.text(xc + 18, 346, b["c"], 11, bold=True)
        s.text(xc + 18, 359, "100 nF", 9, col=GRY)
        s.term(xp + 163, 300, ORG)
        s.text(xp + 160, 290, f"→ {b['a']}", 13, "end", True, ORG)
        fs = 5 * b["ratio"]
        s.text(xc + 18, 420, f"Full scale {fs:.0f} V", 10, col=GRY)
        s.text(xc + 18, 434, f"{b['vmax']} V → {b['vmax']/b['ratio']:.2f} V on pin", 10, col=GRY)
    s.text(24, 572, "Use 1 % metal-film resistors. Set CAL[] in the sketch so the Serial Monitor matches a multimeter.", 11, col=GRY)
    s.text(24, 588, "Every bank negative joins the control GND. First check that no bank negative is tied to anything else (vehicle chassis, inverter earth).", 11, col=GRY)
    s.rect(880, 600, 300, 34, BLK, 1.4)
    s.text(890, 616, "Solar charger selector · Sheet 3 of 4", 11, bold=True)
    s.text(890, 629, "Rev B · 2026-11-26", 10, col=GRY)
    return s.svg("Battery voltage sensing dividers")


def sheet4():
    s = Svg(1200, 470)
    s.text(24, 34, "SHEET 4 · 16x2 LCD (I2C backpack module)", 18, bold=True)
    s.text(24, 54, "Four wires. A4/A5 are the Uno's I2C pins; the SDA/SCL pins next to AREF are the same signals.", 11, col=GRY)
    # Arduino
    s.rect(60, 100, 190, 230, BLK, 1.8, rx=6, fill="#e8f1ec")
    s.text(155, 124, "U2 ARDUINO UNO", 12, "middle", True)
    pins = [("GND", 170, BLK, "GND"), ("5V", 205, ORG, "VCC"), ("A4 / SDA", 240, BLUE, "SDA"), ("A5 / SCL", 275, GRN, "SCL")]
    for lab, y, col, other in pins:
        s.rect(230, y - 8, 20, 16, BLK, 1.2, fill="#222")
        s.text(222, y + 4, lab, 12, "end", True, col)
    # LCD module
    s.rect(500, 90, 640, 250, BLK, 1.8, rx=6, fill="#2f6b4c")
    for x in (514, 1126):
        for y in (104, 326):
            s.add(f'<circle cx="{x}" cy="{y}" r="6" fill="#ffffff" stroke="{BLK}" stroke-width="1"/>')
    s.rect(560, 120, 560, 170, BLK, 2, rx=4, fill="#1d1d1d")
    s.rect(580, 140, 520, 130, BLK, 1, rx=2, fill="#b9d34a")
    s.add(f'<text x="600" y="192" font-size="34" fill="#1f2a0f" style="font-family:Consolas,monospace;letter-spacing:2px" xml:space="preserve">AUTO   CHG 48V</text>')
    s.add(f'<text x="600" y="246" font-size="34" fill="#1f2a0f" style="font-family:Consolas,monospace;letter-spacing:2px" xml:space="preserve">48V 55.2V CHG 7m</text>')
    # backpack
    s.rect(430, 140, 70, 160, BLK, 1.6, rx=3, fill="#1b3f8f")
    s.text(465, 316, "PCF8574", 10, "middle", True)
    s.text(465, 330, "backpack", 9, "middle", col=GRY)
    s.add(f'<circle cx="478" cy="155" r="7" fill="#3b6fd8" stroke="#ffffff" stroke-width="1.2"/>')
    s.text(492, 132, "contrast pot", 9, "middle", col=GRY)
    for lab, y, col, other in pins:
        s.rect(422, y - 6, 16, 12, BLK, 1, fill="#d0d0d0")
        s.text(444, y + 4, other, 10, bold=True, col="#ffffff")
        s.line([(250, y), (422, y)], col, 3)
    s.text(336, 160, "GND", 10, "middle", True)
    s.text(336, 198, "+5 V", 10, "middle", True, ORG)
    s.text(336, 233, "SDA", 10, "middle", True, BLUE)
    s.text(336, 268, "SCL", 10, "middle", True, GRN)
    s.text(24, 380, "Line 1: mode and the battery being charged.  Line 2: each battery in turn, every 2 seconds.", 12, bold=True)
    s.text(24, 400, "CHG 7m = charging, 7 minutes until it counts as full · FULL · FLOAT (all full, still connected) · WAIT · LOW (needs charge)", 11, col=GRY)
    s.text(24, 418, "Blank screen: try address 0x3F in the sketch. Row of solid blocks: turn the contrast pot on the backpack.", 11, col=GRY)
    s.rect(880, 428, 300, 34, BLK, 1.4)
    s.text(890, 444, "Solar charger selector · Sheet 4 of 4", 11, bold=True)
    s.text(890, 457, "Rev C · 2026-11-26", 10, col=GRY)
    return s.svg("16x2 LCD wiring")


def sheet6():
    """Panel-voltage sensing on A5 + PV+-only switching (common-negative controllers)."""
    s = Svg(1200, 700)
    s.text(24, 34, "SHEET 6 · PANEL-VOLTAGE SENSING + PV+ ONLY SWITCHING", 18, bold=True)
    s.text(24, 54, "Full detection without battery wires: a charger that has finished stops pulling current, so the panel voltage rises back towards Voc.", 11, col=GRY)
    PVP, PVN, GND = 130, 190, 560
    s.box(30, 100, 150, 110, "PV ARRAY", ["Voc ≤ 110 V", "for 220k / 10k"], RED)
    s.line([(180, PVP), (1160, PVP)], RED, 3.5)
    s.line([(180, PVN), (1160, PVN)], BLUE, 3.5)
    s.text(190, PVP - 8, "PV+ BUS", 10, bold=True, col=RED)
    s.text(190, PVN + 16, "PV− BUS", 10, bold=True, col=BLUE)

    # chargers: one relay each, PV+ only
    for (name, k, q, pin), cx in zip((("12 V", "K1", "Q1", "D2"), ("48 V", "K3", "Q2", "D3"), ("72 V", "K5", "Q3", "D4")),
                                     (600, 820, 1040)):
        xp, xn = cx - 50, cx + 50
        s.path(f"M{xp} {PVP} V{PVN - 8} A8 8 0 0 1 {xp} {PVN + 8} V232", RED, 3.5)
        s.dot(xp, PVP, RED)
        s.contact(xp, 236, 284, k, RED)
        s.text(xp + 26, 262, f"coil ← {q} ({pin})", 9, col=GRY)
        s.line([(xp, 288), (xp, 330)], RED, 3.5)
        s.line([(xn, PVN), (xn, 330)], BLUE, 3.5)
        s.dot(xn, PVN, BLUE)
        s.rect(cx - 90, 330, 180, 64, BLK, 1.8, rx=4)
        s.text(cx, 366, f"{name} MPPT", 13, "middle", True)
        s.text(xp, 345, "PV+", 9, "middle", col=RED)
        s.text(xn, 345, "PV−", 9, "middle", col=BLUE)
        s.text(xp, 389, "BAT+", 9, "middle", col=RED)
        s.text(xn, 389, "BAT−", 9, "middle")
        s.line([(xp, 394), (xp, 430)], RED, 2.5)
        s.line([(xn, 394), (xn, 430)], BLK, 2.5)
        s.rect(cx - 80, 430, 160, 30, BLK, 1.4, rx=3)
        s.text(cx, 450, f"{name} battery", 11, "middle")
        s.line([(xn, 460), (xn, GND)], BLK, 2.5)
        s.dot(xn, GND)
    s.text(1040 + 92, 362, "PV− = BAT−", 9, col=GRY)
    s.text(1040 + 92, 374, "inside", 9, col=GRY)

    # divider on the PV+ bus (before the relays, so Voc is read during the 10 s pause)
    DX = 270
    s.dot(DX, PVP, RED)
    s.path(f"M{DX} {PVP} V{PVN - 8} A8 8 0 0 1 {DX} {PVN + 8} V212", RED, 2)
    s.rect(DX - 8, 212, 16, 36, BLK, 1.6)
    s.line([(DX, 212), (DX, 248)], BLK, 1.2)
    s.text(DX + 14, 228, "F5", 11, bold=True)
    s.text(DX + 14, 241, "0.5 A", 9, col=GRY)
    s.res_v(DX, 248, 340, "R18", "220k 1%")
    s.dot(DX, 340, ORG)
    s.res_v(DX, 340, 440, "R19", "10k 1%")
    s.line([(DX, 440), (DX, GND)], BLK, 2)
    s.dot(DX, GND)
    xc, xz = DX + 60, DX + 120
    s.line([(DX, 340), (xz, 340)], ORG, 2)
    s.dot(xc, 340, ORG)
    s.line([(xc, 340), (xc, 386)], BLK, 2)
    s.line([(xc - 14, 386), (xc + 14, 386)], BLK, 3)
    s.line([(xc - 14, 394), (xc + 14, 394)], BLK, 3)
    s.line([(xc, 394), (xc, GND)], BLK, 2)
    s.dot(xc, GND)
    s.text(xc + 18, 386, "C4", 11, bold=True)
    s.text(xc + 18, 399, "100 nF", 9, col=GRY)
    s.diode_up(xz, 340, 440, "ZD1", "5.1 V zener")
    s.line([(xz, 440), (xz, GND)], BLK, 2)
    s.dot(xz, GND)
    s.text(xz + 12, 470, "(protects A5)", 9, col=GRY)

    # Arduino
    s.rect(40, 280, 130, 170, BLK, 1.8, rx=4, fill="#e8f1ec")
    s.text(105, 304, "ARDUINO", 12, "middle", True)
    s.text(105, 318, "UNO", 12, "middle", True)
    s.line([(DX, 340), (170, 340)], ORG, 2)
    s.text(162, 344, "A5", 12, "end", True, ORG)
    s.text(105, 444, "GND", 10, "middle", True)
    s.line([(105, 450), (105, GND)], BLK, 2)
    s.dot(105, GND)

    s.line([(30, GND), (1160, GND)], BLK, 2.5)
    s.text(30, GND + 20, "CONTROL GND = Arduino GND = every BAT− (= PV− inside each common-negative controller)", 11, bold=True)
    s.text(24, 606, "Only PV+ is switched: one relay per controller (K1, K3, K5). K2, K4, K6 are not needed. Each MOSFET drives one coil, with its own 1N4007.", 11, col=GRY)
    s.text(24, 622, "Needs common-negative controllers: PV− and BAT− must beep together on every controller. Never join PV− on a common-positive controller.", 11, col=GRY)
    s.text(24, 638, "220k/10k reads up to about 115 V (Voc 110 V gives 4.8 V on A5). For Voc 110–160 V use 330k for R18. The tap is on the PV+ bus, before the relays.", 11, col=GRY)
    s.text(24, 654, "Full = panel voltage stays above 95 % of Voc for 15 min while there is good sun. Voc is measured in every 10 s all-off pause.", 11, col=GRY)
    s.rect(880, 664, 300, 34, BLK, 1.4)
    s.text(890, 680, "Solar charger selector · Sheet 6", 11, bold=True)
    s.text(890, 693, "Rev C · 2026-11-28", 10, col=GRY)
    return s.svg("Panel voltage sensing on A5 and PV plus only switching")


def wiring_rows():
    rows = [
        ("Control", "B1 control battery +", "F1 fuse (1 A) in", "1.0 mm² / 18 AWG red", "Fuse within 20 cm of the battery"),
        ("Control", "F1 fuse out", "+12 V fused bus (terminal strip)", "1.0 mm² / 18 AWG red", "Feeds U1 and all six relay pins 86"),
        ("Control", "B1 control battery −", "Control GND bus (terminal strip)", "1.0 mm² / 18 AWG black", ""),
        ("Control", "+12 V fused bus", "U1 buck IN+", "0.5 mm² red", "Set U1 to 5.0 V before connecting the Arduino"),
        ("Control", "Control GND bus", "U1 buck IN−", "0.5 mm² black", ""),
        ("Control", "U1 OUT+ (5.0 V)", "Arduino 5V pin", "0.5 mm² orange", "Or set U1 to 9 V and use the barrel jack / VIN"),
        ("Control", "U1 OUT−", "Arduino GND", "0.5 mm² black", "Shared ground is required"),
    ]
    for i, c in enumerate(CH):
        n = c["name"]
        rows += [
            (n, f"Arduino {c['pin']}", f"{c['rg']} 100 Ω → {c['q']} Gate (left leg)", "jumper / 0.25 mm² green", ""),
            (n, f"{c['q']} Gate", f"{c['rp']} 10 kΩ → {c['q']} Source", "resistor leads", "Solder at the MOSFET"),
            (n, f"Arduino {c['pin']}", f"{c['rl']} 330 Ω → {c['led']} {c['lc']} long leg (+); short leg → GND", "resistor leads", "Lights while this battery is charging"),
            (n, f"{c['q']} Source (right leg)", "Control GND bus", "0.5 mm² black", ""),
            (n, f"{c['q']} Drain (middle leg)", f"{c['kp']} pin 85 and {c['kn']} pin 85", "0.5 mm² black", "One wire splits to both relays"),
            (n, "+12 V fused bus", f"{c['kp']} pin 86 and {c['kn']} pin 86", "0.5 mm² red", ""),
            (n, f"{c['da']} across {c['kp']} 85–86", f"{c['db']} across {c['kn']} 85–86", "diode leads", "Stripe (cathode) on pin 86"),
            (n, f"PV+ bus", f"{c['kp']} pin 30", "PV cable red", "Size for array Isc × 1.25"),
            (n, f"{c['kp']} pin 87", f"{n} charger PV+", "PV cable red", ""),
            (n, f"PV− bus", f"{c['kn']} pin 30", "PV cable black/blue", ""),
            (n, f"{c['kn']} pin 87", f"{n} charger PV−", "PV cable black/blue", ""),
            (n, f"{n} charger BAT+ / BAT−", f"{n} battery bank", "per charger manual", "Never to relay pins 30 or 87"),
        ]
    for b in SENSE:
        n = b["name"]
        rows += [
            (f"{n} sense", f"{n} bank +", f"{b['f']} 0.5 A fuse → {b['rt']} {b['rtv']}", "0.5 mm² red", "Fuse right at the battery terminal"),
            (f"{n} sense", f"{b['rt']} / {b['rb']} junction", f"Arduino {b['a']}", "0.25 mm² orange", f"{b['c']} 100 nF from {b['a']} to GND"),
            (f"{n} sense", f"{b['rb']} 10k other end", "Control GND bus", "0.25 mm² black", ""),
            (f"{n} sense", f"{n} bank −", "Control GND bus", "0.5 mm² black", "Needed so the Arduino can measure it"),
        ]
    rows += [
        ("LCD", "LCD backpack GND", "Arduino GND", "jumper", ""),
        ("LCD", "LCD backpack VCC", "Arduino 5V", "jumper", "Backlight adds ≈ 25 mA"),
        ("LCD", "LCD backpack SDA", "Arduino A4 (SDA)", "jumper", ""),
        ("LCD", "LCD backpack SCL", "Arduino A5 (SCL)", "jumper", ""),
        ("Buttons", "SW1 AUTO, one leg", "Arduino D5 (J5 AUTO)", "jumper", "Other leg to GND. No resistor: internal pull-up"),
        ("Buttons", "SW2 NEXT, one leg", "Arduino D6 (J5 NEXT)", "jumper", "Each press: 12V → 48V → 72V → OFF"),
        ("Buttons", "SW3 TIMER, one leg", "Arduino A3 (J5 TMR)", "jumper", "Press again to change 15 / 30 / 60 / 120 min"),
        ("Buttons", "SW1–SW3 other legs", "Arduino GND (J5 GND)", "jumper", ""),
        ("Mode LEDs", "Arduino D9", "R16 330 Ω → LED4 white long leg (+); short leg → GND", "wire + resistor leads", "White = AUTO mode"),
        ("Mode LEDs", "Arduino D8", "R17 330 Ω → LED5 red long leg (+); short leg → GND", "wire + resistor leads", "Red = TIMER mode. Both off = MANUAL"),
    ]
    rows += [
        ("Panel sense", "PV+ bus (before the relays)", "F5 0.5 A fuse → R18 220 kΩ", "0.5 mm² red", "Sheet 6. Reads Voc during the 10 s pause"),
        ("Panel sense", "R18 / R19 junction", "Arduino A5", "0.25 mm² orange", "C4 100 nF and ZD1 5.1 V zener from A5 to GND"),
        ("Panel sense", "R19 10 kΩ other end", "Control GND", "0.25 mm² black", "PV− must share this GND (common-negative controllers)"),
    ]
    rows += [
        ("PV", "PV array +/−", "Q0 2-pole DC isolator", "PV cable", "Rated above cold Voc"),
        ("PV", "Q0 out +", "PV+ bus (K1, K3, K5 pin 30)", "PV cable red", ""),
        ("PV", "Q0 out −", "PV− bus (K2, K4, K6 pin 30)", "PV cable black/blue", ""),
    ]
    return rows


PAGE_CSS = """
:root{--bg:#eef0ec;--panel:#ffffff;--ink:#1b2220;--muted:#5b6662;--line:#d3d8d2;--pvp:#b3372b;--pvn:#2b58a6;--warnbg:#fbf0d9;--warn:#8a5600;
--display:"IBM Plex Sans Condensed","Arial Narrow",system-ui,sans-serif;--body:"IBM Plex Sans",system-ui,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,Consolas,monospace}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#111513;--panel:#192020;--ink:#e4ebe7;--muted:#97a39e;--line:#2d3633;--pvp:#e86a5c;--pvn:#76a0ea;--warnbg:#352a12;--warn:#f0b23a;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#111513;--panel:#192020;--ink:#e4ebe7;--muted:#97a39e;--line:#2d3633;--pvp:#e86a5c;--pvn:#76a0ea;--warnbg:#352a12;--warn:#f0b23a;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:15px/1.55 var(--body);padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:20px 48px}
.wrap{max-width:1280px;margin:0 auto;display:grid;gap:22px}
h1,h2{font-family:var(--display);margin:0;text-wrap:balance}
h1{font-size:1.9rem}
h2{font-size:1.15rem;letter-spacing:.04em;text-transform:uppercase}
p{margin:0;max-width:75ch}
.muted{color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:16px;min-width:0;display:grid;gap:10px}
.sheet{overflow-x:auto;border:1px solid var(--line);border-radius:4px;background:#ffffff}
.sheet svg{display:block;width:100%;min-width:900px;height:auto}
.two-sheets{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:12px}
.two-sheets .sheet svg{min-width:520px}
.tbl{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font:600 11px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
td.g{font:600 12px var(--mono);white-space:nowrap}
tr.sep td{border-top:2px solid var(--line)}
ol{margin:0;padding-left:1.3em;display:grid;gap:8px;max-width:85ch}
.warn{background:var(--warnbg);color:var(--warn);padding:10px 12px;border-radius:4px;font-size:14px}
.note{background:var(--bg);border:1px solid var(--line);padding:10px 12px;border-radius:4px;font-size:14px}
.files{font:13px var(--mono);color:var(--muted)}
"""


def page(svg1, svg2, svg3, svg4, svg5="", svg6="", svg7=""):
    rows = wiring_rows()
    trs, last = [], None
    for g, a, b, w, n in rows:
        cls = ' class="sep"' if last is not None and g != last else ""
        last = g
        trs.append(f"<tr{cls}><td class=\"g\">{html.escape(g)}</td><td>{html.escape(a)}</td><td>{html.escape(b)}</td>"
                   f"<td>{html.escape(w)}</td><td class=\"muted\">{html.escape(n)}</td></tr>")
    bom = [
        ("6", "K1–K6", "SPST-NO relay, 12 V coil, contacts rated for your PV DC voltage and ≥ 1.25 × Isc"),
        ("3", "Q1–Q3", "IRLZ44N logic-level N-MOSFET, TO-220"),
        ("6", "D1–D6", "1N4007 diode (one across each relay coil)"),
        ("3", "R1–R3", "100 Ω, ¼ W"),
        ("3", "R4–R6", "10 kΩ, ¼ W"),
        ("3", "LED1–LED3", "5 mm LED: LED1 green (12 V), LED2 yellow (48 V), LED3 blue (72 V)"),
        ("3", "R13–R15", "330 Ω, ¼ W (LED resistors)"),
        ("2", "LED4–LED5", "5 mm LED: LED4 white (AUTO mode), LED5 red (TIMER mode)"),
        ("2", "R16–R17", "330 Ω, ¼ W (mode LED resistors)"),
        ("1", "F1", "Inline blade fuse holder + 1 A fuse"),
        ("1", "U1", "12 V → 5 V buck converter, ≥ 1 A (e.g. LM2596 module)"),
        ("1", "U2", "Arduino Uno"),
        ("3", "F2–F4", "Inline fuse holder + 0.5 A fuse (battery sense wires)"),
        ("1", "R7", "33 kΩ 1 % metal film"),
        ("1", "R8", "150 kΩ 1 % metal film"),
        ("1", "R9", "220 kΩ 1 % metal film"),
        ("3", "R10–R12", "10 kΩ 1 % metal film"),
        ("3", "C1–C3", "100 nF ceramic capacitor"),
        ("1", "R18", "220 kΩ 1 % metal film (panel sense, sheet 6; 330 kΩ if Voc is above 110 V)"),
        ("1", "R19", "10 kΩ 1 % metal film (panel sense)"),
        ("1", "C4", "100 nF ceramic capacitor (panel sense)"),
        ("1", "ZD1", "5.1 V zener diode, 0.5 W (protects A5)"),
        ("1", "F5", "Inline fuse holder + 0.5 A fuse (panel sense wire)"),
        ("1", "DS1", "16x2 character LCD with I2C backpack (PCF8574)"),
        ("3", "SW1–SW3", "Push button, normally open, panel mount (AUTO, NEXT, TIMER)"),
        ("1", "—", "Uno prototype shield; screw terminals 5.08 mm: one 3-way, one 4-way, one 2-way; male pin headers"),
        ("1", "B1", "12 V control battery"),
        ("1", "Q0", "2-pole DC isolator / breaker rated above cold Voc (recommended)"),
        ("2", "—", "Terminal strips for +12 V fused bus and control GND bus"),
        ("1", "—", "Perfboard or screw-terminal board for Q1–Q3 and resistors"),
    ]
    shield_rows = "".join(f"<tr><td class=\"g\">{html.escape(a)}</td><td>{html.escape(b)}</td><td>{html.escape(c)}</td></tr>"
                          for a, b, c in shield.placement_rows())
    bom_html = "".join(f"<tr><td class=\"g\">{q}</td><td class=\"g\">{r}</td><td>{html.escape(d)}</td></tr>" for q, r, d in bom)
    return f"""<title>Solar Selector Wiring</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;600&display=swap">
<style>{PAGE_CSS}</style>
<div class="wrap">
<header style="display:grid;gap:6px">
  <h1>Solar Selector Wiring</h1>
  <p class="muted">Build drawings for switching one PV array between a 12 V, 48 V and 72 V charger with six relays, three IRLZ44N MOSFETs and an Arduino Uno. The Arduino measures each battery and moves to the next one when the current battery is full. Three push buttons choose auto, manual or timer mode, three LEDs show which battery is charging, two more show the mode, and a 16x2 display shows what it is doing. Every part has a reference designator, and every relay connection is given by its pin number.</p>
</header>
<div class="warn">Before buying relays: K1–K6 switch the PV array, so their contacts must be rated for its DC voltage. Most 40 A automotive relays are rated for only 14 V DC. For a 90 V array use relays or contactors rated for at least 110 V DC, or stop the chargers before switching.</div>
<section class="panel"><h2>Sheet 1 · Schematic</h2>
<p class="muted">Top half is the PV power wiring, bottom half is the 12 V control circuit. They connect only through the relays.</p>
<div class="sheet">{svg1}</div></section>
<section class="panel"><h2>Sheet 2 · One channel as real parts</h2>
<p class="muted">Shows the IRLZ44N leg order, where the 10 kΩ goes, and which way the diode stripe points.</p>
<div class="sheet">{svg2}</div></section>
<section class="panel"><h2>Sheet 3 · Battery sensing</h2>
<p class="muted">Lets the Arduino see each battery's voltage, so it can move the solar power to the next battery when one is full.</p>
<div class="sheet">{svg3}</div>
<div class="note">How the automatic switching works: the charger stays on one battery until that battery holds its <b>full voltage</b> (14.2 V per 12 V for lead-acid) for 10 minutes. The Arduino then marks it full and switches, break-before-make, to the next battery in the order 12 V → 48 V → 72 V. A full battery is skipped until it drops below its <b>resume voltage</b> (12.4 V per 12 V). When all three are full, the last one stays connected so its charger can float it. Set the full voltage about 0.2 V per 12 V below your charger's absorption setting.</div>
</section>
<section class="panel"><h2>Sheet 4 · 16x2 display</h2>
<p class="muted">Shows which battery is charging and the voltage of each battery.</p>
<div class="sheet">{svg4}</div>
<details><summary style="cursor:pointer;font-weight:600">Display without an I2C backpack (16 pins, parallel wiring)</summary>
<p class="muted" style="margin-top:8px">Set <span class="mono">#define LCD_I2C 0</span> in the sketch and wire it like this. You also need a 10 kΩ potentiometer for contrast and a 220 Ω resistor for the backlight.</p>
<div class="tbl"><table><thead><tr><th>LCD pin</th><th>Name</th><th>Connect to</th></tr></thead><tbody>
<tr><td class="g">1</td><td>VSS</td><td>GND</td></tr>
<tr><td class="g">2</td><td>VDD</td><td>Arduino 5V</td></tr>
<tr><td class="g">3</td><td>V0</td><td>Middle pin of 10 kΩ pot (outer pins to 5V and GND)</td></tr>
<tr><td class="g">4</td><td>RS</td><td>Arduino D7</td></tr>
<tr><td class="g">5</td><td>RW</td><td>GND</td></tr>
<tr><td class="g">6</td><td>E</td><td>Arduino D8</td></tr>
<tr><td class="g">7–10</td><td>D0–D3</td><td>Not connected</td></tr>
<tr><td class="g">11</td><td>D4</td><td>Arduino D9</td></tr>
<tr><td class="g">12</td><td>D5</td><td>Arduino D10</td></tr>
<tr><td class="g">13</td><td>D6</td><td>Arduino D11</td></tr>
<tr><td class="g">14</td><td>D7</td><td>Arduino D12</td></tr>
<tr><td class="g">15</td><td>A (backlight +)</td><td>220 Ω to Arduino 5V</td></tr>
<tr><td class="g">16</td><td>K (backlight −)</td><td>GND</td></tr>
</tbody></table></div></details>
</section>
<section class="panel"><h2>Sheet 5 · Parts on the prototype shield</h2>
<p class="muted">Hole-by-hole placement on the blue Uno prototype shield. Columns A–N, rows 1–22, read with the RESET button at the top left. Grey bars are the strips already on the board: every hole on one bar is connected. The parts side shows where each part sits. The solder side is the same board flipped over, so left and right swap.</p>
<div class="warn">Check before soldering: on a standard Uno, with the shield's text upright, D0 is at the bottom of the right-hand header and A0 is the top pin of the lower left-hand header. If your shield is labelled differently, follow its labels. Also check with a meter that the rails marked GND and 5V really connect to the Arduino GND and 5V pins.</div>
<div class="two-sheets"><div class="sheet">{svg5}</div><div class="sheet">{svg6}</div></div>
<div class="note"><b>Mode buttons (J5):</b> SW1 AUTO charges each battery until it is full, then moves on. SW2 NEXT switches to manual: each press steps 12 V → 48 V → 72 V → OFF. SW3 TIMER moves to the next battery every 30 minutes; press it again to change the time to 60, 120, 15 or 30 minutes. In timer mode a full battery is skipped. Mount the buttons on the box lid and wire them to J5. The display's first line shows the mode: <span class="mono">AUTO</span>, <span class="mono">MANUAL</span> or <span class="mono">TMR30</span>.<br><b>Mode LEDs:</b> LED4 white (D9) is on in AUTO, LED5 red (D8) is on in TIMER, and both are off in MANUAL. They sit in rows 13 and 16, with the short leg in the GND rail (column H).</div>
<div class="note"><b>Charging LEDs:</b> LED1 green = 12 V, LED2 yellow = 48 V, LED3 blue = 72 V. Each LED and its 330 Ω resistor sit on the same Arduino pin as the MOSFET gate (D2, D3, D4), so an LED is on exactly while its battery is charging. No extra pins or code are needed. The long leg (+) goes in column I, and the short leg (flat side of the rim) goes in the GND rail, column H. To mount the LEDs on the box lid instead, run two wires from those holes to each LED.</div>
<div class="tbl"><table><thead><tr><th>Ref</th><th>Part</th><th>Holes</th></tr></thead><tbody>{shield_rows}</tbody></table></div>
<ol>
<li>Solder the flat parts first: R7–R9 and the bare links, then R1–R15 standing, then C1–C3 and LED1–LED3 (long leg in column I).</li>
<li>Make the solder bridges (short silver bars in the drawing). Then the headers J4 and J5, then the screw terminals, and the MOSFETs last.</li>
<li>Run the wires on the solder side. Use thick wire for the black source bus (C9 → H9 → M9 → J2 GND).</li>
<li>Q1–Q3 metal tabs are the drains. They must not touch each other or anything else.</li>
</ol>
</section>
<section class="panel"><h2>Sheet 6 · Panel-voltage sensing</h2>
<p class="muted">Detects a full battery from the panel voltage instead of the battery voltage, so the battery sense wires are not needed. It also shows the simpler power wiring with one relay per controller, switching PV+ only.</p>
<div class="sheet">{svg7}</div>
<div class="note">How it decides "full": in every 10 s all-off pause the Arduino reads the panel's open-circuit voltage (Voc). While a charger is working, it pulls the panel down to about 75–80 % of Voc. When its battery is full the charger stops pulling current, and the panel climbs back above 95 % of Voc. If that lasts 15 minutes while there is good sun, the battery counts as full and the selector moves on.</div>
<div class="warn">Check every controller before joining PV−: with nothing connected, PV− and BAT− must beep together (common negative). If one does not, do not use this wiring for it.</div>
</section>
<section class="panel"><h2>Wiring list</h2>
<p class="muted">Tick each line off as you wire it. Every channel is wired the same way.</p>
<div class="tbl"><table><thead><tr><th>Group</th><th>From</th><th>To</th><th>Wire</th><th>Note</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div></section>
<section class="panel"><h2>Parts</h2>
<div class="tbl"><table><thead><tr><th>Qty</th><th>Ref</th><th>Part</th></tr></thead><tbody>{bom_html}</tbody></table></div></section>
<section class="panel"><h2>Build and test order</h2>
<ol>
<li>Wire the control side only (section B). Leave the PV array, isolator and chargers disconnected.</li>
<li>Power U1 from the control battery and adjust its output to 5.0 V with a multimeter before connecting the Arduino.</li>
<li>Install the “LiquidCrystal I2C” library (Frank de Brabander) from the Library Manager, then upload <span class="files">solar_selector.ino</span>. The display shows “Solar selector / starting...”. Open the Serial Monitor at 9600 baud with “Newline” selected.</li>
<li>Send <b>12</b>, <b>48</b>, <b>72</b>, <b>0</b> (this turns auto mode off). Each pair should click on after a half-second pause. Check continuity between pins 30 and 87 of the selected pair, and that the other pairs read open.</li>
<li>Press each button: AUTO, NEXT (several times) and TIMER. The first line of the display should show the new mode, and the Serial Monitor prints it. The white LED is on in AUTO, the red LED in TIMER, and both are off in MANUAL.</li>
<li>Each time a battery is selected, its LED lights: green 12 V, yellow 48 V, blue 72 V. With <b>0</b> all three are off. An LED that stays dark is probably in backwards.</li>
<li>Press the Arduino reset button. No relay should click while it boots. If one does, check the 10 kΩ resistors.</li>
<li>Connect each charger to its own battery first (most MPPT chargers need the battery before PV).</li>
<li>Wire sheet 3. Send <b>?</b>, compare the printed voltages with a multimeter on each bank, and adjust CAL[] in the sketch.</li>
<li>Wire the PV side with Q0 open: relay pins 87 to the charger PV inputs, then pins 30 to the PV buses.</li>
<li>Send <b>0</b>, close Q0, then select a charger and confirm it starts charging. Check polarity at each charger before closing Q0.</li>
<li>Send <b>auto</b>. The Arduino picks the first battery that is not full and moves on by itself when it is full.</li>
</ol></section>
<p class="files">Files: Solar_Selector/sheet1_schematic.svg · sheet2_channel.svg · sheet3_sensing.svg · sheet4_lcd.svg · shield_top.svg · shield_bottom.svg · sheet6_panel_sense.svg · solar_selector/solar_selector.ino · regenerate with make_schematic.py</p>
</div>
"""


def main():
    s1, s2, s3, s4, s7 = sheet1(), sheet2(), sheet3(), sheet4(), sheet6()
    s5, s6 = shield.top_svg(), shield.bottom_svg()
    for name, data in (("sheet1_schematic.svg", s1), ("sheet2_channel.svg", s2), ("sheet3_sensing.svg", s3), ("sheet4_lcd.svg", s4),
                       ("shield_top.svg", s5), ("shield_bottom.svg", s6), ("sheet6_panel_sense.svg", s7)):
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + data)
    with open(os.path.join(HERE, "solar_selector_wiring.html"), "w", encoding="utf-8") as f:
        f.write(page(s1, s2, s3, s4, s5, s6, s7))
    print("ok")


if __name__ == "__main__":
    main()
