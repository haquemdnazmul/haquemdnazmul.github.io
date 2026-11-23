"""비전 계통 알고리즘 — `com_lib_core` 의 계산을 골라 이어 붙이는 자리.

    [1] 카메라 워커      장치 하나를 물고 프레임을 슬롯에 놓는다
    [2] 현행 값          회차에서 올린 값을 실행 중에 든다. 기동 · 캡처 · 갱신
    [2-1] 회차 값 풀이   사진에서 회차 값을 푼다. 옆면으로 세로 소실점
    [3] 계산            전처리가 이미지와 마스크를 내고, 질문이 그것을 불러 개체를 확정한다
    [4] 판정 루프        카메라가 새 장을 받을 때마다 계산해 확정 개체 목록을 슬롯에 놓는다. 사영 모델 풀기를 맡는다

화면을 모른다. 일은 큐로 받고 결과는 `Tool.Slot` 과 사건 큐로 낸다.
쓰기(현행 값 · 회차 문서 · 촬영 사진 · 녹화 · 수집 기록)는 쓰기 주인(`Tool.Writer`)에 맡긴다.
"""
from __future__ import annotations

import dataclasses
import datetime
import itertools
import json
import math
import queue
import threading
import time
from concurrent.futures import Future
from enum import Enum, auto
from functools import partial
from pathlib import Path
from types import MappingProxyType
from typing import Any, NamedTuple

#: 머리에서 불러야 한다.
#: `comtypes` 는 **처음 불러들인 스레드**에 COM 을 열어 주는데, 워커 안에서 부르면 그 몫을 워커가 가져가 화면 스레드의 장치 열거가 죽는다
import comtypes

from com_lib_core import Config, Connect, Entity, Tool


# =========================================================================
# 1. 카메라 워커
# =========================================================================


class CameraBus:
    """카메라 하나를 독점하는 워커.

    역할마다 하나를 세운다.
    한 워커가 둘을 번갈아 열지 않는다 — 카메라는 열려 있는 동안 다른 프로세스가 못 쓴다.
    녹화는 장을 받는 것까지만 여기서 하고, 영상 파일을 여닫고 장을 쓰는 일은 쓰기 주인(`writer`)에 맡긴다.
    """

    class Job(Enum):
        """맡길 수 있는 일."""

        OPEN = "open"
        CLOSE = "close"
        READ_SETTINGS = "read_settings"
        READ_RANGES = "read_ranges"               # 조정할 때만 부른다. 닫으면 버린다
        APPLY_SETTINGS = "apply_settings"         # `EraState.apply_settings` 를 워커 위에서
        STARTUP = "startup"                       # `EraState.startup` 을 워커 위에서
        CAPTURE = "capture"                       # `EraState.capture` 를 워커 위에서
        RECORD = "record"                         # `path=` 영상 파일에 받는 장을 모두 쓴다
        RECORD_STOP = "record_stop"

    role: str  # 이 워커가 맡은 카메라 역할(`camera.json` `roles` 의 키)
    camera: "Config.Camera"  # 카메라 규격(`camera.json`) — 기다림 · 버릴 장 수 · 레지스터 · DirectShow · RealSense 대응을 여기서 읽는다
    writer: "Tool.Writer"  # 쓰기 주인. 녹화 파일을 여닫고 받은 장을 쓰는 일을 맡긴다
    frame: Tool.Slot  # 최신 한 장. 지나간 것은 안 쌓는다
    grabbed: Tool.Slot  # 연 뒤로 받은 장 수. 새 장이 들어왔는지 · 영상의 몇 번째 장인지를 이것으로 센다
    opened: Tool.Slot  # 카메라가 열려 있는가
    device: Tool.Slot  # 연 카메라의 대장 항목. 닫혀 있으면 `None`
    settings: Tool.Slot  # 장치에서 마지막으로 읽은 카메라 설정. 이름 → 장치 눈금
    ranges: Tool.Slot  # 장치가 밝힌 속성 범위. 이름 → `Controls.Range`, 지원 안 하면 `None`. 안 읽었으면 슬롯이 `None`
    events: queue.Queue  # 사람이 읽을 말
    requests: queue.Queue  # (일, 실을 것) — 맡은 일감
    _cap: Any = None  # 연 장치(OpenCV 캡처). 닫혀 있으면 `None`
    _controls: "Connect.Device.Usb.Controls | None" = None  # 연 장치의 DirectShow 손잡이
    _sdk_sensor: Any = None  # RealSense 를 열었을 때만 선다
    _video: Any = None  # 녹화 파일. 쓰기 주인의 줄에서만 여닫고 쓴다 — 녹화 중일 때만 선다
    _recording: bool = False  # 받는 장을 녹화에 맡기는가. 이 워커가 든다
    _shutdown: threading.Event  # 워커를 세우라는 알림
    _thread: threading.Thread

    def __init__(self, camera: "Config.Camera", role: str, writer: "Tool.Writer"):
        self.role = role
        self.camera = camera
        self.writer = writer
        self.frame = Tool.Slot()
        self.grabbed = Tool.Slot(0)
        self.opened = Tool.Slot(False)
        self.device = Tool.Slot()
        self.settings = Tool.Slot()
        self.ranges = Tool.Slot()
        self.events = queue.Queue()
        self.requests = queue.Queue()
        self._shutdown = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def shutdown(self) -> None:
        """워커가 카메라를 놓을 때까지 기다린다.

        카메라가 열린 채 프로세스가 끝나면, 마이크 수음이 함께 돌 때 종료가 멎는다.
        """
        self._shutdown.set()
        self._thread.join()

    def submit(self, job: "CameraBus.Job", **payload) -> None:
        """열기 · 닫기 · 설정 읽기 · 설정 적용. 장치는 워커가 독점하므로 여기서 직접 만지지 않는다.

        열기는 `entry=` 로 대장 항목 하나를 고른다. 안 주면 대장 앞의 장치부터 찾는다.
        설정 적용 · 기동 · 캡처는 `state=` 로 `EraState` 를 싣는다. 설정 적용은 `settings=` 로 이름 → 값을 더 싣는다.
        """
        self.requests.put((job, payload))

    def connected(self) -> tuple["Connect.Device.Usb.Entry", ...]:
        """이 역할의 대장에 있으면서 지금 붙어 있는 카메라. 대장 순서다."""
        attached = [device for device in Connect.Device.Usb.camera_ids() if device is not None]
        return tuple(entry for entry in self.camera.roles[self.role].device_ids if any(entry.id.matches(device) for device in attached))

    def fresh_frame(self, settle_s: float) -> Any:
        """로봇이 선 뒤의 새 장.

        흔들림이 가라앉기를 `settle_s` 기다린 뒤, 카메라 링버퍼에 남은 장(`flush_frames`)을 흘려보내고 새로 받은 장이다.
        섰다는 보고를 받은 때 슬롯에 든 장은 그 전에 찍혔을 수 있다.
        그사이 카메라가 닫히면 `None` 이다 — 닫힌 카메라는 장을 더 받지 않는다.
        """
        time.sleep(settle_s)
        wanted = self.grabbed.get() + self.camera.flush_frames
        while self.grabbed.get() < wanted:
            if not self.opened.get(): return None
            time.sleep(0)
        return self.frame.get()

    def _say(self, text: str) -> None:
        self.events.put(Tool.Event(text, time.monotonic()))

    def _open(self, chosen: "Connect.Device.Usb.Entry | None" = None) -> None:
        self._close()
        index, entry = Connect.Device.Usb.find_camera(self.camera.roles[self.role].device_ids if chosen is None else (chosen,))
        self._cap = Connect.Device.Usb.open_camera(index, self.camera.roles[self.role].backend)
        if not self._cap.isOpened():
            self._cap.release()
            self._cap = None
            self._say(f"{self.role} 카메라를 열지 못했다")
            return
        #: 연 직후의 장은 센서 게인 · 노출이 아직 서지 않았다 — 내지 않고 버린다(`Config.Camera.Role.warmup_frames`)
        for _ in range(self.camera.roles[self.role].warmup_frames):
            self._cap.read()
        self._controls = Connect.Device.Usb.Controls(index, self.camera.directshow.controls)
        if any(one.id.matches(entry.id) for one in self.camera.realsense.device_ids):
            self._sdk_sensor = self._find_sdk_sensor(entry)
        self.device.put(entry)
        self.opened.put(True)
        self._say(f"{self.role} 카메라 열림")

    def _find_sdk_sensor(self, entry: "Connect.Device.Usb.Entry") -> Any:
        """RealSense SDK 의 컬러 센서. DirectShow 에 없는 옵션만 여기로 읽고 쓴다. 영상을 긁는 동안에도 된다.

        `pyrealsense2` 는 RealSense 가 붙는 기계에만 있어 여기서 부른다. 같은 기종이 둘 붙는 일은 없다.
        """
        import pyrealsense2 as rs

        device = next(one for one in rs.context().query_devices() if one.get_info(rs.camera_info.product_id) == entry.id.pid)
        return next(sensor for sensor in device.query_sensors() if sensor.get_info(rs.camera_info.name) == self.camera.realsense.sensor)

    def _sdk_option(self, name: str) -> Any:
        import pyrealsense2 as rs

        return getattr(rs.option, self.camera.realsense.options[name])

    def _close(self) -> None:
        self._record_stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._controls = None
        self._sdk_sensor = None
        self.ranges.put(None)
        self.device.put(None)
        self.opened.put(False)
        self.frame.put(None)

    def _grab(self) -> None:
        got, frame = self._cap.read()
        if not got:
            self._say(f"{self.role} 프레임을 못 받았다")
            self._close()
            return
        self.frame.put(frame)
        self.grabbed.put(self.grabbed.get() + 1)
        if self._recording:
            def recorded() -> None:
                if self._video is not None: self._video.write(frame)
            self.writer.submit(recorded)

    def _record(self, path: Path) -> None:
        """받는 장을 모두 영상 파일에 쓰기 시작한다. 장 빠르기와 크기는 연 장치가 밝힌 값이다.

        파일은 쓰기 주인이 연다. 열렸는지 본 뒤에 장을 맡기기 시작한다.
        """
        from cv2 import CAP_PROP_FPS, CAP_PROP_FRAME_HEIGHT, CAP_PROP_FRAME_WIDTH, VideoWriter, VideoWriter_fourcc

        self._record_stop()
        size = (int(self._cap.get(CAP_PROP_FRAME_WIDTH)), int(self._cap.get(CAP_PROP_FRAME_HEIGHT)))
        fps = float(self._cap.get(CAP_PROP_FPS))

        def opened() -> bool:
            video = VideoWriter(str(path), VideoWriter_fourcc(*"mp4v"), fps, size)
            if not video.isOpened():
                self._say(f"녹화를 시작하지 못했다 :: {path}")
                return False
            self._video = video
            self._say(f"녹화 시작 :: {path.name}")
            return True

        self._recording = self.writer.submit(opened).result()

    def _record_stop(self) -> None:
        """녹화를 그친다. 파일은 앞서 맡긴 장을 다 쓴 뒤 쓰기 주인이 닫는다."""
        if not self._recording: return
        self._recording = False

        def closed() -> None:
            self._video.release()
            self._video = None
            self._say("녹화 끝")

        self.writer.submit(closed)

    # 설정 읽기 · 적용 :: 워커 스레드에서만 부른다. 일감 처리와 `EraState` 가 부른다

    def read_settings(self) -> None:
        """카메라 설정 전체를 읽는다. 장치가 읽지 못하는 속성은 `-1` 을 돌려주며 `None` 으로 남긴다.

        못 읽는다는 것도 그 장치의 사실이라 이름을 지우지 않는다.
        OpenCV 가 못 읽는 자동 플래그는 DirectShow 손잡이로 읽고, RealSense 면 SDK 옵션을 더한다.
        """
        read = {name: float(self._cap.get(prop_id)) for name, prop_id in self.camera.property_ids.items()}
        settings = {name: None if value == -1 else value for name, value in read.items()}
        for name, control in self.camera.directshow.auto_flags.items():
            is_auto = self._controls.is_auto(control)
            settings[name] = None if is_auto is None else float(is_auto)
        if self._sdk_sensor is not None:
            settings |= {name: self._sdk_sensor.get_option(self._sdk_option(name)) for name in self.camera.realsense.options}
        self.settings.put(MappingProxyType(settings))

    def apply_settings(self, settings: dict[str, float | None]) -> None:
        """설정을 장치에 써 넣고 다시 읽는다. 장치에 실제로 걸린 값은 다시 읽은 쪽이다. `None` 은 쓸 값이 없다.

        끄는 자동 제어는 수동 값보다 먼저, 켜는 자동 제어는 나중에 쓴다.
        자동이 켜져 있으면 수동 값을 덮는 장치가 있고, 수동 값을 쓰면 자동을 끄는 장치(D455 의 노출 · WB)가 있다.
        자동 끄기를 다시 쓰면 D455 는 방금 쓴 WB 를 되돌린다.
        """
        written = [name for name in settings if settings[name] is not None]
        autos = [name for name in written if name in self.camera.settings_apply.auto_flags]
        turning_on = [name for name in autos if settings[name] > self.camera.settings_apply.auto_on_min]
        turning_off = [name for name in autos if name not in turning_on]
        for name in turning_off + [name for name in written if name not in autos] + turning_on:
            if name in self.camera.directshow.auto_flags:
                self._controls.set_auto(self.camera.directshow.auto_flags[name], settings[name] > self.camera.settings_apply.auto_on_min)
            elif name in self.camera.realsense.options:
                self._sdk_sensor.set_option(self._sdk_option(name), settings[name])
            else:
                self._cap.set(self.camera.property_ids[name], settings[name])
            for _ in range(self.camera.settings_apply.settle_frames):
                self._cap.read()
        self.read_settings()

    def read_ranges(self) -> None:
        """속성마다 장치가 밝힌 범위. 슬라이더를 열 때만 부른다."""
        self.ranges.put(MappingProxyType({name: self._controls.range(name) for name in self.camera.directshow.controls}))

    def _run(self) -> None:
        """열기 전에는 요청만 기다린다. 열려 있는 동안은 계속 긁는다.

        **COM 을 이 스레드에서 연다.**
        DirectShow 열거가 스레드마다 요구하는데, 세운 쪽이 열어 둔 것은 그 스레드 몫이라 여기까지 안 온다.
        """
        comtypes.CoInitialize()
        try:
            self._loop()
        finally:
            comtypes.CoUninitialize()

    def _loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                job, payload = self.requests.get(timeout=self.camera.request_wait__s)
            except queue.Empty:
                if self.opened.get():
                    self._grab()
                continue
            try:
                if job is self.Job.OPEN:
                    self._open(payload.get("entry"))
                elif job is self.Job.CLOSE:
                    self._close()
                    self._say(f"{self.role} 카메라 닫음")
                elif job is self.Job.READ_SETTINGS:
                    self.read_settings()
                elif job is self.Job.READ_RANGES:
                    self.read_ranges()
                elif job is self.Job.APPLY_SETTINGS:
                    payload["state"].apply_settings(self, payload["settings"])
                elif job is self.Job.STARTUP:
                    payload["state"].startup(self)
                elif job is self.Job.RECORD:
                    self._record(payload["path"])
                elif job is self.Job.RECORD_STOP:
                    self._record_stop()
                else:
                    payload["state"].capture(self)
            except Exception as exc:                  # noqa: BLE001
                self._say(f"{job} 에 실패했다 :: {exc}")
        self._close()


