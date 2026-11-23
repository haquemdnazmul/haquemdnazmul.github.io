"""
Face scan + face recognition with your laptop camera, with person details.
Uses OpenCV's deep-learning models: YuNet (find faces) + SFace (recognize faces).

Install once:
    pip install "opencv-contrib-python<5" numpy pillow

Model files (put next to this script), from https://github.com/opencv/opencv_zoo :
    face_detection_yunet_2023mar.onnx
    face_recognition_sface_2021dec.onnx

Run with no arguments (e.g. VS Code Run button) for a menu, or:
    python face_scan.py register --name Alice   # details + face scan (auto-trains)
    python face_scan.py train                   # rebuild face data
    python face_scan.py recognize               # live recognition with details
    python face_scan.py list                    # show registered people
    python face_scan.py edit --name Alice       # change someone's details

To quit the camera: press Q, ESC or Enter in the terminal or camera window.
"""

import argparse
import datetime
import json
import os
import sys

import cv2
import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # still works without Pillow, but only English text on screen
    Image = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Work from the script folder and use relative paths: OpenCV cannot open
# file paths with non-English characters (e.g. Korean user names) on Windows.
os.chdir(BASE_DIR)

DATASET_DIR = "dataset"
EMBEDDINGS_FILE = "face_embeddings.npz"
PEOPLE_FILE = "people.json"  # name -> details
DETECTOR_MODEL = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = "face_recognition_sface_2021dec.onnx"
LOG_FILE = "face_scan_log.txt"
FONT_FILE = r"C:\Windows\Fonts\malgun.ttf"  # Korean-capable font
CAMERA_INDEX = 0
SCAN_COUNT = 20          # photos per person
DETECT_SCORE = 0.85      # how sure the detector must be that it is a face

# ---- Matching settings -------------------------------------------------------
# SFace cosine similarity: same person is usually 0.5 - 0.8, different people < 0.3.
# OpenCV's recommended cut-off is 0.363. Higher = stricter (fewer strangers
# accepted, but known people may show Unknown more often).
MATCH_THRESHOLD = 0.42
# Similarity that is shown as 100% on screen (the threshold is shown as 50%).
FULL_MATCH = 0.90
# The best person must beat the second-best by this much, otherwise Unknown.
MIN_MARGIN = 0.05

# Details asked for at registration. Add or remove fields here if you like.
DETAIL_FIELDS = ["ID", "Age", "Department", "Phone", "Notes"]


# ---------------------------------------------------------------- logging
class _Tee:
    """Copy everything printed into face_scan_log.txt for troubleshooting."""

    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        self.stream.write(text)
        self.log.write(text)
        self.log.flush()

    def flush(self):
        self.stream.flush()


def _start_log():
    import traceback
    log = open(LOG_FILE, "w", encoding="utf-8")
    log.write(f"started {datetime.datetime.now()}\npython {sys.executable} {sys.version}\n"
              f"opencv {cv2.__version__}\nargs {sys.argv}\nstdin is terminal: "
              f"{sys.stdin.isatty() if sys.stdin else None}\n\n")
    sys.stdout = _Tee(sys.stdout, log)
    sys.stderr = _Tee(sys.stderr, log)
    sys.excepthook = lambda t, e, tb: traceback.print_exception(t, e, tb)


_start_log()


