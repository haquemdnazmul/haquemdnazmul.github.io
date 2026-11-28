"""Final schematic of the solar selector as built (2026-11-28): one sheet, PV side + control side.
Run:  py -3.12 make_final_schematic.py  ->  Final_Package/drawings/final_schematic.svg
"""
import os
import make_schematic as ms
from make_schematic import Svg, RED, BLUE, GRN, ORG, BLK, GRY, MAG, CYAN

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "drawings", "final_schematic.svg")


def gnd(s, x, y):
    s.line([(x, y), (x, y + 8)], BLK, 2)
    for dx, dy in ((10, 8), (6, 12), (2, 16)):
        s.line([(x - dx, y + dy), (x + dx, y + dy)], BLK, 2)


def led_left(s, x_anode, y, fill):
    """Horizontal LED, anode on the right (x_anode), cathode 18 px to the left."""
    xa, xk = x_anode, x_anode - 18
    s.path(f"M{xa} {y-9} L{xa} {y+9} L{xk} {y} Z", fill=fill, w=1.4)
    s.line([(xk, y - 9), (xk, y + 9)], w=2.5)
    for dx in (0, 7):
        s.line([(xk + 8 + dx, y - 11), (xk + 3 + dx, y - 19)], w=1.2)
    return xk


def button(s, x_right, y, label):
    """Push button between x_right and x_right-40."""
    s.term(x_right, y, MAG)
    s.term(x_right - 40, y, BLK)
    s.line([(x_right - 6, y - 9), (x_right - 34, y - 9)], BLK, 2.2)
    s.line([(x_right - 20, y - 9), (x_right - 20, y - 19)], BLK, 1.6)
    s.line([(x_right - 27, y - 19), (x_right - 13, y - 19)], BLK, 1.6)
    s.text(x_right - 20, y - 24, label, 10, "middle", True)
    return x_right - 40