# =========================================================================
# 2. 현행 값
# =========================================================================


class EraState:
    """현행 값. 회차 문서와 같은 꼴(`dataset.json` 의 `era_template`)을 실행 중에 든다.

    회차는 캡처한 사진과 그 순간 현행 값의 사본이다. 현행 값은 여기에만 있고 포인터를 두지 않는다.

    현행 값이 출처 회차에서 벗어나는 길은 둘이다 — 카메라 설정 적용과 실시간 갱신(`edit`).
    둘 다 파일을 안 건드리고, 현행 값이 출처 회차 파일과 달라지면 `differs_from_source` 가 선다.
    기동 때 장치가 출처 회차의 카메라 설정을 다 받지 못하면 `settings_missed` 가 선다 — 문서는 파일과 같아도 장치는 그 회차의 조건이 아니다.
    캡처는 둘 중 하나라도 서 있으면 새 회차를 만든다.
    회차 파일을 고치는 것은 회차를 열고 하는 갱신(`update`)뿐이다 — 실시간은 메모리, 회차 파일은 그 회차를 열었을 때다.

    기동 · 설정 적용 · 캡처는 장치를 만지므로 카메라 워커가 부른다(`CameraBus.Job` 의 `state=`). 갱신은 화면이 사람의 입력을 넘길 때, 사영 모델 풀기는 판정 루프가, 대응점 수집 결과는 로봇 워커가 부른다(`Calibration.Collector.finish` 의 `edit`).
    부르는 스레드가 어디든 현행 값을 읽어 고쳐 끼우는 일과 회차 파일 쓰기는 쓰기 주인(`writer`)의 줄에서 돈다 — 두 고침이 섞여 한쪽이 사라지지 않는다.
    장치를 만지는 몫(설정을 써 넣고 다시 읽기 · 장 받기)은 카메라 워커가 먼저 하고, 쓰는 몫만 맡긴다.
    갱신(`update` · `edit`)은 맡긴 표(`Future`)를 돌려준다 — 썼다고 알리거나 쓴 것을 다시 읽을 쪽이 그것으로 끝난 것을 본다. 카메라 워커가 부르는 셋은 쓰기가 끝날 때까지 기다린다.
    """

    class Current(NamedTuple):
        """한 번에 바뀌는 한 벌. 읽는 쪽이 문서와 값이 어긋난 순간을 보지 않는다."""

        source_era: "Config.Dataset.Era"  # 값의 출처 회차. 갱신이 이 회차를 고치면 현행 값도 바뀐다
        doc: dict[str, Any]  # 회차 문서 꼴. 고치지 않고 통째로 바꿔 끼운다
        era_values: "Config.Dataset.EraValues"  # 그 문서의 값. 계산은 이 값을 받아서 돈다(`era_values_of`)
        differs_from_source: bool  # 현행 값이 출처 회차 파일과 다르다(설정 적용 · 실시간 갱신). 다음 캡처가 새 회차를 만든다
        settings_missed: bool  # 기동 때 장치가 출처 회차의 카메라 설정을 다 받지 못했다(회차에 설정이 없었던 때도). 다음 캡처가 새 회차를 만들고, 설정을 다시 적용하면 내린다

    dataset: "Config.Dataset"
    product: "Config.Product"
    writer: "Tool.Writer"  # 쓰기 주인. 현행 값을 고쳐 끼우는 일과 회차 파일 쓰기를 맡긴다
    current: Tool.Slot  # `EraState.Current`. 그 카메라의 회차가 하나도 없으면 `None`
    events: queue.Queue

    def __init__(self, dataset: "Config.Dataset", product: "Config.Product", writer: "Tool.Writer"):
        self.dataset = dataset
        self.product = product
        self.writer = writer
        self.current = Tool.Slot()
        self.events = queue.Queue()

    def _say(self, text: str) -> None:
        self.events.put(Tool.Event(text, time.monotonic()))

    def era_values_of(self, doc: dict[str, Any]) -> "Config.Dataset.EraValues":
        """회차 문서 한 장의 값 — 현행 값과 화면이 보는 회차가 함께 쓴다.

        블록 높이를 넣어 주어 내부 파라미터를 아는 카메라의 세로 소실점을 H35 에서 셈하게 한다(`Config.Dataset.EraValues.Homography.vanishing_point`).
        """
        return Config.Dataset.EraValues(doc, height_mm=self.product.dimensions.height__mm)

    def _differs(self, era: "Config.Dataset.Era", doc: dict[str, Any]) -> bool:
        """현행 값의 문서가 출처 회차 파일과 다른가."""
        return doc != self.dataset.read_era(era.path)

    @staticmethod
    def _written(doc: dict[str, Any], section: str, changes: dict[str, Any]) -> dict[str, Any]:
        """회차 문서 한 장의 한 칸(`section`)에 항목들을 적은 새 문서.

        그 칸의 다른 항목(`camera.pinhole` 같은 것)은 그대로 둔다.
        받은 문서는 고치지 않는다.
        """
        return {**doc, section: {**doc[section], **Tool.JsonNode.plain(changes)}}

    def _adopt(self, era: "Config.Dataset.Era", doc: dict[str, Any], differs_from_source: bool, *, settings_missed: bool) -> None:
        self.current.put(self.Current(era, doc, self.era_values_of(doc), differs_from_source, settings_missed))

    def startup(self, bus: CameraBus) -> None:
        """기동. 같은 카메라의 가장 최근 회차 설정을 장치에 써 넣고, 다시 읽어 확인한 뒤 그 회차 값을 올린다.

        카메라는 다시 꽂으면 공장 기본값으로 돌아가므로 설정을 써 넣는 것이 전제다.
        반영 안 된 속성이 있거나 회차에 설정이 없어도 올리고 화면에 알린다. 그때 장치는 그 회차의 조건이 아니다.
        그때는 `settings_missed` 가 서서 다음 캡처가 새 회차를 만든다.
        같은 카메라로 이미 올렸으면 다시 하지 않는다 — 닫았다 열어도 장치 설정은 남고, 사람이 바꾼 설정을 덮지 않는다.
        카메라가 안 열렸으면 할 일이 없다. 못 열었다는 말은 버스가 한다.
        """
        entry, current = bus.device.get(), self.current.get()
        if entry is None: return
        if current is not None and current.era_values.camera.device.is_among([entry.id]): return
        era = self.dataset.latest(entry.id)
        if era is None:
            bus.read_settings()
            self._say(f"{entry.name} 의 회차가 없다 — 카메라 설정 · 작업영역 · H35 · 아핀을 새로 잡는다")
            return
        doc = self.dataset.read_era(era.path)
        recorded = doc["camera"]["settings"]
        if recorded is None:
            bus.read_settings()
            self._say(f"{era.name} 에 카메라 설정이 없어 장치 값을 그대로 둔다")
            self.writer.submit(self._adopt, era, doc, False, settings_missed=True).result()
        else:
            bus.apply_settings(recorded)
            applied = bus.settings.get()
            missed = [name for name, value in recorded.items() if value is not None and applied[name] != value]
            if missed:
                self._say(f"{era.name} 설정 중 반영 안 됨 :: " + " · ".join(f"{name} {recorded[name]:g} → {applied[name]}" for name in missed))
            self.writer.submit(self._adopt, era, doc, False, settings_missed=bool(missed)).result()
        self._say(f"현행 값을 {era.name} 에서 올렸다")

    def apply_settings(self, bus: CameraBus, settings: dict[str, float | None]) -> None:
        """카메라 설정을 장치에 써 넣는다. 다시 읽은 값이 현행 값의 카메라 설정이 된다.

        현행 값이 출처 회차 파일과 다르면 출처와 달라졌다고 표시한다. 출처 설정으로 되돌려도 실시간 갱신이 남아 있으면 표시가 안 내린다.
        장치에서 다시 읽은 설정을 현행 값에 적으므로 기동 때 못 받은 설정 표시(`settings_missed`)는 내린다.
        """
        bus.apply_settings(settings)
        applied = bus.settings.get()

        def written() -> None:
            current = self.current.get()
            if current is None: return
            doc = self._written(current.doc, "camera", {"settings": dict(applied)})
            self._adopt(current.source_era, doc, self._differs(current.source_era, doc), settings_missed=False)

        self.writer.submit(written).result()

    def capture(self, bus: CameraBus) -> None:
        """사진 한 장을 회차에 넣는다.

        현행 값이 없거나, 출처 회차와 달라졌거나, 기동 때 장치가 출처 회차의 설정을 다 받지 못했거나, 출처가 당일 회차가 아니면 새 회차를 만든다.
        그 밖에는 출처 회차에 더한다.
        새 회차는 현행 값의 사본에 장치와 마지막으로 읽은 카메라 설정 전체를 적은 것이고, 현행 값의 출처가 된다.
        장 · 장치 · 설정은 카메라 워커가 지금 것을 든다. 새 회차를 열지 · 어디에 넣을지는 쓰기 주인의 줄에서 그때의 현행 값으로 정한다.
        """
        from cv2 import imwrite as cv2_imwrite

        when, frame, entry, settings = datetime.datetime.now(), bus.frame.get(), bus.device.get(), bus.settings.get()

        def written() -> None:
            current = self.current.get()
            era = None if current is None else current.source_era
            if current is None or current.differs_from_source or current.settings_missed or era.day != self.dataset.storage_format.era_day(when):
                base = self.dataset.era_template if current is None else current.doc
                doc = self._written(base, "camera", {"device": {"id": entry.id._replace(mi=None).text, "name": entry.name}, "settings": dict(settings)})
                era = self.dataset.create_era(when, doc)
                self._adopt(era, doc, False, settings_missed=False)
                self._say(f"새 회차 {era.name}")
            frame_path = next(path for path in (era.path / self.dataset.storage_format.frame_name(when, collision) for collision in itertools.count())
                              if not path.exists())
            cv2_imwrite(frame_path, frame)
            self._say(f"{era.name} / {frame_path.name}")

        self.writer.submit(written).result()

    def update(self, era: "Config.Dataset.Era", section: str, changes: dict[str, Any]) -> Future:
        """갱신. 화면이 고른 회차의 회차 문서에서 한 칸(`section` — `homography` · `work_area` 같은 것)의 항목들을 바로 쓴다.

        백업 없이 덮는다 — 최신이 참값이다.
        그 회차가 현행 값의 출처이면 현행 값의 같은 칸도 고친다. 현행 값의 카메라 설정은 파일과 다를 수 있어 문서를 다시 읽지 않는다.
        옛 회차에서 고치는 것은 작업영역 · H35 · 소실점이고, 카메라 설정과 아핀은 고치지 않는다.
        """
        def written() -> None:
            self.dataset.write_era(era.path, self._written(self.dataset.read_era(era.path), section, changes))
            current = self.current.get()
            if current is not None and current.source_era.path == era.path:
                current_doc = self._written(current.doc, section, changes)
                self._adopt(era, current_doc, self._differs(era, current_doc), settings_missed=current.settings_missed)

        return self.writer.submit(written)

    def edit(self, section: str, changes: dict[str, Any]) -> Future:
        """실시간 갱신. 현행 값의 한 칸(`section`)의 항목들만 고치고 회차 파일은 안 건드린다.

        출처와 달라졌다고 표시되어 다음 캡처가 이 값을 든 새 회차를 만든다.
        """
        def written() -> None:
            current = self.current.get()
            doc = self._written(current.doc, section, changes)
            self._adopt(current.source_era, doc, self._differs(current.source_era, doc), settings_missed=current.settings_missed)

        return self.writer.submit(written)


