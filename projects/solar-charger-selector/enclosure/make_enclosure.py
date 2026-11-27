"""3D-printable box for the solar selector: Arduino Uno + proto shield + 16x2 I2C display.

Run:  py -3.12 make_enclosure.py      ->  box_base.stl, box_lid.stl, button_plunger.stl, preview.html
Needs: pip install manifold3d numpy

All sizes in mm. Box axes: x = left->right seen from the front, y = front->back, z = up.
Front wall (y = 0) holds the display; the Uno's USB and power jacks come out of the RIGHT wall;
the wires leave through the notch in the BACK wall.
"""
import json
import os
import numpy as np
from manifold3d import Manifold

HERE = os.path.dirname(os.path.abspath(__file__))
SEG = 64

# ------------------------------------------------------------------ settings
T = 2.4            # wall thickness
FLOOR = 2.4        # floor thickness
LID = 2.4          # lid thickness
L, D, H = 96.0, 80.0, 56.0          # inside length (x), depth (y), height (z)
LO, DO = L + 2 * T, D + 2 * T       # outside size
HB = FLOOR + H                      # base height (lid sits on top)

# Arduino Uno (standard 68.58 x 53.34 board, holes from its USB/power-jack corner)
UNO_W, UNO_D = 68.58, 53.34
UNO_HOLES = [(13.97, 2.54), (15.24, 50.80), (66.04, 7.62), (66.04, 35.56)]
STANDOFF_H, STANDOFF_D, SCREW_TAP = 5.0, 6.5, 2.6      # M3 self-tapping screws
LCD_ZONE = 18.0                     # gap between the front wall and the Uno for the display + backpack
BX_RIGHT = T + L - 0.6              # Uno edge on the jack side (right)
BY_FRONT = T + LCD_ZONE             # Uno edge with the digital header (front)
PCB_TOP = FLOOR + STANDOFF_H + 1.6

def uno_to_box(u, v):
    """Uno drawing coords (USB at u=0, digital header at v=53.34) -> box coords (board turned 180 deg)."""
    return BX_RIGHT - u, BY_FRONT + (UNO_D - v)

USB = dict(v=38.1, w=14.0, h=13.0)       # USB-B jack cut-out (centre from the board's power-header edge)
DCJ = dict(v=7.6, w=11.5, h=13.5)        # barrel jack cut-out

# 16x2 display module (standard 1602: PCB 80 x 36, holes 75 x 31, metal bezel 71 x 24)
LCD_W, LCD_H = 80.0, 36.0
LCD_HOLE_DX, LCD_HOLE_DZ, LCD_HOLE_D = 75.0, 31.0, 3.2
WIN_W, WIN_H = 72.5, 26.0                # window for the bezel (bezel pokes through)
LCD_BOSS = 2.5                           # spacer from wall to PCB (clears the header solder joints)
LCD_CZ = FLOOR + 32.0                    # display centre height

# back-wall wire notch, vents
NOTCH_W, NOTCH_DEPTH = 44.0, 14.0
POST = 7.0                               # corner screw posts for the lid
LID_SCREW = 3.4

# ---- buttons and LEDs on the lid --------------------------------------------------------------
# Positions measured on the shield: X from the shield edge on the USB-jack side,
# Y from the shield edge with the digital pins (D0-D13), to the CENTRE of each part.
PARTS_FILE = os.path.join(HERE, "lid_parts.json")
BUTTON_HOLE, LED_HOLE = 7.2, 5.6
PLUNGER_D, FLANGE_D, FLANGE_T, PROTRUDE = 6.6, 9.5, 1.6, 3.0
GUIDE_D, GUIDE_LEN = 10.5, 8.0
UNO_BOTTOM_ON_TABLE = 1.5        # Uno lying on the table rests on its solder joints (~1.5 mm)


# ------------------------------------------------------------------ helpers
def box(x0, y0, z0, x1, y1, z1):
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def cyl_z(cx, cy, z0, h, d):
    return Manifold.cylinder(h, d / 2, d / 2, SEG).translate((cx, cy, z0))


