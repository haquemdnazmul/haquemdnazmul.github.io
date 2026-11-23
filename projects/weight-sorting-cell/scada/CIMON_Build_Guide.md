# CIMON SCADA 3.91 – Integrated Line SCADA (Elevator + Weight Sorter)

This kit turns the web mock-up (`../Integrated_SCADA.html`) into a real CIMON SCADA project.

| File | What it is |
|---|---|
| `CIMON_Tags.xlsx` | 182 tags for both PLCs, in CIMON's Excel paste layout (columns A–AH) |
| `CIMON_Tags_paste.txt` | Same tags, tab separated, no header – open, Ctrl+A, Ctrl+C, paste |
| `make_cimon_tags.py` | Script that generated both files (edit and re-run to change tags) |
| `CIMON_Build_Guide.md` | This guide |

CIMON project and page files (`.prj`, `.dbx`, `.PGX`) are encrypted binary files, so they can't be safely written outside CIMON Designer. You create the project and draw the pages in Designer. The tag database, which is the biggest part of the work, comes in with one paste.

---

## 1. Create the project

1. Open **CIMON Designer** (`C:\CIMON\SCADA 3.91\CiMonD.exe`) → **New project**.
   Name: `Integrated_Line_SCADA`. Page size: **1920 × 1080**.