# =========================================================================
# 2-1. 회차 값 풀이
# =========================================================================


class Calibration:
    """회차 값을 사진에서 푸는 절차. `com_lib_core` 의 계산 부품을 탐색으로 잇는다 — 튜닝이 드는 전략이라 여기 선다."""

    class SideView(NamedTuple):
        """사진 한 장의 옆면 증거. 부르는 쪽이 전처리로 만든다 — 부류를 가르는 법은 여기서 모른다."""

        upper_shapes_px: tuple  # 블록마다 윗면사각형 네 꼭짓점(원본 화소)
        seen: Any  # 보인 부류 지도(`Tool.Vision.PrismFace` 값). 원본 화소 격자
        region: Any  # `seen` 과 같은 크기. 0 보다 큰 곳만 센다
        origin_px: tuple[float, float]  # `seen` 의 왼쪽 위가 원본에서 놓인 자리

    class ProjectiveModel(NamedTuple):
        """회차 하나의 사영 모델을 푼 것(`fit_projective_model`). 화면이 알린다."""

        label_frames: int  # H35 를 푼 라벨 사진 수
        label_quads: int  # H35 를 푼 사각형 수
        outline_photos: int | None  # 세로 소실점을 낸 외곽 사진 수. 내부 파라미터를 아는 카메라라 외곽으로 내지 않았으면 `None`, 떨어진 블록이 든 사진이 없어 못 냈으면 0

    class OutlineView(NamedTuple):
        """사진 한 장의 외곽 증거. 블록과 매트만 가른 실루엣이다 — 윗면과 옆면을 밝기로 가르지 않는다."""

        upper_shapes_px: tuple  # 블록마다 윗면사각형 네 꼭짓점(원본 화소)
        silhouette: Any  # 실루엣 마스크. 0 보다 큰 곳이 블록(윗면 + 보이는 옆면)이다. 원본 화소 격자
        region: Any  # `silhouette` 와 같은 크기. 0 보다 큰 곳만 센다
        origin_px: tuple[float, float]  # `silhouette` 의 왼쪽 위가 원본에서 놓인 자리

        @classmethod
        def observed(cls, photo: "Calc.Photo", route: "Calc.Pre.Route") -> "Calibration.OutlineView":
            """회차 사진 한 장을 계산한 것(`Calc.photo`)에서 외곽 증거를 세운다.

            윗면사각형은 단품만 들이고, 못 가른 덩어리는 셀 곳에서 뺀다 — 그리지 않은 블록이 어긋남에 섞이지 않는다.
            """
            crop = photo.calc.pre.roi(route)
            silhouette = photo.calc.pre.silhouette(route)
            unsplit = Tool.Vision.fill_polygons(silhouette.shape, [[(x - crop.origin_px[0], y - crop.origin_px[1]) for x, y in lump.contour_px] for lump in photo.unsplit], 255)
            return cls(tuple(piece.corners_px for piece in photo.pieces), silhouette, Tool.Vision.mask_minus(crop.mask, unsplit), crop.origin_px)

    @staticmethod
    def vanishing_point_from_sides(homography: "Config.VisionAlgorithm.Homography", h35: "Config.Dataset.EraValues.Homography", views: "list[Calibration.SideView]", *,
                                   search: "Config.VisionAlgorithm.VanishingSearch", raster_scale: int) -> tuple[float, float, float]:
        """옆면으로 세로 소실점을 찾는다. 블록을 윗면 · 옆면으로 그려 보인 부류 지도와 부류째 견준다(`Tool.Vision.class_mismatch`). 훑기는 `_vanishing_searched` 다."""
        return Calibration._vanishing_searched(homography, h35, [(view.upper_shapes_px, view.seen, view.region, view.origin_px) for view in views],
                                               Tool.Vision.class_mismatch, search=search, raster_scale=raster_scale)

    @staticmethod
    def vanishing_point_from_outlines(homography: "Config.VisionAlgorithm.Homography", h35: "Config.Dataset.EraValues.Homography", views: "list[Calibration.OutlineView]", *,
                                      search: "Config.VisionAlgorithm.VanishingSearch", raster_scale: int) -> tuple[float, float, float]:
        """외곽으로 세로 소실점을 찾는다. 그린 블록(윗면 + 보이는 옆면)과 실루엣을 블록 · 매트 두 부류로만 견준다 — 윗면과 옆면을 밝기로 가르지 못하는 설치에서도 선다. 훑기는 `_vanishing_searched` 다.

        윗면은 받은 대로 두고 소실점만 맞춘다 — 윗면 자세까지 풀면 블록을 옮긴 것과 옆면이 넓어진 것이 같은 쪽 윤곽을 키워 자세와 경사가 서로를 먹는다.
        """
        return Calibration._vanishing_searched(homography, h35, [(view.upper_shapes_px, view.silhouette, view.region, view.origin_px) for view in views],
                                               lambda drawn, seen, region: Tool.Vision.class_mismatch(drawn > 0, seen > 0, region),
                                               search=search, raster_scale=raster_scale)

    @staticmethod
    def fit_projective_model(state: EraState, vision_algorithm: "Config.VisionAlgorithm", route: "Calc.Pre.Route", era: "Config.Dataset.Era") -> "Calibration.ProjectiveModel | None":
        """회차 하나의 사영 모델을 풀어 그 회차 파일에 적는다. 라벨이 없으면 `None` 이다.

        H35 는 라벨 전부로 푼다(`Config.VisionAlgorithm.HomographyFit.fit`).
        세로 소실점은 내부 파라미터를 모르는 카메라일 때만 그 회차 사진의 외곽으로 내어 함께 적는다(`vanishing_point_from_outlines`) — 소실점이 이 H35 위에서 풀린다.
        내부 파라미터를 아는 카메라는 회차를 불러올 때 닫힌 식으로 내므로(`Config.Dataset.EraValues.Homography.vanishing_point`) 적지 않는다.
        판정 루프(`CalcBus.Job.FIT_PROJECTIVE_MODEL`)가 부른다. 적은 것이 다 쓰인 뒤에 돌아온다 — 세로 소실점은 적은 H35 를 다시 읽어 그 위에서 푼다.
        """
        labels = Config.Dataset.Labels.load(era.path)
        if not labels.quads_by_frame: return None
        matrix = vision_algorithm.homography_fit.fit(labels.quads_by_frame, width_mm=state.product.dimensions.width__mm)
        #: H35 만 적는다 — 내부 파라미터를 아는 카메라의 세로 소실점은 불러올 때 내는 값이라 파일에 적지 않는다
        state.update(era, "homography", {"matrix": matrix}).result()
        model = Calibration.ProjectiveModel(len(labels.quads_by_frame), sum(len(one) for one in labels.quads_by_frame.values()), None)
        era_values = state.era_values_of(state.dataset.read_era(era.path))
        if era_values.camera.get("pinhole") is not None: return model
        photos = Config.Dataset.Photos(era.path)
        views = [view for view in (Calibration.OutlineView.observed(Calc.photo(vision_algorithm, era_values, route, photos.read(index)), route) for index in range(len(photos))) if view.upper_shapes_px]
        if views:
            point = Calibration.vanishing_point_from_outlines(vision_algorithm.homography, era_values.homography, views, search=vision_algorithm.vanishing_search, raster_scale=vision_algorithm.box_fit.raster_scale)
            state.update(era, "homography", {"vertical_vanishing_point": tuple(float(component) for component in point)}).result()
        return model._replace(outline_photos=len(views))

    @staticmethod
    def _vanishing_searched(homography: "Config.VisionAlgorithm.Homography", h35: "Config.Dataset.EraValues.Homography", evidence: list, mismatch_of: Any, *,
                            search: "Config.VisionAlgorithm.VanishingSearch", raster_scale: int) -> tuple[float, float, float]:
        """옆면 탐색과 외곽 탐색이 함께 쓰는 훑기. 후보마다 블록을 그려(`Tool.Vision.paint_prisms`) 사진마다 `mismatch_of(그린 지도, 보인 지도, 셀 곳)` 을 재고, 그 평균이 가장 작은 것을 고른다.

        `evidence` 는 사진마다 (윗면사각형들, 보인 지도, 셀 곳, 지도의 왼쪽 위가 원본에서 놓인 자리) 다. 보인 지도와 셀 곳은 원본 화소 격자다.
        후보는 윗면 무게중심 한 점에서 잰 35 mm 세로 모서리의 화면 변위와 몫이다(`Homography.vanishing_point_from_edge`). 몫은 0 과 1 사이만 본다 — 카메라가 블록 위에 있다.
        거친 격자를 원본 화소 격자에서 훑고, 앞선 몇 등을 `raster_scale` 배 격자에서 Nelder-Mead 로 다듬는다. 한 점에서 출발해 좁히면 틀린 답으로 수렴할 수 있어 넓게 먼저 본다.
        다듬기는 세 수를 모두 화소 단위로 잰다 — 몫은 무게중심에서 가장 먼 윗면 꼭짓점의 밑면 점이 1 px 움직이는 양을 한 단위로 삼는다.
        윗면은 받은 대로 둔다.
        """
        from cv2 import INTER_NEAREST as cv2_INTER_NEAREST, resize as cv2_resize
        from scipy.optimize import minimize as scipy_minimize

        corners = [point for upper_shapes, _, _, _ in evidence for shape in upper_shapes for point in shape]
        center = (sum(u for u, _ in corners) / len(corners), sum(v for _, v in corners) / len(corners))
        shrink_unit = 1.0 / max(math.dist(point, center) for point in corners)
        grids = {}

        def grid_of(scale):
            if scale not in grids:
                grids[scale] = [(cv2_resize(seen, None, fx=scale, fy=scale, interpolation=cv2_INTER_NEAREST),
                                 cv2_resize(region, None, fx=scale, fy=scale, interpolation=cv2_INTER_NEAREST)) for _, seen, region, _ in evidence]
            return grids[scale]

        def mismatch(edge_u_px, edge_v_px, shrink, scale):
            #: 몫이 범위 밖인 후보는 어긋남의 끝값을 받는다 — 물리로 있을 수 없다
            if not 0.0 < shrink < 1.0: return 1.0
            candidate = h35.replaced(vanishing_point=homography.vanishing_point_from_edge(h35, center, (edge_u_px, edge_v_px), shrink))
            total = 0.0
            for (upper_shapes, _, _, origin_px), (seen, region) in zip(evidence, grid_of(scale)):
                shapes = [(shape, tuple(homography.under_point_px(candidate, u_px, v_px) for u_px, v_px in shape)) for shape in upper_shapes]
                total += mismatch_of(Tool.Vision.paint_prisms(seen.shape, shapes, origin_px, scale), seen, region)
            return total / len(evidence)

        steps = round(2.0 * search.offset_span__px / search.offset_step__px) + 1
        offsets_px = [-search.offset_span__px + index * search.offset_step__px for index in range(steps)]
        coarse = sorted((mismatch(edge_u_px, edge_v_px, shrink, 1), (edge_u_px, edge_v_px, shrink))
                        for edge_u_px in offsets_px for edge_v_px in offsets_px for shrink in search.shrink_grid)

        def refined(start):
            edge_u_px, edge_v_px, shrink = start
            cost = lambda moved: mismatch(edge_u_px + moved[0], edge_v_px + moved[1], shrink + moved[2] * shrink_unit, raster_scale)
            half = search.offset_step__px / 2.0
            simplex = [(0.0, 0.0, 0.0), (half, 0.0, 0.0), (0.0, half, 0.0), (0.0, 0.0, half)]
            result = scipy_minimize(cost, simplex[0], method="Nelder-Mead", options=dict(initial_simplex=simplex, xatol=1.0 / raster_scale, fatol=0.0))
            return result.fun, (edge_u_px + result.x[0], edge_v_px + result.x[1], shrink + result.x[2] * shrink_unit)

        _, (edge_u_px, edge_v_px, shrink) = min(refined(start) for _, start in coarse[:search.refine_starts])
        return homography.vanishing_point_from_edge(h35, center, (edge_u_px, edge_v_px), shrink)

    class Collector:
        """아핀 대응점 수집의 비전 쪽. 로봇 워커(`RobotBus.Job.COLLECT`)가 대피할 때마다 `look` 을 부르고, 첫 단계가 끝나면 `more` 가 둘째 단계 자리를 정하고, 끝나면 `finish` 가 아핀을 푼다.

        두 단계다. 첫 단계는 가동범위 가운데 세 자리(`Config.Robot.bootstrap_points`)로 대략의 아핀을 내고, 그것으로 작업영역을 로봇 좌표로 옮겨 둘째 단계 자리를 그 안에 편다(`layout`) — 카메라가 온전히 보는 곳에만 놓는다.
        가운데에는 손목을 반 바퀴 더 돌려 한 번 더 놓는다. 그 관측은 대응점이 아니라 이동 성분 관측이다(`Config.Dataset.EraValues.Affine` 의 `pivot`) — 행렬의 선형 부분은 대응점이 내고 이동 성분은 이것이 낸다.
        수집마다 폴더 하나에 영상(카메라 워커가 받은 장) · 단계 기록(`trace.jsonl`) · 자리마다 본 장 · 끝의 카메라 기준 장면(`reference_scene`) · 결과(`result.json`)를 남긴다 — 어긋남의 원인을 되짚는 기록이다.
        쓰기는 모두 쓰기 주인(`EraState.writer`)에 맡긴다 — 맡긴 차례대로 쓰므로 단계 기록의 줄 차례가 부른 차례다.
        회차에 담긴 아핀은 `result.json` 의 `matrix` 와 같은 수라, 그 회차의 카메라 기준 장면은 행렬이 같은 수집 폴더에 있다.
        단계 기록의 `frame` 은 녹화를 시작한 뒤 받은 장 수라 영상의 몇 번째 장인지 가리킨다.
        다시 무는 자리는 `regrab` 이 낸다 — 대략 아핀이 선 뒤로는 방금 본 블록을 문다.
        `look` · `more` · `regrab` · `snap` · `reference_scene` · `note` · `finish` 는 로봇 워커 스레드에서, `hear` 는 화면 스레드에서 불린다.
        현행 값에 담는 일은 `finish` 가 하고(`EraState.edit`), 담긴 뒤에 결과를 `result` 에 놓는다 — 화면은 알리기만 한다.
        """

        REFERENCE_SCENE = "reference"  # 수집 끝 카메라 기준 장면의 파일 이름(확장자 앞). 수집 폴더마다 하나다

        class Result(NamedTuple):
            """수집 한 번의 결과."""

            reason: str  # 수집이 끝난 까닭
            pairs: tuple  # 회차 문서 `affine.pairs` 의 항목들(`Tool.JsonNode`) — 쓸 만했던 자리만
            pivot: "Tool.JsonNode | None"  # 회차 문서 `affine.pivot` 의 꼴 — 가운데의 두 관측. 둘 다 봤을 때만 선다
            matrix: tuple | None  # 적합 대응점이 셋 이상이고 이동 성분 관측이 있으면 푼 2x3. 이동 성분은 `pivot` 이 낸 것이다
            fit_mm: tuple  # 적합 대응점의 재투영 거리. 이동 성분을 갈아 끼우기 전 행렬로 잰다 — 대응점은 같은 어긋남을 지녀 그 행렬과 맞는다
            holdout_mm: tuple  # 확인점의 재투영 거리. 같은 행렬로 잰다
            revisit_px: tuple  # 다시 놓은 점이 첫 관측에서 벗어난 화소 거리 — 탈조를 본다
            condition: float | None  # 적합 대응점 배치의 조건수
            offset_mm: float | None  # 처음 놓은 블록 중심이 손목 축에서 어긋난 거리, 상면 mm
            shift_mm: float | None  # 이동 성분이 옮겨 간 거리, 로봇 기저 mm — 갈아 끼우기 전 행렬로 집으면 그 자리에서 이만큼 빗나간다
            accepted: bool  # 행렬이 섰고 확인점이 있으며 적합 · 확인점 모두 허용 잔차 안

        bus: CameraBus
        state: EraState  # 수집 끝에 대응점 · 이동 성분 관측 · 채택된 행렬을 담는 현행 값
        vision_algorithm: "Config.VisionAlgorithm"
        era_values: "Config.Dataset.EraValues"  # 수집을 시작한 때의 현행 값
        calc: "Calc"  # 대피 뒤 관측 한 장을 계산한다
        robot: "Config.Robot"  # 로봇 규격(`robot.json`) — 수집 규격(`motion.calibration`)을 여기서 읽는다
        folder: Path  # 이 수집의 기록 폴더
        layout: Any  # (작업영역을 로봇 좌표로 옮긴 다각형, 여유 mm) → 둘째 단계 자리(`Config.Robot.Motion.Calibration.Point` 들)
        pairs: list  # 회차 문서 `affine.pairs` 의 항목들(`Tool.JsonNode`) — 쓸 만했던 자리만
        looked: int = 0  # 놓고 본 차례. 못 쓴 관측도 센다 — 밀림 식이 이웃한 차례끼리만 식을 세운다
        moves: list  # 쓸 만했던 관측의 (이름, 차례, 화소, 놓은 자리, 손목 더 돌린 각). 다시 문 자리는 `grabbed` 가 든다
        grabbed: dict  # 자리 이름 → 본 뒤 다시 문 로봇 XY
        turned: dict  # 손목을 더 돌려 놓은 관측 :: 같은 자리에 먼저 놓은 대응점 이름 → 검출 중심 화소
        seen: dict  # 자리 이름 → 쓸 만했던 관측의 블록(`Entity.Piece`)
        rough: "Config.Dataset.EraValues.Affine | None" = None  # 첫 단계 대응점으로 푼 대략 아핀. 둘째 단계 자리와 다시 무는 자리를 이것으로 낸다
        last_xy: tuple | None = None  # 앞 자리에서 블록을 다시 문 로봇 XY. 못 문 블록이 거기 남았는지 가린다
        planned: bool = False  # 둘째 단계 자리를 정하러 갔는가
        unplanned: str = ""  # 못 정했으면 그 까닭
        result: Tool.Slot  # `Result`. 수집이 끝나기 전에는 비어 있다
        started: float  # 수집을 시작한 시각. 단조 시계, 초
        first_frame: int  # 수집을 시작할 때까지 카메라가 받은 장 수. 단계 기록의 `frame` 은 여기서부터 센다

        def __init__(self, bus: CameraBus, state: EraState, vision_algorithm: "Config.VisionAlgorithm", era_values: "Config.Dataset.EraValues", route: "Calc.Pre.Route",
                     robot: "Config.Robot", folder: Path, layout: Any):
            self.bus = bus
            self.state = state
            self.vision_algorithm = vision_algorithm
            self.era_values = era_values
            self.calc = Calc(vision_algorithm, era_values, route)
            self.robot = robot
            self.folder = folder
            self.layout = layout
            self.pairs = []
            self.moves = []
            self.grabbed = {}
            self.turned = {}
            self.seen = {}
            self.result = Tool.Slot()
            self.started = time.monotonic()
            self.first_frame = bus.grabbed.get()

        def _write(self, **line: Any) -> None:
            """단계 기록 한 줄. 시각과 장 번호는 부른 때의 것이다."""
            line = {"t_s": round(time.monotonic() - self.started, 3), "frame": self.bus.grabbed.get() - self.first_frame, **line}

            def appended() -> None:
                with (self.folder / "trace.jsonl").open("a", encoding="utf-8") as file_pointer:
                    file_pointer.write(json.dumps(line, ensure_ascii=False) + "\n")

            self.state.writer.submit(appended)

        def note(self, text: str) -> None:
            """로봇 워커의 단계 하나."""
            self._write(step=text)

        def hear(self, text: str) -> None:
            """화면 기록에 올라간 한 줄 — 워커들이 스스로 한 말(이동량 · 거부 · 알람)을 함께 남긴다."""
            self._write(said=text)

        def look(self, point: "Config.Robot.Motion.Calibration.Point") -> bool:
            """팔이 대피한 채 한 장을 보고, 블록이 하나이고 투입점 블록의 규격이며 그 윗면이 작업영역 안이면 쓴다. 떨림이 가라앉기를 기다린 뒤 새로 받은 장만 쓴다.

            윗면이 작업영역 경계에 걸치면 잘린 마스크로 재여 중심이 밀린다. 조금 걸치면 규격 사각형이 작업영역 밖으로 나가고(`WorkArea.encloses`), 많이 걸치면 남은 부분이 더 짧은 규격으로 잡힌다 — 둘 다 버린다. 놓은 것은 투입점 블록 하나라 규격을 안다.
            손목을 더 돌려 놓은 관측은 같은 자리에 먼저 놓은 대응점의 짝(이동 성분 관측)으로 두고, 나머지는 대응점으로 둔다.
            대략 아핀이 선 뒤로는 본 블록이 이번 자리보다 앞 자리(블록을 다시 문 곳)에 가까우면 버린다 — 로봇이 붙음을 못 듣고 들어 올렸는데 실제로 못 물어 블록이 앞 자리에 남은 경우다.
            그 블록의 자리는 남겨 두어(`seen`) 다시 물 때 그곳을 문다.
            """
            from cv2 import imwrite as cv2_imwrite

            name, xy_mm, turn_deg = point.name, point.robot_xy_mm, point.turn_deg
            self.looked += 1
            frame = self.bus.fresh_frame(self.robot.motion.calibration.settle__s)
            self.state.writer.submit(cv2_imwrite, str(self.folder / f"{name}.png"), frame)
            entities = self.calc.observe(frame)
            if len(entities) != 1:
                self._write(look=name, blocks=len(entities), unsplit=len(self.calc.unsplit), kept=False)
                return False
            piece = entities[0]
            enclosed = self.vision_algorithm.work_area.encloses(self.era_values.work_area, piece.corners_px)
            if piece.block.length__mm != self.robot.motion.calibration.supply_length__mm or not enclosed:
                self._write(look=name, blocks=1, length_mm=piece.block.length__mm, outside_work_area=not enclosed, kept=False)
                return False
            pixel = self.vision_algorithm.homography.to_image(self.era_values.homography, piece.pose.x_mm, piece.pose.y_mm)
            self.seen[name] = piece
            if self.rough is not None and self.last_xy is not None:
                at = tuple(self.calc.scope_global.question_position(piece, self.rough))
                if math.dist(at, self.last_xy) < math.dist(at, xy_mm):
                    self._write(look=name, kept=False, left_behind=True, seen_robot_xy_mm=[round(v, 3) for v in at],
                                robot_xy_mm=[round(v, 3) for v in xy_mm], previous_xy_mm=[round(v, 3) for v in self.last_xy])
                    return False
            if turn_deg != 0.0:
                first = point.revisit_of
                if first not in {pair.name for pair in self.pairs}:
                    self._write(look=name, kept=False, turned_without_first=True)
                    return False
                self.turned[first] = pixel
                self.moves.append((name, self.looked, pixel, tuple(xy_mm), turn_deg))
                self._write(look=name, kept=True, turned_of=first, pixel_xy=[round(v, 3) for v in pixel], robot_xy_mm=[round(v, 3) for v in xy_mm])
                return True
            self.moves.append((name, self.looked, pixel, tuple(xy_mm), turn_deg))
            self.pairs.append(Tool.JsonNode({"name": name, "pixel_xy": pixel, "robot_xy__mm": tuple(xy_mm), "holdout": point.holdout, "revisit_of": point.revisit_of}))
            self._write(look=name, kept=True, pixel_xy=[round(v, 3) for v in pixel], robot_xy_mm=[round(v, 3) for v in xy_mm],
                        length_mm=piece.block.length__mm, angle_deg=round(piece.pose.angle_deg, 2))
            return True

        def more(self) -> tuple:
            r"""첫 단계가 끝났다. 모은 대응점으로 대략의 아핀을 풀어 작업영역을 로봇 좌표로 옮기고, 그 안의 둘째 단계 자리를 받는다(`layout`). 끝에 첫 자리를 한 번 더 놓아 탈조를 본다.

            둘째 단계는 한 번뿐이다 — 두 번째로 부르면 빈 튜플이다. 못 정하면 까닭을 기록에 남기고 빈 튜플을 낸다.
            여유는 대략 아핀의 오차에서 낸다. 검출 중심이 한 화소($\sigma$) 흔들린다고 보면, 간격 $L$ 의 세 자리가 정한 방위는 $\sqrt{2}\,\sigma / L$ 만큼 흔들리고, 가운데에서 $D$ 떨어진 곳은 $\sigma (1 + \sqrt{2} D / L)$ 만큼 빗나간다.
            $\sigma$ 는 작업영역 한가운데 축척으로 잰 한 화소(mm), $L$ 은 첫 단계 자리 사이의 가장 짧은 거리, $D$ 는 첫 단계 자리의 무게중심에서 옮긴 작업영역 꼭짓점까지의 가장 먼 거리다.
            """
            if self.planned: return ()
            self.planned = True
            to_world = partial(self.vision_algorithm.homography.to_world, self.era_values.homography)
            affine = self.era_values.affine.replaced(pairs=self.pairs)
            try:
                rough = affine.replaced(matrix=self.vision_algorithm.affine_transform.fitted(affine, to_world))
            except (Tool.Missing, ValueError) as failed:
                return self._unplanned(f"가운데 자리로 대략 아핀을 못 풀었다 :: {failed}")
            self.rough = rough
            region = tuple(self.vision_algorithm.affine_transform.to_robot(rough, *to_world(*corner)) for corner in self.era_values.work_area.polygon__px)
            placed_xy = [pair.robot_xy__mm for pair in affine.fit_pairs]
            center = (sum(x_mm for x_mm, _ in placed_xy) / len(placed_xy), sum(y_mm for _, y_mm in placed_xy) / len(placed_xy))
            spread_mm = min(math.dist(first, second) for first, second in itertools.combinations(placed_xy, 2))
            distance_mm = max(math.dist(center, vertex) for vertex in region)
            margin_mm = (1.0 + math.sqrt(2.0) * distance_mm / spread_mm) / self.era_values.ppm_inplane
            try:
                placed = self.layout(region, margin_mm)
            except Tool.Missing as missing:
                return self._unplanned(str(missing))
            first = self.pairs[0]
            self._write(plan=f"둘째 단계 {len(placed)} 자리", region_xy_mm=[[round(v, 2) for v in vertex] for vertex in region], margin_mm=round(margin_mm, 2))
            return tuple(placed) + (Config.Robot.Motion.Calibration.Point(f"r{first.name}", first.robot_xy__mm, 0.0, holdout=False, revisit_of=first.name),)

        def snap(self, label: str) -> None:
            """지금 장면을 `<이름표>.png` 로 한 장 남긴다. 로봇이 블록을 쥔 채 화면에 든 장면이다 — 로봇을 빼는 계산과 쥔 상태 판정의 자료다."""
            from cv2 import imwrite as cv2_imwrite

            self.state.writer.submit(cv2_imwrite, str(self.folder / f"{label}.png"), self.bus.frame.get())
            self._write(snap=label)

        def reference_scene(self) -> None:
            """로봇이 카메라 기준 장면 자리(`robot.json` `positions.camera_reference`)에 선 뒤 받은 장을 `<REFERENCE_SCENE>.png` 로 남긴다. 이 수집이 낸 아핀과 같은 때의 카메라를 같은 팔 자세로 견줄 기준 장면이다.

            섰다는 보고를 받은 때 슬롯에 든 장은 그 전에 찍혔을 수 있어, 안정화 대기 뒤 새로 받은 장을 쓴다(`CameraBus.fresh_frame`).
            """
            from cv2 import imwrite as cv2_imwrite

            self.state.writer.submit(cv2_imwrite, str(self.folder / f"{self.REFERENCE_SCENE}.png"), self.bus.fresh_frame(self.robot.motion.calibration.settle__s))
            self._write(scene=self.REFERENCE_SCENE)

        def regrab(self, point: "Config.Robot.Motion.Calibration.Point") -> tuple[float, float]:
            """그 자리에서 다시 물 로봇 XY. 대략 아핀(`more`)이 섰고 방금 쓸 만한 관측이 있으면 본 블록 중심을 그 아핀으로 옮긴 자리, 아니면 놓은 자리다.

            다시 물 때마다 블록이 패드 밑에서 조금씩 밀린다. 놓은 자리를 다시 물면 그 밀림이 쌓여 패드가 블록 가장자리로 간다. 본 블록을 물면 한 번 몫으로 묶인다.
            대략 아핀은 첫 단계의 (블록 중심, 놓은 패드 자리) 로 풀었으므로, 그것이 옮긴 자리를 물면 첫 단계와 같은 물림이 된다.
            """
            name, xy_mm = point.name, point.robot_xy_mm
            piece = self.seen.get(name)
            again = tuple(xy_mm) if self.rough is None or piece is None else tuple(self.calc.scope_global.question_position(piece, self.rough))
            if again != tuple(xy_mm):
                self._write(regrab=name, robot_xy_mm=[round(v, 3) for v in again], placed_xy_mm=[round(v, 3) for v in xy_mm])
            self.grabbed[name] = again
            self.last_xy = again
            return again

        def _unplanned(self, why: str) -> tuple:
            self.unplanned = f"둘째 단계를 못 정했다 :: {why}"
            self._write(plan=self.unplanned)
            return ()

        def finish(self, reason: str) -> None:
            """수집이 끝났다. 적합 대응점으로 아핀을 풀고 이동 성분을 가운데 두 관측으로 갈아 끼운다(`AffineTransform.pivoted`). 적합 · 확인점 잔차와 재방문 변위를 잰다. 허용 잔차는 `AffineTransform.max_residual_tol__mm` 다.

            잔차는 갈아 끼우기 전 행렬로 잰다. 확인점이나 이동 성분 관측이 없으면 채택하지 않는다 — 앞의 것이 없으면 오차를 모르고, 뒤의 것이 없으면 이동 성분에 패드 어긋남이 든다.
            밀림 식(`AffineTransform.drift_fitted`)으로도 풀어 결과 기록에 나란히 남긴다. 채택은 대응점 풀이다 — 두 풀이가 작업영역에서 얼마나 다른지(`drift.gap_mm`)는 작업영역 꼭짓점에서 잰다. 두 아핀의 차도 아핀이라 볼록 다각형 안에서는 꼭짓점이 가장 크다.
            """
            if self.unplanned:
                reason = f"{reason} · {self.unplanned}"
            affine = self.era_values.affine.replaced(pairs=self.pairs)
            to_world = partial(self.vision_algorithm.homography.to_world, self.era_values.homography)
            fitted, fit_mm, holdout_mm, condition = None, (), (), None
            if len(affine.fit_pairs) >= self.vision_algorithm.affine_transform.MIN_PAIRS:
                condition = self.vision_algorithm.affine_transform.design_condition_number(affine, to_world)
                try:
                    fitted = self.vision_algorithm.affine_transform.fitted(affine, to_world)
                except ValueError as singular:
                    #: 대응점이 한 줄이나 한 점에 몰리면 설계행렬이 특이하다 — 풀 수 없다는 것도 결과다
                    reason = f"{reason} · 아핀을 못 푼다 :: {singular}"
                if fitted is not None:
                    fit_mm = self.vision_algorithm.affine_transform.residuals_mm(fitted, to_world, affine.fit_pairs)
                    holdout_mm = self.vision_algorithm.affine_transform.residuals_mm(fitted, to_world, affine.holdout_pairs) if affine.holdout_pairs else ()
            first = {pair.name: pair for pair in self.pairs}
            revisit_px = tuple(math.dist(pair.pixel_xy, first[pair.revisit_of].pixel_xy)
                               for pair in affine.revisit_pairs if pair.revisit_of in first)
            pivot, matrix, offset_mm, shift_mm = None, None, None, None
            for name, pixel in self.turned.items():
                pivot = Tool.JsonNode({"robot_xy__mm": first[name].robot_xy__mm, "pixel_xy": (first[name].pixel_xy, pixel)})
                offset_mm = math.hypot(*self.vision_algorithm.affine_transform.pivot_offset_mm(affine.replaced(pivot=pivot), to_world))
            if fitted is not None and pivot is not None:
                matrix = self.vision_algorithm.affine_transform.pivoted(affine.replaced(pivot=pivot), fitted, to_world)
                shift_mm = math.hypot(matrix[0][2] - fitted[0][2], matrix[1][2] - fitted[1][2])
            accepted = (matrix is not None and bool(holdout_mm)
                        and all(self.vision_algorithm.affine_transform.is_residual_accepted(max(distances)) for distances in (fit_mm, holdout_mm)))
            drift = None
            if pivot is not None:
                moves = tuple(Config.VisionAlgorithm.AffineTransform.Move(name, order, pixel, placed, self.grabbed.get(name, placed), turn)
                              for name, order, pixel, placed, turn in self.moves)
                try:
                    solved = self.vision_algorithm.affine_transform.drift_fitted(to_world, moves)
                    #: `pivoted` 는 받은 행렬의 선형 부분만 쓰고 이동 성분을 새로 낸다 — 셋째 열 0 은 자리만 채운다
                    drift_matrix = self.vision_algorithm.affine_transform.pivoted(affine.replaced(pivot=pivot),
                        ((solved.linear[0][0], solved.linear[0][1], 0.0), (solved.linear[1][0], solved.linear[1][1], 0.0)), to_world)
                    corners_mm = [to_world(*corner) for corner in self.era_values.work_area.polygon__px]
                    gap_mm = None if matrix is None else max(
                        math.dist(*(self.vision_algorithm.affine_transform.to_robot(affine.replaced(matrix=one), x_mm, y_mm) for one in (matrix, drift_matrix)))
                        for x_mm, y_mm in corners_mm)
                    drift = dict(matrix=[list(row) for row in drift_matrix],
                                 drift_mm={f"{turn:g}": [round(v, 3) for v in shift] for turn, shift in solved.drift_mm.items()},
                                 residuals_mm=[round(v, 3) for v in solved.residuals_mm],
                                 gap_mm=None if gap_mm is None else round(gap_mm, 3))
                except (Tool.Missing, ValueError) as failed:
                    drift = dict(failed=str(failed))
            result = self.Result(reason, tuple(self.pairs), pivot, matrix, tuple(fit_mm), tuple(holdout_mm), revisit_px, condition, offset_mm, shift_mm, accepted)
            summary = dict(reason=reason, pairs=len(self.pairs), fit_pairs=len(affine.fit_pairs), holdout_pairs=len(affine.holdout_pairs),
                           pivot=None if pivot is None else Tool.JsonNode.plain(pivot),
                           matrix=None if matrix is None else [list(row) for row in matrix],
                           matrix_fitted=None if fitted is None else [list(row) for row in fitted],
                           fit_mm=[round(v, 3) for v in fit_mm], holdout_mm=[round(v, 3) for v in holdout_mm],
                           revisit_px=[round(v, 3) for v in revisit_px], condition=None if condition is None else round(condition, 3),
                           offset_mm=None if offset_mm is None else round(offset_mm, 3), shift_mm=None if shift_mm is None else round(shift_mm, 3),
                           accepted=accepted,
                           rotation_deg=None if matrix is None else round(affine.replaced(matrix=matrix).rotation_deg, 3),
                           scale=None if matrix is None else round(affine.replaced(matrix=matrix).scale, 5),
                           drift=drift)
            self.state.writer.submit(Config.Document.write, self.folder / "result.json", summary)
            self._write(finish=reason, accepted=accepted)
            #: 대응점 원본과 이동 성분 관측은 늘 담고 행렬은 채택될 때만 담는다 — 안 담으면 현행 값의 행렬이 그대로 남는다. 회차에 남기는 것은 촬영이다(실시간은 메모리)
            changes = {"pairs": self.pairs, "pivot": pivot} | ({"matrix": matrix} if accepted else {})
            self.state.edit("affine", changes).result()
            self.result.put(result)