# ---------------------------------------------------------------- people details
def load_people():
    if os.path.exists(PEOPLE_FILE):
        with open(PEOPLE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_people(people):
    with open(PEOPLE_FILE, "w", encoding="utf-8") as fh:
        json.dump(people, fh, ensure_ascii=False, indent=2)


def ask_details(old=None):
    """Ask for each detail in the terminal. Enter keeps the old value / skips."""
    old = old or {}
    details = {}
    print("Enter details (press Enter to skip" + (" / keep current" if old else "") + "):")
    for field in DETAIL_FIELDS:
        current = old.get(field, "")
        hint = f" [{current}]" if current else ""
        value = input(f"  {field}{hint}: ").strip()
        details[field] = value or current
    return details


def details_lines(details):
    return [f"{k}: {v}" for k, v in details.items() if v and k in DETAIL_FIELDS]


# ---------------------------------------------------------------- text drawing
_fonts = {}


def _font(size):
    if size not in _fonts:
        try:
            _fonts[size] = ImageFont.truetype(FONT_FILE, size)
        except OSError:
            _fonts[size] = ImageFont.load_default()
    return _fonts[size]


def draw_texts(frame, items):
    """items: list of (text, (x, y), size, (B, G, R), background or None).
    Uses Pillow so Korean text works; falls back to OpenCV (English only)."""
    if not items:
        return frame
    if Image is None:
        for text, (x, y), size, color, bg in items:
            scale = size / 30
            if bg is not None:
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
                cv2.rectangle(frame, (x - 3, y - 3), (x + tw + 3, y + th + 6), bg, -1)
            cv2.putText(frame, text, (x, y + int(size * 0.8)),
                        cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1)
        return frame
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img)
    for text, (x, y), size, color, bg in items:
        font = _font(size)
        if bg is not None:
            l, t, r, b = draw.textbbox((x, y), text, font=font)
            draw.rectangle((l - 4, t - 3, r + 4, b + 3), fill=(bg[2], bg[1], bg[0]))
        draw.text((x, y), text, font=font, fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------- models
def check_models():
    missing = [m for m in (DETECTOR_MODEL, RECOGNIZER_MODEL) if not os.path.exists(m)]
    if missing:
        sys.exit("Missing model file(s) next to the script: " + ", ".join(missing) +
                 "\nDownload them from https://github.com/opencv/opencv_zoo (models/"
                 "face_detection_yunet and models/face_recognition_sface).")


_detector = None
_recognizer = None


def get_detector(width, height):
    global _detector
    check_models()
    if _detector is None:
        _detector = cv2.FaceDetectorYN.create(DETECTOR_MODEL, "", (width, height),
                                              DETECT_SCORE, 0.3, 5000)
    _detector.setInputSize((width, height))
    return _detector


def get_recognizer():
    global _recognizer
    check_models()
    if _recognizer is None:
        _recognizer = cv2.FaceRecognizerSF.create(RECOGNIZER_MODEL, "")
    return _recognizer


def detect_faces(frame):
    """Returns YuNet face rows: x, y, w, h, 5 landmarks (10 values), score."""
    h, w = frame.shape[:2]
    _, faces = get_detector(w, h).detect(frame)
    return [] if faces is None else list(faces)


def face_feature(aligned):
    feat = get_recognizer().feature(aligned).flatten()
    return feat / (np.linalg.norm(feat) + 1e-9)


# ---------------------------------------------------------------- camera helpers
def open_camera():
    print("Opening camera...")
    for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
        cap = cv2.VideoCapture(CAMERA_INDEX, backend)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            for _ in range(10):  # some cameras return a few empty frames first
                ok, _frame = cap.read()
                if ok:
                    _terminal_quit()  # throw away keys typed before the camera started
                    print("Camera opened. Look for the camera window "
                          "(it may be behind VS Code).")
                    return cap
        cap.release()
    print("ERROR: Cannot open the camera. Close other apps using it (Zoom, Teams, "
          "Camera app) and check Windows Settings > Privacy > Camera.")
    return None


_shown = set()


def show(title, frame):
    cv2.imshow(title, frame)
    if title not in _shown:  # bring the camera window to the front once
        _shown.add(title)
        try:
            cv2.setWindowProperty(title, cv2.WND_PROP_TOPMOST, 1)
        except cv2.error:
            pass


def close_window(cap):
    cap.release()
    cv2.destroyAllWindows()
    cv2.waitKey(1)
    _shown.clear()


def save_image(path, img):
    # imencode + tofile works with any characters in the path / name.
    ok, buf = cv2.imencode(".jpg", img)
    if ok:
        buf.tofile(path)


def load_image(path):
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


# ---------------------------------------------------------------- quitting
QUIT_KEYS = {ord("q"), ord("Q"), 27, 13, 0x3142}  # q, Q, ESC, Enter, ㅂ (Korean Q)


def _terminal_quit():
    """Q / ESC / Enter typed in the terminal (e.g. VS Code) also quits."""
    try:
        import msvcrt
    except ImportError:
        return False
    if not (sys.stdin and sys.stdin.isatty()):
        return False
    hit = False
    while msvcrt.kbhit():
        ch = msvcrt.getwch()
        print(f"[terminal key: {ch!r}]")
        if ch in ("q", "Q", "\x1b", "\r", "\n", "ㅂ"):
            hit = True
    return hit


def quit_pressed(title):
    key = cv2.waitKeyEx(1)
    if key != -1:
        print(f"[window key: {key}]")
        if key in QUIT_KEYS or (key & 0xFF) in (ord("q"), ord("Q"), 27, 13):
            return True
    if _terminal_quit():
        return True
    try:  # the window's X button was clicked
        return cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


# ---------------------------------------------------------------- register
SCAN_POSES = ["Look straight at the camera", "Turn head slightly LEFT",
              "Turn head slightly RIGHT", "Tilt head slightly UP",
              "Tilt head slightly DOWN"]


def register(name, count=SCAN_COUNT, details=None):
    name = name.strip()
    if not name or any(c in name for c in '\\/:*?"<>|'):
        print('Invalid name (do not use \\ / : * ? " < > |).')
        return

    people = load_people()
    if details is None:
        if name in people:
            print(f"'{name}' already has details:")
            for line in details_lines(people[name]):
                print(f"    {line}")
            keep = input("Keep these details? [Y/n]: ").strip().lower()
            details = people[name] if keep in ("", "y", "yes") else ask_details(people[name])
        else:
            details = ask_details()
    entry = people.get(name, {})
    entry.update(details)
    entry.setdefault("Registered", datetime.date.today().isoformat())
    people[name] = entry
    save_people(people)
    print(f"Details saved for '{name}'.")

    check_models()
    person_dir = os.path.join(DATASET_DIR, name)
    os.makedirs(person_dir, exist_ok=True)
    # A re-scan replaces the old photos of this person.
    for f in os.listdir(person_dir):
        os.remove(os.path.join(person_dir, f))

    cap = open_camera()
    if cap is None:
        return
    title = "Face Scan - Register"
    saved, frame_no = 0, 0
    print(f"Scanning '{name}'. Follow the instructions in the camera window. "
          f"Q / ESC / Enter to stop.")

    while saved < count:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        faces = detect_faces(frame)
        frame_no += 1
        view = frame.copy()
        pose = SCAN_POSES[min(len(SCAN_POSES) - 1, saved * len(SCAN_POSES) // count)]
        texts = [(pose, (10, 40), 22, (255, 255, 255), (150, 90, 0))]

        if len(faces) == 1:
            x, y, w, h = map(int, faces[0][:4])
            big_enough = w >= 90
            color = (0, 255, 0) if big_enough else (0, 200, 255)
            cv2.rectangle(view, (x, y), (x + w, y + h), color, 2)
            if not big_enough:
                texts.append(("Come closer to the camera", (10, 75), 20,
                              (255, 255, 255), (0, 120, 220)))
            elif frame_no % 4 == 0:  # skip frames so photos differ a bit
                aligned = get_recognizer().alignCrop(frame, faces[0])
                save_image(os.path.join(person_dir, f"{saved + 1:04d}.jpg"), aligned)
                saved += 1
        elif len(faces) > 1:
            texts.append(("Only one face please", (10, 75), 20, (255, 255, 255), (0, 0, 200)))
        else:
            texts.append(("No face found", (10, 75), 20, (255, 255, 255), (0, 0, 200)))

        # progress bar
        cv2.rectangle(view, (10, 10), (10 + int(300 * saved / count), 28), (0, 255, 0), -1)
        cv2.rectangle(view, (10, 10), (310, 28), (255, 255, 255), 1)
        texts.append((f"{name}  {saved}/{count}", (320, 7), 20, (255, 255, 255), None))
        view = draw_texts(view, texts)
        show(title, view)
        if quit_pressed(title):
            break

    close_window(cap)
    print(f"Saved {saved} face photos to {person_dir}")
    if saved:
        print("Training with the new face...")
        train()


# ---------------------------------------------------------------- edit details
def edit(name):
    people = load_people()
    if name not in people and not os.path.isdir(os.path.join(DATASET_DIR, name)):
        print(f"'{name}' is not registered.")
        return
    entry = people.get(name, {})
    entry.update(ask_details(entry))
    entry.setdefault("Registered", datetime.date.today().isoformat())
    people[name] = entry
    save_people(people)
    print(f"Details updated for '{name}'.")


# ---------------------------------------------------------------- train
def dataset_people():
    if not os.path.isdir(DATASET_DIR):
        return []
    return sorted(d for d in os.listdir(DATASET_DIR)
                  if os.path.isdir(os.path.join(DATASET_DIR, d))
                  and os.listdir(os.path.join(DATASET_DIR, d)))


def train():
    """Compute a face 'fingerprint' (embedding) for every saved photo."""
    check_models()
    names, feats = [], []
    for name in dataset_people():
        folder = os.path.join(DATASET_DIR, name)
        n = 0
        for f in sorted(os.listdir(folder)):
            img = load_image(os.path.join(folder, f))
            if img is None:
                continue
            if img.shape[:2] != (112, 112):  # not an aligned SFace crop
                continue
            feats.append(face_feature(img))
            names.append(name)
            n += 1
        print(f"  {name}: {n} photos")
    if not feats:
        sys.exit("No face photos found. Register someone first (menu 1).")
    np.savez(EMBEDDINGS_FILE, names=np.array(names), feats=np.array(feats, dtype=np.float32))
    print(f"Trained on {len(feats)} photos of {len(set(names))} people -> {EMBEDDINGS_FILE}")


def model_out_of_date():
    """True if people were added/removed/rescanned since the last training."""
    people = dataset_people()
    if not people:
        return False
    if not os.path.exists(EMBEDDINGS_FILE):
        return True
    with np.load(EMBEDDINGS_FILE) as data:
        if set(data["names"].tolist()) != set(people):
            return True
    t = os.path.getmtime(EMBEDDINGS_FILE)
    for name in people:
        folder = os.path.join(DATASET_DIR, name)
        if os.path.getmtime(folder) > t or any(
                os.path.getmtime(os.path.join(folder, f)) > t for f in os.listdir(folder)):
            return True
    return False


# ---------------------------------------------------------------- recognize
def match(feat, names, feats):
    """Return (name or None, similarity) using each person's best 5 photos."""
    sims = feats @ feat
    scores = {}
    for person in set(names.tolist()):
        s = np.sort(sims[names == person])[::-1][:5]
        scores[person] = float(s.mean())
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best, best_sim = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else -1.0
    if best_sim >= MATCH_THRESHOLD and best_sim - second >= MIN_MARGIN:
        return best, best_sim
    return None, best_sim


def match_percent(sim):
    """Threshold -> 50%, FULL_MATCH -> 100%."""
    pct = 50 + (sim - MATCH_THRESHOLD) / (FULL_MATCH - MATCH_THRESHOLD) * 50
    return int(max(0, min(100, pct)))


def recognize():
    check_models()
    if model_out_of_date():
        print("Face data changed since the last training - training now...")
        train()
    if not os.path.exists(EMBEDDINGS_FILE):
        sys.exit("No face data yet. Register someone first (menu 1).")
    with np.load(EMBEDDINGS_FILE) as data:
        names, feats = data["names"], data["feats"]
    people = load_people()
    recognizer = get_recognizer()

    cap = open_camera()
    if cap is None:
        return
    title = "Face Recognition"
    print("Recognizing... To quit: press Q, ESC or Enter here in the terminal "
          "(or in the camera window, or click its X button).")
    last_seen = None

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        view = frame.copy()
        texts = []

        for face in detect_faces(frame):
            x, y, w, h = map(int, face[:4])
            feat = face_feature(recognizer.alignCrop(frame, face))
            name, sim = match(feat, names, feats)
            if name:
                pct = match_percent(sim)
                color = (0, 170, 0)
                label = f"{name}  {pct}%"
                lines = details_lines(people.get(name, {}))
                if name != last_seen:  # print details once when someone appears
                    last_seen = name
                    print(f"Recognized: {name} ({pct}%, similarity {sim:.2f})  " +
                          "  ".join(lines))
            else:
                color, label, lines = (0, 0, 220), "Unknown", []
                if last_seen != "Unknown":
                    last_seen = "Unknown"
                    print(f"Unknown face (best similarity {sim:.2f})")

            cv2.rectangle(view, (x, y), (x + w, y + h), color, 2)
            texts.append((label, (x, max(0, y - 30)), 22, (255, 255, 255), color))
            for i, line in enumerate(lines):  # details under the face box
                texts.append((line, (x, y + h + 6 + i * 22), 17, (255, 255, 255), (40, 40, 40)))

        texts.append(("Quit: Q / ESC / Enter", (10, view.shape[0] - 26), 16,
                      (255, 255, 255), (40, 40, 40)))
        view = draw_texts(view, texts)
        show(title, view)
        if quit_pressed(title):
            break

    close_window(cap)


# ---------------------------------------------------------------- list
def list_people():
    people = load_people()
    names = set(people) | set(dataset_people())
    if not names:
        print("Nobody registered yet.")
        return
    for name in sorted(names):
        folder = os.path.join(DATASET_DIR, name)
        n = len(os.listdir(folder)) if os.path.isdir(folder) else 0
        note = "" if n else "  <- no face scan yet, use menu 1 to scan"
        print(f"- {name}  ({n} face photos){note}")
        for line in details_lines(people.get(name, {})):
            print(f"    {line}")
        if people.get(name, {}).get("Registered"):
            print(f"    Registered: {people[name]['Registered']}")


# ---------------------------------------------------------------- menu / main
def menu():
    """Shown when the script is started with no command (e.g. VS Code Run button)."""
    while True:
        print("\n=== Face Scan ===")
        print("1. Register / re-scan (name + details + face scan)")
        print("2. Train (normally automatic)")
        print("3. Recognize (live camera)")
        print("4. List registered people")
        print("5. Edit a person's details")
        print("0. Exit")
        choice = input("Choose: ").strip()
        print(f"[typed: {choice!r}]")
        try:
            if choice == "1":
                name = input("Name: ").strip()
                if name:
                    register(name)
            elif choice == "2":
                train()
            elif choice == "3":
                recognize()
            elif choice == "4":
                list_people()
            elif choice == "5":
                list_people()
                name = input("Name to edit: ").strip()
                if name:
                    edit(name)
            elif choice == "0":
                break
        except SystemExit as e:  # show the message and go back to the menu
            print(f"\n>>> {e}")
        except Exception:  # log any crash, then go back to the menu
            import traceback
            traceback.print_exc()


def main():
    if len(sys.argv) == 1:
        menu()
        return
    p = argparse.ArgumentParser(description="Laptop camera face scan & recognition")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register", help="enter details and scan a face")
    r.add_argument("--name", required=True, help="person's name")
    r.add_argument("--count", type=int, default=SCAN_COUNT, help="number of photos to take")
    sub.add_parser("train", help="rebuild face data from scanned photos")
    sub.add_parser("recognize", help="live face recognition")
    sub.add_parser("list", help="list registered people and details")
    e = sub.add_parser("edit", help="edit a person's details")
    e.add_argument("--name", required=True)
    args = p.parse_args()

    if args.cmd == "register":
        register(args.name, args.count)
    elif args.cmd == "train":
        train()
    elif args.cmd == "recognize":
        recognize()
    elif args.cmd == "edit":
        edit(args.name)
    else:
        list_people()


if __name__ == "__main__":
    main()
