"""로봇 계통 알고리즘 — 동작 절차와 흡착 음향 판정.

**두 덩이가 한 파일에 산다.**
소속이 같고 한 흐름이기 때문이다 — 흡착을 지령하는 것과 붙었는지 소리로 확인하는 것은 나뉘어 있을 까닭이 없다.
다만 **성격이 다르니 섞지 않는다.**

    RobotBus       시리얼을 독점하는 워커. 큐로 일을 받고 스레드를 돌린다
    VacuumSound    관측 한 벌을 받아 이름을 내는 변환기. 스레드도 장치도 모른다
    VacuumEar      마이크를 독점하는 워커. 소리와 지령을 함께 읽어 슬롯에 놓는다

**워커 둘을 한 스레드에 넣지 않는다.**
시리얼 폴링과 오디오 블록은 주기가 달라 섞으면 둘 다 망가진다.
`VacuumSound` 가 변환기로 따로 서 있는 것도 같은 까닭이다 — 장치를 모르므로 녹음 파일로도 그대로 돌려볼 수 있고, 그래서 채점기와 뷰어가 같은 경로를 탄다.

화면을 모른다. 일은 큐로 받고 결과는 `Tool.Slot` 과 사건 큐로 낸다.
"""
from __future__ import annotations

import queue
import threading
import time
from enum import Enum
from typing import Any, NamedTuple

from com_lib_core import Config, Connect, Entity, Tool


# =========================================================================
# 1. 동작 절차 — 시리얼을 독점하는 워커
# =========================================================================

# 연결 · 조그 · 호밍 · 공압 · 정지 · 상태 폴링.
# 화면을 모른다 — 일은 큐로 받고 결과는 `Tool.Slot` 과 사건 큐로 낸다.
# 시리얼은 이 워커 하나가 독점한다.
#
# 명령 낱말과 축 순서는 `communication.json` 의 `robot_serial.gcode` 가 든다.
# 이 파일은 그 낱말을 엮어 한 줄을 만든다.


