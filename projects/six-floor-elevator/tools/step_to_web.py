"""Tessellate the size-sorter STEP into the simulator's chunk format.
Output: <outdir>/model.json + model.b64.txt  (quantized uint16 positions, uint16 indices, uint8 palette index per vertex)
Usage: python step_to_web.py <in.step> <outdir> [lin_deflection]
"""
import sys, json, time, base64, os
import numpy as np
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorType, XCAFDoc_ColorTool
from OCP.TDF import TDF_Label
from OCP.collections import Sequence_TDF_Label as LabelSeq
from OCP.TDataStd import TDataStd_Name
from OCP.Quantity import Quantity_Color
from OCP.TopLoc import TopLoc_Location
from OCP.IFSelect import IFSelect_RetDone
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool

src, outdir = sys.argv[1], sys.argv[2]
LIN = float(sys.argv[3]) if len(sys.argv) > 3 else 0.6
ANG = 0.45
t0 = time.time()
doc = TDocStd_Document(TCollection_ExtendedString("doc"))
r = STEPCAFControl_Reader(); r.SetColorMode(True); r.SetNameMode(True)
assert r.ReadFile(src) == IFSelect_RetDone
r.Transfer(doc)
st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
print("read %.0fs" % (time.time() - t0), flush=True)

def name(lab):
    a = TDataStd_Name()
    return a.Get().ToExtString() if lab.FindAttribute(TDataStd_Name.GetID_s(), a) else "?"

def hexc(c):
    return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in (c.Red(), c.Green(), c.Blue()))

def lab_colour(lab):
    c = Quantity_Color()
    for t in (XCAFDoc_ColorType.XCAFDoc_ColorSurf, XCAFDoc_ColorType.XCAFDoc_ColorGen):
        if XCAFDoc_ColorTool.GetColor_s(lab, t, c):
            return hexc(c)
    return None

def face_colour(face):
    c = Quantity_Color()
    for t in (XCAFDoc_ColorType.XCAFDoc_ColorSurf, XCAFDoc_ColorType.XCAFDoc_ColorGen):
        try:
            if ct.GetColor(face, t, c):
                return hexc(c)
        except Exception:
            pass
    return None

DEFAULT = [  # (substring of path, colour) for parts without a colour
    ("TOPRW0700", "#2a2e3a"), ("EMG_Button", "#c62828"), ("106_Button", "#d8dadd"), ("Duct", "#9aa1a8"), ("duct", "#9aa1a8"),
    ("254_Cylinder", "#c4c9cf"), ("Sensor_Bracket", "#9aa1a8"), ("CJWS75-P_3", "#2a2e3a"), ("Regulator", "#d8dadd"),
    ("Sol_Valve", "#3a3d43"), ("", "#a8aeb6"),
]

CAR = ("HMI_고정_평커버", "TOPRW0700WD", "HMI_SHAFT_고정_브라켓", "LMHM16", "타이밍벨트 고정 브라켓")
def group_of(path, c):
    return "car" if any(k in path for k in CAR) else "static"

SKIP = ()
COARSE = ("XBC-DR32H", "단상AC모터", "모터기어헤드", "Regulator", "MCCB")
parts = []   # (group, verts Nx3, tris Mx3, colour-per-vertex list)
def walk(lab, loc, path, inh):
    ref = TDF_Label()
    if st.IsReference_s(lab) and st.GetReferredShape_s(lab, ref):
        walk(ref, loc.Multiplied(st.GetLocation_s(lab)), path + [name(lab)], lab_colour(lab) or inh)
        return
    col = lab_colour(lab) or inh
    if st.IsAssembly_s(lab):
        kids = LabelSeq(); st.GetComponents_s(lab, kids)
        for i in range(1, kids.Length() + 1):
            walk(kids.Value(i), loc, path, col)
        return
    p = "/".join(path + [name(lab)])
    if any(s in p for s in SKIP):
        return
    base = st.GetShape_s(lab)
    shape = base.Moved(loc)
    coarse = any(s in p for s in COARSE)
    BRepMesh_IncrementalMesh(shape, LIN * (4 if coarse else 1), False, ANG * (2 if coarse else 1), True)
    if col is None:
        col = next(c for k, c in DEFAULT if k in p)
    V, T, C = [], [], []
    exb = TopExp_Explorer(base, TopAbs_FACE)
    exs = TopExp_Explorer(shape, TopAbs_FACE)
    while exs.More():
        f = TopoDS.Face(exs.Current())
        fb = TopoDS.Face(exb.Current()) if exb.More() else None
        fl = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, fl)
        if tri is not None:
            fc = (face_colour(fb) if fb is not None else None) or col
            tr = fl.Transformation()
            n0 = len(V)
            for i in range(1, tri.NbNodes() + 1):
                q = tri.Node(i).Transformed(tr)
                V.append((q.X(), q.Y(), q.Z())); C.append(fc)
            rev = f.Orientation() == TopAbs_REVERSED
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get()
                T.append((n0 + a - 1, n0 + c - 1, n0 + b - 1) if rev else (n0 + a - 1, n0 + b - 1, n0 + c - 1))
        exs.Next()
        if exb.More(): exb.Next()
    if not T:
        return
    V = np.array(V, dtype=np.float64)
    ctr = (V.min(0) + V.max(0)) / 2
    parts.append((group_of(p, ctr), p, V, np.array(T, dtype=np.int64), C))

