"""3D robot simulator for Motion-X: the Mirobot model moving like the real robot.

* Model: WLKATA mirobot_urdf_2 meshes (Apache-2.0, ..\\sim3d\\mirobot.b64.txt), simplified
  once and cached in sim_mesh_cache.npz.
* Kinematics: URDF joint chain. The real robot's joint angles go in unchanged (checked:
  X/Y match within 0.1 mm); the robot's Z is measured 8 mm higher than the URDF base.
* Rendering: flat-shaded triangles with OpenCV (no 3D library needed), mouse orbit/zoom.
"""
import base64
import functools
import json
import os

import cv2
import numpy as np

import config

ROBOT_Z_SHIFT = 8.0        # robot Cartesian Z + 8 mm = URDF base frame Z
# default 3D view: between the plate (+Y) and the load cell (-Y); double-click resets it
VIEW_TARGET, VIEW_YAW, VIEW_PITCH, VIEW_DIST = (70.0, -10.0, 70.0), -15.0, 30.0, 720.0
CUP_LEN = 32.0             # suction stem + cup below the flange (mm, for the picture)

URDF = [  # joint origin xyz (mm), rpy (rad), axis
    ([0, 0, 65.406], [0, 0, 0], [0, 0, 1]),
    ([29.687, -22.0, 61.593], [3.1402, -1.5708, 1.5722], [0, 0, 1]),
    ([108.0, 0, -9.4471], [0, 0, 0], [0, 0, 1]),
    ([20.001, 107.43, 31.439], [-1.5708, 0, 0], [0, 0, 1]),
    ([0, -10.414, 61.55], [1.5708, -1.5708, -3.1416], [0, 0, -1]),
    ([0, -16.28, 10.525], [-1.5708, 0, 0], [0, 0, 1]),
]
# colour per link (BGR), like the real robot: grey base, orange arms
LINK_COLORS = [(150, 135, 120), (215, 215, 212), (40, 150, 255), (215, 215, 212),
               (40, 150, 255), (150, 135, 120), (215, 215, 212)]
# mesh simplification grid (mm) per link: the base is drawn once (cached) so it keeps more
# detail; the moving links are a little coarser so the arm draws fast (high frame rate)
CELL = [4, 6.5, 5, 6.5, 5.5, 3, 3]


def _rpy(r, p, y):
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    return (np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]]) @
            np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]]) @
            np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]]))


def _axang(a, t):
    a = np.asarray(a, float)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * K @ K


_FIXED = []
for _xyz, _r, _ax in URDF:
    _M = np.eye(4)
    _M[:3, :3] = _rpy(*_r)
    _M[:3, 3] = _xyz
    _FIXED.append((_M, _ax))


def fk(q_deg):
    """4x4 transforms of base + 6 links (mm), for robot joint angles in degrees."""
    T = np.eye(4)
    out = [T.copy()]
    for (M, ax), qi in zip(_FIXED, np.radians(q_deg)):
        R = np.eye(4)
        R[:3, :3] = _axang(ax, qi)
        T = T @ M @ R
        out.append(T.copy())
    return out


def tool_point(q_deg, below=0.0):
    """Flange point (below=0) or a point 'below' mm further along the tool, URDF frame."""
    T = fk(q_deg)[-1]
    return (T @ np.array([0, 0, -below, 1.0]))[:3]


def ik(target_robot_xyz, seed):
    """Joint angles (deg) that put the flange at a robot Cartesian point, tool pointing down."""
    tgt = np.asarray(target_robot_xyz, float) + [0, 0, ROBOT_Z_SHIFT]
    q = np.array(seed, float)
    q[0] = np.degrees(np.arctan2(tgt[1], tgt[0]))
    q[3] = 0.0
    idx = [0, 1, 2, 4]

    def err(qq):
        T = fk(qq)[-1]
        return np.concatenate([(T[:3, 3] - tgt) / 10.0, (T[:3, 2] - [0, 0, 1]) * 5.0])

    for _ in range(40):
        e = err(q)
        if np.linalg.norm(e) < 1e-3:
            break
        J = np.zeros((len(e), len(idx)))
        for k, j in enumerate(idx):
            d = q.copy()
            d[j] += 0.5
            J[:, k] = (err(d) - e) / 0.5
        dq = np.linalg.solve(J.T @ J + 1e-3 * np.eye(len(idx)), -J.T @ e)
        q[idx] += np.clip(dq, -15, 15)
    return q


