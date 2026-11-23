"""Quick health check for an Intel RealSense D455."""
import time
import pyrealsense2 as rs

ctx = rs.context()
devs = ctx.query_devices()
if len(devs) == 0:
    raise SystemExit("No RealSense device found.")

dev = devs[0]
info = lambda k: dev.get_info(k) if dev.supports(k) else "n/a"
print("Name      :", info(rs.camera_info.name))
print("Serial    :", info(rs.camera_info.serial_number))
print("Firmware  :", info(rs.camera_info.firmware_version))
print("USB type  :", info(rs.camera_info.usb_type_descriptor))
print("Sensors   :", [s.get_info(rs.camera_info.name) for s in dev.query_sensors()])

usb2 = str(info(rs.camera_info.usb_type_descriptor)).startswith("2")


def try_stream(label, configure):
    pipe = rs.pipeline()
    cfg = rs.config()
    cfg.enable_device(info(rs.camera_info.serial_number))
    configure(cfg)
    try:
        pipe.start(cfg)
    except RuntimeError as e:
        print(f"[FAIL] {label}: {e}")
        return
    try:
        for _ in range(15):  # let auto-exposure settle
            pipe.wait_for_frames(5000)
        t0, n = time.time(), 0
        while time.time() - t0 < 3:
            frames = pipe.wait_for_frames(5000)
            n += 1
        msg = f"[ OK ] {label}: ~{n / 3:.1f} fps"
        depth = frames.get_depth_frame()
        if depth:
            w, h = depth.get_width(), depth.get_height()
            msg += f", center distance = {depth.get_distance(w // 2, h // 2):.3f} m"
        color = frames.get_color_frame()
        if color:
            msg += f", color {color.get_width()}x{color.get_height()}"
        print(msg)
    except RuntimeError as e:
        print(f"[FAIL] {label}: {e}")
    finally:
        try:
            pipe.stop()
        except RuntimeError:
            pass


print()
if usb2:
    print("Connected at USB 2 -> testing with low-bandwidth modes")
    try_stream("Depth 640x480@15", lambda c: c.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 15))
    try_stream("Color 640x480@15", lambda c: c.enable_stream(rs.stream.color, 640, 480, rs.format.rgb8, 15))
    try_stream("Depth+Color 480x270@15", lambda c: (
        c.enable_stream(rs.stream.depth, 480, 270, rs.format.z16, 15),
        c.enable_stream(rs.stream.color, 424, 240, rs.format.rgb8, 15)))
else:
    try_stream("Depth 848x480@30", lambda c: c.enable_stream(rs.stream.depth, 848, 480, rs.format.z16, 30))
    try_stream("Color 1280x720@30", lambda c: c.enable_stream(rs.stream.color, 1280, 720, rs.format.rgb8, 30))
    try_stream("Depth+Color 848x480@30", lambda c: (
        c.enable_stream(rs.stream.depth, 848, 480, rs.format.z16, 30),
        c.enable_stream(rs.stream.color, 848, 480, rs.format.rgb8, 30)))

try_stream("IMU (accel+gyro)", lambda c: (
    c.enable_stream(rs.stream.accel), c.enable_stream(rs.stream.gyro)))
