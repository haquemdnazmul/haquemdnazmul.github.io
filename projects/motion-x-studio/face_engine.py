"""Face login for the studio: recognise people, add new face IDs, retrain automatically.

Uses the same data as face_scan.py (dataset/<name>/*.jpg 112x112 crops, people.json,
face_embeddings.npz) and the same OpenCV models (YuNet detector + SFace recogniser),
so both programs see the same people. Roles ("Admin" / "Operator") are stored in
people.json as the extra field "Role".

All model/data paths are relative: the studio runs with the project folder as the
working directory, because OpenCV cannot open files under a path with Korean letters.
"""
import datetime
import json
import os
import shutil
import threading
import time

import cv2
import numpy as np

import config

ROLES = ("Admin", "Operator")
DETAIL_FIELDS = ["ID", "Department", "Phone", "Notes"]
SCAN_POSES = ["Look straight at the camera", "Turn your head slightly LEFT",
              "Turn your head slightly RIGHT", "Tilt your head slightly UP",
              "Tilt your head slightly DOWN"]


def _load_image(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def _save_image(path, img):
    ok, buf = cv2.imencode(".jpg", img)
    if ok:
        buf.tofile(path)


# ------------------------------------------------------------------ webcam ---
class Webcam(threading.Thread):
    """Reads the face camera in the background; .frame() gives the newest picture."""

    def __init__(self, index):
        super().__init__(daemon=True)
        self.index = index
        self._frame, self._lock = None, threading.Lock()
        self._halt = threading.Event()
        self.error = ""
        self.cap = None
        self.frame_no = 0                      # counts pictures (the GUI only works on new ones)

    def run(self):
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
            cap = cv2.VideoCapture(self.index, backend)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap = cap
                break
            cap.release()
        if self.cap is None:
            self.error = (f"Cannot open the face camera (index {self.index}). Close other apps "
                          "using it and check Windows Settings > Privacy > Camera.")
            return
        while not self._halt.is_set():
            ok, f = self.cap.read()
            if ok:
                with self._lock:
                    self._frame = cv2.flip(f, 1)       # mirror: feels natural to the user
                    self.frame_no += 1
            else:
                time.sleep(0.02)
        self.cap.release()

    def frame(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self):
        self._halt.set()
        self.join(2)


# ------------------------------------------------------------------- engine ---
class FaceEngine:
    def __init__(self, cfg, log=print):
        self.cfg, self.log = cfg, log
        for m in (config.DETECTOR_MODEL, config.RECOGNIZER_MODEL):
            if not os.path.exists(m):
                raise SystemExit(f"Missing face model {m} in {os.getcwd()} "
                                 "(download from github.com/opencv/opencv_zoo).")
        self.detector = cv2.FaceDetectorYN.create(config.DETECTOR_MODEL, "", (640, 480),
                                                  0.85, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(config.RECOGNIZER_MODEL, "")
        self.names = np.array([])
        self.feats = np.zeros((0, 128), np.float32)
        self.training = False
        self.people = self._load_people()
        self._first_admins()
        if self._out_of_date():
            self.log("Face data changed since last training - training now")
            self.train()
        else:
            self._load_embeddings()

    # ---- people / roles
    def _load_people(self):
        if os.path.exists(config.PEOPLE_FILE):
            with open(config.PEOPLE_FILE, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_people(self):
        if os.path.exists(config.PEOPLE_FILE) and not os.path.exists(config.PEOPLE_FILE + ".bak"):
            shutil.copy(config.PEOPLE_FILE, config.PEOPLE_FILE + ".bak")   # one-time backup
        with open(config.PEOPLE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.people, f, ensure_ascii=False, indent=2)

    def _first_admins(self):
        changed = False
        for name in self.cfg["first_admins"]:
            if name in self.people and "Role" not in self.people[name]:
                self.people[name]["Role"] = "Admin"
                changed = True
        if changed:
            self._save_people()

    def role(self, name):
        return self.people.get(name, {}).get("Role", "Operator")

    def photo_count(self, name):
        d = os.path.join(config.DATASET_DIR, name)
        return len(os.listdir(d)) if os.path.isdir(d) else 0

    def users(self):
        names = set(self.people) | set(self._dataset_people())
        return [dict(name=n, role=self.role(n), photos=self.photo_count(n),
                     **{k: self.people.get(n, {}).get(k, "") for k in DETAIL_FIELDS + ["Registered"]})
                for n in sorted(names, key=str.lower)]

    def save_person(self, name, details, role):
        entry = self.people.get(name, {})
        entry.update({k: v for k, v in details.items() if k in DETAIL_FIELDS})
        entry["Role"] = role
        entry.setdefault("Registered", datetime.date.today().isoformat())
        self.people[name] = entry
        self._save_people()

    def set_role(self, name, role):
        self.people.setdefault(name, {})["Role"] = role
        self._save_people()

    def admins(self):
        return [u["name"] for u in self.users() if u["role"] == "Admin" and u["photos"]]

    def delete_person(self, name):
        self.people.pop(name, None)
        self._save_people()
        d = os.path.join(config.DATASET_DIR, name)
        if os.path.isdir(d):
            shutil.rmtree(d)
        self.train_in_background()

    # ---- training (embeddings)
    def _dataset_people(self):
        if not os.path.isdir(config.DATASET_DIR):
            return []
        return sorted(n for n in os.listdir(config.DATASET_DIR)
                      if os.path.isdir(os.path.join(config.DATASET_DIR, n))
                      and os.listdir(os.path.join(config.DATASET_DIR, n)))

    def _out_of_date(self):
        people = self._dataset_people()
        if not people:
            return False
        if not os.path.exists(config.EMBEDDINGS_FILE):
            return True
        with np.load(config.EMBEDDINGS_FILE) as d:
            if set(d["names"].tolist()) != set(people):
                return True
        t = os.path.getmtime(config.EMBEDDINGS_FILE)
        for n in people:
            folder = os.path.join(config.DATASET_DIR, n)
            if any(os.path.getmtime(os.path.join(folder, f)) > t for f in os.listdir(folder)):
                return True
        return False

    def _load_embeddings(self):
        if os.path.exists(config.EMBEDDINGS_FILE):
            with np.load(config.EMBEDDINGS_FILE) as d:
                self.names, self.feats = d["names"], d["feats"]

    def train(self):
        """Face 'fingerprint' for every saved photo -> face_embeddings.npz."""
        self.training = True
        try:
            rec = cv2.FaceRecognizerSF.create(config.RECOGNIZER_MODEL, "")  # own instance (thread)
            names, feats = [], []
            for name in self._dataset_people():
                folder = os.path.join(config.DATASET_DIR, name)
                for f in sorted(os.listdir(folder)):
                    img = _load_image(os.path.join(folder, f))
                    if img is None or img.shape[:2] != (112, 112):
                        continue
                    v = rec.feature(img).flatten()
                    feats.append(v / (np.linalg.norm(v) + 1e-9))
                    names.append(name)
            if feats:
                np.savez(config.EMBEDDINGS_FILE, names=np.array(names),
                         feats=np.array(feats, np.float32))
            elif os.path.exists(config.EMBEDDINGS_FILE):
                os.remove(config.EMBEDDINGS_FILE)
            self.names = np.array(names)
            self.feats = np.array(feats, np.float32).reshape(-1, 128)
            self.log(f"Face model trained: {len(feats)} photos, {len(set(names))} people")
        finally:
            self.training = False

    def train_in_background(self, done=None):
        def work():
            self.train()
            if done:
                done()
        threading.Thread(target=work, daemon=True).start()

    # ---- recognition
    def detect(self, frame):
        h, w = frame.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame)
        return [] if faces is None else list(faces)

    def feature(self, frame, face):
        v = self.recognizer.feature(self.recognizer.alignCrop(frame, face)).flatten()
        return v / (np.linalg.norm(v) + 1e-9)

    def identify(self, feat, exclude=None):
        """(name or None, similarity, best name). Uses each person's best 5 photos."""
        names, feats = self.names, self.feats
        if exclude is not None and len(names):
            keep = names != exclude
            names, feats = names[keep], feats[keep]
        if not len(names):
            return None, 0.0, None
        sims = feats @ feat
        scores = sorted(((float(np.sort(sims[names == p])[::-1][:5].mean()), p)
                         for p in set(names.tolist())), reverse=True)
        best_sim, best = scores[0]
        second = scores[1][0] if len(scores) > 1 else -1.0
        ok = best_sim >= self.cfg["match_threshold"] and best_sim - second >= self.cfg["match_margin"]
        return (best if ok else None), best_sim, best

    def percent(self, sim):
        th = self.cfg["match_threshold"]
        return int(max(0, min(100, 50 + (sim - th) / (0.90 - th) * 50)))


# ----------------------------------------------------------------- enrolment ---
class Enroller:
    """Takes the photos for a new face ID, one call of feed(frame) per camera frame."""

    def __init__(self, engine, name, count):
        self.engine, self.name, self.count = engine, name, count
        self.crops, self.frame_no = [], 0
        self.message, self.error = "", ""
        self.dup = None
        self.done = False

    def feed(self, frame):
        """Returns the frame with guide drawings; updates .message / .done / .error."""
        view = frame.copy()
        self.frame_no += 1
        faces = self.engine.detect(frame)
        n = len(self.crops)
        self.message = SCAN_POSES[min(len(SCAN_POSES) - 1, n * len(SCAN_POSES) // self.count)]
        if len(faces) == 1:
            x, y, w, h = map(int, faces[0][:4])
            big = w >= 90
            cv2.rectangle(view, (x, y), (x + w, y + h), (0, 220, 0) if big else (0, 200, 255), 2)
            if not big:
                self.message = "Come closer to the camera"
            elif self.frame_no % 4 == 0:
                crop = self.engine.recognizer.alignCrop(frame, faces[0])
                if n == 0:
                    # the same face must not already belong to someone else
                    v = self.engine.recognizer.feature(crop).flatten()
                    v = v / (np.linalg.norm(v) + 1e-9)
                    other, sim, _ = self.engine.identify(v, exclude=self.name)
                    if other:
                        self.dup = (other, self.engine.percent(sim))     # for translated messages
                        self.error = (f"This face is already registered as '{other}' "
                                      f"({self.engine.percent(sim)}%). Not added.")
                        self.done = True
                        return view
                self.crops.append(crop)
        elif len(faces) > 1:
            self.message = "Only one face in the camera, please"
        else:
            self.message = "No face found - look at the camera"
        if len(self.crops) >= self.count:
            self.done = True
        return view

    def save(self):
        """Write the photos (replacing old ones of this person)."""
        d = os.path.join(config.DATASET_DIR, self.name)
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
        for i, c in enumerate(self.crops):
            _save_image(os.path.join(d, f"{i + 1:04d}.jpg"), c)
