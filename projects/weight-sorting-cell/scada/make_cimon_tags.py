"""Build CIMON SCADA tag-database paste files for the Elevator + Weight Sorter SCADA.

Column layout follows CIMON SCADA 3.91 help, "엑셀을 이용한 데이터베이스 편집"
(태그 종류별 엑셀 데이터 형태). Output:
  CIMON_Tags.xlsx       - row 1 = header, rows 2.. = tags (copy A2:AH<last> and paste)
  CIMON_Tags_paste.txt  - same rows, tab separated, no header (open, Ctrl+A, Ctrl+C, paste)

Addresses: elevator = Device_List_EN.xlsx (3조_1차승강기_PLC_v3),
sorter = 3rd Group Weight Sorter Manual (3rd_Group_Weight_Sorter_PLC_250909_EN.xgwx).
Run:  python make_cimon_tags.py
"""
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

ELV = "ELV_PLC"   # I/O device name to create in CIMON (LS XGT Fast Ethernet)
WS = "WS_PLC"     # I/O device name to create in CIMON (LS XGT Fast Ethernet)
NCOL = 34         # A..AH

INT16, INT32 = 1, 2
RANGE = {INT16: (-32768, 32767), INT32: (-2147483648, 2147483647)}

HEADER = [
    "A Tag name", "B Type (1=Digital 2=Analog)", "C Comment", "D Real(1)/Virtual(0)",
    "E I/O device", "F I/O address", "G Initial value", "H Data-collection model",
    "I OFF text | Data type", "J ON text | Deadband", "K Unit", "L Power factor",
    "M Scale", "N Int min", "O Int max", "P Real min", "Q Real max",
    "R Save last state", "S Write initial value", "T Action on change", "U Alarm tag",
    "V Report data", "W Invert | Reset", "X Tag action", "Y Alarm enable",
    "Z Alarm kind (1=OFF 2=ON)", "AA Alarm grade", "AB Alarm area", "AC Sensitivity",
    "AD Alarm delay", "AE Ack text", "AF Clear text", "AG Clear action", "AH Alarm text",
]

rows = []


def digital(name, comment, dev, addr, off="OFF", on="ON", alarm=None, area="A"):
    """alarm = (kind, grade, text) ; kind 1 = OFF alarm, 2 = ON alarm."""
    r = [""] * NCOL
    r[0:10] = [name, 1, comment, 1, dev, addr, 0, "", off, on]
    r[17:21] = [0, 0, 0, 1 if alarm else 0]
    r[21:23] = [0, 0]
    if alarm:
        kind, grade, text = alarm
        r[24:34] = [1, kind, grade, area, "", 0, "Acknowledged", "Cleared", "", text]
    rows.append(r)


def analog(name, comment, dev, addr, dtype=INT16, unit=""):
    lo, hi = RANGE[dtype]
    r = [""] * NCOL
    r[0:17] = [name, 2, comment, 1, dev, addr, 0, "", dtype, 0, unit, 0, 0, lo, hi, lo, hi]
    r[17:23] = [0, 0, 0, 0, 0, 0]
    rows.append(r)


# ======================= ELEVATOR (LS XGB) =======================
e = "ELV_"
# --- position / run data
analog(e + "Current_Floor", "Current floor x10 (odd tens = between floors)", ELV, "D00010")
analog(e + "Target_Floor", "Target floor x10", ELV, "D00011")
analog(e + "Error_Code", "Active error code 1-6", ELV, "D00002")
analog(e + "Door_Step", "Door state-machine step 0,1,2,3,100", ELV, "D00020")
# --- outputs / motor / door
digital(e + "Motor_Power", "Motor power P00020", ELV, "P00020", alarm=(1, 2, "Elevator motor power OFF"))
digital(e + "Motor_Up_CW", "Motor run up (CW)", ELV, "P0002E")
digital(e + "Motor_Down_CCW", "Motor run down (CCW)", ELV, "P0002F")
digital(e + "Door_Cyl_ON", "Door cylinder solenoid", ELV, "P00021")
digital(e + "Door_Open_Sensor", "Door cylinder open sensor", ELV, "P0004C")
digital(e + "Door_Close_Sensor", "Door cylinder closed sensor", ELV, "P0004D")
digital(e + "Boarding_Sensor", "Passenger sensor in doorway", ELV, "P0004E")
# --- safety
digital(e + "EStop_Input", "Physical E-stop (NC: OFF = pressed)", ELV, "P00000",
        off="PRESSED", on="OK", alarm=(1, 1, "Elevator emergency stop pressed"))
