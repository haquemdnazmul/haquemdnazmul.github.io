"""
Motion-X - vision, weighing and robotics studio for the weight-sorting machine.

  * Face login (laptop webcam), Admin / Operator roles, English / Korean.
  * Dashboard: D455 vision camera, live 3D robot simulator, load cell weight,
    start / stop / auto / pick.
  * Learning: pick height learned per stack layer (automatic, saved).
  * Calibration (Admin): one-click automatic camera-to-robot calibration.
  * Users (Admin): add a new face ID (scan + automatic training), roles, delete.
  * Log: everything the machine did, plus who logged in and what admins changed.

Run (Python 3.12 64-bit):
    py -3.12 studio.py              # normal
    py -3.12 studio.py --dry        # robot commands only simulated (robot does not move)
    py -3.12 studio.py --no-plc     # without the PLC load cell
"""
import csv
import datetime
import os
import queue
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

# VS Code may start another Python (e.g. 3.14) without the camera libraries: use 3.12.
try:
    import cv2
    import pyrealsense2  # noqa: F401
except ModuleNotFoundError:
    import subprocess
    if os.environ.get("STUDIO_RELAUNCHED") != "1":
        env = dict(os.environ, STUDIO_RELAUNCHED="1")
        sys.exit(subprocess.call(["py", "-3.12", os.path.abspath(__file__), *sys.argv[1:]], env=env))
    raise SystemExit("Install with:  py -3.12 -m pip install pyrealsense2 opencv-contrib-python numpy pyserial pillow")

import numpy as np
from PIL import Image, ImageDraw, ImageTk

import config

os.chdir(config.PROJECT_DIR)        # face models / dataset use relative paths (see config)

import face_engine  # noqa: E402
import i18n  # noqa: E402
import machine_engine  # noqa: E402
import sim3d  # noqa: E402
from i18n import t  # noqa: E402

APP_NAME = "Motion-X"

# ------------------------------------------------------------------- look ---
BG, SURFACE, LINE = "#f3f6fb", "#ffffff", "#e3e8f0"
TEXT, MUTED = "#0f172a", "#64748b"
BLUE, PURPLE, CYAN = "#2563eb", "#7c3aed", "#06b6d4"
GREEN, ORANGE, RED, PINK, AMBER = "#16a34a", "#f97316", "#e11d48", "#db2777", "#d97706"
GRAD = ((124, 58, 237), (37, 99, 235), (6, 182, 212))      # purple -> blue -> cyan
FONT = "Malgun Gothic"             # Korean + English
NAV_COLORS = {"dashboard": BLUE, "learning": GREEN, "calibration": ORANGE, "users": PURPLE, "log": CYAN}


def f(size, bold=False):
    return (FONT, size, "bold" if bold else "normal")


def gradient_image(w, h, colors=GRAD):
    """Horizontal multi-colour gradient as a Tk image."""
    xs = np.linspace(0, len(colors) - 1, max(w, 2))
    i = np.minimum(xs.astype(int), len(colors) - 2)
    frac = (xs - i)[:, None]
    c = np.array(colors, float)
    row = (c[i] * (1 - frac) + c[i + 1] * frac).astype(np.uint8)
    return ImageTk.PhotoImage(Image.fromarray(np.repeat(row[None], max(h, 1), axis=0)))


def logo_image(size=40):
    """The Motion-X mark: a gradient rounded square with a white X."""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    grad = Image.new("RGB", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        k = y / (s - 1)
        a, b = (GRAD[0], GRAD[1]) if k < 0.5 else (GRAD[1], GRAD[2])
        kk = k * 2 if k < 0.5 else (k - 0.5) * 2
        gd.line([(0, y), (s, y)], fill=tuple(int(a[j] * (1 - kk) + b[j] * kk) for j in range(3)))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 4, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    m, w = s * 0.27, int(s * 0.12)
    d.line([(m, m), (s - m, s - m)], fill="white", width=w)
    d.line([(s - m, m), (m, s - m)], fill="white", width=w)
    d.ellipse([s * 0.42, s * 0.42, s * 0.58, s * 0.58], fill=(255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


# -------------------------------------------------------------------- log ---
class StudioLog:
    """Collects everything printed (robot commands too) into studio_log.txt + the Log page."""

    def __init__(self):
        self.q = queue.Queue()
        self.file = open(config.STUDIO_LOG, "a", encoding="utf-8", buffering=1)
        self.out = sys.__stdout__
        self.file.write(f"\n===== {APP_NAME} started {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n")

    def write(self, s):
        if self.out:
            try:
                self.out.write(s)
            except (OSError, ValueError):
                pass
        self.file.write(s)
        for line in s.splitlines():
            if line.strip():
                self.q.put(f"{time.strftime('%H:%M:%S')}  {line}")

    def flush(self):
        self.file.flush()


def access(user, event):
    new = not os.path.exists(config.ACCESS_LOG)
    with open(config.ACCESS_LOG, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["time", "user", "event"])
        w.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user, event])
    print(f"[access] {user}: {event}")


def to_photo(bgr, w, h):
    """OpenCV picture -> Tk image, fitted into w x h."""
    ih, iw = bgr.shape[:2]
    s = min(w / iw, h / ih)
    img = cv2.resize(bgr, (max(1, int(iw * s)), max(1, int(ih * s))), interpolation=cv2.INTER_AREA)
    return ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))


class LiveImage:
    """A label showing a stream of pictures. Re-uses one Tk image and pastes new frames into
    it (much faster than making a new Tk image for every frame)."""

    def __init__(self, label):
        self.label, self.photo, self.size = label, None, None

    def show(self, bgr, w=None, h=None):
        if w is not None:                                   # fit into w x h
            ih, iw = bgr.shape[:2]
            s = min(w / iw, h / ih)
            size = (max(1, int(iw * s)), max(1, int(ih * s)))
            if size != (iw, ih):
                bgr = cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)
        pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        if self.photo is None or pil.size != self.size:
            self.photo, self.size = ImageTk.PhotoImage(pil), pil.size
            self.label.config(image=self.photo, text="")
        else:
            self.photo.paste(pil)

    def clear(self, text=""):
        self.photo, self.size = None, None
        self.label.config(image="", text=text)


def setw(widget, **kw):
    """widget.config(...) only for options that really changed (Tk redraws are slow)."""
    old = getattr(widget, "_setw", {})
    new = {k: v for k, v in kw.items() if old.get(k) != v}
    if new:
        widget.config(**new)
        old.update(new)
        widget._setw = old


def button(parent, text, cmd, color=BLUE, fg="white", small=False):
    b = tk.Button(parent, text=text, command=cmd, bg=color, fg=fg, activebackground=color,
                  activeforeground=fg, relief="flat", font=f(9 if small else 10, True),
                  padx=10 if small else 16, pady=5 if small else 8, cursor="hand2", bd=0,
                  disabledforeground="#cbd5e1")
    return b