class RobotBus:
    """로봇 시리얼을 독점하는 워커.

    컨트롤러는 GRBL 방언을 쓴다.
    한 줄 보내고 종결자가 보이면 즉시 돌아온다 — 상태 보고는 `>` 로 끝나고 나머지는 `ok` 로 끝난다.
    고정 시간을 기다리면 응답이 빨라도 그 시간을 다 쓰게 되어 상태 폴링이 통째로 느려진다.

    호밍 전에는 `Alarm` 으로 답하고 이동 명령을 거부한다. 그것이 정상 응답이다.
    """

    class Job(Enum):
        """맡길 수 있는 일. `submit` 이 받는 낱말은 이것이 전부다."""

        CONNECT = "connect"
        DISCONNECT = "disconnect"
        STATUS = "status"
        MOVE = "move"            # legs — `Config.Robot.Route` 가 푼 다리 목록
        HOME = "home"            # robot
        AIR = "air"              # level · label
        STOP = "stop"            # what
        LINE = "line"            # text — 사람이 친 줄을 그대로 보낸다
        CYCLE = "cycle"          # sighting · robot · speed
        COLLECT = "collect"      # points · robot · speed · look · note · finish · more · regrab · snap · reference_scene — 아핀 대응점 수집

    class Stop(Enum):
        """`Job.STOP` 이 싣는 멈추는 방식."""

        HOLD = "hold"            # 지금 이송만 멈춘다. 이어서 간다
        RESUME = "resume"        # 멈춘 이송을 이어 간다
        UNLOCK = "unlock"        # 호밍 전 · 리셋 뒤의 알람을 푼다

    class Sighting(NamedTuple):
        """`Job.CYCLE` 이 싣는 블록 하나 — 비전이 낸 것이다. 픽업이 필요로 하는 전부다.

        **이미 로봇 기저 좌표다.**
        화소에서 mm 평면으로, 다시 로봇 기저로 옮기는 일은 비전 쪽이 끝내고 건넨다 (`Config.VisionAlgorithm.homography` · `affine`).
        손목 각도 둘도 `Config.Robot` 이 접어 놓은 지령각이다 (`wrist_angle_deg` · `place_wrist_deg`).
        """

        x_mm: float
        y_mm: float
        wrist_deg: float  # 물 때의 손목 지령각. 손목이 장축에 맞는다
        place_wrist_deg: float  # 투입점에 놓을 때의 손목 지령각. 장축이 벨트 진행 방향을 따른다

    #: 큐를 건너뛰고 바로 보내도 되는 낱말.
    #: 실시간 문자라 수신 인터럽트가 곧바로 처리하며, 줄 단위 프로토콜을 깨지 않는다.
    #: 그 밖은 줄 명령이라 워커 큐로 돌린다.
    IMMEDIATE = (Stop.HOLD, Stop.RESUME)

    communication: "Config.Communication"  # 통신 규격(`communication.json`) 통째 — 시리얼 규격과 명령 낱말을 키 경로로 읽는다(`communication.robot_serial.gcode`)
    route: "Config.Robot.Route"  # 어디로 갈지를 푸는 쪽. 부르는 쪽이 이것으로 다리를 만들어 `Job.MOVE` 에 싣는다
    robot: "Config.Robot"  # 로봇 규격(`robot.json`) — 공압 정지 지령(`motion.pneumatics_pwm.idle`)을 여기서 읽는다. `to_idle` 이 부르는 쪽 없이 스스로 정리 상태로 가야 하므로 생성자에서 받아 든다
    status: Tool.Slot  # `RobotStatus`. 아직 못 받았거나 연결을 닫았으면 `None`
    events: queue.Queue
    connected: Tool.Slot
    firmware: Tool.Slot
    busy: Tool.Slot  # 일감 하나를 맡아 하는 중이다. 사이클 · 수집처럼 팔이 움직이는 동안 참이라 그동안 판정 루프가 관측을 쉰다
    hearing: "Tool.Slot | None" = None  # 흡착 판정 슬롯(`VacuumEar.heard`). 마이크가 열리면 부르는 쪽이 꽂는다. 비어 있으면 무는 동작이 닿은 뒤 진공 체결 대기만큼 쉰다
    link: Connect.Device.Robot
    _jobs: queue.Queue
    _shutdown: threading.Event
    _thread: threading.Thread

    def __init__(self, comm: "Config.Communication", robot: "Config.Robot",
                 route: "Config.Robot.Route"):
        self.communication = comm
        self.route = route
        self.robot = robot
        self.status = Tool.Slot()
        self.events = queue.Queue()
        self.connected = Tool.Slot(False)
        self.firmware = Tool.Slot("")
        self.busy = Tool.Slot(False)
        self._jobs = queue.Queue()
        self.link = Connect.Device.Robot(comm.robot_serial)
        self._shutdown = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    # ---------------------------------------------------------- 바깥 창구

    def start(self) -> None:
        self._thread.start()

    def submit(self, job: "RobotBus.Job", **payload) -> None:
        """워커에 일을 맡긴다. 화면 스레드는 이것만 부른다.

        바깥 인자를 `job` 으로 두는 것은 실어 보내는 값에 `kind` 가 있기 때문이다 — 같은 이름이면 키워드가 부딪혀 호출이 아예 안 선다.
        """
        self._jobs.put((job, payload))

    def shutdown(self) -> None:
        self._shutdown.set()

    def halt_now(self, what: "RobotBus.Stop") -> None:
        """정지 · 재개를 **큐를 건너뛰고 지금 보낸다.** 화면 스레드가 부른다.

        이동 중에는 워커가 `_wait_idle` 안에 잡혀 있어 작업 큐가 돌지 않는다.
        정지를 큐에 넣으면 이동이 끝난 뒤에야 처리되어 **정지의 뜻이 사라진다.**

        `IMMEDIATE` 만 이 길로 보낸다. 줄 명령은 워커의 줄 쓰기와 섞이면 안 되므로 큐로 돌린다.
        """
        if what not in self.IMMEDIATE:
            self.submit(self.Job.STOP, what=what)
            return
        self._halt(what)

    def to_idle(self, why: str) -> None:
        """공압을 끊고 컨트롤러를 쉬는 상태로 되돌린다. 정리는 이 길 하나다.

        예외가 나서 정리하든 사람이 해제를 눌러 정리하든 같은 일을 한다.

        끊는 것은 공압뿐이다.
        가던 이송은 마저 간다 — 명령 버퍼를 비우려면 소프트 리셋을 보내야 하는데 그것이 컨트롤러를 `Offline` 으로 떨군다.
        피드홀드도 안 건다.
        걸어 두면 `Hold` 로 물려 다음 연결이 줄 명령을 못 넣는다.

        이송이 사람을 위협하지 않는 근거는 설비 사정이다 — 제어가 간섭 위치로 보내지만 않으면 된다.
        **다른 설비로 옮기면 이 판단부터 다시 한다.**
        """
        self._say(f"정리한다 :: {why}")
        self._pneumatic(int(self.robot.motion.pneumatics_pwm.idle), 0.0, "  공압 차단", self._say)

    @staticmethod
    def next_sighting(seen, robot: "Config.Robot") -> tuple[Any, str]:
        """관측 한 벌에서 다음에 집을 블록 — ((지령, 개체), "") 이거나 (None, 못 집는 까닭).

        관측된 차례(꼬리표)가 가장 이른 것을 집는다.
        규격이 잡히지 않은 개체는 집지 않고, 집을 수 없는 자리(`Config.Robot.can_pick` — 가동범위 밖이거나 팔이 안 닿는다)의 개체는 건너뛴다 — 못 닿는 블록을 붙들면 다음 블록도 못 집는다.
        좌표는 그 관측을 낸 계산의 좌표 변환이 옮기고(`Calc.Pipe.Review.Global.question_position`), 손목은 기구 규격이 그 계산의 아핀 값을 받아 접는다.
        """
        affine = seen.calc.era_values.affine
        if affine.matrix is None:
            return None, "현행 값에 아핀이 없다 — 준비 탭 ③"
        try:
            if not robot.reach_bands_mm:
                return None, "팔이 픽업 · 이송 · 안전 고도에 모두 닿는 반경이 없다"
        except Tool.Missing as missing:
            return None, f"팔이 닿는 곳을 셀 수 없다 :: {missing}"
        for piece in sorted((one for one in seen.pieces if one.is_spec_resolved), key=lambda one: one.tag):
            x_mm, y_mm = seen.calc.scope_global.question_position(piece, affine)
            if not robot.can_pick(x_mm, y_mm):
                continue
            pick_deg = robot.wrist_angle_deg(affine, piece.pose.angle_deg, piece.block)
            long_axis_deg = robot.vision_algorithm.affine_transform.to_robot_deg(affine, piece.pose.angle_deg)
            return (RobotBus.Sighting(x_mm, y_mm, pick_deg, robot.place_wrist_deg(piece.block, pick_deg, long_axis_deg)), piece), ""
        return None, "집을 수 있는 곳에 규격이 잡힌 블록이 없다"

    # ------------------------------------------------------------ 워커 안

    def _say(self, text: str) -> None:
        self.events.put(Tool.Event(text, time.monotonic()))

    def _run(self) -> None:
        last_poll = 0.0
        while not self._shutdown.is_set():
            try:
                job, payload = self._jobs.get(timeout=self.communication.robot_serial.request_wait__s)
            except queue.Empty:
                if self.link.is_open and time.monotonic() - last_poll >= self.communication.robot_serial.status_poll__s:
                    last_poll = time.monotonic()
                    try:
                        self._read_status()
                    except OSError as exc:
                        self._lost(exc)
                continue
            self.busy.put(True)
            try:
                self._handle(job, payload)
            except OSError as exc:
                self._lost(exc)
            except Exception as exc:                      # noqa: BLE001
                self._say(f"{job} 처리 중 문제가 생겼다 :: {exc}")
                self.to_idle("처리 중 예외")
            finally:
                self.busy.put(False)
        self._close()

    def _lost(self, exc: OSError) -> None:
        """포트를 잃었다. 포트를 놓고 `connected` 를 내려 화면이 끊김 띠를 띄우게 한다. 다시 붙이는 것은 사람이다.

        케이블이 빠지면 pyserial 이 `SerialException`(`OSError` 의 하위)을 낸다.
        공압 차단(`to_idle`)은 같은 포트를 타므로 여기서 부르지 않는다.
        """
        self._say(f"로봇 포트를 잃었다 :: {exc}")
        self._close()

    def _handle(self, job: "RobotBus.Job", payload: dict) -> None:
        if job == self.Job.CONNECT:
            self._connect()
        elif job == self.Job.DISCONNECT:
            #: 포트만 놓으면 공압이 켜진 채 남는다 — 사람이 끊었다고 여긴 뒤에도 설비가 문다
            self.to_idle("연결을 끊는다")
            self._close()
            self._say("연결을 끊었다")
        elif job == self.Job.STATUS:
            self._read_status()
        elif job == self.Job.MOVE:
            self._move(payload["legs"])
        elif job == self.Job.HOME:
            self._home(payload["robot"])
        elif job == self.Job.AIR:
            self._air(payload["level"], payload["label"])
        elif job == self.Job.STOP:
            self._halt(payload["what"])
        elif job == self.Job.LINE:
            self._line(payload["text"])
        elif job == self.Job.CYCLE:
            self._cycle(payload["sighting"], payload["robot"], payload["speed"])
        elif job == self.Job.COLLECT:
            self._collect(payload["points"], payload["robot"], payload["speed"],
                          payload["look"], payload["note"], payload["finish"], payload["more"], payload["regrab"], payload["snap"], payload["reference_scene"])

    def _connect(self) -> None:
        """포트를 열고, **컨트롤러가 줄 명령을 받는지 확인한 뒤에만** 연결로 친다.

        포트가 열린 것과 컨트롤러가 명령을 받는 것은 다른 사실이다.
        이 설비에는 같은 CH340 칩(`1A86:7523`)을 쓰는 장치가 여럿이라(컨트롤러 · 확장 박스) VID/PID 로 갈리지 않고, 컨트롤러의 줄 파서가 막혀 있어도 포트는 열린다.
        둘 다 `?` 에는 그럴듯한 상태를 돌려주므로 실시간 문자로는 못 가른다.
        가르는 것은 **줄 명령의 접수 낱말**이다.
        """
        self._close()
        try:
            banner = self.link.connect()
        except LookupError as exc:
            self._say(str(exc))
            return
        except Exception as exc:                          # noqa: BLE001
            self._say(f"포트를 열지 못했다 :: {exc}")
            return

        if self.communication.robot_serial.gcode.ack.lower() not in banner.lower():
            self._diagnose_mute(banner)
            self._close()
            return

        self.connected.put(True)
        lines = banner.strip().splitlines()
        self.firmware.put(lines[0] if lines else "")
        self._say(f"연결됨 :: {self.link.port}")
        self._read_status()

    def _diagnose_mute(self, banner: str) -> None:
        """줄 명령에 답이 없을 때 무엇이 잘못인지 갈라 말한다.

        두 고장이 같은 얼굴을 한다. 가르는 것은 **상태 조회가 되느냐**다 ::

        1. 상태 조회도 안 되면 :: 이 포트에 컨트롤러가 없다. 같은 칩을 쓰는 다른 장치다
        2. 상태 조회는 되는데 줄만 안 되면 :: 컨트롤러는 살아 있고 줄 파서가 막혔다.
           실시간 문자는 수신 인터럽트가 곧바로 처리하지만 줄은 수신 버퍼를 거치는데, 그 버퍼가 차서 안 비워지면 새 줄이 조용히 버려진다.
           **베이스의 물리 RESET 으로만 푼다** — 소프트 리셋은 컨트롤러를 `Offline` 으로 떨군다
        """
        self._say(f"{self.link.port or '포트'} :: 줄 명령에 응답이 없다 "
                  f"(`$I` -> {banner.strip()[:40] or '없음'})")
        alive = self.link.status()
        if alive is None:
            self._say("  상태 조회도 안 된다. 이 포트에 로봇 컨트롤러가 없다")
            self._say("  같은 CH340 칩을 쓰는 다른 장치일 수 있다 (확장 박스 · 블루투스 박스)")
            return
        self._say(f"  그런데 상태 조회는 된다 :: {alive.state}")
        self._say("  → 컨트롤러는 살아 있고 줄 파서만 막혔다. 통신 방식을 바꾸면 이렇게 된다")
        self._say("  → 베이스 위 RESET 버튼을 누르고, 호밍한 뒤 다시 연결한다")

    def _close(self) -> None:
        self.link.close()
        self.connected.put(False)
        self.status.put(None)

    # -------------------------------------------------------- 명령 보내기

    def _wait_idle(self) -> "Connect.Device.Robot.Status | None":
        """이동이 끝날 때까지 상태를 본다. 움직이는 상태(`Config.Communication.RobotSerial.moving_states`)가 사라지면 끝난 것이다. 상한을 넘기면 마지막 보고를 그대로 낸다."""
        deadline = time.monotonic() + self.communication.robot_serial.motion_wait__s
        last = None
        while time.monotonic() < deadline:
            last = self.link.status() or last
            if last is not None:
                self.status.put(last)
                if not self.communication.robot_serial.is_moving(last.state):
                    return last
            time.sleep(self.communication.robot_serial.motion_poll__s)
        self._say("이동이 제 시간에 끝나지 않았다. 기다리기를 그만둔다")
        return last

    def _wait_settled(self, settle_s: float, limit_s: float) -> "Connect.Device.Robot.Status | None":
        """움직이는 상태(`Config.Communication.RobotSerial.moving_states`)가 사라지고 자리가 `settle_s` 동안 그대로인 것을 본다. 그 사이 다시 움직이면 처음부터 센다. 상한을 넘기면 마지막 보고를 낸다."""
        deadline = time.monotonic() + limit_s
        still, since = None, 0.0
        while time.monotonic() < deadline:
            seen = self.link.status()
            if seen is not None:
                self.status.put(seen)
                moving = self.communication.robot_serial.is_moving(seen.state)
                if moving or still is None or tuple(seen.cartesian) != tuple(still.cartesian):
                    still, since = (None if moving else seen), time.monotonic()
                elif time.monotonic() - since >= settle_s:
                    return seen
            time.sleep(self.communication.robot_serial.motion_poll__s)
        self._say("이동이 제 시간에 끝나지 않았다. 기다리기를 그만둔다")
        return self.status.get()

    def _move(self, legs: tuple) -> bool:
        """다리를 차례로 낸다. 어디로 갈지는 `Config.Robot.Route` 가 이미 풀었다 — 여기는 줄로 옮긴다. 다리를 다 냈으면 참이다.

        **앞 다리가 실패하면 뒤를 안 낸다.**
        안전 고도로 못 올라갔는데 가로로 밀면 기구를 때린다.
        멈춘 자리를 사람에게 알린다.
        접수됐어도 멈춘 것을 못 봤거나 목표에 닿지 않았으면 실패다(`Config.Robot.Route.missed`).

        상대(`G91`)로 보냈으면 **반드시 절대(`G90`)로 되돌린다.**
        상대 모드가 남으면 다음 절대 명령이 지금 자리에 더해져 엉뚱한 곳으로 간다.
        """
        before = self.status.get()
        if self.link.is_alarm(before):
            self._say("호밍 전이라 이동 명령이 거부된다. 먼저 호밍한다")
            return False

        code = self.communication.robot_serial.gcode
        for order, leg in enumerate(legs, 1):
            head = code.cartesian_mode if leg.kind is Config.Robot.Route.Kind.CART else code.angle_mode
            body = " ".join(f"{name}{value:.3f}"
                            for name, value in zip(code.command_axes, leg.axes))
            mode = code.relative if leg.relative else code.absolute
            was = self.status.get()
            verdict, raw = self.link.send(f"{head} {mode} {code.linear} {body} "
                                          f"{code.feed_prefix}{int(leg.speed)}")
            if leg.relative:
                self.link.send(f"{head} {code.absolute}")
            if verdict != "ok":
                self._say(f"{order} 번째 다리에서 멈췄다 ({verdict}) :: "
                          f"{raw.strip()[:80] or '응답 없음'}")
                return False
            after = self._wait_idle()
            self._report_leg(leg, was, after)
            if after is None or self.communication.robot_serial.is_moving(after.state):
                self._say(f"{order} 번째 다리가 끝난 것을 보지 못했다 :: "
                          + ("상태를 읽지 못했다" if after is None else f"상태 {after.state}"))
                return False
            missed = self.route.missed(leg, after)
            if missed:
                here = self.route.at(leg.kind, after)
                offsets = self.route.bias.offset_mm
                names = Config.Robot.Route.AXIS_NAMES[leg.kind]
                self._say(f"{order} 번째 다리가 목표에 닿지 않았다 :: " + " · ".join(
                    f"{names[axis]} 목표 {leg.axes[axis] - (offsets[axis] if axis < len(offsets) else 0.0):.2f} · 보고 {here[axis]:.2f}"
                    for axis in missed))
                return False
        return True

    def _report_leg(self, leg, before: "Connect.Device.Robot.Status | None",
                    after: "Connect.Device.Robot.Status | None") -> None:
        """이 다리가 실제로 움직인 양을 알린다. 접수 응답만으로는 움직였는지 모른다."""
        old = self.route.at(leg.kind, before)
        new = self.route.at(leg.kind, after)
        if old is None or new is None:
            self._say("좌표를 읽지 못해 이동량을 확인할 수 없다")
            return
        names = Config.Robot.Route.AXIS_NAMES[leg.kind]
        for axis in leg.moves:
            unit = "mm" if Config.Robot.Route.is_mm_axis(leg.kind, axis) else "도"
            self._say(f"{names[axis]} {old[axis]:.2f} -> {new[axis]:.2f} {unit} "
                      f"(움직인 양 {new[axis] - old[axis]:+.2f})")

    def _leg(self, plan_of, what: str, note) -> bool:
        """다리를 그때 풀어 낸다. 다리를 다 내고 목표에 닿았으면 참이다(`_move`).

        **계획을 여기서 세운다.** 미리 다 세우면 앞 다리가 움직이기 전 좌표로 뒤를 센다 — 그래서 계획 대신 계획을 푸는 함수(`plan_of`)를 받는다.
        `note(글)` 은 그 일감이 단계를 알리는 길이다 — 사이클 · 호밍은 화면(`_say`), 대응점 수집은 수집 기록(`Calibration.Collector.note`).
        """
        plan = plan_of()
        if plan.refused:
            note(f"{what} 못 함 :: {plan.refused}")
            return False
        note(what)
        if self._move(plan.legs):
            return True
        note(f"{what} — 멈췄다")
        return False

    def _pneumatic(self, level: int, dwell_s: float, what: str, note) -> bool:
        """공압 채널에 PWM 을 준다. 접수됐으면 `dwell_s` 쉬고 참이다 — 안 되면 까닭을 알린다(`note`, `_leg` 와 같은 길).

        흡기와 파기가 한 채널을 공유한다.
        상태 보고는 PWM 을 둘(`Pump` · `Valve`) 내지만 **첫째만 쓴다.**
        둘째를 미는 낱말이 명령집에 없고, 이 설비는 공압 박스가 하나뿐이라 둘째 채널이 필요하지도 않다.
        """
        verdict, raw = self.link.send(f"{self.communication.robot_serial.gcode.pneumatic_prefix}{int(level)}")
        if verdict != "ok":
            note(f"{what} — 공압 명령이 통하지 않았다 ({verdict}) :: {raw.strip()[:70] or '응답 없음'}")
            return False
        note(what)
        time.sleep(dwell_s)
        return True

    # ------------------------------------------------- 물기 · 놓기

    # 사이클 · 대응점 수집 · 호밍이 함께 쓰는 동작이다. 어느 바닥에서 무는지(`Config.Robot.Surface`)와 그 일감만의 판단은 부르는 쪽이 인자로 준다.

    def _grab(self, what: str, surface: "Config.Robot.Surface", wrist_deg: float, lift_z_mm: float,
              robot: "Config.Robot", speed: int, note, *, lift_unheard: bool) -> bool:
        """그 바닥(`surface`)의 블록을 물어 `lift_z_mm` 까지 든다. 들었으면 참이다 — 부르는 쪽은 블록 위 안전 고도에 와 있다.

        차례 ::
        1. 진공 켤 고도(`Surface.vacuum_z_mm`)까지 내리며 손목을 `wrist_deg` 로 맞춘다 — 따로 돌리고 내리면 오래 걸린다
        2. 진공을 켜고 무부하 회전을 듣는다. 닿기 전에 못 들으면 닿은 뒤의 부하 걸린 회전이 기준이 되어 붙어도 무부하로 읽힌다
        3. 무는 고도로 내려가 붙음을 듣는다(상한 `Timings.grip_wait__s`). 못 들으면 더 누르는 고도(`Surface.retry_z_mm`)에서 한 번 더 듣는다
        4. 든다
        붙음을 끝내 못 들으면 `lift_unheard` 가 정한다 — 참이면 그래도 든다(대응점 수집 — 소리 판정은 약한 흡착을 놓치고, 못 문 것은 다음 관측이 가린다).
        거짓이면 블록을 두고 올라온다(사이클 — 거친 면의 리크는 더 눌러도 안 들리니 포기하고 다음 블록으로 간다).
        무부하 회전을 못 듣거나 무는 고도에 못 내려가도 블록을 두고 올라온다 — 공압을 끄고 안전 고도로 오른다. 들어올리지 못하면 공압을 끄고 블록을 그 자리에 둔다.
        소리는 펌프가 무부하로 돈 회전을 기준으로 부하를 잰다(`VacuumSound`).
        들을 슬롯(`hearing`)이 비어 있으면 무부하는 들은 것으로 두고, 닿은 뒤 진공 체결 대기(`Timings.vacuum_dwell__s`)만큼 쉬어 붙은 것으로 둔다 — 붙었는지는 다음 관측이 말한다.
        """
        heights, timings, pneumatics = robot.motion.heights, robot.motion.timings, robot.motion.pneumatics_pwm

        def heard_text() -> str:
            """흡착 판정이 마지막으로 본 값 — 단계 알림에 붙인다. 들을 슬롯이 비었거나 읽은 값이 없으면 빈 글이다."""
            heard = None if self.hearing is None else self.hearing.get()
            if heard is None or heard.reading is None:
                return ""
            reading = heard.reading
            return (f" · 부하비 {reading.load_ratio:.3f} · 기준 {reading.reference_hz:.1f} Hz · 회전 {reading.rotation_hz:.1f} Hz"
                    f" · 판정 {reading.target or '—'}")

        def heard_unloaded() -> bool:
            """판정 기준(그 가동에서 본 가장 빠른 회전)이 무부하 범위 아래끝 이상으로 서는 것을 상한까지 본다."""
            if self.hearing is None:
                return True
            deadline = time.monotonic() + timings.grip_wait__s
            while time.monotonic() < deadline:
                heard = self.hearing.get()
                if heard is not None and heard.reading is not None and heard.reading.reference_hz >= robot.acoustic.pump.unloaded_rotation__hz[0]:
                    return True
                time.sleep(self.communication.robot_serial.motion_poll__s)
            return False

        def gripped() -> bool:
            """지금 뒤의 소리가 붙음을 말하는 것을 상한까지 본다."""
            since = time.monotonic()
            if self.hearing is None:
                time.sleep(timings.vacuum_dwell__s)
                return True
            while time.monotonic() < since + timings.grip_wait__s:
                heard = self.hearing.get()
                if heard is not None and heard.at > since and heard.gripped:
                    return True
                time.sleep(self.communication.robot_serial.motion_poll__s)
            return False

        def leave(why: str) -> bool:
            """블록을 두고 올라온다 — 공압을 끄고 안전 고도로. 들지 않았으므로 늘 거짓이다."""
            note(f"{what} — {why}")
            if self._pneumatic(pneumatics.level(pneumatics.State.IDLE), timings.settle_dwell__s, f"{what} — 공압 끔", note):
                self._leg(lambda: self.route.height(heights.z_safe.z__mm, speed, self.status.get()), f"{what} — 블록을 두고 올라가기", note)
            return False

        if not (self._leg(lambda: self.route.height_turned(surface.vacuum_z_mm, wrist_deg, speed, self.status.get()),
                          f"{what} — 진공 켤 고도로 내리며 손목 맞추기", note)
                and self._pneumatic(pneumatics.level(pneumatics.State.VACUUM), 0.0, f"{what} — 진공", note)):
            return False
        if not heard_unloaded():
            return leave(f"진공을 켜고 {timings.grip_wait__s:.1f} 초 안에 무부하 회전을 못 들었다{heard_text()}")
        if not self._leg(lambda: self.route.height(surface.grip_z_mm, speed, self.status.get()), f"{what} — 닿기", note):
            return leave("무는 고도에 못 내려갔다")
        heard = gripped()
        if not heard and self._leg(lambda: self.route.height(surface.retry_z_mm, speed, self.status.get()),
                                   f"{what} — 붙음을 {timings.grip_wait__s:.1f} 초 안에 못 들어 더 누르기{heard_text()}", note):
            heard = gripped()
        note(f"{what} — " + ("붙음" if heard else "붙음을 못 들었다") + heard_text())
        if not heard and not lift_unheard:
            return leave("블록을 두고 다음 블록으로")
        if self._leg(lambda: self.route.height(lift_z_mm, speed, self.status.get()), f"{what} — 들어올리기", note):
            return True
        self._pneumatic(pneumatics.level(pneumatics.State.IDLE), timings.settle_dwell__s, f"{what} — 못 들어 공압 끔", note)
        return False

    def _release(self, what: str, robot: "Config.Robot", note) -> bool:
        """패드에 붙은 것을 불어 떨구고 공압을 끈다 — 파기를 `Timings.blowoff_dwell__s` 동안 켠 뒤 끄고 `settle_dwell__s` 쉰다. 둘 다 접수됐으면 참이다.

        블록을 놓을 때(매트 · 투입점)와 호밍 전에 진공이 켜져 있을 때 같은 동작이다. 어느 고도에서 놓을지는 부르는 쪽이 정한다(`Surface.release_z_mm`).
        """
        pneumatics, timings = robot.motion.pneumatics_pwm, robot.motion.timings
        return (self._pneumatic(pneumatics.level(pneumatics.State.BLOWOFF), timings.blowoff_dwell__s, f"{what} — 파기", note)
                and self._pneumatic(pneumatics.level(pneumatics.State.IDLE), timings.settle_dwell__s, f"{what} — 공압 끔", note))

    # ------------------------------------------------------------ 일감

    #: 호밍이 실패했을 때 사람에게 하는 말.
    #: **전원 재투입이 정답이다** — 공식 매뉴얼이 `please reapply the power of manipulator and repeat the HOMING action` 으로 못 박았다. 그래서 여기서 자동으로 다시 걸지 않는다.
    #: 버튼은 잠그지 않는다 — 다시 눌러 봐야 안 풀릴 뿐 다치는 경로가 없다
    HOMING_FAILED = "호밍이 실패했다. 로봇 전원을 다시 넣고 호밍한다 — 다시 눌러도 안 풀린다"

    def _home(self, robot: "Config.Robot") -> None:
        """동시 호밍. 원점까지 크게 움직이므로 두 가지를 먼저 정리한다.

        1. 진공이 켜져 있으면 파기하고 끈다. 블록을 문 채 원점으로 가면 경로 어디에
           떨어질지 알 수 없다. 켜짐 여부는 상태 보고의 펌프 PWM 이 말한다
        2. 안전 높이보다 낮으면 먼저 올린다. 낮은 자세에서 접으면 경로를 예측하기 어렵다

        `o105=8` 은 여섯 축 동시 호밍이다. 축을 하나씩 부르면 없는 7축을 찾다 멎는다.
        호밍 끝은 멈춘 자리가 `Config.Communication.RobotSerial.homing_settle__s` 동안 그대로일 때다(`_wait_settled`).
        """
        heights, lift_speed = robot.motion.heights, robot.motion.home_lift_speed__mm_min
        status = self.status.get()
        if status is not None and status.pump_pwm != 0:
            self._say(f"진공이 켜져 있다 (펌프 {status.pump_pwm}). 파기하고 끈다")
            if not self._release("호밍 전", robot, self._say):
                self._say("호밍하지 않는다")
                return

        if status is not None and len(status.cartesian) >= 3:
            if status.cartesian[2] < heights.z_safe.z__mm:
                self._say(f"Z {status.cartesian[2]:.2f} 가 안전 높이 "
                          f"{heights.z_safe.z__mm:.2f} 보다 낮다. 먼저 올린다")
                if not self._leg(lambda: self.route.height(heights.z_safe.z__mm, lift_speed, status), "안전 높이로 올리기", self._say):
                    self._say("안전 높이로 올리지 못했다 — 호밍하지 않는다")
                    return
        else:
            self._say("현재 좌표를 읽지 못해 사전 상승을 건너뛴다")

        self._say("동시 호밍 시작 — 끝날 때까지 기다린다")
        verdict, raw = self.link.send(self.communication.robot_serial.gcode.homing)
        if verdict != "ok":
            self._say(f"호밍 명령이 통하지 않았다 ({verdict}) :: "
                      f"{raw.strip()[:70] or '응답 없음'}")
            self._say(self.HOMING_FAILED)
            return
        started = time.monotonic()
        done = self._wait_settled(self.communication.robot_serial.homing_settle__s, self.communication.robot_serial.homing_wait__s)
        if done is None or self.link.is_alarm(done):
            self._say(self.HOMING_FAILED)
            return
        if self.communication.robot_serial.is_moving(done.state):
            self._say(f"호밍이 {self.communication.robot_serial.homing_wait__s:.0f} 초 안에 끝나지 않았다 :: 상태 {done.state} — 끝난 것을 보고 다음으로 간다")
            return
        self._say(f"호밍 끝 :: 상태 {done.state} · {time.monotonic() - started:.1f} 초")

    def _air(self, level: int, label: str) -> None:
        """사람이 고른 공압 상태를 준다(`Job.AIR`)."""
        self._pneumatic(level, 0.0, f"공압 :: {label} (PWM {level})", self._say)

    def _halt(self, what: "RobotBus.Stop") -> None:
        """멈추거나 푼다.

        **이름을 `_stop` 으로 두면 깨진다.**
        워커 종료 깃발 `_shutdown` 을 그 이름으로 되돌려도 마찬가지다 — 같은 이름의 인스턴스 속성이 메서드를 가려 호출이 서지 않는다.
        """
        if not self.link.is_open:
            return
        code = self.communication.robot_serial.gcode
        if what == self.Stop.HOLD:
            self.link.write_bytes(code.feed_hold.encode("ascii"))
            self._say("피드홀드")
        elif what == self.Stop.RESUME:
            self.link.write_bytes(code.cycle_resume.encode("ascii"))
            self._say("재개")
        elif what == self.Stop.UNLOCK:
            self.link.send(code.alarm_clear)
            self._say("알람 해제")

    def _cycle(self, sighting: "RobotBus.Sighting", robot: "Config.Robot",
               speed: int) -> None:
        """블록 하나를 집어 투입점에 놓는다.

        **말단이 그 자리에 닿기만 하면 집힌다.**
        블록은 이미 거기 놓여 있으므로 발자국이 둘레 안일 필요가 없다 — 그것은 블록을 *놓을* 때의 조건이다 (`Reach.can_seat`).

        가로 이동은 늘 안전 고도다. 내려가는 것은 무는 자리와 놓는 자리 둘뿐이다.
        무는 자리에서는 매트에서 물어(`_grab`, `Config.Robot.mat`) 이송 고도(`Config.Robot.transit_z_mm`)까지 곧게 든다.
        붙음을 끝내 못 들으면 블록을 두고 올라와 끝낸다 — 거친 면의 리크는 더 눌러도 안 들리니 포기하고 다음 블록으로 간다.
        든 뒤에는 안전 고도로 올리면서 투입 방위로 돌린다 — 이송 고도 아래에서 블록을 문 채 돌리면 이웃 블록을 칠 수 있다.
        투입점에서는 놓는 고도(`Config.Robot.conveyor`)로 내려 놓는다(`_release`).
        다리 · 공압 지령마다 끝난 것(목표에 닿음 · 접수)을 보고 다음으로 간다. 못 보면 그 자리에서 멈춘다. 단계는 화면에 알린다.

        **블록을 문 채 손목을 돌려 장축을 벨트 진행 방향에 맞춘다**.
        패드가 둥글어 어느 방위로든 물린다 — 물기 전에 손목을 장축에 맞추는 것은 블록과 손목의 상대 방위를 정해 두려는 것이고, 그래야 투입 방위로 돌린 손목이 장축을 벨트 진행 방향에 놓는다.
        """
        z_safe, note = robot.motion.heights.z_safe.z__mm, self._say

        if not robot.can_pick(sighting.x_mm, sighting.y_mm):
            self._say(f"가동범위 밖이거나 팔이 닿지 않아 못 집는다 :: "
                      f"({sighting.x_mm:.2f}, {sighting.y_mm:.2f})")
            return

        entry = robot.motion.positions.conveyor_entry
        self._say(f"사이클 시작 :: ({sighting.x_mm:.2f}, {sighting.y_mm:.2f}) "
                  f"손목 {sighting.wrist_deg:.2f}도 → 투입 {sighting.place_wrist_deg:.2f}도")

        if not (self._leg(lambda: self.route.plane((sighting.x_mm, sighting.y_mm), speed, self.status.get(), z_safe), "무는 자리로", note)
                and self._grab("블록 물기", robot.mat, sighting.wrist_deg, robot.transit_z_mm, robot, speed, note, lift_unheard=False)):
            return

        for plan_of, what in (
            (lambda: self.route.height_turned(z_safe, sighting.place_wrist_deg, speed, self.status.get()),
             "안전 고도로 올리며 투입 방위로 손목 돌리기"),
            (lambda: self.route.plane(entry.xy, speed, self.status.get(), z_safe), "투입점으로"),
            (lambda: self.route.height(robot.conveyor.release_z_mm, speed, self.status.get()), "놓는 높이로"),
        ):
            if not self._leg(plan_of, what, note):
                self.to_idle(f"{what} 에서 멈췄다")
                return

        if not (self._release("투입점에 놓기", robot, note)
                and self._leg(lambda: self.route.height(z_safe, speed, self.status.get()), "물러나기", note)):
            return
        self._say("사이클 끝")

    def _collect(self, points: tuple, robot: "Config.Robot", speed: int, look, note, finish, more, regrab, snap, reference_scene) -> None:
        """아핀 대응점 수집. 투입점의 블록을 물어 자리마다 놓고, 투입점으로 대피한 뒤 `look` 에게 보게 하고, 제자리에서 다시 문다.

        `points` 는 놓을 자리(`Config.Robot.Motion.Calibration.Point`)의 차례다.
        다 돌면 `more()` 가 다음 자리들을 준다 — 앞 자리의 관측으로 다음 자리를 정하는 쪽(비전)이 낸다.
        `more()` 가 빈 튜플이면 끝이다.
        `look(자리)` 는 팔이 대피한 채 불리고, 쓸 만한 관측이면 참이다 — 무엇을 어떻게 보는지는 비전 쪽이 안다.
        `regrab(자리)` 는 그 자리에서 다시 물 XY 를 준다 — 비전이 방금 본 블록에서 낸다.
        다시 물 자리를 집을 수 없으면(`Config.Robot.can_pick`) 멈춘다.
        `snap(이름표)` 는 지금 장면을 한 장 남긴다 — 문 채 내려놓는 높이에 닿은 순간(`<자리>_held`)과 다시 물어 든 순간(`<자리>_lifted`)이다.
        더 돌리는 각이 앞 자리와 다르면 블록을 문 채 손목을 돌린 뒤 내려놓는다.
        연속으로 `Calibration.discard_limit` 번 거짓이면 멈춘다. 끝나거나 멈추면 들고 있던 블록을 투입점에 되돌려 놓는다 — 장축을 벨트 진행 방향(`Hardware.conveyor_travel__deg`)으로 돌려 놓는다.
        놓는 자리가 조금씩 어긋나므로 장축이 벨트를 가로지르면 양옆 가이드에 걸린다. 제품을 투입할 때 돌려 넣는 것과 같은 까닭이다.
        다 돌고 블록을 되돌려 놓았으면 카메라 기준 장면 자리(`robot.motion.positions.camera_reference` — 티칭 창에서 담는다)에 그 자리의 높이(`Config.Robot.place_z_mm`) · 손목 방위로 가서 `reference_scene()` 으로 한 장 남기고 투입점 위로 다시 비킨다.
        이 아핀과 같은 때의 카메라를 같은 팔 자세로 견줄 기준 장면이다. 그 자리의 팔은 카메라에 들어 블록으로 잡힐 수 있으므로 머물지 않는다.
        물기는 `_grab`, 놓기는 `_release` 다 — 사이클과 같은 동작이다. 투입점에서는 컨베이어 투입점(`Config.Robot.conveyor`)에서 물고 놓고, 매트에서는 매트(`Config.Robot.mat`)에서 다시 물고 놓는다.
        붙음을 끝내 못 들어도 든다 — 소리 판정은 약한 흡착을 놓친다. 못 문 것은 다음 관측이 가린다(`Calibration.Collector.look`).
        이동 · 공압 지령이 끝난 것(목표에 닿음 · 접수)을 못 보면 그 자리에서 멈춘다.
        `note(글)` 은 단계마다 부르고 `finish(까닭)` 는 끝에 한 번 부른다 — 기록과 영상의 시각을 맞추는 자리다. 예외로 빠져도 부른다 — 안 부르면 화면은 수집이 끝난 줄 모른다.

        블록을 매트에 놓는 높이는 내려놓는 높이다(`Config.Robot.mat`) — 벨로즈 패드가 진공에 줄어 블록을 들고 있으므로 픽업 높이보다 아래까지 내려야 밑면이 매트에 닿는다. 떨구지 않으므로 놓은 자리가 로봇 자리다.
        가동범위 안에서 블록을 들고 옮기는 고도는 `Config.Robot.transit_z_mm` 이다. 카메라 앞을 비키는 대피와 가동범위 밖(투입점)을 오가는 길은 안전 높이다.
        """
        spec, z_safe, z_transit = robot.motion.calibration, robot.motion.heights.z_safe.z__mm, robot.transit_z_mm
        entry = robot.motion.positions.conveyor_entry
        supply_block = robot.vision_algorithm.product.block(spec.supply_length__mm)
        start_wrist = entry.rpy.yaw_deg
        carry_wrist = start_wrist + spec.long_axis__deg - spec.supply_long_axis__deg

        def over(xy_mm, what: str) -> bool:
            return self._leg(lambda: self.route.plane(xy_mm, speed, self.status.get(), z_safe), what, note)

        def near(xy_mm, what: str) -> bool:
            return self._leg(lambda: self.route.plane(xy_mm, speed, self.status.get(), z_transit), what, note)

        def to(z_mm: float, what: str) -> bool:
            return self._leg(lambda: self.route.height(z_mm, speed, self.status.get()), what, note)

        def wrist(deg: float, what: str) -> bool:
            return self._leg(lambda: self.route.turn(deg, speed, self.status.get()), what, note)

        def release(what: str) -> bool:
            return self._release(what, robot, note)

        reason = None  # 수집이 끝난 까닭. 예외로 빠지면 비어 있다
        try:
            if not (over(entry.xy, "투입점 위로")
                    and self._grab("투입점 블록 물기", robot.conveyor, start_wrist, z_safe, robot, speed, note, lift_unheard=True)
                    and wrist(carry_wrist, "장축 방위로 손목 돌리기")):
                reason = "투입점에서 블록을 못 물었다"
                return
            held = True  # 블록을 물고 있다고 보는가. 끝에 투입점에 되돌려 놓을 것이 있는지를 말한다

            misses, reason, turned_deg, batch = 0, "끝", 0.0, tuple(points)
            while batch:
                for point in batch:
                    name, xy_mm, turn_deg = point.name, point.robot_xy_mm, point.turn_deg
                    held_wrist = Tool.wrap180(carry_wrist + turn_deg)
                    if turn_deg != turned_deg and not wrist(held_wrist, f"{name} 방위로 손목 돌리기"):
                        reason = f"{name} 방위로 손목을 못 돌렸다"
                        break
                    turned_deg = turn_deg
                    if not (near(xy_mm, f"{name} 위로") and to(robot.mat.release_z_mm, f"{name} 에 내려놓기")):
                        reason = f"{name} 에 못 갔다"
                        break
                    snap(f"{name}_held")
                    if not release(name):
                        reason = f"{name} 에 놓지 못했다"
                        break
                    held = False
                    if not (to(z_safe, f"{name} 에서 올라가기") and over(entry.xy, f"{name} 뒤 투입점으로 대피")):
                        reason = f"{name} 뒤 대피를 못 했다"
                        break
                    seen = look(point)
                    misses = 0 if seen else misses + 1
                    again_xy = regrab(point)
                    if not robot.can_pick(*again_xy):
                        reason = f"{name} 에서 다시 물 자리 ({again_xy[0]:.1f}, {again_xy[1]:.1f}) 가 가동범위 밖이거나 팔이 닿지 않는다"
                        break
                    if not (over(again_xy, f"{name} 로 돌아가기")
                            and self._grab(f"{name} 다시 물기", robot.mat, held_wrist, z_transit, robot, speed, note, lift_unheard=True)):
                        reason = f"{name} 에서 다시 못 물었다"
                        break
                    held = True
                    snap(f"{name}_lifted")
                    if misses >= spec.discard_limit:
                        reason = f"연속 {misses} 번 관측이 어긋나 멈췄다"
                        break
                else:
                    batch = more()
                    continue
                break

            swept = not batch  # 자리를 다 돌았는가 — 중간에 멈추면 돌던 차례가 남는다
            returned = True    # 들고 있던 블록을 투입점에 되돌려 놓았는가. 들고 있지 않았으면 참이다
            if held:
                return_wrist = robot.place_wrist_deg(supply_block, Tool.wrap180(carry_wrist + turned_deg), spec.long_axis__deg + turned_deg)
                if not (over(entry.xy, "되돌리러 투입점 위로") and wrist(return_wrist, "벨트 진행 방위로 손목 돌리기")
                        and to(robot.conveyor.release_z_mm, "투입점에 내리기")):
                    reason, returned = f"{reason} · 블록을 투입점에 되돌리지 못했다", False
                elif not (release("투입점에 되돌려 놓기") and to(z_safe, "투입점에서 올라가기")):
                    reason, returned = f"{reason} · 투입점에 되돌려 놓기를 끝내지 못했다", False
            if swept and returned:
                reference = robot.motion.positions.camera_reference
                reference_z_mm = robot.place_z_mm(reference)
                if not (wrist(reference.rpy.yaw_deg, "카메라 기준 장면 손목으로") and self._leg(lambda: self.route.travel(reference.xy, reference_z_mm, speed, self.status.get(), z_safe), "카메라 기준 장면 자리로", note)):
                    reason = f"{reason} · 카메라 기준 장면 자리로 못 갔다"
                else:
                    reference_scene()
                    if not over(entry.xy, "카메라 기준 장면 뒤 투입점으로 비키기"):
                        reason = f"{reason} · 카메라 기준 장면 자리에서 투입점으로 비키지 못했다"
        finally:
            finish(reason if reason is not None else "처리 중 멈췄다")

    def _line(self, text: str) -> None:
        """사람이 친 줄을 그대로 보낸다. 엔지니어가 쓰는 도구라 낱말을 가리지 않는다."""
        verdict, raw = self.link.send(text)
        self._say(f"{text} -> {verdict} :: {raw.strip()[:80] or '응답 없음'}")

    def _read_status(self) -> None:
        parsed = self.link.status()
        if parsed is not None:
            self.status.put(parsed)


