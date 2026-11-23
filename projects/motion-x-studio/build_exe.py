"""Build the Motion-X package: a folder with Motion-X.exe that runs on any Windows PC
(no Python needed), plus a zip of it.

    py -3.12 -m pip install pyinstaller      (once)
    py -3.12 build_exe.py

Result:
    dist\\Motion-X\\Motion-X.exe   + all data next to it
    dist\\Motion-X_1.0.zip
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
ROBOT = os.path.join(PROJ, "Robot+3DCamera")
DIST = os.path.join(HERE, "dist")
APP = os.path.join(DIST, "Motion-X")
VERSION = "2.1"


def make_icon():
    sys.path.insert(0, HERE)
    from studio import logo_image          # same mark as in the app
    ico = os.path.join(HERE, "build", "motionx.ico")
    os.makedirs(os.path.dirname(ico), exist_ok=True)
    logo_image(256).save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ico


def build(ico):
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "Motion-X", "--icon", ico,
        "--paths", ROBOT, "--paths", HERE,
        "--hidden-import", "d455_pick_place", "--hidden-import", "plc_cnet",
        "--hidden-import", "serial.tools.list_ports",
        "--collect-all", "pyrealsense2",
        "--exclude-module", "matplotlib", "--exclude-module", "pandas", "--exclude-module", "scipy",
        "--distpath", DIST, "--workpath", os.path.join(HERE, "build"), "--specpath", os.path.join(HERE, "build"),
        os.path.join(HERE, "studio.py")], cwd=HERE)


def copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    print("  +", os.path.relpath(dst, APP))


def add_data():
    """Everything Motion-X reads and saves lives next to the exe (see config.FROZEN)."""
    for f in ("face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx",
              "people.json", "face_embeddings.npz"):
        copy(os.path.join(PROJ, f), os.path.join(APP, f))
    for person in os.listdir(os.path.join(PROJ, "dataset")):             # registered face IDs
        src = os.path.join(PROJ, "dataset", person)
        if os.path.isdir(src) and os.listdir(src):
            copy(src, os.path.join(APP, "dataset", person))
    for f in ("mirobot.json", "mirobot.b64.txt", "mirobot_LICENSE.txt"):
        copy(os.path.join(PROJ, "sim3d", f), os.path.join(APP, "sim3d", f))
    copy(os.path.join(ROBOT, "d455_calib.json"), os.path.join(APP, "robot", "d455_calib.json"))
    for f in ("sim_mesh_cache.npz", "studio_config.json", "studio_learning.json", "README.md"):
        if os.path.exists(os.path.join(HERE, f)):
            copy(os.path.join(HERE, f), os.path.join(APP, f))
    with open(os.path.join(APP, "START HERE.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"""Motion-X {VERSION}

1. Double-click  Motion-X.exe
2. Look at the laptop camera to log in (registered face IDs: see README.md).
   Wrong camera? Press "switch camera" on the login screen.
3. Connect the robot (USB), the D455 camera (USB 3) and the USB-RS485 adapter (PLC).
   COM numbers are found automatically.

No Python or other installation is needed.
Drivers: Windows normally installs the robot (CH340) and RS-485 (CH9101) USB drivers
by itself. If a device does not show up, install the WCH CH340 / CH9101 driver once.

New computer or camera moved: log in as Admin -> Calibration -> Run auto calibration.
Check everything: run  Motion-X.exe --selftest  and read selftest.txt

Your data is in this folder (keep it when updating):
  dataset\\, people.json, face_embeddings.npz   face IDs
  robot\\d455_calib.json                         camera-to-robot calibration
  studio_config.json, studio_learning.json      settings, learned pick heights
  access_log.csv, studio_log.txt                logs
""")


def main():
    if os.path.isdir(APP):
        shutil.rmtree(APP)
    build(make_icon())
    print("Adding data:")
    add_data()
    z = shutil.make_archive(os.path.join(DIST, f"Motion-X_{VERSION}"), "zip", DIST, "Motion-X")
    print("\nDONE:", os.path.join(APP, "Motion-X.exe"))
    print("      ", z, f"({os.path.getsize(z) / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