def card(parent, title, color=BLUE):
    outer = tk.Frame(parent, bg=SURFACE, highlightbackground=LINE, highlightthickness=1)
    tk.Frame(outer, bg=color, height=4).pack(fill="x")
    tk.Label(outer, text=title.upper(), bg=SURFACE, fg=color, font=f(8, True)).pack(anchor="w", padx=12, pady=(8, 2))
    return outer


def page_title(parent, title, text, color):
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x")
    tk.Frame(row, bg=color, width=5, height=26).pack(side="left", padx=(0, 10))
    tk.Label(row, text=title, bg=BG, fg=TEXT, font=f(17, True)).pack(side="left")
    if text:
        tk.Label(parent, text=text, bg=BG, fg=MUTED, font=f(10), wraplength=1000, justify="left").pack(
            anchor="w", pady=(6, 14))


# ================================================================== studio ===
class Studio(tk.Tk):
    def __init__(self, dry=False, use_plc=True):
        super().__init__()
        self.cfg = config.load_config()
        i18n.LANG = self.cfg.get("language", "en")
        self.dry, self.use_plc = dry, use_plc and self.cfg["use_plc"]
        self.title(f"{APP_NAME}  ·  Weight Sorting Studio")
        self.configure(bg=BG)
        self.geometry("1500x900")
        self.minsize(1280, 780)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._logo = ImageTk.PhotoImage(logo_image(64))
        self.iconphoto(True, self._logo)
        self._style()

        self.faces = face_engine.FaceEngine(self.cfg, log=print)
        self.machine = None
        self.user, self.user_role = None, None
        self.webcam = None
        self.last_activity = time.time()
        for ev in ("<Motion>", "<KeyPress>", "<Button>"):
            self.bind_all(ev, lambda e: setattr(self, "last_activity", time.time()), add="+")

        # simulator: always running, shows the machine's robot (or the robot at rest)
        self.idle_twin = sim3d.Twin(place_joints=machine_engine.d.PLACE_JOINTS)
        self.idle_plate = machine_engine.plate_from_calib()
        self.sim = sim3d.start_simulator(self.sim_source)

        self.login = self.main = None
        self.build()
        self.after(50, self.tick)

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                    rowheight=30, font=f(10), borderwidth=0)
        s.configure("Treeview.Heading", background="#eef2ff", foreground=PURPLE, font=f(9, True), relief="flat")
        s.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", TEXT)])
        s.configure("Horizontal.TProgressbar", troughcolor="#e2e8f0", background=GREEN, borderwidth=0,
                    thickness=10)

    # ---- (re)build the screens - also used for the language switch
    def build(self, page=None):
        for w in (self.login, self.main):
            if w is not None:
                w.destroy()
        self.login = LoginScreen(self)
        self.main = MainScreen(self)
        if self.user:
            self.main.pack(fill="both", expand=True)
            self.main.on_login(page)
        else:
            self.show_login()

    def toggle_language(self):
        i18n.LANG = "ko" if i18n.LANG == "en" else "en"
        self.cfg["language"] = i18n.LANG
        config.save_config(self.cfg)
        page = self.main.current_name if self.main else None
        if self.main:
            self.main.users_page.cancel_scan()
        self.build(page)

    # ---- simulator source
    def sim_source(self):
        m = self.machine
        if m is not None and (m.is_alive() or m.status["state"] == "error"):
            label = t("sim_dry") if self.dry else t("sim_live")
            return (m.twin, m.scene["plate"] or self.idle_plate, m.scene["blocks"],
                    bool(m.status["plc_empty"]), label)
        return self.idle_twin, self.idle_plate, [], True, t("sim_idle")

    # ---- webcam for faces (only open while it is needed)
    def open_webcam(self):
        if self.webcam is None:
            self.webcam = face_engine.Webcam(self.cfg["face_camera_index"])
            self.webcam.start()
        return self.webcam

    def close_webcam(self):
        if self.webcam is not None:
            self.webcam.stop()
            self.webcam = None

    def next_camera(self):
        """Login screen: try the next camera (another PC may have the webcam on another number)."""
        self.close_webcam()
        self.cfg["face_camera_index"] = (int(self.cfg["face_camera_index"]) + 1) % 4
        config.save_config(self.cfg)
        self.login.start()

    # ---- screens
    def show_login(self):
        self.main.pack_forget()
        self.login.pack(fill="both", expand=True)
        self.login.start()

    def logged_in(self, name):
        self.user, self.user_role = name, self.faces.role(name)
        access(name, f"login ({self.user_role})")
        self.login.pack_forget()
        self.close_webcam()
        self.last_activity = time.time()
        self.main.pack(fill="both", expand=True)
        self.main.on_login()

    def lock(self, reason="locked"):
        if self.user:
            access(self.user, reason)
        self.user, self.user_role = None, None
        self.main.users_page.cancel_scan()
        self.show_login()

    @property
    def is_admin(self):
        return self.user_role == "Admin"

    # ---- machine
    def start_machine(self, auto=True):
        if self.running:
            return
        self.machine = machine_engine.Machine(log=print, dry=self.dry, use_plc=self.use_plc, auto=auto)
        self.machine.start()
        access(self.user, "machine started" + (" (dry run)" if self.dry else ""))

    def stop_machine(self):
        if self.running:
            self.machine.stop()
            access(self.user, "machine stopped")

    @property
    def running(self):
        return self.machine is not None and self.machine.is_alive()

    # ---- main timer
    def tick(self):
        t0 = time.perf_counter()
        try:
            if self.login.winfo_ismapped():
                self.login.update_view()
            else:
                mins = self.cfg["auto_lock_minutes"]
                if mins and time.time() - self.last_activity > mins * 60:
                    self.lock("auto-locked (no use)")
                else:
                    self.main.update_view()
        except Exception as e:          # never let one bad frame stop the studio
            print(f"display error: {e}")
        # next check on a 16 ms rhythm (up to 60 per second), not 16 ms *after* this one
        self.after(max(1, int(16 - (time.perf_counter() - t0) * 1000)), self.tick)

    def on_close(self):
        if self.running:
            if not messagebox.askyesno(APP_NAME, t("close_q")):
                return
            self.stop_machine()
            self._wait_close(time.time())
            return
        self._finish_close()

    def _wait_close(self, t0):
        if self.running and time.time() - t0 < 30:
            self.after(200, lambda: self._wait_close(t0))
        else:
            self._finish_close()

    def _finish_close(self):
        if self.user:
            access(self.user, "studio closed")
        self.sim.stop()
        self.close_webcam()
        self.destroy()


