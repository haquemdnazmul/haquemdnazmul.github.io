# Motion-X

> Part of the [Weight Sorting Cell](../weight-sorting-cell/) project. This copy is for reading: the
> paths below refer to the original project folder, and face photos and logs are not included.

Vision · weighing · robotics studio for the weight-sorting machine:
D455 camera + PLC load cell (RS-485) + WLKATA Mirobot, with face login,
English / Korean, and a live 3D robot simulator.

## Start

VS Code: **File > Open Folder > `Studio`**, Run and Debug, choose **MOTION-X**, press F5.

Terminal (in this folder):

    py -3.12 studio.py            # normal
    py -3.12 studio.py --dry      # simulator only - the real robot does not move
    py -3.12 studio.py --no-plc   # without the load cell

Close WLKATA Studio first. The robot and the USB-RS485 adapter are found by their USB
chip, so the COM numbers do not matter.

## Screens

| Screen | What it shows |
|---|---|
| Face login | Laptop webcam. A registered person is logged in after 5 matching frames |
| Dashboard | D455 vision camera · **3D robot simulator** · machine state · load cell weight · session counts · last weights · START / STOP / AUTO / Pick now / Next block / Retry skipped |
| Learning | Pick height learned per stack layer |
| Calibration (Admin) | One-click automatic camera-to-robot calibration |
| Users (Admin) | Add / re-scan / delete face IDs, Admin / Operator roles |
| Log | Machine log and access log |

Header: machine state, user, **English / 한국어** button (remembered), **Lock**.
Status bar: robot, camera, PLC and face model lights, clock.

## Return block

**↩ Return block** (Dashboard) takes the block that is on the load cell and puts it back on
the plate exactly where the robot picked it:

1. Auto mode switches off (so the returned block is not picked again by itself).
2. **Finds the block by touch:** the robot starts `return_start_mm` (8 mm) above the drop-off pose
   and comes down 1 mm at a time while the PLC weight is watched. When the weight rises by
   `return_touch_g` (3 g) on two readings in a row, the cup is on the block: suction on, then it
   presses `return_seal_mm` (3 mm) more so the cup seals (like a normal pick), and lifts.
   It never goes deeper than `return_max_press_mm` (10 mm). (Dry run / no PLC: fixed
   `return_press_mm` press.)
3. The PLC must show that the weight left the load cell - otherwise the robot stops safely
   (pump off, parks).
4. **Sets it down at pick height + 5 mm:** the reference is the lowest cup point of its pick
   (for 2- and 3-block stacks: the taught height, see below) plus `return_drop_mm` (5 mm).
   The camera checks the spot right after the pick and again before returning; only a real
   change (a block added or removed, 8 mm or more) moves the height. Then the robot parks.

## Pick height (every block measured)

Blocks have different sizes, so each block is picked at its own height:

    lowest cup point Z = plate_z + scale x (height the camera measures)      = 12.0 + 1.05 x h

`pick_model` in `studio_config.json`. Fitted to the heights taught in WLKATA Studio
(`111.qnd`: 2-block stack Z73.8, 3-block stack Z105.0 -> the rule gives Z74.0 / Z104.4); the
camera reads heights about 5 % low. Checked on the real robot 2026-11-20: a flat block (camera
24 mm) that the fixed single-block height Z54.9 (`112.qnd`, taught with a taller block) missed
was picked at Z38 and weighed 109 g. A small correction per stack height is learned on top
(both ways, starts at 0).

Return block remembers where it felt the block on the load cell (`_load_cell_touch_z` in
`studio_learning.json`): next time it moves straight to 2 mm above that height and only does the
last few 1 mm touch steps (about 4 s instead of 14 s).

The button works for the last weighed block and only while the load cell shows a block.

## 3D robot simulator

- Shows the Mirobot (official WLKATA URDF model, Apache-2.0), the plate, the blocks the
  camera sees (picked target highlighted), the load cell, and the block on the suction cup.
- **Real robot:** the arm moves with the robot's own joint angles, read from every status
  reply (J1-J6 shown at the bottom), so the picture matches the real robot.
- **Dry run:** every robot command is turned into joint angles and animated (with suction
  on/off at the right moment), so a run can be checked without moving the robot.
- Mouse: **drag** to turn, **wheel** to zoom, **double-click** to reset the view.

## Face login and roles

| Role | Can do |
|---|---|
| **Operator** | Dashboard, Learning (view), Log |
| **Admin** | everything + Calibration, Users, reset learning |

Lock goes back to the login; the studio also locks after 10 minutes without use
(`auto_lock_minutes`). The machine keeps running while locked.

Add a face ID (Admin): Users > **+ Add new face ID** > details and role > **Next: scan face**
> follow the poses (20 photos). A face already registered under another name is refused.
The face model **retrains automatically** after every add, re-scan or delete.
The last admin cannot be deleted or made Operator; nobody can delete themself.

## Automatic training / learning

| What | How |
|---|---|
| Face model | Retrains itself after every face ID change |
| Pick height | From each block's measured height (`pick_model`), plus a learned correction per stack height, both ways: a success makes the next pick 1 mm higher (max +6 mm), a miss 3 mm lower (max −15 mm). `studio_learning.json` |
| Calibration | Calibration page > Run auto calibration (plate empty). Rejected if the error is above 15 mm |

## Files

| File | What it is |
|---|---|
| `studio.py` | Motion-X window (start this) |
| `sim3d.py` | 3D simulator: robot model, kinematics, renderer |
| `i18n.py` | English / Korean texts |
| `face_engine.py` | Face login, new face IDs, automatic training |
| `machine_engine.py` | Camera + PLC + robot loop, learning, calibration, simulator feed |
| `config.py` | Paths and defaults |
| `studio_config.json` | Settings (face camera, login strictness, auto-lock, language, ...) |
| `studio_learning.json` | Learned pick heights |
| `sim_mesh_cache.npz` | Simplified robot model (made automatically on first start) |
| `access_log.csv` / `studio_log.txt` | Who did what / everything the machine did |

Face data is shared with `..\face_scan.py` (`..\dataset`, `..\people.json`).
Robot code comes from `..\Robot+3DCamera`. Load cell weight = PLC word `D00400` (grams).

## Settings (`studio_config.json`)

| Setting | Default | Meaning |
|---|---|---|
| `language` | `en` | `en` or `ko` (the header button changes it) |
| `face_camera_index` | `0` | Laptop webcam (on this PC `2` is the D455 colour camera) |
| `match_threshold` | `0.42` | Higher = stricter face match |
| `login_frames` | `5` | Matching frames in a row needed to log in |
| `scan_photos` | `20` | Photos per new face ID |
| `auto_lock_minutes` | `10` | `0` = never lock automatically |
| `use_plc` | `true` | Wait for an empty load cell before picking |
| `return_press_mm` | `4` | Return block without load cell feedback: fixed press below the drop-off pose |
| `return_touch_g` | `3` | Weight rise that means the cup touches the block on the load cell |
| `return_seal_mm` | `3` | Press after touching so the suction cup seals |
| `return_drop_mm` | `5` | Return block: set down this far above the pick height |
| `pick_model` | `{"plate_z": 12.0, "scale": 1.05}` | Pick height = plate_z + scale x measured block height (robot Z of the cup's lowest point) |

## Limits

- No liveness check: a good photo of a registered person could log in.
- No other way to log in if the webcam fails - check the camera or `face_camera_index`.