roots = LabelSeq(); st.GetFreeShapes(roots)
for i in range(1, roots.Length() + 1):
    walk(roots.Value(i), TopLoc_Location(), [], None)
print("meshed %d parts %.0fs" % (len(parts), time.time() - t0), flush=True)

# palette
pal = sorted({c for p in parts for c in p[4]})
assert len(pal) < 256, len(pal)
pidx = {c: i for i, c in enumerate(pal)}

# pack parts into chunks of <= 65535 vertices per group
chunks, blobs, off = [], [], 0
def emit(group, V, T, C):
    global off
    lo, hi = V.min(0), V.max(0)
    s = np.where(hi - lo > 0, (hi - lo) / 65535.0, 1e-6)
    q = np.round((V - lo) / s).astype(np.uint16)
    pos_b = q.tobytes(); idx_b = T.astype(np.uint16).tobytes(); col_b = np.array([pidx[c] for c in C], dtype=np.uint8).tobytes()
    ch = {"g": group, "nv": len(V), "nt": len(T), "o": [round(float(v), 4) for v in lo], "s": [float("%.8g" % v) for v in s]}
    for key, b in (("pos", pos_b), ("idx", idx_b), ("col", col_b)):
        pad = (-off) % 4
        if pad: blobs.append(b"\0" * pad); off += pad
        ch[key] = off; blobs.append(b); off += len(b)
    chunks.append(ch)

for g in sorted({p[0] for p in parts}):
    bufV, bufT, bufC = [], [], []; n = 0
    items = []
    for p in (p for p in parts if p[0] == g):
        V, T, C = p[2], p[3], p[4]
        if len(V) <= 60000:
            items.append((V, T, C)); continue
        print("splitting big part:", p[1], len(V))
        step = 18000   # triangles per piece -> <= 54000 vertices
        for k in range(0, len(T), step):
            t = T[k:k + step]; used = np.unique(t); remap = np.full(len(V), -1, np.int64); remap[used] = np.arange(len(used))
            items.append((V[used], remap[t], [C[i] for i in used]))
    for V, T, C in items:
        if n + len(V) > 65535 and n:
            emit(g, np.vstack(bufV), np.vstack(bufT), sum(bufC, [])); bufV, bufT, bufC, n = [], [], [], 0
        bufV.append(V); bufT.append(T + n); bufC.append(C); n += len(V)
    if n:
        emit(g, np.vstack(bufV), np.vstack(bufT), sum(bufC, []))

os.makedirs(outdir, exist_ok=True)
data = b"".join(blobs)
open(os.path.join(outdir, "model.b64.txt"), "w").write(base64.b64encode(data).decode())
json.dump({"palette": pal, "chunks": chunks}, open(os.path.join(outdir, "model.json"), "w"), separators=(",", ":"))
tv = sum(c["nv"] for c in chunks); tt = sum(c["nt"] for c in chunks)
print("chunks %d verts %d tris %d bin %.1f MB b64 %.1f MB  %.0fs" % (len(chunks), tv, tt, len(data) / 1e6, len(data) * 4 / 3 / 1e6, time.time() - t0))
from collections import Counter
print(Counter(c["g"] for c in chunks))