digital(e + "EStop_Relay", "E-stop relay (latched)", ELV, "M00032")
digital(e + "Error_Stop", "Error stop active (see ELV_Error_Code)", ELV, "M00405",
        alarm=(2, 1, "Elevator error stop - check error code"))
digital(e + "Admin_Mode_ON", "Admin mode active", ELV, "M00402")
digital(e + "Arrived", "Car arrived at target floor", ELV, "M00030")
digital(e + "Up_Standby", "Up direction standby", ELV, "M00000")
digital(e + "Down_Standby", "Down direction standby", ELV, "M00002")
# --- floor sensors (upper / lower)
for f in range(1, 7):
    lo_addr = f"P0004{(f - 1) * 2:X}"
    up_addr = f"P0004{(f - 1) * 2 + 1:X}"
    digital(e + f"F{f}_Sensor_Upper", f"{f}F upper position sensor", ELV, up_addr)
    digital(e + f"F{f}_Sensor_Lower", f"{f}F lower position sensor", ELV, lo_addr)
# --- hall call inputs (read only, physical buttons)
hall = {1: ("P00001", None), 2: ("P00003", "P00002"), 3: ("P00005", "P00004"),
        4: ("P00007", "P00006"), 5: ("P00009", "P00008"), 6: (None, "P0000A")}
for f, (up, dn) in hall.items():
    if up:
        digital(e + f"F{f}_Hall_Up", f"{f}F hall up button (input)", ELV, up)
    if dn:
        digital(e + f"F{f}_Hall_Down", f"{f}F hall down button (input)", ELV, dn)
# --- floor request flags (call registered) -> lamp on screen
for f in range(1, 7):
    digital(e + f"Target_{f}F", f"{f}F requested (any call)", ELV, f"M0011{f}")
# --- HMI command bits (write from SCADA, momentary)
for f in range(1, 7):
    digital(e + f"Car_{f}F_Btn", f"Car panel {f}F button (HMI)", ELV, f"M0001{f}")
digital(e + "Car_Close_Btn", "Car panel door close (HMI)", ELV, "M00020")
digital(e + "Car_Open_Btn", "Car panel door open (HMI)", ELV, "M00021")
digital(e + "B_EStop_HMI", "HMI soft E-stop button", ELV, "M00023")
digital(e + "B_Error_Ack", "HMI acknowledge / clear error", ELV, "M00400")
digital(e + "B_Admin_Mode", "HMI admin mode", ELV, "M00401")
digital(e + "B_Admin_Mode_OFF", "HMI leave admin mode", ELV, "M00403")
digital(e + "B_Motor_Power_ON", "HMI motor power on (admin)", ELV, "M0002A")
digital(e + "B_Manual_Up", "HMI manual car up (admin)", ELV, "M0002C")
digital(e + "B_Manual_Down", "HMI manual car down (admin)", ELV, "M0002D")
digital(e + "B_Manual_Open", "HMI manual door open (admin)", ELV, "M0000E")
digital(e + "B_Manual_Close", "HMI manual door close (admin)", ELV, "M0000F")

# ======================= WEIGHT SORTER (XBM-DN32H2) =======================
w = "WS_"
A = "B"  # alarm area for the sorter
# --- data registers
analog(w + "Op_Mode", "1=auto 2=manual 3=stopped", WS, "D00000")
analog(w + "Load_Item_No", "Item being loaded = slot no.", WS, "D00009")
analog(w + "Step_Move", "STEP_MOVE main cycle 1-12", WS, "D00010")
analog(w + "Step_Sort", "STEP_SORT rearrangement 1-9", WS, "D00011")
analog(w + "Step_PickPlace", "STEP_PICK_PLACE 1-4", WS, "D00012")
analog(w + "Step_Init", "STEP_INIT 1-8", WS, "D00013")
analog(w + "Pos_Rack_Item", "First slot with item in wrong place", WS, "D00021")
analog(w + "Pos_Rack_No", "Holding-rack slot = qty+1", WS, "D00022")
analog(w + "Pos_Empty_Item", "Slot holding item for the empty slot", WS, "D00023")
analog(w + "Pos_Empty", "Empty slot", WS, "D00025")
analog(w + "Done_Count", "Progress counter", WS, "D00027")
analog(w + "Work_Qty", "Work quantity 3-8 (write from SCADA)", WS, "D00030")
analog(w + "Wt_Picking", "Weight of item being carried", WS, "D00080", unit="g")
analog(w + "LC_Weight", "Live load-cell weight", WS, "D00400", unit="g")
analog(w + "Err_Code", "Active error 1-9 (0 = none)", WS, "D00401")
analog(w + "LC_Err_Code", "Load-cell module error code", WS, "D00410")
analog(w + "Ax1_Cur_Pos", "Axis 1 (Y) current position, raw counts", WS, "D01004", INT32)
analog(w + "Ax2_Cur_Pos", "Axis 2 (X) current position, raw counts", WS, "D02004", INT32)
for i in range(1, 10):
    analog(w + f"Wt_{i}", f"Weight of item in slot {i}", WS, f"D{200 + (i - 1) * 2:05d}", INT32, "g")