def cyl_y(cx, y0, cz, h, d):     # axis along +y
    return Manifold.cylinder(h, d / 2, d / 2, SEG).rotate((-90, 0, 0)).translate((cx, y0, cz))


def load_parts():
    if not os.path.exists(PARTS_FILE):
        return {"button_top_from_table": None, "parts": []}
    with open(PARTS_FILE, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ base
def make_base():
    shell = box(0, 0, 0, LO, DO, HB) - box(T, T, FLOOR, LO - T, DO - T, HB + 1)

    # corner posts for the lid screws
    for x0 in (T, LO - T - POST):
        for y0 in (T, DO - T - POST):
            p = box(x0, y0, FLOOR - 0.01, x0 + POST, y0 + POST, HB)
            p -= cyl_z(x0 + POST / 2, y0 + POST / 2, HB - 12, 12.1, SCREW_TAP)
            shell += p

    # Uno standoffs
    for u, v in UNO_HOLES:
        x, y = uno_to_box(u, v)
        s = cyl_z(x, y, FLOOR - 0.01, STANDOFF_H + 0.01, STANDOFF_D) - cyl_z(x, y, FLOOR - 1.2, STANDOFF_H + 2, SCREW_TAP)
        shell += s

    # display: window, mounting bosses, screw holes
    cx = LO / 2
    shell -= box(cx - WIN_W / 2, -1, LCD_CZ - WIN_H / 2, cx + WIN_W / 2, T + LCD_BOSS + 1, LCD_CZ + WIN_H / 2)
    for sx in (-1, 1):
        for sz in (-1, 1):
            hx, hz = cx + sx * LCD_HOLE_DX / 2, LCD_CZ + sz * LCD_HOLE_DZ / 2
            shell += cyl_y(hx, T - 0.01, hz, LCD_BOSS + 0.01, 6.5)
            shell -= cyl_y(hx, -1, hz, T + LCD_BOSS + 2, LCD_HOLE_D)

    # right wall: USB and power jack
    for j in (USB, DCJ):
        _, yc = uno_to_box(0, j["v"])
        shell -= box(LO - T - 1, yc - j["w"] / 2, PCB_TOP - 1.5, LO + 1, yc + j["w"] / 2, PCB_TOP - 1.5 + j["h"])

    # back wall: wire notch from the top edge (wires drop in, lid closes over them)
    shell -= box(LO / 2 - NOTCH_W / 2, DO - T - 1, HB - NOTCH_DEPTH, LO / 2 + NOTCH_W / 2, DO + 1, HB + 1)

    # left wall: vent slots
    for i in range(5):
        y = DO / 2 - 20 + i * 10
        shell -= box(-1, y - 1.2, FLOOR + 20, T + 1, y + 1.2, FLOOR + 40)
    return shell


# ------------------------------------------------------------------ lid and plungers
def part_xy(p):
    """Shield measurement (X from USB-side edge, Y from digital-pin edge) -> box x, y."""
    return BX_RIGHT - p["x"], BY_FRONT + p["y"]


def make_lid(cfg):
    lid = box(0, 0, 0, LO, DO, LID)
    for x in (T + POST / 2, LO - T - POST / 2):
        for y in (T + POST / 2, DO - T - POST / 2):
            lid -= cyl_z(x, y, -1, LID + 2, LID_SCREW)
    for p in cfg["parts"]:
        x, y = part_xy(p)
        if p["type"] == "button":
            # guide tube under the lid (printed lid is flipped, so it grows from the lid's underside, z<0 here)
            lid += cyl_z(x, y, -GUIDE_LEN, GUIDE_LEN + 0.01, GUIDE_D)
            lid -= cyl_z(x, y, -GUIDE_LEN - 1, GUIDE_LEN + LID + 2, BUTTON_HOLE)
        else:
            lid -= cyl_z(x, y, -1, LID + 2, LED_HOLE)
    return lid


def plunger_length(cfg):
    top = cfg.get("button_top_from_table")
    if not top:
        return None
    btn_z = top - UNO_BOTTOM_ON_TABLE + FLOOR + STANDOFF_H          # button top inside the box
    return round(HB + LID + PROTRUDE - btn_z, 1)


def make_plunger(length):
    return (cyl_z(0, 0, 0, FLANGE_T, FLANGE_D) + cyl_z(0, 0, FLANGE_T - 0.01, length - FLANGE_T, PLUNGER_D))


# ------------------------------------------------------------------ export
def write_stl(m, path):
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties, dtype=np.float32)[:, :3]
    t = np.asarray(mesh.tri_verts, dtype=np.int64)
    tri = v[t]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(t), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, tri
    with open(path, "wb") as f:
        f.write(b"solar selector enclosure".ljust(80, b" "))
        f.write(np.uint32(len(t)).tobytes())
        f.write(rec.tobytes())
    return v, t