# =========================================================================
# 2. 흡착 음향 판정 — 관측을 이름으로 옮긴다
# =========================================================================

# 패드에서는 소리가 안 난다.
# 압력이 약해 귀를 대도 거의 들리지 않는다.
# 그러므로 **상태가 소리에 실리는 길은 펌프에 걸리는 부하 하나뿐**이다.
# 부하가 걸리면 축이 느려진다.
#
# 느려진 것을 **무부하 대비 비로 잰다.**
# 같은 흡착이라도 밀착이 좋으면 더 느려지므로 — 손으로 눌러 붙인 것은 8.7%, 로봇이 집어 올린 것은 6.1% 떨어졌다 — 비로 적어야 둘 다 한 범위에 든다.
# **그 가동에서 본 가장 빠른 회전을 기준으로 삼고 그 대비 얼마나 느려졌는지**를 본다.
# 펌프는 늘 패드가 닿기 전에 먼저 돌므로 처음 보는 회전이 곧 무부하다.
#
# 회전수는 배음 간격을 자기상관으로 재어 얻는다.
# 대역 안 최댓값을 짚지 않는다 — 리크와 파기에서 ±19 Hz 로 떨린다.
# 자기상관은 배음 여럿을 한꺼번에 보므로 한 선이 흔들려도 견딘다.
#
# 세기는 판정에 쓰지 않는다.
# 빗살 음조성은 게인에는 무차원이나 신호 대 잡음에는 의존한다 — 멀리서 찍은 녹음에서는 같은 흡착이 절반 아래로 나온다.
# 재어 남기되 판정은 위치와 비로만 한다.
# 지령이 켜졌는데 이 값이 안 오르면 펌프가 고장 난 것이므로 기록은 버리지 않는다.
#
# **소리가 답하는 것은 부하 하나뿐이다.**
# 흡입인지 파기인지는 우리가 쏜 지령(`M3 S1000` · `S500`)이 이미 알고, 둘 다 부하가 없어 소리로는 어차피 안 갈린다.
# 그래서 목표를 둘로 둔다 — 걸렸는가, 안 걸렸는가.
#
# `rotation_found` 가 말하는 것은 하나다 — 빗살이 가동 회전 범위에서 잡혔다는 관측일 뿐이다.
# 펌프가 실제로 도는지는 지령이 알고, 잡히고 안 잡히고는 신호가 얼마나 묻혔느냐에도 달린다.
# 이름이 실체를 주장하면 안 잡혔을 때 "펌프가 섰다" 로 잘못 읽힌다.
#
# 목표 이름은 정본 JSON 이 정한다. 여기에 목록을 두지 않는다.


