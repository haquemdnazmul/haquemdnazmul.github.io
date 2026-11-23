# Conveyor Length Sorter

Two conveyors carry 3D-printed blocks past three sensors that measure each block's length. Pneumatic cylinders then push each block into the bin for small, medium or large.

| Block | Size |
|---|---|
| Small | 35 × 35 × 35 mm |
| Medium | 35 × 55 × 35 mm |
| Large | 35 × 85 × 35 mm |

Hardware: LS XGB PLC, TOP touchscreen HMI, 2 conveyors (80 mm belt), 3 length sensors, 5 pneumatic cylinders (0.4–0.6 MPa). A camera and robot arm can load the blocks onto the belt.

**▶ 3D simulator:** https://haquemdnazmul.github.io/conveyor-simulator/ (built from the line's STEP assembly, runs the PLC logic with the real variable names)

## Folders

| Folder | Contents |
|---|---|
| [`plc/`](plc/) | XG5000 ladder program |
| [`hmi/`](hmi/) | HMI screens (TOP Design Studio) |
| [`python/`](python/) | Vision, robot and conveyor code (`run.py` is the entry point) |
| [`docs/`](docs/) | Wiring and pneumatic circuit, flowchart, parts list (BOM), error list, parameter list |
| [`tools/`](tools/) | `step_to_web.py`: turns the STEP assembly into the simulator's web mesh (OpenCascade via `cadquery-ocp`), keeping stoppers, pushers and boxes as separate moving parts |

## PLC design highlights

- **Part tracking without extra hardware:** each block's expected arrival time is queued (FIFO) from a 32-bit running time count, so several blocks can be on the belt at once.
- **Size result latch:** the size reading is held until the block has fully left the sensors. This fixed wrong sorting found during the test run.
- **Arrival check:** an on-delay filter on the arrival sensor, and a block is pushed only if the queue also expects it.
- **Drain stop:** a normal stop runs the belt until it is empty.
- **Safe restart:** after an emergency stop the line goes Reset → Safe → Idle, so nothing moves suddenly.
- **Error system:** alarms are bit-mapped by zone, split into guide messages, light alarms (line waits) and heavy alarms (line stops). A broken upstream sensor is detected from an empty handoff buffer.
- **Interlocks:** cylinder forward/back outputs block each other, and HMI/LAN inputs are bit-masked so they can only write allowed bits.