for i in range(1, 9):
    analog(w + f"Wt_{i}_Sort", f"Sorted weight that belongs in slot {i}", WS, f"D{220 + (i - 1) * 2:05d}", INT32, "g")
# --- error flags (bit 0 of D00411..D00419) -> alarms
WS_ERR = {
    1: "Please enter the work quantity.",
    2: "Please enter a value between 3 and 8.",
    3: "Please set the pickup position.",
    4: "Please set the load position.",
    5: "Zero and span calibration have not been done.",
    6: "The load location is not empty.",
    7: "The cylinder did not operate.",
    8: "The cylinder did not return.",
    9: "Suction did not hold the item.",
}
for n, msg in WS_ERR.items():
    digital(w + f"Err{n}", f"SG_ERR{n} error flag", WS, f"D{410 + n:05d}.0",
            alarm=(2, 1 if n >= 7 else 3, f"Sorter E{n}: {msg}"), area=A)
# --- physical I/O
for i in range(1, 10):
    digital(w + f"S_Pos_{i}", f"Slot {i} proximity sensor (item present)", WS, f"P0000{i}")
digital(w + "EMG_Physical", "Physical emergency stop", WS, "P0000C",
        alarm=(2, 1, "Sorter emergency stop pressed"), area=A)
digital(w + "S_Cyl_Fwd", "Cylinder forward sensor", WS, "P0000D")
digital(w + "S_Cyl_Bwd", "Cylinder backward sensor", WS, "P0000E")
digital(w + "S_Suction", "Vacuum sensor (item held)", WS, "P0000F")
digital(w + "P_Cyl_Fwd_Cmd", "Cylinder valve", WS, "P00020")
digital(w + "P_Suction_Cmd", "Vacuum valve", WS, "P00021")
digital(w + "L_Red", "Tower lamp red (running)", WS, "P00022")
digital(w + "L_Yellow", "Tower lamp yellow (error)", WS, "P00023")
digital(w + "L_Green", "Tower lamp green (load next item)", WS, "P00024")
# --- internal flags
digital(w + "SG_Pick_Pos_Set", "Pickup position taught", WS, "M00021")
digital(w + "SG_Load_Pos_Set", "Slot positions taught", WS, "M00022")
digital(w + "SG_Load_Done", "All items loaded", WS, "M00030")
digital(w + "SG_Item_Ready", "Stable item on load cell", WS, "M00032")
digital(w + "SG_Cal_Save_Done", "Load-cell calibration saved", WS, "M00033")
digital(w + "S_Rack_On", "Holding-rack slot has an item", WS, "M0003A")
digital(w + "R_Sort", "Rearrangement running", WS, "M00040")
digital(w + "SG_Sort_Done", "All slots in order", WS, "M00041")
digital(w + "SG_Rearr_Done", "Rearrangement finished", WS, "M00044")
digital(w + "R_Init", "Initialization running", WS, "M00045")
digital(w + "R_Factory_Reset", "Factory reset running", WS, "M00046")
digital(w + "R_Pick", "Pick request", WS, "M00050")
digital(w + "SG_Pick_Done", "Pick done", WS, "M00051")
digital(w + "R_Place", "Place request", WS, "M00052")
digital(w + "SG_Place_Done", "Place done", WS, "M00053")
digital(w + "R_Lamp_Load_OK", "Operator may load next item", WS, "M00100")
digital(w + "M_Stop", "Machine stopped", WS, "M00500")
digital(w + "R_Stop_Err", "Stopped by an error", WS, "M00501")
digital(w + "R_Stop_Btn", "Stopped by Pause", WS, "M00502")
digital(w + "SG_SV_Pos_Done", "Axis 1 positioning complete", WS, "D01000.2")
# --- HMI command bits (write from SCADA, momentary)
for addr, name, cmt in [
    ("M00000", "B_SV_Connect", "Connect servo network"),
    ("M00001", "B_SV_Off", "Disconnect servo network"),
    ("M00002", "B_SV_Clr", "Clear servo errors"),
    ("M00003", "B_SV_Home", "Home both axes"),
    ("M00005", "B_SV_Stage_1", "Jog speed stage 1"),
    ("M00006", "B_SV_Stage_2", "Jog speed stage 2"),
    ("M00007", "B_SV_Stage_3", "Jog speed stage 3"),
    ("M00008", "B_SV_Stage_4", "Jog speed stage 4"),
    ("M00009", "B_SV_Stage_5", "Jog speed stage 5"),
    ("M0000C", "B_SV_Ax1_CW", "Jog axis 1 CW (hold)"),
    ("M0000D", "B_SV_Ax1_CCW", "Jog axis 1 CCW (hold)"),
    ("M0000E", "B_SV_Ax2_CW", "Jog axis 2 CW (hold)"),
    ("M0000F", "B_SV_Ax2_CCW", "Jog axis 2 CCW (hold)"),
    ("M00010", "B_Set_Place_Pos", "Teach slot 1"),
    ("M00020", "B_Set_Pick_Pos", "Teach pickup position"),
    ("M00024", "B_Sort", "Start rearrangement"),
    ("M00025", "B_Factory_Reset", "Factory reset"),
    ("M00026", "B_Man_Pick", "Manual pick"),
    ("M00027", "B_Man_Place", "Manual place"),
    ("M00028", "B_EMG_HMI", "HMI emergency stop"),
    ("M00029", "B_Init", "Initialize (return items)"),
    ("M0002A", "B_Start", "Start loading"),
    ("M0002B", "B_Err_Reset", "Reset errors"),
    ("M0002C", "B_Auto_Mode", "Auto mode"),
    ("M0002D", "B_Manual_Mode", "Manual mode"),
    ("M0002E", "B_Pause", "Pause / stop"),
    ("M0002F", "B_Restart", "Restart"),
    ("M00060", "B_Man_Pick_Pos", "Manual move to pickup position"),
] + [(f"M0006{i}", f"B_Man_Pos_{i}", f"Manual move to slot {i}") for i in range(1, 10)]:
    digital(w + name, cmt, WS, addr)