# =========================================================================
# 3. 계산
# =========================================================================


class Calc:
    """계산. `CALC`.

    전처리가 한 프레임에서 이미지와 마스크를 내고, 질문이 그것을 필요에 따라 불러 개체를 확정한다.

    설정과 값은 설 때 한 번 받는다 — 영상 설정(`Config.VisionAlgorithm`) · 회차 값 한 벌(`Config.Dataset.EraValues`) · 전처리 경로(`Pre.Route`)다.
    현행 값이 바뀌면 부르는 쪽이 새로 세운다. 단계와 범위는 처음에 한 번 서고, 전처리 목록은 프레임마다 비운다.
    프레임을 넘겨 드는 것은 메모리(`OUTCOME` :: 직전 프레임 · 직전 개체 목록)뿐이다.
    """

    class Pre:
        """전처리. `PRE`. 한 프레임에서 이미지와 마스크를 낸다.

        단계는 이 차례대로 선다 ::

            채널 → 정규화 → { 전역 문턱 → 실루엣 · 상면 }
                          { 영역 추정 → 경계 }       → 단순화 → 면분할

        단계마다 앞 단계의 결과와 **선택**을 받아 제 결과를 낸다.
        이미지는 작업영역으로 자른 격자(`Tool.Vision.Crop`)에 있다 — 원본 좌표는 `origin_px` 를 더한 것이다.

        질문이 받는 `pre` 가 이 인스턴스다. 질문은 경로(`Route`)로 결과를 부르고, 한 프레임 안에서 이미 낸 것은 목록에서 다시 쓴다.
        목록의 열쇠는 그 결과까지 고른 선택지의 차례다.
        """

        class Route(NamedTuple):
            """전처리 경로 한 벌. 단계마다 고른 선택지다."""

            channel: Enum  # `Tool.Vision.ColorSpace` 의 성분 하나
            normalization: "Calc.Pre.Normalization.Choice"
            silhouette: "Calc.Pre.Threshold.Choice"
            topface: "Calc.Pre.Threshold.Choice"

            @classmethod
            def of(cls, chosen: "Config.VisionAlgorithm.Calc.Route") -> "Calc.Pre.Route":
                """설정이 고른 이름을 부품으로 옮긴다. 채널은 `색공간.성분`, 나머지는 선택지 이름이다."""
                space, component = chosen.channel.split(".")
                return cls(getattr(getattr(Tool.Vision.ColorSpace, space), component),
                           Calc.Pre.Normalization.Choice[chosen.normalization],
                           Calc.Pre.Threshold.Choice[chosen.silhouette],
                           Calc.Pre.Threshold.Choice[chosen.topface])

        class Channel:
            """채널. `CHANNEL`. 카메라 프레임에서 채널을 뽑아 작업영역으로 자른다. 채널은 하나만 고른다.

            선택지는 `Tool.Vision.ColorSpace` 의 성분이다. 여백은 작업영역 중심 축척으로 블록 단축만큼 둔다(`WorkArea.margin_mm`).
            """

            vision_algorithm: "Config.VisionAlgorithm"
            era_values: "Config.Dataset.EraValues"  # 작업영역 다각형과 그 중심 축척을 내는 H35 를 든다

            def __init__(self, vision_algorithm, era_values):
                self.vision_algorithm = vision_algorithm
                self.era_values = era_values

            def roi_crop(self, frame, choice):
                """작업영역 이미지. `PRE_ROI_CROP`. 다각형 안팎은 `mask` 로 가른다."""
                margin_px = self.vision_algorithm.facade_crop_margin_px(self.era_values.ppm_inplane)
                return Tool.Vision.crop_to_polygon(Tool.Vision.extract_channel(frame, choice), self.era_values.work_area.polygon__px, margin_px)

        class Normalization:
            """정규화. `NORMALIZATION`. 작업영역 이미지를 다단으로 누적하고 선택적으로 합성한다."""

            class Choice(Enum):
                """선택지. 전역 통계는 작업영역 안쪽 화소로만 잰다."""

                NOTHING = auto()  # 원본 유지
                EQUALIZE_HIST = auto()  # 히스토그램 평활화
                WHITEN = auto()  # 백색화

            vision_algorithm: "Config.VisionAlgorithm"

            def __init__(self, vision_algorithm):
                self.vision_algorithm = vision_algorithm

            def multi_normalization(self, roi_crop, choice):
                """전처리 이미지. `PRE_MULTI_NORMALIZATION`. 작업영역 이미지와 같은 꼴로 낸다 — 마스크와 자리는 그대로다."""
                match choice:
                    case Calc.Pre.Normalization.Choice.NOTHING: image = roi_crop.image
                    case Calc.Pre.Normalization.Choice.EQUALIZE_HIST: image = Tool.Vision.equalize_hist(roi_crop.image, roi_crop.mask)
                    case Calc.Pre.Normalization.Choice.WHITEN:
                        image = Tool.Vision.whiten(roi_crop.image, roi_crop.mask, Tool.EPS, self.vision_algorithm.preprocess.whiten_sigma_span)
                return roi_crop._replace(image=image)

        class Threshold:
            """전역 문턱. `THRESHOLD`. 전처리 이미지를 마스크로 가른다. 문턱은 작업영역 안쪽 화소로 고르고, 바깥은 검정이다."""

            class Choice(Enum):
                """선택지. 문턱을 스스로 고르는 것들이라 받는 값이 없다."""

                OTSU = auto()  # 오츠
                TRIANGLE = auto()  # 삼각형
                ISODATA = auto()  # 리들러-칼바드
                MULTI_OTSU = auto()  # 다단계 오츠. 실루엣은 낮은 문턱 위, 상면은 높은 문턱 위

            @staticmethod
            def _above(normalized, choice, side_of_multi):
                """고른 문턱보다 밝은 곳. 다단계 오츠는 두 문턱 가운데 `side_of_multi` 가 고른 쪽이다."""
                image, mask = normalized.image, normalized.mask
                match choice:
                    case Calc.Pre.Threshold.Choice.OTSU: return Tool.Vision.otsu_threshold(image, mask)[1]
                    case Calc.Pre.Threshold.Choice.TRIANGLE: return Tool.Vision.triangle_threshold(image, mask)[1]
                    case Calc.Pre.Threshold.Choice.ISODATA: return Tool.Vision.isodata_threshold(image, mask)[1]
                    case Calc.Pre.Threshold.Choice.MULTI_OTSU: return side_of_multi(Tool.Vision.multi_otsu_threshold(image, mask))

            def silhouette(self, multi_normalization, choice):
                """실루엣 마스크. `PRE_SILHOUETTE`. 매트보다 밝은 곳 — 윗면과 보이는 옆면이다."""
                return self._above(multi_normalization, choice, lambda levels: levels.above_low)

            def topface(self, multi_normalization, choice):
                """상면 마스크. `PRE_TOPFACE`. 가장 밝은 무리 — 윗면이다."""
                return self._above(multi_normalization, choice, lambda levels: levels.above_high)

        class Boundary:
            """영역 추정. `BOUNDARY`. 전처리 이미지에서 경계를 뽑는다."""

            def boundary(self, multi_normalization, choice):
                """경계 마스크. `PRE_BOUNDARY`."""

        class Simplify:
            """단순화. `SIMPLIFY`. 마스크 하나를 단순한 형상으로 줄인다.

            실루엣 · 상면 · 경계가 각각 하나씩 들어온다. 결과는 면분할이 받는다.
            """

            def simplify(self, mask, choice):
                """단순화한 마스크 하나."""

        class Multi:
            """면분할. `MULTI`. 단순화 결과와 실루엣으로 면을 나눈다."""

            class Choice(Enum):
                """선택지."""

                PRISM_FACE = auto()  # 윗면 · 옆면. 상면이 윗면, 실루엣에서 상면을 뺀 곳이 옆면(`Tool.Vision.PrismFace`)

            def multi(self, simplified, silhouette, choice):
                """분할면. `PRE_MULTI`. 부류 지도다 — 화소값이 면 부류다."""
                from numpy import uint8 as np_uint8, where as np_where

                match choice:
                    case Calc.Pre.Multi.Choice.PRISM_FACE:
                        side = np_where(silhouette > 0, int(Tool.Vision.PrismFace.SIDE), int(Tool.Vision.PrismFace.NONE))
                        return np_where(simplified > 0, int(Tool.Vision.PrismFace.TOP), side).astype(np_uint8)

        channel: "Calc.Pre.Channel"
        normalization: "Calc.Pre.Normalization"
        threshold: "Calc.Pre.Threshold"
        boundary: "Calc.Pre.Boundary"
        simplify: "Calc.Pre.Simplify"
        multi: "Calc.Pre.Multi"
        frame: Any  # 지금 계산하는 프레임. 원본 화소
        pre_list: dict  # `PRE_LIST`. 전처리 이미지 목록 — 그 결과까지 고른 선택지의 차례 → 결과
        pre_list_mask: dict  # `PRE_LIST_MASK`. 전처리 마스크 목록 — 열쇠는 위와 같다

        def __init__(self, vision_algorithm, era_values):
            self.channel = self.Channel(vision_algorithm, era_values)
            self.normalization = self.Normalization(vision_algorithm)
            self.threshold = self.Threshold()
            self.boundary = self.Boundary()
            self.simplify = self.Simplify()
            self.multi = self.Multi()
            self.reset(None)

        def reset(self, frame):
            """새 프레임을 받는다. 지난 프레임의 목록을 비운다."""
            self.frame = frame
            self.pre_list = {}
            self.pre_list_mask = {}

        @staticmethod
        def _kept(store, key, make):
            if key not in store: store[key] = make()
            return store[key]

        # 경로로 부르는 자리 :: 질문이 부른다. 앞 단계는 목록에 있으면 다시 쓴다

        def roi(self, route):
            """작업영역 이미지(`Tool.Vision.Crop`)."""
            return self._kept(self.pre_list, (route.channel,), lambda: self.channel.roi_crop(self.frame, route.channel))

        def gray(self):
            """작업영역의 회색 밝기 이미지(`Tool.Vision.Crop`). 경로의 채널과 상관없이 밝기를 물을 때 쓴다."""
            channel = Tool.Vision.ColorSpace.GRAY.GRAY
            return self._kept(self.pre_list, (channel,), lambda: self.channel.roi_crop(self.frame, channel))

        def image(self, route):
            """전처리 이미지(`Tool.Vision.Crop`)."""
            return self._kept(self.pre_list, (route.channel, route.normalization),
                              lambda: self.normalization.multi_normalization(self.roi(route), route.normalization))

        def silhouette(self, route):
            """실루엣 마스크. 작업영역 격자다."""
            return self._kept(self.pre_list_mask, (route.channel, route.normalization, "silhouette", route.silhouette),
                              lambda: self.threshold.silhouette(self.image(route), route.silhouette))

        def topface(self, route):
            """상면 마스크. 작업영역 격자다."""
            return self._kept(self.pre_list_mask, (route.channel, route.normalization, "topface", route.topface),
                              lambda: self.threshold.topface(self.image(route), route.topface))

        def faces(self, route):
            """윗면 · 옆면 부류 지도. 작업영역 격자다. 단순화는 거치지 않는다."""
            return self._kept(self.pre_list_mask, (route, "faces"),
                              lambda: self.multi.multi(self.topface(route), self.silhouette(route), Calc.Pre.Multi.Choice.PRISM_FACE))

    class Pipe:
        """질문. `PIPE`. 전처리 결과를 불러 인식 계통과 전환 계통을 거친다.

        인식 계통이 전역 → 덩어리 → 단품 순으로 좁혀 `Piece` 를 내고, 전환 계통이 그것을 받는다.
        메서드 이름은 판정이 `question_*`, 처리가 `process_*` 다.
        범위마다 `run` 이 그 범위를 한 번 돈다. 범위 안에서 무엇을 어떤 차례로 물을지는 `run` 이 정한다.
        범위는 설 때 영상 설정 · 회차 값 한 벌 · 전처리 경로를 받는다.
        """

        class Perception:
            """인식 계통. `SYSTEM_PERCEPTION`.

            **블록은 떨어뜨리지 않는다.** 들어오는 것은 블록 · 사람 손 · 로봇뿐이고, 떨어지는 것은 가장 작은 블록보다 한참 작은 노이즈다.
            크기는 두 번 묻는다.
            노이즈인지는 화소 격자에서 가른다(`is_sized`) — 덩어리 넓이가 제 둘레의 양자화 띠보다 넓어야 한다.
            상면 사각형에 맞출 만한지는 상면 mm² 를 적합 입력 하한(`RectFit.area_min_mm2` — 가장 작은 블록 윗면 35 × 35 mm 에 비율을 곱한 것)과 견준다(`is_fittable`).
            상면 mm² 로 재므로 자리마다 다른 축척이 문턱에 섞이지 않는다.
            """

            @staticmethod
            def lumps_of(mask, origin_px, era_values):
                """마스크의 연결 성분마다 `Lump` 하나. 윤곽은 원본 화소, 면적은 윤곽을 H35 로 상면에 옮겨 잰다."""
                from cv2 import CHAIN_APPROX_NONE as cv2_CHAIN_APPROX_NONE, RETR_EXTERNAL as cv2_RETR_EXTERNAL, contourArea as cv2_contourArea
                from numpy import float32 as np_float32

                lumps = []
                for component in Tool.Geometry.Partition.by_connected_components(mask, 1):
                    contour, = Tool.Vision.find_contours(component, cv2_RETR_EXTERNAL, cv2_CHAIN_APPROX_NONE)
                    contour_px = tuple((float(x) + origin_px[0], float(y) + origin_px[1]) for x, y in contour.reshape(-1, 2))
                    area_mm2 = float(cv2_contourArea(Tool.Fit.Homography.project(contour_px, era_values.homography.matrix).astype(np_float32)))
                    lumps.append(Entity.Lump(contour_px, area_mm2))
                return tuple(lumps)

            @staticmethod
            def is_sized(lump, vision_algorithm):
                """노이즈보다 큰가. 덩어리 넓이가 제 둘레의 화소 양자화 띠보다 넓은가(`Quantization.is_resolved`).

                잡음의 크기를 블록이 아니라 화소 격자에서 낸다 — 블록은 탈락하지 않고 탈락하는 것은 노이즈다. 그래서 하한이 아주 작다.
                """
                from cv2 import contourArea as cv2_contourArea
                from numpy import array as np_array, float32 as np_float32

                return vision_algorithm.quantization.is_resolved(float(cv2_contourArea(np_array(lump.contour_px, np_float32))), lump.perimeter_px)

            @staticmethod
            def is_fittable(lump, vision_algorithm):
                """상면 사각형 적합에 넣을 만한가. 상면 mm² 가 사각형 적합기 입력 하한(`Config.VisionAlgorithm.facade_rect_fit_area_min_mm2`)을 넘는가.

                덩어리 안 상면 조각을 셀 때 쓴다 — "명확한 단품?" 은 사각형으로 맞출 만한 상면 조각이 하나인지 묻는다. 그보다 작은 조각은 상면으로 맞출 수 없다.
                """
                return lump.area_mm2 >= vision_algorithm.facade_rect_fit_area_min_mm2

            @staticmethod
            def region_of(lump, shape, origin_px):
                """덩어리가 차지하는 곳. 작업영역 격자의 마스크다 — 윤곽 안은 구멍까지 채운다."""
                return Tool.Vision.fill_polygons(shape, [[(x - origin_px[0], y - origin_px[1]) for x, y in lump.contour_px]], 255)

            @staticmethod
            def tops_in(lump, pre, route, vision_algorithm, era_values):
                """덩어리 안의 상면 조각들. 조각마다 `Lump` 하나이고, 상면으로 맞출 만한 것만 센다(`is_fittable`)."""
                topface = pre.topface(route)
                origin_px = pre.roi(route).origin_px
                inside = Tool.Vision.mask_and(topface, Calc.Pipe.Perception.region_of(lump, topface.shape, origin_px))
                return tuple(top for top in Calc.Pipe.Perception.lumps_of(inside, origin_px, era_values) if Calc.Pipe.Perception.is_fittable(top, vision_algorithm))

            class Scene:
                """전역 단위. `SCOPE_SCENE`. 프레임 전체를 보고 덩어리로 나눈다. 결과는 `Lump` 들이다."""

                vision_algorithm: "Config.VisionAlgorithm"
                era_values: "Config.Dataset.EraValues"
                route: "Calc.Pre.Route"

                def __init__(self, vision_algorithm, era_values, route):
                    self.vision_algorithm = vision_algorithm
                    self.era_values = era_values
                    self.route = route

                def run(self, pre, previous_frame):
                    """전역 단위를 한 번 돈다. `Lump` 들을 낸다."""
                    if not self.question_exist(pre): return ()
                    return tuple(lump for lump in self.process_cluster(pre) if self.question_size(lump))

                def question_stop(self, pre, previous_frame):
                    """프레임 정적인가? 차분 오차 수준으로 평가한다."""

                def question_exist(self, pre):
                    """존재하나? 무엇이라도 있어야 검사를 시작한다. 작업영역 안에 바닥 밝기(`Preprocess.brightness_floor__gray`)보다 밝은 화소가 있는가.

                    자동 문턱은 늘 무리를 가르므로, 블록이 없는 매트에서도 매트 결을 실루엣으로 낸다 — 흰 것이 하나도 없으면 그 실루엣은 블록이 아니다.
                    """
                    crop = pre.gray()
                    return bool(((crop.image > self.vision_algorithm.preprocess.brightness_floor__gray) & (crop.mask > 0)).any())

                def question_size(self, lump):
                    """유효한 크기인가? 노이즈 먼지보다 커야 한다. 연결 성분 하나마다 묻는다."""
                    return Calc.Pipe.Perception.is_sized(lump, self.vision_algorithm)

                def process_cluster(self, pre):
                    """클러스터링. 실루엣의 연결 성분마다 덩어리 하나로 나눈다."""
                    return Calc.Pipe.Perception.lumps_of(pre.silhouette(self.route), pre.roi(self.route).origin_px, self.era_values)

            class Blob:
                """덩어리 단위. `SCOPE_BLOB`. 덩어리 하나를 단품으로 가른다. 결과는 `Piece` 들이다.

                단품 후보는 덩어리 그대로 넘긴다(`Lump`). 규격과 자세는 단품 단위가 맞춘다.
                """

                vision_algorithm: "Config.VisionAlgorithm"
                era_values: "Config.Dataset.EraValues"
                route: "Calc.Pre.Route"

                def __init__(self, vision_algorithm, era_values, route):
                    self.vision_algorithm = vision_algorithm
                    self.era_values = era_values
                    self.route = route

                def run(self, lump, pre):
                    """덩어리 하나를 한 번 돈다. 명확한 단품이면 그 덩어리를 단품 후보로 낸다.

                    명확한 단품이 아닌 덩어리는 아무것도 내지 않는다 — 가르는 경로(음영 · 노치 · 이음)가 받을 몫이고, `Calc.unsplit` 에 남는다.
                    """
                    return (lump,) if self.question_lump(lump, pre) else ()

                def question_block(self, lump, pre):
                    """명확한 뭉치? 대상 블록은 곡면이 거의 없다."""

                def question_lump(self, lump, pre):
                    """명확한 단품? 덩어리 안의 상면이 한 조각이면 단품으로 본다.

                    윗면 사이 골이 상면을 가르지 않을 만큼 맞닿은 블록은 한 조각으로 보인다 — 그 덩어리는 여기서 단품이 된다.
                    """
                    return len(Calc.Pipe.Perception.tops_in(lump, pre, self.route, self.vision_algorithm, self.era_values)) == 1

                def question_shade(self, lump, pre):
                    """음영이 있나? 카메라 노출이 적으면 상면 골이 보일 수 있다."""

                def question_concave(self, lump, pre):
                    """오목한가? 오목하면 조합 형상이다."""

                def question_notch(self, lump, pre):
                    """뾰족한가? 꼭지점 노치는 크기가 작다."""

                def question_side(self, lump, pre):
                    """옆이 보이나? 같은 사진이라도 수직뷰와 사선뷰가 나뉠 수 있다."""

                def process_shade(self, lump, pre):
                    """음영 기반 분리. 흰 영역을 가로지르는 음영을 흑색선으로 만들어 분리에 쓴다."""

                def process_vertex(self, lump, pre):
                    """꼭지점 이음. 흰색에서 Z 소실점 방향으로 긋고 회색 꼭지점과 비교한다."""

                def process_lineline(self, lump, pre):
                    """선↔선 이음. 불충분한 길이로 끊긴 벡터끼리 이어지는지 확인한다."""

                def process_linenotch(self, lump, pre):
                    """선↔점 이음. 불충분한 길이로 끊긴 벡터가 뾰족하게 들어간 끝점과 이어지는지 확인한다."""

                def process_notchnotch(self, lump, pre):
                    """점↔점 이음. 노치에서 연결 변의 수직 방향으로 이었을 때 분할 결과가 말이 되는지 확인한다."""

                def process_lump(self, lump, pre):
                    """덩어리 재설정. 명확한 단품이 빠진 영역에 구분색을 칠한다."""

            class Inst:
                """단품 단위. `SCOPE_INST`. 단품 하나의 형상을 확정한다."""

                vision_algorithm: "Config.VisionAlgorithm"
                era_values: "Config.Dataset.EraValues"
                route: "Calc.Pre.Route"

                def __init__(self, vision_algorithm, era_values, route):
                    self.vision_algorithm = vision_algorithm
                    self.era_values = era_values
                    self.route = route

                def run(self, piece, pre):
                    """단품 하나를 한 번 돈다. 형상이 확정된 `Piece` 를 낸다.

                    받는 것은 단품 후보(`Lump`)다. 자세는 윗면사각형이 정한다. 3D 형상은 윗면과 세로 소실점에서 나온다(`Homography.shape_3d_px`).
                    3D 로 그려 견주어 자세를 다듬는 길은 `process_3d` 다. 지금 경로의 옆면 부류로는 라벨에서 더 멀어져 부르지 않는다.
                    """
                    return self.process_uppershape(piece, pre)

                def question_intact(self, piece, pre):
                    """온전한 블록인가? 노치가 있으면 一자로 조합된 것일 수 있어 되돌린다."""

                def question_side(self, piece, pre):
                    """옆이 보이나? 3D 예측과 위치 파악에 쓴다. 세로 소실점이 풀려 있고, 윗면 꼭짓점마다 밑면이 윗면과 소실점 사이에 놓이는가."""
                    homography, h35 = self.vision_algorithm.homography, self.era_values.homography
                    return h35.is_vanishing_solved and homography.is_under_between(h35, piece.corners_px)

                def question_box(self, piece, pre):
                    """육면체 형상인가? 3D 예측에 쓴다."""

                def question_rectangle(self, piece, pre):
                    """사각형 형상인가? 탑뷰 여부를 확인한다."""

                def question_position(self, piece, pre):
                    """이 위치에서 보일 형상인가? 시야 반대편에 측면이 잡히지 않았는지 본다."""

                def question_same(self, piece, other):
                    """같은 블록인가? 여러 알고리즘이 같은 개체를 내놓을 때 쓴다. 발자국이 겹치면 같은 블록이다(`Entity.Piece.is_same`)."""
                    return piece.is_same(other)

                def process_uppershape(self, piece, pre):
                    """윗면 사각형. 상면은 가려짐 없이 보인다.

                    상면 조각의 윤곽을 H35 로 상면에 옮겨 규격마다 최소 외접 직사각형을 맞추고, 치수가 가장 가까운 규격을 고른다(`Tool.Fit.MinAreaRect`).
                    놓는 사각형은 규격 치수다 — 마스크 경계는 비탈의 어디를 자르느냐로 안쪽으로 물러나 치수를 짧게 재지만, 고르게 물러나면 중심과 방위는 그대로다.
                    """
                    top, = Calc.Pipe.Perception.tops_in(piece, pre, self.route, self.vision_algorithm, self.era_values)
                    homography, h35 = self.vision_algorithm.homography, self.era_values.homography
                    world_mm = Tool.Fit.Homography.project(top.contour_px, h35.matrix)
                    fits = [(Tool.Fit.MinAreaRect.fit(world_mm, block.length__mm, block.dimensions.width__mm), block) for block in self.vision_algorithm.product.blocks]
                    ((center_x_mm, center_y_mm), angle_deg, _), block = min(fits, key=lambda fit: fit[0][2])
                    placed = Entity.Piece(0, Entity.Piece.Pose(center_x_mm, center_y_mm, angle_deg), block.length__mm, block.dimensions.width__mm, (), block)
                    return dataclasses.replace(placed, corners_px=homography.upper_shape_px(h35, placed.corners_mm))

                def process_undershape(self, piece, pre):
                    """밑면 사각형. 안 보일 수 있어 보이는 측면을 활용한다."""

                def process_3d(self, piece, pre):
                    """3D 형상 예측. 윗면과 밑면 사각형의 꼭지점을 잇는다.

                    블록을 윗면 · 옆면으로 그려 보인 면 부류와 견주고, 어긋남이 줄도록 자세를 옮긴다(`Config.VisionAlgorithm.BoxFit`).
                    견주는 곳은 이 블록의 그린 윤곽을 마스크 팽창 여유(`WorkArea.mask_dilation_margin__mm`)만큼 넓힌 자리다 — 옆 블록이 어긋남에 섞이지 않는다.
                    """
                    from cv2 import INTER_NEAREST as cv2_INTER_NEAREST, MORPH_DILATE as cv2_MORPH_DILATE, MORPH_ELLIPSE as cv2_MORPH_ELLIPSE, resize as cv2_resize

                    homography, h35, box_fit = self.vision_algorithm.homography, self.era_values.homography, self.vision_algorithm.box_fit
                    scale = box_fit.raster_scale
                    origin_px = pre.roi(self.route).origin_px
                    seen = cv2_resize(pre.faces(self.route), None, fx=scale, fy=scale, interpolation=cv2_INTER_NEAREST)
                    outline = Tool.Geometry.Polygon.silhouette(*homography.shape_3d_px(h35, piece.corners_mm))
                    drawn = Tool.Vision.fill_polygons(seen.shape, [[((x - origin_px[0]) * scale, (y - origin_px[1]) * scale) for x, y in outline]], 255)
                    margin_px = self.vision_algorithm.work_area.mask_dilation_margin__mm * homography.ppm_inplane_at(h35, *homography.to_image(h35, piece.pose.x_mm, piece.pose.y_mm)) * scale
                    region = Tool.Vision.morphology(drawn, cv2_MORPH_DILATE, 2.0 * margin_px + 1.0, cv2_MORPH_ELLIPSE)
                    return box_fit.pose_fitted((piece,), 0, seen, region, origin_px, homography, h35)

        class Review:
            """전환 계통. `SYSTEM_REVIEW`. 인식 계통이 낸 `Piece` 를 받는다."""

            class Global:
                """좌표 변환. `SCOPE_GLOBAL`."""

                vision_algorithm: "Config.VisionAlgorithm"
                era_values: "Config.Dataset.EraValues"
                route: "Calc.Pre.Route"

                def __init__(self, vision_algorithm, era_values, route):
                    self.vision_algorithm = vision_algorithm
                    self.era_values = era_values
                    self.route = route

                def run(self, piece):
                    """단품 하나를 한 번 돈다. 확정 개체 하나를 낸다. 자세는 H35 상면 mm 좌표다 — 로봇 좌표는 집을 때 `question_position` 이 옮긴다."""
                    return piece

                def question_position(self, piece, affine):
                    """어느 위치인가? 단품 중심의 로봇 기저 XY 다.

                    상면 mm 를 받은 아핀으로 옮긴다(`Config.VisionAlgorithm.AffineTransform.to_robot`) — 사이클은 회차 아핀을, 대응점 수집은 대략 아핀을 넘긴다.
                    아핀이 없으면 `Tool.Missing` 이다.
                    """
                    return self.vision_algorithm.affine_transform.to_robot(affine, piece.pose.x_mm, piece.pose.y_mm)

                def question_fit(self, piece):
                    """어떤 자세인가?"""

    class Photo(NamedTuple):
        """회차 사진 한 장을 그 회차 값으로 계산한 것(`Calc.photo`)."""

        pieces: tuple  # 확정 개체 목록
        unsplit: tuple  # 단품으로 못 가른 덩어리
        calc: "Calc"  # 그 장을 계산한 것. 그 장의 전처리 결과(`pre`)를 더 꺼낼 때 쓴다

    @staticmethod
    def is_ready(era_values):
        """이 회차 값으로 계산이 서는가. 작업영역으로 자르고 H35 로 상면에 옮기므로 둘 다 있어야 한다."""
        return bool(era_values.work_area.polygon__px) and era_values.homography.matrix is not None

    @classmethod
    def photo(cls, vision_algorithm: "Config.VisionAlgorithm", era_values: "Config.Dataset.EraValues", route: "Calc.Pre.Route", image: Any) -> "Calc.Photo":
        """회차 사진 한 장을 그 회차 값으로 계산한다.

        장마다 새로 세운다 — 장을 넘겨 드는 메모리(직전 프레임 · 직전 개체)가 없다.
        """
        calc = cls(vision_algorithm, era_values, route)
        return cls.Photo(tuple(calc.observe(image)), calc.unsplit, calc)

    vision_algorithm: "Config.VisionAlgorithm"
    era_values: "Config.Dataset.EraValues"  # 이 계산이 선 회차 값 한 벌
    pre: "Calc.Pre"
    scope_scene: "Calc.Pipe.Perception.Scene"
    scope_blob: "Calc.Pipe.Perception.Blob"
    scope_inst: "Calc.Pipe.Perception.Inst"
    scope_global: "Calc.Pipe.Review.Global"
    # 메모리 :: `OUTCOME_PRE_FRAME` · `OUTCOME_PRE_ENTITY`. 이름의 PRE 가 여기서는 '직전' 이라 풀어 적었다
    previous_frame: Any = None
    previous_entities: tuple = ()
    tags: itertools.count  # 새 개체에 줄 꼬리표. 개체가 없는 프레임을 지나도 이어서 센다 — 한 번 준 꼬리표를 다른 블록에 다시 주지 않는다
    unsplit: tuple = ()  # 지난 프레임에서 단품으로 못 가른 덩어리. 버리지 않고 화면에 낸다

    def __init__(self, vision_algorithm, era_values, route):
        self.vision_algorithm = vision_algorithm
        self.era_values = era_values
        self.pre = self.Pre(vision_algorithm, era_values)
        self.scope_scene = self.Pipe.Perception.Scene(vision_algorithm, era_values, route)
        self.scope_blob = self.Pipe.Perception.Blob(vision_algorithm, era_values, route)
        self.scope_inst = self.Pipe.Perception.Inst(vision_algorithm, era_values, route)
        self.scope_global = self.Pipe.Review.Global(vision_algorithm, era_values, route)
        self.tags = itertools.count()

    def observe(self, frame):
        """한 프레임을 계산해 확정 개체 목록(`HAND`)을 낸다. 준비 → 계산 → 출력.

        범위 단위로만 부른다 :: 전역 → `Lump` 들 → 덩어리 → 단품 후보들 → 단품 → 좌표 변환.
        꼬리표는 처음 관측된 차례다 — 직전 프레임 개체와 발자국이 겹치면 그 꼬리표를 잇고(`Entity.Piece.paired`), 새 개체는 이어서 번호를 받는다. 관측된 차례로 집는다.
        """
        self.pre.reset(frame)
        lumps = self.scope_scene.run(self.pre, self.previous_frame)
        split = [(lump, self.scope_blob.run(lump, self.pre)) for lump in lumps]
        self.unsplit = tuple(lump for lump, candidates in split if not candidates)
        candidates = [candidate for _, found in split for candidate in found]
        pieces = [self.scope_inst.run(candidate, self.pre) for candidate in candidates]
        pieces = [dataclasses.replace(piece, tag=next(self.tags) if before is None else self.previous_entities[before].tag)
                  for piece, before in zip(pieces, Entity.Piece.paired(self.previous_entities, pieces))]
        entities = [self.scope_global.run(piece) for piece in pieces]
        self.previous_frame, self.previous_entities = frame, tuple(entities)
        return entities