# ================================================================== header ===
class Header(tk.Canvas):
    """Gradient bar with the Motion-X logo, machine state, user, language and lock."""

    def __init__(self, parent, app, with_user=True):
        super().__init__(parent, height=64, highlightthickness=0, bd=0, bg=BLUE)
        self.app = app
        self._bg = None
        self._logo = ImageTk.PhotoImage(logo_image(40))
        self.bind("<Configure>", self._redraw)
        self.right = tk.Frame(self, bg=PURPLE)
        self.lang = button(self.right, t("lang_btn"), app.toggle_language, "#ffffff", fg=PURPLE, small=True)
        self.lang.pack(side="right", padx=(8, 0))
        if with_user:
            button(self.right, t("lock"), lambda: app.lock("logout"), "#1e1b4b", small=True).pack(side="right", padx=(8, 0))
            self.who = tk.Label(self.right, text="", fg="white", bg=PURPLE, font=f(10, True))
            self.who.pack(side="right", padx=8)
        self.pill = tk.Label(self, text="", font=f(9, True), padx=12, pady=4, fg="white", bg=GREEN)
        self.dry = tk.Label(self, text=t("dry_banner"), font=f(9, True), padx=10, pady=4, fg="#1f2937",
                            bg="#fde68a") if app.dry else None

    def _redraw(self, e=None):
        w, h = self.winfo_width(), self.winfo_height()
        self._bg = gradient_image(w, h)
        self.delete("all")
        self.create_image(0, 0, image=self._bg, anchor="nw")
        self.create_image(18, h // 2, image=self._logo, anchor="w")
        self.create_text(68, h // 2 - 9, text=APP_NAME, anchor="w", fill="white", font=("Segoe UI", 19, "bold"))
        self.create_text(70, h // 2 + 14, text=t("tagline"), anchor="w", fill="#e0e7ff", font=f(8))
        if hasattr(self, "who"):                          # main screen only (not on the login)
            self.create_window(300, h // 2, window=self.pill, anchor="w")
        if self.dry is not None:
            self.create_window(470, h // 2, window=self.dry, anchor="w")
        self.update_idletasks()
        x = w - 16 - self.right.winfo_reqwidth() / 2      # middle of the right-hand controls
        col = self._pixel(x, w)
        self.right.config(bg=col)
        if hasattr(self, "who"):
            self.who.config(bg=col)
        self.create_window(w - 16, h // 2, window=self.right, anchor="e")

    @staticmethod
    def _pixel(x, w):
        """Gradient colour at x, so the controls blend into the bar."""
        k = max(0.0, min(1.0, x / max(w, 1))) * (len(GRAD) - 1)
        i = min(int(k), len(GRAD) - 2)
        fr = k - i
        c = [int(GRAD[i][j] * (1 - fr) + GRAD[i + 1][j] * fr) for j in range(3)]
        return "#%02x%02x%02x" % tuple(c)

    def set_state(self, state):
        colors = {"running": GREEN, "calibrating": ORANGE, "starting": AMBER, "error": RED, "stopped": "#475569"}
        self.pill.config(text=f"{t('machine')} · {t('state_' + state)}", bg=colors.get(state, "#475569"))


# ============================================================ login screen ===
class LoginScreen(tk.Frame):
    def __init__(self, app):
        super().__init__(app, bg=BG)
        self.app = app
        Header(self, app, with_user=False).pack(fill="x")
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        right = tk.Frame(body, bg=SURFACE, highlightbackground=LINE, highlightthickness=1)
        right.pack(side="right", fill="y", padx=(0, 30), pady=30)
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=30, pady=30)
        self.video = tk.Label(left, bg="#0f172a")
        self.video.pack(fill="both", expand=True)
        self.live = LiveImage(self.video)

        tk.Frame(right, bg=PURPLE, height=5).pack(fill="x")
        self._logo = ImageTk.PhotoImage(logo_image(84))
        tk.Label(right, image=self._logo, bg=SURFACE).pack(pady=(40, 6))
        tk.Label(right, text=APP_NAME, bg=SURFACE, fg=TEXT, font=("Segoe UI", 26, "bold")).pack()
        tk.Label(right, text=t("tagline"), bg=SURFACE, fg=MUTED, font=f(10)).pack(pady=(0, 26))
        tk.Label(right, text=t("face_login"), bg=SURFACE, fg=PURPLE, font=f(9, True)).pack(anchor="w", padx=36)
        self.msg = tk.Label(right, text="", bg=SURFACE, fg=TEXT, font=f(16, True), wraplength=380, justify="left")
        self.msg.pack(anchor="w", padx=36, pady=(8, 4))
        self.sub = tk.Label(right, text="", bg=SURFACE, fg=MUTED, font=f(10), wraplength=380, justify="left")
        self.sub.pack(anchor="w", padx=36)
        self.bar = ttk.Progressbar(right, maximum=1, length=380)
        self.bar.pack(anchor="w", padx=36, pady=22)
        tk.Label(right, text=t("login_help"), bg=SURFACE, fg=MUTED, font=f(9), justify="left",
                 wraplength=380).pack(side="bottom", anchor="w", padx=36, pady=(8, 30))
        self.cam_btn = button(right, "", app.next_camera, "#94a3b8", small=True)
        self.cam_btn.pack(side="bottom", anchor="w", padx=36)
        self.streak_name, self.streak = None, 0
        self._img = None

    def start(self):
        self.streak_name, self.streak = None, 0
        self.bar.config(maximum=self.app.cfg["login_frames"], value=0)
        self.msg.config(text=t("starting_camera"), fg=TEXT)
        self.sub.config(text="")
        self.cam_btn.config(text=t("switch_cam", n=self.app.cfg["face_camera_index"]))
        self.app.open_webcam()

    def update_view(self):
        cam = self.app.webcam
        if cam is None:
            return
        if cam.error:
            self.msg.config(text=t("cam_unavailable"), fg=RED)
            self.sub.config(text=cam.error)
            return
        if cam.frame_no == getattr(self, "_fno", -1):         # no new picture yet
            return
        self._fno = cam.frame_no
        frame = cam.frame()
        if frame is None:
            return
        now = time.time()
        if now - getattr(self, "_det_at", 0) < 0.12:          # recognise max ~8x/s, show every frame
            view = frame.copy()
            for (x, y, w, h), color in getattr(self, "_boxes", []):
                cv2.rectangle(view, (x, y), (x + w, y + h), color, 3)
            self.live.show(view, max(self.video.winfo_width(), 320), max(self.video.winfo_height(), 240))
            return
        self._det_at = now
        self._boxes = []
        faces = self.app.faces.detect(frame)
        view = frame.copy()
        need = self.app.cfg["login_frames"]
        if self.app.faces.training:
            self.msg.config(text=t("updating_model"), fg=AMBER)
        elif len(faces) == 1:
            face = faces[0]
            x, y, w, h = map(int, face[:4])
            name, sim, _ = self.app.faces.identify(self.app.faces.feature(frame, face))
            if name and self.app.faces.photo_count(name):
                self.streak = self.streak + 1 if name == self.streak_name else 1
                self.streak_name = name
                color = (80, 200, 80)
                self.msg.config(text=t("hello", name=name), fg=GREEN)
                self.sub.config(text=t("match_hold", role=t("role_" + self.app.faces.role(name)),
                                       pct=self.app.faces.percent(sim)))
                if self.streak >= need:
                    self.app.logged_in(name)
                    return
            else:
                self.streak, self.streak_name = 0, None
                color = (90, 60, 230)
                self.msg.config(text=t("not_registered"), fg=RED)
                self.sub.config(text=t("ask_admin"))
            cv2.rectangle(view, (x, y), (x + w, y + h), color, 3)
            self._boxes = [((x, y, w, h), color)]
        else:
            self.streak, self.streak_name = 0, None
            self.msg.config(text=t("look_camera") if not faces else t("one_person"), fg=TEXT)
            self.sub.config(text="")
        setw(self.bar, value=self.streak)
        self.live.show(view, max(self.video.winfo_width(), 320), max(self.video.winfo_height(), 240))


# ============================================================= main screen ===
class MainScreen(tk.Frame):
    def __init__(self, app):
        super().__init__(app, bg=BG)
        self.app = app
        self.header = Header(self, app)
        self.header.pack(fill="x")

        self.statusbar = StatusBar(self, app)
        self.statusbar.pack(side="bottom", fill="x")
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        self.nav = tk.Frame(body, bg=SURFACE, highlightbackground=LINE, highlightthickness=1)
        self.nav.pack(side="left", fill="y")
        tk.Label(self.nav, text="", bg=SURFACE, width=22).pack()
        self.content = tk.Frame(body, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)

        self.dash = DashboardPage(self.content, app)
        self.learn_page = LearningPage(self.content, app)
        self.cal_page = CalibrationPage(self.content, app)
        self.users_page = UsersPage(self.content, app)
        self.log_page = LogPage(self.content, app)
        self.pages = [("dashboard", self.dash, False), ("learning", self.learn_page, False),
                      ("calibration", self.cal_page, True), ("users", self.users_page, True),
                      ("log", self.log_page, False)]
        self.nav_items = {}
        self.current, self.current_name = None, None

    def on_login(self, page=None):
        app = self.app
        self.header.who.config(text=f"{app.user}  ·  {t('role_' + app.user_role)}")
        for w in self.nav_items.values():
            w[0].destroy()
        self.nav_items = {}
        for name, pg, admin_only in self.pages:
            if admin_only and not app.is_admin:
                continue
            row = tk.Frame(self.nav, bg=SURFACE, cursor="hand2")
            row.pack(fill="x", pady=1)
            bar = tk.Frame(row, bg=SURFACE, width=4)
            bar.pack(side="left", fill="y")
            dot = tk.Label(row, text="●", bg=SURFACE, fg=NAV_COLORS[name], font=f(11))
            dot.pack(side="left", padx=(16, 8), pady=10)
            lbl = tk.Label(row, text=t("nav_" + name), bg=SURFACE, fg=TEXT, font=f(11), anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            for w in (row, dot, lbl):
                w.bind("<Button-1>", lambda e, n=name, p=pg: self.open(n, p))
            self.nav_items[name] = (row, bar, dot, lbl)
        names = [n for n, _, a in self.pages if not a or app.is_admin]
        target = page if page in names else "dashboard"
        self.open(target, dict((n, p) for n, p, _ in self.pages)[target])

    def open(self, name, page):
        if self.current:
            self.current.pack_forget()
        self.current, self.current_name = page, name
        page.pack(fill="both", expand=True, padx=20, pady=16)
        for n, (row, bar, dot, lbl) in self.nav_items.items():
            sel = n == name
            bg = "#eef2ff" if sel else SURFACE
            for w in (row, dot, lbl):
                w.config(bg=bg)
            bar.config(bg=NAV_COLORS[n] if sel else SURFACE)
            lbl.config(fg=NAV_COLORS[n] if sel else TEXT, font=f(11, sel))
        if hasattr(page, "on_show"):
            page.on_show()

    def update_view(self):
        # pictures: every tick (as soon as a new frame is ready); text: 5 times a second
        if self.current and hasattr(self.current, "update_pictures"):
            self.current.update_pictures()
        now = time.time()
        if now - getattr(self, "_slow_at", 0) < 0.2:
            return
        self._slow_at = now
        m = self.app.machine
        if m is None:
            state = "stopped"
        else:
            state = m.status["state"] if m.is_alive() or m.status["state"] == "error" else "stopped"
        self.header.set_state(state)
        self.statusbar.update_view()
        self.log_page.pump()
        if self.current and hasattr(self.current, "update_view"):
            self.current.update_view()


class StatusBar(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=SURFACE, highlightbackground=LINE, highlightthickness=1)
        self.app = app
        self.items = {}
        for key in ("sb_robot", "sb_camera", "sb_plc", "sb_face"):
            dot = tk.Label(self, text="●", bg=SURFACE, fg="#cbd5e1", font=f(10))
            dot.pack(side="left", padx=(14, 4), pady=4)
            lbl = tk.Label(self, text=t(key), bg=SURFACE, fg=MUTED, font=f(9))
            lbl.pack(side="left")
            self.items[key] = dot
        self.clock = tk.Label(self, text="", bg=SURFACE, fg=MUTED, font=f(9))
        self.clock.pack(side="right", padx=14)
        tk.Label(self, text=f"{APP_NAME} 2.1", bg=SURFACE, fg=PURPLE, font=f(9, True)).pack(side="right", padx=6)

    def update_view(self):
        m, run = self.app.machine, self.app.running
        st = m.status if m else {}
        robot_ok = run and st.get("state") in ("running", "calibrating")
        self.items["sb_robot"].config(fg=GREEN if robot_ok else ("#cbd5e1" if not run else AMBER))
        self.items["sb_camera"].config(fg=GREEN if robot_ok else "#cbd5e1")
        self.items["sb_plc"].config(fg=(GREEN if st.get("plc_ok") else RED) if run and self.app.use_plc else "#cbd5e1")
        self.items["sb_face"].config(fg=AMBER if self.app.faces.training else GREEN)
        self.clock.config(text=time.strftime("%Y-%m-%d  %H:%M:%S"))


# ================================================================ dashboard ===
class DashboardPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        right = tk.Frame(self, bg=BG, width=300)
        right.pack(side="right", fill="y", padx=(16, 0))
        center = tk.Frame(self, bg=BG)
        center.pack(side="left", fill="both", expand=True)

        views = tk.Frame(center, bg=BG)
        views.pack(fill="both", expand=True)
        views.columnconfigure(0, weight=1, uniform="v")
        views.columnconfigure(1, weight=1, uniform="v")
        views.rowconfigure(0, weight=1)
        c1 = card(views, t("camera_view"), BLUE)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.video = tk.Label(c1, bg="#0f172a", text=t("machine_stopped"), fg="#94a3b8", font=f(13))
        self.video.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        c2 = card(views, t("sim_view"), PURPLE)
        c2.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.simview = tk.Label(c2, bg="#eef2ff", cursor="fleur")
        self.simview.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.sim_badge = tk.Label(c2, text="", bg=PURPLE, fg="white", font=f(8, True), padx=8, pady=2)
        self.sim_badge.place(relx=1.0, x=-14, y=34, anchor="ne")
        self.suction = tk.Label(c2, text="", bg=GREEN, fg="white", font=f(8, True), padx=8, pady=2)
        self.simview.bind("<ButtonPress-1>", self._drag_start)
        self.simview.bind("<B1-Motion>", self._drag)
        self.simview.bind("<MouseWheel>", self._wheel)
        self.simview.bind("<Double-Button-1>", lambda e: app.sim.renderer.reset_view())

        ctrl = tk.Frame(center, bg=BG)
        ctrl.pack(fill="x", pady=(12, 0))
        self.b_start = button(ctrl, "▶  " + t("start"), lambda: app.start_machine(auto=True), GREEN)
        self.b_start.pack(side="left")
        self.b_stop = button(ctrl, "■  " + t("stop"), app.stop_machine, RED)
        self.b_stop.pack(side="left", padx=8)
        self.b_auto = button(ctrl, t("auto_on"), self.toggle_auto, BLUE)
        self.b_auto.pack(side="left", padx=8)
        button(ctrl, t("pick_now"), lambda: self.send("pick"), ORANGE).pack(side="left", padx=4)
        button(ctrl, t("next_block"), lambda: self.send("next"), PURPLE).pack(side="left", padx=4)
        button(ctrl, t("retry_skipped"), lambda: self.send("clear"), CYAN).pack(side="left", padx=4)
        self.b_return = button(ctrl, "↩  " + t("return_block"), self.return_block, PINK)
        self.b_return.pack(side="left", padx=4)

        c = card(right, t("card_machine"), BLUE)
        c.pack(fill="x")
        self.state_lbl = tk.Label(c, text=i18n.status("Stopped"), bg=SURFACE, fg=TEXT, font=f(12, True),
                                  wraplength=270, justify="left")
        self.state_lbl.pack(anchor="w", padx=12, pady=(0, 12))

        c = card(right, t("card_loadcell"), GREEN)
        c.pack(fill="x", pady=10)
        row = tk.Frame(c, bg=SURFACE)
        row.pack(fill="x", padx=12)
        self.weight = tk.Label(row, text="--", bg=SURFACE, fg=TEXT, font=("Segoe UI", 32, "bold"))
        self.weight.pack(side="left")
        tk.Label(row, text=" g", bg=SURFACE, fg=MUTED, font=f(14)).pack(side="left", anchor="s", pady=10)
        self.lc_badge = tk.Label(row, text="—", bg="#94a3b8", fg="white", font=f(9, True), padx=9, pady=3)
        self.lc_badge.pack(side="right")
        self.plc_lbl = tk.Label(c, text="", bg=SURFACE, fg=MUTED, font=f(9), wraplength=260, justify="left")
        self.plc_lbl.pack(anchor="w", padx=12, pady=(2, 12))

        c = card(right, t("card_session"), ORANGE)
        c.pack(fill="x")
        row = tk.Frame(c, bg=SURFACE)
        row.pack(fill="x", padx=8, pady=(0, 12))
        self.counts = {}
        for key, label, col in (("ok", "weighed", GREEN), ("fail", "missed", AMBER), ("skipped", "skipped", RED)):
            box = tk.Frame(row, bg=SURFACE)
            box.pack(side="left", expand=True, fill="x")
            self.counts[key] = tk.Label(box, text="0", bg=SURFACE, fg=col, font=("Segoe UI", 22, "bold"))
            self.counts[key].pack()
            tk.Label(box, text=t(label), bg=SURFACE, fg=MUTED, font=f(9)).pack()

        c = card(right, t("card_weights"), PINK)
        c.pack(fill="both", expand=True, pady=10)
        self.weights = tk.Listbox(c, bg=SURFACE, fg=TEXT, font=f(10), bd=0, highlightthickness=0,
                                  selectbackground="#fce7f3", selectforeground=TEXT, activestyle="none")
        self.weights.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._n_weights, self._drag0 = -1, None
        self.sim_live = LiveImage(self.simview)
        self.cam_live = LiveImage(self.video)

    # ---- simulator mouse
    def _drag_start(self, e):
        r = self.app.sim.renderer
        self._drag0 = (e.x, e.y, r.yaw, r.pitch)

    def _drag(self, e):
        if self._drag0:
            x0, y0, yaw, pitch = self._drag0
            r = self.app.sim.renderer
            r.yaw = yaw - (e.x - x0) * 0.4
            r.pitch = max(5.0, min(85.0, pitch + (e.y - y0) * 0.3))

    def _wheel(self, e):
        r = self.app.sim.renderer
        r.dist = max(300.0, min(1600.0, r.dist * (0.9 if e.delta > 0 else 1.1)))

    def send(self, c):
        if self.app.running:
            self.app.machine.cmd(c)

    def return_block(self):
        if self.app.running and messagebox.askyesno(APP_NAME, t("return_q")):
            access(self.app.user, "return block")
            self.app.machine.cmd("return")

    def toggle_auto(self):
        if self.app.running:
            m = self.app.machine
            m.cmd("auto_off" if m.status["auto"] else "auto_on")

    def update_pictures(self):
        """Fast path, every tick: simulator and camera pictures (only when a new frame exists)."""
        w, h = max(self.simview.winfo_width() - 4, 160), max(self.simview.winfo_height() - 4, 120)
        self.app.sim.size = (w, h)
        fid = getattr(self.app.sim, "frame_id", 0)
        if fid != getattr(self, "_sim_fid", -1):
            img = self.app.sim.image()
            if img is not None:
                self._sim_fid = fid
                self.sim_live.show(img)
                self.app.fps_count = getattr(self.app, "fps_count", 0) + 1
        m = self.app.machine
        if self.app.running and m.frame_no != getattr(self, "_cam_fno", -1):
            frame = m.frame()
            if frame is not None:
                self._cam_fno = m.frame_no
                self.cam_live.show(frame, max(self.video.winfo_width() - 4, 320),
                                   max(self.video.winfo_height() - 4, 240))

    def update_view(self):
        """Slow path, 5 times a second: buttons, numbers, badges (changed values only)."""
        m, running = self.app.machine, self.app.running
        setw(self.b_start, state="disabled" if running else "normal")
        setw(self.b_stop, state="normal" if running else "disabled")
        st0 = m.status if m is not None else {}
        on_scale = (not self.app.use_plc) or self.app.dry or (st0.get("plc_ok") and not st0.get("plc_empty"))
        can = running and st0.get("can_return") and on_scale and st0.get("state") == "running"
        setw(self.b_return, state="normal" if can else "disabled")
        twin, _, _, _, label = self.app.sim_source()
        setw(self.sim_badge, text=label, bg=GREEN if label == t("sim_live") else
             (PURPLE if label == t("sim_dry") else "#94a3b8"))
        if twin.vacuum != getattr(self, "_vac", None):
            self._vac = twin.vacuum
            if twin.vacuum:
                self.suction.config(text=t("suction_on"))
                self.suction.place(relx=1.0, x=-14, y=60, anchor="ne")
            else:
                self.suction.place_forget()
        if not running and getattr(self, "_cam_fno", None) != -1:
            self._cam_fno = -1
            self.cam_live.clear(t("machine_stopped"))
        if m is None:
            return
        st = m.status
        setw(self.b_auto, text=t("auto_on") if st["auto"] else t("auto_off"), bg=BLUE if st["auto"] else "#94a3b8")
        setw(self.state_lbl, text=i18n.status(st["text"]), fg=RED if st["state"] == "error" else
             (GREEN if st["text"] == "READY" else TEXT))
        if self.app.use_plc:
            wv = st["weight"]
            setw(self.weight, text="--" if wv is None or not st["plc_ok"] else f"{wv:g}")
            if not st["plc_ok"]:
                setw(self.lc_badge, text=t("no_data"), bg=RED)
            else:
                setw(self.lc_badge, text=t("empty") if st["plc_empty"] else t("loaded"),
                     bg=GREEN if st["plc_empty"] else ORANGE)
            err = st["plc_error"] or ""
            setw(self.plc_lbl, text=t("plc_ok") if st["plc_ok"] else
                 (t("plc_adapter") if "port lost" in err else t("plc_connecting")))
        else:
            setw(self.weight, text="--")
            setw(self.lc_badge, text=t("plc_off"), bg="#94a3b8")
        for k, lbl in self.counts.items():
            setw(lbl, text=str(st[k]))
        if len(m.weights) != self._n_weights:
            self._n_weights = len(m.weights)
            self.weights.delete(0, "end")
            for tm, g in m.weights:
                self.weights.insert("end", f"  {tm}      {g:g} g")


# ================================================================= learning ===
class LearningPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        page_title(self, t("learn_title"), t("learn_text"), GREEN)
        cols = ("layer", "height", "offset", "ok", "fail", "rate", "updated")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=10)
        for c in cols:
            self.tree.heading(c, text=t("col_" + c))
            self.tree.column(c, width=140, anchor="center")
        self.tree.pack(fill="x")
        self.default = tk.Label(self, text="", bg=BG, fg=MUTED, font=f(10))
        self.default.pack(anchor="w", pady=12)
        self.reset_btn = button(self, t("reset_learning"), self.reset, RED)
        self.reset_btn.pack(anchor="w")
        self._sig = None

    def learner(self):
        m = self.app.machine
        if m is not None:
            return m.learner
        return machine_engine.HeightLearner()

    def on_show(self):
        self._sig = None
        self.reset_btn.config(state="normal" if self.app.is_admin else "disabled")

    def update_view(self):
        lr = self.learner()
        rows = lr.rows()
        sig = str(rows)
        if sig == self._sig:
            return
        self._sig = sig
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            pick = t("taught_z", z=r["taught"]) if r.get("taught") is not None else f"{r['offset']:+.0f}"
            self.tree.insert("", "end", values=(r["layer"], f"~{r['height']}", pick,
                                                r["ok"], r["fail"], f"{r['rate']:.0f}%", r["updated"]))
        self.default.config(text=t("learn_default", off=lr.default))

    def reset(self):
        if messagebox.askyesno(APP_NAME, t("reset_q")):
            self.learner().reset()
            access(self.app.user, "learning reset")
            self._sig = None


# ============================================================== calibration ===
class CalibrationPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        page_title(self, t("cal_title"), t("cal_text"), ORANGE)
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x")
        self.run_btn = button(row, t("run_cal"), self.run_cal, ORANGE)
        self.run_btn.pack(side="left")
        button(row, t("cancel"), lambda: self.app.running and self.app.machine.cmd("cancel_calibration"),
               "#94a3b8").pack(side="left", padx=8)
        self.info = tk.Label(self, text="", bg=BG, fg=TEXT, font=f(11), justify="left")
        self.info.pack(anchor="w", pady=10)
        c = card(self, t("camera_view"), ORANGE)
        c.pack(fill="both", expand=True)
        self.video = tk.Label(c, bg="#0f172a")
        self.video.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.live = LiveImage(self.video)
        self._pending = False

    def run_cal(self):
        if not messagebox.askyesno(APP_NAME, t("cal_confirm")):
            return
        access(self.app.user, "calibration started")
        if not self.app.running:
            self.app.start_machine(auto=False)
            self._pending = True            # send the command once the machine is up
        else:
            self.app.machine.cmd("calibrate")

    def update_view(self):
        m = self.app.machine
        if self._pending and m is not None and m.status["state"] == "running":
            m.cmd("calibrate")
            self._pending = False
        elif self._pending and (m is None or not m.is_alive()):
            self._pending = False           # machine could not start (see Log)
        calib = os.path.join(config.ROBOT_DIR, "d455_calib.json")
        if m is not None and m.status["calib_date"]:
            last = t("cal_last", date=m.status["calib_date"], err=m.status["calib_error"] or 0)
        elif os.path.exists(calib):
            last = t("cal_last_date", date=time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(calib))))
        else:
            last = t("cal_none")
        state = i18n.status(m.status["text"]) if m is not None and self.app.running else i18n.status("Stopped")
        self.info.config(text=f"{last}\n{t('cal_now', state=state)}")
        busy = m is not None and m.status["state"] in ("calibrating", "starting")
        setw(self.run_btn, state="disabled" if busy or self._pending else "normal")

    def update_pictures(self):
        m = self.app.machine
        if m is not None and self.app.running and m.frame_no != getattr(self, "_cam_fno", -1):
            frame = m.frame()
            if frame is not None:
                self._cam_fno = m.frame_no
                self.live.show(frame, max(self.video.winfo_width() - 4, 320), max(self.video.winfo_height() - 4, 240))


# ==================================================================== users ===
class UsersPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        page_title(self, t("users_title"), t("users_text"), PURPLE)
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", pady=(0, 10))
        button(row, t("add_face"), self.add, GREEN).pack(side="left")
        button(row, t("rescan"), self.rescan, BLUE).pack(side="left", padx=6)
        button(row, t("make_admin"), lambda: self.set_role("Admin"), PURPLE).pack(side="left", padx=6)
        button(row, t("make_operator"), lambda: self.set_role("Operator"), CYAN).pack(side="left", padx=6)
        button(row, t("delete"), self.delete, RED).pack(side="left", padx=6)
        self.train_lbl = tk.Label(row, text="", bg=BG, fg=MUTED, font=f(10, True))
        self.train_lbl.pack(side="right")

        cols = ("name", "role", "id", "dept", "photos", "reg")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=8)
        for c, w in zip(cols, (200, 110, 90, 180, 110, 130)):
            self.tree.heading(c, text=t("col_" + c))
            self.tree.column(c, width=w, anchor="w" if c == "name" else "center")
        self.tree.pack(fill="x")

        self.scan = tk.Frame(self, bg=BG)
        top = tk.Frame(self.scan, bg=BG)
        top.pack(fill="x", pady=(14, 6))
        self.scan_msg = tk.Label(top, text="", bg=BG, fg=TEXT, font=f(14, True))
        self.scan_msg.pack(side="left")
        button(top, t("cancel_scan"), self.cancel_scan, "#94a3b8").pack(side="right")
        self.scan_bar = ttk.Progressbar(self.scan, maximum=1)
        self.scan_bar.pack(fill="x")
        self.scan_video = tk.Label(self.scan, bg="#0f172a")
        self.scan_video.pack(fill="both", expand=True, pady=8)
        self.scan_live = LiveImage(self.scan_video)
        self.enroller, self.pending = None, None

    def on_show(self):
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for u in self.app.faces.users():
            photos = u["photos"] if u["photos"] else t("no_scan")
            self.tree.insert("", "end", iid=u["name"], values=(u["name"], t("role_" + u["role"]), u["ID"],
                                                               u["Department"], photos, u["Registered"]))

    def selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, t("select_first"))
            return None
        return sel[0]

    def add(self):
        PersonDialog(self, self.app, on_ok=self.begin_scan)

    def rescan(self):
        name = self.selected()
        if name:
            p = self.app.faces.people.get(name, {})
            self.begin_scan(name, {k: p.get(k, "") for k in face_engine.DETAIL_FIELDS},
                            self.app.faces.role(name))

    def set_role(self, role):
        name = self.selected()
        if not name:
            return
        if role == "Operator" and name in self.app.faces.admins() and len(self.app.faces.admins()) <= 1:
            messagebox.showwarning(APP_NAME, t("last_admin"))
            return
        self.app.faces.set_role(name, role)
        access(self.app.user, f"{name} -> {role}")
        self.refresh()

    def delete(self):
        name = self.selected()
        if not name:
            return
        if name == self.app.user:
            messagebox.showwarning(APP_NAME, t("no_self_delete"))
            return
        if name in self.app.faces.admins() and len(self.app.faces.admins()) <= 1:
            messagebox.showwarning(APP_NAME, t("last_admin_del"))
            return
        if messagebox.askyesno(APP_NAME, t("delete_q", name=name)):
            self.app.faces.delete_person(name)
            access(self.app.user, f"deleted face ID {name}")
            self.refresh()

    # ---- scanning
    def begin_scan(self, name, details, role):
        self.pending = (name, details, role)
        self.enroller = face_engine.Enroller(self.app.faces, name, self.app.cfg["scan_photos"])
        self.scan_bar.config(maximum=self.enroller.count, value=0)
        self.scan_msg.config(text=t("scanning", name=name), fg=TEXT)
        self.scan.pack(fill="both", expand=True)
        self.app.open_webcam()

    def cancel_scan(self):
        if self.enroller is not None:
            self.enroller, self.pending = None, None
            self.app.close_webcam()
        self.scan.pack_forget()

    def update_view(self):
        tr = self.app.faces.training
        setw(self.train_lbl, text=t("training") if tr else "✓ " + t("model_ok"), fg=AMBER if tr else GREEN)

    def update_pictures(self):
        """Face scan: every new webcam picture (fast path)."""
        e = self.enroller
        if e is None:
            return
        cam = self.app.webcam
        if cam is not None and cam.error:
            self.scan_msg.config(text=cam.error, fg=RED)
            return
        if cam is None or cam.frame_no == getattr(self, "_fno", -1):     # new pictures only
            return
        self._fno = cam.frame_no
        frame = cam.frame()
        if frame is None:
            return
        view = e.feed(frame)
        self.scan_bar.config(value=len(e.crops))
        self.scan_msg.config(text=f"{e.name}:  {i18n.pose(e.message)}   ({len(e.crops)}/{e.count})")
        self.scan_live.show(view, max(self.scan_video.winfo_width(), 320), max(self.scan_video.winfo_height(), 240))
        if e.done:
            self.finish_scan()

    def finish_scan(self):
        e, (name, details, role) = self.enroller, self.pending
        self.enroller, self.pending = None, None
        self.app.close_webcam()
        self.scan.pack_forget()
        if e.error:
            msg = t("dup_face", other=e.dup[0], pct=e.dup[1]) if e.dup else e.error
            messagebox.showwarning(APP_NAME, msg)
            return
        e.save()
        self.app.faces.save_person(name, details, role)
        access(self.app.user, f"added/updated face ID {name} ({role})")
        self.app.faces.train_in_background(done=lambda: print(f"Face ID ready: {name}"))
        self.refresh()
        messagebox.showinfo(APP_NAME, t("saved_face", name=name, n=len(e.crops)))


class PersonDialog(tk.Toplevel):
    def __init__(self, page, app, on_ok):
        super().__init__(app)
        self.app, self.on_ok = app, on_ok
        self.title(t("new_face_id"))
        self.configure(bg=SURFACE)
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()
        tk.Frame(self, bg=PURPLE, height=5).grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(self, text=t("new_face_id"), bg=SURFACE, fg=TEXT, font=f(14, True)).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=22, pady=(16, 10))
        self.vars = {}
        i = 2
        for field in ["Name"] + face_engine.DETAIL_FIELDS:
            tk.Label(self, text=t("f_" + field), bg=SURFACE, fg=MUTED, font=f(10)).grid(row=i, column=0, sticky="w", padx=22, pady=4)
            v = tk.StringVar()
            tk.Entry(self, textvariable=v, bg="#f1f5f9", fg=TEXT, insertbackground=TEXT, relief="flat",
                     font=f(11), width=28).grid(row=i, column=1, padx=(0, 22), pady=4, ipady=5)
            self.vars[field] = v
            i += 1
        tk.Label(self, text=t("f_Role"), bg=SURFACE, fg=MUTED, font=f(10)).grid(row=i, column=0, sticky="w", padx=22, pady=4)
        self.role = ttk.Combobox(self, values=[t("role_Admin"), t("role_Operator")], state="readonly", width=26)
        self.role.set(t("role_Operator"))
        self.role.grid(row=i, column=1, sticky="w", padx=(0, 22), pady=4)
        row = tk.Frame(self, bg=SURFACE)
        row.grid(row=i + 1, column=0, columnspan=2, sticky="e", padx=22, pady=18)
        button(row, t("cancel"), self.destroy, "#94a3b8").pack(side="left", padx=6)
        button(row, t("next_scan"), self.ok, GREEN).pack(side="left")

    def ok(self):
        name = self.vars["Name"].get().strip()
        if not name or any(c in name for c in '\\/:*?"<>|'):
            messagebox.showwarning(APP_NAME, t("bad_name"), parent=self)
            return
        if name in self.app.faces.people or self.app.faces.photo_count(name):
            if not messagebox.askyesno(APP_NAME, t("exists_q", name=name), parent=self):
                return
        details = {k: self.vars[k].get().strip() for k in face_engine.DETAIL_FIELDS}
        role = "Admin" if self.role.get() == t("role_Admin") else "Operator"
        self.destroy()
        self.on_ok(name, details, role)


