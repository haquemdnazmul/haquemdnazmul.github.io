"""Paths and settings shared by the studio parts.

Settings that people may want to change are kept in studio_config.json (created on
first start with the defaults below), so they can be edited without touching code.
"""
import json
import os
import sys

FROZEN = getattr(sys, "frozen", False)        # running as Motion-X.exe (PyInstaller)
if FROZEN:
    # exe: everything that is read AND saved lives next to Motion-X.exe
    #   Motion-X\Motion-X.exe, studio_config.json, logs, dataset\, people.json,
    #   face models, robot\d455_calib.json, sim3d\ ...
    STUDIO_DIR = PROJECT_DIR = os.path.dirname(sys.executable)
    ROBOT_DIR = os.path.join(PROJECT_DIR, "robot")
else:
    STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_DIR = os.path.dirname(STUDIO_DIR)
    ROBOT_DIR = os.path.join(PROJECT_DIR, "Robot+3DCamera")

# Face data is shared with face_scan.py (same folder, same file formats).
FACE_DIR = PROJECT_DIR
DATASET_DIR = "dataset"                     # relative to FACE_DIR (OpenCV + Korean paths)
PEOPLE_FILE = "people.json"
EMBEDDINGS_FILE = "face_embeddings.npz"
DETECTOR_MODEL = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = "face_recognition_sface_2021dec.onnx"

CONFIG_FILE = os.path.join(STUDIO_DIR, "studio_config.json")
LEARN_FILE = os.path.join(STUDIO_DIR, "studio_learning.json")
ACCESS_LOG = os.path.join(STUDIO_DIR, "access_log.csv")
STUDIO_LOG = os.path.join(STUDIO_DIR, "studio_log.txt")

DEFAULTS = {
    "face_camera_index": 0,        # laptop webcam (2 = D455 colour camera on this PC)
    "match_threshold": 0.42,       # SFace similarity needed to accept a face
    "match_margin": 0.05,          # best person must beat the 2nd best by this much
    "login_frames": 5,             # same person recognised this many times in a row = login
    "scan_photos": 20,             # photos taken when a new face ID is added
    "auto_lock_minutes": 10,       # back to face login after this long without use (0 = never)
    "first_admins": ["Nazmul", "Jiwoo"],   # made Admin if they have no role yet
    "use_plc": True,
    "return_press_mm": 4,          # Return block without load cell feedback: fixed press below drop-off pose
    "return_touch_g": 3,           # Return block: weight rise (g) that means "the cup touches the block"
    "return_start_mm": 8,          # Return block: start the touch search this far above the drop-off pose
    "return_max_press_mm": 10,     # Return block: never go deeper than this below the drop-off pose
    "return_seal_mm": 3,           # Return block: press this far after touching, so the suction cup seals
    "return_drop_mm": 5,           # Return block: set the block down this far above where it was picked
    # Pick height for EVERY block from the height the camera measures (blocks differ in size):
    #   lowest cup point Z = plate_z + scale * measured height
    # Fitted 2026-11-20 to the heights taught in WLKATA Studio (111.qnd: 2-block stack Z73.8,
    # 3-block stack Z105.0) and the camera's measured stack heights (~59 / ~88 mm): the camera
    # reads heights ~5 % low. A small per-layer correction is learned on top (both ways).
    "pick_model": {"plate_z": 12.0, "scale": 1.05},
}


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (OSError, ValueError):
            pass
    else:
        save_config(cfg)
    return cfg


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def add_robot_path():
    """Make the robot programs (d455_pick_place, plc_cnet) importable.
    (In the exe they are bundled inside; only their data lives in ROBOT_DIR.)"""
    if not FROZEN and ROBOT_DIR not in sys.path:
        sys.path.insert(0, ROBOT_DIR)