class Reading(NamedTuple):
    """한 관측에서 읽은 것."""

    rotation_hz: float  # 배음 간격으로 잰 펌프 축 회전수. 못 재면 0
    reference_hz: float  # 이번 가동에서 본 가장 빠른 회전. 무부하 기준이다
    load_ratio: float  # 회전수 / 기준. 부하가 걸릴수록 작다. 기준이 없으면 0
    comb_tonality_db: float  # 기계 주기성의 세기. 기록만 한다
    rotation_found: bool  # 빗살이 가동 회전 범위에서 잡혔는가. 펌프 가동 여부는 공압 PWM 되읽기가 안다
    reading: str  # 이 관측 하나가 가리킨 목표 이름. 못 짚었으면 빈 문자열
    target: str  # 연속으로 굳은 목표 이름. 바깥이 쓸 답이다
    at: float  # 관측 시각


class VacuumSound:
    """음향 관측을 목표 이름으로 옮긴다. 화면도 장치도 모른다.

    한 가동의 무부하 회전수를 기억하므로 **상태를 든다.** 가동이 끝나면 `reset` 으로 버린다.
    """

    robot: "Config.Robot"  # 로봇 규격(`robot.json`) — 음향 규격(`acoustic`)을 여기서 읽는다
    reference_hz: float
    _last_comb_at: float | None
    _last_answer_at: float | None
    _settled: str
    _candidate: str
    _streak: int

    def __init__(self, robot: "Config.Robot") -> None:
        self.robot = robot
        self.reset()

    def reset(self) -> None:
        """기준과 굳은 상태를 버린다. 펌프가 서거나 다른 녹음으로 넘어갈 때 부른다."""
        self.reference_hz = 0.0
        self._last_comb_at = None
        self._last_answer_at = None
        self._settled = ""
        self._candidate = ""
        self._streak = 0

    def _settle(self, reading: str) -> str:
        """연속으로 같은 답이 몇 번 나와야 상태를 바꾼다.

        **답이 없는 관측은 세지 않는다.**
        회전수를 못 재면 답 자리가 빈다.
        그것을 하나의 답으로 세면 답과 답 사이에 끼어들어 연속을 끊는다 — 실제로 신호가 약한 녹음에서 세 번에 한 번 꼴로만 회전이 잡히는 구간이 있었고, 잡힐 때마다 옳은 답을 내는데도 사이의 빈칸 때문에 상태가 영영 안 굳었다.

        한 관측이 흔들려도 상태가 따라 흔들리지 않게 한다.
        들어가는 쪽과 나가는 쪽에 같은 수를 쓴다.
        다만 가진 해제 표본이 전부 펌프 정지와 겹쳐 있어, **펌프가 도는 채 흡착만 풀리는** 경우는 아직 재 본 적이 없다.
        그 녹화가 생기면 다시 본다.
        """
        if reading == self._candidate:
            self._streak += 1
        else:
            self._candidate, self._streak = reading, 1
        if self._candidate != self._settled and self._streak >= self.robot.acoustic.settling.answers_to_change:
            self._settled = self._candidate
        return self._settled

    # ------------------------------------------------------------ 보조

    def _combed(self, rotation_hz: float, fs: int) -> bool:
        """빗살이 실제로 잡혔는가.

        자기상관이 못 찾으면 답이 탐색 구간의 끝 칸에 놓인다.
        그 자리는 칸 폭에서 나오므로 도구에 물어본다.
        탐색 범위의 몇 퍼센트 같은 것으로 잡으면 칸 폭이 바뀔 때 조용히 틀어진다.
        """
        low, high = Tool.Acoustic.spacing_deadzone_hz(fs, self.robot.acoustic.block_size(fs), self.robot.acoustic.rotation_search_hz)
        return low < rotation_hz < high

    def _match(self, load_ratio: float) -> str:
        """부하비가 가리키는 목표. 가장 가까운 범위를 고른다.

        펌프가 도는 것이 확인된 뒤라면 부하는 걸렸거나 안 걸렸거나 둘뿐이라 제 3 의 답이 없다.
        두 범위 사이 빈틈에 떨어져도 모른다고 하지 않고 가까운 쪽을 준다 — 빈틈은 실측 구름 사이의 여백이다.
        """
        return min(
            self.robot.acoustic.pump.targets,
            key=lambda name: Tool.outside(load_ratio, self.robot.acoustic.target(name).load_ratio),
        )

    # ------------------------------------------------------------ 읽기

    def read(self, frame: Entity.AcousticFrame) -> Reading:
        """관측 한 벌을 읽고 기준을 갱신한다.

        빗살이 끊겨도 바로 기준을 버리지 않는다.
        컴프레셔는 기계 관성이 있어 순간적으로 섰다 돌 수 없다.
        블록 하나 길이만큼 견디고 그보다 오래 빗살이 없으면 정말 선 것으로 본다.

        시계가 둘이다.
        **빗살이 끊긴 시간**은 기준을 버릴지를 정하고, **쓸 수 있는 답이 없던 시간**은 상태를 놓을지를 정한다.
        둘은 다르다 — 신호가 약한 녹음에서는 빗살은 계속 잡히는데 회전이 가동 범위 안팎을 오가 답만 드문드문 나온다.
        그때 기준까지 버리면 이미 느려진 회전을 새 무부하 기준으로 삼아 이후가 통째로 어긋난다.

        **짧은 빈칸과 긴 빈칸은 다르다.**
        짧으면 잡음이라 세지 않고, 블록 하나 길이를 넘게 이어지면 그 자체가 "섰다" 는 답이라 투표에 넣는다.
        빈칸을 늘 세면 짧은 구간이 영영 안 굳고, 한 번도 안 세면 상태가 정지로 못 돌아온다.
        """
        freqs, power = frame.freqs, frame.power

        rotation_hz = Tool.Acoustic.harmonic_spacing_hz(
            freqs, power, self.robot.acoustic.equipment_sound.comb_scan__hz, self.robot.acoustic.rotation_search_hz
        )
        comb_tonality_db = Tool.Acoustic.tonality_db(freqs, power, self.robot.acoustic.equipment_sound.comb__hz)

        combed = self._combed(rotation_hz, frame.fs)
        found = combed and Tool.outside(rotation_hz, self.robot.acoustic.running_rotation_hz) == 0.0
        hold = self.robot.acoustic.hold_s(frame.fs)

        if combed:
            self._last_comb_at = frame.at
        if found:
            self._last_answer_at = frame.at
            self.reference_hz = max(self.reference_hz, rotation_hz)

        stale_comb = self._last_comb_at is None or frame.at - self._last_comb_at > hold
        stale_answer = self._last_answer_at is None or frame.at - self._last_answer_at > hold
        if stale_comb:
            self.reset()

        load_ratio = rotation_hz / self.reference_hz if (found and self.reference_hz) else 0.0
        hit = self._match(load_ratio) if load_ratio else ""
        if not hit and stale_answer:
            hit = ""  # 오래 답이 없으면 그 자체가 "섰다" 는 답이다
            vote = True
        else:
            vote = bool(hit)

        return Reading(
            rotation_hz=rotation_hz if combed else 0.0,
            reference_hz=self.reference_hz,
            load_ratio=load_ratio,
            comb_tonality_db=comb_tonality_db,
            rotation_found=found,
            reading=hit,
            target=self._settle(hit) if vote else self._settled,
            at=frame.at,
        )