# ====================================================================== log ===
class LogPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        page_title(self, t("log_title"), t("log_saved", a=config.STUDIO_LOG, b=config.ACCESS_LOG), CYAN)
        c = tk.Frame(self, bg=SURFACE, highlightbackground=LINE, highlightthickness=1)
        c.pack(fill="both", expand=True)
        self.text = tk.Text(c, bg=SURFACE, fg=TEXT, font=("Consolas", 10), relief="flat",
                            wrap="none", state="disabled", padx=10, pady=8)
        self.text.pack(fill="both", expand=True)
        for tag, col in (("warn", AMBER), ("err", RED), ("ok", GREEN), ("acc", PURPLE), ("cmd", "#94a3b8")):
            self.text.tag_config(tag, foreground=col)
        self.history = getattr(app, "_log_history", [])
        app._log_history = self.history
        if self.history:
            self._insert(self.history[-1500:])

    def _insert(self, lines):
        self.text.config(state="normal")
        for line in lines:
            tag = ("err" if "ERROR" in line else "warn" if "WARNING" in line or "SKIP" in line
                   else "ok" if "arrived" in line or "saved" in line.lower() else
                   "acc" if "[access]" in line else "cmd" if ">>" in line else "")
            self.text.insert("end", line + "\n", tag)
        if int(self.text.index("end-1c").split(".")[0]) > 3000:
            self.text.delete("1.0", "1000.0")
        self.text.see("end")
        self.text.config(state="disabled")

    def pump(self):
        log = sys.stdout if isinstance(sys.stdout, StudioLog) else None
        if log is None:
            return
        lines = []
        while not log.q.empty() and len(lines) < 300:
            lines.append(log.q.get())
        if lines:
            self.history.extend(lines)
            del self.history[:-3000]
            self._insert(lines)