# =========================================================================
# 4. 판정 루프
# =========================================================================


class CalcBus:
    """판정 루프. 카메라가 새 장을 받을 때마다 현행 값으로 계산해 확정 개체 목록을 슬롯에 놓는다. 워커 하나다.

    `Calc` 는 현행 값 한 벌마다 선다 — 현행 값이 바뀌면 새로 세우고, 직전 프레임 · 직전 개체(메모리)도 그때 비운다.
    현행 값에 작업영역 · H35 가 없으면 계산하지 않는다(`Calc.is_ready`).
    사영 모델 풀기를 맡으면(`Job.FIT_PROJECTIVE_MODEL`) 그것부터 한다 — 풀고 적는 동안 판정은 쉬고, 적은 값이 현행 값이면 다음 장부터 그 값으로 판정한다.
    풀 때는 회차를 보는 중이라 카메라가 닫혀 있어 판정 루프가 마침 논다.
    로봇이 움직이는 동안은 관측하지 않는다. 관측해도 되는지는 부르는 쪽이 `idle` 로 알리고, 쉬는 동안은 슬롯을 비운다 — 팔이 집어 간 블록이 화면에 남지 않는다.
    로봇이 다시 서면 흔들림 대기 뒤 묵은 장을 버리고 새 장부터 본다(`CameraBus.fresh_frame`) — 섰다는 알림 때 슬롯의 장은 팔이 화면에 있을 때 찍혔을 수 있다.
    프레임이 정지했는지(`Calc.Pipe.Perception.Scene.question_stop`)는 아직 묻지 않는다.
    """

    class Seen(NamedTuple):
        """한 장의 관측."""

        grabbed: int  # 그 장이 카메라를 연 뒤 몇 번째 장인가
        pieces: tuple  # 확정 개체 목록. 꼬리표는 처음 관측된 차례다
        unsplit: tuple  # 단품으로 못 가른 덩어리
        calc: "Calc"  # 이 관측을 낸 계산. 부르는 쪽이 같은 현행 값으로 좌표를 옮긴다(`Calc.Pipe.Review.Global`)

    class Job(Enum):
        """맡길 수 있는 일."""

        FIT_PROJECTIVE_MODEL = "fit_projective_model"   # `era=` 회차 하나의 사영 모델을 풀어 적는다(`Calibration.fit_projective_model`). 표는 `Calibration.ProjectiveModel | None` 을 낸다

    eye: CameraBus
    state: EraState
    vision_algorithm: "Config.VisionAlgorithm"
    route: "Calc.Pre.Route"
    idle: Any  # 지금 관측해도 되는가. 인자 없이 불러 참 · 거짓을 받는다
    robot: "Config.Robot"  # 로봇 규격(`robot.json`) — 로봇이 선 뒤 흔들림이 가라앉기를 기다리는 시간(`motion.calibration.settle__s`)을 여기서 읽는다
    seen: Tool.Slot  # `CalcBus.Seen`. 관측이 없으면 `None`
    events: queue.Queue
    requests: queue.Queue  # (일, 실을 것, 표) — 맡은 일감
    _shutdown: threading.Event
    _thread: threading.Thread

    def __init__(self, eye: CameraBus, state: EraState, vision_algorithm: "Config.VisionAlgorithm", route: "Calc.Pre.Route", idle: Any, *, robot: "Config.Robot"):
        self.eye = eye
        self.state = state
        self.vision_algorithm = vision_algorithm
        self.route = route
        self.idle = idle
        self.robot = robot
        self.seen = Tool.Slot()
        self.events = queue.Queue()
        self.requests = queue.Queue()
        self._shutdown = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def shutdown(self) -> None:
        self._shutdown.set()
        self._thread.join()

    def submit(self, job: "CalcBus.Job", **payload) -> Future:
        """일감 하나를 맡긴다. 받은 표로 끝났는지와 그 결과를 본다."""
        future: Future = Future()
        self.requests.put((job, payload, future))
        return future

    def _say(self, text: str) -> None:
        self.events.put(Tool.Event(text, time.monotonic()))

    def _run(self) -> None:
        """새 장마다 한 번 계산한다. 계산이 장 간격보다 길면 그사이 장은 건너뛴다 — 슬롯은 최신 한 장이다.

        한 장에서 난 오류는 그 장에서 끝낸다(스트리밍 루프는 장 단위로 격리한다). 같은 말을 장마다 되풀이하지 않는다.
        """
        calc, built_for, last, failed = None, None, None, ""
        robot_moved = False  # 로봇이 움직였고 그 뒤로 새 장을 아직 안 받았다
        while not self._shutdown.is_set():
            try:
                job, payload, future = self.requests.get_nowait()
            except queue.Empty:
                pass
            else:
                try:
                    future.set_result(Calibration.fit_projective_model(self.state, self.vision_algorithm, self.route, payload["era"]))
                except Exception as exc:                  # noqa: BLE001
                    self._say(f"{job} 에 실패했다 :: {exc}")
                    future.set_exception(exc)
                continue
            if not self.idle():
                robot_moved = True
            elif robot_moved:
                robot_moved = False
                if self.eye.fresh_frame(self.robot.motion.calibration.settle__s) is None:
                    continue
            grabbed, current = self.eye.grabbed.get(), self.state.current.get()
            if not self.idle() or current is None or self.eye.frame.get() is None:
                self.seen.put(None)
                time.sleep(self.eye.camera.frame_poll__s)
                continue
            if grabbed == last:
                time.sleep(self.eye.camera.frame_poll__s)
                continue
            last = grabbed
            if current is not built_for:
                calc, built_for = (Calc(self.vision_algorithm, current.era_values, self.route) if Calc.is_ready(current.era_values) else None), current
            if calc is None:
                self.seen.put(None)
                continue
            try:
                pieces = calc.observe(self.eye.frame.get())
            except Exception as exc:                  # noqa: BLE001
                if str(exc) != failed:
                    self._say(f"판정 루프 :: {exc}")
                failed = str(exc)
                continue
            failed = ""
            self.seen.put(self.Seen(grabbed, tuple(pieces), calc.unsplit, calc))