def sheet():
    s = Svg(1600, 1180)
    s.text(24, 34, "SOLAR CHARGER SELECTOR — FINAL SCHEMATIC (as built)", 20, bold=True)
    s.text(24, 54, "Dots are connections; wires that cross without a dot (or with a hop) are not connected. ⏚ = control GND.", 11, col=GRY)

    # ================================================================ A: PV side
    s.text(24, 84, "A · PV SIDE — one relay per controller switches PV+; PV− goes to every controller (common-negative controllers only)", 12, bold=True, col=GRY)
    PVP, PVN = 130, 190
    s.box(30, 100, 150, 110, "PV ARRAY", ["Voc set in sketch", "(PANEL_VOC)"], RED)
    s.line([(180, PVP), (1570, PVP)], RED, 3.5)
    s.line([(180, PVN), (1570, PVN)], BLUE, 3.5)
    s.text(190, PVP - 8, "PV+ BUS", 10, bold=True, col=RED)
    s.text(190, PVN + 16, "PV− BUS", 10, bold=True, col=BLUE)

    # panel-voltage divider -> A5
    DX = 300
    s.dot(DX, PVP, RED)
    s.path(f"M{DX} {PVP} V{PVN - 8} A8 8 0 0 1 {DX} {PVN + 8} V212", RED, 2)
    s.rect(DX - 8, 212, 16, 36, BLK, 1.6)
    s.line([(DX, 212), (DX, 248)], BLK, 1.2)
    s.text(DX + 14, 228, "F5", 11, bold=True)
    s.text(DX + 14, 241, "0.5 A", 9, col=GRY)
    s.res_v(DX, 248, 340, "R18", "220k 1%")
    s.dot(DX, 340, ORG)
    s.res_v(DX, 340, 430, "R19", "10k 1%")
    gnd(s, DX, 430)
    xc, xz = DX + 60, DX + 120
    s.line([(DX, 340), (xz + 70, 340)], ORG, 2)
    s.dot(xc, 340, ORG)
    s.line([(xc, 340), (xc, 380)], BLK, 2)
    s.line([(xc - 14, 380), (xc + 14, 380)], BLK, 3)
    s.line([(xc - 14, 388), (xc + 14, 388)], BLK, 3)
    s.line([(xc, 388), (xc, 430)], BLK, 2)
    gnd(s, xc, 430)
    s.text(xc + 18, 380, "C4", 11, bold=True)
    s.text(xc + 18, 393, "100 nF", 9, col=GRY)
    s.dot(xz, 340, ORG)
    s.diode_up(xz, 340, 430, "ZD1", "5.1 V")
    gnd(s, xz, 430)
    s.term(xz + 73, 340, ORG)
    s.text(xz + 70, 330, "→ A5", 12, "end", True, ORG)

    # controllers
    CXA = [760, 1040, 1320]
    names = ("12 V", "48 V", "72 V")
    for i, cx in enumerate(CXA):
        xp, xn = cx - 60, cx + 60
        k = ("K1", "K3", "K5")[i]
        s.path(f"M{xp} {PVP} V{PVN - 8} A8 8 0 0 1 {xp} {PVN + 8} V232", RED, 3.5)
        s.dot(xp, PVP, RED)
        s.contact(xp, 236, 284, k, RED)
        s.text(xp + 26, 262, "coil: section B", 9, col=GRY)
        s.line([(xp, 288), (xp, 310)], RED, 3.5)
        s.line([(xn, PVN), (xn, 310)], BLUE, 3.5)
        s.dot(xn, PVN, BLUE)
        s.rect(cx - 110, 310, 220, 70, BLK, 1.8, rx=4)
        s.text(cx, 350, f"{names[i]} MPPT CONTROLLER", 12, "middle", True)
        s.text(xp, 325, "PV+", 9, "middle", col=RED)
        s.text(xn, 325, "PV−", 9, "middle", col=BLUE)
        s.text(xp, 374, "BAT+", 9, "middle", col=RED)
        s.text(xn, 374, "BAT−", 9, "middle")
        s.line([(xp, 380), (xp, 420)], RED, 2.5)
        s.line([(xn, 380), (xn, 420)], BLK, 2.5)
        s.rect(cx - 90, 420, 180, 30, BLK, 1.4, rx=3)
        s.text(cx, 440, f"{names[i]} battery bank", 11, "middle")
    # 12 V controller LOAD output feeds the control circuit
    lx = CXA[0] - 110
    s.line([(lx, 330), (560, 330), (560, 600)], RED, 2.5)
    s.text(lx - 6, 325, "LOAD+", 9, "end", col=RED)
    s.line([(lx, 362), (590, 362), (590, 378)], BLK, 2.5)
    gnd(s, 590, 378)
    s.text(lx - 6, 358, "LOAD−", 9, "end")
    s.rect(552, 470, 16, 36, BLK, 1.6)
    s.line([(560, 470), (560, 506)], BLK, 1.2)
    s.text(574, 486, "F1 1 A", 11, bold=True)
    s.text(574, 499, "LOAD set to 24 h / always on", 9, col=GRY)
    s.text(760, 476, "Inside each common-negative controller PV− = BAT− = LOAD−, so ⏚ (control GND) = PV−.", 10, col=GRY)
    s.text(760, 490, "Check each controller with a meter: PV− and BAT− must beep together.", 10, col=GRY)
    s.add('<line x1="20" y1="540" x2="1580" y2="540" stroke="#999" stroke-width="1" stroke-dasharray="6 5"/>')

    # ================================================================ B: control side
    s.text(24, 566, "B · CONTROL — Arduino Uno and the proto shield", 12, bold=True, col=GRY)
    BUS = 600
    s.line([(80, BUS), (1570, BUS)], RED, 2.5)
    s.dot(560, BUS, RED)
    s.text(1570, BUS - 8, "+12 V CONTROL (LOAD+ through F1)", 11, "end", True, RED)

    # buck
    s.box(80, 630, 130, 76, "U1 BUCK", ["12 V → 5 V"])
    s.line([(100, BUS), (100, 630)], RED, 2)
    s.dot(100, BUS, RED)
    s.line([(100, 706), (100, 716)], BLK, 2)
    gnd(s, 100, 716)
    s.line([(210, 650), (400, 650)], ORG, 2)
    s.text(216, 644, "OUT+ 5 V", 9, col=ORG)

    # Arduino
    s.rect(400, 630, 140, 400, BLK, 1.8, rx=4, fill="#e8f1ec")
    s.text(470, 656, "U2", 13, "middle", True)
    s.text(470, 672, "ARDUINO UNO", 11, "middle", True)
    s.text(408, 654, "5V", 10, bold=True, col=ORG)
    s.line([(470, 1030), (470, 1044)], BLK, 2)
    gnd(s, 470, 1044)
    s.text(476, 1024, "GND", 10, bold=True)

    # A5 from section A
    s.text(408, 704, "A5", 11, bold=True, col=ORG)
    s.line([(400, 700), (352, 700)], ORG, 2)
    s.term(349, 700, ORG)
    s.text(345, 690, "from panel sense (A)", 10, "end", True, ORG)

    # LCD
    s.rect(120, 730, 140, 74, BLK, 1.6, rx=4, fill="#eef3d6")
    s.text(190, 752, "DS1 16x2 LCD", 11, "middle", True)
    s.text(190, 766, "I2C backpack 0x27", 9, "middle", col=GRY)
    for y, lab, pin, col in ((780, "SDA", "A4", CYAN), (796, "SCL", "D7", CYAN)):
        s.text(254, y + 4, lab, 9, "end", col=GRY)
        s.line([(260, y), (400, y)], col, 2)
        s.text(408, y + 4, pin, 11, bold=True, col=col)
    s.line([(190, 730), (190, 716), (230, 716), (230, 650)], ORG, 1.6)
    s.dot(230, 650, ORG)
    s.text(196, 726, "VCC", 9, col=GRY)
    s.line([(150, 804), (150, 812)], BLK, 2)
    gnd(s, 150, 812)

    # buttons
    for y, pin, lab in ((850, "D5", "SW1 AUTO"), (890, "D6", "SW2 NEXT"), (930, "A3", "SW3 TIMER")):
        s.text(408, y + 4, pin, 11, bold=True, col=MAG)
        s.line([(400, y), (342, y)], MAG, 2)
        xl = button(s, 338, y, lab)
        s.line([(xl - 4, y), (270, y)], BLK, 2)
        gnd(s, 270, y)
    s.text(150, 872, "no resistors:", 9, col=GRY)
    s.text(150, 884, "internal pull-ups", 9, col=GRY)

    # mode LEDs
    for y, pin, ref, fill, rref, lab in ((975, "D9", "LED4", "#ffffff", "R16", "white = AUTO"),
                                        (1010, "D8", "LED5", "#e53935", "R17", "red = TIMER")):
        s.text(408, y + 4, pin, 11, bold=True, col=CYAN)
        s.line([(400, y), (382, y)], CYAN, 2)
        s.rect(342, y - 6, 40, 12)
        s.text(362, y - 10, f"{rref} 330Ω", 9, "middle", True)
        s.line([(342, y), (334, y)])
        xk = led_left(s, 334, y, fill)
        s.line([(xk, y), (270, y)], BLK, 2)
        gnd(s, 270, y)
        s.text(240, y + 4, f"{ref} {lab}", 9, "end", col=GRY)

    # channels
    CXB = [770, 1090, 1410]
    lanes = [880, 920, 960]
    chans = (("Q1", "K1", "R1", "R4", "D1", "D2", "LED1", "green", "#2ecc40", "R13", "12 V"),
             ("Q2", "K3", "R2", "R5", "D3", "D3", "LED2", "yellow", "#ffd400", "R14", "48 V"),
             ("Q3", "K5", "R3", "R6", "D5", "D4", "LED3", "blue", "#2f7bff", "R15", "72 V"))
    for idx, (q, k, rg, rp, dd, pin, led, lc, lf, rl, nm) in enumerate(chans):
        cx, lane = CXB[idx], lanes[idx]
        s.text(540 - 8, lane + 4, pin, 11, "end", True, GRN)
        s.dot(cx, BUS, RED)
        s.line([(cx, BUS), (cx, 640)], RED, 2)
        s.coil(cx, 640, 690, k)
        s.line([(cx, 690), (cx, 730)], BLK, 2)
        xd = cx + 40
        s.line([(cx, 620), (xd, 620)], BLK, 1.8)
        s.dot(cx, 620)
        s.diode_up(xd, 620, 712, dd, "1N4007")
        s.line([(xd, 712), (cx, 712)], BLK, 1.8)
        s.dot(cx, 712)
        gy = s.nmos(cx, 730, 790, q, "IRLZ44N")
        s.line([(cx, 790), (cx, 804)], BLK, 2)
        gnd(s, cx, 804)
        node = cx - 80
        s.line([(cx - 16, gy), (node, gy)], GRN, 2)
        s.dot(node, gy, GRN)
        s.res_h(cx - 170, node, gy, rg, "100Ω", GRN)
        s.res_v(node, gy, 840, rp, "10k", BLK)
        gnd(s, node, 840)
        xl = cx - 200
        s.line([(cx - 170, gy), (xl, gy), (xl, lane), (540, lane)], GRN, 2)
        s.dot(xl, lane, GRN)
        hops = "".join(f" V{ly - 7} A7 7 0 0 1 {xl} {ly + 7}" for ly in lanes if ly > lane)
        y0 = lanes[-1] + 10
        s.path(f"M{xl} {lane}{hops} V{y0}", GRN, 2)
        s.rect(xl - 6, y0, 12, 30)
        s.line([(xl, y0 + 30), (xl, y0 + 38)])
        s.text(xl + 12, y0 + 13, rl, 11, bold=True)
        s.text(xl + 12, y0 + 26, "330Ω", 10)
        s.led_down(xl, y0 + 38, y0 + 66, led, lc, lf)
        s.line([(xl, y0 + 66), (xl, y0 + 74)], BLK, 2)
        gnd(s, xl, y0 + 74)
        s.text(cx + 20, 830, f"relay {k} → {nm} controller PV+", 10, col=GRY)

    s.text(24, 1104, "Only one relay is ever on. Every change: all relays off for 10 s, then one relay on. Each relay coil has its own 1N4007 (stripe to +12 V).", 11, col=GRY)
    s.text(24, 1120, "Relay contacts K1/K3/K5 must be rated for the array's cold Voc in DC. Divider R18: 220k for Voc up to ~110 V, 330k up to ~160 V (set R_TOP_K in the sketch).", 11, col=GRY)
    s.text(24, 1136, "Battery voltage sensing (A0–A2) is not used in this version: a full battery is detected from the panel voltage on A5.", 11, col=GRY)
    s.rect(1240, 1140, 340, 36, BLK, 1.4)
    s.text(1250, 1156, "Solar charger selector · final schematic", 11, bold=True)
    s.text(1250, 1170, "Rev D · 2026-11-28 · code/solar_selector/solar_selector.ino", 10, col=GRY)
    return s.svg("Final schematic of the solar charger selector")


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + sheet())
    print("ok", OUT)