# ------------------------------------------------------------------ meshes ---
def _load_meshes():
    cache = os.path.join(config.STUDIO_DIR, "sim_mesh_cache.npz")
    if os.path.exists(cache):
        d = np.load(cache)
        return [(d[f"v{i}"], d[f"f{i}"]) for i in range(7)]
    src = os.path.join(config.PROJECT_DIR, "sim3d")
    meta = json.load(open(os.path.join(src, "mirobot.json")))
    with open(os.path.join(src, "mirobot.b64.txt")) as fh:
        buf = base64.b64decode(fh.read().strip())
    meshes = []
    for c, cell in zip(meta["links"], CELL):
        q = np.frombuffer(buf, np.uint16, c["nv"] * 3, c["pos"]).reshape(-1, 3).astype(float)
        v = (np.array(c["o"]) + q * np.array(c["s"])) * 1000.0
        f = np.frombuffer(buf, np.uint32 if c["wide"] else np.uint16, c["nt"] * 3,
                          c["idx"]).reshape(-1, 3).astype(np.int64)
        key = np.floor(v / cell).astype(np.int64)
        _, inv = np.unique(key, axis=0, return_inverse=True)
        inv = inv.ravel()
        n = inv.max() + 1
        nv = np.zeros((n, 3))
        np.add.at(nv, inv, v)
        nv /= np.bincount(inv, minlength=n)[:, None]
        nf = inv[f]
        nf = nf[(nf[:, 0] != nf[:, 1]) & (nf[:, 1] != nf[:, 2]) & (nf[:, 0] != nf[:, 2])]
        _, first = np.unique(np.sort(nf, axis=1), axis=0, return_index=True)
        meshes.append((nv.astype(np.float32), nf[np.sort(first)].astype(np.int32)))
    np.savez_compressed(cache, **{f"v{i}": m[0] for i, m in enumerate(meshes)},
                        **{f"f{i}": m[1] for i, m in enumerate(meshes)})
    return meshes


def _vertex_normals(v, f):
    """Area-weighted vertex normals: neighbouring triangles get similar light (smooth look)."""
    tri = v[f].astype(np.float64)
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    vn = np.zeros((len(v), 3))
    for k in range(3):
        np.add.at(vn, f[:, k], fn)
    return vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-9)


@functools.lru_cache(maxsize=256)
def _box_cached(cx, cy, z0, sx, sy, sz, tile, top):
    return _box(cx, cy, z0, sx, sy, sz, tile, top)


def box(cx, cy, z0, sx, sy, sz, tile=1e9, top=True):
    """Box mesh (vertices, faces) standing on z0 (same box -> same arrays, made once)."""
    r = lambda x: round(float(x), 1)  # noqa: E731
    return _box_cached(r(cx), r(cy), r(z0), r(sx), r(sy), r(sz), tile, top)


def _box(cx, cy, z0, sx, sy, sz, tile=1e9, top=True):
    """Box mesh (vertices, faces) standing on z0. Big faces can be cut into tiles."""
    x0, x1, y0, y1, z1 = cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, z0 + sz
    corners = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    if not top:                                    # stand under something: its top is never seen
        quads.pop(1)
    vs, fs = [], []
    for a, b, c, d in quads:
        A, B, D = corners[a], corners[b], corners[d]
        nu = max(1, int(np.ceil(np.linalg.norm(B - A) / tile)))
        nv = max(1, int(np.ceil(np.linalg.norm(D - A) / tile)))
        u, w = np.meshgrid(np.linspace(0, 1, nu + 1), np.linspace(0, 1, nv + 1), indexing="ij")
        grid = A + u[..., None] * (B - A) + w[..., None] * (D - A)
        base = sum(len(x) for x in vs)
        vs.append(grid.reshape(-1, 3))
        idx = np.arange((nu + 1) * (nv + 1)).reshape(nu + 1, nv + 1) + base
        p00, p10, p11, p01 = idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]
        fs.append(np.stack([p00, p10, p11], -1).reshape(-1, 3))
        fs.append(np.stack([p00, p11, p01], -1).reshape(-1, 3))
    return np.concatenate(vs).astype(np.float32), np.concatenate(fs).astype(np.int32)