def preview(parts, path):
    """Self-contained three.js viewer (orbit with the mouse)."""
    data = []
    for name, (v, t, col, off) in parts.items():
        data.append({"name": name, "col": col, "off": off,
                     "v": np.round(v, 2).ravel().tolist(), "t": t.ravel().tolist()})
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Solar Selector Box</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body{{margin:0;height:100%;background:#eef0ec;font:14px system-ui,sans-serif}}#c{{width:100%;height:100%;display:block}}
#k{{position:fixed;left:12px;top:10px;background:#fffd;padding:8px 10px;border-radius:6px}}#k label{{margin-right:10px}}</style></head><body>
<div id="k"><b>Solar selector box</b> · drag to rotate, scroll to zoom<br>
<label><input type="checkbox" id="explode" checked> lid lifted</label></div>
<canvas id="c"></canvas>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script>
const DATA={json.dumps(data)};
const r=new THREE.WebGLRenderer({{canvas:document.getElementById('c'),antialias:true}});r.setPixelRatio(devicePixelRatio);
const s=new THREE.Scene();s.background=new THREE.Color(0xeef0ec);
const cam=new THREE.PerspectiveCamera(35,1,1,2000);cam.up.set(0,0,1);cam.position.set(-150,-190,150);
const ctl=new THREE.OrbitControls(cam,r.domElement);ctl.target.set({LO/2},{DO/2},{HB/2});
s.add(new THREE.HemisphereLight(0xffffff,0x667766,0.9));const dl=new THREE.DirectionalLight(0xffffff,0.6);dl.position.set(-1,-2,3);s.add(dl);
const objs={{}};
for(const p of DATA){{const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(p.v,3));g.setIndex(p.t);g.computeVertexNormals();
 const m=new THREE.Mesh(g,new THREE.MeshStandardMaterial({{color:p.col,roughness:0.75,metalness:0.0,flatShading:true}}));m.position.set(...p.off);s.add(m);objs[p.name]=m;}}
function ex(){{const on=document.getElementById('explode').checked;if(objs.lid)objs.lid.position.z={HB}+(on?40:0);}}
document.getElementById('explode').onchange=ex;ex();
function rs(){{r.setSize(innerWidth,innerHeight,false);cam.aspect=innerWidth/innerHeight;cam.updateProjectionMatrix();}}addEventListener('resize',rs);rs();
(function a(){{requestAnimationFrame(a);ctl.update();r.render(s,cam);}})();
</script></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    cfg = load_parts()
    base, lid = make_base(), make_lid(cfg)
    out = {}
    v, t = write_stl(base, os.path.join(HERE, "box_base.stl"))
    out["base"] = (v, t, "#3a7bd5", (0, 0, 0))
    v, t = write_stl(lid, os.path.join(HERE, "box_lid.stl"))
    out["lid"] = (v, t, "#f2f2ee", (0, 0, HB))
    pl = plunger_length(cfg)
    if pl:
        v, t = write_stl(make_plunger(pl), os.path.join(HERE, "button_plunger.stl"))
        print(f"plunger length {pl} mm")
    preview(out, os.path.join(HERE, "preview.html"))
    print(f"box outside {LO:.1f} x {DO:.1f} x {HB + LID:.1f} mm; base volume {base.volume() / 1000:.1f} cm3, "
          f"lid {lid.volume() / 1000:.1f} cm3; parts on lid: {len(cfg['parts'])}")


if __name__ == "__main__":
    main()