2. Save it in `Weight_Sorting_Project\SCADA_Interface\CIMON\Integrated_Line_SCADA\`.

## 2. I/O devices (two PLCs)

**I/O 디바이스 → 추가 → LS산전 → XGT Fast Ethernet** (TCP, port **2004**). Create two devices. Their names must be exactly these, because the tags use them:

| Device name | PLC | Port | IP |
|---|---|---|---|
| `ELV_PLC` | Elevator, LS XGB (built-in FEnet) | 2004 | your elevator PLC IP |
| `WS_PLC` | Weight sorter, XBM-DN32H2 (built-in FEnet) | 2004 | your sorter PLC IP |

Put both PLCs and the SCADA PC on the same subnet (for example 192.168.0.x). In XG5000, turn on the built-in FEnet and allow the dedicated (XGT) server connection.

Address format: bits are written like XG5000, `P0002E` = word P0002, bit E. A bit inside a D word is written `D00411.0`, with the bit number in decimal.

## 3. Import the tags

1. Open `CIMON_Tags.xlsx` → sheet **CIMON_Tags**.
2. Select **A2 to AH183**. Leave out the header row.
3. Ctrl+C → open **데이터베이스 (Database manager)** → click the tag list → **Ctrl+V**.
4. Save. Open 3–4 tags to check them, for example `ELV_Current_Floor` (D00010, INT16), `WS_Ax1_Cur_Pos` (D01004, INT32) and `WS_Err7` (D00417.0, ON alarm).

If the paste puts values in the wrong fields, copy one existing tag from CIMON into Excel to see your version's column order. Then adjust `HEADER` and the row builders in `make_cimon_tags.py` and run it again: `python make_cimon_tags.py`.

**Tag naming**
- `ELV_*` = elevator, `WS_*` = sorter.
- `*_B_*` and `*_Btn` = HMI command bits (M area) that SCADA writes.
- `*_S_*` and `*_Sensor_*` = inputs (display only).
- `ELV_Fx_Hall_*` = physical hall buttons. These are PLC inputs, so display them only and never write them.

**Alarms already set by the import**

| Area | Tag | Alarm |
|---|---|---|
| A (Elevator) | `ELV_EStop_Input` (P00000, NC) | OFF alarm: emergency stop pressed |
| A | `ELV_Error_Stop` (M00405) | ON alarm: error stop – check `ELV_Error_Code` |
| A | `ELV_Motor_Power` (P00020) | OFF alarm: motor power off |
| B (Sorter) | `WS_EMG_Physical` (P0000C) | ON alarm: emergency stop |
| B | `WS_Err1` … `WS_Err9` (D00411.0 … D00419.0) | ON alarm, with the manual's message for each error |

Elevator error code meanings (`ELV_Error_Code`, D00002): 1 Motor not running · 2 Motor power off · 3 Door failed to open · 4 Door failed to close · 5 Stopped between floors · 6 Out of range.

## 4. Pages

Make 5 pages. `MAIN` is the frame; the other four open inside it.

| Page | Size | Purpose |
|---|---|---|
| `MAIN` | 1920×1080 | Top bar plus a navigation button row; holds the other pages |
| `OVERVIEW` | 1920×960 | Both stations side by side, like the web mock-up |
| `ELEVATOR` | 1920×960 | Elevator detail plus admin and manual controls |
| `SORTER` | 1920×960 | Sorter detail plus servo jog, teaching and manual moves |
| `ALARM` | 1920×960 | Alarm summary object (areas A and B) |

Navigation buttons on `MAIN`: **Touch → script** `ReplacePage("OVERVIEW", "ELEVATOR")`, and the same pattern for the other pages. Or use `OpenPagePos("ELEVATOR", "0,120,1920,960")`.

Use the colour rules from the mock-up (ISA-101 style): grey plant, and colour only for state.
- Green = running / ON
- Yellow = waiting / warning
- Red = alarm or E-stop
- Unlit lamp = dark grey

### 4.1 Top bar (on MAIN)

| Object | Tag / script | Animation |
|---|---|---|
| Title text "Integrated Line SCADA" | – | – |
| Lamp "ELV PLC" | I/O device status of `ELV_PLC` (system tag) | Colour: OK = green, fail = red |
| Lamp "WS PLC" | I/O device status of `WS_PLC` | Colour |
| Active alarms | `GetAlarmCount(...)` in a script → virtual tag `SYS_AlarmCount` | Number display, red when > 0 |
| Clock | system time | Text |

### 4.2 Elevator (OVERVIEW left half, and the ELEVATOR page)

**Shaft:** draw 6 floor rows, each 100 px high, labelled 6F at the top down to 1F.

| Object | Tag | CIMON animation |
|---|---|---|
| Car (rectangle group) | `ELV_Current_Floor` | **Move (위치이동) Y**: value 10 → 1F position, 60 → 6F position (offset −500 px). Values 15, 25, … put the car between floors automatically. |
| Door leaves (2 rectangles) | `ELV_Door_Open_Sensor` / `ELV_Door_Close_Sensor` | **Size (크기변화) width**, or Visibility (출몰): closed leaves when Close_Sensor = 1 |
| Floor sensor marks (12 small rectangles) | `ELV_Fn_Sensor_Upper` / `_Lower` | Colour: ON green |
| Hall call lamps ▲▼ | `ELV_Target_nF` (call registered) | Colour: ON amber, lit lamp |
| Up / down arrows | `ELV_Motor_Up_CW` / `ELV_Motor_Down_CCW` | Colour: ON green |
| Current floor big number | `ELV_Current_Floor` | Number display, expression `ELV_Current_Floor / 10` |
| Door text | `ELV_Door_Step` | Text by value: 0 Closed · 1 Opening · 2 Open · 3 Closing |
| Car panel buttons 1–6 | `ELV_Car_nF_Btn` (M00011–M00016) | **Touch → digital, momentary (누르는 동안 ON)**; lamp colour from `ELV_Target_nF` |
| Open / Close buttons | `ELV_Car_Open_Btn` / `ELV_Car_Close_Btn` | Touch, momentary |
| E-STOP button (red) | `ELV_B_EStop_HMI` (M00023) | Touch, momentary. Colour blinks from `ELV_EStop_Relay` |
| ERROR ACK | `ELV_B_Error_Ack` (M00400) | Touch, momentary |
| I/O lamp row | `ELV_Motor_Power`, `ELV_Door_Cyl_ON`, `ELV_Boarding_Sensor`, … | Colour |
| Status text | expression (see below) | Text |

Elevator status text, as one expression or a small script into a virtual string tag:
`ELV_EStop_Relay` → "E-STOP"; `ELV_Error_Stop` → "ERROR " + code; `ELV_Motor_Up_CW` → "RUNNING UP"; `ELV_Motor_Down_CCW` → "RUNNING DOWN"; otherwise "IDLE".

ELEVATOR page only (admin panel): `ELV_B_Admin_Mode`, `ELV_B_Admin_Mode_OFF`, `ELV_B_Motor_Power_ON`, `ELV_B_Manual_Up/Down/Open/Close`. Show this panel only while `ELV_Admin_Mode_ON` = 1 (Visibility, 출몰).

### 4.3 Weight sorter (OVERVIEW right half, and the SORTER page)

**Layout (top view):** load cell square on the left. To its right, a 3 × 3 grid of 150 px slot squares numbered row by row: 1 2 3 / 4 5 6 / 7 8 9.

| Object | Tag | CIMON animation |
|---|---|---|
| Slot sensor dot (×9) | `WS_S_Pos_n` | Colour: ON green |
| Item circle in slot (×9) | `WS_S_Pos_n` | Visibility (출몰) |
| Weight text in slot (×9) | `WS_Wt_n` | Number, unit g |
| Target weight under slot (×8) | `WS_Wt_n_Sort` | Number. Visible when `WS_Step_Move >= 8` |
| In-place frame (×8) | expression `WS_Wt_n == WS_Wt_n_Sort && WS_Step_Move >= 10` | Colour: green |
| Holding-rack label | expression `WS_Pos_Rack_No == n && WS_R_Sort` | Visibility: "RACK" text, dashed frame |
| Gantry bridge (horizontal bar) | `WS_Ax1_Cur_Pos` (Y) | Move Y – see calibration below |
| Carriage + cup | `WS_Ax2_Cur_Pos` (X), `WS_Ax1_Cur_Pos` (Y) | Move X and Y |
| Cup inner dot | `WS_S_Suction` | Colour: ON blue (vacuum) |
| Cylinder state | `WS_S_Cyl_Fwd` / `WS_S_Cyl_Bwd` | Text FWD / BWD |
| Tower lamp (3 segments) | `WS_L_Red`, `WS_L_Yellow`, `WS_L_Green` | Colour: lit / unlit |
| Live weight (large) | `WS_LC_Weight` | Number, "g" |
| Work quantity input | `WS_Work_Qty` (D00030) | **Touch → analog input**, min 3, max 8 |
| Mode text | `WS_Op_Mode` | 1 Auto · 2 Manual · 3 Stopped |
| Step readouts | `WS_Step_Move`, `WS_Step_Sort`, `WS_Step_PickPlace`, `WS_Load_Item_No`, `WS_Done_Count` | Number |
| START / SORT / PAUSE / RESTART / ERR RESET | `WS_B_Start`, `WS_B_Sort`, `WS_B_Pause`, `WS_B_Restart`, `WS_B_Err_Reset` | Touch, momentary |
| AUTO / MANUAL | `WS_B_Auto_Mode`, `WS_B_Manual_Mode` | Touch, momentary |
| E-STOP | `WS_B_EMG_HMI` | Touch, momentary (red) |
| Status text | `WS_Step_Move` | 0 Idle · 1 Waiting item · 2 Weighing · 3 To load cell · 4 Pick · 5 To slot · 6 Place · 7 Next · 8 Data sort · 10 Waiting for SORT · 11 Rearranging · 12 Complete |
| Error text | `WS_Err_Code` | Text by value 1–9 (messages in section 3) |

**Gantry position calibration.** The axis unit is a module parameter (the manual suggests 0.1 µm/count), so take the numbers from the real machine:
1. In runtime, read `WS_Ax2_Cur_Pos` and `WS_Ax1_Cur_Pos` with the cup over **slot 1**, and again over **slot 9**.
2. In the Move animation, set *tag min/max* = those two counts and *pixel move* = the distance on screen between slot 1 and slot 9.
3. For reference, the pickup position must be inside X 1,250,000–1,600,000 and Y −1,300,000 to −800,000 (the window that error 3 checks).

SORTER page only (commissioning panel):
- Servo: `WS_B_SV_Connect`, `WS_B_SV_Off`, `WS_B_SV_Clr`, `WS_B_SV_Home`, and speed stages `WS_B_SV_Stage_1…5`.
- Jog: `WS_B_SV_Ax1_CW/CCW` and `WS_B_SV_Ax2_CW/CCW` (momentary, hold to jog).
- Teaching: `WS_B_Set_Pick_Pos`, `WS_B_Set_Place_Pos`, with status lamps `WS_SG_Pick_Pos_Set` and `WS_SG_Load_Pos_Set`.
- Manual: `WS_B_Man_Pick`, `WS_B_Man_Place`, `WS_B_Man_Pick_Pos`, `WS_B_Man_Pos_1…9`.
- Recovery: `WS_B_Init`, and `WS_B_Factory_Reset` (put a confirmation popup on it).

### 4.4 Alarm page

Place a **경보 요약 오브젝트 (Alarm summary)** at full size, with the filter set to areas **A + B**. Add a column for area, so operators see which station raised the alarm. Add buttons with `AlarmCommand("ALM1", ...)` to acknowledge all or acknowledge the selected alarm.

On `MAIN`, also place a small one-line alarm banner (an Alarm summary set to 1 row, newest first). That way an active alarm shows on every page.

## 5. Test without the PLCs

1. Set both I/O devices to simulation (or leave them disconnected). In **CimonX** runtime, write test values to `ELV_Current_Floor` (10 → 35 → 60) and `WS_Step_Move` (0 … 12), and check that the car moves and the status texts change.
2. Set `WS_Err7` (D00417) to 1 → an area B alarm must appear with "The cylinder did not operate."
3. Then connect the real PLCs and run one elevator call and one sorting cycle with quantity 3.

## 6. Things to confirm on the real machines

- **Momentary command bits:** check that the ladder resets each HMI bit or uses it as a pulse. Both manuals say to use short pushes.
- **Hall-call inputs:** `ELV_Fx_Hall_*` (P0000x) are inputs, so the SCADA cannot place a hall call. If you want hall calls from SCADA, add M bits in the elevator ladder and add matching tags.
- **Weight register size:** `WS_Wt_n` / `WS_Wt_n_Sort` are set as INT32 (every 2nd word, as the manual says). If the values look wrong, change the data type to INT16.
- **Load-cell calibration buttons** (M00301–M00306) are left out because the manual doesn't give one address per button. Add them after you check them in XG5000.
