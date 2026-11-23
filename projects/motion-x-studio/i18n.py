"""English / Korean text for Motion-X. t("key") gives the text in the current language."""
import re

LANG = "en"

S = {
    # brand / header
    "tagline": ("Vision · Weighing · Robotics", "비전 · 계량 · 로봇 통합 스튜디오"),
    "lock": ("Lock", "잠금"),
    "lang_btn": ("한국어", "English"),
    "machine": ("MACHINE", "장비"),
    "dry_banner": ("DRY RUN · robot does not move", "모의 운전 · 로봇은 움직이지 않음"),
    "state_running": ("RUNNING", "운전 중"), "state_stopped": ("STOPPED", "정지"),
    "state_starting": ("STARTING", "시작 중"), "state_calibrating": ("CALIBRATING", "보정 중"),
    "state_error": ("ERROR", "오류"),
    "role_Admin": ("Admin", "관리자"), "role_Operator": ("Operator", "작업자"),
    # nav
    "nav_dashboard": ("Dashboard", "대시보드"), "nav_learning": ("Learning", "학습"),
    "nav_calibration": ("Calibration", "보정"), "nav_users": ("Users", "사용자"), "nav_log": ("Log", "기록"),
    # status bar
    "sb_robot": ("Robot", "로봇"), "sb_camera": ("Camera", "카메라"), "sb_plc": ("PLC", "PLC"),
    "sb_face": ("Face model", "얼굴 모델"),
    # login
    "face_login": ("FACE LOGIN", "얼굴 인증 로그인"),
    "starting_camera": ("Starting camera...", "카메라 시작 중..."),
    "cam_unavailable": ("Face camera not available", "얼굴 인식 카메라를 사용할 수 없습니다"),
    "updating_model": ("Updating face model...", "얼굴 모델 업데이트 중..."),
    "hello": ("Hello, {name}", "{name} 님, 안녕하세요"),
    "match_hold": ("{role}  ·  match {pct}%  ·  hold still", "{role}  ·  일치율 {pct}%  ·  움직이지 마세요"),
    "not_registered": ("Face not registered", "등록되지 않은 얼굴입니다"),
    "ask_admin": ("Ask an admin to add your face ID.", "관리자에게 얼굴 ID 등록을 요청하세요."),
    "look_camera": ("Look at the camera", "카메라를 바라봐 주세요"),
    "switch_cam": ("Camera {n}  ·  switch camera", "카메라 {n}  ·  카메라 전환"),
    "one_person": ("One person at a time, please", "한 명씩 인증해 주세요"),
    "login_help": ("Look at the laptop camera. Registered people log in automatically.\n"
                   "New people: ask an admin to add your face ID.",
                   "노트북 카메라를 바라보면 등록된 사용자는 자동으로 로그인됩니다.\n"
                   "신규 사용자는 관리자에게 얼굴 ID 등록을 요청하세요."),
    # dashboard
    "start": ("START", "시작"), "stop": ("STOP", "정지"),
    "auto_on": ("AUTO  ON", "자동  ON"), "auto_off": ("AUTO  OFF", "자동  OFF"),
    "pick_now": ("Pick now", "지금 집기"), "next_block": ("Next block", "다음 블록"),
    "retry_skipped": ("Retry skipped", "건너뛴 블록 재시도"),
    "return_block": ("Return block", "블록 되돌리기"),
    "return_q": ("Take the block off the load cell and put it back where it was picked?\n"
                 "Auto mode will be switched off.",
                 "로드셀 위의 블록을 원래 집었던 위치로 되돌릴까요?\n자동 모드는 꺼집니다."),
    "camera_view": ("VISION CAMERA · D455", "비전 카메라 · D455"),
    "sim_view": ("ROBOT SIMULATOR · drag to turn, wheel to zoom", "로봇 시뮬레이터 · 드래그 회전, 휠 확대"),
    "sim_live": ("LIVE · real robot joints", "실시간 · 실제 로봇 관절"),
    "sim_dry": ("SIMULATED · dry run", "시뮬레이션 · 모의 운전"),
    "sim_idle": ("MACHINE STOPPED", "장비 정지"),
    "suction_on": ("SUCTION ON", "흡착 ON"),
    "machine_stopped": ("Machine stopped\n\nPress  START", "장비 정지\n\n시작 버튼을 누르세요"),
    "card_machine": ("Machine", "장비 상태"),
    "card_loadcell": ("Load cell · PLC D00400", "로드셀 · PLC D00400"),
    "card_session": ("This session", "이번 작업"),
    "card_weights": ("Last weights", "최근 측정 무게"),
    "weighed": ("Weighed", "계량 완료"), "missed": ("Missed", "실패"), "skipped": ("Skipped", "건너뜀"),
    "no_data": ("NO DATA", "데이터 없음"), "empty": ("EMPTY", "비어 있음"), "loaded": ("LOADED", "적재됨"),
    "plc_off": ("PLC OFF", "PLC 꺼짐"),
    "plc_ok": ("PLC link OK (RS-485)", "PLC 통신 정상 (RS-485)"),
    "plc_connecting": ("PLC: connecting", "PLC: 연결 중"),
    "plc_adapter": ("PLC: USB-RS485 adapter not found - plug it in", "PLC: USB-RS485 어댑터 없음 - 연결해 주세요"),
    # learning
    "learn_title": ("Learned pick height", "학습된 집기 높이"),
    "learn_text": ("Each block is picked at its own height: the camera measures it and the pick height is "
                   "12.0 + 1.05 x measured height (fitted to your taught heights). On top, a small correction "
                   "is learned per stack height: a block that arrives on the load cell makes the next pick 1 mm "
                   "higher, a missed block 3 mm lower. Saved automatically.",
                   "블록마다 높이가 다르므로 카메라가 측정한 높이로 집기 높이를 정합니다: 12.0 + 1.05 × 측정 높이 "
                   "(티칭한 높이에 맞춤). 여기에 쌓인 높이별 보정값을 학습합니다: 로드셀에 도착하면 다음 집기를 "
                   "1 mm 높이고, 실패하면 3 mm 낮춥니다. 자동 저장됩니다."),
    "col_layer": ("Stack layer", "적층 단"), "col_height": ("Block top (mm)", "블록 윗면 (mm)"),
    "col_offset": ("Correction (mm)", "보정 (mm)"), "col_ok": ("Weighed", "계량 완료"),
    "col_fail": ("Missed", "실패"), "col_rate": ("Success", "성공률"), "col_updated": ("Last change", "최근 변경"),
    "learn_default": ("Stack heights not listed use correction {off:+.0f} mm. Only admins can reset.",
                      "목록에 없는 높이는 보정값 {off:+.0f} mm 를 사용합니다. 초기화는 관리자만 가능합니다."),
    "reset_learning": ("Reset learning", "학습 초기화"),
    "taught_z": ("taught Z{z:.1f}", "티칭 Z{z:.1f}"),
    "reset_q": ("Forget all learned pick heights?", "학습된 집기 높이를 모두 지울까요?"),
    # calibration
    "cal_title": ("Automatic calibration", "자동 보정"),
    "cal_text": ("Teaches the program where the camera is relative to the robot. Run it after the camera "
                 "was moved.\n1. Remove ALL blocks from the plate.  2. Keep hands out of the robot area.  "
                 "3. Press Run - the robot visits 36 points (about 3 minutes).",
                 "카메라와 로봇의 위치 관계를 학습합니다. 카메라를 옮긴 뒤에 실행하세요.\n"
                 "1. 플레이트의 블록을 모두 치우세요.  2. 로봇 작업 영역에 손을 넣지 마세요.  "
                 "3. 실행을 누르면 로봇이 36개 지점을 이동합니다 (약 3분)."),
    "run_cal": ("Run auto calibration", "자동 보정 실행"), "cancel": ("Cancel", "취소"),
    "cal_last": ("Last calibration: {date}   mean error {err:.1f} mm", "최근 보정: {date}   평균 오차 {err:.1f} mm"),
    "cal_last_date": ("Last calibration: {date}", "최근 보정: {date}"),
    "cal_none": ("Not calibrated yet", "아직 보정되지 않음"),
    "cal_now": ("Now: {state}", "현재: {state}"),
    "cal_confirm": ("Is the plate EMPTY and the robot area clear?", "플레이트가 비어 있고 로봇 주변이 안전합니까?"),
    # users
    "users_title": ("Users and face IDs", "사용자 및 얼굴 ID"),
    "users_text": ("Everyone with a face ID can log in. Admins can also calibrate, add/remove face IDs and "
                   "reset learning. The face model retrains automatically after every change.",
                   "얼굴 ID가 있는 사람은 모두 로그인할 수 있습니다. 관리자는 보정, 얼굴 ID 추가/삭제, 학습 "
                   "초기화도 할 수 있습니다. 변경할 때마다 얼굴 모델이 자동으로 다시 학습됩니다."),
    "add_face": ("+  Add new face ID", "+  새 얼굴 ID 등록"), "rescan": ("Re-scan face", "얼굴 다시 스캔"),
    "make_admin": ("Make Admin", "관리자로 지정"), "make_operator": ("Make Operator", "작업자로 지정"),
    "delete": ("Delete", "삭제"),
    "training": ("Training face model...", "얼굴 모델 학습 중..."),
    "model_ok": ("Face model up to date", "얼굴 모델 최신 상태"),
    "col_name": ("Name", "이름"), "col_role": ("Role", "권한"), "col_id": ("ID", "사번"),
    "col_dept": ("Department", "부서"), "col_photos": ("Photos", "사진"), "col_reg": ("Registered", "등록일"),
    "no_scan": ("no face scan", "스캔 없음"),
    "select_first": ("Select a person in the list first.", "먼저 목록에서 사람을 선택하세요."),
    "last_admin": ("This is the last admin - make someone else Admin first.",
                   "마지막 관리자입니다 - 먼저 다른 사람을 관리자로 지정하세요."),
    "last_admin_del": ("This is the last admin - it cannot be deleted.", "마지막 관리자는 삭제할 수 없습니다."),
    "no_self_delete": ("You cannot delete yourself.", "자기 자신은 삭제할 수 없습니다."),
    "delete_q": ("Delete '{name}' and all face photos?\nThis cannot be undone.",
                 "'{name}' 및 모든 얼굴 사진을 삭제할까요?\n되돌릴 수 없습니다."),
    "scanning": ("Scanning {name}: look at the laptop camera", "{name} 스캔 중: 노트북 카메라를 바라보세요"),
    "cancel_scan": ("Cancel scan", "스캔 취소"),
    "saved_face": ("{name} saved ({n} photos).\nThe face model is training now - ready in a few seconds.",
                   "{name} 저장 완료 (사진 {n}장).\n얼굴 모델을 학습 중입니다 - 몇 초 후 사용 가능합니다."),
    "dup_face": ("This face is already registered as '{other}' ({pct}%). Not added.",
                 "이 얼굴은 이미 '{other}'(으)로 등록되어 있습니다 ({pct}%). 등록하지 않았습니다."),
    "pose_0": ("Look straight at the camera", "카메라를 정면으로 보세요"),
    "pose_1": ("Turn your head slightly LEFT", "고개를 살짝 왼쪽으로 돌리세요"),
    "pose_2": ("Turn your head slightly RIGHT", "고개를 살짝 오른쪽으로 돌리세요"),
    "pose_3": ("Tilt your head slightly UP", "고개를 살짝 위로 드세요"),
    "pose_4": ("Tilt your head slightly DOWN", "고개를 살짝 아래로 숙이세요"),
    "closer": ("Come closer to the camera", "카메라에 더 가까이 오세요"),
    "only_one": ("Only one face in the camera, please", "카메라에 한 사람만 보이게 해 주세요"),
    "no_face": ("No face found - look at the camera", "얼굴이 보이지 않습니다 - 카메라를 보세요"),
    # person dialog
    "new_face_id": ("New face ID", "새 얼굴 ID"),
    "f_Name": ("Name", "이름"), "f_ID": ("ID", "사번"), "f_Department": ("Department", "부서"),
    "f_Phone": ("Phone", "전화번호"), "f_Notes": ("Notes", "메모"), "f_Role": ("Role", "권한"),
    "next_scan": ("Next: scan face", "다음: 얼굴 스캔"),
    "bad_name": ('Enter a name (without \\ / : * ? " < > |).', '이름을 입력하세요 (\\ / : * ? " < > | 제외).'),
    "exists_q": ("'{name}' already exists. Replace the face scan?", "'{name}'은(는) 이미 있습니다. 얼굴 스캔을 교체할까요?"),
    # log / close
    "log_title": ("Log", "기록"),
    "log_saved": ("Saved in {a}  and  {b}", "저장 위치: {a}  ,  {b}"),
    "close_q": ("The machine is running.\nStop it (pump off, robot parks) and close?",
                "장비가 운전 중입니다.\n정지하고 (펌프 끔, 로봇 원위치) 종료할까요?"),
}

