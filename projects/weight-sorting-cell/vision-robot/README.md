# Robot + 3D Camera + PLC load cell (WLKATA Mirobot + Intel RealSense D455 + LS XGB)

The D455 finds blue blocks on the work plate. When the PLC load cell (`D00400`) is
**empty**, the Mirobot picks a block at the position the camera gives and puts it on the
load cell. It waits until the load cell shows the block's weight, and picks the next
block only after the load cell is empty again.

## Folder

| File | What it is |
|---|---|
| `d455_pick_place.py` | **Main program** - camera detection, calibration, PLC check, pick & place |
| `plc_cnet.py` | Reads the load cell weight (`D00400`) from the PLC over RS-485 (XGT Cnet). Also a test tool |
| `load_cell_pick_test.py` | Test without camera: pick at the taught pick pose, place on the load cell |
| `d455_calib.json` | Saved camera-to-robot calibration (keep it next to the script) |
| `run_log.txt` | Everything the main program printed, every run (for checking problems afterwards) |
| `requirements.txt` | Python packages |
| `tools/camera_check.py` | Checks the D455: connection, USB speed, depth, color, IMU |
| `tools/blue_blocks_viewer.py` | Live view of blue blocks with size and position (no robot) |
| `tools/height_check.py` | Measures each blue block / pile height (no robot) |
| `.vscode/` | Run buttons for VS Code |

## Setup (once)

- Python **3.12 64-bit** (pyrealsense2 does not support 3.14 yet)
- `py -3.12 -m pip install -r requirements.txt`
- Robot (CH340, USB ID 1A86:7523) and USB-RS485 adapter (CH9101, 1A86:55D8) are found
  automatically by their USB ID, whatever COM number Windows gives them (`PORT` / `PLC_PORT`
  are only fallbacks). Close WLKATA Studio before running (only one program can use a port).
- Camera fixed above the work plate, about 45-65 cm up, looking down.

## Run

VS Code: open **this folder** (File > Open Folder > `Robot+3DCamera`), go to Run and Debug,
choose **FULL SYSTEM - Camera + PLC load cell + Robot**, press F5.

| Run button | What it does |
|---|---|
| FULL SYSTEM - Camera + PLC load cell + Robot | Normal use |
| Load cell test (no camera, taught pick spot) | Robot + PLC only |
| Pick & Place - camera only (no PLC) | Picks without waiting for the load cell |
| Recalibrate (camera moved) | Automatic camera calibration |
| Dry run (no robot) | Camera + PLC, robot commands only printed |

Terminal (in this folder):

    py -3.12 d455_pick_place.py auto           # normal use
    py -3.12 d455_pick_place.py auto --no-plc  # without the PLC
    py -3.12 d455_pick_place.py autocal        # recalibrate after the camera moved
    py -3.12 d455_pick_place.py run --dry      # no robot, only prints commands
    py -3.12 plc_cnet.py                       # show the load cell weight live
    py -3.12 plc_cnet.py scan                  # find PLC port / baud / station
    py -3.12 load_cell_pick_test.py --once     # one pick/place without camera

Keys in the camera window: `q` stop (pump off, robot parks), `c` pick all again,
`a` auto on/off, `g` pick selected, `n` next block, `[` pick 2 mm lower, `]` pick 2 mm higher.

Bottom line of the camera window: number of blocks, load cell weight (`EMPTY` when empty),
pick height offset (`Z-25`). Top left: `READY` or why it waits.

## Settings

Top of `d455_pick_place.py`:

| Setting | Value | Meaning |
|---|---|---|
| `PORT` | `"COM4"` | Robot serial port |
| `PLACE_JOINTS` | `(-70, 37, 15, 0, -50, 0)` | Drop-off pose over the load cell (J1-J6), from WLKATA Studio |
| `TIP_VISIBLE_OFFSET` | `-25` | Pick height correction in mm (more negative = lower) |
| `USE_PLC` | `True` | Wait for an empty load cell before picking |
| `EMPTY_STABLE_SEC` | `1.0` | Load cell must be empty this long before a pick |
| `LOAD_WAIT_SEC` | `10.0` | After a place, the weight must appear within this time |
| `AUTO_LOWER_MM` / `AUTO_LOWER_MAX` | `3` / `15` | No weight after a place -> next pick 3 mm lower (max 15 mm) |
| `TAUGHT_PICK_JOINTS` | `(55, 40, 10, 0, -35, -45)` | Height reference used by calibration |
| `BLUE_LO` / `BLUE_HI` | HSV range | Block colour to detect |
| `DISPARITY_SHIFT` | `50` | Close-range depth mode (needed for stacked blocks); `0` = normal |

Top of `plc_cnet.py`:

| Setting | Value | Meaning |
|---|---|---|
| `PLC_PORT` | `"COM5"` | USB-RS485 adapter |
| `PLC_BAUD` / `PLC_STATION` | `9600` / `0` | PLC built-in Cnet (found with `scan`) |
| `WEIGHT_DEVICE` | `"D00400"` | Load cell weight in grams (D00400 + D00401 = 32-bit) |
| `EMPTY_BELOW` | `5` | Less than 5 g = empty |

## How it handles problems

- **Robot cannot reach a block** (too close to the base, `Soft limit` error): the pick is
  cancelled, the block is marked red `CAN'T REACH` and skipped. `c` tries all blocks again.
- **No weight after a place** (block not lifted / dropped): warning in the log, next pick 3 mm lower.
- **USB-RS485 adapter drops out** (`WriteFile failed, PermissionError 13`): COM5 is reopened
  automatically within about 1 s; the robot waits meanwhile.
- **Plate height** comes from the calibration (not from the camera), so blocks covering the
  plate do not confuse the height measurement. Run `autocal` again whenever the camera moves.

## PLC side

- XG5000: built-in Cnet channel 2 (RS-485) = **XGT server**, 9600 baud, 8N1, station 0.
- The ladder must keep the load cell weight (grams) in `D00400`.
- Wiring: adapter A(+) -> PLC 485+, B(-) -> PLC 485-, **GND -> SG** (reduces adapter dropouts).
  Keep the RS-485 / USB cables away from the robot motor and pump cables.
- The HMI uses the PLC's Ethernet port (192.168.1.2), not RS-485 - no conflict with this program.

## Calibration

Automatic, no clicking. **Remove all blocks from the plate first** (the program checks).
The robot moves the suction tool to 36 points over the plate at three heights (150, 105,
65 mm), the camera finds the white cap on the orange arm end, and `solvePnPRansac`
computes where the camera is (wrong detections are ignored). The height is anchored to
the taught pick pose. Run `autocal` again whenever the camera is moved. If
`d455_calib.json` is missing, `auto` calibrates by itself first.