# ===================================================================== main ===
def main():
    try:                                    # sharp text on scaled Windows displays
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MotionX.Studio")
    except (AttributeError, OSError):
        pass
    cv2.setNumThreads(2)                    # leave CPU cores for the 3D view, camera and robot
    sys.stdout = sys.stderr = StudioLog()
    if "--selftest" in sys.argv:
        selftest()
        return
    try:
        app = Studio(dry="--dry" in sys.argv, use_plc="--no-plc" not in sys.argv)
    except BaseException as e:              # the exe has no console: show why it cannot start
        import traceback
        traceback.print_exc()
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, f"{APP_NAME} could not start:\n\n{e}\n\nDetails: {config.STUDIO_LOG}")
        root.destroy()
        return
    app.mainloop()


def selftest():
    """Motion-X.exe --selftest : check every part on this computer -> selftest.txt"""
    lines = [f"{APP_NAME} self-test {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
             f"folder: {config.PROJECT_DIR}", f"exe: {config.FROZEN}"]

    def check(name, fn):
        try:
            lines.append(f"OK    {name}: {fn()}")
        except BaseException as e:
            lines.append(f"FAIL  {name}: {e}")

    import serial.tools.list_ports
    check("OpenCV", lambda: cv2.__version__)
    check("RealSense library", lambda: __import__("pyrealsense2").__version__ if hasattr(
        __import__("pyrealsense2"), "__version__") else "loaded")
    check("D455 camera", lambda: [d.get_info(__import__("pyrealsense2").camera_info.name) for d in
                                  __import__("pyrealsense2").context().query_devices()] or "not connected")
    check("face models", lambda: f"{len(face_engine.FaceEngine(config.load_config(), log=lambda m: None).users())} users")
    check("robot 3D model", lambda: f"{sum(len(f_) for _, f_ in sim3d.Renderer().meshes)} triangles")
    check("simulator render", lambda: sim3d.Renderer().render(320, 240, np.zeros(6), []).shape)

    def sim_process():
        tw = sim3d.Twin()
        sp = sim3d.start_simulator(lambda: (tw, None, [], True, ""))
        try:
            t0 = time.time()
            while time.time() - t0 < 20 and getattr(sp, "frame_id", 0) == 0:
                time.sleep(0.2)
            n = getattr(sp, "frame_id", 0)
            if n == 0:
                raise RuntimeError("no frame in 20 s")
            return f"{type(sp).__name__}, first frame after {time.time() - t0:.1f} s"
        finally:
            sp.stop()
    check("simulator process", sim_process)
    check("calibration", lambda: "found" if os.path.exists(machine_engine.d.CALIB_FILE) else "missing - run calibration")
    check("serial ports", lambda: [f"{p.device} {p.hwid}" for p in serial.tools.list_ports.comports()])
    check("robot USB (CH340)", lambda: machine_engine.d.find_port(machine_engine.d.ROBOT_USB_ID, "not found"))
    import plc_cnet
    check("PLC USB-RS485 (CH9101)", lambda: plc_cnet.find_port(plc_cnet.PLC_USB_ID, "not found"))
    for i in range(3):
        def cam(i=i):
            c = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            ok = c.isOpened() and c.read()[0]
            c.release()
            return "picture OK" if ok else "no camera"
        check(f"camera index {i}", cam)
    out = os.path.join(config.STUDIO_DIR, "selftest.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()        # the exe's simulator process starts through here
    main()