# machine status lines (English from the engine) -> current language
_STATUS = [
    (r"^READY$", ("READY", "준비 완료")),
    (r"^Connecting\.\.\.$", ("Connecting...", "연결 중...")),
    (r"^Connecting robot\.\.\.$", ("Connecting robot...", "로봇 연결 중...")),
    (r"^Starting camera\.\.\.$", ("Starting camera...", "카메라 시작 중...")),
    (r"^Homing robot\.\.\.$", ("Homing robot...", "로봇 원점 복귀 중...")),
    (r"^Not calibrated$", ("Not calibrated - run calibration", "보정 필요 - 보정을 실행하세요")),
    (r"^Stopped$", ("Stopped", "정지")),
    (r"^PAUSED \(auto off\)$", ("PAUSED (auto off)", "일시정지 (자동 꺼짐)")),
    (r"^PAUSED - no block$", ("PAUSED - no block", "일시정지 - 블록 없음")),
    (r"^No block to pick$", ("No block to pick", "집을 블록 없음")),
    (r"^WAIT: no PLC data$", ("WAIT: no PLC data", "대기: PLC 데이터 없음")),
    (r"^WAIT: block going onto load cell$", ("WAIT: block going onto load cell", "대기: 블록을 로드셀에 올리는 중")),
    (r"^WAIT: load cell not empty \((.*)\)$", ("WAIT: load cell not empty ({0})", "대기: 로드셀에 물건 있음 ({0})")),
    (r"^WAIT: load cell empty, confirming$", ("WAIT: load cell empty, confirming", "대기: 로드셀 비움 확인 중")),
    (r"^WAIT: movement in view \(hand\?\)$", ("WAIT: movement in view (hand?)", "대기: 화면에 움직임 감지 (손?)")),
    (r"^WAIT: block still (.*)$", ("WAIT: block still {0}", "대기: 블록 정지 확인 {0}")),
    (r"^PICKING at (.*)$", ("PICKING at {0}", "집는 중 {0}")),
    (r"^RETURNING block to (.*)$", ("RETURNING block to {0}", "블록 되돌리는 중 → {0}")),
    (r"^Calibrating - keep hands out of the robot area$",
     ("Calibrating - keep hands out of the robot area", "보정 중 - 로봇 영역에 손을 넣지 마세요")),
    (r"^Calibrating: (.*)$", ("Calibrating: {0}", "보정 중: {0}")),
    (r"^Calibration not saved: (.*)$", ("Calibration not saved: {0}", "보정 저장 안 됨: {0}")),
    (r"^ERROR: (.*)$", ("ERROR: {0}", "오류: {0}")),
]


def t(key, **kw):
    pair = S.get(key)
    if pair is None:
        return key
    text = pair[1 if LANG == "ko" else 0]
    return text.format(**kw) if kw else text


def status(text):
    for pat, pair in _STATUS:
        m = re.match(pat, text or "")
        if m:
            return pair[1 if LANG == "ko" else 0].format(*m.groups())
    return text or ""


def pose(message):
    """Enroller messages (English) -> current language."""
    for i in range(5):
        if message == S[f"pose_{i}"][0]:
            return t(f"pose_{i}")
    for k in ("closer", "only_one", "no_face"):
        if message == S[k][0]:
            return t(k)
    return message