# ======================= write files =======================
out = Path(__file__).with_name("CIMON_Tags.xlsx")
wb = openpyxl.Workbook()
ws_ = wb.active
ws_.title = "CIMON_Tags"
ws_.append(HEADER)
for r in rows:
    ws_.append(r)
hdr_fill = PatternFill("solid", fgColor="D9DEE3")
for c in ws_[1]:
    c.font = Font(bold=True)
    c.fill = hdr_fill
    c.alignment = Alignment(wrap_text=True, vertical="top")
ws_.row_dimensions[1].height = 45
ws_.freeze_panes = "B2"
widths = {1: 26, 3: 42, 5: 10, 6: 11, 34: 46}
for i in range(1, NCOL + 1):
    ws_.column_dimensions[get_column_letter(i)].width = widths.get(i, 9)
# text format for address column so Excel never turns P0002E into a number
for row in ws_.iter_rows(min_row=2, min_col=6, max_col=6):
    for c in row:
        c.number_format = "@"

info = wb.create_sheet("How to paste")
for line in [
    ["CIMON SCADA 3.91 - tag import for Elevator + Weight Sorter"],
    [""],
    ["1. In CIMON Designer create two I/O devices (LS산전 > XGT Fast Ethernet, TCP port 2004):"],
    [f"     {ELV}  -> IP of the elevator XGB built-in FEnet"],
    [f"     {WS}   -> IP of the weight-sorter XBM-DN32H2 built-in FEnet"],
    ["2. On sheet CIMON_Tags select cells A2 to AH" + str(len(rows) + 1) + " (do NOT include the header row)."],
    ["3. Ctrl+C, open 데이터베이스 관리기 (Database), click the tag list, Ctrl+V."],
    ["   Existing tags with the same name are updated, new names are added."],
    ["4. Save the database and check a few tags (address, data type, alarm)."],
    [""],
    ["Alarm area A = elevator, B = weight sorter. Grade 1 = E-stop/critical, 2 = motor power, 3 = start-check errors."],
    ["Tags named *_B_* or *_Btn are HMI command bits: link them to momentary (누르는 동안 ON) buttons."],
    ["Hall-call tags (ELV_Fx_Hall_*) are physical inputs: display only, do not write."],
    [f"Total tags: {len(rows)}"],
]:
    info.append(line)
info.column_dimensions["A"].width = 110
wb.move_sheet("How to paste", offset=-1)
wb.save(out)

txt = Path(__file__).with_name("CIMON_Tags_paste.txt")
with open(txt, "w", encoding="utf-8-sig", newline="\r\n") as f:
    for r in rows:
        f.write("\t".join("" if v is None else str(v) for v in r) + "\n")

print(f"{len(rows)} tags -> {out.name}, {txt.name}")