# =========================================================================
# 3. 수음 워커 — 마이크를 물고 판정을 슬롯에 놓는다
# =========================================================================


class VacuumEar:
    """마이크를 독점하고 공압 상태를 슬롯에 놓는다.

    `RobotBus` 와 같은 결이되 **섞지 않는다.**
    시리얼 폴링과 오디오 블록은 주기가 다르므로 한 스레드에 넣으면 둘 다 망가진다.
    마이크는 이 워커 하나가 문다.

    **늘 듣는다.**
    공압 지령이 나간 뒤에 켜면 늦다 — 무부하 회전수를 기준으로 잡으려면 펌프가 돌기 시작하는 첫 순간을 봐야 하는데 그때는 이미 지나가 있다.

    **지령을 판정 조건으로 쓴다.**
    소리가 답할 수 있는 것은 부하가 걸렸는가 하나뿐이다.
    펌프가 도는지 · 흡입인지 파기인지는 로봇이 되읽어 주는 공압 PWM 이 말해 준다.
    되읽은 값을 쓰는 것은 그것이 실제로 걸린 값이기 때문이다.

    **판정을 근거로 지령을 되돌리지 않는다.** 소리가 틀렸을 때 설비를 움직이게 하는 길이라 위험하다.
    여기는 읽기만 하고 무엇을 할지는 부르는 쪽이 정한다.
    """

    class Heard(NamedTuple):
        """한 순간의 공압 상태. 소리와 지령을 함께 읽은 것이다."""

        commanded: "Config.Robot.Motion.PneumaticsPwm.State | None"  # 되읽은 PWM 이 말하는 지령. 모르면 None
        gripped: bool | None  # 붙었는가. 물을 것이 없는 자리에서는 None
        reading: "Reading"  # 소리에서 읽은 원값 한 벌
        at: float

    robot: "Config.Robot"  # 로봇 규격(`robot.json`) — 음향 규격(`acoustic`)과 공압 레벨(`motion.pneumatics_pwm`)을 여기서 읽는다
    status: "Tool.Slot | None"  # `RobotBus.status`. 없으면 소리만으로 읽는다
    preferred_name: str | None
    reader: VacuumSound
    heard: Tool.Slot  # `Heard` 이거나 `None`
    events: queue.Queue
    sound: "Connect.Device.Sound | None" = None
    _running: bool = False
    _thread: threading.Thread | None = None

    def __init__(
        self,
        robot: "Config.Robot",
        status: "Tool.Slot | None" = None,
        preferred_name: str | None = None,
    ) -> None:
        self.robot = robot
        self.status = status
        self.preferred_name = preferred_name

        self.reader = VacuumSound(robot)
        self.heard = Tool.Slot()
        self.events = queue.Queue()

    # ------------------------------------------------------------ 살림

    def start(self) -> None:
        """마이크를 열고 듣기 시작한다.

        장치를 먼저 고르고 그 표본율로 블록 크기를 정한 뒤에 연다.
        블록 크기가 표본율에서 나오므로 순서가 거꾸로면 엉뚱한 크기로 창을 잡는다.
        """
        if self._running:
            return
        device = Connect.Device.Sound.choose(self.preferred_name)
        fs = device["native_fs"]
        self.sound = Connect.Device.Sound(
            block_size=self.robot.acoustic.block_size(fs),
            hop_size=self.robot.acoustic.hop_size(fs),
            preferred_name=self.preferred_name,
            exclusive=self.robot.acoustic.capture.exclusive,
            backlog_hops=self.robot.acoustic.capture.backlog_hops,
            block_wait_s=self.robot.acoustic.capture.block_wait__s,
            stop_wait_s=self.robot.acoustic.capture.stop_wait__s,
        )
        self.sound.start()
        self.reader.reset()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._say(f"수음 :: {device['name']} · {fs} Hz · 블록 {self.robot.acoustic.block_size(fs)}")

    def shutdown(self) -> None:
        """듣기를 멈추고 마이크를 놓는다."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=self.robot.acoustic.capture.reader_stop_wait__s)
            self._thread = None
        if self.sound is not None:
            self.sound.stop()
        self.heard.put(None)

    def next_device(self) -> None:
        """다음 마이크로 옮겨 문다. 기준을 새로 잡아야 하므로 판독기도 비운다."""
        if self.sound is None:
            return
        device = self.sound.next_device()
        self.reader.reset()
        self.heard.put(None)
        self._say(f"수음 장치 :: {device['name']}")

    def _say(self, text: str) -> None:
        self.events.put(Tool.Event(text, time.monotonic()))

    # ------------------------------------------------------------ 듣기

    def _commanded(self) -> "Config.Robot.Motion.PneumaticsPwm.State | None":
        """되읽은 공압 PWM 이 말하는 지령. 로봇이 안 붙어 있으면 모른다."""
        if self.status is None:
            return None
        latest = self.status.get()
        if latest is None or latest.pump_pwm is None:
            return None
        return self.robot.motion.pneumatics_pwm.nearest_state(latest.pump_pwm)

    def _gripped(
        self, commanded: "Config.Robot.Motion.PneumaticsPwm.State | None", reading: "Reading"
    ) -> bool | None:
        """붙었는가. 물을 것이 없는 자리에서는 `None` 이다.

        흡입 지령이 아니면 애초에 붙을 일이 없으므로 소리를 볼 까닭이 없다.
        지령을 모를 때는 소리만으로 답한다 — 로봇 없이 녹음만 흘릴 때가 그 경우다.
        """
        if commanded is not None and commanded is not self.robot.motion.pneumatics_pwm.State.VACUUM:
            return None
        if not reading.target:
            return None
        return reading.target == self.robot.acoustic.loaded_target

    def _run(self) -> None:
        """관측이 새로 뜰 때마다 읽는다. 같은 관측을 두 번 읽지 않는다."""
        fs = self.sound.fs
        nap = self.robot.acoustic.hop_size(fs) / fs / 2.0
        seen = 0.0
        while self._running:
            frame = self.sound.latest
            if frame is None or frame.at <= seen:
                time.sleep(nap)
                continue
            seen = frame.at
            reading = self.reader.read(frame)
            commanded = self._commanded()
            self.heard.put(
                VacuumEar.Heard(
                    commanded=commanded,
                    gripped=self._gripped(commanded, reading),
                    reading=reading,
                    at=frame.at,
                )
            )