def cylinder(r0, r1, z0, z1, n=14):
    """Cylinder/cone along -z in tool frame (top radius r0 at z0, bottom r1 at z1)."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    top = np.c_[r0 * np.cos(a), r0 * np.sin(a), np.full(n, z0)]
    bot = np.c_[r1 * np.cos(a), r1 * np.sin(a), np.full(n, z1)]
    v = np.vstack([top, bot, [[0, 0, z0], [0, 0, z1]]]).astype(np.float32)
    f = []
    for i in range(n):
        j = (i + 1) % n
        f += [[i, n + i, n + j], [i, n + j, j], [2 * n, j, i], [2 * n + 1, n + i, n + j]]
    return v, np.array(f, np.int32)


# ---------------------------------------------------------------- renderer ---
class Renderer:
    def __init__(self):
        self.meshes = _load_meshes()
        self.vnormals = [_vertex_normals(v, f) for v, f in self.meshes]
        self.cup = cylinder(5, 5, 0, -14), cylinder(5.5, 10, -14, -CUP_LEN)
        self.yaw, self.pitch, self.dist = VIEW_YAW, VIEW_PITCH, VIEW_DIST
        self.target = np.array(VIEW_TARGET)
        self.light = np.array([0.4, -0.5, 0.75])
        self.light /= np.linalg.norm(self.light)

    def reset_view(self):
        self.yaw, self.pitch, self.dist = VIEW_YAW, VIEW_PITCH, VIEW_DIST

    def _camera(self):
        y, p = np.radians(self.yaw), np.radians(self.pitch)
        eye = self.target + self.dist * np.array([np.cos(p) * np.cos(y), np.cos(p) * np.sin(y), np.sin(p)])
        fwd = self.target - eye
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        return eye, np.stack([right, up, fwd])

    def _background(self, w, h, eye, project):
        """Sky gradient + floor grid fading into the distance (cached until the view changes)."""
        key = (w, h, self.yaw, self.pitch, self.dist, tuple(self.target))
        if getattr(self, "_bg_key", None) == key:
            return self._bg.copy()
        img = np.empty((h, w, 3), np.uint8)
        t = np.linspace(0, 1, h)[:, None]
        top, bot = np.array((252, 247, 243)), np.array((236, 226, 218))
        img[:] = (top * (1 - t) + bot * t)[:, None, :].astype(np.uint8)
        floor, fz = (234, 225, 218), -TABLE_T - 160.0       # floor grid well below the table
        for k in range(-500, 651, 60):
            for a, b in (((k, -600, fz), (k, 560, fz)), ((-500, k, fz), (650, k, fz))):
                seg = np.linspace(a, b, 12)
                p, z = project(seg)
                for i in range(len(p) - 1):
                    fade = float(np.clip((z[i] - self.dist * 0.6) / (self.dist * 1.3), 0, 1))
                    col = tuple(int(c) for c in np.array((205, 190, 178)) * (1 - fade) + np.array(floor) * fade)
                    cv2.line(img, tuple(np.int32(p[i])), tuple(np.int32(p[i + 1])), col, 1, cv2.LINE_AA)
        self._bg_key, self._bg = key, img
        return img.copy()

    def _shadows(self, img, project, footprints):
        """Soft shadows on the floor under the robot base and the objects."""
        layer = np.zeros(img.shape[:2], np.float32)
        a = np.linspace(0, 2 * np.pi, 40, endpoint=False)
        for cx, cy, rx, ry, strength in footprints:
            ring = np.c_[cx + rx * np.cos(a), cy + ry * np.sin(a), np.zeros_like(a)]
            p, _ = project(ring)
            cv2.fillConvexPoly(layer, np.int32(p), strength, cv2.LINE_AA)
        k = max(9, int(img.shape[1] / 40) | 1)
        layer = cv2.GaussianBlur(layer, (k, k), 0)[:, :, None]
        img[:] = (img * (1 - 0.35 * layer)).astype(np.uint8)

    def render(self, w, h, q_deg, scene):
        """BGR image of the robot at joint angles q_deg plus the scene objects.

        Fixed things (table, plate, load cell, robot base, their shadows) are drawn once into
        a cached picture; each frame only draws the moving arm and the blocks on top of it."""
        eye, rot = self._camera()
        focal = 1.25 * min(w, h)

        def project(p):
            c = (p - eye) @ rot.T
            z = np.maximum(c[:, 2], 1.0)
            return np.c_[w / 2 + focal * c[:, 0] / z, h / 2 - focal * c[:, 1] / z], c[:, 2]

        static = [s for s in scene if len(s) > 3 and s[3] < 2]
        moving = [s for s in scene if not (len(s) > 3 and s[3] < 2)]
        skey = (w, h, self.yaw, self.pitch, self.dist, tuple(self.target),
                tuple((len(s[0]), round(float(s[0][0, 0]), 1), round(float(s[0][0, 1]), 1)) for s in static))
        if getattr(self, "_static_key", None) != skey:
            img = self._background(w, h, eye, project)
            foot = [(0.0, 0.0, 95.0, 95.0, 1.0)]
            for v, f, col, *_ in static:
                lo, hi = v.min(axis=0), v.max(axis=0)
                if -1 < lo[2] < 1:                          # stands on the table: drop a shadow
                    foot.append(((lo[0] + hi[0]) / 2 + 6, (lo[1] + hi[1]) / 2 - 6,
                                 (hi[0] - lo[0]) / 2 + 6, (hi[1] - lo[1]) / 2 + 6, 0.8))
            self._shadows(img, project, foot)
            v0, f0 = self.meshes[0]                         # robot base never moves (J1 turns link 1)
            parts = [(v0[f0], self.vnormals[0][f0].mean(axis=1), LINK_COLORS[0], 30.0, 1)]
            parts += [(v[f], None, col, 15.0, layer) for v, f, col, layer in static]
            self._draw(img, project, eye, parts)
            self._static_key, self._static = skey, img
        img = self._static.copy()

        Ts = fk(q_deg)
        parts = []
        for i in range(1, len(self.meshes)):
            v, f = self.meshes[i]
            T = Ts[i]
            parts.append(((v @ T[:3, :3].T + T[:3, 3])[f],
                          (self.vnormals[i] @ T[:3, :3].T)[f].mean(axis=1),       # smooth shading normal
                          LINK_COLORS[i], 55.0 if i in (2, 4) else 30.0, 2))      # glossy orange arms
        for (cv_, cf), col in zip(self.cup, ((70, 70, 70), (35, 35, 35))):
            T = Ts[6]
            parts.append(((cv_ @ T[:3, :3].T + T[:3, 3])[cf], None, col, 20.0, 2))
        parts += [(s[0][s[1]], None, s[2], 15.0, 2) for s in moving]
        self._draw(img, project, eye, parts)
        return img

    def _draw(self, img, project, eye, parts):
        """Shade and draw triangles: parts = [(triangles Nx3x3, smooth normals or None, colour, shine, layer)]."""
        if not parts:
            return
        tris = [p[0] for p in parts]
        vnorm = [p[1] for p in parts]
        base = [np.tile(p[2], (len(p[0]), 1)) for p in parts]
        shine = [np.full(len(p[0]), p[3]) for p in parts]
        layer = [np.full(len(p[0]), p[4]) for p in parts]

        tri = np.concatenate(tris).astype(np.float64)
        fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        fn /= np.linalg.norm(fn, axis=1, keepdims=True) + 1e-9
        cen = tri.mean(axis=1)
        starts = np.cumsum([0] + [len(t) for t in tris[:-1]])
        n = np.concatenate([fn[s:s + len(t)] if vn is None else fn[s:s + len(t)] + 1.5 * vn
                            for s, t, vn in zip(starts, tris, vnorm)])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
        vis = np.einsum("ij,ij->i", fn, eye - cen) > 0                     # back faces away
        tri, n, cen = tri[vis], n[vis], cen[vis]
        col = np.concatenate(base)[vis].astype(np.float64)
        shine = np.concatenate(shine)[vis]
        layer = np.concatenate(layer)[vis]

        view = eye - cen
        view /= np.linalg.norm(view, axis=1, keepdims=True)
        key = np.clip(n @ self.light, 0, 1)
        fill = np.clip(n @ np.array([-0.6, 0.5, 0.3]) / np.linalg.norm([-0.6, 0.5, 0.3]), 0, 1)
        half = self.light + view
        half /= np.linalg.norm(half, axis=1, keepdims=True)
        spec = np.clip(np.einsum("ij,ij->i", n, half), 0, 1) ** 24 * shine
        rim = (1 - np.clip(np.einsum("ij,ij->i", n, view), 0, 1)) ** 3 * 25
        light = 0.38 + 0.55 * key + 0.17 * fill
        col = np.clip(col * light[:, None] + (spec + rim)[:, None], 0, 255)

        pts, depth = project(tri.reshape(-1, 3))
        depth = depth.reshape(-1, 3).mean(axis=1)
        order = np.lexsort((-depth, layer))          # layer first, then far-to-near
        pts = np.round(pts.reshape(-1, 3, 2)[order] * 4).astype(np.int32)
        cols = col[order].astype(np.int32).tolist()
        fillp, aa = cv2.fillConvexPoly, cv2.LINE_AA
        for p, c in zip(pts, cols):
            fillp(img, p, c, aa, 2)

    def tool_frame(self, q_deg):
        return fk(q_deg)[6]


# ------------------------------------------------------------------- twin ---
class Twin:
    """What the simulator shows: robot joints (smoothly following the robot), suction, blocks."""

    HOME = np.zeros(6)

    def __init__(self, place_joints=None):
        self.q = self.HOME.copy()          # shown now
        self.goal = self.HOME.copy()       # where the robot is / is going
        self.queue = []                    # dry run: targets to play one after another
        self.vacuum = False
        self.on_scale_since = 0.0          # a block was put on the load cell at this time (0 = none)
        self.scale = None                  # load cell: (x, y, top z) in the URDF frame
        if place_joints is not None:
            tip = tool_point(place_joints, CUP_LEN)
            self.scale = (tip[0], tip[1], tip[2] - 34.0)      # a 32 mm block under the cup

    @property
    def holding(self):
        return self.vacuum and self.gripped

    gripped = False                        # the cup touched a block while sucking
    picked_xy, picked_until = None, 0.0    # hide the picked block until the camera sees the plate again

    def release(self):
        """Suction off: if the cup is over the load cell, the block stays there."""
        if not self.gripped:
            return
        self.gripped = False
        import time
        self.picked_until = time.time() + 6.0
        tip = tool_point(self.goal, CUP_LEN)
        if self.scale is not None and np.hypot(tip[0] - self.scale[0], tip[1] - self.scale[1]) < 45:
            import time
            self.on_scale_since = time.time()

    # smooth motion state
    _seg = None                            # dry run: (start, goal, duration, elapsed)
    _mq = _mt = None                       # real robot: last measured joints and time
    _mv = np.zeros(6)                      # real robot: joint speed (deg/s) from the last two reports
    commanded = None                       # real robot: joints the current move ends at
    JOINT_SPEED = 80.0                     # deg/s, about the Mirobot at F2000

    PLAYBACK_DELAY = 0.45                  # s: show the real robot's path this much later, drawn
                                           #   smoothly between its (irregular) reports

    def measured(self, q, moving=True):    # real robot reported its joints
        import time
        from collections import deque
        now, q = time.time(), np.asarray(q, float)
        if not hasattr(self, "_hist"):
            self._hist = deque(maxlen=30)
        self._hist.append((now, q.copy()))
        if moving and self._mq is not None and now - self._mt > 0.02:
            self._mv = np.clip((q - self._mq) / (now - self._mt), -150, 150)
        else:
            self._mv = np.zeros(6)         # robot idle: settle exactly here, no overshoot
        self._mq, self._mt = q, now
        self.goal = q
        self.queue.clear()
        self._seg = None

    def planned(self, q):                  # dry run: command sent, animate to it
        self.queue.append(np.asarray(q, float))

    def planned_vacuum(self, on):          # dry run: suction change, in order with the moves
        self.queue.append(bool(on))

    def set_vacuum(self, on):
        if self.vacuum and not on:
            self.release()
        self.vacuum = on

    def step(self, dt):
        import time
        # dry run: play the queued moves one by one, each easing in and out
        while self._seg is None and self.queue:
            item = self.queue.pop(0)
            if isinstance(item, bool):
                self.set_vacuum(item)      # arrived: now switch the suction
            else:
                dur = max(0.35, float(np.abs(item - self.q).max()) / self.JOINT_SPEED)
                self._seg = [self.q.copy(), item, dur, 0.0]
                self.goal = item
        if self._seg is not None:
            start, goal, dur, el = self._seg
            el += dt
            s = min(1.0, el / dur)
            e = s * s * s * (s * (6 * s - 15) + 10)            # smootherstep: soft start and stop
            self.q = start + (goal - start) * e
            self._seg[3] = el
            if s >= 1.0:
                self._seg = None
            return self.q
        # real robot: play its reported path back slightly delayed, straight lines between
        # reports (no guessing ahead - irregular report times made a guess wobble), and round
        # the corners with a critically damped spring
        hist = getattr(self, "_hist", None)
        if hist:
            ts = time.time() - self.PLAYBACK_DELAY
            target = hist[-1][1]
            if ts <= hist[0][0]:
                target = hist[0][1]
            else:
                for (t0, q0), (t1, q1) in zip(list(hist)[:-1], list(hist)[1:]):
                    if t0 <= ts <= t1:
                        target = q0 + (q1 - q0) * ((ts - t0) / max(t1 - t0, 1e-6))
                        break
        else:
            target = self.goal
        dt = min(dt, 0.05)
        w = 14.0                                       # corner rounding (settles in ~0.3 s)
        v = getattr(self, "_v", np.zeros(6))
        v = v + (w * w * (target - self.q) - 2 * w * v) * dt
        self.q = self.q + v * dt
        self._v = v
        return self.q


# ------------------------------------------------------------- live view ---
BLOCK = 34.0                      # block edge (mm) in the picture
C_PLATE, C_STAND = (200, 192, 184), (150, 140, 132)
C_TABLE = (222, 214, 206)                 # aluminium machine table
TABLE = (75.0, -20.0, 470.0, 600.0)       # centre x, y and size (mm) - holds robot, plate, load cell
TABLE_T = 28.0                            # table thickness (mm), its top is the robot base (z = 0)
C_BLOCK, C_TARGET = (200, 105, 30), (235, 150, 40)
C_PAD, C_SCALE = (95, 185, 70), (90, 90, 96)


def build_scene(twin, plate, blocks, scale_empty, now):
    """Scene objects (vertices, faces, colour) in the URDF frame (mm)."""
    # one machine table: the robot base, the plate stand and the load cell all stand on it (z = 0)
    # layer: 0 table, 1 things fixed on the table, 2 blocks and robot arm (drawn in that order,
    # each layer sorted far-to-near: the camera looks from above, so a lower layer never hides a higher one)
    sc = [(*box(TABLE[0], TABLE[1], -TABLE_T, TABLE[2], TABLE[3], TABLE_T), C_TABLE, 0)]
    if plate is not None:
        cx, cy, zt = plate
        top = zt + ROBOT_Z_SHIFT                       # real plate height from the calibration
        sc.append((*box(cx, cy, 0, 150, 150, top - 6, top=False), C_STAND, 1))
        sc.append((*box(cx, cy, top - 6, 170, 170, 6), C_PLATE, 1))
    tip = tool_point(twin.q, CUP_LEN)
    if twin.vacuum and not twin.gripped:           # suction on: grip when the cup reaches a block
        for x, y, top, h, _ in blocks:
            if np.hypot(x - tip[0], y - tip[1]) < 30 and tip[2] <= top + ROBOT_Z_SHIFT + 6:
                twin.gripped = True
                twin.picked_xy = (x, y)
    on_scale = bool(twin.on_scale_since) and now - twin.on_scale_since < 120 \
        and not (scale_empty and now - twin.on_scale_since > 4)
    if twin.vacuum and not twin.gripped and on_scale and twin.scale is not None:
        sx, sy, stop = twin.scale                      # "Return block": grip the block on the load cell
        if np.hypot(sx - tip[0], sy - tip[1]) < 30 and tip[2] <= stop + 32 + 6:
            twin.gripped, twin.on_scale_since, twin.picked_xy = True, 0.0, None
    hide = twin.picked_xy if (twin.holding or now < twin.picked_until) else None
    for x, y, top, h, is_target in blocks:
        if hide is not None and np.hypot(x - hide[0], y - hide[1]) < 30:
            continue                                       # this one is on the cup / was just taken
        top += ROBOT_Z_SHIFT
        sc.append((*box(x, y, top - max(h, 10), BLOCK, BLOCK, max(h, 10)), C_TARGET if is_target else C_BLOCK, 2))
    if twin.scale is not None:
        x, y, top = twin.scale
        sc.append((*box(x, y, 0, 44, 44, max(top - 6, 1), top=False), C_SCALE, 1))
        sc.append((*box(x, y, max(top - 6, 1), 64, 64, 6), C_PAD, 1))
        on = twin.on_scale_since and now - twin.on_scale_since < 120 \
            and not (scale_empty and now - twin.on_scale_since > 4)
        if on and not twin.holding:
            sc.append((*box(x, y, max(top, 7), BLOCK, BLOCK, 32), C_BLOCK, 2))
    if twin.holding:                                       # block hanging on the suction cup
        T = fk(twin.q)[6]
        v, f = box(0, 0, -CUP_LEN - 32, BLOCK, BLOCK, 32)
        sc.append(((v @ T[:3, :3].T + T[:3, 3]).astype(np.float32), f, C_BLOCK, 2))
    return sc


class SimThread:
    """Renders the simulator in the background; .image() gives the newest picture (BGR)."""

    def __init__(self, source):
        import threading
        self.source = source              # () -> (twin, plate, blocks, scale_empty, label)
        self.renderer = Renderer()
        self.renderer.target = np.array(VIEW_TARGET)
        self.renderer.dist = VIEW_DIST
        self.size = (520, 420)
        self._img, self._lock = None, threading.Lock()
        self._halt = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        import time
        last = time.time()
        while not self._halt.is_set():
            now = time.time()
            dt, last = now - last, now
            try:
                twin, plate, blocks, empty, label = self.source()
                q = twin.step(dt)
                w, h = self.size
                r = self.renderer
                sc = build_scene(twin, plate, blocks, empty, now)
                sig = (np.round(q, 2).tobytes(), w, h, r.yaw, r.pitch, r.dist,
                       tuple((len(s[0]), round(float(s[0][0, 0]), 1), round(float(s[0][0, 2]), 1)) for s in sc))
                if sig != getattr(self, "_sig", None):           # nothing moved: keep the last picture
                    img = r.render(max(w, 160), max(h, 120), q, sc)
                    self._overlay(img, q, twin, label)
                    with self._lock:
                        self._img = img
                        self.frame_id = getattr(self, "frame_id", 0) + 1
                    self._sig = sig
            except Exception as e:                       # keep the view alive
                print(f"simulator: {e}")
                time.sleep(1)
            time.sleep(max(0.004, 0.016 - (time.time() - now)))      # up to ~60 frames/s

    @staticmethod
    def _overlay(img, q, twin, label):
        """Joint readout along the bottom (labels/badges are drawn by the studio, in its language)."""
        h, w = img.shape[:2]
        cv2.rectangle(img, (0, h - 28), (w, h), (255, 255, 255), -1)
        step = w / 6
        for i, v in enumerate(q):
            x = int(i * step + 8)
            cv2.putText(img, f"J{i + 1}", (x, h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (237, 58, 124), 1, cv2.LINE_AA)
            cv2.putText(img, f"{v:.1f}", (x + 22, h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (90, 70, 60), 1, cv2.LINE_AA)

    def image(self):
        with self._lock:
            return None if self._img is None else self._img

    def stop(self):
        self._halt.set()


# ------------------------------------------------- render in its own process ---
MAX_W, MAX_H = 1920, 1200          # largest simulator picture


class _View:
    """Camera angle of the 3D view (what the mouse changes); the renderer runs elsewhere."""

    def __init__(self):
        self.target = np.array(VIEW_TARGET)
        self.reset_view()

    def reset_view(self):
        self.yaw, self.pitch, self.dist = VIEW_YAW, VIEW_PITCH, VIEW_DIST


def _render_worker(jobs, shm_name, info):
    """Runs in a separate process (own CPU core): renders frames into shared memory.
    info = [frames done, width, height, slot]; two slots so the window never reads a half frame."""
    from multiprocessing import shared_memory
    shm = shared_memory.SharedMemory(name=shm_name)
    slots = np.ndarray((2, MAX_H, MAX_W, 3), np.uint8, shm.buf)
    r = Renderer()
    slot = 0
    while True:
        job = jobs.get()
        while True:                                  # only the newest job matters
            try:
                job = jobs.get_nowait()
            except Exception:
                break
        if job is None:
            break
        q, scene, (yaw, pitch, dist, target), (w, h) = job
        r.yaw, r.pitch, r.dist, r.target = yaw, pitch, dist, np.array(target)
        try:
            img = r.render(w, h, q, scene)
            SimThread._overlay(img, q, None, None)
        except Exception:
            continue
        slot = 1 - slot
        slots[slot, :h, :w] = img
        with info.get_lock():
            info[1], info[2], info[3] = w, h, slot
            info[0] += 1
    del slots
    shm.close()


class SimProcess:
    """Same use as SimThread (.image(), .frame_id, .size, .renderer for the mouse, .stop()),
    but the 3D drawing runs in its own process, so it does not wait for the window, the
    camera or the robot control (Python runs only one of those at a time per process)."""

    def __init__(self, source):
        import multiprocessing as mp
        import threading
        from multiprocessing import shared_memory
        self.source = source
        self.renderer = _View()
        self.size = (520, 420)
        ctx = mp.get_context("spawn")
        self._shm = shared_memory.SharedMemory(create=True, size=2 * MAX_H * MAX_W * 3)
        self._slots = np.ndarray((2, MAX_H, MAX_W, 3), np.uint8, self._shm.buf)
        self._info = ctx.Array("i", 4)
        self._jobs = ctx.Queue()
        self._proc = ctx.Process(target=_render_worker, args=(self._jobs, self._shm.name, self._info), daemon=True)
        self._proc.start()
        self._halt = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    @property
    def frame_id(self):
        return self._info[0]

    def _run(self):
        """Light work here: move the robot model, build the scene, send it to the renderer."""
        import time
        last, sent, sent_at, last_sig = time.time(), 0, 0.0, None
        while not self._halt.is_set():
            now = time.time()
            dt, last = now - last, now
            try:
                twin, plate, blocks, empty, label = self.source()
                q = twin.step(dt)
                sc = build_scene(twin, plate, blocks, empty, now)
                v = self.renderer
                w, h = min(max(self.size[0], 160), MAX_W), min(max(self.size[1], 120), MAX_H)
                sig = (np.round(q, 2).tobytes(), w, h, v.yaw, v.pitch, v.dist,
                       tuple((len(s[0]), round(float(s[0][0, 0]), 1), round(float(s[0][0, 2]), 1)) for s in sc))
                ready = self._info[0] >= sent or now - sent_at > 0.25     # renderer free (or stuck)
                if sig != last_sig and ready:
                    self._jobs.put((q.copy(), sc, (v.yaw, v.pitch, v.dist, tuple(v.target)), (w, h)))
                    sent, sent_at, last_sig = self._info[0] + 1, now, sig
            except Exception as e:
                print(f"simulator: {e}")
                time.sleep(1)
            time.sleep(0.004)

    def image(self):
        with self._info.get_lock():
            n, w, h, slot = self._info[0], self._info[1], self._info[2], self._info[3]
        if n == 0:
            return None
        return self._slots[slot, :h, :w].copy()

    def stop(self):
        self._halt.set()
        try:
            self._jobs.put(None)
            self._proc.join(2)
            if self._proc.is_alive():
                self._proc.terminate()
        except Exception:
            pass
        try:
            del self._slots
            self._shm.close()
            self._shm.unlink()
        except Exception:
            pass


def start_simulator(source):
    """3D drawing in its own process if possible, otherwise in a thread."""
    try:
        return SimProcess(source)
    except Exception as e:
        print(f"simulator: separate process not available ({e}) - drawing in a thread")
        return SimThread(source)
