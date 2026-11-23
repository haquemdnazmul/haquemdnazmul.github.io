"""컨베이어 PLC — PLC 한 대에 붙는 워커.

태그 하나를 직접 읽고 쓰는 창구다. 화면을 모른다 — 일은 큐로 받고 결과는 사건 큐로 낸다.

표기를 주소로 옮기고 펑션코드를 태우는 일은 `Connect.Device.PLC` 가 한다.
이 파일은 **어느 PLC 에 언제 붙어서 무엇을 주고받을지**만 정한다.

설비 상태를 한 벌로 읽는 길은 래더를 보고 정한다.
그때까지 **자리를 미리 만들지 않는다** — 없으면 없는 채로 두고 부르는 쪽이 터지게 한다.
고장이 곧 계측기다.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any, NamedTuple
from enum import Enum, IntEnum, StrEnum, Flag, auto, nonmember

from com_lib_core import Config, Connect, Tool
import cv2


class PlcBus:
    """PLC **한 대**에 붙는 워커.

    한 워커가 한 대를 독점한다.
    PLC 가 둘이면 이것을 둘 세운다 — 하나가 둘을 번갈아 보지 않는다.
    상대를 어디에 적어 두는지가 그 전제 위에 서 있다 (`com_lib_core` `Data.LS.talking_to`).

    링크를 세우는 것은 부르는 쪽 스레드이고 **붙는 것은 이 워커**다.
    둘이 다른 스레드라 `Controller` 가 `open()` 에서 자기를 앉힌다.
    """

    class Job(Enum):
        """맡길 수 있는 일. `submit` 이 받는 낱말은 이것이 전부다."""

        CONNECT = "connect"
        DISCONNECT = "disconnect"
        READ = "read"            # device
        WRITE = "write"          # device · value

    communication: "Config.Communication"  # 통신 규격(`communication.json`) 통째 — 맡은 PLC · LS 표기 · QR 규격을 키 경로로 읽는다. 화면도 이것으로 규격을 본다
    which: int  # 이 워커가 맡은 PLC 가 `plc_controller` 의 몇 번째인가
    connected: Tool.Slot
    reading: Tool.Slot  # `PlcRead.survey` 가 푼 한 벌. 열쇠는 `PlcRead.AddressRule.Type` 이다. 안 붙었으면 `None`
    special: Tool.Slot  # `PlcRead.loose` 가 읽은 낱개 코일 한 벌. 열쇠는 `SpecialBit` 이다. 안 붙었으면 `None`
    sorter: "QrSort"  # QR 상태기계. 긁을 때마다 판독 모드와 측정부 재실로 단계를 나아간다
    events: queue.Queue
    requests: queue.Queue
    _link: Connect.Device.PLC.Data.LS.Controller
    _shutdown: threading.Event
    _thread: threading.Thread

    def __init__(self, comm: "Config.Communication", which: int = 0):
        self.communication = comm
        self.which = which
        self.connected = Tool.Slot(False)
        self.reading = Tool.Slot()
        self.special = Tool.Slot()
        self.sorter = QrSort(comm)
        self.events = queue.Queue()
        self.requests = queue.Queue()
        self._link = Connect.Device.PLC.Data.LS.Controller(comm.plc_ls, comm.plc_controller[which])
        self._shutdown = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def shutdown(self) -> None:
        self._shutdown.set()

    def submit(self, job: "PlcBus.Job", **payload) -> None:
        """연결 · 해제 · 단발 읽기 · 쓰기 요청. 링크는 워커가 독점하므로 여기서 직접 만지지 않는다."""
        self.requests.put((job, payload))

    def _say(self, text: str) -> None:
        self.events.put(Tool.Event(text, time.monotonic()))

    def _do_request(self, job: "PlcBus.Job", payload: dict) -> None:
        tag = payload.get("device", "").strip().upper()
        if not tag:
            self._say("태그를 입력한다")
            return
        # 표기를 읽는 것은 `Device` 다. 어느 PLC 에 묻는지는 이 워커가 앉힌 상대가 정한다
        one = Connect.Device.PLC.Data.LS.Device(tag)
        if job == self.Job.READ:
            value = one.value
            self._say(f"{tag} = {'ON' if value is True else 'OFF' if value is False else value}")
            return
        text = payload.get("value", "").strip()
        try:
            number = int(text)
        except ValueError:
            self._say(f"쓸 값이 정수가 아니다 :: {text!r}")
            return
        one.value = number
        self._say(f"{tag} 에 {number} 을 썼다")

    def _handle(self, job: "PlcBus.Job", payload: dict) -> None:
        if job == self.Job.CONNECT:
            self._connect()
        elif job == self.Job.DISCONNECT:
            self._close()
            self._say("PLC 연결을 닫았다")
        else:
            self._do_request(job, payload)

    def _connect(self) -> None:
        host = self.communication.plc_controller[self.which].transport.host
        if not self._link.open():
            self._say(f"PLC 에 닿지 못했다 :: {host}")
            return
        self.connected.put(True)
        self._say(f"PLC 연결됨 :: {host}")

    def _close(self) -> None:
        try:
            self._link.close()
        except Exception:                                 # noqa: BLE001
            pass
        self.connected.put(False)
        self.reading.put(None)
        self.special.put(None)

    def _poll(self) -> None:
        try:
            self.reading.put(PlcRead.survey(self.communication.plc_controller[self.which].ladder.read_start))
            special = PlcRead.loose()
            self.special.put(special)
            special_bit = PlcRead.AddressRule.Type.SpecialBit
            self.sorter.advance(special[special_bit.FLAG_DetectMode_QR], special[special_bit.SIG_GET_CHK_L0])
        except Exception as exc:                          # noqa: BLE001
            self._say(f"PLC 를 읽지 못했다 :: {exc}")
            self._close()

    def _run(self) -> None:
        """붙기 전에는 요청만 기다린다. 붙어 있는 동안만 정주기로 긁는다."""
        last = 0.0
        while not self._shutdown.is_set():
            try:
                job, payload = self.requests.get(timeout=self.communication.plc_controller[self.which].transport.request_wait__s)
            except queue.Empty:
                if self.connected.get() and time.monotonic() - last >= self.communication.plc_controller[self.which].transport.poll_cycle__s:
                    last = time.monotonic()
                    self._poll()
                continue
            try:
                self._handle(job, payload)
            except Exception as exc:                      # noqa: BLE001
                self._say(f"{job} 에 실패했다 :: {exc}")
        self._close()


# -------------------------------------------------------------------- QR

class QrSort:
    """QR 로 규격을 읽어 PLC 에 알린다. 로봇 투입 사이클 밖이며 독립으로 돈다.

    래더가 신호를 받는 창은 자재가 측정부에 들어와 있는 동안이다.
    그 창 안에서 일어난 상승 에지만 규격을 물리므로, 켜 둔 채로 두거나 창 밖에서 보내면 아무 일도 안 일어난다.

    한 자재에 한 번만 보낸다. 자재가 나가야 다음 자재를 받는다.
    """

    class Step(StrEnum):
        """지금 무엇을 기다리는가."""

        OFF = "off"      # 센서 측정 모드다. 할 일이 없다
        WAIT = "wait"    # 자재를 기다린다
        SCAN = "scan"    # 자재가 들어왔다. 읽는 중이다
        SENT = "sent"    # 보냈다. 자재가 나갈 때까지 쉰다

    communication: "Config.Communication"  # 통신 규격 통째 — QR 규격(`plc_qr`)을 키 경로로 읽는다
    step: "QrSort.Step"
    code: str | None = None  # 이번 자재의 규격. 아직 못 읽었으면 비어 있다
    previous: str | None = None  # 직전 자재의 규격
    _reader: Any = None

    def __init__(self, communication: "Config.Communication") -> None:
        self.communication = communication
        self.step = self.Step.OFF

    def advance(self, reading_qr: bool, entered: bool) -> "QrSort.Step":
        """설비 사실 둘로 다음 단계를 정한다.

        `reading_qr` :: 참이면 QR 판독 모드, 거짓이면 센서 측정 모드
        `entered`    :: 자재가 측정부에 들어와 있는가

        **둘을 어디서 읽는지는 여기가 모른다.**
        부르는 쪽이 건넨다.
        사실 둘을 인자로 받으면 못 건네는 쪽이 터지므로 모르고 지나갈 수 없다.

        이 둘을 무엇으로 읽을지는 래더가 정하고 Config 가 어떻게 들지는 미정이다.
        """
        if not reading_qr:
            self.step = self.Step.OFF
        elif not entered:
            if self.step is not self.Step.WAIT and self.code is not None:
                self.previous, self.code = self.code, None
            self.step = self.Step.WAIT
        elif self.step in (self.Step.OFF, self.Step.WAIT):
            self.step = self.Step.SCAN
        return self.step

    def judge(self, frame) -> "Tool.JsonNode | None":
        """한 장에서 규격을 읽는다. QR 이 없거나 모르는 문자열이면 `None`.

        한 번 정해진 규격은 자재가 나갈 때까지 유지한다.
        래더도 자재가 빠질 때 소거하고, 같은 자재를 여러 장 보는 동안 한 장이 흐리다고 판정이 풀리면 안 된다.
        """
        if self._reader is None:
            self._reader = cv2.QRCodeDetector()
        text, points, _ = self._reader.detectAndDecode(frame)
        if points is None or not text:
            return None
        code = self.communication.plc_qr.code(text)
        if code is not None:
            self.code = code
        return code

    def announce(self, code) -> None:
        """규격 하나를 세웠다 내린다. 켜 두면 다음 자재의 에지가 안 생긴다.

        **켜고 · 기다리고 · 끄는 차례는 여기가 든다.**
        라이브러리는 한 번 쓰는 법만 알고 몇 초를 세워 둘지는 모른다.
        부르는 스레드가 `plc_qr.pulse__s` 동안 붙들리므로 워커 안에서 부른다 — 화면 스레드에서 부르면 창이 그만큼 언다.

        아직 부르는 곳이 없다. 자재가 측정부에 있는 창을 누가 감시하는지가 안 정해졌다.
        """
        one = Connect.Device.PLC.Data.LS.Device(code.device)
        one.value = 1
        time.sleep(self.communication.plc_qr.pulse__s)
        one.value = 0
        self.step = self.Step.SENT


# ------------------------------------------------------------ PLC 읽기 (초안)

class PlcRead:
    class AddressRule:
        class Type(IntEnum):
            FLAGS_GUIDE = 0
            FLAGS_ALM_SYS = 1
            FLAGS_ALM_UNIT = 2
            ALM_RAW_TOTAL = 20
            ALM_WARN_TOTAL = 21
            ALM_ERR_TOTAL = 22
            ALM_SUMMARY_WORD = 23
            SUMMARY = 24
            Safety = 25
            Mode = 26
            State = 27
            SEQ_컨베어 = 29
            SEQ_분류기 = 30

            @nonmember
            class SpecialBit(IntEnum):
                SIG_GET_CHK_L0 = 10 * 16 + 0x4
                FLAG_DetectMode_QR = 200 * 16 + 0x4

        class Bits:
            class Guide(Flag):
                UTIL_NOT_RDY = auto()
                MOTOR_NOT_RDY = auto()
                DOOR_OPEN = auto()
                BOX_MISSING = auto()
                CYL_NOT_RET = auto()
                SEQ_NOT_CLR = auto()
                CV_SEN_NOT_OFF = auto()
                FIFO_NOT_CLR = auto()
                TOSS_NOT_CLR = auto()

            class Alarm_Sys(Flag):
                WARN_SYS_RUNTIME_OVER = auto()
                WARN_SYS_TACT_DELAY = auto()
                WARN_SYS_LUBRICANT_LOW = auto()
                WARN_SYS_AIR_DROP = auto()

            class Alarm_Unit(Flag):
                WARN_TARGET_QTY_REACH = 1 << 0
                WARN_TARGET_QTY_OVER = 1 << 1
                WARN_NO_OUTLET_BOX = 1 << 2
                ERR_Z_AXIS_SENSOR_DUAL = 1 << 6
                ERR_Y_AXIS_SENSOR_DUAL = 1 << 7
                ERR_CYCLE_TIMEOUT = 1 << 8
                ERR_ARRIVE_TIMEOUT = 1 << 9
                ERR_DIMENSION_NG = 1 << 10
                ERR_UNEXPECTED_ENTRY = 1 << 11
                ERR_TRACKING_MISMATCH = 1 << 12

            class Seq_컨베어(Flag):
                길이측정 = 1 << 1
                측정부 = 1 << 2
                QR판독 = 1 << 3

            class Seq_분류기(Flag):
                배출부1 = 1 << 1
                배출부2 = 1 << 2
                배출부3 = 1 << 3

            class Summary_Word(Flag):
                GUIDE_EXIST = auto()
                WARN_EXIST = auto()
                ERR_EXIST = auto()

            class Summary(Flag):
                LanBusy = auto()

        class Codes:
            class Unit(IntEnum):
                INSP = 0
                REJ1 = 1
                PASS = 2
                REJ2 = 3
                ULD = 4

            class Safety(IntEnum):
                INITIALIZING = 0
                SAFE = 1
                EMERGENCY = 2

            class Mode(IntEnum):
                AUTO = 0
                MANUAL = 1

            class State(IntEnum):
                IDLE = 0
                READY = 1
                RUN = 2
                DRAIN = 3
                FAULT = 4
                RESET = 5
                JOG = 6
                PAUSE = 7

        TABLE: dict = {Type.FLAGS_GUIDE: Bits.Guide, Type.FLAGS_ALM_SYS: Bits.Alarm_Sys,
                       Type.FLAGS_ALM_UNIT: Bits.Alarm_Unit, Type.ALM_RAW_TOTAL: Bits.Alarm_Unit,
                       Type.ALM_WARN_TOTAL: Bits.Alarm_Unit, Type.ALM_ERR_TOTAL: Bits.Alarm_Unit,
                       Type.ALM_SUMMARY_WORD: Bits.Summary_Word, Type.SUMMARY: Bits.Summary,
                       Type.SEQ_컨베어: Bits.Seq_컨베어, Type.SEQ_분류기: Bits.Seq_분류기,
                       Type.Safety: Codes.Safety, Type.Mode: Codes.Mode, Type.State: Codes.State}

    @staticmethod
    def survey(start: str) -> dict:
        """시작 워드에서 한 번에 긁어 Type 마다 푼다. 왕복 한 번이다."""
        LS = Connect.Device.PLC.Data.LS
        R = PlcRead.AddressRule
        head = LS.Device(start)
        words = LS.relay(head, count=max(R.Type) + 1)

        def read(one: "PlcRead.AddressRule.Type", at: int = 0):
            return R.TABLE[one](words[int(one) + at])

        out = {one: read(one) for one in R.Type if one is not R.Type.FLAGS_ALM_UNIT}
        out[R.Type.FLAGS_ALM_UNIT] = {
            unit: read(R.Type.FLAGS_ALM_UNIT, int(unit)) for unit in R.Codes.Unit}
        return out

    @staticmethod
    def loose() -> dict:
        """워드 밖에 흩어진 낱개 코일. 서로 멀어 한 번에 못 긁는다.

        `SpecialBit` 이 절대 비트 자리를 들고 있으므로 글자와 함께 표기로 되돌려 읽는다.
        """
        LS = Connect.Device.PLC.Data.LS
        out = {}
        for one in PlcRead.AddressRule.Type.SpecialBit:
            word, at = divmod(int(one), LS.plc_ls.word_bits)
            out[one] = bool(LS.Device(f"M{word}{at:X}").value)
        return out

    @staticmethod
    def is_feed_permitted(reading: dict) -> bool:
        """투입 허가 :: 측정부 시퀀스가 원점으로 돌아왔는가 (래더 D00049.2). `reading` 은 `survey` 가 푼 한 벌이다."""
        return PlcRead.AddressRule.Bits.Seq_컨베어.측정부 in reading[PlcRead.AddressRule.Type.SEQ_컨베어]
