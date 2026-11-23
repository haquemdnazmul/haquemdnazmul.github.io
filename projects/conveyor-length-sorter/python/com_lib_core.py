r"""공통 라이브러리 — 여러 계통이 함께 쓰는 것을 담는다.

최상위는 넷이며 **주체**로 갈린다.

- `Tool` :: 설비도 화면도 모르는 범용 도구. 결측 예외 · 사건 한 줄 · 최신 값 슬롯 · 쓰기 주인 · 읽은 JSON 구획 · 홀수화 · 닫힌 다각형의 변
- `Config` :: **정의**. 정본 JSON 이 선언한 것을 의미로 세운다. 회차 문서를 읽으면 그 회차의 정의가 된다
- `Entity` :: **개체**. 계통끼리 주고받는 어휘 — 개체 하나와 한 관측의 결과
- `Connect` :: **바깥**. 바깥과 주고받는 일. 장치에 붙는 것과 남이 만든 코드에 맞추는 것으로 갈린다

여기 있는 것은 **대안이 없는 것**이다.
필렛의 접점 기하는 다른 답이 없고, Modbus 번지 해석은 설비가 무엇을 하든 같다.
무엇을 어떤 차례로 할지 고르는 일은 알고리즘 모듈이, 사람에게 어떻게 보일지는 화면이 맡는다.

설정 계층이 지키는 것
- **JSON 이름 그대로** :: 설정은 읽은 JSON 을 그대로 들고 키 경로로 부른다. 단위 접미사도 키 그대로다(`product.dimensions.width__mm`). 코드가 셈한 값은 단일 밑줄로 단위를 붙인다(`Product.Block.fillet_r_mm`)
- **유도식** :: 원천에서 나오는 값은 저장하지 않고 프로퍼티로 낸다

설정과 개체는 dict 필드를 포함해 불변으로 다룬다.
원천을 바꾸려면 새 인스턴스를 만든다 (읽은 JSON 을 든 설정 · 회차 값은 `Tool.JsonNode.replaced`, 개체는 `dataclasses.replace`).
유도 프로퍼티는 `cached_property` 로 처음 읽을 때 계산해 두며, 캐시가 인스턴스 `__dict__` 에 실리므로 `slots=True` 와 함께 쓸 수 없다.

값 한 벌은 `Config.Product.load()` 로 세우고 `product.dimensions.width__mm` 으로 읽는다.

이 모듈을 불러온 뒤로는 `cv2` 를 불러오는 순간 `cv2.imread` · `cv2.imwrite` 가 한글 경로를 읽고 쓰는 함수로 바뀐다.
`cv2` · `numpy` · `pymodbus` · `pyserial` 은 쓰는 자리에서 불러온다.
"""

from __future__ import annotations

import dataclasses
import datetime
import importlib.abc
import importlib.util
import inspect
import itertools
import json
import math
import queue
import re
import statistics
import sys
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum, IntEnum, StrEnum, auto
from functools import cache, cached_property
from pathlib import Path
from typing import Any, NamedTuple






class Tool:
    """범용 도구함. 설비도 화면도 모르는 것만 둔다.

    여기 있는 것은 어느 프로젝트에서도 뜻이 통한다. 소속이 분명한 것은 그 소속에 둔다 — 필렛 기하가 `Product.Block` 에 있는 것과 같은 이유다.
    """

    #: 배정밀도 최소 상대 간격.
    EPS = sys.float_info.epsilon

    class Missing(ValueError):
        """있어야 할 값이 비어 있다.

        정의(정본 JSON)에도 기록(회차 문서)에도 없고, 실물에서 얻어야 하는 값이다.
        이름만 지닌 예외인 것은 하는 일이 그것뿐이기 때문이다 — **부르는 쪽이 이것만 골라 잡아** 사람에게 무엇을 채워야 하는지 보인다.
        넓게 잡으면 오탈자와 결측이 한 그물에 걸린다.
        """

    class Event(NamedTuple):
        """사건 한 줄. 사람이 읽을 문장과 단조 시계를 함께 든다."""

        text: str
        at: float

    class Slot:
        """최신 한 벌만 남는 자리. 쓰는 쪽이 덮고 읽는 쪽이 지금 것을 가져간다.

        값은 불변(`NamedTuple` · `None`)이라 참조를 바꾸는 것으로 갱신이 끝난다.
        읽는 쪽이 반쯤 쓰인 값을 보는 일이 없다. 워커와 화면처럼 주기가 다른 둘을 잇는다.
        """

        _value: Any

        def __init__(self, initial: Any = None) -> None:
            self._value = initial

        def put(self, snapshot: Any) -> None:
            self._value = snapshot

        def get(self) -> Any:
            return self._value

    class Writer:
        """쓰기 주인 — lib 워커. 여럿이 함께 보는 것은 이 워커 하나가 받은 차례대로 쓴다. 현행 값 · 회차 문서 · 촬영 사진 · 티칭 · 라벨 · 녹화 · 수집 기록이 그것이다.

        읽기는 누구나 한다. 쓰기가 한 줄이라 두 쓰기가 섞여 한쪽 고침이 사라지는 일이 없다.
        일감은 "이 함수를 이 값으로 돌려라" 꼴이다 — lib 은 alg 를 부르지 못하므로 무엇을 어떻게 쓰는지는 맡기는 쪽이 함수로 싣는다.
        맡긴 차례대로 쓰므로 회차 만들기 다음 사진, 수집 폴더 만들기 다음 기록처럼 잇따른 쓰기는 기다리지 않고 차례로 맡긴다.
        쓴 것을 다시 읽거나 썼다고 알려야 하는 쪽은 맡길 때 받은 표(`Future`)로 끝난 것을 보고 간다.
        일감이 던진 예외는 사람이 읽을 말로 `events` 에 낸다 — 표를 보지 않는 쪽의 실패도 묻히지 않는다.
        """

        busy: "Tool.Slot"  # 줄에 일이 남았는가. 누구나 읽는다 — 내가 맡긴 그 일이 끝났는지는 표가 답한다
        events: queue.Queue
        _pool: ThreadPoolExecutor  # 일꾼 하나짜리라 한 줄이다
        _pending: int = 0  # 맡았는데 아직 안 끝난 일감 수
        _lock: threading.Lock  # 맡기는 스레드들과 끝낸 일꾼이 `_pending` 을 함께 센다

        def __init__(self) -> None:
            self.busy = Tool.Slot(False)
            self.events = queue.Queue()
            self._pool = ThreadPoolExecutor(max_workers=1)
            self._lock = threading.Lock()

        def submit(self, work: Any, *args: Any, **kwargs: Any) -> Future:
            """일감 하나를 줄 끝에 세운다. 받은 표로 끝났는지 · 돌려준 값 · 던진 예외를 본다."""
            with self._lock:
                self._pending += 1
                self.busy.put(True)
            future = self._pool.submit(work, *args, **kwargs)
            future.add_done_callback(self._done)
            return future

        def _done(self, future: Future) -> None:
            with self._lock:
                self._pending -= 1
                self.busy.put(self._pending > 0)
            if future.exception() is not None:
                self.events.put(Tool.Event(f"쓰기에 실패했다 :: {future.exception()}", time.monotonic()))

        def shutdown(self) -> None:
            """줄에 남은 일감을 다 쓴 뒤 일꾼을 세운다 — 녹화 파일은 닫는 일감까지 돌아야 온전하다."""
            self._pool.shutdown(wait=True)

    class JsonNode(Mapping):
        """읽은 JSON 한 구획을 깨지 않고 든다 — 키가 곧 부르는 이름이라 `node.matrix` 가 `doc["matrix"]` 다.

        값은 읽은 그대로 내고 목록만 튜플로 굳힌다 — 든 dict 를 부르는 쪽이 고칠 길이 없다.
        안의 구획은 그 키와 이름이 같은 중첩 클래스(밑줄과 대소문자는 가리지 않는다 — `work_area` → `WorkArea`, `directshow` → `DirectShow`)가 있으면 그것으로, 없으면 `JsonNode` 로 감싼다 — 그 구획에서 나오는 계산을 거기에 단다.
        구획 밖에서 정해져 들어오는 값(다른 칸 · 다른 설정의 값)은 그 클래스 본문에 선언한 이름으로 받는다(`given`).
        이름으로 묶인 항목(키가 항목 이름이고 값이 같은 꼴의 구획 — `camera.roles` 의 `BLOCK` · `QR`)은 그 키에서 끝 `s` 를 뗀 이름의 중첩 클래스(`roles` → `Role`)가 항목마다 감싼다. 목록의 항목도 같다.
        이름으로 묶인 항목은 dict 처럼도 돈다 — `items` · `get` · `[]`.
        """

        #: 이 글자로 시작하는 키는 주석이라 이름으로 부르지 않고 돌 때도 뺀다
        COMMENT_PREFIX = "_"

        doc: dict[str, Any]  # 이 구획의 원본 dict — 고치지 않는다
        given: dict[str, Any]  # 구획 밖에서 들어온 값 — `replaced` 가 이어 받는다
        _wrapped: dict[str, Any]  # 키 → 감싼 값 — 처음 부를 때 감싸 두므로 같은 키는 같은 객체를 내고 안 구획의 캐시가 산다

        def __init__(self, doc: dict[str, Any], **given: Any) -> None:
            self.doc, self.given, self._wrapped = doc, given, {}
            for name, value in given.items(): setattr(self, name, value)

        def __getattr__(self, key: str) -> Any:
            """그 키의 값 — 메서드 · 캐시 · 넣어 준 값에 없는 이름만 여기로 온다."""
            if key.startswith(Tool.JsonNode.COMMENT_PREFIX) or key not in self.__dict__.get("doc", ()): raise AttributeError(f"{type(self).__qualname__} 에 `{key}` 키가 없다")
            if key not in self._wrapped:
                classes = {member.__name__.lower(): member for klass in type(self).__mro__ for member in vars(klass).values()
                           if isinstance(member, type) and issubclass(member, Tool.JsonNode)}
                wanted = key.replace("_", "").lower()
                node_class = classes.get(wanted, Tool.JsonNode)
                item_class = classes.get(wanted[:-1]) if wanted not in classes and wanted.endswith("s") else None

                def wrapped(value: Any) -> Any:
                    if isinstance(value, dict): return node_class(value)
                    if isinstance(value, list): return tuple(item_class(element) if item_class and isinstance(element, dict) else wrapped(element) for element in value)
                    return value

                node = wrapped(self.doc[key])
                if item_class is not None and isinstance(node, Tool.JsonNode):
                    node._wrapped.update({name: item_class(body) for name, body in node.doc.items() if not name.startswith(Tool.JsonNode.COMMENT_PREFIX) and isinstance(body, dict)})
                self._wrapped[key] = node
            return self._wrapped[key]

        def __getitem__(self, key: str) -> Any:
            if key.startswith(Tool.JsonNode.COMMENT_PREFIX) or key not in self.doc: raise KeyError(key)
            return getattr(self, key)

        def __iter__(self) -> Iterator[str]:
            return (key for key in self.doc if not key.startswith(Tool.JsonNode.COMMENT_PREFIX))

        def __len__(self) -> int:
            return sum(1 for _ in self)

        def replaced(self, **changes: Any) -> Any:
            """이 구획의 사본 — 클래스에 선언한 이름(구획 밖에서 들어온 값)은 갈아 끼우고, 나머지는 dict 사본의 그 키에 적는다(없던 키면 더한다).

            dict 에는 JSON 에 적을 꼴로 적는다(`plain`).
            넣어 준 값은 그대로 이어 받는다.
            """
            declared = {name for klass in type(self).__mro__ if isinstance(klass, type) and issubclass(klass, Tool.JsonNode) and klass is not Tool.JsonNode
                        for name in inspect.get_annotations(klass)}
            doc, given = dict(self.doc), dict(self.given)
            for name, value in changes.items():
                if name in declared: given[name] = value
                else: doc[name] = Tool.JsonNode.plain(value)
            return type(self)(doc, **given)

        def warm(self) -> None:
            """유도값(`cached_property`)을 지금 다 셈해 둔다 — 안 구획과 이름으로 묶인 항목까지 내려간다. 쓰는 자리에서 처음 셈하지 않는다."""
            for klass in type(self).__mro__:
                for name, member in vars(klass).items():
                    if isinstance(member, cached_property): getattr(self, name)
            for key in self:
                value = self[key]
                for node in value if isinstance(value, tuple) else (value,):
                    if isinstance(node, Tool.JsonNode): node.warm()

        @staticmethod
        def plain(value: Any) -> Any:
            """JSON 에 적을 꼴 — `JsonNode` 는 든 dict 로, 튜플은 목록으로 푼다."""
            if isinstance(value, Tool.JsonNode): return Tool.JsonNode.plain(value.doc)
            if isinstance(value, dict): return {key: Tool.JsonNode.plain(one) for key, one in value.items()}
            if isinstance(value, (tuple, list)): return [Tool.JsonNode.plain(one) for one in value]
            return value

    class Acoustic:
        """음향 특징 연산.

        대역과 임계값은 전부 인자로 받는다 — 기본값을 두면 튜닝이 도구 안에 숨는다.
        스펙트럼 계열은 `power_spectrum` 한 번의 결과(`freqs` · `power`)를 나눠 쓴다. 대역 인자는 `(하한 Hz, 상한 Hz)` 다.
        """

        #: 로그에 0 을 넣지 않기 위한 바닥. 부동소수점 상대 스텝이라 실제 신호에 더해도 값이 안 바뀐다
        POWER_FLOOR = sys.float_info.epsilon

        # ------------------------------------------------- 물리 · 수학 불변식

        @staticmethod
        def rotation_frequency_hz(rpm: float, strokes_per_rev: float) -> float:
            """회전수와 회전당 행정수로부터 기본 구동 주파수. `f = rpm * n / 60`."""
            return (rpm * strokes_per_rev) / 60.0

        @staticmethod
        def piston_band_hz(motor_band_hz: tuple[float, float], strokes_per_rev: int) -> tuple[float, float]:
            """회전 대역에 대응하는 토출 맥동 대역. 행정수만큼 곱한다.

            측정 오차 여유는 부르는 쪽이 붙인다. 여기서 한쪽에만 더하면 대역이 기운다.
            """
            return (motor_band_hz[0] * strokes_per_rev, motor_band_hz[1] * strokes_per_rev)

        @staticmethod
        def ac_sync_frequency_hz(grid_freq_hz: float, poles: int) -> float:
            """상용 전원 유도 전동기의 동기 회전 주파수. `f = 2 * f_grid / P`.

            **교류 유도 전동기에만 쓴다.**
            회전이 전원 주파수에 묶인 모터라야 이 식이 선다 — 실측 회전수가 동기 속도를 넘으면 다른 종류다.
            """
            return (2.0 * grid_freq_hz) / float(poles)

        @staticmethod
        def ac_motor_band_hz(grid_freq_hz: float, poles: int, slip_range: tuple[float, float]) -> tuple[float, float]:
            """슬립률 범위에 대응하는 실부하 축 회전 대역. **교류 유도 전동기에만 쓴다.**

            슬립은 늘 양수라 결과가 동기 속도를 넘지 않는다. 그 점이 이 식을 쓸 수 있는지 가르는 시금석이다.
            """
            f_sync = Tool.Acoustic.ac_sync_frequency_hz(grid_freq_hz, poles)
            return (f_sync * (1.0 - slip_range[1]), f_sync * (1.0 - slip_range[0]))

        @staticmethod
        def harmonic_frequency_hz(f0_hz: float, order: int) -> float:
            """정수배 고조파의 이론 주파수. `f_n = n * f_0`."""
            return f0_hz * float(order)

        @staticmethod
        def harmonic_match_tolerance_hz(sample_rate_hz: int, block_size: int, order: int, bin_sigma_ratio: float, sigma_multiple: float) -> float:
            """`|f_n - n*f_0|` 이 이 안이면 정수배로 본다.

            봉우리 하나의 주파수 불확실성을 `sigma = 칸 폭 * bin_sigma_ratio` 로 잡는다.
            두 봉우리의 오차가 서로 독립이므로 차의 불확실성은 `sqrt(1 + n^2) * sigma` 로 퍼진다 — **차수마다 달라지므로 `order` 를 받는다.**
            2 배 고조파에 맞춘 폭을 3 배에 그대로 쓰면 과하게 엄격해진다.

            몇 sigma 까지 받을지(`sigma_multiple`)와 보간 잔여 오차가 칸 폭의 몇 분의 일인지 (`bin_sigma_ratio`)는 부르는 쪽이 고르는 값이라 인자로 둔다.
            """
            sigma_hz = (sample_rate_hz / block_size) * bin_sigma_ratio
            return sigma_multiple * math.hypot(1.0, float(order)) * sigma_hz

        @staticmethod
        def fft_bin_resolution_hz(sample_rate_hz: int, block_size: int) -> float:
            """푸리에 변환 한 칸의 폭. `delta_f = fs / N`."""
            return sample_rate_hz / block_size

        @staticmethod
        def db_to_linear(db: float) -> float:
            """데시벨을 선형 전력비로. `P = 10^(db/10)`."""
            return float(10.0 ** (db / 10.0))

        @staticmethod
        def linear_to_db(linear: float) -> float:
            """선형 전력비를 데시벨로. `db = 10 log10(P)`."""
            return float(10.0 * math.log10(max(linear, Tool.Acoustic.POWER_FLOOR)))

        # ----------------------------------------------------------- 특징 추출

        @staticmethod
        def _band(freqs: Any, band: tuple[float, float]) -> Any:
            return (freqs >= band[0]) & (freqs <= band[1])

        @staticmethod
        def power_spectrum(block: Sequence[float], sample_rate_hz: int) -> tuple[Any, Any]:
            """한 블록의 한쪽 전력 스펙트럼. 해닝 창으로 칸 사이 누설을 줄인다."""
            from numpy import abs as np_abs, asarray as np_asarray, float64 as np_float64, hanning as np_hanning
            from numpy.fft import rfft as np_fft_rfft, rfftfreq as np_fft_rfftfreq

            signal = np_asarray(block, dtype=np_float64)
            window = np_hanning(len(signal))
            amplitude = np_abs(np_fft_rfft(signal * window)) / (window.sum() / 2.0)
            return np_fft_rfftfreq(len(signal), 1.0 / sample_rate_hz), amplitude ** 2

        @staticmethod
        def spectral_subtract(power: Any, noise_power: Any, floor_ratio: float) -> Any:
            """미리 재 둔 잡음 프로파일을 빼고 바닥을 남긴다.

            프로파일은 소리를 안 내는 동안의 전력 스펙트럼 평균이다.
            그냥 빼면 음수가 되거나 0 에 눌려 남은 잔여가 음조처럼 들리므로, 바닥을 원래 전력의 `floor_ratio` 배로 막는다.

            프로파일과 신호를 **같은 게인으로 잰 것**일 때만 뜻이 있다.
            마이크를 바꾸거나 볼륨을 만지면 다시 재야 한다.
            그 조건만 지키면 빼기가 두 쪽에 같이 걸려 무차원 지표를 깨지 않는다.
            """
            from numpy import maximum as np_maximum

            return np_maximum(power - noise_power, floor_ratio * power)

        # --------------------------------------------------------- 대역 에너지

        @staticmethod
        def band_power_db(freqs: Any, power: Any, band: tuple[float, float]) -> float:
            """대역 평균 전력(dB). 녹음 음량을 그대로 따라가므로 단독 판정보다 대역끼리의 차로 쓴다."""
            return float(10.0 * math.log10(float(power[Tool.Acoustic._band(freqs, band)].mean()) + Tool.Acoustic.POWER_FLOOR))

        @staticmethod
        def band_power_linear(freqs: Any, power: Any, band: tuple[float, float]) -> float:
            """대역 평균 전력(선형). 비를 낼 때 로그를 거치지 않으려고 둔다."""
            band_mask = Tool.Acoustic._band(freqs, band)
            if not band_mask.any(): return Tool.Acoustic.POWER_FLOOR
            return float(power[band_mask].mean() + Tool.Acoustic.POWER_FLOOR)

        @staticmethod
        def band_power_ratio_linear(freqs: Any, power: Any, numerator_band: tuple[float, float], denominator_band: tuple[float, float]) -> float:
            """두 대역의 선형 전력비. 마이크 게인과 음원 거리가 분모 · 분자에서 약분되는 무차원 양이다."""
            return Tool.Acoustic.band_power_linear(freqs, power, numerator_band) / Tool.Acoustic.band_power_linear(freqs, power, denominator_band)

        # ------------------------------------------------------- 봉우리와 음조

        @staticmethod
        def peak_frequency_hz(freqs: Any, power: Any, band: tuple[float, float]) -> float:
            """대역 안 가장 센 음조선의 높이. 대역에 칸이 하나도 없으면 0 을 낸다.

            봉우리 칸과 양옆 칸의 로그 전력에 포물선을 맞춰 칸보다 잘게 읽는다.
            해닝 창의 봉우리는 로그 눈금에서 포물선에 가깝다.
            꼭짓점이 위로 볼록하지 않거나(대역 가장자리) 반 칸을 넘으면 칸 중심을 믿는다 — 안 묶으면 봉우리가 대역 밖으로 튄다.

            **대역이 칸 폭보다 좁으면 답이 늘 0 이다.** 부르는 쪽이 대역 폭과 칸 폭을 견줘야 한다.
            """
            from numpy import flatnonzero as np_flatnonzero

            band_indices = np_flatnonzero(Tool.Acoustic._band(freqs, band))
            if len(band_indices) == 0: return 0.0
            peak_index = band_indices[power[band_indices].argmax()]
            if peak_index <= 0 or peak_index >= len(power) - 1: return float(freqs[peak_index])
            floor = Tool.Acoustic.POWER_FLOOR
            log_power_previous, log_power_peak, log_power_next = math.log(float(power[peak_index - 1]) + floor), math.log(float(power[peak_index]) + floor), math.log(float(power[peak_index + 1]) + floor)
            denom = log_power_previous - 2.0 * log_power_peak + log_power_next
            offset = 0.0 if denom >= 0 else max(-0.5, min(0.5, 0.5 * (log_power_previous - log_power_next) / denom))
            return float(freqs[peak_index] + offset * (freqs[1] - freqs[0]))

        @staticmethod
        def peak_prominence_db(freqs: Any, power: Any, band: tuple[float, float]) -> float:
            """대역 안 가장 센 칸이 대역 중앙값보다 얼마나 솟았나(dB).

            바닥을 대역 스스로에서 재므로 음량이 바뀌어도 둘이 함께 움직여 상쇄된다.
            """
            from numpy import log10 as np_log10, median as np_median

            band_mask = Tool.Acoustic._band(freqs, band)
            if not band_mask.any(): return 0.0
            power_db = 10.0 * np_log10(power[band_mask] + Tool.Acoustic.POWER_FLOOR)
            return float(power_db.max() - np_median(power_db))

        @staticmethod
        def tonality_db(freqs: Any, power: Any, band: tuple[float, float]) -> float:
            """스펙트럼 평탄도(기하평균 / 산술평균)의 역수(dB).

            백색잡음은 0 dB 에 수렴하고 음조선이 설수록 커진다. 진폭 배율이 두 평균에서 약분되어 무차원이다.
            """
            from numpy import log as np_log

            band_mask = Tool.Acoustic._band(freqs, band)
            if not band_mask.any(): return 0.0
            band_power = power[band_mask] + Tool.Acoustic.POWER_FLOOR
            geom_mean, arith_mean = math.exp(float(np_log(band_power).mean())), float(band_power.mean())
            return float(-10.0 * math.log10(geom_mean / arith_mean))

        @staticmethod
        def tonality_linear(freqs: Any, power: Any, band: tuple[float, float]) -> float:
            """평탄도의 역수를 선형으로(산술평균 / 기하평균). 백색잡음은 1 에 수렴한다."""
            from numpy import log as np_log

            band_mask = Tool.Acoustic._band(freqs, band)
            if not band_mask.any(): return 1.0
            band_power = power[band_mask] + Tool.Acoustic.POWER_FLOOR
            flatness = math.exp(float(np_log(band_power).mean())) / float(band_power.mean())
            return float(1.0 / max(flatness, Tool.Acoustic.POWER_FLOOR))

        @staticmethod
        def tonal_to_noise_db(freqs: Any, power: Any, band: tuple[float, float], line_count: int, line_halfwidth_hz: float) -> float:
            """으뜸 음조선 몇 개의 전력 대 나머지 배경의 전력비(dB).

            센 칸부터 골라 그 둘레 `line_halfwidth_hz` 를 음조선으로 떼어 낸다.
            몇 개를 셀지와 얼마나 넓게 떼어 낼지는 신호마다 달라 인자로 받는다.
            """
            from numpy import flatnonzero as np_flatnonzero, zeros as np_zeros

            band_indices = np_flatnonzero(Tool.Acoustic._band(freqs, band))
            if len(band_indices) == 0: return 0.0
            band_power, band_frequencies = power[band_indices], freqs[band_indices]
            tonal = np_zeros(len(band_indices), dtype=bool)
            remaining = band_power.copy()
            for _ in range(line_count):
                near = abs(band_frequencies - band_frequencies[remaining.argmax()]) <= line_halfwidth_hz
                tonal |= near
                remaining[near] = 0.0
            floor = Tool.Acoustic.POWER_FLOOR
            tonal_db, noise_db = 10.0 * math.log10(float(band_power[tonal].sum()) + floor), 10.0 * math.log10(float(band_power[~tonal].sum()) + floor)
            return float(tonal_db - noise_db)

        # ----------------------------------------------------------- 배음 간격

        @staticmethod
        def harmonic_spacing_hz(freqs: Any, power: Any, band: tuple[float, float], spacing_range_hz: tuple[float, float]) -> float:
            """대역 안 배음선 사이의 되풀이 간격(Hz). 로그 스펙트럼 자기상관의 으뜸 지연이다.

            **`spacing_range_hz` 를 좁게 주면 그 안의 답이 반드시 나온다.**
            빗살이 아예 없으면 자기상관이 단조 감소만 해서 으뜸 지연이 탐색 하한에 붙는다 — 하한을 옮기면 답도 따라 옮는다.
            그러므로 "빗살이 있나" 를 물으려면 범위를 넓게 열고 답이 기대 구간에 떨어지는지를 봐야 한다.
            좁게 열면 기대 구간 안의 값이 늘 나와 일치가 저절로 성립한다.
            """
            from numpy import correlate as np_correlate, log10 as np_log10

            band_mask = Tool.Acoustic._band(freqs, band)
            if not band_mask.any(): return 0.0
            power_db = 10.0 * np_log10(power[band_mask] + Tool.Acoustic.POWER_FLOOR)
            power_db = power_db - power_db.mean()
            step = freqs[1] - freqs[0]
            corr = np_correlate(power_db, power_db, mode="full")[len(power_db) - 1:]
            lag_minimum = max(1, math.ceil(spacing_range_hz[0] / step))
            lag_maximum = min(len(corr) - 2, math.floor(spacing_range_hz[1] / step))
            if lag_minimum >= lag_maximum: return 0.0
            lag = lag_minimum + int(corr[lag_minimum:lag_maximum + 1].argmax())
            correlation_previous, correlation_peak, correlation_next = corr[lag - 1:lag + 2]
            denom = correlation_previous - 2.0 * correlation_peak + correlation_next
            offset = 0.0 if denom >= 0 else max(-0.5, min(0.5, 0.5 * (correlation_previous - correlation_next) / denom))
            return float((lag + offset) * step)

        @staticmethod
        def spacing_deadzone_hz(sample_rate_hz: int, block_size: int, spacing_range_hz: tuple[float, float]) -> tuple[float, float]:
            """`harmonic_spacing_hz` 가 빗살을 **못 찾았을 때** 답이 놓이는 두 자리.

            주기성이 없으면 로그 스펙트럼 자기상관은 지연 0 에서 단조 감소만 하므로 으뜸 지연이 탐색 구간의 끝 칸에 놓인다.
            **끝 칸에 놓였다는 것이 곧 못 찾았다는 뜻이다** — 답은 늘 숫자로 나오므로 빗살의 유무는 이 자리 하나로 가른다.

            답은 칸 번호에 포물선 보간 오프셋을 더해 나오고 그 오프셋은 반 칸으로 묶여 있다.
            그러므로 끝 칸에 놓인 답은 그 칸을 중심으로 반 칸 안에 든다.
            이 폭은 **칸 폭에서 나온다** — 탐색 범위의 몇 퍼센트 같은 것으로 잡으면 칸 폭이 바뀔 때 조용히 틀어진다.
            """
            step = sample_rate_hz / block_size
            bin_minimum, bin_maximum = math.ceil(spacing_range_hz[0] / step), math.floor(spacing_range_hz[1] / step)
            return ((bin_minimum + 0.5) * step, (bin_maximum - 0.5) * step)

        # -------------------------------------------------------- 그 밖의 특징

        @staticmethod
        def spectral_centroid_hz(freqs: Any, power: Any, band: tuple[float, float]) -> float:
            """대역 전력의 주파수 무게중심(Hz). 고역 난류가 늘면 올라간다."""
            band_mask = Tool.Acoustic._band(freqs, band)
            band_power = power[band_mask]
            return float((freqs[band_mask] * band_power).sum() / (band_power.sum() + Tool.Acoustic.POWER_FLOOR))

        @staticmethod
        def envelope_modulation(signal_block: Sequence[float], sample_rate_hz: int, carrier_band: tuple[float, float], modulation_range_hz: tuple[float, float], filter_order: int) -> tuple[float, float]:
            """반송 대역을 떼어 낸 뒤 진폭이 떨리는 주파수(Hz)와 떨림 깊이를 낸다.

            대역통과로 반송을 고르고 힐베르트 변환으로 포락선을 얻는다.
            포락선을 다시 변환해 으뜸 떨림을 찾는다.
            깊이는 포락선의 표준편차 / 평균이라 음량에 무관하다.
            """
            from numpy import abs as np_abs, asarray as np_asarray, float64 as np_float64
            from scipy.signal import butter as scipy_butter, hilbert as scipy_hilbert, sosfiltfilt as scipy_sosfiltfilt

            sos = scipy_butter(filter_order, carrier_band, btype="bandpass", fs=sample_rate_hz, output="sos")
            carrier = scipy_sosfiltfilt(sos, np_asarray(signal_block, dtype=np_float64))
            envelope = np_abs(scipy_hilbert(carrier))
            depth = float(envelope.std() / (envelope.mean() + Tool.Acoustic.POWER_FLOOR))
            freqs, power = Tool.Acoustic.power_spectrum(envelope - envelope.mean(), sample_rate_hz)
            modulation_mask = Tool.Acoustic._band(freqs, modulation_range_hz)
            if not modulation_mask.any(): return 0.0, depth
            return float(freqs[modulation_mask][power[modulation_mask].argmax()]), depth

        @staticmethod
        def pitch_rate_hz_per_s(times_s: Sequence[float], pitches_hz: Sequence[float]) -> float:
            """음 높이 시계열의 기울기(Hz/s). 최소제곱 직선 하나를 맞춘다."""
            from numpy import asarray as np_asarray, float64 as np_float64, polyfit as np_polyfit

            times = np_asarray(times_s, dtype=np_float64)
            pitches = np_asarray(pitches_hz, dtype=np_float64)
            if len(times) < 2: return 0.0
            return float(np_polyfit(times - times.mean(), pitches, 1)[0])

        @staticmethod
        def impact_onsets_s(signal_samples: Sequence[float], sample_rate_hz: int, frame_s: float, history_s: float, rise_db: float, refractory_s: float) -> list[float]:
            """충격음이 난 시각들(초).

            짧은 칸으로 에너지를 잘라 직전 `history_s` 의 **중앙값** 보다 `rise_db` 넘게 솟은 자리를 집는다.
            중앙값을 쓰는 것은 직전에 다른 충격이 있어도 기준선이 안 들리기 때문이다.
            한 번 잡으면 `refractory_s` 동안 다시 잡지 않는다 — 한 번의 충격이 여러 칸에 걸친다.
            """
            from numpy import asarray as np_asarray, float64 as np_float64, log10 as np_log10, median as np_median

            signal = np_asarray(signal_samples, dtype=np_float64)
            frame = max(1, round(frame_s * sample_rate_hz))
            count = len(signal) // frame
            if count == 0: return []
            block_energy = (signal[:count * frame].reshape(count, frame) ** 2).mean(axis=1)
            energy_db = 10.0 * np_log10(block_energy + Tool.Acoustic.POWER_FLOOR)
            history = max(1, round(history_s / frame_s))
            onsets: list[float] = []
            last_onset_s = -math.inf
            for block_index in range(history, count):
                onset_time_s = block_index * frame / sample_rate_hz
                risen = energy_db[block_index] - float(np_median(energy_db[block_index - history:block_index])) > rise_db
                if risen and onset_time_s - last_onset_s >= refractory_s:
                    onsets.append(onset_time_s)
                    last_onset_s = onset_time_s
            return onsets

        # ------------------------------------------------------- 시계열 동역학

        @staticmethod
        def exponential_smoothing(previous: float, current: float, alpha: float) -> float:
            """1 차 저역통과 지수 평활. `s[k] = alpha * s[k-1] + (1 - alpha) * x[k]`.

            `alpha = exp(-dt / tau)` 로 잡으면 시정수 `tau` 인 1 차 계통과 같아진다.
            다만 그 `tau` 는 **현상이 얼마나 빨리 변하나** 를 뜻한다.
            **얼마나 오래 봐야 확신하나** 는 따로 정하고, 둘을 같은 수로 두면 한쪽이 틀어진다.
            """
            return float((alpha * previous) + ((1.0 - alpha) * current))

        @staticmethod
        def schmitt_trigger(current: float, state: bool, u_cut: float, l_cut: float) -> bool:
            """히스테리시스 이치 판정. 상한을 넘으면 참, 하한 밑이면 거짓, 사이면 직전을 잇는다.

            경계에 붙은 값이 잔떨림으로 상태를 뒤집는 것을 막는다.
            """
            if current >= u_cut: return True
            if current <= l_cut: return False
            return state

    class Vision:
        """영상 특징 추출과 필터링 연산. 임계값과 커널 크기는 전부 인자로 받는다 — 기본값을 두면 튜닝이 도구 안에 숨는다."""

        class ColorSpace:
            """색 공간 및 채널 위상 정의. OpenCV 가 BGR 에서 바꿔 주는 색 공간을 전부 든다.

            8비트 영상에서 HSV · HLS 의 H 는 0~179, Lab · Luv 는 0~255 로 눌린다 (OpenCV 규약).
            """

            class RGB(Enum): R = auto(); G = auto(); B = auto()
            class HSV(Enum): H = auto(); S = auto(); V = auto()
            class HLS(Enum): H = auto(); L = auto(); S = auto()
            class YCrCb(Enum): Y = auto(); CR = auto(); CB = auto()
            class YUV(Enum): Y = auto(); U = auto(); V = auto()
            class Lab(Enum): L = auto(); A = auto(); B = auto()
            class Luv(Enum): L = auto(); U = auto(); V = auto()
            class XYZ(Enum): X = auto(); Y = auto(); Z = auto()
            class GRAY(Enum): GRAY = auto()

        class Blend(Enum):
            """여러 장을 한 장으로 합치는 방식."""

            WEIGHTED_MEAN = auto()  # 가중 평균. 둘의 성질을 섞는다
            MAX = auto()  # 화소별 최대. 어느 쪽이든 밝게 드러난 곳을 살린다
            MIN = auto()  # 화소별 최소. 모두 밝은 곳만 살린다

        class PrismFace(IntEnum):
            """위에서 본 기둥의 면 부류. 부류 지도의 화소값이다."""

            NONE = 0  # 기둥이 아닌 곳
            TOP = 1  # 윗면
            SIDE = 2  # 보이는 옆면

        class MultiOtsu(NamedTuple):
            """다단계 오츠 문턱 둘과 그 위쪽 마스크. 문턱은 위 무리의 첫 계조다."""

            low: int  # 배경 | 중간 무리 경계
            high: int  # 중간 무리 | 밝은 무리 경계
            above_low: Any  # `low` 이상인 화소
            above_high: Any  # `high` 이상인 화소

        class Gradient(NamedTuple):
            """기울기 크기와 방향."""

            magnitude: Any  # 8비트. 이론 최댓값을 255 에 맞춘다
            direction_rad: Any  # `atan2(gy, gx)`, 화소 좌표계(y 아래)

        class Crop(NamedTuple):
            """작업영역으로 잘라낸 한 벌. 같은 계산에서 함께 나온다."""

            image: Any  # 다각형을 감싸는 직사각형 + 여백. 바깥 화소도 원래 값 그대로다
            mask: Any  # `image` 와 같은 크기. 다각형 안 255 · 밖 0. 전역 통계 연산이 받는다
            origin_px: tuple[int, int]  # `image` 의 왼쪽 위가 원본에서 놓인 자리 (x, y). 더하면 원본 좌표다

        #: 8비트 계조 수. 문턱이 머물 수 있는 자리 수라 isodata 반복 상한으로 쓴다
        LEVELS = 256
        #: isodata 수렴 판정. 문턱은 정수 계조에 적용되므로 반 계조 안에서 움직이면 결과가 안 바뀐다
        ISODATA_TOL_LEVEL = 0.5

        # ----------------------------------------------------------- 채널 분리
        @staticmethod
        def extract_channel(image: Any, channel: Enum) -> Any:
            if image.ndim == 2: return image
            match channel:
                case Tool.Vision.ColorSpace.RGB.R: return image[:, :, 2]
                case Tool.Vision.ColorSpace.RGB.G: return image[:, :, 1]
                case Tool.Vision.ColorSpace.RGB.B: return image[:, :, 0]
                case _:
                    from cv2 import (
                        cvtColor as cv2_cvtColor,
                        COLOR_BGR2HSV as cv2_COLOR_BGR2HSV,
                        COLOR_BGR2HLS as cv2_COLOR_BGR2HLS,
                        COLOR_BGR2YCrCb as cv2_COLOR_BGR2YCrCb,
                        COLOR_BGR2YUV as cv2_COLOR_BGR2YUV,
                        COLOR_BGR2Lab as cv2_COLOR_BGR2Lab,
                        COLOR_BGR2Luv as cv2_COLOR_BGR2Luv,
                        COLOR_BGR2XYZ as cv2_COLOR_BGR2XYZ,
                        COLOR_BGR2GRAY as cv2_COLOR_BGR2GRAY,
                    )
                    match channel:
                        case Tool.Vision.ColorSpace.HSV.H: return cv2_cvtColor(image, cv2_COLOR_BGR2HSV)[:, :, 0]
                        case Tool.Vision.ColorSpace.HSV.S: return cv2_cvtColor(image, cv2_COLOR_BGR2HSV)[:, :, 1]
                        case Tool.Vision.ColorSpace.HSV.V: return cv2_cvtColor(image, cv2_COLOR_BGR2HSV)[:, :, 2]
                        case Tool.Vision.ColorSpace.HLS.H: return cv2_cvtColor(image, cv2_COLOR_BGR2HLS)[:, :, 0]
                        case Tool.Vision.ColorSpace.HLS.L: return cv2_cvtColor(image, cv2_COLOR_BGR2HLS)[:, :, 1]
                        case Tool.Vision.ColorSpace.HLS.S: return cv2_cvtColor(image, cv2_COLOR_BGR2HLS)[:, :, 2]
                        case Tool.Vision.ColorSpace.YCrCb.Y: return cv2_cvtColor(image, cv2_COLOR_BGR2YCrCb)[:, :, 0]
                        case Tool.Vision.ColorSpace.YCrCb.CR: return cv2_cvtColor(image, cv2_COLOR_BGR2YCrCb)[:, :, 1]
                        case Tool.Vision.ColorSpace.YCrCb.CB: return cv2_cvtColor(image, cv2_COLOR_BGR2YCrCb)[:, :, 2]
                        case Tool.Vision.ColorSpace.YUV.Y: return cv2_cvtColor(image, cv2_COLOR_BGR2YUV)[:, :, 0]
                        case Tool.Vision.ColorSpace.YUV.U: return cv2_cvtColor(image, cv2_COLOR_BGR2YUV)[:, :, 1]
                        case Tool.Vision.ColorSpace.YUV.V: return cv2_cvtColor(image, cv2_COLOR_BGR2YUV)[:, :, 2]
                        case Tool.Vision.ColorSpace.Lab.L: return cv2_cvtColor(image, cv2_COLOR_BGR2Lab)[:, :, 0]
                        case Tool.Vision.ColorSpace.Lab.A: return cv2_cvtColor(image, cv2_COLOR_BGR2Lab)[:, :, 1]
                        case Tool.Vision.ColorSpace.Lab.B: return cv2_cvtColor(image, cv2_COLOR_BGR2Lab)[:, :, 2]
                        case Tool.Vision.ColorSpace.Luv.L: return cv2_cvtColor(image, cv2_COLOR_BGR2Luv)[:, :, 0]
                        case Tool.Vision.ColorSpace.Luv.U: return cv2_cvtColor(image, cv2_COLOR_BGR2Luv)[:, :, 1]
                        case Tool.Vision.ColorSpace.Luv.V: return cv2_cvtColor(image, cv2_COLOR_BGR2Luv)[:, :, 2]
                        case Tool.Vision.ColorSpace.XYZ.X: return cv2_cvtColor(image, cv2_COLOR_BGR2XYZ)[:, :, 0]
                        case Tool.Vision.ColorSpace.XYZ.Y: return cv2_cvtColor(image, cv2_COLOR_BGR2XYZ)[:, :, 1]
                        case Tool.Vision.ColorSpace.XYZ.Z: return cv2_cvtColor(image, cv2_COLOR_BGR2XYZ)[:, :, 2]
                        case Tool.Vision.ColorSpace.GRAY.GRAY: return cv2_cvtColor(image, cv2_COLOR_BGR2GRAY)
                        case _: raise Tool.Missing(f"유효하지 않은 색 공간 채널 규격이다 :: {channel}")

        # ----------------------------------------------------------- 작업영역
        @staticmethod
        def crop_to_polygon(image: Any, polygon_px: Sequence[tuple[float, float]], margin_px: int) -> "Tool.Vision.Crop":
            """다각형을 감싸는 직사각형에 여백을 더해 잘라낸다. 바깥을 칠하지 않는다.

            칠하면 두 가지가 틀어진다 — 칠한 색이 히스토그램에 가짜 무리로 섞이고, 칠한 테두리가 가장 강한 경계로 잡힌다.
            그래서 안과 밖은 `mask` 로만 가른다. 여백은 원본 가장자리에서 멈춘다.
            """
            from cv2 import fillPoly as cv2_fillPoly
            from numpy import array as np_array, int32 as np_int32, zeros as np_zeros, uint8 as np_uint8

            height, width = image.shape[:2]
            xs, ys = [x for x, _ in polygon_px], [y for _, y in polygon_px]
            x0, y0 = max(0, int(math.floor(min(xs))) - margin_px), max(0, int(math.floor(min(ys))) - margin_px)
            x1, y1 = min(width, int(math.ceil(max(xs))) + margin_px + 1), min(height, int(math.ceil(max(ys))) + margin_px + 1)
            mask = np_zeros((y1 - y0, x1 - x0), np_uint8)
            cv2_fillPoly(mask, [np_array([(x - x0, y - y0) for x, y in polygon_px]).round().astype(np_int32)], 255)
            return Tool.Vision.Crop(image[y0:y1, x0:x1], mask, (x0, y0))

        # ----------------------------------------------------------- 정규화 및 보정
        @staticmethod
        def flat_field(image: Any, reference: Any, gain_floor_ratio: float, gain_patch_px: int) -> Any:
            """백색 균일 기준면의 중앙 패치 밝기로 게인맵을 생성해 비네팅을 보정한다."""
            from cv2 import cvtColor as cv2_cvtColor, COLOR_BGR2GRAY as cv2_COLOR_BGR2GRAY
            from numpy import (
                clip as np_clip,
                iinfo as np_iinfo,
                integer as np_integer,
                issubdtype as np_issubdtype,
                maximum as np_maximum,
            )

            grey = (
                cv2_cvtColor(reference, cv2_COLOR_BGR2GRAY).astype(float)
                if reference.ndim == 3
                else reference.astype(float)
            )
            height, width = grey.shape[:2]
            half = gain_patch_px // 2
            center = float(
                grey[
                    max(0, height // 2 - half) : min(height, height // 2 + half + 1),
                    max(0, width // 2 - half) : min(width, width // 2 + half + 1),
                ].mean()
            )
            floor = center * gain_floor_ratio
            gain = center / np_maximum(grey, floor)
            ceiling = np_iinfo(image.dtype).max if np_issubdtype(image.dtype, np_integer) else 1.0
            mult = gain[:, :, None] if image.ndim == 3 else gain
            return np_clip(image.astype(float) * mult, 0, ceiling).astype(image.dtype)

        @staticmethod
        def clahe(image: Any, clip_limit: float, grid_cols: int, grid_rows: int) -> Any:
            from cv2 import createCLAHE as cv2_createCLAHE
            return cv2_createCLAHE(clipLimit=clip_limit, tileGridSize=(grid_cols, grid_rows)).apply(image)

        @staticmethod
        def equalize_hist(image: Any, mask: Any) -> Any:
            """히스토그램 평활화. 누적 분포는 `mask` 안쪽 화소로만 세고, 그 표를 영상 전체에 적용한다."""
            from cv2 import LUT as cv2_LUT
            from numpy import bincount as np_bincount, cumsum as np_cumsum, round as np_round, uint8 as np_uint8

            cdf = np_cumsum(np_bincount(image[mask > 0].ravel(), minlength=Tool.Vision.LEVELS)).astype(float)
            cdf_min = cdf[cdf > 0][0]
            table = np_round((cdf - cdf_min) / max(cdf[-1] - cdf_min, Tool.EPS) * 255.0).clip(0, 255).astype(np_uint8)
            return cv2_LUT(image, table)

        @staticmethod
        def gamma(image: Any, gamma_value: float) -> Any:
            from cv2 import LUT as cv2_LUT
            from numpy import array as np_array
            inv_gamma = 1.0 / max(gamma_value, Tool.EPS)
            table = np_array([((gray_level / 255.0) ** inv_gamma) * 255.0 for gray_level in range(256)]).astype(image.dtype)
            return cv2_LUT(image, table)

        @staticmethod
        def whiten(image: Any, mask: Any, eps: float, sigma_span: float) -> Any:
            """화소 평균을 빼고 표준편차로 나누어 조명 절대치 변동을 상쇄한다.

            평균과 표준편차는 `mask` 안쪽 화소로만 잰다. 평균 ± `sigma_span` σ 를 0~255 로 펴 8비트로 낸다 — 그 밖은 양끝에 붙는다.
            """
            from numpy import clip as np_clip, uint8 as np_uint8

            float_image = image.astype(float)
            inside = float_image[mask > 0]
            standardized = (float_image - float(inside.mean())) / (float(inside.std()) + eps)
            return np_clip((standardized / sigma_span + 1.0) * 127.5, 0, 255).astype(np_uint8)

        @staticmethod
        def match_template(image: Any, template: Any, method: int) -> Any:
            from cv2 import matchTemplate as cv2_matchTemplate
            return cv2_matchTemplate(image, template, method)

        @staticmethod
        def normalized_cross_correlation(image: Any, template: Any) -> Any:
            """정규화교차상관 지도. 원본과 같은 크기의 8비트로 낸다.

            값은 템플릿 중심이 놓인 화소에 적는다. 템플릿이 닿지 못하는 가장자리는 상관 0 으로 채운다. −1~1 을 0~255 로 편다.
            """
            from cv2 import (
                copyMakeBorder as cv2_copyMakeBorder,
                matchTemplate as cv2_matchTemplate,
                BORDER_CONSTANT as cv2_BORDER_CONSTANT,
                TM_CCOEFF_NORMED as cv2_TM_CCOEFF_NORMED,
            )
            from numpy import clip as np_clip, uint8 as np_uint8

            response = cv2_matchTemplate(image, template, cv2_TM_CCOEFF_NORMED)
            template_h, template_w = template.shape[:2]
            top, left = template_h // 2, template_w // 2
            padded = cv2_copyMakeBorder(response, top, template_h - 1 - top, left, template_w - 1 - left, cv2_BORDER_CONSTANT, value=0.0)
            return np_clip((padded + 1.0) * 127.5, 0, 255).astype(np_uint8)

        @staticmethod
        def rounded_rect_template(length_px: float, width_px: float, radius_px: float, angle_deg: float) -> Any:
            r"""둥근 직사각형 모양의 흑백 템플릿. 규격 상면을 합성할 때 쓴다.

            회전한 도형이 들어가는 가장 작은 정사각 캔버스에 흰색으로 채운다.
            **화소 중심이 도형 안에 드는 화소**가 흰색이다 — 둥근 직사각형의 부호 거리 $\lVert \max(q, 0) \rVert + \min(\max(q_x, q_y), 0) - r \le 0$, $q = (|u| - L/2 + r,\ |v| - W/2 + r)$ 로 판정한다.
            $(u, v)$ 는 화소 중심을 도형 축으로 돌린 좌표다.

            도형 중심을 캔버스 중심에서 1/4 화소 비켜 놓는다.
            변이 화소 중심을 정확히 지나면 양쪽 경계 화소가 모두 들어와 면적이 커지는데, 비켜 두면 한쪽은 들고 한쪽은 빠진다.
            """
            from numpy import hypot as np_hypot, indices as np_indices, maximum as np_maximum, minimum as np_minimum, uint8 as np_uint8

            side = int(math.ceil(math.hypot(length_px, width_px))) + 2
            rows, cols = np_indices((side, side)).astype(float) - (side - 1) / 2.0 - 0.25
            cos_a, sin_a = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
            along, across = cols * cos_a + rows * sin_a, -cols * sin_a + rows * cos_a
            qx, qy = abs(along) - length_px / 2.0 + radius_px, abs(across) - width_px / 2.0 + radius_px
            distance = np_hypot(np_maximum(qx, 0.0), np_maximum(qy, 0.0)) + np_minimum(np_maximum(qx, qy), 0.0) - radius_px
            return (distance <= 0.0).astype(np_uint8) * 255

        @staticmethod
        def combine(images: Sequence[Any], how: "Tool.Vision.Blend", weights: Sequence[float] | None) -> Any:
            """여러 장을 한 장으로 합친다. `weights` 는 가중 평균만 쓴다.

            n 장을 한 번에 받는다. 가중 평균은 두 장씩 거듭하면 가중이 틀어지기 때문이다 — `평균(평균(a, b), c)` 에서 c 는 절반을 차지한다.
            """
            from numpy import maximum as np_maximum, minimum as np_minimum, uint8 as np_uint8

            match how:
                case Tool.Vision.Blend.WEIGHTED_MEAN:
                    total = sum(weight * image.astype(float) for weight, image in zip(weights, images))
                    return (total / sum(weights)).round().clip(0, 255).astype(np_uint8)
                case Tool.Vision.Blend.MAX: return np_maximum.reduce(list(images))
                case Tool.Vision.Blend.MIN: return np_minimum.reduce(list(images))

        # ----------------------------------------------------------- 형태학적 필터링
        @staticmethod
        def tophat(image: Any, side_px: int) -> Any:
            """타원형 구조요소로 열림 연산 배경을 추출해 차감함으로써 고르지 않은 조명을 평탄화한다."""
            from cv2 import (
                getStructuringElement as cv2_getStructuringElement,
                morphologyEx as cv2_morphologyEx,
                MORPH_ELLIPSE as cv2_MORPH_ELLIPSE,
                MORPH_TOPHAT as cv2_MORPH_TOPHAT,
            )
            return cv2_morphologyEx(image, cv2_MORPH_TOPHAT, cv2_getStructuringElement(cv2_MORPH_ELLIPSE, (kernel_size := Tool.odd(side_px), kernel_size)))

        @staticmethod
        def blackhat(image: Any, side_px: int) -> Any:
            """타원형 구조요소로 닫힘 연산 포락을 구해 원본과의 차이로 필렛 간극 음영을 추출한다."""
            from cv2 import (
                getStructuringElement as cv2_getStructuringElement,
                morphologyEx as cv2_morphologyEx,
                MORPH_ELLIPSE as cv2_MORPH_ELLIPSE,
                MORPH_BLACKHAT as cv2_MORPH_BLACKHAT,
            )
            return cv2_morphologyEx(image, cv2_MORPH_BLACKHAT, cv2_getStructuringElement(cv2_MORPH_ELLIPSE, (kernel_size := Tool.odd(side_px), kernel_size)))

        @staticmethod
        def morphology(image: Any, cv2_operation: int, side_px: int, shape: int) -> Any:
            from cv2 import getStructuringElement as cv2_getStructuringElement, morphologyEx as cv2_morphologyEx
            return cv2_morphologyEx(image, cv2_operation, cv2_getStructuringElement(shape, (kernel_size := Tool.odd(side_px), kernel_size)))

        # ----------------------------------------------------------- 이진화 및 문턱
        @staticmethod
        def level_and_noise(image: Any, mask: Any) -> tuple[float, float]:
            """`mask` 안쪽의 밝기 수준(중앙값)과 잡음(중앙 절대 편차 × 1.4826 — 정규분포의 σ 와 맞춘 값)이다.

            잡음은 밝기 한 단계를 바닥으로 한다 — 8비트 영상은 한 단계보다 가는 차를 담지 못해, 어두운 매트에서 편차가 0 으로 재진다.
            """
            from numpy import abs as np_abs, median as np_median

            values = image[mask > 0]
            level = float(np_median(values))
            return level, max(1.4826 * float(np_median(np_abs(values - level))), 1.0)

        @staticmethod
        def _masked_level(image: Any, mask: Any, method_flag: int) -> float:
            """`mask` 안쪽 화소만 모아 OpenCV 의 자동 문턱(오츠 · 삼각형)을 고른다. `cv2.threshold` 는 마스크를 받지 않는다."""
            from cv2 import threshold as cv2_threshold, THRESH_BINARY as cv2_THRESH_BINARY
            threshold, _ = cv2_threshold(image[mask > 0].reshape(-1, 1), 0, 255, cv2_THRESH_BINARY | method_flag)
            return float(threshold)

        @staticmethod
        def _binarize(image: Any, mask: Any, threshold: float) -> Any:
            """문턱보다 밝은 화소를 흰색으로. `mask` 바깥은 검정이다."""
            from cv2 import bitwise_and as cv2_bitwise_and, threshold as cv2_threshold, THRESH_BINARY as cv2_THRESH_BINARY
            return cv2_bitwise_and(cv2_threshold(image, threshold, 255, cv2_THRESH_BINARY)[1], mask)

        @staticmethod
        def otsu_threshold(image: Any, mask: Any) -> tuple[float, Any]:
            """오츠 문턱. `mask` 안쪽 화소의 히스토그램으로 고른다."""
            from cv2 import THRESH_OTSU as cv2_THRESH_OTSU
            threshold = Tool.Vision._masked_level(image, mask, cv2_THRESH_OTSU)
            return threshold, Tool.Vision._binarize(image, mask, threshold)

        @staticmethod
        def triangle_threshold(image: Any, mask: Any) -> tuple[float, Any]:
            """삼각형 문턱. `mask` 안쪽 화소의 히스토그램으로 고른다."""
            from cv2 import THRESH_TRIANGLE as cv2_THRESH_TRIANGLE
            threshold = Tool.Vision._masked_level(image, mask, cv2_THRESH_TRIANGLE)
            return threshold, Tool.Vision._binarize(image, mask, threshold)

        @staticmethod
        def isodata_threshold(image: Any, mask: Any) -> tuple[float, Any]:
            """isodata(리들러-칼바드) 문턱. 두 무리 평균의 중점으로 수렴시킨다. `mask` 안쪽 화소로만 센다."""
            inside = image[mask > 0]
            threshold = float(inside.mean())
            for _ in range(Tool.Vision.LEVELS):
                fg = inside[inside >= threshold]
                bg = inside[inside < threshold]
                mean_foreground = float(fg.mean()) if fg.size > 0 else threshold
                mean_background = float(bg.mean()) if bg.size > 0 else threshold
                next_t = (mean_foreground + mean_background) / 2.0
                if abs(next_t - threshold) < Tool.Vision.ISODATA_TOL_LEVEL: threshold = next_t; break
                threshold = next_t
            return threshold, Tool.Vision._binarize(image, mask, threshold)

        @staticmethod
        def multi_otsu_threshold(image: Any, mask: Any) -> "Tool.Vision.MultiOtsu":
            r"""다단계 오츠. 문턱 둘로 세 무리를 가른다 — 배경 · 중간(측면 · 음영) · 밝은 무리(상면).

            세 무리의 급간 분산 $\sum_k \mu_k^2 / w_k$ 가 가장 큰 문턱 쌍을 모든 쌍에서 고른다. $w_k$ 는 무리의 화소 비율,
            $\mu_k$ 는 무리의 계조 1차 모멘트다. 계조가 256 이라 쌍은 3 만 남짓이다. `mask` 안쪽 화소로만 센다.
            """
            from numpy import (
                arange as np_arange,
                argmax as np_argmax,
                bincount as np_bincount,
                cumsum as np_cumsum,
                errstate as np_errstate,
                inf as np_inf,
                triu as np_triu,
                ones as np_ones,
                unravel_index as np_unravel_index,
                where as np_where,
            )

            histogram = np_bincount(image[mask > 0].ravel(), minlength=Tool.Vision.LEVELS).astype(float)
            probability = histogram / histogram.sum()
            weight = np_cumsum(probability)[:-1]                                    # 계조 0..i 의 비율
            moment = np_cumsum(probability * np_arange(Tool.Vision.LEVELS))[:-1]    # 계조 0..i 의 1차 모멘트
            total_moment = float((probability * np_arange(Tool.Vision.LEVELS)).sum())
            w0, m0 = weight[:, None], moment[:, None]                               # 행 i :: 낮은 무리 끝
            w2, m2 = 1.0 - weight[None, :], total_moment - moment[None, :]          # 열 j :: 중간 무리 끝
            w1, m1 = weight[None, :] - w0, moment[None, :] - m0
            with np_errstate(divide="ignore", invalid="ignore"):
                between = m0 ** 2 / w0 + m1 ** 2 / w1 + m2 ** 2 / w2
            valid = np_triu(np_ones(between.shape, bool), k=1) & (w0 > 0) & (w1 > 0) & (w2 > 0)
            i, j = np_unravel_index(np_argmax(np_where(valid, between, -np_inf)), between.shape)
            low, high = int(i) + 1, int(j) + 1
            return Tool.Vision.MultiOtsu(low, high, Tool.Vision._binarize(image, mask, low - 1), Tool.Vision._binarize(image, mask, high - 1))

        @staticmethod
        def adaptive_gaussian(image: Any, block_size_px: int, c_offset: float) -> Any:
            from cv2 import adaptiveThreshold as cv2_adaptiveThreshold, ADAPTIVE_THRESH_GAUSSIAN_C as cv2_ADAPTIVE_THRESH_GAUSSIAN_C, THRESH_BINARY as cv2_THRESH_BINARY
            return cv2_adaptiveThreshold(image, 255, cv2_ADAPTIVE_THRESH_GAUSSIAN_C, cv2_THRESH_BINARY, max(3, Tool.odd(block_size_px)), c_offset)

        @staticmethod
        def sauvola_threshold(image: Any, window_px: int, weight_k: float, dynamic_range_r: float) -> Any:
            """국소 표준편차를 동적 반영하여 저대비 경계면과 음영을 적응형으로 분할한다."""
            from cv2 import boxFilter as cv2_boxFilter, BORDER_REPLICATE as cv2_BORDER_REPLICATE, CV_64F as cv2_CV_64F
            from numpy import maximum as np_maximum, sqrt as np_sqrt, uint8 as np_uint8, where as np_where

            float_image = image.astype(float)
            ksize = (window_size := Tool.odd(window_px), window_size)
            mean = cv2_boxFilter(float_image, cv2_CV_64F, ksize, borderType=cv2_BORDER_REPLICATE)
            sq_mean = cv2_boxFilter(float_image ** 2, cv2_CV_64F, ksize, borderType=cv2_BORDER_REPLICATE)
            variance = np_maximum(sq_mean - mean ** 2, 0.0)
            standard_deviation = np_sqrt(variance)
            threshold = mean * (1.0 + weight_k * (standard_deviation / dynamic_range_r - 1.0))
            return np_where(float_image >= threshold, np_uint8(255), np_uint8(0))

        # ----------------------------------------------------------- 경계 및 미분
        @staticmethod
        def canny(image: Any, threshold1: float, threshold2: float, aperture_size: int) -> Any:
            from cv2 import Canny as cv2_Canny
            return cv2_Canny(image, threshold1, threshold2, apertureSize=aperture_size)

        @staticmethod
        def sobel(image: Any, order_x: int, order_y: int, ksize_px: int) -> Any:
            from cv2 import Sobel as cv2_Sobel, convertScaleAbs as cv2_convertScaleAbs, CV_64F as cv2_CV_64F
            return cv2_convertScaleAbs(cv2_Sobel(image, cv2_CV_64F, order_x, order_y, ksize=Tool.odd(ksize_px)))

        @staticmethod
        def scharr(image: Any, dx: int, dy: int) -> Any:
            from cv2 import Scharr as cv2_Scharr, convertScaleAbs as cv2_convertScaleAbs, CV_64F as cv2_CV_64F
            return cv2_convertScaleAbs(cv2_Scharr(image, cv2_CV_64F, dx, dy))

        @staticmethod
        def difference_of_gaussians(image: Any, ksize1_px: int, sigma1: float, ksize2_px: int, sigma2: float) -> Any:
            from cv2 import GaussianBlur as cv2_GaussianBlur
            from numpy import clip as np_clip, uint8 as np_uint8

            fine_blur = cv2_GaussianBlur(image, (k1 := Tool.odd(ksize1_px), k1), sigma1).astype(float)
            coarse_blur = cv2_GaussianBlur(image, (k2 := Tool.odd(ksize2_px), k2), sigma2).astype(float)
            return np_clip(abs(fine_blur - coarse_blur), 0, 255).astype(np_uint8)

        @staticmethod
        def gradient(image: Any, ksize_px: int) -> "Tool.Vision.Gradient":
            r"""기울기 크기와 방향. 소벨이며, `ksize_px` 가 `cv2.FILTER_SCHARR`(−1)면 샤르다.

            크기는 $\sqrt{g_x^2 + g_y^2}$ 를 **이론 최댓값**으로 나눠 8비트로 편다.
            최댓값은 커널 양의 가중 합 × 255 × $\sqrt{2}$ 다 — 영상에 따라 눈금이 바뀌지 않는다.
            마스크로 바꿀 때는 전역 문턱을 그대로 쓴다.
            """
            from cv2 import FILTER_SCHARR as cv2_FILTER_SCHARR, Sobel as cv2_Sobel, getDerivKernels as cv2_getDerivKernels, CV_64F as cv2_CV_64F
            from numpy import arctan2 as np_arctan2, float32 as np_float32, hypot as np_hypot, uint8 as np_uint8

            size = ksize_px if ksize_px == cv2_FILTER_SCHARR else Tool.odd(ksize_px)
            gradient_x = cv2_Sobel(image, cv2_CV_64F, 1, 0, ksize=size)
            gradient_y = cv2_Sobel(image, cv2_CV_64F, 0, 1, ksize=size)
            derivative, smoothing = cv2_getDerivKernels(1, 0, size)
            peak = 255.0 * float(derivative[derivative > 0].sum()) * float(abs(smoothing).sum()) * math.sqrt(2.0)
            magnitude = (np_hypot(gradient_x, gradient_y) / peak * 255.0).round().clip(0, 255).astype(np_uint8)
            return Tool.Vision.Gradient(magnitude, np_arctan2(gradient_y, gradient_x).astype(np_float32))

        # ----------------------------------------------------------- 마스크 조합
        # 마스크는 0 · 255 의 8비트다. 문턱 함수들이 그렇게 낸다
        @staticmethod
        def mask_and(mask_a: Any, mask_b: Any) -> Any:
            """교집합."""
            from cv2 import bitwise_and as cv2_bitwise_and
            return cv2_bitwise_and(mask_a, mask_b)

        @staticmethod
        def mask_or(mask_a: Any, mask_b: Any) -> Any:
            """합집합."""
            from cv2 import bitwise_or as cv2_bitwise_or
            return cv2_bitwise_or(mask_a, mask_b)

        @staticmethod
        def mask_not(mask: Any) -> Any:
            """반전."""
            from cv2 import bitwise_not as cv2_bitwise_not
            return cv2_bitwise_not(mask)

        @staticmethod
        def mask_minus(mask_a: Any, mask_b: Any) -> Any:
            """차집합 `a − b`. 예 :: 실루엣에서 경계를 빼 붙은 블록 사이 틈을 가른다."""
            from cv2 import bitwise_and as cv2_bitwise_and, bitwise_not as cv2_bitwise_not
            return cv2_bitwise_and(mask_a, cv2_bitwise_not(mask_b))

        @staticmethod
        def mask_xor(mask_a: Any, mask_b: Any) -> Any:
            """어느 한쪽에만 있는 곳. 두 방식이 어긋난 자리를 본다."""
            from cv2 import bitwise_xor as cv2_bitwise_xor
            return cv2_bitwise_xor(mask_a, mask_b)

        @staticmethod
        def fill_polygons(shape: tuple[int, int], polygons: Sequence[Sequence[tuple[float, float]]], value: int) -> Any:
            """다각형들을 `value` 로 칠한 8비트 영상. 나머지는 0 이다.

            확정한 단품을 덩어리에서 지울 때 쓴다 — 칠한 뒤 `mask_minus` 로 빼고, 남은 조각을 연결 성분으로 나눈다.
            꼭짓점은 정수로 반올림하므로 칠한 영역이 경계에서 한 화소쯤 넓다. 지우는 쪽으로 넉넉하다.
            """
            from cv2 import fillPoly as cv2_fillPoly
            from numpy import array as np_array, int32 as np_int32, zeros as np_zeros, uint8 as np_uint8

            canvas = np_zeros(shape, np_uint8)
            cv2_fillPoly(canvas, [np_array(polygon).round().astype(np_int32) for polygon in polygons], value)
            return canvas

        @staticmethod
        def paint_prisms(shape: tuple[int, int], prisms: Sequence[tuple[Sequence[tuple[float, float]], Sequence[tuple[float, float]]]],
                         origin_px: tuple[float, float], scale: int) -> Any:
            """위에서 본 기둥들의 부류 지도다. 화소값은 `PrismFace` 다.

            기둥 하나는 (윗면 꼭짓점 화소, 그 바로 아래 바닥 꼭짓점 화소) 한 쌍이다.
            보이는 옆면은 블록 윤곽(`Tool.Geometry.Polygon.silhouette`)에서 윗면을 뺀 영역이다.
            옆면을 모두 먼저 칠하고 윗면을 위에 칠한다 — 윗면이 모두 같은 높이일 때만 윗면이 남의 옆면을 가린다는 것이 맞다.
            `origin_px` 는 부류 지도의 왼쪽 위가 원본에서 놓인 자리, `scale` 은 원본 한 화소를 몇 칸으로 나누는가다.
            """
            from cv2 import fillPoly as cv2_fillPoly
            from numpy import array as np_array, float32 as np_float32, int32 as np_int32, uint8 as np_uint8, zeros as np_zeros

            origin = np_array(origin_px, np_float32)
            to_canvas = lambda points: ((np_array(points, np_float32) - origin) * scale).round().astype(np_int32)
            canvas = np_zeros(shape, np_uint8)
            for top_px, bottom_px in prisms:
                cv2_fillPoly(canvas, [to_canvas(Tool.Geometry.Polygon.silhouette(top_px, bottom_px))], int(Tool.Vision.PrismFace.SIDE))
            for top_px, _ in prisms:
                cv2_fillPoly(canvas, [to_canvas(top_px)], int(Tool.Vision.PrismFace.TOP))
            return canvas

        @staticmethod
        def class_mismatch(drawn: Any, seen: Any, region: Any) -> float:
            """두 부류 지도가 어긋난 몫이다. 1 − (부류가 같은 칠한 화소) ÷ (둘 중 하나라도 칠한 화소), `region` 안쪽만 센다.

            0 이면 두 지도가 같다. 부류 0 은 칠하지 않은 곳이라 둘 다 0 인 화소는 세지 않는다.
            """
            from numpy import count_nonzero as np_count_nonzero

            painted = (region > 0) & ((drawn > 0) | (seen > 0))
            return 1.0 - np_count_nonzero(painted & (drawn == seen)) / np_count_nonzero(painted)

        @staticmethod
        def mask_vote(masks: Sequence[Any], count_min: int) -> Any:
            """다수결. `masks` 가운데 `count_min` 장 이상이 흰 곳만 남긴다."""
            from numpy import uint8 as np_uint8
            votes = sum((mask > 0).astype(np_uint8) for mask in masks)
            return (votes >= count_min).astype(np_uint8) * 255

        # ----------------------------------------------------------- 단순화 및 면분할
        @staticmethod
        def find_contours(image: Any, mode: int, method: int) -> tuple[Any, ...]:
            from cv2 import findContours as cv2_findContours
            return tuple(cv2_findContours(image, mode, method)[0])

        @staticmethod
        def approx_poly_dp(curve: Any, epsilon_px: float, closed: bool) -> Any:
            from cv2 import approxPolyDP as cv2_approxPolyDP
            return cv2_approxPolyDP(curve, epsilon_px, closed)

        @staticmethod
        def hough_lines_p(image: Any, rho_px: float, theta_rad: float, threshold: int, min_length_px: float, max_gap_px: float) -> Any | None:
            from cv2 import HoughLinesP as cv2_HoughLinesP
            lines = cv2_HoughLinesP(image, rho=rho_px, theta=theta_rad, threshold=threshold, minLineLength=min_length_px, maxLineGap=max_gap_px)
            return lines.reshape(-1, 4) if lines is not None else None

        @staticmethod
        def watershed(image: Any, markers: Any) -> Any:
            from cv2 import cvtColor as cv2_cvtColor, watershed as cv2_watershed, COLOR_GRAY2BGR as cv2_COLOR_GRAY2BGR
            from numpy import int32 as np_int32

            image_bgr = cv2_cvtColor(image, cv2_COLOR_GRAY2BGR) if image.ndim == 2 else image
            markers_copy = markers.copy().astype(np_int32)
            cv2_watershed(image_bgr, markers_copy)
            return markers_copy

        @staticmethod
        def count_changed_pixels(previous_gray: Any, current_gray: Any, level_min: float) -> int:
            from cv2 import absdiff as cv2_absdiff
            return int((cv2_absdiff(current_gray, previous_gray) >= level_min).sum())

        @staticmethod
        def threshold_hough_lines(image: Any, threshold: float, rho_px: float, theta_rad: float, hough_threshold: int, min_length_px: float, max_gap_px: float) -> Any | None:
            from cv2 import threshold as cv2_threshold, HoughLinesP as cv2_HoughLinesP, THRESH_BINARY as cv2_THRESH_BINARY
            lines = cv2_HoughLinesP(cv2_threshold(image, threshold, 255, cv2_THRESH_BINARY)[1], rho=rho_px, theta=theta_rad, threshold=hough_threshold, minLineLength=min_length_px, maxLineGap=max_gap_px)
            return lines.reshape(-1, 4) if lines is not None else None

    class Geometry:
        """좌표·선분·외곽선의 기하 관계 계산과 공간 분할. 허용 공차와 거리 임계값은 전부 인자로 받는다 — 기본값을 두면 튜닝이 도구 안에 숨는다."""

        @staticmethod
        def projective_denominator(matrix: tuple[tuple[float, ...], ...], u: float, v: float) -> float:
            """3x3 사영 행렬이 점 `(u, v)` 에 주는 동차 좌표의 셋째 수. 0 에 가까울수록 그 점이 소실선에 가깝다."""
            return matrix[2][0] * u + matrix[2][1] * v + matrix[2][2]

        @staticmethod
        def project(matrix: tuple[tuple[float, ...], ...], u: float, v: float) -> tuple[float, float]:
            """3x3 사영 행렬로 한 점을 보낸다. 동차 좌표를 나눠 평면으로 되돌린다."""
            projection_x = matrix[0][0] * u + matrix[0][1] * v + matrix[0][2]
            projection_y = matrix[1][0] * u + matrix[1][1] * v + matrix[1][2]
            projection_scale_w = Tool.Geometry.projective_denominator(matrix, u, v)
            if abs(projection_scale_w) < Tool.EPS: raise ValueError("사영 분모가 0 이다 — 점이 소실선 위에 있다")
            return (projection_x / projection_scale_w, projection_y / projection_scale_w)

        class Defect:
            """외곽선 볼록 결함 기하 연산."""

            @staticmethod
            def extract_points(contour: Any, depth_min_px: float, cut_angle_cos: float, cut_angle_sin: float) -> tuple[tuple[tuple[int, int], tuple[float, float], tuple[float, float]], ...]:
                from cv2 import convexHull as cv2_convexHull, convexityDefects as cv2_convexityDefects

                hull = cv2_convexHull(contour, returnPoints=False) if len(contour) >= 4 else None
                defects = cv2_convexityDefects(contour, hull) if (hull is not None and len(hull) >= 3) else None
                if defects is None: return ()

                contour_points = contour.reshape(-1, 2)
                points_count = len(contour_points)
                notches = []

                for defect_index in range(defects.shape[0]):
                    _, _, far_index, depth_fix = defects[defect_index]
                    depth_px = depth_fix / 256.0
                    if depth_px < depth_min_px: continue

                    far_point = contour_points[far_index]
                    vector_previous = contour_points[(far_index - 1) % points_count] - far_point
                    vector_next = contour_points[(far_index + 1) % points_count] - far_point
                    norm_previous = float(math.hypot(float(vector_previous[0]), float(vector_previous[1])))
                    norm_next = float(math.hypot(float(vector_next[0]), float(vector_next[1])))
                    if norm_previous <= Tool.EPS or norm_next <= Tool.EPS: continue
                    unit_previous = (float(vector_previous[0] / norm_previous), float(vector_previous[1] / norm_previous))
                    unit_next = (float(vector_next[0] / norm_next), float(vector_next[1] / norm_next))

                    dot = abs(unit_previous[0] * unit_next[0] + unit_previous[1] * unit_next[1])
                    cross = abs(unit_previous[0] * unit_next[1] - unit_previous[1] * unit_next[0])
                    is_geom_valid = (
                        (dot >= cut_angle_cos or cross <= cut_angle_sin)
                        or (cross >= cut_angle_cos or dot <= cut_angle_sin)
                    )
                    if is_geom_valid: notches.append(((int(far_point[0]), int(far_point[1])), unit_previous, unit_next))

                return tuple(notches)

            @staticmethod
            def connect_pairs(defects: Sequence[tuple[tuple[int, int], tuple[float, float], tuple[float, float]]], mask: Any, min_distance_px: float, max_distance_px: float, sample_step_px: float) -> tuple[tuple[tuple[int, int], tuple[int, int]], ...]:
                from numpy import clip as np_clip, int32 as np_int32, linspace as np_linspace

                cuts = []
                defects_count = len(defects)
                mask_height, mask_width = mask.shape[:2]
                for index_a in range(defects_count):
                    point_a = defects[index_a][0]
                    for index_b in range(index_a + 1, defects_count):
                        point_b = defects[index_b][0]
                        distance = float(math.hypot(point_b[0] - point_a[0], point_b[1] - point_a[1]))
                        if Tool.outside(distance, (min_distance_px, max_distance_px)) > 0.0: continue

                        steps = max(2, int(distance / max(sample_step_px, 1.0)))
                        xs = np_clip(np_linspace(point_a[0], point_b[0], steps).astype(np_int32), 0, mask_width - 1)
                        ys = np_clip(np_linspace(point_a[1], point_b[1], steps).astype(np_int32), 0, mask_height - 1)
                        if mask[ys, xs].all(): cuts.append((point_a, point_b))
                return tuple(cuts)

        class Segment:
            """2차원 선분 기하 연산."""

            @staticmethod
            def convergence_resolvable_distance_px(baseline_px: float, segment_px: float, position_sigma_px: float, margin: float) -> float:
                r"""선분들이 한 점으로 모이는 것을 평행과 가를 수 있는 그 점까지의 거리 한계.

                거리 $D$ 에 있는 점으로 모이는 두 직선이 $B$ 만큼 떨어져 있으면 둘이 이루는 각은 $B / D$ 다.
                길이 $\ell$ 인 선분의 방향은 양 끝점 위치 오차 $\sigma$ 때문에 $\sqrt{2}\,\sigma / \ell$ 만큼 흔들린다.
                모이는 각이 흔들림의 `margin` 배는 넘어야 보이므로 $D_{\max} = B\,\ell / (\text{margin}\,\sqrt{2}\,\sigma)$ 다.

                유효 조건 :: 각이 작아 $\tan\theta \approx \theta$ 인 범위다.
                $D$ 가 이보다 크면 평행으로 둬도 선분 끝의 어긋남 $\ell B / D$ 가 위치 오차보다 작다.
                """
                return baseline_px * segment_px / (margin * math.sqrt(2.0) * position_sigma_px)

            @staticmethod
            def connect_collinear(segments: Sequence[tuple[tuple[float, float], tuple[float, float]]], angle_cos_limit: float, gap_max_px: float) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
                merged = []
                used = [False] * len(segments)

                for segment_index_a in range(len(segments)):
                    if used[segment_index_a]: continue
                    segment_start_a, segment_end_a = segments[segment_index_a]
                    vector_a = (segment_end_a[0] - segment_start_a[0], segment_end_a[1] - segment_start_a[1])
                    len1 = float(math.hypot(vector_a[0], vector_a[1]))
                    if len1 <= Tool.EPS: continue
                    unit_a = (vector_a[0] / len1, vector_a[1] / len1)

                    best_match = -1
                    for segment_index_b in range(segment_index_a + 1, len(segments)):
                        if used[segment_index_b]: continue
                        segment_start_b, segment_end_b = segments[segment_index_b]
                        vector_b = (segment_end_b[0] - segment_start_b[0], segment_end_b[1] - segment_start_b[1])
                        len2 = float(math.hypot(vector_b[0], vector_b[1]))
                        if len2 <= Tool.EPS: continue
                        unit_b = (vector_b[0] / len2, vector_b[1] / len2)
                        dot = abs(unit_a[0] * unit_b[0] + unit_a[1] * unit_b[1])
                        if dot < angle_cos_limit: continue

                        gap = min(
                            float(math.hypot(segment_end_a[0] - segment_start_b[0], segment_end_a[1] - segment_start_b[1])),
                            float(math.hypot(segment_start_a[0] - segment_end_b[0], segment_start_a[1] - segment_end_b[1])),
                            float(math.hypot(segment_start_a[0] - segment_start_b[0], segment_start_a[1] - segment_start_b[1])),
                            float(math.hypot(segment_end_a[0] - segment_end_b[0], segment_end_a[1] - segment_end_b[1])),
                        )
                        if gap <= gap_max_px:
                            best_match = segment_index_b
                            break

                    all_points = [segment_start_a, segment_end_a, segments[best_match][0], segments[best_match][1]] if best_match != -1 else [segment_start_a, segment_end_a]
                    if best_match != -1: used[best_match] = True
                    projs = [endpoint[0] * unit_a[0] + endpoint[1] * unit_a[1] for endpoint in all_points]
                    projection_minimum_index = min(range(len(projs)), key=projs.__getitem__)
                    projection_maximum_index = max(range(len(projs)), key=projs.__getitem__)
                    merged.append((all_points[projection_minimum_index], all_points[projection_maximum_index]))
                    used[segment_index_a] = True

                return tuple(merged)

            @staticmethod
            def snap_to_points(segments: Sequence[tuple[tuple[float, float], tuple[float, float]]], points: Sequence[tuple[int, int]], snap_distance_px: float) -> tuple[tuple[tuple[int, int], tuple[int, int]], ...]:
                connections = []
                for segment_start, segment_end in segments:
                    for candidate_point in points:
                        for endpoint in (segment_start, segment_end):
                            distance = float(math.hypot(endpoint[0] - candidate_point[0], endpoint[1] - candidate_point[1]))
                            if distance > 0.0 and Tool.outside(distance, (0.0, snap_distance_px)) == 0.0:
                                connections.append(((int(round(endpoint[0])), int(round(endpoint[1]))), candidate_point))
                return tuple(connections)

        class Partition:
            """수학적 영역 및 점군 분할 알고리즘군."""

            @staticmethod
            def by_cuts(mask: Any, cuts: Sequence[tuple[tuple[int, int], tuple[int, int]]], line_thickness_px: int) -> tuple[Any, ...]:
                from cv2 import (
                    CHAIN_APPROX_SIMPLE as cv2_CHAIN_APPROX_SIMPLE,
                    RETR_EXTERNAL as cv2_RETR_EXTERNAL,
                    findContours as cv2_findContours,
                    line as cv2_line,
                )
                work_mask = mask.copy()
                for cut_start, cut_end in cuts:
                    cv2_line(work_mask, cut_start, cut_end, 0, thickness=line_thickness_px)
                contours, _ = cv2_findContours(work_mask, cv2_RETR_EXTERNAL, cv2_CHAIN_APPROX_SIMPLE)
                return tuple(contours)

            @staticmethod
            def by_connected_components(mask: Any, min_area_px: int) -> tuple[Any, ...]:
                from cv2 import (
                    CC_STAT_AREA as cv2_CC_STAT_AREA,
                    connectedComponentsWithStats as cv2_connectedComponentsWithStats,
                )
                from numpy import uint8 as np_uint8, where as np_where

                labels_count, labels, stats, _ = cv2_connectedComponentsWithStats(mask, connectivity=8)
                lumps = []
                for label_index in range(1, labels_count):
                    area = stats[label_index, cv2_CC_STAT_AREA]
                    if area >= min_area_px: lumps.append(np_where(labels == label_index, np_uint8(255), np_uint8(0)))
                return tuple(lumps)

            @staticmethod
            def by_distance_watershed(image: Any, mask: Any, distance_ratio: float, min_area_px: int) -> tuple[Any, ...]:
                from cv2 import (
                    COLOR_GRAY2BGR as cv2_COLOR_GRAY2BGR,
                    DIST_L2 as cv2_DIST_L2,
                    THRESH_BINARY as cv2_THRESH_BINARY,
                    connectedComponents as cv2_connectedComponents,
                    cvtColor as cv2_cvtColor,
                    distanceTransform as cv2_distanceTransform,
                    threshold as cv2_threshold,
                    watershed as cv2_watershed,
                )
                from numpy import uint8 as np_uint8, where as np_where

                distance_transform = cv2_distanceTransform(mask, cv2_DIST_L2, 5)
                maximum_distance = float(distance_transform.max())
                _, sure_fg = cv2_threshold(distance_transform, max(maximum_distance * distance_ratio, 1.0), 255, cv2_THRESH_BINARY)
                markers_count, markers = cv2_connectedComponents(sure_fg.astype(np_uint8))
                markers = markers + 1
                markers[mask == 0] = 0

                bgr = cv2_cvtColor(image, cv2_COLOR_GRAY2BGR) if image.ndim == 2 else image
                cv2_watershed(bgr, markers)

                lumps = []
                for marker_index in range(2, markers_count + 1):
                    lump_mask = np_where(markers == marker_index, np_uint8(255), np_uint8(0))
                    if int(lump_mask.sum()) >= min_area_px: lumps.append(lump_mask)
                return tuple(lumps)

            @staticmethod
            def by_kmeans(mask: Any, cluster_count: int, max_iter: int, attempts: int) -> tuple[Any, ...]:
                from cv2 import (
                    KMEANS_PP_CENTERS as cv2_KMEANS_PP_CENTERS,
                    TERM_CRITERIA_EPS as cv2_TERM_CRITERIA_EPS,
                    TERM_CRITERIA_MAX_ITER as cv2_TERM_CRITERIA_MAX_ITER,
                    kmeans as cv2_kmeans,
                )
                from numpy import (
                    column_stack as np_column_stack,
                    float32 as np_float32,
                    uint8 as np_uint8,
                    where as np_where,
                    zeros as np_zeros,
                )

                ys, xs = np_where(mask > 0)
                if len(xs) < cluster_count: return (mask.copy(),) if len(xs) > 0 else ()
                points_f32 = np_column_stack((xs, ys)).astype(np_float32)
                criteria = (cv2_TERM_CRITERIA_EPS + cv2_TERM_CRITERIA_MAX_ITER, max_iter, 1.0)
                _, labels, _ = cv2_kmeans(points_f32, cluster_count, None, criteria, attempts, cv2_KMEANS_PP_CENTERS)
                labels = labels.flatten()

                mask_height, mask_width = mask.shape[:2]
                lumps = []
                for cluster_index in range(cluster_count):
                    lump_mask = np_zeros((mask_height, mask_width), dtype=np_uint8)
                    sel = labels == cluster_index
                    lump_mask[ys[sel], xs[sel]] = 255
                    lumps.append(lump_mask)
                return tuple(lumps)

            @staticmethod
            def by_graphcut(image: Any, bounding_box: tuple[int, int, int, int], iter_count: int) -> Any:
                from cv2 import (
                    COLOR_GRAY2BGR as cv2_COLOR_GRAY2BGR,
                    GC_FGD as cv2_GC_FGD,
                    GC_INIT_WITH_RECT as cv2_GC_INIT_WITH_RECT,
                    GC_PR_FGD as cv2_GC_PR_FGD,
                    cvtColor as cv2_cvtColor,
                    grabCut as cv2_grabCut,
                )
                from numpy import float64 as np_float64, uint8 as np_uint8, where as np_where, zeros as np_zeros

                bgr = cv2_cvtColor(image, cv2_COLOR_GRAY2BGR) if image.ndim == 2 else image
                image_height, image_width = bgr.shape[:2]
                mask = np_zeros((image_height, image_width), dtype=np_uint8)
                bgd_model = np_zeros((1, 65), dtype=np_float64)
                fgd_model = np_zeros((1, 65), dtype=np_float64)
                cv2_grabCut(bgr, mask, bounding_box, bgd_model, fgd_model, iter_count, cv2_GC_INIT_WITH_RECT)
                return np_where((mask == cv2_GC_FGD) | (mask == cv2_GC_PR_FGD), np_uint8(255), np_uint8(0))

            @staticmethod
            def points_by_distance(points: Any, distance_threshold_px: float) -> tuple[Any, ...]:
                from numpy import hypot as np_hypot, where as np_where, zeros as np_zeros

                points_float64 = points.astype(float)
                points_count = len(points_float64)
                visited = np_zeros(points_count, dtype=bool)
                clusters = []

                for point_index in range(points_count):
                    if visited[point_index]: continue
                    cluster_indices = [point_index]
                    visited[point_index] = True
                    queue = [point_index]
                    while queue:
                        current_point_index = queue.pop(0)
                        diffs = points_float64 - points_float64[current_point_index]
                        dists = np_hypot(diffs[:, 0], diffs[:, 1])
                        neighbors = np_where((dists <= distance_threshold_px) & (~visited))[0]
                        for neighbor in neighbors:
                            visited[neighbor] = True
                            queue.append(neighbor)
                            cluster_indices.append(neighbor)
                    clusters.append(points_float64[cluster_indices])
                return tuple(clusters)

        class Polygon:
            """다각형 위상 및 적합 지표."""

            @staticmethod
            def perimeter_order(points: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
                """점을 무게중심 둘레의 각도 순으로 세운다. 어느 순서로 받아도 변끼리 엇갈리지 않는 둘레가 된다.

                받은 순서가 둘레 순서라는 보장이 없는 곳에 쓴다 — 대각선끼리 이어지는 순서면 채우기가 나비꼴이 된다.
                각도 순으로 세운 다각형은 중심에서 모든 꼭짓점이 보이므로 변이 엇갈리지 않는다. 첫 점과 도는 방향은 뜻이 없다.
                """
                xs, ys = zip(*points)
                center_x, center_y = sum(xs) / len(points), sum(ys) / len(points)
                return tuple(sorted(points, key=lambda point: math.atan2(point[1] - center_y, point[0] - center_x)))

            @staticmethod
            def quad_aspect_ratio(points: Sequence[tuple[float, float]]) -> float:
                """둘레 차례로 온 사각형 네 점의 종횡비. 마주 보는 두 변 길이를 평균해 긴 쪽을 짧은 쪽으로 나눈다 — 1 이상이다.

                원근으로 기운 사각형도 마주 보는 변을 평균하면 가로 · 세로 길이에 가깝다.
                """
                first, second, third, fourth = itertools.starmap(math.dist, Tool.closed_edges(tuple(points)))
                along, across = (first + third) / 2.0, (second + fourth) / 2.0
                return max(along, across) / min(along, across)

            @staticmethod
            def counterclockwise(points: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
                """둘레 차례로 온 다각형을 반시계로 세운다. 시계 방향이면 뒤집는다 — 안쪽 법선이 늘 변의 왼쪽이 된다."""
                points = tuple(points)
                return points if Tool.Geometry.Polygon.signed_area(points) >= 0.0 else points[::-1]

            @staticmethod
            def signed_area(points: Sequence[tuple[float, float]]) -> float:
                """둘레 차례로 온 다각형의 부호 있는 넓이(신발끈). 반시계면 양수다."""
                return sum(start[0] * end[1] - end[0] * start[1] for start, end in Tool.closed_edges(tuple(points))) / 2.0

            @staticmethod
            def inward_normal(start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float]:
                """반시계 다각형의 변 하나에서 안쪽을 가리키는 단위 법선. 변의 왼쪽이다."""
                length = math.dist(start, end)
                return (-(end[1] - start[1]) / length, (end[0] - start[0]) / length)

            @staticmethod
            def half_plane_clipped(points: Sequence[tuple[float, float]], origin: tuple[float, float],
                                   normal: tuple[float, float], offset: float) -> tuple[tuple[float, float], ...]:
                r"""볼록 다각형에서 $\mathbf{n} \cdot (\mathbf{p} - \mathbf{o}) \ge d$ 쪽만 남긴다(서덜랜드-호지먼 한 번). 남는 것이 없으면 빈 튜플이다.

                변 하나를 안으로 $d$ 만큼 민 직선으로 자르는 것과 같다. 볼록 다각형을 자른 것은 볼록하다.
                """
                def side(point): return normal[0] * (point[0] - origin[0]) + normal[1] * (point[1] - origin[1]) - offset

                kept = []
                for start, end in Tool.closed_edges(tuple(points)):
                    start_side, end_side = side(start), side(end)
                    if start_side >= 0.0: kept.append(start)
                    if (start_side >= 0.0) != (end_side >= 0.0):
                        ratio = start_side / (start_side - end_side)
                        kept.append((start[0] + ratio * (end[0] - start[0]), start[1] + ratio * (end[1] - start[1])))
                return tuple(kept)

            @staticmethod
            def chord_y(points: Sequence[tuple[float, float]], x: float) -> tuple[float, float]:
                """볼록 다각형을 세로선 $x$ 로 자른 구간 (아래, 위). 세로선이 다각형을 지나야 한다."""
                crossings = []
                for start, end in Tool.closed_edges(tuple(points)):
                    if min(start[0], end[0]) <= x <= max(start[0], end[0]):
                        if start[0] == end[0]:
                            crossings += [start[1], end[1]]
                        else:
                            crossings.append(start[1] + (x - start[0]) / (end[0] - start[0]) * (end[1] - start[1]))
                return (min(crossings), max(crossings))

            @staticmethod
            def ray_span(points: Sequence[tuple[float, float]], angle_rad: float) -> tuple[float, float] | None:
                r"""원점에서 각 $\theta$ 로 낸 반직선이 볼록 다각형을 지나는 거리 구간 (들어감, 나감). 안 지나면 `None` 이다.

                볼록 다각형은 변마다 안쪽 반평면의 교집합이다(`half_plane_clipped`). 반직선 위 점 $t\mathbf{d}$ 가 변의 안쪽이려면
                $t\,(\mathbf{n} \cdot \mathbf{d}) \ge \mathbf{n} \cdot \mathbf{s}$ 다($\mathbf{n}$ 안쪽 법선 · $\mathbf{s}$ 변의 시작) — 변마다 $t$ 의 아래나 위 한계가 하나씩 선다.
                꼭짓점을 스치는 반직선은 두 한계가 한 점에서 만난다. 부동소수 오차 안이면 만난 것으로 본다(`math.isclose`).
                원점이 다각형 밖이어야 들어감과 나감이 갈린다.
                """
                polygon = Tool.Geometry.Polygon
                direction_x, direction_y = math.cos(angle_rad), math.sin(angle_rad)
                near, far = 0.0, math.inf
                for start, end in Tool.closed_edges(polygon.counterclockwise(points)):
                    normal_x, normal_y = polygon.inward_normal(start, end)
                    facing = normal_x * direction_x + normal_y * direction_y
                    offset = normal_x * start[0] + normal_y * start[1]
                    if facing == 0.0:
                        if offset > 0.0: return None
                        continue
                    if facing > 0.0: near = max(near, offset / facing)
                    else: far = min(far, offset / facing)
                if near > far and not math.isclose(near, far): return None
                return near, max(near, far)

            @staticmethod
            def annulus_clipped(points: Sequence[tuple[float, float]], radius: tuple[float, float],
                                angle_deg: tuple[float, float], sagitta: float) -> tuple[tuple[tuple[float, float], ...], ...]:
                r"""볼록 다각형 가운데 원점 둘레 고리(반경 `radius`) · 각 범위(`angle_deg`) 안에 드는 곳의 외곽선들. 원점이 다각형 밖이어야 한다.

                원점이 밖이라 원점에서 낸 반직선마다 다각형을 한 구간 [들어감, 나감] 으로 지난다(`ray_span`).
                고리와 겹친 곳은 각마다 $[\max(\text{들어감}, r_{lo}), \min(\text{나감}, r_{hi})]$ 이다.
                각을 훑으며 안쪽 끝을 늘어놓고 바깥 끝을 거꾸로 이으면 외곽선이다.
                겹친 곳이 비는 각에서 끊기므로 외곽선이 여럿일 수 있다.

                표본 각은 다각형 꼭짓점 · 두 원이 변과 만나는 점 · 바깥 원호를 꺾은선으로 펼 때 화살 높이 $r(1 - \cos\frac{\Delta\theta}{2})$ 가 `sagitta` 를 넘지 않는 간격이다.
                꼭짓점과 만나는 점을 표본에 넣으므로 변 위의 외곽선은 꺾은선이 곧 변이다.
                """
                points = tuple(points)
                low_mm, high_mm = radius
                center_x, center_y = sum(x for x, _ in points) / len(points), sum(y for _, y in points) / len(points)
                middle = math.atan2(center_y, center_x)

                def unwrapped(x: float, y: float) -> float:
                    #: (각 − 가운데 + π) mod 2π − π :: 다각형이 ±π 를 걸쳐도 이어진 각으로 센다
                    return middle + (math.atan2(y, x) - middle + math.pi) % (2.0 * math.pi) - math.pi

                corners = [unwrapped(x, y) for x, y in points]
                first = max(min(corners), math.radians(angle_deg[0]))
                last = min(max(corners), math.radians(angle_deg[1]))
                if first >= last: return ()

                angles = set(corners)
                for (start_x, start_y), (end_x, end_y) in Tool.closed_edges(points):
                    edge_x, edge_y = end_x - start_x, end_y - start_y
                    #: |s + u(e − s)|² = r² 를 u 의 이차식으로
                    a, b = edge_x ** 2 + edge_y ** 2, 2.0 * (start_x * edge_x + start_y * edge_y)
                    for circle_mm in (low_mm, high_mm):
                        c = start_x ** 2 + start_y ** 2 - circle_mm ** 2
                        discriminant = b * b - 4.0 * a * c
                        if discriminant < 0.0: continue
                        for along in ((-b - math.sqrt(discriminant)) / (2.0 * a), (-b + math.sqrt(discriminant)) / (2.0 * a)):
                            if 0.0 <= along <= 1.0: angles.add(unwrapped(start_x + along * edge_x, start_y + along * edge_y))
                step = 2.0 * math.acos(max(-1.0, 1.0 - sagitta / high_mm))
                count = max(1, math.ceil((last - first) / step))
                angles.update(first + (last - first) * index / count for index in range(count + 1))

                loops, run = [], []
                for angle in sorted(angle for angle in angles if first <= angle <= last):
                    span = Tool.Geometry.Polygon.ray_span(points, angle)
                    near, far = (max(span[0], low_mm), min(span[1], high_mm)) if span else (1.0, 0.0)
                    if near <= far:
                        run.append((angle, near, far))
                        continue
                    if run: loops.append(run)
                    run = []
                if run: loops.append(run)
                return tuple(
                    tuple((near * math.cos(angle), near * math.sin(angle)) for angle, near, _ in run)
                    + tuple((far * math.cos(angle), far * math.sin(angle)) for angle, _, far in reversed(run))
                    for run in loops)

            @staticmethod
            def solidity(contour: Any) -> tuple[float, float, float]:
                from cv2 import contourArea as cv2_contourArea, convexHull as cv2_convexHull
                area = float(cv2_contourArea(contour))
                hull = cv2_convexHull(contour)
                hull_area = float(cv2_contourArea(hull)) if hull is not None else 0.0
                solidity = (area / hull_area) if hull_area > 0.0 else 0.0
                return area, hull_area, solidity

            @staticmethod
            def silhouette(upper_px: Any, under_px: Any) -> Any:
                """블록의 화면 윤곽. 윗면과 밑면 꼭짓점을 합친 볼록 껍질이다 — 볼록한 블록의 실루엣은 꼭짓점의 볼록 껍질이다."""
                from cv2 import convexHull as cv2_convexHull
                from numpy import array as np_array, float32 as np_float32, vstack as np_vstack

                return cv2_convexHull(np_vstack([np_array(upper_px, np_float32), np_array(under_px, np_float32)])).reshape(-1, 2)

            @staticmethod
            def evaluate_iou(hull_points: Any, observed_mask: Any) -> float:
                from cv2 import fillPoly as cv2_fillPoly
                from numpy import int32 as np_int32, uint8 as np_uint8, zeros as np_zeros

                mask_height, mask_width = observed_mask.shape[:2]
                pred_mask = np_zeros((mask_height, mask_width), dtype=np_uint8)
                points_int32 = hull_points.round().astype(np_int32)
                cv2_fillPoly(pred_mask, [points_int32], 255)

                intersection = ((pred_mask > 0) & (observed_mask > 0)).sum()
                union = ((pred_mask > 0) | (observed_mask > 0)).sum()
                return float(intersection / union) if union > 0 else 0.0

    class Fit:
        """모형을 관측에 맞추는 해법들. 해법 하나가 클래스 하나로 아래에 선다.

        **여기 이름을 걸어 두는 까닭은 해법이 여럿이기 때문이다.** 같은 물음을 다른 해법으로 풀어 보고 점수로 고르는 것이 이 프로젝트의 전제이므로, 해법끼리 형제로 서야 갈아 끼우는 자리가 보인다.

        **어느 해법도 무엇을 적합하는지 모른다.** 모형을 안쪽에 넣으면 모형마다 해법이 하나씩 생겨 같은 소거가 여러 벌이 된다.
        """

        class LeastSquares:
            """잔차 제곱합을 가장 작게 하는 해.

            설계행렬의 행과 관측을 받을 뿐이라 열이 무슨 뜻인지는 부르는 쪽이 안다.
            `Acoustic` 과 같은 결로 튜닝을 안 들고 계산만 한다.
            """

            #: 배정밀도가 구별하는 최소 상대 간격. 추축 바닥을 세우는 재료다.
            EPS = sys.float_info.epsilon

            @classmethod
            def solve(cls, rows: Sequence[Sequence[float]], constants: Sequence[float]) -> tuple[float, ...]:
                r"""설계행렬 `rows` 와 관측 `values` 의 최소자승 해.

                정규방정식 $A^{T}A\,x = A^{T}b$ 를 세워 부분 추축 가우스 소거로 푼다.
                미지수가 적고(아핀 한 줄이 셋) 관측이 흩어져 있으면 정규방정식이 조건수를 제곱하는 것이 문제가 되지 않는다.

                **추축 바닥은 행렬에서 나온다** :: $n \cdot \varepsilon \cdot \max|N|$.
                이보다 작은 추축은 그 행렬을 배정밀도로 세울 때 생기는 반올림에 묻혀 0 과 구별되지 않는다.
                고정값으로 두면 행렬 크기에 따라 뜻이 달라진다.

                **막는 것은 "풀 수 없다" 하나뿐이다.**
                풀리기는 하는데 나쁘게 풀리는 것은 여기서 안 본다 — 해법은 열이 무슨 뜻인지 모른다. 아핀의 대응점 배치는 `Config.VisionAlgorithm.AffineTransform.design_condition_number` 가 본다.
                """
                width = len(rows[0])
                if len(rows) < width: raise Tool.Missing(f"미지수 {width} 개를 풀기에 관측 {len(rows)} 개는 모자란다")

                # ----------------------------------------- 정규방정식을 세운다
                normal = [[sum(row[pivot_row_index] * row[column_index] for row in rows) for column_index in range(width)]
                          for pivot_row_index in range(width)]
                right = [sum(row[pivot_row_index] * constant for row, constant in zip(rows, constants)) for pivot_row_index in range(width)]
                floor = width * cls.EPS * max(abs(matrix_element) for row in normal for matrix_element in row)

                # --------------------------------------- 부분 추축 가우스 소거
                for step in range(width):
                    pivot = max(range(step, width), key=lambda row_index: abs(normal[row_index][step]))
                    # 무엇이 겹쳤는지는 모형을 아는 쪽이 말한다. 여기서 원인을 이름 붙이면 아핀에 맞춘 문장이 사영에서 거짓이 된다
                    if abs(normal[pivot][step]) < floor: raise ValueError("설계행렬이 특이하다 — 관측이 서로 독립인 식을 못 준다")
                    normal[step], normal[pivot] = normal[pivot], normal[step]
                    right[step], right[pivot] = right[pivot], right[step]
                    for under in range(step + 1, width):
                        ratio = normal[under][step] / normal[step][step]
                        for col in range(step, width):
                            normal[under][col] -= ratio * normal[step][col]
                        right[under] -= ratio * right[step]

                # --------------------------------------------------- 후진 대입
                answer = [0.0] * width
                for step in reversed(range(width)):
                    back_substitution_sum = sum(normal[step][col] * answer[col] for col in range(step + 1, width))
                    answer[step] = (right[step] - back_substitution_sum) / normal[step][step]
                return tuple(answer)

            @staticmethod
            def residuals(rows: Sequence[Sequence[float]], constants: Sequence[float], answer: Sequence[float]) -> tuple[float, ...]:
                """관측마다 남은 오차. 부호를 지운다 — 크기만 보고 채택을 가른다."""
                return tuple(abs(sum(coefficient * solution for coefficient, solution in zip(row, answer)) - constant)
                             for row, constant in zip(rows, constants))

        class Homography:
            """3x3 사영 변환 평면 투영 해법."""

            @staticmethod
            def project(points: Any, homography_matrix: Any) -> Any:
                """3x3 사영 변환 행렬을 취해 2차원 좌표점 배열을 다른 평면 좌표계로 사영한다."""
                from cv2 import perspectiveTransform as cv2_perspectiveTransform
                from numpy import asarray as np_asarray, empty as np_empty, float64 as np_float64

                matrix = np_asarray(homography_matrix, dtype=np_float64)
                if matrix.shape != (3, 3): raise Tool.Missing(f"사영 변환 행렬 형상이 (3, 3)이 아니라 {matrix.shape}이다")
                if len(points) == 0: return np_empty((0, 2), dtype=np_float64)
                transformed = cv2_perspectiveTransform(np_asarray(points, dtype=np_float64).reshape(-1, 1, 2), matrix)
                return transformed.reshape(-1, 2)

        class MinAreaRect:
            """2차원 점군 최소 외접 직사각형 적합 해법."""

            @staticmethod
            def fit(points_world_mm: Any, target_length_mm: float, target_width_mm: float) -> tuple[tuple[float, float], float, float]:
                """점군에서 규격 치수 오차가 최소화되는 중심 좌표, 회전각, 형상 잔차를 산출한다."""
                from cv2 import minAreaRect as cv2_minAreaRect
                from numpy import float32 as np_float32

                if len(points_world_mm) < 3: raise Tool.Missing("직사각형 피팅을 위한 점군이 3개 미만으로 부족하다")
                (center_x, center_y), (rectangle_width, rectangle_height), angle = cv2_minAreaRect(points_world_mm.astype(np_float32).reshape(-1, 1, 2))
                if rectangle_width < rectangle_height: rectangle_width, rectangle_height = rectangle_height, rectangle_width; angle = (angle + 90.0) % 180.0
                resid_mm = float(math.hypot(rectangle_width - target_length_mm, rectangle_height - target_width_mm))
                return (float(center_x), float(center_y)), float(angle), resid_mm

    @staticmethod
    def outside(target_value: float, span: tuple[float, float]) -> float:
        """값이 범위 밖으로 얼마나 벗어났나. 안에 들면 0 이다.

        소속을 묻는 데도 쓰고(0 인가) 여럿 중 가까운 것을 고르는 데도 쓴다(가장 작은 것).
        두 물음이 같은 양으로 답해지므로 경계에 닿은 값과 멀리 떨어진 값이 같은 잣대로 다뤄진다 — 참 · 거짓만 내면 "얼마나 벗어났나" 를 잃어 고를 수가 없다.
        """
        return max(span[0] - target_value, target_value - span[1], 0.0)

    @staticmethod
    def wrap180(deg: float) -> float:
        """각도를 (-180, 180] 으로 접는다. 누적 회전이 지령 범위를 넘지 않게 하고, 두 방위의 차를 가장 짧은 쪽으로 잰다."""
        return (deg + 180.0) % 360.0 - 180.0

    @staticmethod
    def odd(size_px: float) -> int:
        """커널 크기로 쓸 홀수. 중심 화소가 있어야 구조요소가 대칭이 된다. 크기는 양의 물리량(축척 · mm · 비율)의 곱이라 결과는 1 이상이다."""
        return round(size_px) | 1

    @staticmethod
    def closed_edges(points: Sequence[tuple[float, float]]) -> Iterator[tuple]:
        """닫힌 다각형의 변을 차례로 낸다. 마지막 점은 첫 점으로 잇는다."""
        return zip(points, points[1:] + points[:1])


# =========================================================================
# 2. 중간 설정 계층
# =========================================================================


class Config:
    """계통별 설정 클래스 묶음."""

    class Document:
        """JSON 을 읽고 쓰는 방식 하나 — 파일 하나를 읽은 그대로 내고, 받은 그대로 쓴다.

        어느 파일을 읽고 어디에 쓰는지는 부르는 쪽이 쥔다.
        """

        #: 영속화 JSON 이 놓인 디렉토리. 이 파일 위치 기준이다.
        CONFIG_DIR = Path(__file__).resolve().parent

        #: 영속화 자산 파일 확장자.
        SUFFIX = ".json"

        #: 이 글자로 시작하는 키는 주석이다. 읽는 쪽이 건너뛴다(`entries` · `Tool.JsonNode`)
        COMMENT_PREFIX = Tool.JsonNode.COMMENT_PREFIX

        #: 쓰는 동안 내용을 담는 옆 파일의 꼬리. 다 쓰면 이름을 바꿔 원래 파일 자리에 끼운다(`write`)
        PART_SUFFIX = ".part"

        @staticmethod
        def entries(mapping: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
            """이름으로 묶인 항목들. 주석 키를 뺀다. 키가 곧 이름인 구획을 돌 때 `dict.items()` 대신 쓴다."""
            return tuple((name, body) for name, body in mapping.items() if not name.startswith(Config.Document.COMMENT_PREFIX))

        @staticmethod
        def setting_path(stem: str) -> Path:
            """정본 디렉토리에 계통 이름으로 놓인 설정 파일 하나의 자리 — 파일 안의 최상위 키도 그 이름이다."""
            return Config.Document.CONFIG_DIR / f"{stem}{Config.Document.SUFFIX}"

        @staticmethod
        def read(path: Path) -> Any:
            """JSON 파일 하나를 읽은 그대로 낸다."""
            with path.open(encoding="utf-8") as file_pointer:
                return json.load(file_pointer)

        @staticmethod
        def write(path: Path, doc: Any) -> None:
            """JSON 파일 하나를 받은 그대로 쓴다.

            두 칸 들여쓰기에 한글은 글자 그대로 적고 끝에 줄바꿈을 둔다.
            옆 파일에 다 쓴 뒤 이름을 바꿔 끼운다 — 읽는 쪽은 언제 읽어도 다 쓴 파일만 본다. 쓰다 실패하면 원래 파일은 그대로다.
            """
            part = path.with_name(path.name + Config.Document.PART_SUFFIX)
            with part.open("w", encoding="utf-8") as file_pointer:
                json.dump(doc, file_pointer, ensure_ascii=False, indent=2)
                file_pointer.write("\n")
            part.replace(path)

    # ------------------------------------------------------------------
    # 2-1. 자재 물리 규격
    # ------------------------------------------------------------------

    class Product(Tool.JsonNode):
        r"""블록 3종의 불변 규격과 거기서 나오는 기하 사실 — `product.json` 을 읽은 그대로 들고, 부르는 이름은 그 키 경로다(`product.dimensions.width__mm`).

        3종은 단축과 높이가 공통이고 길이만 다르다.
        윗면에서 보면 짧은 변이 언제나 단축 폭(`dimensions.width__mm`)이므로 종횡비 하나로 규격이 갈린다.
        치수(`dimensions`)의 `width__mm` 은 3종 공통 단축 폭이다 — 규격 판별의 기본 척도이자 흡착 패드 좌우 마진의 경계다.
        `height__mm` 은 3종 공통 높이다 — 상면이 이루는 수평 평면의 절대 고도이며 H35 평면의 Z 다.
        `fillet_r__mm` 은 12개 모서리 필렛의 공칭 반경이다 — 상면 음영 띠와 밀착 노치의 근원이다.
        공차(`tolerances`)의 `profile_tol__mm` 은 도면 윤곽도 공차다 — 이상 직사각형 대비 허용 편측 편차 상한이다.
        """

        #: 영속화 자산 파일 이름(확장자 제외).
        DOCUMENT_STEM = "product"

        # -------------------------------------------------------- 적재

        @classmethod
        def load(cls) -> "Config.Product":
            """정본 디렉토리의 `product.json` 을 읽는다. 규격마다와 대표 단품의 필렛 반경이 단축의 절반을 넘지 않는지 여기서 본다(`Block.fillet_r_mm`)."""
            product = cls(Config.Document.read(Config.Document.setting_path(cls.DOCUMENT_STEM))[cls.DOCUMENT_STEM])
            for block in product.blocks + (product.nominal_block,): block.fillet_r_mm
            return product

        # -------------------------------------------------- 하위 규격

        class Block(Tool.JsonNode):
            """규격 한 종(`blocks` 의 항목) — 공칭 장축 길이(`length__mm`)와 그 규격에서 실측된 필렛 반경(`fillet_r__mm`)을 들고, 거기서 나오는 기하 사실을 낸다.

            필렛 반경은 공통 공칭값을 물려받되, 규격마다 가공 편차가 실측되면 그 값으로 선다(`fillet_r_mm`).
            규격이 정해지기 전 단계는 `Product.nominal_block` 을 쓴다.
            """

            dimensions: "Tool.JsonNode"  # 3종 공통 치수(`product.dimensions`) — 단축 폭과 공칭 필렛 반경을 여기서 받는다
            nominal: bool  # 넣어 주면 대표 단품이다(`Product.nominal_block`) — 필렛 반경을 실측 대신 공칭으로 센다

            @cached_property
            def fillet_r_mm(self) -> float:
                """이 규격의 필렛 반경 — 실측(`fillet_r__mm`)이 비었거나 대표 단품이면 공칭 반경(`dimensions.fillet_r__mm`)이다. 단축의 절반을 넘으면 거부한다."""
                fillet_r_mm = self.dimensions.fillet_r__mm if getattr(self, "nominal", False) or self.fillet_r__mm is None else self.fillet_r__mm
                if not fillet_r_mm <= self.dimensions.width__mm / 2.0: raise ValueError(f"{self.length__mm} mm 규격의 필렛 반경 {fillet_r_mm} mm 가 단축의 절반 {self.dimensions.width__mm / 2.0} mm 를 넘는다")
                return fillet_r_mm

            @cached_property
            def aspect_ratio_nominal(self) -> float:
                """공칭 종횡비. 축척을 몰라도 성립하는 무차원 불변량이다."""
                return self.length__mm / self.dimensions.width__mm

            @cached_property
            def symmetry_deg(self) -> float:
                r"""이 규격 윗면의 점대칭 주기.

                윗면이 정사각이면 $90^\circ$ 마다, 아니면 $180^\circ$ 마다 같은 자세가 된다.
                필렛은 네 모서리에 같게 들어가므로 대칭을 깨지 않는다.
                손목 지령각을 접을 때 이 주기 안의 후보를 모두 본다.
                """
                return 90.0 if self.length__mm == self.dimensions.width__mm else 180.0

            @cached_property
            def area_mm2(self) -> float:
                """외접 사각형 상면 면적."""
                return self.dimensions.width__mm * self.length__mm

            @cached_property
            def notch_depth_mm(self) -> float:
                r"""두 블록이 맞닿을 때 생기는 접합부 틈새의 이론 깊이.

                상면 평탄부에서 시작하는 반경 $r$ 의 두 원호 모서리가 맞닿는 접점 바닥까지의 깊이는 필렛 반경 $r$ 과 일치한다.
                밀착 접합부를 찾을 때 오목을 노치로 인정하는 깊이의 물리적 기준이 된다.
                """
                return self.fillet_r_mm

            @cached_property
            def fillet_arc_length_mm(self) -> float:
                r"""모서리 원호 단면의 호 길이. $90^\circ$ 원호이므로 $\frac{\pi}{2}\,r$ 이다."""
                return (math.pi / 2.0) * self.fillet_r_mm

            @cached_property
            def contact_min_mm(self) -> float:
                r"""대향 필렛 틈새 쌍이 물리적 접촉면으로 성립하는 최소 길이. $2r$.

                맞닿은 두 블록이 각자 모서리 필렛을 맞대어 접합부 틈새를 이룬다.
                양측 필렛 반경의 합인 $2r$ 이상이어야 평탄부 면접촉 구간이 존재한다.
                """
                return 2.0 * self.fillet_r_mm

            @cached_property
            def fillet_area_loss_mm2(self) -> float:
                r"""상면 네 모서리에서 필렛으로 잘려 나간 면적 합. $(4 - \pi)r^2$."""
                return (4.0 - math.pi) * (self.fillet_r_mm**2)

            @cached_property
            def rectangularity_ideal(self) -> float:
                r"""필렛만 반영한 이론 직사각형 충실도. 외접 사각형 대비 상면 면적비.

                $1 - (4 - \pi)r^2 / (W \cdot L)$. 값의 범위는 $[\pi/4, 1]$ 이다. 하한 $\pi/4 \approx 0.7854$ 는 적재 시점에 검사하는 기하 한계 $r \le W/2$ 에서 정사각 단품이 갖는 내접원 면적비다.
                """
                return 1.0 - self.fillet_area_loss_mm2 / self.area_mm2

        class Span(NamedTuple):
            """길이 구간."""

            min_mm: float
            max_mm: float

        # ----------------------------------------------------- 규격 조회

        @cached_property
        def blocks(self) -> tuple["Config.Product.Block", ...]:
            """규격 3종(`blocks`) — 3종 공통 치수를 넣어 준다."""
            return tuple(self.Block(entry, dimensions=self.dimensions) for entry in self.doc["blocks"])

        @cached_property
        def lengths_mm(self) -> tuple[float, ...]:
            """공칭 길이 집합."""
            return tuple(block.length__mm for block in self.blocks)

        def block(self, length_mm: float) -> "Config.Product.Block":
            """공칭 길이로 규격 한 종을 찾는다. 없는 규격은 기동을 거부한다."""
            for block in self.blocks:
                if block.length__mm == length_mm:
                    return block
            raise Tool.Missing(
                f"{self.DOCUMENT_STEM}.blocks 에 공칭 길이 {length_mm} mm 없음"
            )

        # --------------------------------------------------- 장축 극치

        @cached_property
        def length_min_mm(self) -> float:
            """가장 짧은 규격. 군집 면적 하한과 이론 직사각형 충실도의 기준 단품이다."""
            return min(self.lengths_mm)

        @cached_property
        def length_max_mm(self) -> float:
            """가장 긴 규격. 단일 블록 면적 상한과 배경 추정 커널의 기준이다."""
            return max(self.lengths_mm)

        @cached_property
        def aspect_ratios_nominal(self) -> tuple[float, ...]:
            """규격별 공칭 종횡비. 축척을 몰라도 성립하는 무차원 불변량이다."""
            return tuple(block.aspect_ratio_nominal for block in self.blocks)

        def block_by_aspect(self, aspect_ratio: float) -> "Config.Product.Block":
            """종횡비가 가장 가까운 규격. 축척도 사영 모델도 안 쓰므로, 사람이 찍은 라벨의 규격이 그 라벨로 풀 H35 에 기대지 않는다."""
            return min(self.blocks, key=lambda block: abs(block.aspect_ratio_nominal - aspect_ratio))

        @cached_property
        def block_area_mean_mm2(self) -> float:
            """규격 3종의 평균 상면 면적. 군집을 몇 덩이로 볼지 가늠하는 자다."""
            return statistics.fmean(block.area_mm2 for block in self.blocks)

        # --------------------------------------------- 필렛 기하 유도

        @cached_property
        def nominal_block(self) -> "Config.Product.Block":
            """규격이 정해지기 전 단계가 쓰는 대표 단품.

            필렛은 공통 공칭 반경으로, 면적 결손 비율은 가장 불리한 최소 규격 길이로 센다 — product.json 의 가장 짧은 규격 항목을 그대로 들고 필렛만 공칭으로 센다(`Block.nominal`).
            """
            shortest = min(self.blocks, key=lambda block: block.length__mm)
            return self.Block(shortest.doc, dimensions=self.dimensions, nominal=True)

        @cached_property
        def contact_span(self) -> "Config.Product.Span":
            """대향 접합선이 물리적으로 접촉일 수 있는 길이 구간.

            하한은 두 공칭 필렛이 만나는 최소 길이, 상한은 가장 긴 규격이다.
            """
            return self.Span(min_mm=self.nominal_block.contact_min_mm, max_mm=self.length_max_mm)

        @cached_property
        def fillet_r_max_mm(self) -> float:
            """규격 3종 중 가장 큰 필렛 반경."""
            return max(block.fillet_r_mm for block in self.blocks)

        @cached_property
        def gap_max_mm(self) -> float:
            r"""밀착 블록 접합부에서 발생하는 틈새의 물리 최대 폭. 양측 필렛 반경 합인 2 * r_max 다."""
            return 2.0 * self.fillet_r_max_mm


    # ------------------------------------------------------------------
    # 2-2. 광학 센서
    # ------------------------------------------------------------------

    class Camera(Tool.JsonNode):
        """광학 센서 하드웨어 규격(레지스터 주입값 · 역할별 장치 특정)과 노출 비용 함수 — `camera.json` 을 읽은 그대로 들고, 부르는 이름은 그 키 경로다(`camera.request_wait__s`).

        `request_wait__s` 는 카메라 워커가 요청을 한 번 기다리는 길이다 — 기다림이 끝나면 열린 카메라에서 한 장을 긁는다.
        `frame_poll__s` 는 판정 루프가 새 장을 기다리는 간격이다 — 카메라의 장 간격(30 fps 에서 33 ms)보다 짧으면 된다.
        `flush_frames` 는 로봇이 선 뒤 새 장을 받기 전에 버리는 장 수다 — 카메라 링버퍼에 남은 장이다.
        `property_ids` 는 OpenCV 로 읽고 쓰는 UVC 레지스터 이름 → 백엔드 레지스터 번호다.
        """

        #: 영속화 자산 파일 이름(확장자 제외).
        DOCUMENT_STEM = "camera"

        # -------------------------------------------------------- 적재

        @classmethod
        def load(cls) -> "Config.Camera":
            """정본 디렉토리의 `camera.json` 을 읽는다."""
            return cls(Config.Document.read(Config.Document.setting_path(cls.DOCUMENT_STEM))[cls.DOCUMENT_STEM])

        # -------------------------------------------------- 하위 규격

        class Role(Tool.JsonNode):
            """역할별 장치 특정 및 취득 규격(`roles` 의 항목).

            물리 인덱스는 재연결마다 뒤바뀌므로 역할로 요청하고 USB 식별자로 찾는다.
            `backend` 는 캡처 백엔드다 — UVC 레지스터 직접 쓰기가 가능한 규격이어야 한다.
            `warmup_frames` 는 셔터 개방 직후 폐기할 프레임 수다 — 센서 게인 안정화 대기다.
            연속 촬영 규격(`burst_capture`)은 블록 검출 역할만 가진다.
            """

            class BurstCapture(Tool.JsonNode):
                """연속 촬영 스케줄 규격 — 버스트 한 회의 총 지속 시간(`duration__s`) · 프레임 간 최소 간격(`interval__s`) · 한 버스트에서 남길 최대 매수(`max_frames`)다."""

                def should_capture(self, elapsed_s: float, since_last_s: float, frame_count: int) -> bool:
                    """지금 한 장 찍을 때인가. 대기하지 않고 경과 시간만 보고 판정하므로 제어 루프를 막지 않는다."""
                    return (
                        elapsed_s < self.duration__s
                        and since_last_s >= self.interval__s
                        and frame_count <= self.max_frames
                    )

            @cached_property
            def device_ids(self) -> tuple["Connect.Device.Usb.Entry", ...]:
                """이 역할에 쓸 장치 후보(`device_ids`) — 앞선 것이 우선이다. 식별자 글자를 풀어 둔다."""
                return Connect.Device.Usb.entries(self.doc["device_ids"])

        class SettingsApply(Tool.JsonNode):
            """카메라 설정을 장치에 써 넣는 규격.

            `auto_flags` 는 자동 제어 속성이다 — 끄는 것은 수동 값보다 먼저, 켜는 것은 나중에 쓴다.
            `auto_on_min` 을 넘으면 자동이 켜진 것이다 — DirectShow 노출 0.25/0.75 와 그 밖의 0/1 을 함께 가른다.
            `settle_frames` 는 속성 하나를 쓴 뒤 버리는 프레임 수다 — 레거시 `apply_camera_settings` 의 값이다.
            """

        class DirectShow(Tool.JsonNode):
            """OpenCV 가 감싸지 않은 DirectShow 속성 손잡이(`Connect.Device.Usb.Controls`)의 대응.

            `controls` 는 설정 이름 → (인터페이스, 속성 번호)다 — 범위와 지원 여부를 여기로 묻는다.
            `auto_flags` 는 자동 제어 설정 이름 → 그 플래그가 붙은 속성이다 — 값은 켜짐 1 · 꺼짐 0 이다.
            """

        class RealSense(Tool.JsonNode):
            """DirectShow 에 없는 RealSense 옵션을 SDK 로 읽고 쓰는 규격. 설정 이름은 `realsense_` 로 가른다.

            `sensor` 는 SDK 센서 이름이다 — 컬러 영상을 내는 쪽이다.
            `options` 는 설정 이름 → `pyrealsense2.option` 의 속성 이름이다.
            """

            @cached_property
            def device_ids(self) -> tuple["Connect.Device.Usb.Entry", ...]:
                """RealSense 제품(`device_ids`) — 연 카메라가 여기 있으면 SDK 로 보충한다. 식별자 글자를 풀어 둔다."""
                return Connect.Device.Usb.entries(self.doc["device_ids"])

        class TuningTarget(Tool.JsonNode):
            """노출 탐색의 목표와 비용 함수 계수.

            `monitored_properties` 는 스윕 중 되읽어 기록할 레지스터 목록이다.
            `target_brightness_min` · `target_brightness_max` 는 전경 목표 평균 밝기의 하한 · 상한이다.
            `clip_threshold_high` 이상을 포화 화소로, `clip_threshold_low` 이하를 암전 화소로 센다.
            `saturation_penalty_base` 는 포화 초과 시 부과하는 기저 비용이고, `saturation_penalty_weight` 는 포화율에 곱하는 추가 비용 가중치다.
            `max_saturation_ratio__percent` 는 허용 포화 화소 비율 상한이다.
            `min_separation_score` 는 전경-배경 평균 계조 차의 하한이다.
            `convergence_tol` 미만의 비용이면 스윕을 조기 종료한다.
            `tuning_priority` 는 1차원 스윕 순서다 — 게인 선제 상향을 피한다.
            """

            @cached_property
            def target_brightness_mid(self) -> float:
                """목표 밝기 대역의 중앙. 비용 함수가 재는 기준점이다."""
                return (self.target_brightness_min + self.target_brightness_max) / 2.0

            def is_separated(self, mean_foreground: float, mean_background: float) -> bool:
                """전경과 배경이 이진화로 갈릴 만큼 벌어져 있는가."""
                return (mean_foreground - mean_background) >= self.min_separation_score

            def is_saturated(self, clip_percent: float) -> bool:
                """포화 화소 비율이 허용 상한을 넘었는가.

                하드웨어 단에서 클리핑된 화소는 후처리로 되살릴 수 없고, 상면 반사광이 포화하면 외곽 에지가 부풀어 치수와 각도 오차를 키운다.
                """
                return clip_percent > self.max_saturation_ratio__percent

            def exposure_cost(self, mean_foreground: float, clip_percent: float) -> float:
                """노출 품질 비용. 낮을수록 좋다.

                포화가 상한을 넘으면 밝기가 목표에 가깝더라도 포화 해가 선택되지 않도록 큰 비용을 준다.
                """
                if self.is_saturated(clip_percent):
                    return self.saturation_penalty_base + self.saturation_penalty_weight * clip_percent
                return abs(mean_foreground - self.target_brightness_mid)

            def is_converged(self, cost: float) -> bool:
                """스윕을 더 돌 필요가 없을 만큼 좋은가."""
                return cost < self.convergence_tol

        @dataclass(frozen=True)
        class ControlRange:
            """레지스터 하나의 실측 유효 범위.

            펌웨어에 극단값을 넣고 되읽어 잰 값이다.
            """

            min: int  # 실측 하한. 음수일 수 있다
            max: int  # 실측 상한
            step: int  # 유효 증분
            default: int  # 드라이버 초기값
            writable: bool  # 쓰기가 실제로 먹히는가

            @cached_property
            def offset(self) -> int:
                r"""음수 하한을 0 으로 끌어올리는 이동량. $\max(0, -L_{lo})$.

                GUI 트랙바는 음수를 받지 못하는데 UVC 노출 레지스터는 음수 규격을 쓴다.
                둘 사이를 잇기 위한 평행 이동이다.
                """
                return max(0, -self.min)

            @cached_property
            def span(self) -> int:
                """이동 후 눈금의 전체 폭."""
                return self.max + self.offset

            def to_slider(self, value: int) -> int:
                """하드웨어 눈금을 비음수 트랙바 위치로 옮긴다."""
                return min(max(value + self.offset, 0), self.span)

            def to_hardware(self, position: int) -> int:
                """트랙바 위치를 하드웨어 눈금으로 되돌린다."""
                return position - self.offset

        # ---------------------------------------------------- 역할 조회

        def role(self, name: str) -> "Config.Camera.Role":
            """역할 이름으로 취득 규격을 찾는다. 없는 역할은 기동을 거부한다."""
            if name not in self.roles: raise Tool.Missing(f"{self.DOCUMENT_STEM}.roles.{name} 미정의 — 역할 배정 확인")
            return self.roles[name]




    # ------------------------------------------------------------------
    # 2-3. 공간 사상
    # ------------------------------------------------------------------

    class VisionAlgorithm(Tool.JsonNode):
        r"""영상 관측 평면을 물리 공간과 기구 기준계로 보내는 사상 모델과, 그 위에서 도는 영상 처리 단계들의 규격.

        `vision_algorithm.json` 을 읽은 그대로 들고, 부르는 이름은 그 키 경로다(`vision_algorithm.homography_fit.soft_l1_scale__mm`).
        자재 규격을 자로 삼으므로 `Config.Product` 한 벌을 넣어 받는다(`product`).
        축척(`ppm`)은 프레임마다 갱신되는 계측값이라, 축척에 기대는 유도식은 호출 시점에 축척을 받는다.
        """

        #: 영속화 자산 파일 이름(확장자 제외).
        DOCUMENT_STEM = "vision_algorithm"

        # -------------------------------------------- 보조 연산

        #: 부동소수 영 판정 한계. Tool.EPS의 상위 정본을 참조한다.
        EPS = Tool.EPS

        # -------------------------------------------------------- 적재

        @classmethod
        def load(cls, product: "Config.Product | None" = None) -> "Config.VisionAlgorithm":
            """정본 디렉토리의 `vision_algorithm.json` 을 읽는다. 자재 규격을 안 주면 정본에서 읽는다."""
            return cls(Config.Document.read(Config.Document.setting_path(cls.DOCUMENT_STEM))[cls.DOCUMENT_STEM], product=product or Config.Product.load())

        @staticmethod
        def _inverse(matrix: tuple[tuple[float, ...], ...]) -> tuple[tuple[float, ...], ...]:
            """3x3 행렬의 역행렬. 수반행렬을 행렬식으로 나눈다."""
            (a, b, c), (d, e, f), (g, h, i) = matrix
            cof = (
                (e * i - f * h, c * h - b * i, b * f - c * e),
                (f * g - d * i, a * i - c * g, c * d - a * f),
                (d * h - e * g, b * g - a * h, a * e - b * d),
            )
            det = a * cof[0][0] + b * cof[1][0] + c * cof[2][0]
            if abs(det) < Config.VisionAlgorithm.EPS: raise ValueError("사영 행렬이 특이하다 — 역변환이 성립하지 않는다")
            return tuple(tuple(cofactor / det for cofactor in row) for row in cof)

        @staticmethod
        def _delta(p: tuple[float, float], q: tuple[float, float]) -> float:
            """두 점 사이 유클리드 거리."""
            return math.dist(p, q)

        # -------------------------------------------------- 하위 규격

        class MotionDetect(Tool.JsonNode):
            """움직임 판정 규격. 연속 두 프레임의 차분으로 지금 만지는 중인지 본다.

            `noise_sigma_factor` :: 프레임 차분 잡음의 몇 배를 화소 변화로 볼지
            `perimeter_jitter_factor` :: 덩어리 둘레 합의 몇 배를 장면 움직임으로 볼지
            `still_frame_count` :: 이만큼 연속으로 조용하면 멎은 것으로 본다
            """

            def changed_level_min(self, frame_difference_sigma_gray: float | None) -> float:
                """화소 하나가 변했다고 볼 계조 차이."""
                if frame_difference_sigma_gray is None: raise Tool.Missing("프레임 차분 잡음 σ 가 없다 — 판정이 차분 영상에서 구해 넘긴다")
                return self.noise_sigma_factor * frame_difference_sigma_gray

            def changed_pixels_min(self, perimeter_px: float) -> float:
                """장면이 움직였다고 볼 변한 화소 수. 잡음은 경계가 한 화소 폭으로 흔들리며 생긴다."""
                return self.perimeter_jitter_factor * perimeter_px

        class WorkArea(Tool.JsonNode):
            """작업영역 추출 규격. 다각형은 회차 값이라 받아서 쓴다(`Config.Dataset.EraValues.WorkArea`).

            `mask_dilation_margin__mm` :: 마스크 팽창 여유. 물리 길이로 준다
            `min_seed_area_ratio` :: 최소 단품 면적 대비 씨앗 인정 하한 비율
            `sever_ratio` :: 다리 절단 커널을 블록 단축 화소폭의 몇 배로 잡을지
            `ring_ratio` :: 재구성 고리 커널 배율
            `hull_area_ratio_min` :: 볼록 껍질이 프레임에서 차지할 면적 하한
            `hull_area_ratio_max` :: 같은 상한. 벗어나면 껍질이 붕괴한 것이다
            `solidity_min` :: 껍질 대비 성분 면적의 하한
            """

            def seed_area_min_px2(self, ppm: float, *, width_mm: float, length_min_mm: float) -> float:
                r"""씨앗으로 인정할 최소 화소 면적. $W \cdot L_{\min} \cdot \text{PPM}^2 \cdot R_{seed}$.

                최소 단품의 물리 면적을 화소로 환산한 뒤 비율을 먹인다.
                """
                return width_mm * length_min_mm * ppm * ppm * self.min_seed_area_ratio

            @staticmethod
            def margin_mm(*, width_mm: float) -> float:
                """다각형 바깥으로 남길 여백이다. 경계에 걸친 블록이 통째로 들어오도록 블록 단축만큼 남긴다.

                잘라 보기(`crop_margin_px`)와 정면 복원(`Config.VisionAlgorithm.rectify_matrix`)이 같은 뜻의 여백을 쓰므로 한 이름에 둔다.
                """
                return width_mm

            @staticmethod
            def crop_margin_px(ppm: float, *, width_mm: float) -> int:
                """크롭 시 다각형 바깥으로 남길 여백을 화소로."""
                return math.ceil(Config.VisionAlgorithm.WorkArea.margin_mm(width_mm=width_mm) * ppm)

            def sever_kernel_px(self, width_px: float) -> int:
                """다리 절단 커널 크기."""
                return Tool.odd(width_px * self.sever_ratio)

            def ring_kernel_px(self, width_px: float) -> int:
                """재구성 고리 커널 크기."""
                return Tool.odd(width_px * self.ring_ratio)

            def encloses(self, work_area: "Config.Dataset.EraValues.WorkArea", points_px: Sequence[tuple[float, float]]) -> bool:
                """점이 모두 작업영역 안인가(경계 포함). 원본 화소다.

                계산은 작업영역으로 잘라 하므로 윗면이 경계에 걸친 블록은 잘린 마스크로 재여 중심이 안쪽으로 밀린다. 그 관측을 가려낼 때 쓴다.
                """
                from cv2 import pointPolygonTest as cv2_pointPolygonTest
                from numpy import array as np_array, float32 as np_float32

                contour = np_array(work_area.polygon__px, np_float32)
                return all(cv2_pointPolygonTest(contour, (float(u), float(v)), False) >= 0 for u, v in points_px)

            def is_hull_sane(self, hull_area_px2: float, frame_area_px2: float) -> bool:
                """볼록 껍질 면적이 프레임 대비 성립 범위 안에 있는가.

                너무 작으면 잡음을 잡은 것이고, 너무 크면 배경까지 삼킨 것이다.
                """
                return self.hull_area_ratio_min <= (hull_area_px2 / frame_area_px2) <= self.hull_area_ratio_max

            def is_solid(self, component_area_px2: float, hull_area_px2: float) -> bool:
                """성분이 껍질을 채우는 정도가 하한을 넘는가."""
                return (component_area_px2 / hull_area_px2) >= self.solidity_min

        class Homography(Tool.JsonNode):
            r"""운전 중에 쓰는 상면 사영 모델의 계산.

            $H_{35}$ 는 화소를 $Z = 35\text{ mm}$ 평면의 mm 좌표로 보낸다. 행렬 · 세로 소실점은 회차 값이라 받아서 쓴다(`Config.Dataset.EraValues.Homography`).
            이 모델을 라벨에서 푸는 절차의 규격은 `HomographyFit` 에 있다.
            `tilt_displacement_limit__deg` :: 카메라 브라켓 허용 경사 변위
            `perspective_rectangularity_factor` :: 원근 투영이 관측 직사각형 충실도에 남기는 비율
            `edge_position_sigma__px` :: 영상에서 잡은 모서리 끝점의 위치 오차. 튜닝 — 근거 없음
            `vanishing_convergence_multiple` :: 모이는 각이 선분 방향 흔들림의 몇 배면 소실점이 보인다고 볼지. 튜닝 — 근거 없음
            """

            #: 화면에 투영된 띠가 표본에 잡히는 최소 폭. 띠가 두 화소에 걸려야 잡힌다 — 회색 측면 띠 `ppm ≥ 2 / (H·sin τ)` · 필렛 전이 띠 `ppm ≥ 2 / r` 과 같은 뜻이다.
            BAND_PX_MIN = 2.0

            @staticmethod
            def _require_matrix(h35: "Config.Dataset.EraValues.Homography") -> tuple[tuple[float, float, float], ...]:
                if h35.matrix is None:
                    raise Tool.Missing("회차 문서 homography.matrix 미기입 — 라벨에서 풀어 입력한다")
                return h35.matrix

            @staticmethod
            def to_world(h35: "Config.Dataset.EraValues.Homography", u_px: float, v_px: float) -> tuple[float, float]:
                """화소 좌표를 상면 mm 좌표로 보낸다."""
                return Tool.Geometry.project(Config.VisionAlgorithm.Homography._require_matrix(h35), u_px, v_px)

            def denominator_at(self, h35: "Config.Dataset.EraValues.Homography", u_px: float, v_px: float) -> float:
                """화소 `(u_px, v_px)` 의 사영 분모.

                0 에 가까울수록 소실선에 가깝고, 상면 mm 좌표가 발산한다.
                부호가 뒤집힌 화소는 소실선 너머로 사상되어 수치가 유한해도 거짓이다.
                """
                return Tool.Geometry.projective_denominator(self._require_matrix(h35), u_px, v_px)

            @staticmethod
            def to_image(h35: "Config.Dataset.EraValues.Homography", x_mm: float, y_mm: float) -> tuple[float, float]:
                """상면 mm 좌표를 화소 좌표로 되돌린다."""
                return Tool.Geometry.project(h35.inv_matrix, x_mm, y_mm)

            @staticmethod
            def ppm_inplane_at(h35: "Config.Dataset.EraValues.Homography", u_px: float, v_px: float) -> float:
                r"""화소 `(u_px, v_px)` 자리의 면내 축척. 상면에서 $1\text{ mm}$ 이동이 몇 화소인가.

                사영 변환은 위치마다 배율이 다르다. 직교 두 방향의 $1\text{ mm}$ 변위를 화소로 재고 평균한다.
                """
                x_mm, y_mm = Config.VisionAlgorithm.Homography.to_world(h35, u_px, v_px)
                delta_x = Config.VisionAlgorithm._delta(Config.VisionAlgorithm.Homography.to_image(h35, x_mm + 1.0, y_mm), (u_px, v_px))
                delta_y = Config.VisionAlgorithm._delta(Config.VisionAlgorithm.Homography.to_image(h35, x_mm, y_mm + 1.0), (u_px, v_px))
                return (delta_x + delta_y) / 2.0

            def under_point_px(self, h35: "Config.Dataset.EraValues.Homography", u_px: float, v_px: float) -> tuple[float, float]:
                r"""윗면 화소를 그 바로 아래 밑면 화소로 내린다. 밑면 화소는 윗면 화소와 세로 소실점을 잇는 직선 위에 있다.

                높이 $Z$ 평면의 사영 행렬은 셋째 열만 선형으로 변하므로, 밑면 화소는 동차 좌표에서 소실점을 빼는 한 식으로 나온다.
                """
                if not h35.is_vanishing_solved:
                    raise Tool.Missing("회차 문서 homography.vertical_vanishing_point 미해결")
                row = self._require_matrix(h35)[2]
                vanishing_x, vanishing_y, vanishing_z = h35.vanishing_point
                scale_factor = u_px * row[0] + v_px * row[1] + row[2]
                denom = 1.0 - scale_factor * vanishing_z
                return ((u_px - scale_factor * vanishing_x) / denom, (v_px - scale_factor * vanishing_y) / denom)

            def is_under_between(self, h35: "Config.Dataset.EraValues.Homography", points_px: Sequence[tuple[float, float]]) -> bool:
                r"""모든 윗면 점에서 밑면 점이 윗면 점과 세로 소실점 사이에 놓이는가. 카메라가 블록 위에 있다는 물리 조건이다.

                밑면 점은 소실점에서 윗면 점까지 거리의 $1 / (1 - k w_z)$ 자리에 있다 — $k$ 는 H35 셋째 행과 윗면 화소의 곱, $w_z$ 는 소실점 동차 좌표의 셋째 수.
                그러므로 $k w_z < 0$ 이면 사이다. 무한원($w_z = 0$)은 사이가 아니다 — 세로 모서리가 화면에서 평행이면 카메라가 옆을 본다.
                """
                if not h35.is_vanishing_solved:
                    raise Tool.Missing("회차 문서 homography.vertical_vanishing_point 미해결")
                vanishing_z = h35.vanishing_point[2]
                return all(self.denominator_at(h35, u_px, v_px) * vanishing_z < 0.0 for u_px, v_px in points_px)

            def vanishing_point_fitted(self, h35: "Config.Dataset.EraValues.Homography", top_bottom_px: Sequence[tuple[tuple[float, float], tuple[float, float]]]) -> tuple[float, float, float]:
                r"""윗면 꼭짓점과 그 바로 아래 밑면 꼭짓점의 화소 쌍에서 세로 소실점을 푼다. 내부 파라미터 없이 선다.

                `under_point_px` 를 거꾸로 푼다 — 밑면 $\mathbf{b} \propto \mathbf{x} - k\,\mathbf{w}$, $\mathbf{w}$ 는 소실점의 동차 좌표, $k$ 는 H35 셋째 행과 윗면 화소 $\mathbf{x}$ 의 곱이다.
                쌍 하나가 $w_x - b_u w_z = (u - b_u)/k$ 와 $-w_y + b_v w_z = (b_v - v)/k$ 두 식을 주므로 쌍이 둘 이상이면 풀린다.
                $k$ 가 이 H35 에서 나오므로 푼 소실점의 동차 크기는 이 H35 의 배율에 매인다 — H35 를 다시 풀면 다시 푼다.
                윗면과 밑면이 영상에서 갈리는 쌍이어야 식이 선다.
                """
                row = self._require_matrix(h35)[2]
                design_rows, constants = [], []
                for (u_px, v_px), (bottom_u_px, bottom_v_px) in top_bottom_px:
                    scale_factor = u_px * row[0] + v_px * row[1] + row[2]
                    design_rows += [(1.0, 0.0, -bottom_u_px), (0.0, -1.0, bottom_v_px)]
                    constants += [(u_px - bottom_u_px) / scale_factor, (bottom_v_px - v_px) / scale_factor]
                return Tool.Fit.LeastSquares.solve(design_rows, constants)

            def vanishing_point_from_edge(self, h35: "Config.Dataset.EraValues.Homography", reference_px: tuple[float, float], edge_px: tuple[float, float], shrink: float) -> tuple[float, float, float]:
                r"""윗면 한 점에서 본 35 mm 세로 모서리로 세로 소실점을 세운다. 그 점에서 `under_point_px` 를 거꾸로 푼 것이다.

                `edge_px` 는 윗면 점 $c$ 에서 밑면 점까지의 화면 변위 $d$, `shrink` 는 밑면 점이 소실점까지 거리를 줄이는 몫 $\sigma$ 다 — 소실점은 $c + d / \sigma$.
                $0 < \sigma < 1$ 이면 밑면 점이 윗면 점과 소실점 사이에 놓인다(카메라가 블록 위). $\sigma \to 0$ 이면 소실점이 무한원으로 가고 동차 좌표는 그대로 이어진다.
                """
                (u_px, v_px), (edge_u_px, edge_v_px) = reference_px, edge_px
                kept = (1.0 - shrink) * self.denominator_at(h35, u_px, v_px)
                vanishing_z = -shrink / kept
                return (vanishing_z * u_px - edge_u_px / kept, vanishing_z * v_px - edge_v_px / kept, vanishing_z)

            @staticmethod
            def vanishing_point_of(matrix: tuple[tuple[float, float, float], ...], pinhole: "Tool.JsonNode", *, height_mm: float) -> tuple[float, float, float]:
                r"""내부 파라미터를 아는 카메라의 세로 소실점. H35 와 내부 파라미터로 닫힌 식이다.

                H35 의 역행렬 $G$ 는 윗면($Z = h$) 평면을 화면에 보내는 카메라 행렬의 세 열이다 :: $G = \mu K [r_1\ r_2\ h r_3 + t]$.
                $K^{-1}$ 로 앞 두 열을 풀면 크기가 $|\mu|$ 인 윗면의 두 축이 나오고, 세로축은 둘의 외적 방향 $r_3$ 이다.
                밑면($Z = 0$)은 윗면 열에서 $h K r_3$ 를 뺀 자리이므로 `under_point_px` 가 쓰는 동차 좌표는 $w = \mu h K r_3$ 다.
                $\mu$ 의 부호는 H35 셋째 행이 주점에서 갖는 부호다 — 화면 앞의 점은 깊이가 양이다.
                $r_3$ 의 부호는 위가 카메라 쪽이라는 물리 조건으로 고른다(주점으로 보는 광선과 반대쪽) — 그러면 밑면 점이 윗면 점과 소실점 사이에 놓인다.
                렌즈 왜곡은 두지 않는다(바늘구멍 카메라).
                """
                (focal_x, focal_y), (principal_x, principal_y) = pinhole.focal__px, pinhole.principal__px
                inverse = Config.VisionAlgorithm._inverse(matrix)
                to_camera = lambda column: ((inverse[0][column] - principal_x * inverse[2][column]) / focal_x,
                                            (inverse[1][column] - principal_y * inverse[2][column]) / focal_y,
                                            inverse[2][column])
                (ax, ay, az), (bx, by, bz) = to_camera(0), to_camera(1)
                depth_sign = math.copysign(1.0, Tool.Geometry.projective_denominator(matrix, principal_x, principal_y))
                scale = depth_sign * math.sqrt(math.hypot(ax, ay, az) * math.hypot(bx, by, bz))
                cross = (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)
                length = math.hypot(*cross) * (1.0 if cross[2] < 0.0 else -1.0)
                up_x, up_y, up_z = (component / length for component in cross)
                return (scale * height_mm * (focal_x * up_x + principal_x * up_z),
                        scale * height_mm * (focal_y * up_y + principal_y * up_z),
                        scale * height_mm * up_z)

            def upper_shape_px(self, h35: "Config.Dataset.EraValues.Homography", corners_mm: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
                """윗면사각형. 윗면 꼭짓점(mm)을 H35 로 영상에 옮긴다."""
                return tuple(self.to_image(h35, x_mm, y_mm) for x_mm, y_mm in corners_mm)

            def under_shape_px(self, h35: "Config.Dataset.EraValues.Homography", corners_mm: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
                """밑면사각형. 윗면 꼭짓점(mm)마다 그 바로 아래 밑면 꼭짓점을 영상에서 낸다(`under_point_px`)."""
                return tuple(self.under_point_px(h35, u_px, v_px) for u_px, v_px in self.upper_shape_px(h35, corners_mm))

            def shape_3d_px(self, h35: "Config.Dataset.EraValues.Homography", corners_mm: Sequence[tuple[float, float]]) -> tuple[tuple[tuple[float, float], ...], tuple[tuple[float, float], ...]]:
                """3D 형상. 윗면사각형과 밑면사각형이다 — 같은 차례의 꼭짓점끼리 세로 모서리로 이어진다. 블록 높이는 H35 평면의 고도다."""
                return self.upper_shape_px(h35, corners_mm), self.under_shape_px(h35, corners_mm)

            def ppm_vertical_at(self, h35: "Config.Dataset.EraValues.Homography", u_px: float, v_px: float, *, height_mm: float) -> float:
                """화소 `(u_px, v_px)` 자리의 수직 축척. 윗면에서 밑면까지 화소 거리를 블록 높이로 나눈다.

                사선 촬영계에서는 수직 방향과 상면 수평 방향의 화소 밀도가 크게 갈리므로 축척을 분리해서 쓴다.
                """
                under_u, under_v = self.under_point_px(h35, u_px, v_px)
                return Config.VisionAlgorithm._delta((under_u, under_v), (u_px, v_px)) / height_mm

            def is_side_resolvable(self, h35: "Config.Dataset.EraValues.Homography", u_px: float, v_px: float) -> bool:
                """화소 `(u_px, v_px)` 자리의 옆면이 영상에서 가려질 만큼 찍히는가. 윗면 점과 그 바로 아래 밑면 점이 화면에서 `BAND_PX_MIN` 이상 떨어져 있으면 그렇다.

                보이는 옆면의 폭은 블록 높이가 화면에 투영된 길이이고, 그 길이가 윗면 점과 밑면 점(`under_point_px`)의 화소 거리다.
                옆면을 증거로 세로 방향을 읽는 방식은 이 폭이 표본에 잡혀야 선다. 카메라 발 자리(`camera_center`)에서 멀수록 폭이 커지므로 자리마다 묻는다.
                """
                return Config.VisionAlgorithm._delta(self.under_point_px(h35, u_px, v_px), (u_px, v_px)) >= self.BAND_PX_MIN

            class CameraCenter(NamedTuple):
                """카메라 중심의 자리. 상면 mm 좌표계에 매트를 높이 0 으로 둔 것이다."""

                x_mm: float  # 카메라 바로 아래 발 자리, 상면 mm 좌표
                y_mm: float
                height_mm: float  # 매트에서 카메라 중심까지 수직 거리

            def camera_center(self, h35: "Config.Dataset.EraValues.Homography", *, height_mm: float) -> "Config.VisionAlgorithm.Homography.CameraCenter":
                r"""카메라 중심의 자리를 H35 와 세로 소실점에서 낸다. 내부 파라미터를 쓰지 않는다.

                매트 높이를 0 으로 둔 세계 점 $(X, Y, Z, 1)$ 을 화면에 보내는 사영 행렬은 $P = [\,g_1\ \ g_2\ \ w/h\ \ g_3 - w\,]$ 다 — $g_i$ 는 H35 역행렬의 열, $w$ 는 세로 소실점의 동차 좌표, $h$ 는 윗면 높이다.
                윗면 점 $(X, Y, h)$ 은 $G(X, Y, 1)$ 로 가고 밑면 점 $(X, Y, 0)$ 은 거기서 $w$ 를 뺀 자리로 가므로 `under_point_px` 와 같은 모형이다.
                카메라 중심은 $P$ 가 0 으로 보내는 점이다 — 성분 $j$ 는 $P$ 에서 열 $j$ 를 뺀 3x3 행렬식에 $(-1)^j$ 를 곱한 것이고, 넷째 성분으로 나눠 mm 로 만든다.
                """
                if not h35.is_vanishing_solved:
                    raise Tool.Missing("회차 문서 homography.vertical_vanishing_point 미해결")
                (g11, g12, g13), (g21, g22, g23), (g31, g32, g33) = h35.inv_matrix
                w_x, w_y, w_z = h35.vanishing_point
                p0, p1, p2, p3 = ((g11, g21, g31), (g12, g22, g32),
                                  (w_x / height_mm, w_y / height_mm, w_z / height_mm), (g13 - w_x, g23 - w_y, g33 - w_z))

                def determinant(a, b, c):
                    r"""세 열로 선 3x3 행렬식. 삼중곱 $a \cdot (b \times c)$ 다."""
                    return (a[0] * (b[1] * c[2] - b[2] * c[1]) + a[1] * (b[2] * c[0] - b[0] * c[2]) + a[2] * (b[0] * c[1] - b[1] * c[0]))

                c0, c1, c2, c3 = determinant(p1, p2, p3), -determinant(p0, p2, p3), determinant(p0, p1, p3), -determinant(p0, p1, p2)
                return Config.VisionAlgorithm.Homography.CameraCenter(c0 / c3, c1 / c3, c2 / c3)

            def _vertical_in_camera(self, h35: "Config.Dataset.EraValues.Homography", focal_px: tuple[float, float], principal_px: tuple[float, float]) -> tuple[float, float, float]:
                r"""세로 소실점을 카메라 좌표계의 방향으로 옮긴다. $K^{-1} w$, $w$ 는 소실점의 동차 좌표다.

                소실점은 화소 동차 좌표라 주점을 빼고 초점거리로 나눠야 방향이 된다.
                경사각과 방위각은 이 방향만 쓰므로 동차 좌표의 크기와 부호에 매이지 않는다.
                """
                if not h35.is_vanishing_solved:
                    raise Tool.Missing("회차 문서 homography.vertical_vanishing_point 미해결")
                vanishing_x, vanishing_y, vanishing_z = h35.vanishing_point
                (focal_x, focal_y), (principal_x, principal_y) = focal_px, principal_px
                return ((vanishing_x - principal_x * vanishing_z) / focal_x, (vanishing_y - principal_y * vanishing_z) / focal_y, vanishing_z)

            def tilt_deg(self, h35: "Config.Dataset.EraValues.Homography", *, focal_px: tuple[float, float], principal_px: tuple[float, float]) -> float:
                r"""카메라 광축과 수직선이 이루는 각이다. 곧장 내려다보면 0 이다.

                $\theta = \operatorname{atan2}(\sqrt{x^2 + y^2}, |z|)$, $(x, y, z) = K^{-1} w$.
                내부 파라미터(초점거리 · 주점, 화소)는 카메라가 정하는 값이라 부르는 쪽이 준다.
                """
                camera_x, camera_y, camera_z = self._vertical_in_camera(h35, focal_px, principal_px)
                return math.degrees(math.atan2(math.hypot(camera_x, camera_y), abs(camera_z)))

            def azimuth_deg(self, h35: "Config.Dataset.EraValues.Homography", *, focal_px: tuple[float, float], principal_px: tuple[float, float]) -> float:
                r"""카메라가 기운 방향이다. 영상에서 세로 소실점이 주점으로부터 놓인 방향을 카메라 좌표계(x 오른쪽 · y 아래)의 각으로 낸다.

                $\varphi = \operatorname{atan2}(y \operatorname{sgn} z, x \operatorname{sgn} z)$, $(x, y, z) = K^{-1} w$ — $\operatorname{sgn} z$ 를 곱해 동차 좌표의 부호에 매이지 않게 한다.
                경사각이 0 이면 기운 방향이 없으므로 값에 뜻이 없다.
                """
                camera_x, camera_y, camera_z = self._vertical_in_camera(h35, focal_px, principal_px)
                z_sign = -1.0 if camera_z < 0.0 else 1.0
                return math.degrees(math.atan2(camera_y * z_sign, camera_x * z_sign))

            def is_tilt_within(self, h35: "Config.Dataset.EraValues.Homography", baseline_deg: float, *, focal_px: tuple[float, float], principal_px: tuple[float, float]) -> bool:
                """경사각이 기준선에서 허용 변위 안에 있는가. 브라켓 흔들림 감시다."""
                return abs(self.tilt_deg(h35, focal_px=focal_px, principal_px=principal_px) - baseline_deg) <= self.tilt_displacement_limit__deg

            def is_vanishing_parallel(self, h35: "Config.Dataset.EraValues.Homography", reference_px: tuple[float, float], *, baseline_px: float, segment_px: float) -> bool:
                """세로 모서리들이 화소 조건에서 평행과 갈리지 않는가.

                소실점이 `reference_px` 에서 `Tool.Geometry.Segment.convergence_resolvable_distance_px` 보다 멀면 그렇다.
                마지막 성분이 0 이면 무한원이다. `baseline_px` 는 잰 모서리들이 퍼진 폭, `segment_px` 는 모서리가 찍힌 길이다.
                """
                if not h35.is_vanishing_solved:
                    raise Tool.Missing("회차 문서 homography.vertical_vanishing_point 미해결")
                vanishing_x, vanishing_y, vanishing_z = h35.vanishing_point
                limit_px = Tool.Geometry.Segment.convergence_resolvable_distance_px(
                    baseline_px, segment_px, self.edge_position_sigma__px, self.vanishing_convergence_multiple)
                if abs(vanishing_z) <= Config.VisionAlgorithm.EPS: return True
                return math.dist(reference_px, (vanishing_x / vanishing_z, vanishing_y / vanishing_z)) > limit_px

        class HomographyFit(Tool.JsonNode):
            """사영 모델을 라벨에서 푸는 캘리브레이션 절차의 규격. 운전 중에는 쓰지 않는다.

            `soft_l1_scale__mm` :: 로버스트 손실 전이 규모. 소수 불량 라벨이 해를 끌고 가지 못하게 한다
            `holdout_split_ratio` :: 검증 분할 비율
            `holdout_bias_ratio` :: 검증 오차가 학습 오차의 몇 배를 넘으면 편중으로 보는가
            `outlier_len_tol__mm` :: 공칭 길이에서 이만큼 벗어나면 적합 표본에서 제외
            """

            def is_holdout_biased(self, train_median: float, test_median: float) -> bool:
                """검증 오차가 학습 오차에 비해 치우쳐 있는가. 과적합 감시다."""
                return test_median > self.holdout_bias_ratio * train_median

            def is_length_outlier(self, measured_mm: float, nominal_mm: float) -> bool:
                """적합 표본에서 뺄 만큼 공칭 길이에서 벗어났는가."""
                return abs(measured_mm - nominal_mm) > self.outlier_len_tol__mm

            # --------------------------------------------------- 채점

            class LabelScore(NamedTuple):
                """라벨 하나의 채점. 답지는 라벨이다."""

                frame: str
                class_mm: float  # 라벨이 붙인 규격 길이
                clicked_px: tuple[tuple[float, float], ...]  # 사람이 찍은 꼭짓점
                fitted_px: tuple[tuple[float, float], ...]  # H35 아래에 놓은 규격 직사각형을 영상으로 되돌린 꼭짓점
                corner_px: tuple[float, ...]  # 꼭짓점마다 두 점의 거리
                tolerance_px: float  # 맞음 선. 윤곽도 공차를 그 자리 축척으로 바꾼 화소
                iou: float  # 두 사각형의 겹침 비율

                @property
                def is_correct(self) -> bool:
                    return max(self.corner_px) <= self.tolerance_px

            @staticmethod
            def placement(world_mm: Sequence[tuple[float, float]], class_mm: float, width_mm: float) -> tuple[tuple[tuple[float, float], ...], tuple[float, float, float]]:
                """라벨 하나에 놓을 규격 직사각형의 꼭짓점(자기 좌표, mm)과 출발 자세(중심 x · y mm, 방위 rad).

                라벨 꼭짓점 차례는 장축을 말하지 않는다.
                상면으로 옮긴 두 변의 mm 길이로 장축을 가르고, 상면에서의 감김 방향도 라벨을 따른다.
                꼭짓점 차례가 라벨과 같아 짝이 1 대 1 이다.
                """
                from cv2 import contourArea as cv2_contourArea
                from numpy import array as np_array, float32 as np_float32

                first_mm, second_mm = math.dist(world_mm[0], world_mm[1]), math.dist(world_mm[1], world_mm[2])
                along_first, along_second = (class_mm, width_mm) if first_mm >= second_mm else (width_mm, class_mm)
                local_mm = ((-along_first / 2, -along_second / 2), (along_first / 2, -along_second / 2),
                            (along_first / 2, along_second / 2), (-along_first / 2, along_second / 2))
                orientation = [cv2_contourArea(np_array(points, np_float32), oriented=True) for points in (world_mm, local_mm)]
                if (orientation[0] >= 0.0) != (orientation[1] >= 0.0):
                    local_mm = tuple((x_mm, -y_mm) for x_mm, y_mm in local_mm)
                start = (sum(x for x, _ in world_mm) / 4, sum(y for _, y in world_mm) / 4,
                         math.atan2(world_mm[1][1] - world_mm[0][1], world_mm[1][0] - world_mm[0][0]))
                return local_mm, start

            @staticmethod
            def placed(local_mm: Sequence[tuple[float, float]], pose: Sequence[float]) -> list[tuple[float, float]]:
                """자세(중심 · 방위)에 놓은 직사각형 꼭짓점의 상면 mm 좌표."""
                center_x, center_y, angle = pose
                cosine, sine = math.cos(angle), math.sin(angle)
                return [(center_x + cosine * x_mm - sine * y_mm, center_y + sine * x_mm + cosine * y_mm) for x_mm, y_mm in local_mm]

            @staticmethod
            def score(homography: "Config.VisionAlgorithm.Homography", h35: "Config.Dataset.EraValues.Homography", quads_by_frame: dict[str, tuple], *,
                      width_mm: float, profile_tol_mm: float) -> tuple["Config.VisionAlgorithm.HomographyFit.LabelScore", ...]:
                r"""주어진 H35 가 라벨을 얼마나 설명하는가.

                라벨마다 H35 를 고정하고 규격 직사각형(장축 `class_mm` × 단축 `width_mm`)의 자세(중심 · 방위)만 맞춘다.
                잔차는 영상 화소다 — 직사각형 꼭짓점을 영상으로 되돌려 사람이 찍은 꼭짓점과 잰다.
                """
                from cv2 import contourArea as cv2_contourArea, intersectConvexConvex as cv2_intersectConvexConvex
                from numpy import array as np_array, float32 as np_float32
                from scipy.optimize import least_squares as scipy_least_squares

                scores = []
                for frame, quads in quads_by_frame.items():
                    for clicked_px, class_mm in quads:
                        local_mm, start = Config.VisionAlgorithm.HomographyFit.placement(
                            [homography.to_world(h35, u_px, v_px) for u_px, v_px in clicked_px], class_mm, width_mm)

                        def fitted(pose, local_mm=local_mm):
                            return [homography.to_image(h35, x_mm, y_mm) for x_mm, y_mm in Config.VisionAlgorithm.HomographyFit.placed(local_mm, pose)]

                        def residual(pose, clicked_px=clicked_px):
                            return [component for point, target in zip(fitted(pose), clicked_px) for component in (point[0] - target[0], point[1] - target[1])]

                        fitted_px = tuple(fitted(scipy_least_squares(residual, start).x))
                        overlap, _ = cv2_intersectConvexConvex(np_array(fitted_px, np_float32), np_array(clicked_px, np_float32))
                        union = cv2_contourArea(np_array(fitted_px, np_float32)) + cv2_contourArea(np_array(clicked_px, np_float32)) - overlap
                        center_px = (sum(u for u, _ in clicked_px) / 4, sum(v for _, v in clicked_px) / 4)
                        scores.append(Config.VisionAlgorithm.HomographyFit.LabelScore(
                            frame, class_mm, tuple(clicked_px), fitted_px,
                            tuple(math.dist(point, target) for point, target in zip(fitted_px, clicked_px)),
                            profile_tol_mm * homography.ppm_inplane_at(h35, *center_px),
                            overlap / union,
                        ))
                return tuple(scores)

            # --------------------------------------------------- 풀이

            def fit(self, quads_by_frame: dict[str, tuple], *, width_mm: float) -> tuple[tuple[float, float, float], ...]:
                r"""라벨에서 H35(화소 → 상면 mm)를 푼다.

                1. 출발 :: `InitialGuess.VanishingPointRectify` 가 규격 · 장축 가정 없이 모든 사각형을 상사까지 걷는다
                2. 놓기 :: 걷은 평면에서 라벨마다 `placement` 로 장축을 가르고 규격 직사각형을 놓는다
                3. 정제 :: 상면 → 영상 행렬 $G$(원소 여덟)와 라벨마다 자세 셋을 함께 푼다. 잔차는 영상 화소 —
                   $G$ 로 직사각형 꼭짓점을 영상에 보내 찍은 꼭짓점과 잰다. H35 는 $G^{-1}$ 이다

                로버스트 손실의 전이 규모는 `soft_l1_scale__mm` 를 라벨들의 축척 중앙값(px/mm)으로 화소로 바꾼 값이다.
                라벨 하나의 자세는 제 잔차 여덟에만 걸리므로 야코비안이 희소하다 — 이것을 알려야 수치 미분이 끝난다.
                """
                from numpy import zeros as np_zeros
                from scipy.optimize import least_squares as scipy_least_squares

                labels = [(clicked_px, class_mm) for quads in quads_by_frame.values() for clicked_px, class_mm in quads]
                start_matrix = Config.VisionAlgorithm.HomographyFit.InitialGuess.VanishingPointRectify.solve(
                    [clicked_px for clicked_px, _ in labels], width_mm)
                layouts, scales = [], []
                for clicked_px, class_mm in labels:
                    world_mm = [Tool.Geometry.project(start_matrix, u_px, v_px) for u_px, v_px in clicked_px]
                    layouts.append(Config.VisionAlgorithm.HomographyFit.placement(world_mm, class_mm, width_mm))
                    scales.append(sum(itertools.starmap(math.dist, Tool.closed_edges(list(clicked_px))))
                                  / sum(itertools.starmap(math.dist, Tool.closed_edges(world_mm))))
                inverse = Config.VisionAlgorithm._inverse(start_matrix)
                parameters = [inverse[row][column] / inverse[2][2] for row in range(3) for column in range(3)][:8]
                for _, pose in layouts: parameters += list(pose)

                def residual(values):
                    to_image = (tuple(values[0:3]), tuple(values[3:6]), (values[6], values[7], 1.0))
                    out = []
                    for index, (clicked_px, _) in enumerate(labels):
                        local_mm = layouts[index][0]
                        for (x_mm, y_mm), (u_px, v_px) in zip(Config.VisionAlgorithm.HomographyFit.placed(local_mm, values[8 + 3 * index: 11 + 3 * index]), clicked_px):
                            projected_u, projected_v = Tool.Geometry.project(to_image, x_mm, y_mm)
                            out += [projected_u - u_px, projected_v - v_px]
                    return out

                sparsity = np_zeros((8 * len(labels), 8 + 3 * len(labels)), dtype=int)
                sparsity[:, :8] = 1
                for index in range(len(labels)):
                    sparsity[8 * index: 8 * index + 8, 8 + 3 * index: 11 + 3 * index] = 1
                solved = scipy_least_squares(residual, parameters, loss="soft_l1",
                                             f_scale=self.soft_l1_scale__mm * statistics.median(scales),
                                             jac_sparsity=sparsity, x_scale="jac", tr_solver="lsmr").x
                to_image = (tuple(solved[0:3]), tuple(solved[3:6]), (solved[6], solved[7], 1.0))
                matrix = Config.VisionAlgorithm._inverse(to_image)
                return tuple(tuple(element / matrix[2][2] for element in row) for row in matrix)

            # --------------------------------------------------- 초기값

            class InitialGuess:
                """비선형 적합에 넣을 출발 행렬을 닫힌 해로 세우는 길들. 길 하나가 클래스 하나다.

                **닫힌 해로 주는 까닭은 발산 때문이다.**
                원소 여덟과 라벨별 자세를 한꺼번에 비선형으로 풀면 출발이 나쁠 때 멀리 간다.

                **두 길이 요구하는 것이 다르다.**
                하나는 규격을 알아야 하고 하나는 단축만 알면 된다.
                무엇을 손에 쥐었느냐로 골라 쓰라고 형제로 세운다.
                """

                class DirectLinearTransform:
                    """대응점에서 사영 행렬을 선형으로 푼다.

                    규격을 아는 블록 윗면 하나면 선다.
                    그 블록 근처만 정확하므로 나머지 라벨을 얹어 정제하는 것이 다음 단계다.
                    """

                    #: 사영이 8 자유도이고 대응점 하나가 식 둘을 주므로 넷은 있어야 한다.
                    MIN_POINTS = 4

                    @classmethod
                    def solve(cls, image_px: Sequence[tuple[float, float]], world_mm: Sequence[tuple[float, float]]) -> tuple[tuple[float, float, float], ...]:
                        r"""화소 → 상면 mm 사영 행렬. $h_{22}=1$ 로 고정해 미지수를 여덟로 둔다.

                        한 대응점이 식 둘을 준다. 분모를 옮기면 미지수에 대해 선형이 된다 ::

                        $$X\,(h_{20}u + h_{21}v + 1) = h_{00}u + h_{01}v + h_{02}$$

                        넷이면 딱 떨어지고 더 주면 최소자승이 된다.

                        **원점을 여기서 정하지 않는다.**
                        규격을 아는 블록 하나의 국소 좌표를 `world_mm` 으로 주면 그 블록 기준의 해가 나온다.
                        전역 원점이 어디든 로봇 아핀이 흡수한다.

                        **어느 화소 꼭짓점이 어느 물리 꼭짓점인지는 부르는 쪽이 정한다.**
                        라벨의 네 점은 TL · TR · BR · BL 차례로 올 뿐 어느 변이 장축인지 말하지 않는다.
                        짝짓기는 규격 가설과 함께 고르는 일이라 여기서 하지 않는다.
                        """
                        if len(image_px) < cls.MIN_POINTS:
                            raise Tool.Missing(
                                f"대응점이 {len(image_px)} 쌍이다 — {cls.MIN_POINTS} 쌍은 있어야 푼다"
                            )
                        rows, values = [], []
                        for (u_px, v_px), (x_mm, y_mm) in zip(image_px, world_mm):
                            rows.append((u_px, v_px, 1.0, 0.0, 0.0, 0.0, -x_mm * u_px, -x_mm * v_px))
                            values.append(x_mm)
                            rows.append((0.0, 0.0, 0.0, u_px, v_px, 1.0, -y_mm * u_px, -y_mm * v_px))
                            values.append(y_mm)
                        found = Tool.Fit.LeastSquares.solve(tuple(rows), tuple(values))
                        return ((found[0], found[1], found[2]),
                                (found[3], found[4], found[5]),
                                (found[6], found[7], 1.0))

                class VanishingPointRectify:
                    """평행과 직교라는 무차원 구속으로 사영을 두 단계에 걸쳐 걷는다.

                    **규격을 몰라도 선다.** 쓰는 물리량이 단축 하나뿐이고 그것은 3종 공통이다.
                    규격을 알아야 하는 `DirectLinearTransform` 과 갈리는 자리가 이것이다.

                    1. **평행** :: 마주 보는 변 쌍 둘이 각각 소실점을 만들고, 두 점이 무한선을
                       세운다. 그 선을 무한대로 보내면 사영이 아핀까지 걷힌다
                    2. **직교** :: 걷힌 평면에서 두 변 방향이 직각이라는 구속으로 상사까지 간다.
                       남는 축척은 단축이 고정한다

                    낼 수 있는 것은 상사까지다 — 회전과 평행이동은 정해지지 않는다.
                    로봇 아핀이 흡수하므로 초기값으로는 그것으로 족하다.

                    **사각형을 한 프레임에서만 모으지 않는다.**
                    무한선과 직교 구속은 회차 하나의 사실이라 프레임을 건너 합쳐도 같은 것을 말한다.
                    소실점은 나란한 두 변에서 나오므로 라벨 클릭 한 화소가 크게 번지는데, 합치면 그것이 눌린다.
                    """

                    #: 직교 구속은 사각형 하나에 식 하나인데 걷을 자유도가 둘이라 하나로는 안 선다.
                    #: 1 단계(평행)는 하나로도 서지만 2 단계가 못 서므로 이 수가 전체를 정한다.
                    MIN_QUADS = 2

                    #: 방위가 갈려야 식이 는다.
                    #: **90도 차이는 갈린 것이 아니다** — 사각형을 90도 돌리면 두 변 방향이 자리만 바꿔 같은 쌍이 되고, $S$ 가 대칭이라 같은 식이 된다.
                    ONE_PAIR = ("변 방향 쌍이 한 벌뿐이라 상사까지 못 간다 — "
                                "90도 돌려 놓은 것은 같은 쌍이므로 비스듬히 놓은 사각형이 있어야 한다")

                    @staticmethod
                    def _join(a_px: tuple[float, float], b_px: tuple[float, float]) -> tuple[float, float, float]:
                        """두 점을 지나는 직선. 동차 좌표의 외적이다."""
                        return (a_px[1] - b_px[1],
                                b_px[0] - a_px[0],
                                a_px[0] * b_px[1] - a_px[1] * b_px[0])

                    @staticmethod
                    def _meet(line_p: tuple[float, float, float], line_q: tuple[float, float, float]) -> tuple[float, float, float]:
                        """두 직선이 만나는 점. 같은 외적이다.

                        **동차인 채로 둔다.**
                        영상에서 변이 나란하면 소실점이 무한원에 놓여 마지막 성분이 0 이 되는데, 나누는 순간 그 점이 사라진다.
                        """
                        return (line_p[1] * line_q[2] - line_p[2] * line_q[1],
                                line_p[2] * line_q[0] - line_p[0] * line_q[2],
                                line_p[0] * line_q[1] - line_p[1] * line_q[0])

                    @classmethod
                    def solve(cls, quads_px: Sequence[Sequence[tuple[float, float]]], width_mm: float) -> tuple[tuple[float, float, float], ...]:
                        r"""화소 → 상면 mm 사영 행렬. 꼭짓점은 네 개가 변을 따라 도는 차례로 온다.

                        **무한선을 $l_3=1$ 로 세운다.**
                        소실점은 무한원에 있을 수 있어도 무한선은 그럴 수 없다 — 그 선이 원점을 지나면 상면이 카메라 중심을 품는다는 뜻이라 상이 맺히지 않는다.

                        **직교 구속은 이중 원점 원뿔에 거는 식이다.**
                        걷힌 평면의 두 변 방향 $d_1 \perp d_2$ 에서 $d_1^{T} S\, d_2 = 0$ 이고, $S$ 는 축척을 빼면 자유도가 둘이라 **식이 둘은 있어야 한다.**
                        방위가 같은 사각형을 더 주면 같은 식이 늘 뿐이므로 서로 다른 방위로 놓는다.
                        """
                        if len(quads_px) < cls.MIN_QUADS:
                            raise Tool.Missing(
                                f"사각형이 {len(quads_px)} 개다 — 방위가 다른 것으로 "
                                f"{cls.MIN_QUADS} 개는 있어야 직교 구속이 선다"
                            )

                        # ------------------------------ 1. 평행 → 무한선 → 아핀
                        seen = []
                        for quad in quads_px:
                            seen.append(cls._meet(cls._join(quad[0], quad[1]), cls._join(quad[3], quad[2])))
                            seen.append(cls._meet(cls._join(quad[1], quad[2]), cls._join(quad[0], quad[3])))
                        slope = Tool.Fit.LeastSquares.solve(
                            tuple((point[0], point[1]) for point in seen),
                            tuple(-point[2] for point in seen),
                        )
                        rectify = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (slope[0], slope[1], 1.0))

                        # ---------------------------------------- 2. 직교 → 상사
                        rows, constants, flattened = [], [], []
                        for quad in quads_px:
                            flat = tuple(Tool.Geometry.project(rectify, u_px, v_px) for u_px, v_px in quad)
                            flattened.append(flat)
                            along = (flat[1][0] - flat[0][0], flat[1][1] - flat[0][1])
                            across = (flat[2][0] - flat[1][0], flat[2][1] - flat[1][1])
                            rows.append((along[0] * across[0], along[0] * across[1] + along[1] * across[0]))
                            constants.append(-along[1] * across[1])
                        # 방위가 한 벌이면 두 길로 드러난다.
                        # 정확히 겹치면 설계행렬이 특이해지고, 잡음이 섞여 아슬하게 풀리면 $S$ 가 양정부호를 잃는다.
                        # 같은 일이라 같이 말한다
                        try:
                            s11, s12 = Tool.Fit.LeastSquares.solve(tuple(rows), tuple(constants))
                        except ValueError as exc:
                            raise ValueError(cls.ONE_PAIR) from exc
                        if s11 <= Config.VisionAlgorithm.EPS or s11 - s12 * s12 <= Config.VisionAlgorithm.EPS:
                            raise ValueError(cls.ONE_PAIR)
                        # 촐레스키. $A^{T}A = S$ 이고 회전만큼의 자유가 남는다
                        scale_x = math.sqrt(s11)
                        shear = s12 / scale_x
                        scale_y = math.sqrt(1.0 - shear * shear)
                        metric = ((scale_x, shear, 0.0), (0.0, scale_y, 0.0), (0.0, 0.0, 1.0))

                        # ------------------------------------- 3. 단축으로 축척
                        shorts = []
                        for flat in flattened:
                            corners = tuple(Tool.Geometry.project(metric, corner_x, corner_y) for corner_x, corner_y in flat)
                            shorts.append(min(Config.VisionAlgorithm._delta(corners[0], corners[1]),
                                              Config.VisionAlgorithm._delta(corners[1], corners[2])))
                        grown = width_mm / statistics.median(shorts)
                        scaled = ((grown * metric[0][0], grown * metric[0][1], 0.0),
                                  (grown * metric[1][0], grown * metric[1][1], 0.0),
                                  (0.0, 0.0, 1.0))
                        return tuple(
                            tuple(sum(scaled[row_index][k_index] * rectify[k_index][column_index] for k_index in range(3)) for column_index in range(3))
                            for row_index in range(3)
                        )

        class Preprocess(Tool.JsonNode):
            """영상 전처리 규격. 커널은 물리 길이에 축척을 곱해 화소로 낸다.

            `bg_kernel_scale` :: 배경 추정 커널을 최장 규격의 몇 배로 잡을지
            `clahe_cell_min__px` :: CLAHE 격자 셀의 화소 하한
            `clahe_contrast_limit` :: 히스토그램 한 칸이 균등 분포의 몇 배까지 솟는 것을 허용할지
            `gain_floor_ratio` :: 기준면이 중앙 밝기의 이 비율 아래면 게인을 고정한다
            `gain_patch_ratio` :: 기준 밝기를 뽑을 중앙 패치가 짧은 변의 몇 분의 일인지
            `morph_area_factor` :: 모폴로지 연산이 관측 마스크 면적에 남기는 비율
            `whiten_sigma_span` :: 백색화에서 평균 ± 몇 σ 를 0~255 양끝에 맞출지. 튜닝 — 근거 없음
            `adaptive_c_noise_multiple` :: 적응형 가우시안 보정값을 프레임 차분 잡음 σ 의 몇 배로 둘지. 튜닝 — 근거 없음
            `sauvola_weight_k` :: 사우볼라 국소 표준편차 가중. 튜닝 — 근거 없음
            `brightness_floor__gray` :: 바닥 밝기, 회색 계조. 작업영역에 이보다 밝은 화소가 없으면 블록이 없다. 블록 옆면은 이보다 어두울 수 있어 마스크를 자르는 데는 안 쓴다
            """

            class CountRange(NamedTuple):
                """격자 분할 수의 하한과 상한."""

                min_count: int
                max_count: int

            class Grid(NamedTuple):
                """격자 분할 수. 영상 가로 방향 칸 수와 세로 방향 칸 수."""

                cols: int
                rows: int

            @cached_property
            def clahe_grid_clip(self) -> "Config.VisionAlgorithm.Preprocess.CountRange":
                """격자 분할 수의 하한과 상한 — `clahe_grid_clip` 의 [하한, 상한] 이다."""
                return self.CountRange(*(int(count) for count in self.doc["clahe_grid_clip"]))

            def adaptive_c_offset(self, frame_difference_sigma_gray: float) -> float:
                """적응형 가우시안 문턱의 보정값. 국소 평균에서 이만큼 더 밝아야 흰색이다 — 잡음 σ 에 배수를 곱한다."""
                return self.adaptive_c_noise_multiple * frame_difference_sigma_gray

            def gain_patch_px(self, image_w_px: int, image_h_px: int) -> int:
                """게인맵의 기준 밝기를 뽑을 중앙 패치의 변 길이.

                짧은 변에서 잡는다 — 긴 변에서 잡으면 세로로 잘린 화면에서 패치가 화면 밖으로 나간다.
                """
                return Tool.odd(min(image_w_px, image_h_px) * self.gain_patch_ratio)

            def bg_kernel_px(self, ppm: float, *, length_max_mm: float) -> int:
                """조명 배경 추정 열림 연산 커널. 최장 규격보다 커야 블록이 배경에 안 남는다."""
                return Tool.odd(ppm * self.bg_kernel_scale * length_max_mm)

            def window_kernel_px(self, ppm: float, *, width_mm: float) -> int:
                """국소 분할 윈도우. 블록 단축 하나가 들어가는 크기로 잡는다."""
                return Tool.odd(ppm * width_mm)

            def clahe_cell_px(self, ppm: float, *, width_mm: float) -> float:
                """CLAHE 격자 셀 한 변. 블록 단축 하나를 담되 화소 하한을 지킨다."""
                return max(self.clahe_cell_min__px, ppm * width_mm)

            def is_cell_block_sized(self, ppm: float, *, width_mm: float) -> bool:
                """셀이 블록 단축을 담는가.

                하한에 걸리면 셀이 블록을 따라가지 않는다.
                격자는 그래도 쪼개지지만 "블록 하나가 한 칸" 이라는 뜻이 사라져 국소 대비를 올린다는 목적이 성립하지 않는다.
                """
                return ppm * width_mm >= self.clahe_cell_min__px

            def clahe_grid(self, ppm: float, image_w_px: int, image_h_px: int, *, width_mm: float) -> "Config.VisionAlgorithm.Preprocess.Grid":
                """CLAHE 격자 분할 수.

                셀 하나가 블록 단축 하나를 담도록 잡되, 축척이 낮으면 셀이 지나치게 작아지므로 화소 하한을 둔다.
                """
                cell = self.clahe_cell_px(ppm, width_mm=width_mm)
                grid_minimum, grid_maximum = self.clahe_grid_clip
                return self.Grid(
                    cols=min(max(round(image_w_px / cell), grid_minimum), grid_maximum),
                    rows=min(max(round(image_h_px / cell), grid_minimum), grid_maximum),
                )

        class Quantization(Tool.JsonNode):
            """화소 격자로 끊긴 윤곽이 관측 면적에 남기는 손실 규격.

            `contour_bias__px` :: 윤곽선이 실제 경계에서 안쪽으로 밀리는 평균 화소 편차
            """

            def area_loss_ratio(self, ppm: float, *, width_mm: float, length_mm: float) -> float:
                r"""경계 화소 편차 $k$ 에 의한 상면 면적 손실 비율.

                물리 결손 면적 $\Delta A = (k / \text{PPM}) \cdot P$ 이며, $r=0$ 참값이자 보수적 상한인 직사각형 둘레 $P = 2(W + L)$ 와 면적 $A = W L$ 에서 유도된다.

                $$\varepsilon_q = \frac{\Delta A}{A} = \frac{2k}{\text{PPM}} \cdot \frac{W + L}{W L}$$

                축척(PPM)이 낮을수록, 블록 치수($W, L$)가 작을수록 손실비가 커지므로 최소 단품에서 최악 조건 상한을 갖는다.
                """
                return (2.0 * self.contour_bias__px / ppm) * (width_mm + length_mm) / (width_mm * length_mm)

            @staticmethod
            def contour_bias_of(region_area_px: float, contour_area_px: float, perimeter_px: float) -> float:
                r"""경계 화소 편차 $k$ 를 영역 하나에서 잰다. $\Delta A = k \cdot P$ 를 거꾸로 푼 것이다 — $k = (A_{\text{영역}} - A_{\text{윤곽}}) / P$.

                영역은 마스크의 화소 수, 윤곽은 그 영역의 경계 화소를 이은 다각형이다. 문턱이 실제 경계를 고르게 가르면 화소 수가 실제 넓이를 편향 없이 재므로, 둘의 차가 화소 격자로 끊긴 윤곽이 남기는 손실이다.
                """
                return (region_area_px - contour_area_px) / perimeter_px

            def is_resolved(self, area_px: float, perimeter_px: float) -> bool:
                r"""윤곽 하나가 화소 격자 잡음보다 큰가. 넓이가 제 둘레의 양자화 띠 $k P$ 보다 넓어야 한다.

                $\Delta A = k P$ 는 화소 격자로 끊긴 경계가 넓이에 남기는 몫이다(`contour_bias_of`). 넓이가 그 몫보다 작으면 넓이 전부가 격자 탓과 구별되지 않는다.
                """
                return area_px > self.contour_bias__px * perimeter_px

        class Segmentation(Tool.JsonNode):
            """밀착 블록 분할 규격. 접합부 필렛 결함점을 찾아 절단선을 세운다.

            `depth_sigma_factor` :: 화소 양자화 잡음의 몇 배를 유효 깊이로 볼지
            `notch_depth_ratio` :: 경사 시점 차폐 및 화소 뭉개짐에 대비한 이론 노치 깊이 유효 하한 비율
            `cut_angle_tol__deg` :: 절단선이 외곽 주 변과 평행·직교로 인정되는 허용각
            """

            #: 화소 격자 양자화 잡음의 표준편차. 균등분포 폭 1 화소에서 1/sqrt(12) 로 나온다.
            GRID_SIGMA_PX = 1.0 / math.sqrt(12.0)

            def depth_min_px(self, ppm: float, *, notch_depth_mm: float) -> float:
                r"""분할 결함점으로 인정하는 최소 오목 깊이.

                화소 격자 양자화 잡음과 유효 노치 깊이(이론 노치 깊이에 하한 비율을 곱한 값) 중 큰 값을 취한다.
                """
                return max(
                    self.depth_sigma_factor * self.GRID_SIGMA_PX,
                    self.notch_depth_ratio * notch_depth_mm * ppm,
                )

            @cached_property
            def step_min_px(self) -> float:
                r"""윤곽 샘플링 간격의 하한.

                샘플 간격은 국소 방향을 재는 기선 길이다.
                표본 하나의 가로 불확도가 격자 잡음 $\sigma$ 이므로 두 점으로 잰 방향의 오차는 $\sqrt{2}\,\sigma / L$ 이고, 이것이 절단선 허용각을 넘으면 방향 판정이 성립하지 않는다.

                $$L_{\min} = \frac{\sqrt{2}\,\sigma}{\tan \theta_{tol}}$$

                허용각을 좁히면 기선이 길어진다.
                """
                return math.sqrt(2.0) * self.GRID_SIGMA_PX / math.tan(
                    math.radians(self.cut_angle_tol__deg)
                )

            @staticmethod
            def spec_error_limit_mm(*, fillet_r_mm: float) -> float:
                r"""측정 장축이 공칭 규격으로 인정되는 허용 편차.

                양 끝단 코너 원호 접점 물러남으로 인한 최대 겉보기 길이 축소 한계인 2 * r 을 적용한다.
                """
                return 2.0 * fillet_r_mm

            @cached_property
            def cut_angle_cos(self) -> float:
                """허용각의 코사인. 평행 판정의 내적 하한이자 직교 판정의 외적 하한."""
                return math.cos(math.radians(self.cut_angle_tol__deg))

            @cached_property
            def cut_angle_sin(self) -> float:
                """허용각의 사인. 평행 판정의 외적 상한이자 직교 판정의 내적 상한."""
                return math.sin(math.radians(self.cut_angle_tol__deg))

            def is_collinear(self, vector_u: tuple[float, float], vector_v: tuple[float, float]) -> bool:
                r"""두 단위 방향이 평행한가.

                정규화 오차가 한 지표만 흔드는 것을 막기 위해 내적($|u \cdot v| \ge \cos\theta_{tol}$)과 외적($|u \times v| \le \sin\theta_{tol}$)을 함께 본다.
                """
                return (
                    abs(vector_u[0] * vector_v[0] + vector_u[1] * vector_v[1]) >= self.cut_angle_cos
                    or abs(vector_u[0] * vector_v[1] - vector_u[1] * vector_v[0]) <= self.cut_angle_sin
                )

            def is_orthogonal(self, vector_u: tuple[float, float], vector_v: tuple[float, float]) -> bool:
                r"""두 단위 방향이 직교하는가.

                $90^\circ$ 회전한 법선 벡터 $v^\perp = (-v_y, v_x)$ 에 대해 $|u \cdot v^\perp| = |u \times v|$ 이 성립하므로 평행 판정으로 일원화한다.
                """
                return self.is_collinear(vector_u, (-vector_v[1], vector_v[0]))

            @staticmethod
            def block_count(area_world_mm2: float, *, block_area_mean_mm2: float) -> int:
                """군집 면적으로부터 추정한 공칭 블록 수.

                절단선을 $N-1$ 개만 채택해 과분할을 막는 상한으로 쓴다. 군집을 전제로 부르므로 하한은 2다.
                """
                return max(2, round(area_world_mm2 / block_area_mean_mm2))

        class RectFit(Tool.JsonNode):
            """사각형 적합기 입력 관문 규격.

            `min_valid_area_ratio` :: 최소 단품 외접 직사각형 대비 적합 입력 마스크 면적 하한 비율
            """

            def area_min_mm2(self, *, width_mm: float, length_min_mm: float) -> float:
                r"""적합 입력으로 채택하는 최소 상면 면적. 최소 단품 외접 직사각형 면적에 유효 하한 비율을 곱한다."""
                return self.min_valid_area_ratio * (length_min_mm * width_mm)

        class CameraShift(Tool.JsonNode):
            r"""카메라가 조금 밀렸을 때 화면이 얼마나 밀렸나를 재고, 화소에 매인 회차 값을 그만큼 옮기는 절차의 규격이다.

            카메라 높이가 그대로이고 조금 돌거나 기운 정도면 화면이 거의 고르게 밀린다. 그래서 밀림을 화면 전체의 유클리드 변환 $W$ (이동 · 회전)로 본다.
            기준 장면과 지금 장면은 로봇이 같은 자세일 때 찍은 것이어야 한다 — 움직인 것이 카메라뿐이어야 한다. 블록이 드나드는 작업영역 안은 견주지 않는다.
            `iterations` :: ECC 되풀이 상한
            `eps` :: ECC 상관계수가 이보다 덜 늘면 멈춘다
            `gauss_filter__px` :: ECC 가 견주기 전에 두 장을 흐리는 가우시안 크기
            """

            def warp(self, reference: Any, current: Any, work_area_px: Sequence[tuple[float, float]]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
                r"""기준 장면의 화소를 지금 장면의 화소로 보내는 $W$ (2 × 3). 작업영역 밖만 견준다(ECC · 유클리드).

                ECC 는 $\text{기준}(\mathbf{x}) \approx \text{지금}(W\mathbf{x})$ 이 되게 $W$ 를 푼다.
                """
                from cv2 import (COLOR_BGR2GRAY as cv2_COLOR_BGR2GRAY, MOTION_EUCLIDEAN as cv2_MOTION_EUCLIDEAN,
                                 TERM_CRITERIA_COUNT as cv2_TERM_CRITERIA_COUNT, TERM_CRITERIA_EPS as cv2_TERM_CRITERIA_EPS,
                                 cvtColor as cv2_cvtColor, findTransformECC as cv2_findTransformECC)
                from numpy import eye as np_eye, float32 as np_float32

                def gray(image: Any) -> Any:
                    return (cv2_cvtColor(image, cv2_COLOR_BGR2GRAY) if image.ndim == 3 else image).astype(np_float32)

                outside = 255 - Tool.Vision.fill_polygons(reference.shape[:2], [work_area_px], 255)
                _, matrix = cv2_findTransformECC(gray(reference), gray(current), np_eye(2, 3, dtype=np_float32), cv2_MOTION_EUCLIDEAN,
                                                 (cv2_TERM_CRITERIA_COUNT | cv2_TERM_CRITERIA_EPS, self.iterations, self.eps),
                                                 outside, self.gauss_filter__px)
                return tuple(tuple(float(element) for element in row) for row in matrix)

            @staticmethod
            def moved_era_values(h35: "Config.Dataset.EraValues.Homography", work_area: "Config.Dataset.EraValues.WorkArea", affine: "Config.Dataset.EraValues.Affine", warp: Sequence[Sequence[float]]) -> tuple["Config.Dataset.EraValues.Homography", "Config.Dataset.EraValues.WorkArea", "Config.Dataset.EraValues.Affine"]:
                r"""화면이 $W$ 만큼 밀린 설치의 회차 값. 화소에 매인 값만 옮기고 나머지는 그대로 둔다.

                - H35 (화소 → 상면 mm) :: $H W^{-1}$ — 밀린 화소를 되돌려 같은 상면 mm 로 보낸다
                - 세로 소실점 (동차 세 수) :: $W \mathbf{w}$ — 밑면 화소 $\mathbf{b} \propto \mathbf{x} - k\mathbf{w}$ 의 $k$ 는 H35 셋째 행과 화소의 곱이라 $H W^{-1}$ 과 $W\mathbf{x}$ 에서 그대로다
                - 작업영역 · 아핀 대응점 · 이동 성분 관측의 화소 :: $W\mathbf{x}$
                H35 는 셋째 행 셋째 수가 1 이 되게 나눈다. 나눈 수 $c$ 만큼 $k$ 가 작아지므로 소실점에 $c$ 를 곱한다.
                아핀 행렬(상면 mm → 로봇)은 카메라와 무관하므로 그대로다.
                """
                forward = (tuple(warp[0]), tuple(warp[1]), (0.0, 0.0, 1.0))

                def point(xy: Sequence[float]) -> tuple[float, float]:
                    return Tool.Geometry.project(forward, float(xy[0]), float(xy[1]))

                if h35.matrix is not None:
                    backward = Config.VisionAlgorithm._inverse(forward)
                    matrix = [[sum(h35.matrix[row][k] * backward[k][column] for k in range(3)) for column in range(3)] for row in range(3)]
                    scale = matrix[2][2]
                    h35 = h35.replaced(matrix=tuple(tuple(element / scale for element in row) for row in matrix), vanishing_point=None if h35.vanishing_point is None else tuple(scale * sum(forward[row][column] * h35.vanishing_point[column] for column in range(3)) for row in range(3)))
                if work_area.polygon__px is not None:
                    work_area = work_area.replaced(polygon__px=tuple(point(xy) for xy in work_area.polygon__px))
                affine = affine.replaced(pairs=tuple(pair.replaced(pixel_xy=point(pair.pixel_xy)) for pair in affine.pairs), pivot=None if affine.get("pivot") is None else affine.pivot.replaced(pixel_xy=tuple(point(xy) for xy in affine.pivot.pixel_xy)))
                return h35, work_area, affine

        class BoxFit(Tool.JsonNode):
            """블록의 상면 자세를 영상의 면 부류에 맞추는 절차의 규격이다.

            블록을 기둥으로 그려 윗면은 흰 부류와, 보이는 옆면은 회색 부류와 견준다.
            보인 부류 지도(`seen`)는 부르는 쪽이 전처리로 세 부류(`Tool.Vision.PrismFace` 값)로 나눠, 원본을 `raster_scale` 배로 키운 격자에 준다.
            세로 소실점이 풀린 사영 모델이 있어야 옆면이 그려진다.
            `raster_scale` :: 원본 한 화소를 몇 칸으로 나눠 채점하나
            """

            def mismatch(self, pieces: Sequence["Entity.Piece"], seen: Any, region: Any, origin_px: tuple[float, float],
                         homography: "Config.VisionAlgorithm.Homography", h35: "Config.Dataset.EraValues.Homography") -> float:
                """블록들을 기둥으로 그린 부류 지도가 보인 부류 지도와 어긋난 몫이다(`Tool.Vision.class_mismatch`)."""
                drawn = Tool.Vision.paint_prisms(seen.shape, [homography.shape_3d_px(h35, piece.corners_mm) for piece in pieces], origin_px, self.raster_scale)
                return Tool.Vision.class_mismatch(drawn, seen, region)

            def pose_fitted(self, pieces: Sequence["Entity.Piece"], index: int, seen: Any, region: Any, origin_px: tuple[float, float],
                            homography: "Config.VisionAlgorithm.Homography", h35: "Config.Dataset.EraValues.Homography") -> "Entity.Piece":
                """블록 하나의 상면 자세 (x, y, θ)를 Nelder-Mead 로 옮기고 돌려 어긋남을 줄인다. 다른 블록은 제자리에 둔 채 함께 그린다.

                자세를 축마다 그 자리의 영상 1 px 을 한 단위로 재어 푼다 — 위치는 1 px 에 해당하는 mm, 각도는 블록 끝이 1 px 도는 각이다.
                첫 걸음은 한 단위, 멈춤은 채점 격자 한 칸(`1 / raster_scale` 단위)이라 세 축에서 뜻이 같다.
                다른 블록과 발자국이 겹치는 자세(`Entity.Piece.clearance_mm` 가 음수)는 어떤 맞는 자세보다도 나쁘게 친다 — 공면 위 블록은 겹칠 수 없다.
                겹친 깊이를 채점 격자 칸 수로 세어 어긋남의 끝값 1 위에 얹으므로, 겹친 채 받은 블록도 풀리는 쪽으로 움직인다.
                어긋남이 줄지 않으면 받은 블록을 그대로 돌려준다.
                """
                from scipy.optimize import minimize as scipy_minimize

                pieces = tuple(pieces)
                piece = pieces[index]
                mm_per_px = 1.0 / homography.ppm_inplane_at(h35, *homography.to_image(h35, piece.pose.x_mm, piece.pose.y_mm))
                deg_per_px = math.degrees(mm_per_px / (piece.length_mm / 2.0))

                per_px = (mm_per_px, mm_per_px, deg_per_px)
                cell_mm = mm_per_px / self.raster_scale

                def pose_of(steps) -> "Entity.Piece.Pose":
                    return Entity.Piece.Pose(*(float(origin_value + step * unit) for origin_value, step, unit in zip(piece.pose, steps, per_px)))

                def cost(steps) -> float:
                    moved = dataclasses.replace(piece, pose=pose_of(steps))
                    overlap_mm = max((-moved.clearance_mm(other) for other in pieces[:index] + pieces[index + 1:]), default=0.0)
                    if overlap_mm > 0.0: return 1.0 + math.ceil(overlap_mm / cell_mm)
                    return self.mismatch(pieces[:index] + (moved,) + pieces[index + 1:], seen, region, origin_px, homography, h35)

                simplex = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
                result = scipy_minimize(cost, simplex[0], method="Nelder-Mead", options=dict(initial_simplex=simplex, xatol=1.0 / self.raster_scale, fatol=0.0))
                if result.fun >= cost(simplex[0]):
                    return piece
                fitted = dataclasses.replace(piece, pose=pose_of(result.x))
                return dataclasses.replace(fitted, corners_px=homography.upper_shape_px(h35, fitted.corners_mm))

            def poses_fitted(self, pieces: Sequence["Entity.Piece"], seen: Any, region: Any, origin_px: tuple[float, float],
                             homography: "Config.VisionAlgorithm.Homography", h35: "Config.Dataset.EraValues.Homography") -> tuple["Entity.Piece", ...]:
                """블록마다 `pose_fitted` 를 돌고, 한 바퀴 동안 아무 블록도 안 움직일 때까지 되풀이한다.

                어긋남이 줄어든 자세만 받으므로 되풀이는 끝난다 — 어긋남도 겹친 깊이도 격자 칸 수로 세므로 끝없이 줄 수 없다.
                """
                pieces = tuple(pieces)
                moved = True
                while moved:
                    moved = False
                    for index in range(len(pieces)):
                        fitted = self.pose_fitted(pieces, index, seen, region, origin_px, homography, h35)
                        if fitted is not pieces[index]:
                            pieces = pieces[:index] + (fitted,) + pieces[index + 1:]
                            moved = True
                return pieces

        class VanishingSearch(Tool.JsonNode):
            """옆면으로 세로 소실점을 찾는 탐색의 규격. 탐색은 `vis_alg_core.Calibration.vanishing_point_from_sides` 가 한다.

            훑는 수는 윗면 무게중심 한 점에서 잰 셋이다 — 35 mm 세로 모서리의 화면 변위 (가로 · 세로) 와 몫(`Homography.vanishing_point_from_edge`).
            `offset_span__px` :: 거친 격자가 훑는 변위의 반폭
            `offset_step__px` :: 거친 격자의 변위 간격
            `shrink_grid` :: 거친 격자가 훑는 몫. 0 과 1 사이
            `refine_starts` :: 거친 격자에서 다듬을 등수
            """

        class ScaleBootstrap(Tool.JsonNode):
            """H35 가 없거나 틀어졌을 때 블록 단축으로 축척을 어림하는 대체 경로의 규격.

            `ppm_ema_alpha` :: 축척 시간축 평활 계수
            `ppm_update_threshold` :: 이 변화량 미만이면 축척을 갱신하지 않는다
            """

            def ppm_updated(self, previous: float, measured: float) -> float:
                """축척 시간축 평활. 변화가 문턱 미만이면 갱신하지 않는다.

                프레임마다 축척이 흔들리면 커널 크기가 같이 흔들려 검출이 떨린다.
                """
                if abs(measured - previous) < self.ppm_update_threshold:
                    return previous
                return (1.0 - self.ppm_ema_alpha) * previous + self.ppm_ema_alpha * measured

        class LabelAudit(Tool.JsonNode):
            """라벨 무결성 검증 규격. 사영 모델을 풀 입력을 거른다.

            `fit_separation_margin` :: 차선 대비 최선 잔차 비가 이보다 커야 채택한다
            `fit_max_rms__mm` :: 최선 적합의 잔차 상한
            """

            #: 사람이 한 화소보다 정확히 찍을 수 없다는 클릭 양자화 바닥.
            CLICK_JITTER_PX = 1.0

            def is_separated(self, rms_best_mm: float, rms_second_mm: float) -> bool:
                """최선과 차선이 갈릴 만큼 벌어졌는가. 붙어 있으면 판정을 보류한다."""
                return rms_second_mm >= self.fit_separation_margin * rms_best_mm

            def is_fit_accepted(self, rms_best_mm: float, rms_second_mm: float) -> bool:
                """적합을 채택하는가. 잔차가 작고 차선과 갈려야 한다."""
                return rms_best_mm <= self.fit_max_rms__mm and self.is_separated(
                    rms_best_mm, rms_second_mm
                )

            def intrusion_ratio_min(self, ppm: float, *, width_mm: float) -> float:
                r"""겹침이 클릭 오차로 설명되는 상한. 지터를 단축으로 나눈 비다.

                겹침이 한 변을 따라 폭 $j$ 의 띠로 생기면 면적비가 $j/W$ 가 된다. 변 길이가 상쇄되므로 규격과 무관하고, 축척이 좋아지면 한 화소가 짧아져 함께 내려간다.
                """
                return self.CLICK_JITTER_PX / (ppm * width_mm)

            def is_intruded(self, overlap_ratio: float, ppm: float, *, width_mm: float) -> bool:
                r"""두 사각형이 비정상적으로 겹쳤는가.
                블록 실체는 외접 직사각형이므로 물리적 겹침이 0이나, 라벨러가 상면 필렛 음영 경계를 육안 식별하며 수반하는 시각적 클릭 편차를 흡수하기 위해 지터 임계값 이내의 겹침만 허용한다.
                """
                return overlap_ratio > self.intrusion_ratio_min(ppm, width_mm=width_mm)

        class LabelAssist(Tool.JsonNode):
            """라벨 자동 제안 규격. 사람이 확정하기 전의 초안을 만든다.

            `fill_min_ratio` :: 원근 투영 · 모폴로지 · 화소 양자화 누적 손실을 반영한 외접 사각형 대비 면적비 하한
            `ar_cross_check` :: 규격 적합을 원시 종횡비로 교차 검증하는가
            `ar_cross_margin` :: 관측 종횡비가 다른 규격 쪽에 이만큼 더 가까울 때만 어긋난 것으로 본다
            """

            def is_fill_accepted(self, fill_ratio: float) -> bool:
                """외접 사각형 대비 관측 면적비가 누적 손실 하한 이상인지 판정한다."""
                return fill_ratio >= self.fill_min_ratio

            def is_aspect_agreed(self, aspect_observed: float, length_model_mm: float, *, width_mm: float, aspect_ratios_nominal: tuple[float, ...]) -> bool:
                """적합이 고른 규격이 원시 종횡비와 맞는가.

                종횡비는 척도에도 사영 모델에도 기대지 않는 독립 근거다.
                경계에 걸친 값으로 뒤집지 않도록 마진을 둔다.
                """
                if not self.ar_cross_check:
                    return True
                best = min(abs(aspect_observed - ratio) for ratio in aspect_ratios_nominal)
                return (abs(aspect_observed - length_model_mm / width_mm) - best) <= self.ar_cross_margin

        class AffineTransform(Tool.JsonNode):
            """상면 mm 평면을 로봇 기저 좌표계로 보내는 2차원 아핀 사상의 계산.

            행렬과 그것을 푼 대응점 · 이동 성분 관측은 회차 값이라 받아서 쓴다(`Config.Dataset.EraValues.Affine`).
            `angle_offset__deg` :: 엔드 이펙터 장착 영점 오차
            `max_residual_tol__mm` :: 재투영 최대 잔차 허용 상한
            """

            class Move(NamedTuple):
                """대응점 수집에서 블록을 한 번 놓고 보고 다시 문 기록. `drift_fitted` 가 받는다."""

                name: str
                order: int  # 같은 블록을 놓은 차례. 이웃한 차례끼리만 식을 세운다 — 사이에 못 쓴 관측이 끼면 그 쌍은 빠진다
                pixel_xy: tuple[float, float]  # 놓은 뒤 본 검출 중심, 화소
                placed_xy_mm: tuple[float, float]  # 패드가 블록을 놓은 지령 자리
                grabbed_xy_mm: tuple[float, float]  # 본 뒤 패드가 블록을 다시 문 지령 자리
                turn_deg: float  # 들고 다니는 방위에서 손목을 더 돌린 각

            class DriftFit(NamedTuple):
                """`drift_fitted` 의 답."""

                linear: tuple[tuple[float, float], tuple[float, float]]  # 선형 부분 A — 상면 mm 를 로봇 mm 로
                drift_mm: dict  # 손목을 더 돌린 각 → 한 번 놓을 때 블록이 패드 밑에서 밀린 양 (x, y), 로봇 mm
                residuals_mm: tuple[float, ...]  # 이웃 관측 쌍마다 남은 거리

            @staticmethod
            def _require_matrix(affine: "Config.Dataset.EraValues.Affine") -> tuple[tuple[float, float, float], ...]:
                if affine.matrix is None:
                    raise Tool.Missing("회차 문서 affine.matrix 미티칭")
                return affine.matrix

            def to_robot(self, affine: "Config.Dataset.EraValues.Affine", x_mm: float, y_mm: float) -> tuple[float, float]:
                """상면 mm 좌표를 로봇 기저 좌표로 보낸다."""
                affine_matrix = self._require_matrix(affine)
                return (
                    affine_matrix[0][0] * x_mm + affine_matrix[0][1] * y_mm + affine_matrix[0][2],
                    affine_matrix[1][0] * x_mm + affine_matrix[1][1] * y_mm + affine_matrix[1][2],
                )

            def to_world(self, affine: "Config.Dataset.EraValues.Affine", x_mm: float, y_mm: float) -> tuple[float, float]:
                """로봇 기저 좌표를 상면 mm 좌표로 되돌린다(`Config.Dataset.EraValues.Affine.inv_matrix`)."""
                inverse = affine.inv_matrix
                return (
                    inverse[0][0] * x_mm + inverse[0][1] * y_mm + inverse[0][2],
                    inverse[1][0] * x_mm + inverse[1][1] * y_mm + inverse[1][2],
                )

            def to_robot_deg(self, affine: "Config.Dataset.EraValues.Affine", angle_deg: float) -> float:
                """상면 mm 평면에서 잰 방위를 로봇 기저 방위로 보낸다.

                두 좌표계의 방위 차(`Affine.rotation_deg`)를 더한다.
                두 평면이 거울상이면(`Affine.is_mirrored`) 상면 mm 의 방위가 로봇 기저에서 거꾸로 돈다.
                """
                sign = -1.0 if affine.is_mirrored else 1.0
                return sign * angle_deg + affine.rotation_deg

            def is_residual_accepted(self, residual_max_mm: float) -> bool:
                """재투영 최대 잔차가 채택 기준 안인가."""
                return residual_max_mm <= self.max_residual_tol__mm

            # ------------------------------------------- 대응점에서 푸는 쪽

            #: 한 줄에 미지수가 셋(`a`, `b`, 평행이동)이라 대응점이 셋은 있어야 선다.
            MIN_PAIRS = 3

            @staticmethod
            def _rows(to_world, pairs: tuple) -> tuple[tuple[float, float, float], ...]:
                """대응점의 화소를 상면 mm 로 옮겨 설계행렬의 행으로 세운다. 끝의 1 이 평행이동 열이다."""
                return tuple(to_world(*calibration_pair.pixel_xy) + (1.0,) for calibration_pair in pairs)

            def _require_fit_pairs(self, affine: "Config.Dataset.EraValues.Affine") -> tuple["Tool.JsonNode", ...]:
                if len(affine.fit_pairs) < self.MIN_PAIRS:
                    raise Tool.Missing(f"아핀 대응점이 {len(affine.fit_pairs)} 개다 — {self.MIN_PAIRS} 개는 있어야 푼다")
                return affine.fit_pairs

            def design_condition_number(self, affine: "Config.Dataset.EraValues.Affine", to_world) -> float:
                r"""적합 대응점이 세우는 설계행렬의 등방 정규화 조건수 $\kappa$ 다. 1 이 가장 좋고 한 직선 위면 무한대다.

                대응점이 한 줄로 늘어서면 그 줄에 수직인 방향의 사상이 거의 정해지지 않는데, 적합 잔차는 작게 나와 잔차로는 안 보인다.
                무게중심으로 옮기고 평균 거리를 $\sqrt{2}$ 로 맞춘 뒤 잰다 — 원점 위치와 좌표 크기가 지워지고 배치의 모양만 남는다.
                정규화가 크기를 지우므로 한 곳에 몰린 것은 못 본다 — 보는 것은 방향에 따른 퍼짐의 치우침이다.

                정규화한 점은 합이 0 이라 $A^{T}A$ 가 대응점 수 $K$ 와 $2 \times 2$ 블록 $S$ 로 갈리고, 평균 거리 $\sqrt{2}$ 가 $\operatorname{tr} S = 2K$ 를 준다.
                $$d = \sqrt{\left(\frac{S_{xx} - S_{yy}}{2}\right)^2 + S_{xy}^2}, \quad \kappa = \sqrt{\frac{K + d}{K - d}}$$
                """
                points_mm = [row[:2] for row in self._rows(to_world, self._require_fit_pairs(affine))]
                count = len(points_mm)
                xs_mm, ys_mm = zip(*points_mm)
                center_x, center_y = sum(xs_mm) / count, sum(ys_mm) / count
                centered = [(x_mm - center_x, y_mm - center_y) for x_mm, y_mm in points_mm]
                rms = math.sqrt(sum(offset_x * offset_x + offset_y * offset_y for offset_x, offset_y in centered) / count)
                if rms == 0.0: return math.inf  # 대응점이 전부 한 자리다
                scale = math.sqrt(2.0) / rms
                s_xx = sum((offset_x * scale) ** 2 for offset_x, _ in centered)
                s_yy = sum((offset_y * scale) ** 2 for _, offset_y in centered)
                s_xy = sum(offset_x * offset_y * scale * scale for offset_x, offset_y in centered)
                spread = math.hypot((s_xx - s_yy) / 2.0, s_xy)
                if spread >= count: return math.inf  # 한 직선 위다
                return math.sqrt((count + spread) / (count - spread))

            def fitted(self, affine: "Config.Dataset.EraValues.Affine", to_world) -> tuple[tuple[float, float, float], ...]:
                """적합 대응점으로 2x3 을 푼다.

                **화소를 상면 mm 로 옮기는 일은 받아서 한다.** 대응점이 든 것은 검출 중심의 화소이고 아핀은 상면 mm 에서 출발하므로 사이에 $H_{35}$ 가 낀다.
                그 사슬을 부르는 자리에서 보이게 둔다 — `to_world` 로 H35 의 것을 받는다.
                여기서 형제를 직접 집으면 아핀이 사영을 알게 되고, 축척만 아는 자리에서 풀어 볼 길이 닫힌다.

                **두 줄을 따로 푼다.** 로봇 X 와 Y 는 설계행렬이 같고 관측만 다르다.
                여섯을 한꺼번에 세우면 행렬이 넷 배가 되는데 푸는 것은 같다.
                """
                pairs = self._require_fit_pairs(affine)
                design_rows = self._rows(to_world, pairs)
                return tuple(
                    Tool.Fit.LeastSquares.solve(
                        design_rows, tuple(pair.robot_xy__mm[axis] for pair in pairs)
                    )
                    for axis in (0, 1)
                )

            def drift_fitted(self, to_world, moves: Sequence["Config.VisionAlgorithm.AffineTransform.Move"]) -> "Config.VisionAlgorithm.AffineTransform.DriftFit":
                r"""선형 부분 $A$ 와, 놓을 때마다 블록이 패드 밑에서 밀리는 양 $\mathbf{s}$ 를 함께 푼다.

                이웃한 두 관측 사이에 블록이 움직인 양은 패드가 다시 문 자리에서 다음에 놓은 자리까지 움직인 양에 한 번 몫의 밀림을 더한 것이다 ::
                $A(\mathbf{u}_k - \mathbf{u}_{k-1}) - \mathbf{s} = \mathbf{p}_k - \mathbf{g}_{k-1}$ ($\mathbf{u}$ 본 자리 상면 mm · $\mathbf{p}$ 놓은 자리 · $\mathbf{g}$ 다시 문 자리).
                블록이 패드 밑 어디에 물렸든 둘이 함께 움직이므로, 다시 문 자리가 블록 중심을 얼마나 빗나갔는지는 식에서 지워진다 — `fitted` 의 대응점은 그것을 다 지닌다.

                `moves` 는 쓸 만했던 관측을 놓은 차례로 늘어놓은 것이다. 차례(`Move.order`)가 이어진 이웃끼리만 식을 세운다.
                손목 방위가 같은 이웃끼리만 식을 세운다. 방위가 바뀌면 패드에서 어긋난 블록 중심이 손목 축을 돌아 옮겨 간다. 밀림은 방위마다 따로 둔다.
                이동 성분은 이 식에 없다 — `pivoted` 가 반 바퀴 관측으로 낸다.
                """
                moves = tuple(moves)
                seen_mm = [to_world(*move.pixel_xy) for move in moves]
                steps = [(previous, current, before, after)
                         for previous, current, before, after in zip(moves, moves[1:], seen_mm, seen_mm[1:])
                         if current.order == previous.order + 1 and previous.turn_deg == current.turn_deg]
                turns = sorted({current.turn_deg for _, current, _, _ in steps})
                rows = tuple((after[0] - before[0], after[1] - before[1]) + tuple(-1.0 if turn == current.turn_deg else 0.0 for turn in turns)
                             for _, current, before, after in steps)
                moved = tuple(tuple(current.placed_xy_mm[axis] - previous.grabbed_xy_mm[axis] for previous, current, _, _ in steps) for axis in (0, 1))
                solved = tuple(Tool.Fit.LeastSquares.solve(rows, moved[axis]) for axis in (0, 1))
                left = tuple(Tool.Fit.LeastSquares.residuals(rows, moved[axis], solved[axis]) for axis in (0, 1))
                return self.DriftFit(linear=((solved[0][0], solved[0][1]), (solved[1][0], solved[1][1])),
                                     drift_mm={turn: (solved[0][2 + index], solved[1][2 + index]) for index, turn in enumerate(turns)},
                                     residuals_mm=tuple(math.hypot(error_x, error_y) for error_x, error_y in zip(*left)))

            def residuals_mm(self, matrix: tuple[tuple[float, float, float], ...], to_world, pairs: tuple) -> tuple[float, ...]:
                """대응점마다 남은 재투영 거리. `is_residual_accepted` 가 받을 값의 출처다.

                **축마다 따로 내지 않고 평면 거리로 낸다.** 로봇이 빗나가는 것은 두 축이 합쳐진 결과이고, 사람이 자로 잴 수 있는 것도 그 거리다.

                받은 행렬로 잰다 — 방금 푼 것을 정본에 적기 전에 봐야 하고, 적합 대응점과 홀드아웃을 같은 잣대로 재야 과적합이 드러난다.
                """
                design_rows = self._rows(to_world, pairs)
                per_axis = tuple(
                    Tool.Fit.LeastSquares.residuals(
                        design_rows, tuple(pair.robot_xy__mm[axis] for pair in pairs), matrix[axis]
                    )
                    for axis in (0, 1)
                )
                return tuple(math.hypot(error_x, error_y) for error_x, error_y in zip(*per_axis))

            # ------------------------------------------- 이동 성분을 다시 내는 쪽

            @staticmethod
            def _require_pivot(affine: "Config.Dataset.EraValues.Affine") -> "Tool.JsonNode":
                if affine.get("pivot") is None:
                    raise Tool.Missing("이동 성분 관측이 없다 — 준비 탭 ④")
                return affine.pivot

            def pivot_center_mm(self, affine: "Config.Dataset.EraValues.Affine", to_world) -> tuple[float, float]:
                """손목 축이 선 지령 자리의 상면 mm. 두 검출 중심을 상면 mm 로 옮긴 가운데다."""
                (first_x, first_y), (second_x, second_y) = (to_world(*pixel) for pixel in self._require_pivot(affine).pixel_xy)
                return ((first_x + second_x) / 2.0, (first_y + second_y) / 2.0)

            def pivot_offset_mm(self, affine: "Config.Dataset.EraValues.Affine", to_world) -> tuple[float, float]:
                """처음 놓은 블록 중심이 손목 축에서 어긋난 양, 상면 mm. 두 검출 차의 절반이다."""
                (first_x, first_y), (second_x, second_y) = (to_world(*pixel) for pixel in self._require_pivot(affine).pixel_xy)
                return ((first_x - second_x) / 2.0, (first_y - second_y) / 2.0)

            def pivoted(self, affine: "Config.Dataset.EraValues.Affine", matrix: tuple[tuple[float, float, float], ...], to_world) -> tuple[tuple[float, float, float], ...]:
                r"""받은 행렬의 이동 성분을 이동 성분 관측으로 다시 낸다. 선형 부분 $A$ 는 그대로 둔다 :: $t = r - A u$.

                $u$ 는 손목 축이 선 지령 자리의 상면 mm(`pivot_center_mm`), $r$ 은 그 로봇 지령 좌표다.
                대응점은 처음 문 어긋남을 다 같이 지닌다. 상면 mm 에서 모든 대응점에 같은 차이가 붙으면 그 차이는 아핀의 이동 성분으로만 흡수된다 — 그래서 선형 부분은 대응점이 낸 것을 쓰고 이동 성분만 갈아 낀다.
                """
                center_x_mm, center_y_mm = self.pivot_center_mm(affine, to_world)
                return tuple(
                    (row[0], row[1], target_mm - row[0] * center_x_mm - row[1] * center_y_mm)
                    for row, target_mm in zip(matrix, self._require_pivot(affine).robot_xy__mm)
                )

        class Calc(Tool.JsonNode):
            """`calc` 구획 — `vis_alg_core.Calc` 가 고른 전처리 경로(`route`)를 든다."""

            class Route(Tool.JsonNode):
                """`Calc` 가 고른 전처리 경로의 이름(`calc.route`). 이름을 부품으로 옮기는 일은 `vis_alg_core.Calc.Pre.Route` 가 한다.

                `channel` :: `색공간.성분`
                `silhouette` :: 실루엣 문턱
                `topface` :: 상면 문턱
                """

        # ------------------------------------------------ 넣어 받는 값

        product: "Config.Product"  # 자재 규격(`product.json`) — 영상 계산의 자다

        # ---------------------------------------------------- 사영과 면내 축척

        @cached_property
        def plane_z_mm(self) -> float:
            """사영 평면의 고도. 블록 상면이 이루는 수평면이다."""
            return self.product.dimensions.height__mm

        @staticmethod
        def _require_work_area_px(work_area: "Config.Dataset.EraValues.WorkArea") -> tuple[tuple[float, float], ...]:
            if work_area.polygon__px is None:
                raise Tool.Missing("회차 문서 work_area.polygon__px 미기입 — 작업영역을 찍어 입력한다")
            return work_area.polygon__px

        def is_projection_sane(self, h35: "Config.Dataset.EraValues.Homography", work_area: "Config.Dataset.EraValues.WorkArea", u_px: float, v_px: float) -> bool:
            """화소 `(u_px, v_px)` 를 상면 mm 로 보내도 되는가.

            사영 분모가 0 에서 떨어져 있고 부호가 작업영역 중심과 같아야 한다.
            부호가 다르면 소실선 너머라 좌표가 뒤집힌다.
            """
            here = self.homography.denominator_at(h35, u_px, v_px)
            return abs(here) > Config.VisionAlgorithm.EPS and (here > 0.0) == (self.homography.denominator_at(h35, *work_area.center_px) > 0.0)

        def rectify_matrix(self, h35: "Config.Dataset.EraValues.Homography", work_area: "Config.Dataset.EraValues.WorkArea", image_w_px: int, image_h_px: int) -> tuple[tuple[float, float, float], ...]:
            r"""원본 화소를 상면을 위에서 편 그림의 화소로 보내는 3x3 이다. $M = S \cdot H_{35}$.

            편 그림은 `cv2.warpPerspective(image, M, (image_w_px, image_h_px))` 로 내고, 크기는 원본과 같게 준다.
            범위는 작업영역 꼭짓점을 상면 mm 로 옮긴 외접 사각형에 `WorkArea.margin_mm` 만큼 여백을 두른 것이라, 작업영역을 다시 찍으면 따라 바뀐다.
            축척은 가로 세로 하나로 넘치지 않는 쪽에 맞춘다 — 편 그림에서 1 mm 는 어느 방향이든 같은 화소 수다.
            $$s = \min\left(\frac{W}{X_1 - X_0}, \frac{H}{Y_1 - Y_0}\right), \quad S = \begin{bmatrix} s & 0 & -X_0 s \\ 0 & s & -Y_0 s \\ 0 & 0 & 1 \end{bmatrix}$$
            """
            corners_mm = [self.homography.to_world(h35, u_px, v_px) for u_px, v_px in self._require_work_area_px(work_area)]
            margin_mm = self.work_area.margin_mm(width_mm=self.product.dimensions.width__mm)
            xs_mm, ys_mm = zip(*corners_mm)
            left_mm, right_mm = min(xs_mm) - margin_mm, max(xs_mm) + margin_mm
            top_mm, bottom_mm = min(ys_mm) - margin_mm, max(ys_mm) + margin_mm
            scale = min(image_w_px / (right_mm - left_mm), image_h_px / (bottom_mm - top_mm))
            window = ((scale, 0.0, -left_mm * scale), (0.0, scale, -top_mm * scale), (0.0, 0.0, 1.0))
            matrix = h35.matrix
            return tuple(tuple(sum(window[row_index][k_index] * matrix[k_index][column_index] for k_index in range(3))
                               for column_index in range(3)) for row_index in range(3))

        # =================================================================
        # 파사드
        # =================================================================

        # ------------------------------------------------- 광학 및 작업영역

        def facade_ppm_vertical_at(self, h35: "Config.Dataset.EraValues.Homography", u_px: float, v_px: float) -> float:
            """수직 축척."""
            return self.homography.ppm_vertical_at(h35, u_px, v_px, height_mm=self.product.dimensions.height__mm)

        def facade_crop_margin_px(self, ppm: float) -> int:
            """작업영역 크롭 여백."""
            return self.work_area.crop_margin_px(ppm, width_mm=self.product.dimensions.width__mm)

        def facade_seed_area_min_px2(self, ppm: float) -> float:
            """씨앗 최소 화소 면적."""
            return self.work_area.seed_area_min_px2(
                ppm, width_mm=self.product.dimensions.width__mm,
                length_min_mm=self.product.length_min_mm,
            )

        def facade_changed_pixels_min(self, perimeter_sum_px: float, ppm: float) -> float:
            """움직임 화소 문턱. 안정화 시점 덩어리가 없으면 최소 규격 하나의 둘레를 바닥값으로 쓴다."""
            if perimeter_sum_px <= 0.0: perimeter_sum_px = 2.0 * (self.product.dimensions.width__mm + self.product.length_min_mm) * ppm
            return self.motion_detect.changed_pixels_min(perimeter_sum_px)

        # ------------------------------------------------- 전처리 및 분할

        def facade_window_kernel_px(self, ppm: float) -> int:
            """국소 분할 윈도우."""
            return self.preprocess.window_kernel_px(ppm, width_mm=self.product.dimensions.width__mm)

        def facade_depth_min_px(self, ppm: float) -> float:
            """결함 최소 깊이."""
            return self.segmentation.depth_min_px(
                ppm, notch_depth_mm=self.product.nominal_block.notch_depth_mm,
            )

        def facade_block_count(self, area_world_mm2: float) -> int:
            """군집의 추정 블록 수."""
            return self.segmentation.block_count(
                area_world_mm2, block_area_mean_mm2=self.product.block_area_mean_mm2,
            )

        def facade_cut_count(self, area_world_mm2: float) -> int:
            """군집을 낱개로 가르는 데 채택할 절단선 수. 블록 수보다 하나 적다."""
            return self.facade_block_count(area_world_mm2) - 1

        # ------------------------------------------------- 적합 및 규격

        @cached_property
        def facade_rect_fit_area_min_mm2(self) -> float:
            """적합기 입력 최소 상면 면적."""
            return self.rect_fit.area_min_mm2(
                width_mm=self.product.dimensions.width__mm, length_min_mm=self.product.length_min_mm,
            )

        @cached_property
        def facade_spec_error_limit_mm(self) -> float:
            """측정 장축의 규격 인정 허용 편차."""
            return self.segmentation.spec_error_limit_mm(fillet_r_mm=self.product.dimensions.fillet_r__mm)

        def facade_spec_length_error_mm(self, observed_mm: float) -> float:
            """관측 장축이 가장 가까운 공칭 규격에서 벗어난 거리."""
            return min(abs(observed_mm - nominal) for nominal in self.product.lengths_mm)

        def facade_is_spec_length(self, observed_mm: float) -> bool:
            """관측 장축이 공칭 규격 중 하나로 인정되는가."""
            return self.facade_spec_length_error_mm(observed_mm) <= self.facade_spec_error_limit_mm

        # ------------------------------------------------- 라벨 및 충실도

        def facade_is_intruded(self, overlap_ratio: float, ppm: float) -> bool:
            """두 사각이 겹쳤는가."""
            return self.label_audit.is_intruded(overlap_ratio, ppm, width_mm=self.product.dimensions.width__mm)

        def facade_is_label_aspect_agreed(self, aspect_observed: float, length_model_mm: float) -> bool:
            """라벨 제안의 종횡비 교차 검증."""
            return self.label_assist.is_aspect_agreed(
                aspect_observed,
                length_model_mm,
                width_mm=self.product.dimensions.width__mm,
                aspect_ratios_nominal=self.product.aspect_ratios_nominal,
            )

        def facade_is_label_fill_accepted(self, fill_ratio: float) -> bool:
            """라벨 제안의 직사각형 충실도 판정."""
            return self.label_assist.is_fill_accepted(fill_ratio)

        def facade_rectangularity_expected(self, ppm: float) -> float:
            """단일 블록을 관측했을 때 기대되는 직사각형 충실도.

            제품의 이론값에 원근 투영 · 모폴로지 · 화소 양자화가 남기는 비율을 곱한다. 양자화 손실은 최소 단품 기준으로 가장 불리하게 센다.
            """
            return (
                self.product.nominal_block.rectangularity_ideal
                * self.homography.perspective_rectangularity_factor
                * self.preprocess.morph_area_factor
                * (
                    1.0
                    - self.quantization.area_loss_ratio(
                        ppm, width_mm=self.product.dimensions.width__mm,
                        length_mm=self.product.length_min_mm,
                    )
                )
            )


    # ------------------------------------------------------------------
    # 2-4. 기구 모션
    # ------------------------------------------------------------------

    class Robot(Tool.JsonNode):
        r"""로봇 실체가 직접 받거나 내보내는 물리 지령값 — `robot.json` 을 읽은 그대로 들고, 부르는 이름은 그 키 경로다(`robot.motion.heights.z_safe.z__mm`).

        손목 각도는 비전 평면과 로봇 기저의 방위 차를 알아야 풀리므로 `Config.VisionAlgorithm` 한 벌을 넣어 받는다(`vision_algorithm`).
        아핀 행렬은 회차 값이라 받아서 쓴다(`Config.Dataset.EraValues.Affine`).
        `arm` 은 로봇 팔 자체가 닿는 범위다 — 실측 둘레(`reach`)와 함께 본다.
        """

        #: 영속화 자산 파일 이름(확장자 제외).
        DOCUMENT_STEM = "robot"

        # -------------------------------------------------------- 적재

        @classmethod
        def load(cls, vision_algorithm: "Config.VisionAlgorithm | None" = None) -> "Config.Robot":
            """정본 디렉토리의 `robot.json` 을 읽는다. 영상 규격을 안 주면 정본에서 읽는다."""
            return cls(Config.Document.read(Config.Document.setting_path(cls.DOCUMENT_STEM))[cls.DOCUMENT_STEM], vision_algorithm=vision_algorithm or Config.VisionAlgorithm.load())

        # -------------------------------------------------------- 티칭

        class Teaching:
            """지금 자세를 정본에 담는다.

            **시리얼을 안 탄다.** 워커가 이미 읽어 둔 상태를 쓸 뿐이라 `RobotBus` 밖에 산다 — 워커가 시리얼 하나만 독점한다는 전제를 흐리지 않는다.

            **높이와 자리를 따로 담는다.** 자리는 XY 만 담고 Z 는 높이 표가 든다.
            한 번에 여섯 축을 담으면 그 자리의 Z 가 높이로 굳어, 같은 높이를 쓰는 다른 자리와 갈린다.

            티칭한 값이 코드 바깥에 남는 유일한 길이다 — `robot.json` 을 통째로 읽어 그 항목만 고쳐 그대로 쓴다.
            틀리면 다시 티칭해 쓴다.
            쓰기 주인(`Tool.Writer`)이 부른다 — 화면은 맡기고, 끝난 뒤 돌려준 글을 알리고 정본을 다시 읽는다.
            """

            MUTE = "좌표를 못 읽어 담지 못했다"

            @staticmethod
            def height(key: str, status: "Connect.Device.Robot.Status | None") -> str:
                """지금 Z 를 그 높이 항목에 담는다. `key` 는 정본 키다."""
                if status is None:
                    return Config.Robot.Teaching.MUTE
                z_mm = status.cartesian[2]
                path = Config.Document.setting_path(Config.Robot.DOCUMENT_STEM)
                robot_json = Config.Document.read(path)
                doc = robot_json[Config.Robot.DOCUMENT_STEM]
                doc["motion"]["heights"][key]["z__mm"] = round(z_mm, 3)
                Config.Document.write(path, robot_json)
                return f"{doc['motion']['heights'][key]['label']} 에 Z {z_mm:.3f} 를 담았다"

            @staticmethod
            def place(key: str, status: "Connect.Device.Robot.Status | None") -> str:
                """지금 XY 를 그 자리에 담는다. **Z 는 안 담는다** — 그 자리가 쓰는 높이는 따로 정한다."""
                if status is None:
                    return Config.Robot.Teaching.MUTE
                x_mm, y_mm = status.cartesian[0], status.cartesian[1]
                path = Config.Document.setting_path(Config.Robot.DOCUMENT_STEM)
                robot_json = Config.Document.read(path)
                doc = robot_json[Config.Robot.DOCUMENT_STEM]
                spot = doc["motion"]["positions"][key]
                spot["xy"] = [round(x_mm, 3), round(y_mm, 3)]
                Config.Document.write(path, robot_json)
                return f"{spot['label']} 에 XY ({x_mm:.3f}, {y_mm:.3f}) 를 담았다"

            @staticmethod
            def reach(points_xy_mm: tuple) -> str:
                """가동범위 둘레를 담는다. 네 귀퉁이를 조그로 찍어 만든다."""
                path = Config.Document.setting_path(Config.Robot.DOCUMENT_STEM)
                robot_json = Config.Document.read(path)
                doc = robot_json[Config.Robot.DOCUMENT_STEM]
                doc["reach"]["points_xy__mm"] = [[round(x, 3), round(y, 3)] for x, y in points_xy_mm]
                Config.Document.write(path, robot_json)
                return f"가동범위 {len(points_xy_mm)} 점을 담았다"

        # -------------------------------------------------- 하위 규격

        class Hardware(Tool.JsonNode):
            """기구에 물려 있는 실물 치수.

            `pad_diameter__mm` :: 흡착 패드 외경. 블록 단축과의 간섭 마진을 한정한다
            `conveyor_width__mm` :: 벨트 유효 이송 폭. 최대 규격의 직교 투입을 막는 한계선
            `conveyor_travel__deg` :: 벨트 진행 방향의 로봇 기저 방위. 장축을 이 방위로 놓아야 패시브 얼라인을 지난다
            """

        class Reach(Tool.JsonNode):
            """실물 조그로 잰 도달 가능 평면 둘레.

            픽업 고도에서 유효한 평면 한계선이다. 고도는 `Heights` 가 갖는다.
            `points_xy__mm` :: 로봇 기저 좌표계 다각형 정점
            """

            def contains(self, x_mm: float, y_mm: float) -> bool:
                """점이 둘레 안에 있는가. 수평 레이 캐스팅 교차 횟수의 홀짝으로 판정한다."""
                polygon_points = self.points_xy__mm
                inside = False
                for vertex_index in range(len(polygon_points)):
                    (current_x, current_y), (previous_x, previous_y) = polygon_points[vertex_index], polygon_points[vertex_index - 1]
                    if (current_y > y_mm) != (previous_y > y_mm) and x_mm < (previous_x - current_x) * (y_mm - current_y) / (
                        previous_y - current_y
                    ) + current_x:
                        inside = not inside
                return inside

            def footprint(self, xy_mm: tuple[float, float], block: "Config.Product.Block", theta_deg: float) -> tuple[tuple[float, float], ...]:
                """블록 윗면 네 모서리의 기저 좌표. 중심과 각도가 자국을 정한다.

                각도는 장축의 로봇 기저 방위다. 점대칭 주기만큼 돌린 각도 바닥 자국은 같다.
                """
                rad = math.radians(theta_deg)
                cos, sin = math.cos(rad), math.sin(rad)
                along, across = block.length__mm / 2.0, block.dimensions.width__mm / 2.0
                base_x, base_y = xy_mm
                return tuple(
                    (base_x + local_x * cos - local_y * sin, base_y + local_x * sin + local_y * cos)
                    for local_x, local_y in ((+along, +across), (+along, -across),
                                 (-along, -across), (-along, +across))
                )

            def can_seat(self, xy_mm: tuple[float, float], block: "Config.Product.Block", theta_deg: float) -> bool:
                r"""이 자리에 이 블록을 이 각도로 놓을 수 있는가.

                **네 모서리가 다 둘레 안이어야 한다.**
                중심만 물으면 중심이 둘레에 닿았을 때 모서리는 이미 밖이다.
                물리는 여유가 각도에 따라 연속으로 변하므로 ($\frac{L}{2}|\cos\theta| + \frac{W}{2}|\sin\theta|$) 축에 정렬했다고 보고 한 벌로 물릴 수 없다.

                둘레가 볼록해야 성립한다. 실물 조그로 네 귀퉁이를 찍어 만든 사각이라 그렇다.
                """
                return all(self.contains(footprint_x, footprint_y)
                           for footprint_x, footprint_y in self.footprint(xy_mm, block, theta_deg))

        class Arm(Tool.JsonNode):
            r"""로봇 팔 자체가 닿는 범위 — 링크 길이 · 관절 범위 · 툴 길이(컨트롤러 `$$` 실측).

            공구가 아래를 향한 채(Rx = Ry = 0) 패드 끝이 $(x, y, z)$ 에 서는 관절각을 닫힌 식으로 푼다. 4축은 0 이고 6축은 손목 방위만 돌리므로 자리를 정하는 축은 1 · 2 · 3 · 5 다.
            팔꿈치가 위인 풀이 하나만 쓴다. 각은 홈 자세(관절 모두 0)를 0 으로 둔 기하 각이다 — 1축은 기저 방위, 2 · 3 · 5축은 앞 · 아래로 숙이는 쪽, 4축은 홈 자세에서 기저 X 축 둘레 오른손 방향, 6축은 위에서 보아 반시계가 + 다.
            컨트롤러 각은 기하 각에 `joint_sign` 을 곱한 것이다. 부호를 모르는 축이 있으면 그 축을 쓰는 계산이 `Tool.Missing` 을 낸다.

            1축 둘레로 대칭이라 한 고도에서 닿는 곳은 반경 구간(`radius_bands_mm`)과 1축 방위 범위(`azimuth_range_deg`)로 갈린다 — 기저 둘레 고리 부채꼴이다.
            `d1__mm` :: $29 바닥 ~ 2축 높이
            `a1__mm` :: $30 1축 ~ 2축 수평 거리
            `a2__mm` :: $31 아래팔 — 2축 ~ 3축
            `a3__mm` :: $32 3축 ~ 위팔 축의 높이 차
            `d4__mm` :: $33 위팔 — 3축 ~ 손목 중심
            `l__mm` :: $34 손목 중심 ~ 플랜지 밑면. 컨트롤러가 음수로 적는다 — 플랜지가 손목 중심 아래다
            `joint_range__deg` :: 1 ~ 6 축 (아래, 위) 한계. 컨트롤러 부호
            `joint_sign` :: 1 ~ 6 축 기하 각 → 컨트롤러 각의 부호. 모르면 None
            `tool_z__mm` :: 플랜지 밑면 ~ 패드 끝. 좌표가 패드 끝을 가리킨다(`$50=1`)
            """

            #: 공구를 세운 채 기저 반경 · 높이를 정하는 축 — 2 · 3 · 5 (0 부터 센 차례)
            RADIAL = (1, 2, 4)

            @cached_property
            def forearm_mm(self) -> float:
                """3축 ~ 손목 중심 거리. 위팔 축과 3축의 높이 차까지 든다."""
                return math.hypot(self.a3__mm, self.d4__mm)

            @cached_property
            def forearm_rise_deg(self) -> float:
                """홈 자세에서 3축 → 손목 중심이 수평 위로 든 각."""
                return math.degrees(math.atan2(self.a3__mm, self.d4__mm))

            def wrist_center_mm(self, r_mm: float, z_mm: float) -> tuple[float, float]:
                """패드 끝이 기저 반경 r · 높이 z 일 때 손목 중심의 2축 기준 (앞, 위) 거리. 공구가 아래를 향하므로 손목 중심은 패드 끝 바로 위다."""
                return r_mm - self.a1__mm, z_mm + self.tool_z__mm - self.l__mm - self.d1__mm

            def geometric_deg(self, x_mm: float, y_mm: float, z_mm: float) -> tuple[float, float, float, float, float] | None:
                r"""패드 끝을 공구를 세운 채 $(x, y, z)$ 에 세우는 기하 각 (1 ~ 5축). 팔을 다 펴거나 다 접어도 못 닿으면 `None` 이다.

                2축 · 손목 중심 평면에서 아래팔 $a_2$ 와 위팔 $\ell$ 의 두 마디 팔이다. 손목 중심까지 $D$ 일 때 ::
                $\theta_2 = \operatorname{atan2}(\text{앞}, \text{위}) - \arccos\frac{a_2^2 + D^2 - \ell^2}{2 a_2 D}$ (아래팔이 연직에서 앞으로 기운 각),
                $\theta_3 = \phi - \alpha - \theta_2$ ($\phi$ 홈 자세 위팔 든 각, $\alpha$ 지금 위팔이 수평 위로 든 각),
                $\theta_5 = -(\theta_2 + \theta_3)$ — 공구를 세우려 손목이 위팔의 숙임을 갚는다.
                """
                ahead, up = self.wrist_center_mm(math.hypot(x_mm, y_mm), z_mm)
                reach, upper, fore = math.hypot(ahead, up), self.a2__mm, self.forearm_mm
                if not abs(upper - fore) <= reach <= upper + fore: return None
                #: 코사인 법칙 — 아래팔과 2축 → 손목 중심 선이 이루는 각. 경계에서 부동소수 오차가 정의역을 넘지 않게 자른다
                opening = math.acos(max(-1.0, min(1.0, (upper ** 2 + reach ** 2 - fore ** 2) / (2.0 * upper * reach))))
                lean = math.degrees(math.atan2(ahead, up) - opening)
                elbow_ahead, elbow_up = upper * math.sin(math.radians(lean)), upper * math.cos(math.radians(lean))
                fold = self.forearm_rise_deg - math.degrees(math.atan2(up - elbow_up, ahead - elbow_ahead)) - lean
                return (math.degrees(math.atan2(y_mm, x_mm)), lean, fold, 0.0, -(lean + fold))

            def sign(self, axis: int) -> int:
                """기하 각 → 컨트롤러 각의 부호. 모르면 `Tool.Missing`."""
                if self.joint_sign[axis] is None:
                    raise Tool.Missing(f"robot.arm.joint_sign {axis + 1} 축 미기입 — 상태 보고 `?` 의 관절각으로 읽는다")
                return self.joint_sign[axis]

            def geometric_range_deg(self, axis: int) -> tuple[float, float]:
                """컨트롤러 한계를 기하 각으로 옮긴 범위 (작은 쪽, 큰 쪽)."""
                low, high = (limit * self.sign(axis) for limit in self.joint_range__deg[axis])
                return min(low, high), max(low, high)

            @cached_property
            def azimuth_range_deg(self) -> tuple[float, float]:
                """1축이 닿는 기저 방위 범위 — 기하 각."""
                return self.geometric_range_deg(0)

            def fits_radius(self, r_mm: float, z_mm: float) -> bool:
                """패드 끝이 공구를 세운 채 기저 반경 r · 높이 z 에 설 수 있는가 — `RADIAL` 축만 본다. 1축 방위와 무관하다."""
                angles = self.geometric_deg(r_mm, 0.0, z_mm)
                return angles is not None and all(low <= angles[axis] <= high for axis in self.RADIAL
                                                  for low, high in (self.geometric_range_deg(axis),))

            def reaches(self, x_mm: float, y_mm: float, z_mm: float) -> bool:
                """패드 끝이 공구를 세운 채 $(x, y, z)$ 에 설 수 있는가 — 1축 방위와 `RADIAL` 축이 모두 범위 안인가."""
                low, high = self.azimuth_range_deg
                return low <= math.degrees(math.atan2(y_mm, x_mm)) <= high and self.fits_radius(math.hypot(x_mm, y_mm), z_mm)

            def radius_bands_mm(self, z_mm: float) -> tuple[tuple[float, float], ...]:
                r"""높이 z 에서 공구를 세운 채 닿는 기저 반경 구간들 (안, 밖). 1축 방위와 무관하다.

                구간의 끝은 한계에 선 축이 2축 · 손목 중심 평면 (앞, 위) 에 그리는 원 위에 있다 ::
                - 2축이 한계 $c$ :: 중심 $a_2(\sin c, \cos c)$ · 반지름 $\ell$ — 팔꿈치가 서고 위팔이 돈다
                - 3축이 한계 $c$ :: 중심 2축 · 반지름 $\sqrt{a_2^2 + \ell^2 + 2 a_2 \ell \sin(\phi - c)}$ — 두 마디 사이 각이 선다
                - 5축이 한계 $c$ :: 중심 $\ell(\cos(\phi + c), \sin(\phi + c))$ · 반지름 $a_2$ — 위팔 방위가 선다
                - 다 편 팔 · 다 접은 팔 :: 중심 2축 · 반지름 $a_2 \pm \ell$
                그 높이의 수평선이 원들과 만나는 반경이 후보다. 이웃 후보 사이 가운데가 닿으면(`fits_radius`) 그 사이가 구간이다.
                """
                _, up = self.wrist_center_mm(0.0, z_mm)
                upper, fore, rise = self.a2__mm, self.forearm_mm, self.forearm_rise_deg
                circles = [(0.0, 0.0, upper + fore), (0.0, 0.0, abs(upper - fore))]
                for limit in self.geometric_range_deg(1):
                    circles.append((upper * math.sin(math.radians(limit)), upper * math.cos(math.radians(limit)), fore))
                for limit in self.geometric_range_deg(2):
                    circles.append((0.0, 0.0, math.sqrt(max(0.0, upper ** 2 + fore ** 2 + 2.0 * upper * fore * math.sin(math.radians(rise - limit))))))
                for limit in self.geometric_range_deg(4):
                    circles.append((fore * math.cos(math.radians(rise + limit)), fore * math.sin(math.radians(rise + limit)), upper))
                candidates = {0.0}
                for center_ahead, center_up, circle_radius in circles:
                    if abs(up - center_up) > circle_radius: continue
                    half = math.sqrt(circle_radius ** 2 - (up - center_up) ** 2)
                    candidates.update(r for r in (center_ahead - half + self.a1__mm, center_ahead + half + self.a1__mm) if r > 0.0)
                ordered = sorted(candidates)
                bands: list[list[float]] = []
                for inner, outer in zip(ordered, ordered[1:]):
                    if not self.fits_radius((inner + outer) / 2.0, z_mm): continue
                    if bands and bands[-1][1] == inner:
                        bands[-1][1] = outer
                    else:
                        bands.append([inner, outer])
                return tuple((inner, outer) for inner, outer in bands)

        class Motion(Tool.JsonNode):
            """`motion` 구획 — 높이 · 공압 레벨 · 지령 편차 · 대기 · 아핀 대응점 수집 · 이름 붙은 자리(`positions`).

            `pick_safety_margin__mm` :: 패드가 모서리 필렛 곡면을 침범하지 않게 두는 편측 여유
            `deadband__mm` :: 위치 불감대이자 최소 유효 이동 변위
            `home_lift_speed__mm_min` :: 호밍 전에 안전 고도로 들어올릴 때의 이송률. 사람이 고르는 자리가 아니라 절차가 제 속도를 갖는 것이다 — 화면의 조그 속도와 섞지 않는다
            """

            class Heights(Tool.JsonNode):
                """높이 한 벌 — 티칭으로 담는 높이(이름을 든 것)와 거기서 더하고 빼는 높이 차.

                이름을 든 높이는 사람이 읽는 `label` 과 고도 `z__mm` 을 든 구획이다 — 이것만 담을 수 있고, 높이 차는 이름이 없어 빠진다.
                `z_safe` :: 장애물과 카메라 시야를 피하는 급속 이송 고도
                `z_pick` :: 블록 상면 흡착 기준 고도
                `z_conveyor` :: 벨트 안착 고도
                `z_place` :: 블록을 문 채 매트에 내려놓는 고도. 벨로즈 패드가 진공에 줄어 블록을 들고 있어 픽업 높이보다 아래다. 담기 전에는 `z__mm` 이 null
                `z_conveyor_drop_offset__mm` :: 벨트 충돌을 피해 파기하는 비접촉 여유
                `z_conveyor_pick_press__mm` :: 투입점에서 물 때 컨베이어 접촉 높이보다 더 내려가는 누름 깊이
                `grip_retry_press__mm` :: 붙음을 못 들으면 닿은 자리에서 더 눌러 한 번 더 듣는 깊이
                """

            class PneumaticsPwm(Tool.JsonNode):
                """단일 채널 공압 지령 레벨.

                흡기와 파기가 채널 하나를 공유하므로 상태를 레벨로 가른다.
                `vacuum` :: 진공 흡기 펌프 가동 지령
                `blowoff` :: 압축 공기 파기 밸브 개방 지령
                `idle` :: 솔레노이드 정지 지령
                """

                class State(Enum):
                    """공압 채널의 세 가지 상태."""

                    VACUUM = "흡착"
                    BLOWOFF = "파기"
                    IDLE = "정지"

                def level(self, state: "Config.Robot.Motion.PneumaticsPwm.State") -> int:
                    """상태에 대응하는 지령 레벨."""
                    return {
                        self.State.VACUUM: self.vacuum,
                        self.State.BLOWOFF: self.blowoff,
                        self.State.IDLE: self.idle,
                    }[state]

                def nearest_state(self, measured: float) -> "Config.Robot.Motion.PneumaticsPwm.State":
                    """되읽은 PWM 에 가장 가까운 상태. 드라이버 반올림 편차를 흡수한다."""
                    return min(self.State, key=lambda state: abs(measured - self.level(state)))

            class CommandBias(Tool.JsonNode):
                """절대 지령과 보고 좌표 사이의 계통 차. 직교 세 축의 실측이다.

                **보고 좌표는 지령한 수와 같아지지 않는다.**
                그래서 도착 여부를 같음으로 묻지 않고 `tolerance__mm` 안인지로 묻는다.
                `offset__mm` 은 그 차를 메우려고 보낼 때 더하는 양이며, 움직이지 않는 축에도 얹어야 지령을 낼 때마다 조금씩 밀리지 않는다.

                자세 세 축(A · B · C)의 계통 차는 재지 않았다. 손목 방위(Rz)는 도착만 묻고, 그 허용은 관절 분해능에서 낸다(`wrist_tolerance_deg`).
                `offset__mm` :: 지령에 더한다. 보고가 목표에 닿도록
                `tolerance__mm` :: 이 안이면 도착했다고 본다
                `wrist_joint_resolution__step_per_deg` :: 공구가 아래를 향할 때 Rz 를 돌리는 수직 관절(J1 · J6)의 분해능
                """

                @property
                def wrist_tolerance_deg(self) -> float:
                    """손목 방위의 도착 허용. 관절은 스텝 단위로만 서므로 Rz 보고는 지령과 관절마다 한 스텝까지 어긋날 수 있다 — 그 합이다."""
                    return sum(1.0 / steps_per_deg for steps_per_deg in self.wrist_joint_resolution__step_per_deg)

            class Timings(Tool.JsonNode):
                """공압 시퀀스 대기 시간.

                `vacuum_dwell__s` :: 진공 체결 대기. 흡착을 들을 마이크가 없을 때 닿은 뒤 이만큼 쉰다
                `blowoff_dwell__s` :: 파기 분사 지속. 블록을 놓을 때와 호밍 전에 패드에 붙은 것을 떨굴 때 같다
                `settle_dwell__s` :: 모션 정지 안정화
                `grip_wait__s` :: 닿은 뒤(또는 더 누른 뒤) 붙음을 기다리는 상한
                """

            class Calibration(Tool.JsonNode):
                """아핀 대응점 수집의 규격.

                로봇이 투입점의 블록을 물어 가동범위 안 자리마다 놓고, 투입점으로 대피한 뒤 카메라가 본다. 제자리에서 다시 물어 다음 자리로 간다.
                투입점이 블록의 수급처다 — 비전에 기대지 않는 고정 좌표다.
                `supply_length__mm` :: 투입점에 올려 둔 블록의 규격 길이
                `supply_long_axis__deg` :: 투입점에 올려 둔 블록 장축의 로봇 기저 방위
                `long_axis__deg` :: 들고 다닐 때 장축의 로봇 기저 방위. 손목이 두 방위의 차만큼 돈다
                `grid_rows` :: 격자 행 수 — 가동범위 둘째 변 방향
                `grid_cols` :: 격자 열 수 — 가동범위 첫째 변 방향
                `holdout_uv` :: 적합에 안 쓰는 확인점. 줄인 가동범위 안의 정규화 좌표 (0 – 1)
                `settle__s` :: 대피 뒤 팔 떨림이 가라앉기를 기다리는 시간
                `discard_limit` :: 연속으로 이만큼 관측이 어긋나면 멈춘다
                """

                class Point(NamedTuple):
                    """대응점 수집이 블록을 놓는 자리 하나.

                    첫 단계(`Robot.bootstrap_points`)와 둘째 단계(`Robot.calibration_points`)가 같은 꼴로 낸다.
                    """

                    name: str
                    robot_xy_mm: tuple[float, float]  # 블록을 놓는 로봇 지령 좌표
                    turn_deg: float  # 들고 다니는 방위에서 손목을 더 돌리는 각
                    holdout: bool  # 적합에 쓰지 않고 검증에 쓰는 확인점인가
                    revisit_of: str | None  # 같은 자리에 다시 놓는 것이면 먼저 놓은 자리의 이름. 손목을 더 돌렸으면 이동 성분 관측의 짝이고, 아니면 탈조 확인이다

            class Position(Tool.JsonNode):
                """이름 붙은 한 자리(`positions` 의 항목).

                **XY 만 든다.**
                Z 는 `z` 가 가리키는 높이 항목이 들며, 같은 높이를 여러 자리가 함께 쓴다.
                여기 Z 를 또 적으면 두 벌이 되어 갈라진다.
                `label` :: 사람이 읽는 이름. 화면이 이것을 고르개에 낸다
                `xy` :: 티칭 창에서 담은 XY(mm). 담기 전에는 null
                `z` :: 이 자리의 Z — 그 Z 를 든 높이 항목의 정본 키 경로(`robot.motion.heights.<키>`)
                """

                class Rpy(NamedTuple):
                    """엔드 이펙터 자세. 로봇 기저 축 기준 회전각."""

                    roll_deg: float
                    pitch_deg: float
                    yaw_deg: float

                @cached_property
                def rpy(self) -> "Config.Robot.Motion.Position.Rpy":
                    """엔드 이펙터 자세(`rpy` — roll · pitch · yaw 순서의 목록)."""
                    return self.Rpy(*self.doc["rpy"])

        class Surface(NamedTuple):
            """블록이 놓이는 바닥 한 곳에서 패드 끝이 서는 고도 한 벌 — 매트(`Robot.mat`)와 컨베이어 투입점(`Robot.conveyor`). 물기(`RobotBus._grab`)와 놓기가 이것을 읽는다."""

            vacuum_z_mm: float  # 진공을 켜는 고도. 패드가 블록 윗면에 닿는 고도에서 블록 높이만큼 위다 — 닿기 전에 무부하 회전을 듣는다
            grip_z_mm: float  # 무는 고도
            retry_z_mm: float  # 붙음을 못 들었을 때 더 눌러 한 번 더 듣는 고도
            release_z_mm: float | None  # 놓는 고도. 담기 전에는 None

        class Acoustic(Tool.JsonNode):
            """소리로 흡착 상태를 읽기 위한 공압 음향 규격 — robot.json `acoustic` 을 읽은 그대로 들고, 부르는 이름은 그 키 경로다(`acoustic.pump.strokes_per_rev`).

            **표본율은 여기 없다.**
            장치가 준다 — 배타 모드는 하드웨어 고유 율만 받으므로 고를 수 없다.
            **블록 크기도 없다.**
            응답 요구와 표본율에서 나온다.

            목표를 **무부하 대비 비**로 적는다.
            같은 흡착이라도 밀착이 좋으면 회전이 더 떨어진다 — 손으로 눌러 붙인 것은 8.7%, 로봇이 집어 올린 것은 6.1% 내려갔다.
            비로 적으면 둘 다 0.88~0.94 에 든다.

            관측 목표의 이름은 JSON `pump.targets` 가 정한다 — 코드에 목록을 두지 않는다.

            `pump.targets` :: 관측 목표 이름 → 그 목표를 알아보는 실측 범위. `load_ratio` 는 무부하 대비 회전수 비이고 부하가 걸릴수록 작다
            `pump.unloaded_rotation__hz` :: 부하 없이 돌 때의 축 회전수. 녹음이 달라도 같았다
            `pump.strokes_per_rev` :: 회전당 압축 행정수. 토출 맥동이 회전수의 이 배로 선다
            `supply_power.voltage__v` :: 공급 전원 전압
            `supply_power.frequency__hz` :: 공급 전원 주파수. 이 선이 스펙트럼에 상시 서 있다
            `install.block_samples__exp` :: 블록 표본 수를 2 의 거듭제곱으로 적은 지수. 설치할 때 한 번 잰다
            `settling.answers_per_block` :: 블록 하나가 지나는 동안 답을 몇 번 내나
            `settling.answers_to_change` :: 답 몇 개가 연이어 같아야 상태를 바꾸나
            `equipment_sound.comb__hz` :: 기계 주기성의 세기를 보는 대역
            `equipment_sound.comb_scan__hz` :: 배음 간격을 자기상관으로 훑는 대역
            `capture.exclusive` :: 마이크를 배타 모드로 먼저 열어 본다. 윈도우 공유 믹서가 자동 게인 · 소음 억제로 원 신호를 고치기 때문이다
            `capture.backlog_hops` :: 분석 워커가 못 따라갈 때 쌓아 두는 덩어리 수. 넘치면 버리고 센다
            `capture.block_wait__s` :: 분석 워커가 다음 덩어리를 한 번 기다리는 길이
            `capture.stop_wait__s` :: 마이크를 놓을 때 분석 워커가 서기를 기다리는 상한
            `capture.reader_stop_wait__s` :: 듣기를 멈출 때 판정 워커가 서기를 기다리는 상한
            """

            # ------------------------------------------------- 목표별 조회

            def target(self, name: str) -> "Tool.JsonNode":
                """이름으로 관측 목표를 꺼낸다."""
                if name not in self.pump.targets:
                    raise Tool.Missing(f"robot.acoustic.pump.targets 에 '{name}' 없음")
                return self.pump.targets[name]

            def piston_hz(self, name: str) -> tuple[float, float]:
                """관측 목표의 토출 맥동 대역. 회전수에 행정수를 곱한 것뿐이다."""
                rotation_minimum_hz, rotation_maximum_hz = self.pump.unloaded_rotation__hz
                ratio = self.target(name).load_ratio
                return Tool.Acoustic.piston_band_hz((rotation_minimum_hz * ratio[0], rotation_maximum_hz * ratio[1]), self.pump.strokes_per_rev)

            # ------------------------------------------------- 범위 유도

            @cached_property
            def loaded_target(self) -> str:
                """부하가 걸린 쪽 목표의 이름.

                부하가 걸리면 축이 느려지므로 **부하비가 낮은 쪽**이다.
                이름을 코드에 적지 않고 이렇게 내는 것은, 목표 이름을 정하는 것이 정본이기 때문이다.
                """
                return min(self.pump.targets, key=lambda name: sum(self.target(name).load_ratio))

            @cached_property
            def running_rotation_hz(self) -> tuple[float, float]:
                """어느 목표든 돌고 있다면 회전수가 드는 범위. 무부하 범위에 부하비를 씌운다."""
                rotation_minimum_hz, rotation_maximum_hz = self.pump.unloaded_rotation__hz
                ratios = [self.target(name).load_ratio for name in self.pump.targets]
                return (rotation_minimum_hz * min(ratio[0] for ratio in ratios), rotation_maximum_hz * max(ratio[1] for ratio in ratios))

            @cached_property
            def rotation_search_hz(self) -> tuple[float, float]:
                """배음 간격을 찾을 범위. 가동 회전수 범위에서 나온다.

                자기상관은 참값의 두 배와 반에도 봉우리가 서므로, 범위가 그 둘을 품으면 답이 그리로 빠진다.
                실제로 멀리서 찍은 녹음에서 회전 60 Hz 가 121 Hz 로 읽혔다.

                아래는 **가장 빠른 회전의 반**으로 끊는다 — 그 아래는 전부 반배 별칭이다.
                빗살이 아예 없으면 자기상관이 단조 감소만 해서 답이 이 하한에 붙으므로, 하한에 붙었다는 것이 곧 빗살이 없다는 표시가 된다.

                위는 **가장 느린 회전의 두 배**를 넘으면 안 되고 가장 빠른 회전보다는 높아야 한다.
                그 사이 어디를 잡을지는 고르는 일이라 로그 눈금의 가운데를 잡았다 — 참값을 자르는 쪽과 옥타브를 들이는 쪽에서 똑같이 멀다.
                """
                rotation_minimum_hz, rotation_maximum_hz = self.running_rotation_hz
                return (rotation_maximum_hz / 2.0, math.sqrt(rotation_maximum_hz * rotation_minimum_hz * 2.0))

            # --------------------------------------------- 표본율에 딸린 유도

            @cached_property
            def rotation_precision_hz(self) -> float:
                """회전수 측정이 이보다 잘 떨어야 두 부하 상태가 갈린다.

                두 실측 구름 사이의 빈틈을 절반으로 나눈 값이다 — 각 구름의 반폭이 그보다 크면 둘이 맞닿는다.
                정본의 부하비 두 범위에서 나온다.
                """
                spans = sorted((self.target(target_name).load_ratio for target_name in self.pump.targets), key=lambda span: span[0])
                gap = min(next_span[0] - previous_span[1] for previous_span, next_span in itertools.pairwise(spans))
                return gap * sum(self.pump.unloaded_rotation__hz) / 2.0 / 2.0

            def block_size(self, sample_rate_hz: int) -> int:
                """한 번에 변환할 표본 수.

                `rotation_precision_hz` 를 만족하는 가장 작은 2의 거듭제곱을 실측으로 골라 정본에 적어 두었다.
                흩어짐과 블록 길이의 관계는 신호 대 잡음과 살아남은 배음 수에 달려 닫힌 식이 없고, 배가할 때 어떻게 줄지도 일정하지 않다 — 빗살이 잡히기 시작하는 문턱에서 무너지듯 떨어지고 그 뒤로는 완만하다.
                **후보를 훑어 고르는 수밖에 없다.**

                흩어짐을 정하는 것은 마이크 위치 · 기기 · 배경 소음이고 셋 다 **설치하면 안 바뀐다.**
                그러므로 이 값은 설치할 때 한 번 재는 제원이다.

                표본율이 달라도 같은 표본 수를 쓴다.
                창의 물리적 길이는 달라지나 주파수 칸 폭은 표본율에 비례해 함께 움직이므로, 가려야 할 것을 가르는 능력은 유지된다.

                2 의 거듭제곱으로 적는 것은 푸리에 변환이 그때 가장 빠르기 때문이다.
                물리적인 뜻은 없으므로 지수로 적어 그 사실이 값에 드러나게 했다.
                """
                return 2 ** self.install.block_samples__exp

            def hop_size(self, sample_rate_hz: int) -> int:
                """답과 답 사이 간격. 블록을 이만큼씩 밀며 흘린다."""
                return max(1, self.block_size(sample_rate_hz) // self.settling.answers_per_block)

            def change_time_s(self, sample_rate_hz: int) -> float:
                """상태가 바뀌는 데 걸리는 시간. 답 주기에 필요한 답 수를 곱한 것이다.

                답 주기와 답 수가 따로 적혀 있고 **곱해야 시간이 된다.**
                동작을 정하는 것은 그 시간이다.
                겹침을 바꾸면 답 수도 같이 바꿔야 동작이 유지된다.
                """
                return self.settling.answers_to_change * self.hop_size(sample_rate_hz) / sample_rate_hz

            def hold_s(self, sample_rate_hz: int) -> float:
                """빗살이 끊겨도 기준을 붙들고 있는 시간. 블록 하나 길이로 둔다.

                컴프레셔는 기계 관성이 있어 순간적으로 섰다 돌 수 없다. 실측에서 가동 중 끊김은 길어야
                0.09 초라 블록 하나가 덮는다. 그래서 숫자를 따로 두지 않았다.
                """
                return self.block_size(sample_rate_hz) / sample_rate_hz

        # ------------------------------------------------- 이동 다리

        class Route:
            """어디로 갈 것인가를 푼다. 시리얼을 모른다.

            다리 목록을 내놓을 뿐 보내지 않는다.
            장치 없이 돌려 볼 수 있으므로, 가동범위 판정과 안전 높이 선행이 맞게 걸리는지 로봇 앞에 서기 전에 확인한다.
            보내는 일은 `rbt_alg_core.RobotBus._move` 가 한다.

            **다리는 축을 다 채워서 낸다.**
            절대 이동에서 생략한 축을 이 컨트롤러가 어떻게 다루는지 실물로 확인하지 않았다.
            지금 자리로 채우므로 손목의 기울기(A · B)도 지금 값 그대로 간다.
            """

            class Kind(StrEnum):
                """어느 좌표로 움직이는가. 좌표계가 정해져야 축 번호에 뜻이 생긴다."""

                CART = "cart"            # 직교
                JOINT = "joint"          # 관절

            #: 좌표 방식마다 사람이 읽는 축 이름. 화면과 알림에 쓴다
            AXIS_NAMES = {Kind.CART: ("X", "Y", "Z", "Rx", "Ry", "Rz"), Kind.JOINT: ("J1", "J2", "J3", "J4", "J5", "J6")}

            @staticmethod
            def is_mm_axis(kind: "Config.Robot.Route.Kind", axis: int) -> bool:
                """그 축의 값이 mm 인가. 직교의 앞 세 축(X · Y · Z)만 길이이고 나머지와 관절은 도다."""
                return kind is Config.Robot.Route.Kind.CART and axis < 3

            class Leg(NamedTuple):
                """한 줄로 나가는 이동 하나."""

                axes: tuple[float, ...]   # `command_axes` 순서. 절대면 목표, 상대면 변위
                kind: "Config.Robot.Route.Kind"        # 모드 낱말이 여기서 갈린다
                speed: int                # 이송 속도 (mm/min)
                relative: bool = False    # 참이면 상대로 내고 절대로 되돌린다
                moves: tuple[int, ...] = ()   # 이 다리가 바꾸려는 축 번호. 움직였는지 볼 때 쓴다
                why: str = ""             # 사람에게 할 말

            class Plan(NamedTuple):
                """푼 결과.

                셋 중 하나다 :: 갈 다리가 있거나, 갈 까닭이 없어 비었거나, 못 가거나.
                못 가는 것을 예외가 아니라 값으로 내는 것은 부르는 쪽이 화면이기 때문이다.
                """

                legs: tuple = ()
                refused: str = ""

            robot: "Config.Robot"  # 로봇 규격(`robot.json`) — 불감대(`motion.deadband__mm`)와 지령 편차(`motion.command_bias`)를 여기서 읽는다
            communication: "Config.Communication"  # 통신 규격(`communication.json`) — 명령 낱말(`robot_serial.gcode`)을 여기서 읽는다

            def __init__(self, robot: "Config.Robot", *, communication: "Config.Communication") -> None:
                self.robot = robot
                self.communication = communication

            # ------------------------------------------------------------ 지금 자리

            def at(self, kind: "Config.Robot.Route.Kind",
                   status: "Connect.Device.Robot.Status | None") -> "tuple[float, ...] | None":
                """지금 자리를 `command_axes` 순서로. 못 읽으면 `None`."""
                if status is None:
                    return None
                if kind is self.Kind.CART:
                    seen = status.cartesian
                    return tuple(seen) if len(seen) >= len(self.communication.robot_serial.gcode.command_axes) else None
                seen = status.angles_deg
                slots = self.communication.robot_serial.gcode.angle_slots
                if len(seen) <= max(slots):
                    return None
                return tuple(seen[slot] for slot in slots)

            def _still(self, delta: float) -> bool:
                """움직일 양이 없는가. 불감대는 기구가 실제로 움직이는 최소 변위다."""
                return abs(delta) < self.robot.motion.deadband__mm

            def _arrived(self, axis: int, here: float, goal_mm: float) -> bool:
                """이미 그 자리인가.

                **같음으로 묻지 않는다.**
                보고 좌표가 지령한 수에 정확히 서지 않으므로 (`Config.Robot.Motion.CommandBias`), 같음으로 물으면 절대 이동이 영원히 끝나지 않는다.
                """
                return abs(here - goal_mm) < self.robot.motion.command_bias.tolerance__mm[axis]

            def _turned(self, here_deg: float, goal_deg: float) -> bool:
                """손목이 이미 그 방위인가 — 도착 허용(`CommandBias.wrist_tolerance_deg`) 안인가. −180 과 180 은 같은 방위다."""
                return abs(Tool.wrap180(here_deg - goal_deg)) < self.robot.motion.command_bias.wrist_tolerance_deg

            def _sent(self, here: tuple) -> list:
                """지금 자리를 그대로 지키는 지령값.
                보정을 얹어야 제자리에 선다 — 얹지 않고 보고값을 그대로 다시 보내면 지령을 낼 때마다 편차만큼 밀린다.
                """
                offsets = self.robot.motion.command_bias.offset__mm
                return [value + (offsets[n] if n < len(offsets) else 0.0)
                        for n, value in enumerate(here)]

            def missed(self, leg: "Config.Robot.Route.Leg", status: "Connect.Device.Robot.Status | None") -> tuple[int, ...]:
                """절대 직교 다리가 바꾸려던 축 가운데 목표 허용 밖에 선 축. X · Y · Z 는 `CommandBias.tolerance__mm`, 손목은 `CommandBias.wrist_tolerance_deg` 로 묻는다. 상대 · 관절 다리는 묻지 않는다.

                접수 응답과 정지만으로는 갔는지 모른다 — 컨트롤러가 지령을 받고도 안 움직일 때가 있다.
                """
                here = self.at(leg.kind, status)
                if leg.relative or leg.kind is not self.Kind.CART or here is None:
                    return ()
                offsets = self.robot.motion.command_bias.offset__mm

                def off(axis: int) -> bool:
                    if axis == self.WRIST:
                        return not self._turned(here[axis], leg.axes[axis])
                    return axis < len(self.robot.motion.command_bias.tolerance__mm) and not self._arrived(axis, here[axis], leg.axes[axis] - offsets[axis])

                return tuple(axis for axis in leg.moves if off(axis))

            def aimed(self, axis: int, goal_mm: float) -> float:
                """보고 좌표계의 목표를 지령값으로 옮긴다."""
                offsets = self.robot.motion.command_bias.offset__mm
                return goal_mm + (offsets[axis] if axis < len(offsets) else 0.0)

            # ------------------------------------------------------------ 푸는 것 셋

            def step(self, kind: "Config.Robot.Route.Kind", axis: int, delta: float, speed: int) -> "Config.Robot.Route.Plan":
                """한 축을 상대로 한 걸음. 지금 자리를 몰라도 낼 수 있는 유일한 이동이다."""
                if self._still(delta):
                    return self.Plan()
                moved = [0.0] * len(self.communication.robot_serial.gcode.command_axes)
                moved[axis] = delta
                return self.Plan((self.Leg(tuple(moved), kind, speed, relative=True,
                                           moves=(axis,), why="한 걸음 민다"),))

            #: 손목 회전이 놓인 명령 축 번호.
            #: 직교 여섯은 (X · Y · Z · Rx · Ry · Rz) 이고 블록을 돌리는 것은 마지막 하나다
            WRIST = 5

            def turn(self, wrist_deg: float, speed: int,
                     status: "Connect.Device.Robot.Status | None") -> "Config.Robot.Route.Plan":
                """손목만 돌린다. 자리는 그대로 둔다 — 내려가기 전에 자세를 맞춘다."""
                here = self.at(self.Kind.CART, status)
                if here is None:
                    return self.Plan(refused="지금 좌표를 읽지 못했다")
                if self._turned(here[self.WRIST], wrist_deg):
                    return self.Plan()
                goal = self._sent(here)
                goal[self.WRIST] = wrist_deg
                return self.Plan((self.Leg(tuple(goal), self.Kind.CART, speed,
                                           moves=(self.WRIST,), why=f"손목 {wrist_deg:.2f}도 로"),))

            def height(self, z_mm: float, speed: int,
                       status: "Connect.Device.Robot.Status | None") -> "Config.Robot.Route.Plan":
                """XY 와 자세를 둔 채 Z 만. 목표 고도는 부르는 쪽이 정본에서 꺼내 온다."""
                here = self.at(self.Kind.CART, status)
                if here is None:
                    return self.Plan(refused="지금 좌표를 읽지 못했다")
                if self._arrived(2, here[2], z_mm):
                    return self.Plan()
                goal = self._sent(here)
                goal[2] = self.aimed(2, z_mm)
                return self.Plan((self.Leg(tuple(goal), self.Kind.CART, speed,
                                           moves=(2,), why=f"높이 {z_mm:.2f} 로"),))

            def height_turned(self, z_mm: float, wrist_deg: float, speed: int,
                              status: "Connect.Device.Robot.Status | None") -> "Config.Robot.Route.Plan":
                """XY 를 둔 채 Z 와 손목을 한 다리로 함께 옮긴다 — 돌리는 동안 오르내린다. 손목을 따로 돌리고 오르내리는 것보다 짧다."""
                here = self.at(self.Kind.CART, status)
                if here is None:
                    return self.Plan(refused="지금 좌표를 읽지 못했다")
                moves = tuple(axis for axis, moving in ((2, not self._arrived(2, here[2], z_mm)),
                                                        (self.WRIST, not self._turned(here[self.WRIST], wrist_deg))) if moving)
                if not moves:
                    return self.Plan()
                goal = self._sent(here)
                goal[2] = self.aimed(2, z_mm)
                goal[self.WRIST] = wrist_deg
                return self.Plan((self.Leg(tuple(goal), self.Kind.CART, speed, moves=moves,
                                           why=f"높이 {z_mm:.2f} · 손목 {wrist_deg:.2f}도 로"),))

            def plane(self, xy_mm: tuple[float, float], speed: int,
                      status: "Connect.Device.Robot.Status | None",
                      z_safe_mm: float) -> "Config.Robot.Route.Plan":
                """안전 고도 평면에서 XY 만. **내려오지 않는다** — 촬영 대피가 이것을 쓴다."""
                return self._cross(xy_mm, None, speed, status, z_safe_mm)

            def travel(self, xy_mm: tuple[float, float], z_mm: float, speed: int,
                       status: "Connect.Device.Robot.Status | None",
                       z_safe_mm: float) -> "Config.Robot.Route.Plan":
                """올라가고 · 가로지르고 · 내려간다."""
                return self._cross(xy_mm, z_mm, speed, status, z_safe_mm)

            def _cross(self, xy_mm: tuple[float, float], z_mm: "float | None", speed: int,
                       status: "Connect.Device.Robot.Status | None",
                       z_safe_mm: float) -> "Config.Robot.Route.Plan":
                """자리를 옮기는 한 계획.

                **XYZ 를 직선으로 한 번에 가지 않는다.**
                대각선으로 내려가면 경로 한가운데가 어디를 지나는지 사람이 못 읽는다.
                올라가고 · 가로지르고 · 내려가는 셋으로 나눈다.
                그래서 가로지르는 동안 늘 안전 고도이고, 걸릴 데가 없다.

                **여기서 가동범위를 보지 않는다.**
                `Config.Robot.Reach` 의 둘레는 블록을 무는 자리의 한계이고, 투입점은 그 밖에 있다.
                여기서 막으면 대피도 배출도 못 간다.
                """
                here = self.at(self.Kind.CART, status)
                if here is None:
                    return self.Plan(refused="지금 좌표를 읽지 못했다")

                legs, goal, standing = [], self._sent(here), here[2]
                if here[2] < z_safe_mm and not self._arrived(2, here[2], z_safe_mm):
                    goal[2], standing = self.aimed(2, z_safe_mm), z_safe_mm
                    legs.append(self.Leg(tuple(goal), self.Kind.CART, speed,
                                         moves=(2,), why="안전 고도로 먼저 올린다"))
                if not (self._arrived(0, here[0], xy_mm[0]) and self._arrived(1, here[1], xy_mm[1])):
                    goal[0], goal[1] = self.aimed(0, xy_mm[0]), self.aimed(1, xy_mm[1])
                    legs.append(self.Leg(tuple(goal), self.Kind.CART, speed,
                                         moves=(0, 1), why=f"({xy_mm[0]:.2f}, {xy_mm[1]:.2f}) 로"))
                if z_mm is not None and not self._arrived(2, standing, z_mm):
                    goal[2] = self.aimed(2, z_mm)
                    legs.append(self.Leg(tuple(goal), self.Kind.CART, speed,
                                         moves=(2,), why=f"높이 {z_mm:.2f} 로"))
                return self.Plan(tuple(legs))

        # ------------------------------------------------ 넣어 받는 값

        vision_algorithm: "Config.VisionAlgorithm"  # 아핀 계산과 자재 규격을 공급한다

        # -------------------------------------------------------- 적재

        # ------------------------------------------------- 흡착 기하

        def seat_width_mm(self, block: "Config.Product.Block") -> float:
            r"""그 규격의 패드가 안착할 수 있는 상면 평탄부 폭.

            $W - 2r - 2m_{safe}$. 단축에서 양쪽 필렛을 빼고 안전 여유를 다시 뺀다.
            필렛 반경은 규격마다 다르므로 집을 블록의 값을 쓴다.
            """
            return block.dimensions.width__mm - 2.0 * block.fillet_r_mm - 2.0 * self.motion.pick_safety_margin__mm

        def tol_pick_center_mm(self, block: "Config.Product.Block") -> float:
            """비전이 낸 중심이 벗어나도 되는 한계.

            평탄부에 패드를 얹고 남는 편측 여유다.
            이보다 크게 빗나가면 패드가 모서리 필렛 곡면으로 넘어가 진공이 샌다.
            비전 정밀도 요구의 근거가 되는 수치다.
            """
            return (self.seat_width_mm(block) - self.hardware.pad_diameter__mm) / 2.0

        # ------------------------------------------------- 대응점 수집

        #: 반 바퀴. 가운데 자리에 두 번째로 놓을 때 손목을 이만큼 더 돌리면 두 관측이 손목 축에 대해 점대칭이 된다(`Config.Dataset.EraValues.Affine` 의 `pivot`)
        HALF_TURN_DEG = 180.0

        def bootstrap_points(self, block: "Config.Product.Block") -> tuple["Config.Robot.Motion.Calibration.Point", ...]:
            """대응점 수집의 첫 단계 자리(`Calibration.Point`).

            가동범위 꼭짓점의 무게중심과, 거기서 X · Y 로 블록 단변만큼 옮긴 두 자리다.

            카메라 작업영역이 로봇 좌표의 어디인지 아직 모르므로 그 안일 가능성이 가장 높은 가운데에서 시작한다. 단변만큼 옮겨도 작업영역 안이다.
            세 관측이 대략의 아핀을 내고, 그것으로 둘째 단계의 자리를 작업영역과 견주어 정한다(`calibration_points`).
            가운데에는 손목을 반 바퀴 더 돌려 한 번 더 놓는다 — 두 관측의 가운데가 지령 자리라 행렬의 이동 성분을 낸다(`Config.Dataset.EraValues.Affine` 의 `pivot`).
            """
            corners = self.reach.points_xy__mm
            center = (sum(x_mm for x_mm, _ in corners) / len(corners), sum(y_mm for _, y_mm in corners) / len(corners))
            step_mm = block.dimensions.width__mm
            placed = (self.Motion.Calibration.Point("c", center, 0.0, holdout=False, revisit_of=None),
                      self.Motion.Calibration.Point("c180", center, self.HALF_TURN_DEG, holdout=False, revisit_of="c"),
                      self.Motion.Calibration.Point("cx", (center[0] + step_mm, center[1]), 0.0, holdout=False, revisit_of=None),
                      self.Motion.Calibration.Point("cy", (center[0], center[1] + step_mm), 0.0, holdout=False, revisit_of=None))
            for point in placed:
                x_mm, y_mm = point.robot_xy_mm
                if not self.reach.can_seat(point.robot_xy_mm, block, self.motion.calibration.long_axis__deg):
                    raise Tool.Missing(f"대응점 {point.name} ({x_mm:.1f}, {y_mm:.1f}) 에 놓으면 블록이 가동범위를 벗어난다 — 가동범위를 다시 잡는다")
                if not self.can_pick(x_mm, y_mm):
                    raise Tool.Missing(f"대응점 {point.name} ({x_mm:.1f}, {y_mm:.1f}) 에 팔이 닿지 않는다(`Config.Robot.can_pick`) — 가동범위를 다시 잡는다")
            return placed

        def calibration_points(self, block: "Config.Product.Block", region_xy_mm: Sequence[tuple[float, float]],
                               margin_mm: float) -> tuple["Config.Robot.Motion.Calibration.Point", ...]:
            """대응점 수집의 둘째 단계 자리(`Calibration.Point`).

            격자 마디가 앞, 확인점이 뒤다.

            `region_xy_mm` 은 블록을 놓으면 카메라가 온전히 보는 곳 — 작업영역을 로봇 좌표로 옮긴 다각형이다. 가동범위와 겹치는 곳으로 줄인다.
            겹치는 곳의 변마다, 변의 법선 방향으로 블록 자국이 차지하는 반폭과 위치 불감대와 `margin_mm` 을 더한 만큼 안으로 민다. 장축 방위는 들고 다니는 방위(`Calibration.long_axis__deg`)다.
            민 다각형 위에 격자를 편다 — 열은 둘째로 작은 꼭짓점 X 에서 둘째로 큰 꼭짓점 X 까지를 고르게 나누고, 열마다 그 X 에서 다각형의 Y 구간을 고르게 나눈다.
            맨 끝 꼭짓점의 세로선은 다각형과 그 한 점에서만 만나 세로 구간이 사라지므로 끝 열을 거기 세우지 않는다. 볼록 다각형이라 마디가 그 안에 선다.
            첫 단계에서 이미 본 자리(`bootstrap_points`)에서 블록 단변 안에 드는 마디는 뺀다 — 같은 곳을 한 번 더 재는 셈이라 놓기만 는다. 마디 이름은 격자 자리 그대로라 빠진 번호가 생긴다.
            """
            spec, polygon = self.motion.calibration, Tool.Geometry.Polygon
            axis_rad = math.radians(spec.long_axis__deg)
            overlap = polygon.counterclockwise(region_xy_mm)
            for start, end in Tool.closed_edges(polygon.counterclockwise(self.reach.points_xy__mm)):
                overlap = polygon.half_plane_clipped(overlap, start, polygon.inward_normal(start, end), 0.0)
            inner = overlap
            for start, end in Tool.closed_edges(overlap):
                normal = polygon.inward_normal(start, end)
                normal_rad = math.atan2(normal[1], normal[0])
                half_mm = (block.length__mm / 2.0 * abs(math.cos(axis_rad - normal_rad))
                           + block.dimensions.width__mm / 2.0 * abs(math.sin(axis_rad - normal_rad)) + self.motion.deadband__mm + margin_mm)
                inner = polygon.half_plane_clipped(inner, start, normal, half_mm)
            if len(inner) < 3:
                raise Tool.Missing("작업영역과 가동범위가 겹치는 곳이 좁아 블록 자국과 여유를 빼면 격자 자리가 안 남는다")
            xs_mm = sorted(x_mm for x_mm, _ in inner)
            x_min_mm, x_max_mm = xs_mm[1], xs_mm[-2]

            def at(u: float, v: float) -> tuple[float, float]:
                x_mm = x_min_mm + u * (x_max_mm - x_min_mm)
                low_mm, high_mm = polygon.chord_y(inner, x_mm)
                return (x_mm, low_mm + v * (high_mm - low_mm))

            seen_xy_mm = [point.robot_xy_mm for point in self.bootstrap_points(block)]
            grid = [self.Motion.Calibration.Point(f"g{row * spec.grid_cols + col}", at(col / (spec.grid_cols - 1), row / (spec.grid_rows - 1)), 0.0, holdout=False, revisit_of=None)
                    for row in range(spec.grid_rows) for col in range(spec.grid_cols)]
            grid = [node for node in grid if all(math.dist(node.robot_xy_mm, xy_mm) >= block.dimensions.width__mm for xy_mm in seen_xy_mm)]
            checks = [self.Motion.Calibration.Point(f"h{index}", at(u, v), 0.0, holdout=True, revisit_of=None) for index, (u, v) in enumerate(spec.holdout_uv)]
            for point in grid + checks:
                x_mm, y_mm = point.robot_xy_mm
                if not self.reach.can_seat(point.robot_xy_mm, block, spec.long_axis__deg):
                    raise Tool.Missing(f"대응점 {point.name} ({x_mm:.1f}, {y_mm:.1f}) 에 놓으면 블록이 가동범위를 벗어난다")
                if not self.can_pick(x_mm, y_mm):
                    raise Tool.Missing(f"대응점 {point.name} ({x_mm:.1f}, {y_mm:.1f}) 에 팔이 닿지 않는다(`Config.Robot.can_pick`)")
            return tuple(grid + checks)

        # ------------------------------------------------- 물고 놓는 고도

        @cached_property
        def transit_z_mm(self) -> float:
            """가동범위 안에서 블록을 문 채 옮기는 고도. 픽업 높이에서 블록 높이만큼 위다 — 든 블록의 밑면이 매트 위 블록의 윗면 높이까지 오른다.

            사이클 · 대응점 수집은 매트에서 문 블록을 이 고도까지 곧게 들고, 수집은 이 고도로 옮긴다.

            가동범위는 픽업 높이에서 걸리는 것이 없는 둘레라 그 안에서는 안전 높이까지 들 까닭이 없다. 카메라 앞을 비키는 대피와 가동범위 밖(투입점)을 오가는 길은 안전 높이다.
            """
            return self.motion.heights.z_pick.z__mm + self.vision_algorithm.product.dimensions.height__mm

        @cached_property
        def mat(self) -> "Config.Robot.Surface":
            """매트 — 가동범위 안. 패드가 블록 윗면에 닿는 고도가 픽업 높이이고 거기서 문다. 놓는 고도는 내려놓는 높이다 — 벨로즈 패드가 블록을 들고 있어 픽업 높이보다 아래다."""
            heights = self.motion.heights
            return self.Surface(vacuum_z_mm=heights.z_pick.z__mm + self.vision_algorithm.product.dimensions.height__mm, grip_z_mm=heights.z_pick.z__mm,
                                retry_z_mm=heights.z_pick.z__mm - heights.grip_retry_press__mm, release_z_mm=heights.z_place.z__mm)

        @cached_property
        def conveyor(self) -> "Config.Robot.Surface":
            """컨베이어 투입점 — 대응점 수집이 블록을 처음 무는 곳이고, 사이클 · 수집이 블록을 놓는 곳.

            패드가 블록 윗면에 닿는 고도는 투입점 자리의 Z 다(`place_z_mm` — 지금은 컨베이어 접촉 높이를 가리킨다).
            거기서 누름 깊이(`Heights.z_conveyor_pick_press__mm`)만큼 아래에서 물고, 비접촉 여유(`Heights.z_conveyor_drop_offset__mm`)만큼 위에서 파기해 놓는다 — 벨트를 긁지 않는다.
            """
            heights = self.motion.heights
            contact_z_mm = self.place_z_mm(self.motion.positions.conveyor_entry)
            grip_z_mm = contact_z_mm - heights.z_conveyor_pick_press__mm
            return self.Surface(vacuum_z_mm=contact_z_mm + self.vision_algorithm.product.dimensions.height__mm, grip_z_mm=grip_z_mm,
                                retry_z_mm=grip_z_mm - heights.grip_retry_press__mm, release_z_mm=contact_z_mm + heights.z_conveyor_drop_offset__mm)

        def place_z_mm(self, position: "Config.Robot.Motion.Position") -> float | None:
            """이름 붙은 자리(`motion.positions` 의 항목)에 서는 높이. 그 자리의 `z` 가 가리키는 담는 높이다 — 담기 전이면 `None` 이다."""
            height = self
            for part in position.z.split(".")[1:]: height = getattr(height, part)
            return height.z__mm

        # ------------------------------------------------- 팔이 닿는 곳

        @cached_property
        def pick_heights_mm(self) -> tuple[float, ...]:
            """블록을 집거나 놓으러 매트 위 한 자리에서 지나는 패드 끝 고도 — 안전(가로지르기) · 이송, 매트의 진공 켜는 · 무는 · 더 누르는 고도, 담겼으면 놓는 고도."""
            mat = self.mat
            return tuple(z_mm for z_mm in (self.motion.heights.z_safe.z__mm, self.transit_z_mm, mat.vacuum_z_mm, mat.grip_z_mm,
                                           mat.retry_z_mm, mat.release_z_mm) if z_mm is not None)

        @cached_property
        def reach_bands_mm(self) -> tuple[tuple[float, float], ...]:
            """`pick_heights_mm` 의 고도 모두에서 팔이 닿는 기저 반경 구간 — 고도마다 낸 구간(`Arm.radius_bands_mm`)의 교집합. 높을수록 안쪽 원이 커지고 바깥 원이 작아진다."""
            bands: tuple[tuple[float, float], ...] = ((0.0, math.inf),)
            for z_mm in self.pick_heights_mm:
                bands = tuple((max(inner, other_inner), min(outer, other_outer))
                              for inner, outer in bands for other_inner, other_outer in self.arm.radius_bands_mm(z_mm)
                              if max(inner, other_inner) < min(outer, other_outer))
            return bands

        def can_pick(self, x_mm: float, y_mm: float) -> bool:
            """매트 위 이 자리를 집거나 이 자리에 놓을 수 있는가 — 실측 둘레(`Reach`) 안이고, 팔이 `pick_heights_mm` 의 고도 모두에서 패드 끝을 세운 채 닿는가.

            컨트롤러의 G01 직교 보간이 꺼져 있어(`$35=0`) 다리는 목표점까지만 간다 — 두 끝이 닿으면 된다고 본다.
            """
            return self.reach.contains(x_mm, y_mm) and all(self.arm.reaches(x_mm, y_mm, z_mm) for z_mm in self.pick_heights_mm)

        def reachable_outlines_mm(self, sagitta_mm: float) -> tuple[tuple[tuple[float, float], ...], ...]:
            """실측 둘레(`Reach`) 가운데 팔이 집고 놓을 수 있는 곳의 외곽선들 — 로봇 기저 mm. `sagitta_mm` 은 원호를 꺾은선으로 펼 때 허용하는 어긋남이다.

            실측 둘레는 픽업 높이에서 걸리는 것이 없는 둘레이고, 그 안이 다 닿는다는 뜻이 아니다. 기저 둘레 고리(`reach_bands_mm`)와 1축 방위 범위로 깎는다.
            """
            return tuple(loop for inner, outer in self.reach_bands_mm
                         for loop in Tool.Geometry.Polygon.annulus_clipped(self.reach.points_xy__mm, (inner, outer), self.arm.azimuth_range_deg, sagitta_mm))

        def reachable_outlines_px(self, era_values: "Config.Dataset.EraValues") -> tuple[tuple[tuple[float, float], ...], ...]:
            """팔이 집고 놓을 수 있는 곳의 외곽선들(`reachable_outlines_mm`)을 그 회차 값으로 화소에 옮긴다 — 로봇 기저 mm → 아핀의 역 → 상면 mm → H35.

            원호를 펼 때 허용하는 어긋남은 화면 한 화소(`Config.Dataset.EraValues.ppm_inplane`)다.
            아핀 · H35 · 관절 부호 가운데 빈 것이 있으면 비어 있다.
            """
            if not era_values.affine.is_solved or not era_values.homography.matrix:
                return ()
            try:
                loops = self.reachable_outlines_mm(1.0 / era_values.ppm_inplane)
            except Tool.Missing:
                return ()
            affine, homography = self.vision_algorithm.affine_transform, self.vision_algorithm.homography
            return tuple(tuple(homography.to_image(era_values.homography, *affine.to_world(era_values.affine, x_mm, y_mm)) for x_mm, y_mm in loop) for loop in loops)

        # ------------------------------------------------- 손목 각도

        def wrist_angle_deg(self, affine: "Config.Dataset.EraValues.Affine", vision_angle_deg: float, block: "Config.Product.Block", reference_deg: float | None = None) -> float:
            """비전이 낸 블록 각도를 손목 지령각으로 접는다. 손목이 장축에 맞는다.

            비전 평면과 로봇 기저의 방위 차, 그리고 엔드 이펙터 장착 영점 오차를 더해 원시각을 만든다.
            두 평면이 거울상이면(`Affine.is_mirrored`) 비전 각도가 로봇 기저에서 거꾸로 돈다.
            블록은 점대칭이라 주기만큼 돌린 각이 같은 자세이므로 후보 가운데 하나를 고른다(`_folded_deg`).
            """
            return self._folded_deg(self.vision_algorithm.affine_transform.to_robot_deg(affine, vision_angle_deg) + self.vision_algorithm.affine_transform.angle_offset__deg, block, reference_deg)

        def place_wrist_deg(self, block: "Config.Product.Block", held_wrist_deg: float, held_long_axis_deg: float) -> float:
            """투입점에 놓을 때의 손목 지령각.

            블록을 문 채 이 각으로 돌리면 장축이 벨트 진행 방향(`Hardware.conveyor_travel__deg`)을 따른다.
            `held_wrist_deg` 는 블록을 문 지금 손목각이고, `held_long_axis_deg` 는 그때 블록 장축의 로봇 기저 방위다.
            손목을 돌린 만큼 장축이 따라 돌므로, 문 손목에서 벨트 진행 방위와 장축 방위의 차만큼 더 돌린다.
            후보 가운데 문 손목에서 가장 덜 도는 것을 고른다 — 블록을 문 채 도는 양이 주기의 절반을 넘지 않는다.
            """
            return self._folded_deg(held_wrist_deg + self.hardware.conveyor_travel__deg - held_long_axis_deg, block, held_wrist_deg)

        def _folded_deg(self, raw_angle_deg: float, block: "Config.Product.Block", reference_deg: float | None) -> float:
            r"""같은 자세가 되는 손목각 가운데 하나.

            주기는 규격이 정한다.
            윗면이 정사각인 규격은 $90^\circ$ 마다 같은 자세가 되어 후보가 넷이고, 나머지는 $180^\circ$ 마다라 둘이다.

            기준각을 주면 그 각에서 가까운 후보를, 주지 않으면 절댓값이 가장 작은 후보를 고른다.
            후자는 주기의 절반 안으로 접는 것과 같다.
            경계에서 동률이면 원시각을 택한다 — 후보 순서의 첫 항이 원시각이다.
            """
            raw_angle_deg = Tool.wrap180(raw_angle_deg)
            period_deg = block.symmetry_deg
            candidates = tuple(
                Tool.wrap180(raw_angle_deg + step * period_deg)
                for step in range(int(360.0 / period_deg))
            )
            if reference_deg is None: return min(candidates, key=abs)
            return min(candidates, key=lambda angle: abs(Tool.wrap180(angle - reference_deg)))


    # ------------------------------------------------------------------
    # 2-5. 외부 통신
    # ------------------------------------------------------------------

    class Communication(Tool.JsonNode):
        """외부 장치 통신 규격 — `communication.json` 을 읽은 그대로 들고, 부르는 이름은 그 키 경로다(`communication.robot_serial.baudrate__bps`).

        하드웨어마다 한 묶음이다. LS 표기는 한 번(`plc_ls`), PLC 는 대마다 한 번(`plc_controller`)이다 — 문서가 그렇게 갈려 있다.
        """

        #: 영속화 자산 파일 이름(확장자 제외).
        DOCUMENT_STEM = "communication"

        # -------------------------------------------------------- 적재

        @classmethod
        def load(cls) -> "Config.Communication":
            """정본 디렉토리의 `communication.json` 을 읽는다."""
            return cls(Config.Document.read(Config.Document.setting_path(cls.DOCUMENT_STEM))[cls.DOCUMENT_STEM])

        # ------------------------------------------------------------------
        # WLKATA Mirobot (GRBL 계열 다관절 로봇)
        # ------------------------------------------------------------------

        class RobotSerial(Tool.JsonNode):
            """GRBL 계열 로봇 컨트롤러 시리얼 규격(`robot_serial`).

            `dtr_enable` :: 상승 엣지가 보드를 리셋해 기구가 주저앉으므로 끈다
            `bus_address` :: -1 은 주소 접두 없는 단일 시리얼을 뜻한다
            `boot_settle__s` :: 포트 개방 직후 부팅 바이트 배출 대기
            `query_timeout__s` :: 응답 최대 대기
            `probe_poll__ms` :: 수신 버퍼 검사 주기
            `request_wait__s` :: 로봇 워커가 일감 큐를 한 번 기다리는 길이. 쉬는 동안의 상태 조회가 이만큼 늦을 수 있다
            `status_poll__s` :: 일이 없는 동안 상태 보고를 묻는 간격
            `motion_poll__s` :: 이동 완료를 확인하는 상태 조회 간격
            `motion_wait__s` :: 이동이 끝나기를 기다리는 상한. 기다림의 천장이다 — 이만큼 지나도 `Idle` 이 안 오면 기다리기를 그만두고 사람에게 알린다
            `homing_wait__s` :: 호밍이 끝나기를 기다리는 상한. 원점까지 전 축이 돌아 한 다리 이송보다 길다 — 기다림의 천장이라 넉넉히 잡았다(근거 없음)
            `homing_settle__s` :: 호밍 끝으로 치려면 멈춘 자리가 그대로 머물러야 하는 시간. 호밍 막바지에 잠깐 선 것을 끝으로 읽지 않는다(근거 없음 — 기다림의 바닥)
            `terminator` :: 이 문자가 보이면 즉시 반환한다
            `alarm_prefix` :: 상태 문자열이 이것으로 시작하면 원점 미확정이다
            `moving_states` :: 기구가 움직이는 동안의 상태 보고(소문자). 호밍 중에는 `Home` 으로 답하고, 그동안 줄 명령에 접수 낱말을 안 준다
            """

            class GCode(Tool.JsonNode):
                """컨트롤러가 알아듣는 명령 낱말과 축 순서(`gcode`).

                펌웨어가 정한 사실이다.
                낱말을 엮어 한 줄을 만드는 문법은 부르는 쪽이 갖는다.
                `cartesian_mode` :: 직교 모드 전환
                `angle_mode` :: 관절 모드 전환
                `absolute` :: 절대 좌표
                `relative` :: 상대 좌표. 쓴 뒤에는 절대로 되돌린다
                `rapid` :: 최대 속도 이동. 속도 인자를 요구하지 않는다
                `linear` :: 직선 보간. 속도가 없으면 컨트롤러가 거부한다
                `feed_prefix` :: 이송 속도 접두. 단위는 mm/min
                `homing` :: 전 축 동시 원점 복귀
                `unlock_axes` :: 전원 투입 후 축 잠금 해제(`M50`). **버튼으로 내지 않는다** — 이것을 쓰는 수동 정렬 절차(공식 매뉴얼)가 **소프트 리밋 해제**를 먼저 요구하는데, 리밋이 꺼진 채 조작하면 기구를 때린다. 낱말만 여기 둔다
                `alarm_clear` :: 알람 해제
                `pneumatic_prefix` :: 공압 PWM 접두
                `status_query` :: 상태 보고 요청
                `ack` :: 명령을 접수했을 때 돌아오는 낱말
                `feed_hold` :: 이송 일시 정지
                `cycle_resume` :: 이송 재개. 피드홀드를 푼다
                `soft_reset_byte` :: 소프트 리셋 제어 문자의 코드. **보내지 않는다** — 컨트롤러가 `Offline` 로 떨어지고 베이스의 물리 RESET 으로만 돌아온다. 낱말만 둔다
                `command_axes` :: 명령에 쓰는 축 문자. 순서가 곧 축 번호다
                `report_angle_axes` :: 상태 보고가 각도를 늘어놓는 순서. 축마다 이 안에서 제 자리를 골라 읽는다
                `report_angles_tag` :: 상태 보고에서 관절 각도 묶음의 머리. 뒤에 붙는 축 순서는 `report_angle_axes` 가 든다
                `report_cartesian_tag` :: 상태 보고에서 직교 좌표 묶음의 머리
                `report_pump_tag` :: 상태 보고에서 펌프 PWM 의 머리
                `report_valve_tag` :: 상태 보고에서 밸브 PWM 의 머리
                """

                @cached_property
                def angle_slots(self) -> tuple[int, ...]:
                    """축 번호 순으로, 그 축이 상태 보고의 몇 번째 자리에 있는가.

                    두 순서에서 유도한다.
                    따로 적어 두면 한쪽만 갱신되어 조용히 어긋난다 — 보고에서 1축 자리를 읽는다고 믿으며 4축 값을 읽게 된다.
                    """
                    return tuple(self.report_angle_axes.index(axis)
                                 for axis in self.command_axes)

                @property
                def soft_reset(self) -> bytes:
                    """소프트 리셋으로 보낼 바이트."""
                    return bytes((self.soft_reset_byte,))

            @cached_property
            def device_ids(self) -> tuple["Connect.Device.Usb.Entry", ...]:
                """포트 번호 대신 USB 식별자로 장치를 찾는다(`device_ids`) — 식별자 글자를 풀어 둔다."""
                return Connect.Device.Usb.entries(self.doc["device_ids"])

            def is_alarm(self, status: str) -> bool:
                """컨트롤러가 알람 상태인가. 호밍 전에는 이동 지령이 거부된다."""
                return status.strip().lower().startswith(self.alarm_prefix.lower())

            def is_moving(self, status: str) -> bool:
                """기구가 움직이는 중이라는 상태 보고인가."""
                return status.lower() in self.moving_states

            def is_alarm_response(self, text: str) -> bool:
                """응답 어디엔가 알람 표시가 섞여 있는가. 거부된 명령이 그렇게 답한다."""
                return self.alarm_prefix.lower() in text.lower()

            def is_complete(self, buffer: str) -> bool:
                """수신 버퍼가 응답 하나를 다 받았는가."""
                return self.terminator in buffer

        # ------------------------------------------------------------------
        # LS XGB PLC (Modbus)
        # ------------------------------------------------------------------

        class PlcQr(Tool.JsonNode):
            """QR 로 규격을 읽어 PLC 에 알리는 계통(`plc_qr`). 로봇 투입 사이클 밖이다.

            래더가 신호를 받는 창은 자재가 측정부에 들어와 있는 동안이고, 그 안에서 일어난 상승 에지만 규격을 물린다.
            창 밖에서 보낸 신호는 아무 일도 하지 않는다.
            `pulse__s` :: 상승 에지를 만드는 켜짐 시간
            `codes` :: QR 문자열 하나와 그것이 세울 접점 — `text` 는 QR 에 실린 문자열, `device` 는 세울 가상 통합 입력 비트(쓸 때 LAN 뱅크로 치환된다), `name` 은 사람이 읽는 규격 이름이다
            """

            # 판독 모드와 측정부 재실은 `cnv_alg_core.QrSort.advance` 가 인자로 받는다.
            # 래더에서 읽어 이 클래스가 들게 되면 그때 자리를 만든다

            def code(self, text: str) -> "Tool.JsonNode | None":
                """읽은 문자열에 맞는 규격. 모르는 문자열이면 `None`."""
                for one in self.codes:
                    if one.text == text:
                        return one
                return None

        class PlcLs(Tool.JsonNode):
            """LS 디바이스 표기를 읽는 규칙(`plc_ls`).

            **LS 가 정한 것이라 PLC 가 몇 대든 한 벌이다.** 래더를 다시 짜도 안 바뀐다.
            `word_bits` :: 워드 하나의 비트 수. LS 규격이 정한다
            `devices` :: 디바이스 글자 → 그 표기 규칙. `bit_tail` 은 끝 한 자리가 비트인가다
            """

        class PlcController(Tool.JsonNode):
            """LS PLC 한 대가 가진 것(`plc_controller` 의 항목). **대마다 다르다.**

            `area_start` :: 영역마다 시작하는 디바이스 표기. 게이트웨이를 다시 잡으면 바뀐다 — 키는 `Area` 이름의 소문자다
            """

            class Area(Enum):
                """Modbus 로 열어 둔 영역 넷. 비트냐 워드냐 × 읽기냐 쓰기냐."""

                BIT_READ = auto()
                BIT_WRITE = auto()
                WORD_READ = auto()
                WORD_WRITE = auto()

            class Transport(Tool.JsonNode):
                """이 PLC 에 붙는 길.

                `transport` :: `tcp` 또는 `serial`
                `poll_cycle__s` :: 벨트 위 고속 물류의 센서 입력 누락을 막는 정주기 간격
                `request_wait__s` :: PLC 워커가 요청을 한 번 기다리는 길이. 정주기 긁기가 이만큼 늦을 수 있으므로 `poll_cycle__s` 보다 짧아야 한다
                `serial_port` :: 시리얼 Modbus 포트 이름
                `serial_baudrate__bps` :: 시리얼 Modbus 보율
                """

            class Ladder(Tool.JsonNode):
                """이 PLC 에 실린 래더가 약속한 것. **래더를 다시 짜면 바뀐다.**

                `read_start` :: 상태를 내놓는 첫 워드. **여기서부터 몇 워드를 읽을지는 싣지 않는다** — 그건 무엇을 읽느냐가 정하는 것이라 알고리즘이 안다(`cnv_alg_core.PlcRead.AddressRule.Type`)
                `virtual_word_threshold` :: 이 번호부터는 약속된 자리다
                `device_block_words` :: 디바이스 한 덩이가 차지하는 워드 수
                `lan_word_base` :: LAN 우회가 시작하는 워드
                """

                @cached_property
                def lan_write_mask(self) -> dict[int, int]:
                    """워드 → 그 워드에서 쓰기가 닿는 비트(`lan_write_mask` — 키는 워드 번호 글자, 값은 16진 글자)."""
                    return {int(word): int(mask, 16) if isinstance(mask, str) else int(mask) for word, mask in Config.Document.entries(self.doc["lan_write_mask"])}

    # ------------------------------------------------------------------
    # 2-6. 작업자 화면
    # ------------------------------------------------------------------

    class Ui(Tool.JsonNode):
        """작업자 GUI 표시 규격 — `ui.json` 을 읽은 그대로 들고, 부르는 이름은 그 키 경로다(`ui.viewer.target__fps`).

        층(`layers`)과 오버레이(`overlays`)는 이름으로 묶인 항목이고, 선언 순서가 곧 화면 순서다.
        층은 바탕 위에 색을 입혀 섞는 것이고, 오버레이는 그 위에 그리는 도형이다.
        항목마다 `name`(사람이 읽는 이름) · `color`(테마 색의 이름) · `on`(켜고 시작하는가)을 든다.
        """

        #: 영속화 자산 파일 이름(확장자 제외).
        DOCUMENT_STEM = "ui"

        # -------------------------------------------------------- 적재

        @classmethod
        def load(cls) -> "Config.Ui":
            """정본 디렉토리의 `ui.json` 을 읽는다. 테마마다 기본 테마의 색 뜻을 하나라도 안 채우면 여기서 멈춘다."""
            ui = cls(Config.Document.read(Config.Document.setting_path(cls.DOCUMENT_STEM))[cls.DOCUMENT_STEM])
            meanings = set(ui.theme.themes[ui.theme.default].colors)
            for key, theme in ui.theme.themes.items():
                missing = sorted(meanings - set(theme.colors))
                if missing: raise Tool.Missing(f"{cls.DOCUMENT_STEM}.theme.themes.{key}.colors 미기입 :: " + " · ".join(missing))
            return ui

        # -------------------------------------------------- 하위 규격

        class Viewer(Tool.JsonNode):
            """화면 표시 규격(`viewer`).

            `target__fps` :: 취득 · 검출 루프의 목표 프레임률. 화면 갱신 주기는 여기서 유도한다
            `overlay_alpha` :: 형상 채움 반투명 가중치
            """

            class CornerAnchor(Tool.JsonNode):
                """검출 꼭짓점 이중 동심원 앵커 규격.

                `outer_color` :: 테마 색의 이름
                `inner_r__px` :: 내부 원은 규격별 색을 쓴다
                """

            class Coverage(Tool.JsonNode):
                """라벨 분포도 레이어 표시 규격.

                `alpha` :: 히트맵을 원본에 합성할 때의 투명도
                `blur_kernel__px` :: 라벨 누적 맵을 평활하는 가우시안 커널
                """

                @cached_property
                def blur_kernel_odd_px(self) -> int:
                    """가우시안 커널로 쓸 홀수."""
                    return Tool.odd(self.blur_kernel__px)

            @staticmethod
            def to_source_px(disp_xy: tuple[float, float], scale: float) -> tuple[int, int]:
                """화면 좌표를 센서 화소 좌표로 되돌린다. 클릭 지점을 원본에 꽂을 때 쓴다."""
                return (round(disp_xy[0] / scale), round(disp_xy[1] / scale))

            def tick_ms(self) -> int:
                """화면 갱신 주기. 취득 · 검출 목표 프레임률에서 유도한다."""
                return max(1, round(1000.0 / self.target__fps))

            def blend(self, base: float, fill: float) -> float:
                """반투명 합성 한 채널."""
                return self.overlay_alpha * fill + (1.0 - self.overlay_alpha) * base

        class Theme(Tool.JsonNode):
            """색 테마(`theme`).

            `widget_theme` :: 플랫폼 기본 테마가 버튼 배경색을 무시하므로 고정한다
            `default` :: 처음 거는 테마의 키
            `themes` :: 테마 키 → 테마 한 벌
            """

            class Theme(Tool.JsonNode):
                """테마 한 벌(`themes` 의 항목) — 색의 뜻과 값. 이름은 그대로고 테마마다 값이 바뀐다.

                빨강이 정지라는 것은 약속이다.
                약속이 적혀 있지 않으면 화면마다 달라지므로 정의가 든다.
                부르는 쪽은 뜻으로 부른다(`theme.colors.ok` · `theme.colors.danger`) — 뜻의 이름은 이 JSON 이 정한다.
                `name` :: 사람이 고를 때 보이는 이름
                `colors` :: 색의 뜻 → 값(`#rrggbb`). `ground` 창 바탕 · `surface` 패널 바탕 · `surface2` 한 단 들어간 바탕 · `stage` 영상 뒤 · `line` 테두리 · `ink` 본문 글자 · `ink2` 흐린 글자 · `ink3` 더 흐린 글자 · `accent` 고른 것 · 강조 · `ok` 정상 · `warn` 주의 · `danger` 위험 · 정지 · `idle` 잠긴 것 · `layer_mask` 마스크 층 · `layer_cut` 절단선 층 · `layer_shape` 형상 층
                """

                def bgr(self, name: str) -> tuple[int, int, int]:
                    """영상 위에 그릴 때 쓰는 채널 순서. 화면과 같은 색을 같은 뜻으로 쓴다."""
                    hex_rgb = self.colors[name].lstrip("#")
                    return (int(hex_rgb[4:6], 16), int(hex_rgb[2:4], 16), int(hex_rgb[0:2], 16))

    # ------------------------------------------------------------------
    # 2-7. 표본 자료
    # ------------------------------------------------------------------

    class Dataset(Tool.JsonNode):
        """촬영 회차(이력)를 읽는다 — 저장 서식 · 회차 찾기 · 회차 문서와 그 칸(`Camera` · `Homography` · `WorkArea` · `Affine`). 현행 값은 `vis_alg_core.EraState` 가 든다.

        회차 하나가 환경 조건(카메라 · 설정값 · 촬영 위치)의 단위다.
        회차 문서에는 그 회차에서 관찰한 값만 있고, 관찰하지 않은 값은 `null` 이다.
        읽을 때 다른 회차에서 당겨오지 않는다.
        보관 규격은 `dataset.json` 을 읽은 그대로 들고, 부르는 이름은 그 키 경로다(`dataset.storage_format.era_pattern`).
        `era_document` :: 회차 폴더마다 하나인 회차 문서 파일 이름
        """

        #: 영속화 자산 파일 이름(확장자 제외).
        DOCUMENT_STEM = "dataset"

        #: 아핀 대응점 수집의 기록(영상 · 단계 · 자리마다 본 장)이 쌓이는 폴더. 회차 규칙에 안 맞는 이름이라 회차로 안 읽힌다
        CALIBRATION_DIR = "_calib"

        # -------------------------------------------------------- 적재

        @classmethod
        def load(cls) -> "Config.Dataset":
            """정본 디렉토리의 `dataset.json` 을 읽는다."""
            return cls(Config.Document.read(Config.Document.setting_path(cls.DOCUMENT_STEM))[cls.DOCUMENT_STEM])

        class StorageFormat(Tool.JsonNode):
            """파일 명명 규격(`storage_format`).

            `era_pattern` :: 회차 디렉토리 이름 규격. 날짜 자리(`ERA_DAY_SLOT`)와 순번 글자 자리(`ERA_LETTER_SLOT`)가 든다
            `max_daily_count` :: 하루에 열 수 있는 회차 슬롯 수
            `frame_pattern` :: 장 파일 이름 규격. `<tenth>` 자리에 초 미만 눈금이 든다
            `time_resolution__s` :: 파일명 시각 분해능
            """

            #: 회차 이름 규격(`era_pattern`)에서 날짜가 서는 자리. 날짜 6자리로 바뀐다
            ERA_DAY_SLOT = "%y%m%d"
            #: 회차 이름 규격에서 같은 날 순번 글자가 서는 자리. 순번 1 이 `a` 다
            ERA_LETTER_SLOT = "[a-z]"

            @staticmethod
            def era_day(when: "datetime.datetime") -> str:
                """회차 이름의 날짜 6자리."""
                return when.strftime(Config.Dataset.StorageFormat.ERA_DAY_SLOT)

            def era_name(self, when: "datetime.datetime", index: int) -> str:
                """회차 디렉토리 이름. 규격의 날짜 자리에 날짜를, 순번 글자 자리에 같은 날 순번 글자를 넣는다."""
                return when.strftime(self.era_pattern.replace(self.ERA_LETTER_SLOT, chr(ord("a") + index - 1)))

            @cached_property
            def era_name_regex(self) -> "re.Pattern[str]":
                """회차 디렉토리 이름을 푸는 식.

                규격의 날짜 자리는 날짜 6자리, 순번 글자 자리는 글자 하나이고, 글자가 없는 이름도 읽는다(순번 0).
                뒤에 사람이 읽는 꼬리표(`_설명`)가 붙을 수 있다.
                """
                head, _, tail = self.era_pattern.partition(self.ERA_LETTER_SLOT)
                prefix, _, between = head.partition(self.ERA_DAY_SLOT)
                return re.compile(f"^{re.escape(prefix)}(\\d{{6}}){re.escape(between)}([a-z]?){re.escape(tail)}(?:_(.+))?$")

            def frame_name(self, when: "datetime.datetime", collision: int = 0) -> str:
                """프레임 파일명.

                초 미만을 분해능 단위로 끊어 붙인다.
                같은 눈금에 두 장이 들어오면 꼬리 번호를 더해 덮어쓰기를 막는다.
                """
                tenth = int((when.microsecond / 1_000_000) / self.time_resolution__s)
                base = self.frame_pattern.replace("<tenth>", str(tenth)).replace(".png", "")
                base = when.strftime(base)
                return f"{base}.png" if collision == 0 else f"{base}_{collision}.png"

        class Era(NamedTuple):
            """회차 하나. 폴더 이름에서 날짜와 순번을 푼다."""

            path: Path
            day: str  # `%y%m%d` 날짜 6자리
            index: int  # 같은 날 순번. 글자 없음 0 · `a` 1 … `z` 26

            @property
            def name(self) -> str: return self.path.name

            @property
            def key(self) -> tuple[str, int]:
                """정렬 키. 꼬리 설명은 쓰지 않는다."""
                return (self.day, self.index)

            @classmethod
            def parse(cls, path: Path, *, storage_format: "Config.Dataset.StorageFormat") -> "Config.Dataset.Era | None":
                """이름이 회차 규칙(`StorageFormat.era_name_regex`)에 맞지 않으면 `None`. `_labelcards` · `_render` 같은 곁 폴더가 여기서 빠진다."""
                name_match = storage_format.era_name_regex.match(path.name)
                if name_match is None: return None
                day, letter, _ = name_match.groups()
                return cls(path, day, ord(letter) - ord("a") + 1 if letter else 0)

        class EraValues(Tool.JsonNode):
            """회차 문서 한 장 — 카메라 · H35 · 작업영역 · 아핀이고, 그 회차 사진에서 좌표를 내는 조건이다.

            읽은 dict 를 그대로 들고, 부르는 이름은 회차 문서의 키 경로다(`era_values.work_area.polygon__px`).
            """

            height_mm: float  # 블록 높이 — H35 평면의 고도이고, 세로 소실점을 셈하도록 `homography` 칸에 넣어 준다

            class Camera(Tool.JsonNode):
                """`camera` 칸 — 그 회차를 찍은 장치(`device`) · 그때 걸린 설정(`settings`) · 장치가 밝힌 내부 파라미터(`pinhole`)다.

                장치는 `id`(`VID_xxxx&PID_xxxx&MI_xx` 꼴)와 사람이 읽는 `name` 을 든다.
                설정은 장치 내부 눈금이라 물리 단위가 없다.
                내부 파라미터는 바늘구멍 카메라의 초점거리(`focal__px`)와 주점(`principal__px`)이다.
                회차가 장치나 설정을 안 적었으면 `null` 이고, 모르는 장치의 회차에는 `pinhole` 칸이 없다 — `get("pinhole")` 로 부른다.
                """

                class Device(Tool.JsonNode):
                    """회차를 찍은 장치. 같은 장치인지는 `VID/PID` 로만 가른다."""

                    def is_among(self, found: "Sequence[Connect.Device.Usb.Id | None]") -> bool:
                        """열거된 장치 중에 이 회차를 찍은 장치가 있는가."""
                        target_id = Connect.Device.Usb.Id.parse(self.id)
                        return any(one is not None and target_id.matches(one) for one in found)

            class Homography(Tool.JsonNode):
                """`homography` 칸 — 화소를 상면 mm 로 보내는 H35(`matrix`)와 세로 소실점(`vertical_vanishing_point`)이다.

                둘 다 카메라 자세에 매인다.
                """

                pinhole: "Tool.JsonNode | None"  # 그 회차 카메라의 내부 파라미터(`camera.pinhole`) — 모르는 장치면 `None`
                height_mm: float  # 블록 높이 — H35 평면의 고도
                vanishing_point: tuple[float, float, float] | None  # 넣어 주면 그 값이 세로 소실점을 대신한다 — 후보를 시험할 때다

                @cached_property
                def vanishing_point(self) -> tuple[float, float, float] | None:
                    """세로 소실점. 동차 화소 좌표 (x, y, z) — 화면 위치는 (x/z, y/z), z 는 H35 와 함께 밑면이 소실점 쪽으로 가는 거리를 정한다.

                    내부 파라미터를 아는 카메라는 H35 에서 닫힌 식으로 낸다(`Config.VisionAlgorithm.Homography.vanishing_point_of`) — 런타임 입력으로 되풀리는 값이라 회차 문서에 적지 않는다.
                    모르는 카메라는 회차 문서의 `vertical_vanishing_point` 다.
                    """
                    if self.pinhole is None or self.matrix is None: return self.vertical_vanishing_point
                    return Config.VisionAlgorithm.Homography.vanishing_point_of(self.matrix, self.pinhole, height_mm=self.height_mm)

                @cached_property
                def is_vanishing_solved(self) -> bool:
                    """세로 소실점이 풀려 있는가. 3차원 실루엣 예측과 경사각 역산이 이 값에 기댄다."""
                    return self.vanishing_point is not None and any(abs(coordinate) > Config.VisionAlgorithm.EPS for coordinate in self.vanishing_point)

                @cached_property
                def inv_matrix(self) -> tuple[tuple[float, ...], ...]:
                    """역행렬. 상면 mm 를 화소로 되돌린다."""
                    return Config.VisionAlgorithm._inverse(Config.VisionAlgorithm.Homography._require_matrix(self))

            class WorkArea(Tool.JsonNode):
                """`work_area` 칸 — 매 프레임 패드를 다시 찾지 않으려고 고정해 둔 작업영역 다각형(`polygon__px` — 4점, 원본 화소)이다.

                카메라 자세에 매인다.
                """

                @staticmethod
                def picked(points_px: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
                    """사람이 찍은 점에서 선 작업영역 다각형 — `polygon__px` 에 적는다.

                    쓰는 곳(잘라 보기 · 오버레이)이 둘레 차례를 전제하므로 둘레 차례로 세운다(`Tool.Geometry.Polygon.perimeter_order`).
                    """
                    return tuple((float(u_px), float(v_px)) for u_px, v_px in Tool.Geometry.Polygon.perimeter_order(points_px))

                @cached_property
                def center_px(self) -> tuple[float, float]:
                    """작업영역 다각형의 무게중심. 대표 축척을 재는 자리다."""
                    polygon = Config.VisionAlgorithm._require_work_area_px(self)
                    return (statistics.fmean(point[0] for point in polygon), statistics.fmean(point[1] for point in polygon))

            class Affine(Tool.JsonNode):
                """`affine` 칸 — 상면 mm 를 로봇 기저로 보내는 2x3(`matrix`)과, 그것을 푼 대응점(`pairs`) · 이동 성분 관측(`pivot`)이다.

                티칭 전에는 행렬이 `null`, 대응점이 빈 목록, 이동 성분 관측이 `null` 이다.
                이동 성분 관측을 들이기 전의 회차에는 `pivot` 칸이 없다 — `get("pivot")` 로 부른다.
                대응점 하나는 로봇이 블록을 놓은 자리(`robot_xy__mm` — 로봇 지령 좌표)와 카메라가 본 자리(`pixel_xy` — 검출 중심, 화소)다.
                대응점의 `holdout` 이 참이면 적합에 쓰지 않고 검증에 쓴다.
                대응점의 `revisit_of` 는 같은 자리를 다시 놓은 점일 때 첫 점의 이름이다 — 적합에 쓰지 않고 탈조 확인에 쓴다.
                이동 성분 관측은 한 자리(`robot_xy__mm`)에 같은 블록을 두 번 놓고 본 두 검출 중심(`pixel_xy`)이다 — 두 번째는 블록을 문 채 손목만 반 바퀴 더 돌려 놓았다.
                이동 성분 관측이 행렬의 이동 성분을 낸다(`Config.VisionAlgorithm.AffineTransform.pivoted`).
                블록은 패드에서 어긋난 채 물린다.
                손목만 반 바퀴 돌리면 블록 중심이 손목 축에 대해 점대칭인 자리로 가므로, 두 검출의 가운데가 손목 축이 선 지령 자리다.
                직교 지령에서 손목만 돌리면 자리는 그대로라고 본다(`Config.Robot.Route.turn`) — 패드가 손목 축과 동심이라는 가정이다.
                """

                @cached_property
                def fit_pairs(self) -> tuple["Tool.JsonNode", ...]:
                    """적합에 쓰는 대응점."""
                    return tuple(calibration_pair for calibration_pair in self.pairs if not calibration_pair.holdout and calibration_pair.revisit_of is None)

                @cached_property
                def holdout_pairs(self) -> tuple["Tool.JsonNode", ...]:
                    """검증에 쓰는 대응점."""
                    return tuple(calibration_pair for calibration_pair in self.pairs if calibration_pair.holdout and calibration_pair.revisit_of is None)

                @cached_property
                def revisit_pairs(self) -> tuple["Tool.JsonNode", ...]:
                    """탈조 확인에 쓰는 재방문 대응점."""
                    return tuple(calibration_pair for calibration_pair in self.pairs if calibration_pair.revisit_of is not None)

                @cached_property
                def is_solved(self) -> bool:
                    """아핀이 풀려 있는가."""
                    return self.matrix is not None

                @cached_property
                def inv_matrix(self) -> tuple[tuple[float, ...], ...]:
                    """역아핀. 2x3 을 동차 3x3 으로 올려 역산한 뒤 위 두 행만 돌려준다."""
                    affine_matrix = Config.VisionAlgorithm.AffineTransform._require_matrix(self)
                    return Config.VisionAlgorithm._inverse((affine_matrix[0], affine_matrix[1], (0.0, 0.0, 1.0)))[:2]

                @cached_property
                def scale(self) -> float:
                    r"""분해 등방 축척. $\sqrt{a_{11}^2 + a_{21}^2}$. 설치 상태 진단에 쓴다."""
                    affine_matrix = Config.VisionAlgorithm.AffineTransform._require_matrix(self)
                    return math.hypot(affine_matrix[0][0], affine_matrix[1][0])

                @cached_property
                def rotation_deg(self) -> float:
                    """분해 회전각. 두 좌표계의 방위 차다."""
                    affine_matrix = Config.VisionAlgorithm.AffineTransform._require_matrix(self)
                    return math.degrees(math.atan2(affine_matrix[1][0], affine_matrix[0][0]))

                @cached_property
                def is_mirrored(self) -> bool:
                    """상면 mm 평면과 로봇 기저가 거울상인가. 선형 부분의 행렬식이 음수다 — 거울상이면 상면 mm 에서 잰 방위가 로봇 기저에서 거꾸로 돈다."""
                    affine_matrix = Config.VisionAlgorithm.AffineTransform._require_matrix(self)
                    return affine_matrix[0][0] * affine_matrix[1][1] - affine_matrix[0][1] * affine_matrix[1][0] < 0.0

            @cached_property
            def homography(self) -> "Config.Dataset.EraValues.Homography":
                """`homography` 칸 — 세로 소실점을 셈하도록 카메라의 내부 파라미터와 블록 높이를 넣어 준다."""
                return self.Homography(self.doc["homography"], pinhole=self.camera.get("pinhole"), height_mm=self.height_mm)

            @cached_property
            def ppm_inplane(self) -> float:
                """작업영역 중심의 면내 축척. 위치에 민감한 계산은 `Config.VisionAlgorithm.Homography.ppm_inplane_at` 을 쓴다."""
                return Config.VisionAlgorithm.Homography.ppm_inplane_at(self.homography, *self.work_area.center_px)

        @cached_property
        def captures_dir(self) -> Path:
            """회차 아카이브 루트(`captures_dir`). JSON 에는 정본 디렉토리 기준 상대경로로 적혀 있어 절대경로로 풀어 둔다."""
            return (Config.Document.CONFIG_DIR / self.doc["captures_dir"]).resolve()

        @cached_property
        def era_template(self) -> dict[str, Any]:
            """회차 문서의 형태(`era_template`) — 새 회차 문서의 바탕이라 읽은 dict 그대로 낸다."""
            return self.doc["era_template"]

        def eras(self) -> tuple["Config.Dataset.Era", ...]:
            """회차. 최근 것이 앞이다.

            캡처가 가동 중에 회차를 더하므로 부를 때마다 폴더를 다시 훑는다.
            """
            found = (self.Era.parse(d, storage_format=self.storage_format) for d in self.captures_dir.iterdir() if d.is_dir())
            return tuple(sorted((era for era in found if era is not None), key=lambda era: era.key, reverse=True))

        def latest(self, device: "Connect.Device.Usb.Id") -> "Config.Dataset.Era | None":
            """같은 카메라(VID/PID)의 가장 최근 회차. 기동이 이 회차의 값을 현행으로 올린다. 없으면 `None`."""
            for era in self.eras():
                recorded = self.read_era(era.path)["camera"]["device"]
                # 장치를 적지 않은 회차는 어느 카메라의 것도 아니라 건너뛴다
                if recorded is not None and Connect.Device.Usb.Id.parse(recorded["id"]).matches(device): return era
            return None

        class Photos:
            """회차 폴더의 사진을 차례로 내주는 입력."""

            SUFFIX = ".png"

            era_dir: Path
            frames: tuple[Path, ...]

            def __init__(self, era_directory: Path) -> None:
                self.era_dir = era_directory
                self.frames = tuple(sorted(era_directory.glob(f"*{self.SUFFIX}")))

            @property
            def name(self) -> str: return self.era_dir.name
            def __len__(self) -> int: return len(self.frames)
            def frame_name(self, index: int) -> str: return self.frames[index].name

            def read(self, index: int) -> Any:
                """그 자리의 사진. 한글 경로는 `Connect.Code.OpenCvPath` 가 덮어 둔 `imread` 가 연다."""
                from cv2 import imread as cv2_imread

                return cv2_imread(str(self.frames[index]))

            def scene(self, index: int) -> "Entity.Scene | None":
                """관측 한 벌. 계측 부품이 서면 여기에 결과가 함께 담긴다."""
                image = self.read(index)
                if image is None: return None
                return Entity.Scene(self.name, index, self.frame_name(index), image)


        class Labels:
            """회차 폴더의 정답 라벨. 윗면 네 꼭짓점과 규격이다.

            레거시가 남긴 `labels.json` 을 그대로 읽는다 — 채점 표본의 정본이라 옮겨 적지 않는다.
            더하고 빼는 쓰기(`append` · `drop_last`)는 쓰기 주인(`Tool.Writer`)이 부른다.
            """

            DOCUMENT = "labels.json"

            #: 규격 판정을 보류한 사각형의 `class_source`. 규격이 없어 읽지 않는다
            PENDING_SOURCE = "review"
            #: 사람이 네 점을 찍고, 규격은 그 네 점의 종횡비로 고른 사각형의 `class_source`
            ASPECT_SOURCE = "aspect"

            quads_by_frame: dict[str, tuple]

            def __init__(self, quads_by_frame: dict[str, tuple]) -> None:
                self.quads_by_frame = quads_by_frame

            @classmethod
            def load(cls, era_directory: Path) -> "Config.Dataset.Labels":
                quads_by_frame = {
                    name: tuple(
                        (tuple(tuple(float(v) for v in corner) for corner in quad["corners"]),
                         float(quad["class_mm"]))
                        for quad in entry.get("quads", ())
                        if quad.get("class_source") != cls.PENDING_SOURCE
                    )
                    for name, entry in cls._document(era_directory).get("images", {}).items()
                }
                return cls({name: quads for name, quads in quads_by_frame.items() if quads})

            def of(self, frame_name: str) -> tuple: return self.quads_by_frame.get(frame_name, ())

            @property
            def frame_count(self) -> int: return len(self.quads_by_frame)

            @property
            def quad_count(self) -> int: return sum(len(quads) for quads in self.quads_by_frame.values())

            # 쓰기 :: 라벨 탭이 부른다. 파일을 통째로 읽고 그 장의 사각형만 고쳐 쓴다 — 다른 칸은 그대로 남는다

            @classmethod
            def _document(cls, era_directory: Path) -> dict[str, Any]:
                """그 회차의 라벨 파일 전체 — 파일이 없으면 빈 틀이다."""
                path = era_directory / cls.DOCUMENT
                if not path.is_file(): return {"images": {}}
                return Config.Document.read(path)

            @classmethod
            def append(cls, era_directory: Path, frame_name: str, points_px: Sequence[tuple[float, float]], *, product: "Config.Product") -> float:
                """사람이 찍은 네 점을 그 장에 사각형 하나로 더하고, 고른 규격 길이(mm)를 낸다. 파일이 없으면 만든다.

                점은 둘레 차례로 세우고 화소 u + v 가 가장 작은 꼭짓점(왼쪽 위)부터 시작한다.
                규격은 사각형의 종횡비로 고른다(`ASPECT_SOURCE`).
                """
                ordered = Tool.Geometry.Polygon.perimeter_order(points_px)
                start = min(range(len(ordered)), key=lambda index: ordered[index][0] + ordered[index][1])
                corners_px = ordered[start:] + ordered[:start]
                class_mm = product.block_by_aspect(Tool.Geometry.Polygon.quad_aspect_ratio(corners_px)).length__mm
                doc = cls._document(era_directory)
                entry = doc.setdefault("images", {}).setdefault(frame_name, {})
                entry.setdefault("quads", []).append(
                    {"corners": [[float(u_px), float(v_px)] for u_px, v_px in corners_px], "class_mm": float(class_mm), "class_source": cls.ASPECT_SOURCE})
                Config.Document.write(era_directory / cls.DOCUMENT, doc)
                return class_mm

            @classmethod
            def drop_last(cls, era_directory: Path, frame_name: str) -> bool:
                """그 장의 마지막 사각형을 뺀다. 뺄 것이 없으면 거짓이다."""
                doc = cls._document(era_directory)
                quads = doc.get("images", {}).get(frame_name, {}).get("quads", [])
                if not quads: return False
                quads.pop()
                Config.Document.write(era_directory / cls.DOCUMENT, doc)
                return True

        def read_era(self, era_directory: Path) -> dict[str, Any] | None:
            """회차 문서. 파일이 없으면 `None`."""
            path = era_directory / self.era_document
            if not path.is_file(): return None
            return Config.Document.read(path)

        def write_era(self, era_directory: Path, doc: dict[str, Any]) -> None:
            """회차 문서를 쓴다."""
            Config.Document.write(era_directory / self.era_document, doc)

        def create_era(self, when: datetime.datetime, doc: dict[str, Any]) -> "Config.Dataset.Era":
            """새 회차를 만든다. 문서는 그 순간의 현행 값 사본이다.

            이름은 당일 비어 있는 첫 순번이다. 순번은 꼬리 설명을 떼고 가르므로 `_era_260908a_spc` 가 `a` 를 차지한다.
            """
            day = self.storage_format.era_day(when)
            taken = {era.index for era in self.eras() if era.day == day}
            index = next(index for index in range(1, self.storage_format.max_daily_count + 1) if index not in taken)
            era_directory = self.captures_dir / self.storage_format.era_name(when, index)
            era_directory.mkdir()
            self.write_era(era_directory, doc)
            return self.Era.parse(era_directory, storage_format=self.storage_format)


# =========================================================================
# 3. 개체 자료형
# =========================================================================


class Entity:
    """계통끼리 주고받는 개체. 한 관측마다 새로 세운다.

    - `Lump` :: 분할 이전의 흰 덩어리. 블록 몇 개인지, 사람 손이나 로봇 팔인지 모른다
    - `Piece` :: 분할과 적합이 끝난 블록 하나. 로봇에 넘기는 단위다
    """

    # ------------------------------------------------------------------
    # 1. 분할 이전
    # ------------------------------------------------------------------

    @dataclass(frozen=True)
    class Lump:
        """흰 덩어리 하나. 전경 마스크의 연결 성분 하나에 대응한다."""

        contour_px: tuple[tuple[float, float], ...]  # 관측된 전경 윤곽
        area_mm2: float  # 상면 면적. 사영이 위치마다 다른 축척을 주므로 계측 엔진이 H35 로 적분해 낸다

        @cached_property
        def perimeter_px(self) -> float:
            """전경 윤곽의 둘레, 화소. 프레임 차분 잡음이 경계에서 생기므로 움직임 판정 문턱의 원천이다."""
            return sum(itertools.starmap(math.dist, Tool.closed_edges(self.contour_px)))

    # ------------------------------------------------------------------
    # 2. 분할 이후
    # ------------------------------------------------------------------

    @dataclass(frozen=True)
    class Piece:
        """블록 하나. 분할과 사각형 적합이 확정한 사실을 담는다."""
        class Pose(NamedTuple):
            """상면 물리 평면에서의 자세. 각도는 적합된 장축 방위의 원시값이다."""

            x_mm: float
            y_mm: float
            angle_deg: float

        tag: int  # 프레임 간 대조를 위한 임시 번호
        pose: "Entity.Piece.Pose"
        length_mm: float  # 적합 사각형의 장축. 규격이 가려지면 그 규격의 길이다 — 마스크 경계가 안쪽으로 물러나 관측 치수는 짧게 재진다
        width_mm: float  # 적합 사각형의 단축. 종횡비의 분모
        corners_px: tuple[tuple[float, float], ...]  # 적합 사각형 네 꼭짓점. 화면 묘사와 사후 확인의 근거
        block: Config.Product.Block | None  # 규격 3종 중 하나. 가려지지 않았으면 부재

        # --------------------------------------------------- 규격 조회

        @cached_property
        def is_spec_resolved(self) -> bool:
            """규격이 가려졌는가. 가려지지 않은 개체는 집지 않는다."""
            return self.block is not None

        def require_block(self) -> Config.Product.Block:
            """확정 규격. 흡착 허용 오차가 규격마다 달라 미확정이면 예외를 던진다."""
            if self.block is None: raise Tool.Missing(f"꼬리표 {self.tag} 의 규격 미확정 — 집을 수 없다")
            return self.block

        # --------------------------------------------------- 관측 유도

        @cached_property
        def aspect_ratio_observed(self) -> float:
            """관측 종횡비. 축척을 몰라도 성립하는 무차원량이라 규격 교차 검증에 쓴다."""
            return self.length_mm / self.width_mm

        @cached_property
        def perimeter_px(self) -> float:
            """적합 사각형의 둘레, 화소."""
            return sum(itertools.starmap(math.dist, Tool.closed_edges(self.corners_px)))

        def center_distance_mm(self, other: "Entity.Piece") -> float:
            """두 개체 중심 사이 상면 거리."""
            return math.hypot(self.pose.x_mm - other.pose.x_mm, self.pose.y_mm - other.pose.y_mm)

        # --------------------------------------------------- 겹침 기하

        @cached_property
        def corners_mm(self) -> tuple[tuple[float, float], ...]:
            """상면 물리 평면에서의 네 꼭짓점. 반시계 방향이며, 겹침 계산은 이 좌표로 한다."""
            x_mm, y_mm, angle_deg = self.pose
            half_l, half_w = self.length_mm / 2.0, self.width_mm / 2.0
            rad = math.radians(angle_deg)
            cos_t, sin_t = math.cos(rad), math.sin(rad)
            return tuple(
                (
                    x_mm + (sign_length * half_l) * cos_t - (sign_width * half_w) * sin_t,
                    y_mm + (sign_length * half_l) * sin_t + (sign_width * half_w) * cos_t,
                )
                for sign_length, sign_width in ((1.0, 1.0), (-1.0, 1.0), (-1.0, -1.0), (1.0, -1.0))
            )

        @cached_property
        def area_mm2(self) -> float:
            """적합 사각형(외접 사각형)의 상면 면적."""
            return self.length_mm * self.width_mm

        def intersection_mm(self, other: "Entity.Piece") -> tuple[tuple[float, float], ...]:
            """두 적합 사각형이 겹치는 영역의 꼭짓점. 겹치지 않으면 빈 튜플이다.

            화면에 겹침을 칠하려면 이 점들을 `Homography.to_image` 로 화소로 보낸다.
            """
            polygon = Tool.Geometry.Polygon
            overlap = self.corners_mm
            for start, end in Tool.closed_edges(other.corners_mm):
                overlap = polygon.half_plane_clipped(overlap, start, polygon.inward_normal(start, end), 0.0)
            return overlap

        def intersection_area_mm2(self, other: "Entity.Piece") -> float:
            """겹치는 면적."""
            return abs(Tool.Geometry.Polygon.signed_area(self.intersection_mm(other)))

        def iou(self, other: "Entity.Piece") -> float:
            """합집합 대비 교집합 비. 실루엣 정합 · 조합 탐색에 쓴다. 겹침 판정은 `overlap_ratio`."""
            overlap_mm2 = self.intersection_area_mm2(other)
            union_mm2 = self.area_mm2 + other.area_mm2 - overlap_mm2
            return overlap_mm2 / union_mm2

        def overlap_ratio(self, other: "Entity.Piece") -> float:
            """더 작은 쪽 면적 대비 교집합 비. `LabelAudit.is_intruded` 가 받는 값이다.

            작은 사각이 큰 사각에 온전히 들어가면 1 이 된다.
            겹침이 한 변을 따라 폭 $j$ 의 띠로 생기면 $j / W$ 가 되어 규격과 무관하다.
            """
            return self.intersection_area_mm2(other) / min(self.area_mm2, other.area_mm2)

        def clearance_mm(self, other: "Entity.Piece") -> float:
            r"""두 블록 발자국 사이의 틈. 맞닿으면 0, 음수면 그만큼 겹친 것이다 — 공면 위 블록은 겹칠 수 없으므로 음수는 물리로 있을 수 없는 자세다.

            발자국은 모서리 필렛 때문에 네 귀가 반경 $r$ 로 둥근 직사각형이고, 이는 두 변에서 $r$ 씩 뺀 속 사각형에 반경 $r$ 원을 민 모양이다.
            그러므로 틈은 두 속 사각형 사이의 거리에서 두 반경을 뺀 것이다 — 귀끼리 비스듬히 닿는 경우까지 정확하다.
            속 사각형이 떨어져 있으면 거리는 꼭짓점과 변 사이 거리의 최솟값이고, 겹쳐 있으면 분리축(두 사각형 변의 법선 넷)으로 잰 침투 깊이를 음수로 쓴다.
            """
            def inner(piece):
                r_mm = piece.require_block().fillet_r_mm
                return dataclasses.replace(piece, length_mm=piece.length_mm - 2.0 * r_mm, width_mm=piece.width_mm - 2.0 * r_mm).corners_mm, r_mm

            (first, first_r_mm), (second, second_r_mm) = inner(self), inner(other)
            axes = [(start[1] - end[1], end[0] - start[0]) for start, end in (*Tool.closed_edges(first), *Tool.closed_edges(second))]
            gaps = []
            for axis_x, axis_y in axes:
                length = math.hypot(axis_x, axis_y)
                first_span = [(x * axis_x + y * axis_y) / length for x, y in first]
                second_span = [(x * axis_x + y * axis_y) / length for x, y in second]
                gaps.append(max(min(second_span) - max(first_span), min(first_span) - max(second_span)))
            separation_mm = max(gaps)
            if separation_mm < 0.0:
                return separation_mm - first_r_mm - second_r_mm

            def to_segment(point, start, end):
                along_x, along_y = end[0] - start[0], end[1] - start[1]
                ratio = max(0.0, min(1.0, ((point[0] - start[0]) * along_x + (point[1] - start[1]) * along_y) / (along_x * along_x + along_y * along_y)))
                return math.dist(point, (start[0] + ratio * along_x, start[1] + ratio * along_y))

            distance_mm = min(min(to_segment(point, start, end) for point in first for start, end in Tool.closed_edges(second)),
                              min(to_segment(point, start, end) for point in second for start, end in Tool.closed_edges(first)))
            return distance_mm - first_r_mm - second_r_mm

        def is_same(self, other: "Entity.Piece") -> bool:
            """같은 블록인가. 발자국이 겹치면 같은 블록이다 — 공면 위의 다른 블록끼리는 겹칠 수 없다(`clearance_mm`)."""
            return self.clearance_mm(other) < 0.0

        @staticmethod
        def paired(previous: Sequence["Entity.Piece"], current: Sequence["Entity.Piece"]) -> tuple[int | None, ...]:
            """이번 개체마다 이어지는 직전 개체의 차례. 이어지는 것이 없으면 `None` 이다.

            발자국이 겹치면 같은 블록이다(`is_same`). 짝은 하나씩만 잇고, 겹친 깊이가 큰 쌍부터 잇는다.
            같은 블록은 발자국이 거의 다 겹치고 맞닿은 이웃과는 적합 흔들림만큼만 겹치므로, 깊이 차례가 둘을 가른다.
            """
            depths = sorted(((-now.clearance_mm(before), now_index, before_index)
                             for now_index, now in enumerate(current) for before_index, before in enumerate(previous)), reverse=True)
            continued: list[int | None] = [None] * len(current)
            taken = set()
            for depth_mm, now_index, before_index in depths:
                if depth_mm <= 0.0: break
                if continued[now_index] is None and before_index not in taken:
                    continued[now_index] = before_index
                    taken.add(before_index)
            return tuple(continued)


    @dataclass(frozen=True)
    class Scene:
        """한 프레임의 관측 결과 한 벌. 프레임마다 새로 세우고 쌓지 않는다.

        비전이 채우고 로봇과 화면이 읽는다.
        아직 부품이 없는 자리는 `None` 으로 남는다 — 무엇이 오게 되는지를 지금 정해 두려고 자리를 세워 둔다.
        """

        source_name: str
        index: int
        frame_name: str
        image: Any                              # 원본 BGR
        preprocessed: Any | None = None         # 고른 전처리 갈래의 결과
        rectified: Any | None = None            # 상면 평면으로 편 그림
        rectify_matrix: Any | None = None       # 원본 화소 → 편 그림 화소
        masks: dict[str, Any] | None = None     # 층 이름 → 이진 마스크
        lumps: tuple = ()                       # 분할 이전 덩어리
        pieces: tuple = ()                      # 규격과 자세가 확정된 블록
        rejected: tuple = ()                    # 규격에 맞지 않아 집지 않는 덩어리
        score: dict[str, Any] | None = None

        def mask(self, key: str): return (self.masks or {}).get(key)

    class AcousticFrame(NamedTuple):
        """한 순간의 음향 관측 한 벌.

        `freqs` 와 `power` 는 같은 길이의 배열이고 짝으로만 뜻이 있다.
        판정에 쓰이는 대역 평균이나 봉우리는 여기 담지 않는다 — 무엇을 잴지는 보는 쪽이 정한다.
        """

        freqs: Any              # 주파수 축 (Hz)
        power: Any              # 한쪽 전력 스펙트럼
        total_power_db: float   # 전대역 평균 전력 (dB)
        fs: int                 # 이 관측을 뜬 표본율 (Hz). 장치가 정한다
        at: float               # 단조 시계 시각 (초)


# =========================================================================
# 4. 바깥과의 연결
# =========================================================================


class Connect:
    """바깥과 주고받는 일. 무엇에 붙느냐로 갈린다.

    장치에 붙는 것과, 남이 만든 코드에 우리를 맞추는 것은 성격이 다르다.
    규약이 정한 대로 주고받는 데까지가 여기이고, 무엇을 어떤 차례로 보낼지는 부르는 쪽이 정한다.
    """

    class Device:
        """장치에 붙는다."""

        class PLC:
            """LS PLC 하나."""

            # =================================================================
            # 통신 — Modbus 만 안다
            # =================================================================

            class Protocol:
                """말하는 법."""

                class Modbus:
                    """펑션코드를 태운다. 디바이스 표기를 모른다. 주소와 개수만 받는다."""

                    class FC(IntEnum):
                        """Modbus 펑션코드. 값이 곧 코드다."""

                        READ_COILS = 0x01
                        READ_DISCRETE_INPUTS = 0x02
                        READ_HOLDING_REGISTERS = 0x03
                        READ_INPUT_REGISTERS = 0x04
                        WRITE_SINGLE_COIL = 0x05
                        WRITE_SINGLE_REGISTER = 0x06
                        WRITE_MULTIPLE_COILS = 0x0F
                        WRITE_MULTIPLE_REGISTERS = 0x10

                    #: 코드마다 pymodbus 에서 부를 것과 답에서 꺼낼 자리. 쓰기는 꺼낼 것이 없다
                    CALL = {FC.READ_COILS: ("read_coils", "bits"),
                            FC.READ_DISCRETE_INPUTS: ("read_discrete_inputs", "bits"),
                            FC.READ_HOLDING_REGISTERS: ("read_holding_registers", "registers"),
                            FC.READ_INPUT_REGISTERS: ("read_input_registers", "registers"),
                            FC.WRITE_SINGLE_COIL: ("write_coil", None),
                            FC.WRITE_SINGLE_REGISTER: ("write_register", None),
                            FC.WRITE_MULTIPLE_COILS: ("write_coils", None),
                            FC.WRITE_MULTIPLE_REGISTERS: ("write_registers", None)}

                    client: Any  # 말을 실어 나르는 것

                    def __init__(self, client: Any) -> None:
                        self.client = client

                    def link(self, function_code: "Connect.Device.PLC.Protocol.Modbus.FC", address: int, payload: Any = None, count: int = 1) -> Any:
                        """펑션코드 하나를 태운다. 읽기는 값을, 쓰기는 `None` 을 돌려준다."""
                        call, field = self.CALL[function_code]
                        reply = (getattr(self.client, call)(address, payload) if field is None
                                 else getattr(self.client, call)(address, count=count))
                        return None if field is None else getattr(reply, field)[:count]

            # =================================================================
            # 자료 — LS 디바이스만 안다
            # =================================================================

            class Data:
                """무엇이 있는가."""

                class LS:
                    """LS 디바이스의 세계.

                    **인스턴스화하지 않는다.**
                    여기 실린 것은 LS 가 정한 표기라 PLC 가 몇 대든 한 벌이기 때문이다.
                    대마다 다른 것(붙는 길 · 영역 기준점 · 래더 약속)은 `Controller` 가 든다.
                    """

                    plc_ls: "Config.Communication.PlcLs"  # LS 표기 규칙(`communication.plc_ls`) — 워드 비트 수(`word_bits`)와 디바이스 글자마다 끝 한 자리가 비트인가(`devices.<글자>.bit_tail`)

                    #: 이 스레드가 지금 상대하는 PLC.
                    #:
                    #: 클래스에 칸을 하나만 두면 워커 둘이 같은 칸을 써서 **나중에 붙은 쪽이 앞사람을 밀어낸다** — 둘 다 제 일을 옳게 해도 조용히 다른 PLC 를 읽는다.
                    #: 스레드마다 칸을 따로 두면 그 일이 구조적으로 안 생긴다.
                    #: 워커 하나가 장치 하나를 독점하는 것이 이 설계의 전제라 칸과 일꾼이 짝이다.
                    #:
                    #: 지키는 것 :: **한 워커가 두 Controller 를 번갈아 쓰지 않는다.**
                    #: 그러면 같은 줄이 때에 따라 다른 PLC 를 읽는다.
                    #: 안 앉힌 스레드에서 부르면 터지므로 모르고 지나갈 일은 없다.
                    talking_to = threading.local()

                    @classmethod
                    def define(cls, plc_ls: "Config.Communication.PlcLs") -> None:
                        """LS 표기 규격을 세운다. 몇 대가 붙든 같은 값이라 여러 번 불러도 같다."""
                        cls.plc_ls = plc_ls

                    @classmethod
                    def current(cls) -> "Connect.Device.PLC.Data.LS.Controller":
                        """이 스레드가 상대하는 PLC. 안 정해졌으면 알린다 — 조용히 넘기지 않는다."""
                        one = getattr(cls.talking_to, "controller", None)
                        if one is None: raise Tool.Missing("이 스레드가 상대할 PLC 가 정해지지 않았다 — `Controller.open()` 이 먼저다")
                        return one

                    # =========================================================
                    # PLC 한 대
                    # =========================================================

                    class Controller:
                        """LS PLC 한 대. 붙는 것도 끊는 것도 이것이 한다.

                        **붙는 자리에서 자기를 그 스레드의 상대로 앉힌다.**
                        세우는 것과 붙는 것이 다른 스레드일 수 있어서다 — 워커를 만드는 것은 화면 쪽이고 붙는 것은 워커 자신이다.
                        세울 때 앉히면 화면 스레드의 칸에 들어가 워커가 못 찾는다.

                        수명이 렉시컬한 자리(임시 드라이버 · 한 번 읽고 마는 검사)에서는 `with` 가 닫아 준다.
                        사람이 누를 때 붙고 누를 때 끊는 자리에서는 `close` 를 직접 부른다 — 그쪽은 감쌀 블록이 없다.
                        """

                        plc_controller: "Config.Communication.PlcController"  # 이 PLC 의 정본(`communication.plc_controller` 의 한 항목)
                        modbus: "Connect.Device.PLC.Protocol.Modbus | None"  # 붙어 있을 때만 있다
                        base: dict["Config.Communication.PlcController.Area", int]

                        def __init__(self, plc_ls: "Config.Communication.PlcLs", plc_controller: "Config.Communication.PlcController") -> None:
                            """규격을 받는다. 아직 안 붙는다."""
                            LS = Connect.Device.PLC.Data.LS
                            LS.define(plc_ls)   # 표기가 서야 아래에서 디바이스를 읽을 수 있다

                            self.plc_controller, self.modbus = plc_controller, None
                            # 영역이 시작하는 자리.
                            # 표기로 적혀 있으므로 디바이스로 읽어 LS 자리를 꺼낸다.
                            # Modbus 주소는 여기서부터 센 거리다 — `relay` 가 이것을 뺀다
                            self.base = {area: LS.Device(plc_controller.area_start[area.name.lower()]).path
                                         for area in Config.Communication.PlcController.Area}

                        # ----------------------------------------------- 수명

                        def open(self) -> bool:
                            """붙는다. 붙었으면 이 스레드의 상대로 앉는다."""
                            from pymodbus.client import ModbusSerialClient as pymodbus_ModbusSerialClient, ModbusTcpClient as pymodbus_ModbusTcpClient

                            way = self.plc_controller.transport
                            client = (pymodbus_ModbusTcpClient(way.host, port=way.port)
                                      if way.transport == "tcp" else
                                      pymodbus_ModbusSerialClient(way.serial_port,
                                                         baudrate=way.serial_baudrate__bps))
                            if not client.connect():
                                client.close()
                                return False

                            self.modbus = Connect.Device.PLC.Protocol.Modbus(client)
                            Connect.Device.PLC.Data.LS.talking_to.controller = self
                            return True

                        def close(self) -> None:
                            """소켓을 놓아준다. 게이트웨이가 접속 수를 세므로 재연결 전에 비운다."""
                            if self.modbus is not None:
                                self.modbus.client.close()
                                self.modbus = None

                            talking = Connect.Device.PLC.Data.LS.talking_to
                            if getattr(talking, "controller", None) is self:
                                talking.controller = None

                        def __enter__(self) -> "Connect.Device.PLC.Data.LS.Controller":
                            if not self.open(): raise Tool.Missing(f"PLC 에 닿지 못했다 :: {self.plc_controller.transport.host}")
                            return self

                        def __exit__(self, *_: Any) -> None: self.close()

                        def __repr__(self) -> str:
                            way = self.plc_controller.transport
                            state = "붙음" if self.modbus is not None else "끊김"
                            return f"Controller({way.host}:{way.port} {state})"

                    # LS 자리를 Modbus 주소로 옮기는 일.
                    # 두 계통이 만나는 자리라 어느 쪽도 혼자 못 한다 — `Device` 는 LS 만 알고 `Modbus` 는 Modbus 만 안다.
                    # 읽기와 쓰기가 기준점이 다르므로 무엇을 하는지 아는 이 자리에서 옮긴다

                    @classmethod
                    def relay(cls, one: "Connect.Device.PLC.Data.LS.Device", payload: Any = None, count: int = 1) -> Any:
                        """값을 안 건네면 받아 오고, 건네면 보낸다.

                        `one` 에서 이어지는 자리를 한 번에 다룬다 — 읽기는 `count` 개, 쓰기는 목록을 건네면 그 길이만큼이다.
                        래더가 워드를 묶어 내놓으므로 한 자리씩 왕복할 까닭이 없다.

                        어느 PLC 에 묻는지는 **이 스레드의 상대**가 정한다.
                        """
                        ModbusFunction = Connect.Device.PLC.Protocol.Modbus.FC
                        Area = Config.Communication.PlcController.Area
                        ctrl = cls.current()
                        coil = cls.plc_ls.devices[one.type].bit_tail

                        if payload is None:
                            function_code = ModbusFunction.READ_COILS if coil else ModbusFunction.READ_HOLDING_REGISTERS
                            area = Area.BIT_READ if coil else Area.WORD_READ
                            return ctrl.modbus.link(function_code, one.path - ctrl.base[area], count=count)

                        many = isinstance(payload, (list, tuple))
                        if coil:
                            function_code = ModbusFunction.WRITE_MULTIPLE_COILS if many else ModbusFunction.WRITE_SINGLE_COIL
                            payload = [bool(word) for word in payload] if many else bool(payload)
                            area = Area.BIT_WRITE
                        else:
                            function_code = ModbusFunction.WRITE_MULTIPLE_REGISTERS if many else ModbusFunction.WRITE_SINGLE_REGISTER
                            payload = [int(word) for word in payload] if many else int(payload)
                            area = Area.WORD_WRITE
                        ctrl.modbus.link(function_code, one.path - ctrl.base[area], payload)
                        return None

                    class Device:
                        """디바이스 하나. 워드 디바이스면 워드, 비트 디바이스면 비트 하나다."""

                        class Bit:
                            """워드 안의 한 자리. 스스로 통신하지 않고 부모의 `value` 를 통해 본다."""

                            parent: "Connect.Device.PLC.Data.LS.Device"  # 이 자리가 들어 있는 워드
                            at: int                       # 워드 안의 자리

                            def __init__(self, parent: "Connect.Device.PLC.Data.LS.Device", at: int) -> None:
                                self.parent, self.at = parent, at

                            @property
                            def value(self) -> bool:
                                return bool((self.parent.value >> self.at) & 1)

                            @value.setter
                            def value(self, bit_state: Any) -> None:
                                """읽어서 이 자리만 고쳐 되쓴다. 부모의 `value` 가 통신을 다 한다."""
                                self.parent.value = ((self.parent.value & ~(1 << self.at))
                                                     | (bool(bit_state) << self.at))

                            def __bool__(self) -> bool: return bool(self.value)
                            def __int__(self) -> int: return int(self.value)
                            def __repr__(self) -> str: return f"{self.parent!r}.{self.at:X}"
                            def __eq__(self, other: Any) -> bool:
                                return (isinstance(other, Connect.Device.PLC.Data.LS.Device.Bit)
                                        and self.parent == other.parent and self.at == other.at)

                        type: str  # 디바이스 글자
                        path: int  # LS 자리. 워드 디바이스면 워드 번호, 비트 디바이스면 비트 번호

                        # ------------------------------------------------- 표기 읽기

                        def __new__(cls, tag: str) -> Any:
                            # 점이 있으면 워드 안의 자리다. 워드를 만들어 감싸 돌려준다.
                            # 워드형 글자일 때만이다 — 비트 디바이스는 끝 자리가 이미 비트다
                            text = tag.strip().upper()
                            letter, address_string = text[0], text[1:]
                            if "." in address_string and not Connect.Device.PLC.Data.LS.plc_ls.devices[letter].bit_tail:
                                word_number, bit_offset = address_string.split(".", 1)
                                return cls.Bit(cls(f"{letter}{word_number}"), int(bit_offset, 16))
                            return super().__new__(cls)

                        def __init__(self, tag: str) -> None:
                            # 비트 디바이스는 끝 한 자리가 16진 비트고 앞이 워드다.
                            # 자릿수는 아무 값이나 와도 된다 — 비트 디바이스를 워드로 읽을 일이 없어 가를 것이 없다
                            text = tag.strip().upper()
                            self.type, address_string = text[0], text[1:]
                            if Connect.Device.PLC.Data.LS.plc_ls.devices[self.type].bit_tail:
                                self.path = int(address_string[:-1] or 0) * Connect.Device.PLC.Data.LS.plc_ls.word_bits + int(address_string[-1], 16)
                            else:
                                self.path = int(address_string)

                        # ------------------------------------------------- 값

                        @property
                        def value(self) -> Any:
                            """지금 PLC 에 있는 값. 들고 있지 않고 부를 때마다 묻는다."""
                            return Connect.Device.PLC.Data.LS.relay(self)[0]

                        @value.setter
                        def value(self, new_value: Any) -> None:
                            Connect.Device.PLC.Data.LS.relay(self, new_value)

                        # ------------------------------------------------- 값처럼 굴기

                        def __call__(self, at: int) -> "Connect.Device.PLC.Data.LS.Device.Bit": return self.Bit(self, at)
                        def __getitem__(self, at: int) -> "Connect.Device.PLC.Data.LS.Device.Bit": return self.Bit(self, at)
                        def __bool__(self) -> bool: return bool(self.value)
                        def __int__(self) -> int: return int(self.value)
                        def __eq__(self, other: Any) -> bool:
                            return (isinstance(other, Connect.Device.PLC.Data.LS.Device)
                                    and self.type == other.type and self.path == other.path)

                        def __repr__(self) -> str:
                            if not Connect.Device.PLC.Data.LS.plc_ls.devices[self.type].bit_tail:
                                return f"{self.type}{self.path}"
                            word_number, bit_offset = divmod(self.path, Connect.Device.PLC.Data.LS.plc_ls.word_bits)
                            return f"{self.type}{word_number}{bit_offset:X}"

        class Robot:
            """GRBL 계열 로봇 컨트롤러와 시리얼로 주고받는 연결 하나.

            한 줄 보내고 종결자가 보이면 즉시 돌아온다 — 고정 시간을 기다리면 응답이 빨라도 그 시간을 다 쓰게 되어 상태 폴링이 통째로 느려진다.
            무엇을 어떤 차례로 보낼지는 부르는 쪽이 정한다.
            """

            robot_serial: Config.Communication.RobotSerial
            serial: Any = None

            def __init__(self, robot_serial: Config.Communication.RobotSerial) -> None:
                self.robot_serial = robot_serial

            @property
            def is_open(self) -> bool: return self.serial is not None

            @property
            def port(self) -> str: return self.serial.port if self.serial is not None else ""

            def connect(self) -> str:
                """포트를 열고 `$I` 에 돌아온 것을 **원문 그대로** 돌려준다.

                판정하지 않는다 — 답이 없으면 빈 문자열이 나온다.
                이것을 연결로 칠지는 부르는 쪽이 정한다.

                읽기 제한 시간을 건다 — 걸지 않으면 `readline` 이 줄바꿈을 무한정 기다려, 케이블이 빠지면 부르는 쪽이 그대로 멎는다.
                """
                self.close()
                self.serial = Connect.Device.Usb.open_serial(
                    self.robot_serial.device_ids, self.robot_serial.baudrate__bps,
                    self.robot_serial.dtr_enable, self.robot_serial.rts_enable,
                )
                self.serial.timeout = self.robot_serial.query_timeout__s
                # 포트를 열면 컨트롤러가 부팅 문자열을 뱉는다. 다 나올 때까지 두고 버린다
                time.sleep(self.robot_serial.boot_settle__s)
                self.serial.reset_input_buffer()
                return self.ask("$I", self.robot_serial.gcode.ack)

            def close(self) -> None:
                """포트를 놓는다.

                닫기는 뒷정리다.
                **이미 죽은 포트를 닫으려다 난 오류로 앞길을 막지 않는다** — 이 메서드는 재연결의 첫 줄에서도 불리므로, 여기서 예외를 올리면 복구 경로가 함께 막힌다.
                다만 받는 것은 포트가 이미 없거나 핸들이 무효인 경우뿐이고, 그 밖의 오류는 올린다.
                """
                if self.serial is None: return
                try: self.serial.close()
                except (OSError, ValueError): pass
                finally:
                    self.serial = None

            def ask(self, command: str, until: str) -> str:
                """한 줄 보내고 종결자가 보일 때까지 읽는다. 상한은 질의 제한 시간이다."""
                if self.serial is None: return ""
                self.serial.reset_input_buffer()
                self.serial.write((command + "\r\n").encode("utf-8"))
                deadline = time.monotonic() + self.robot_serial.query_timeout__s
                chunks: list[str] = []
                while time.monotonic() < deadline:
                    if self.serial.in_waiting:
                        chunks.append(self.serial.readline().decode("utf-8", "replace"))
                        if until in "".join(chunks): break
                        continue
                    time.sleep(self.robot_serial.probe_poll__ms / 1000.0)
                return "".join(chunks)

            def send(self, command: str) -> tuple[str, str]:
                """한 줄 보내고 접수 여부를 판정한다. 돌려주는 것 :: (`ok` · `error` · `none`, 원문).

                `ok` 는 **명령을 받았다**는 뜻이다.
                목표가 지금 자리와 같으면 컨트롤러는 `ok` 를 주고 아무것도 하지 않는다.
                """
                raw = self.ask(command, self.robot_serial.gcode.ack)
                low = raw.lower()
                if "error" in low or self.robot_serial.is_alarm_response(low):
                    return "error", raw
                return ("ok" if self.robot_serial.gcode.ack.lower() in low else "none"), raw

            def write_bytes(self, payload: bytes) -> None:
                """제어 바이트를 그대로 보낸다. 일시 정지와 소프트 리셋이 쓴다."""
                if self.serial is not None: self.serial.write(payload)

            def status(self) -> "Connect.Device.Robot.Status | None":
                """상태 보고 한 번. 꼴이 아니면 `None`."""
                return self.parse(self.ask(self.robot_serial.gcode.status_query, self.robot_serial.terminator))

            class Status(NamedTuple):
                """상태 보고 한 번의 결과.

                각도는 관절 도, 직교는 mm 와 도다. 펌프 · 밸브는 컨트롤러 PWM 눈금이라 단위가 없다.
                """

                state: str                       # Idle · Run · Alarm …
                angles_deg: tuple[float, ...]
                cartesian: tuple[float, ...]     # X Y Z mm · Rx Ry Rz deg
                pump_pwm: int
                valve_pwm: int
                at: float                        # 받은 시각 (단조 시계)

            def parse(self, response_text: str) -> "Connect.Device.Robot.Status | None":
                """상태 보고 한 줄을 뜯는다.

                보고는 `<상태,Angle(ABCDXYZ):…,Cartesian coordinate(XYZ RxRyRz):…,Pump PWM:…>` 모양이다.
                앞머리가 상태 이름이고 괄호 뒤 콜론부터 쉼표로 끊긴 수가 따라온다.
                """
                if "<" not in response_text: return None
                state = response_text[response_text.index("<") + 1:].split(",", 1)[0].strip() or "미상"

                def numbers(tag: str) -> tuple[float, ...]:
                    tag_position = response_text.find(tag)
                    if tag_position < 0: return ()
                    tail = response_text[tag_position + len(tag):]
                    tail = tail.split(":", 1)[1] if ":" in tail.split(",")[0] else tail
                    parsed_numbers: list[float] = []
                    for token in tail.split(","):
                        try: parsed_numbers.append(float(token.strip().rstrip(">")))
                        except ValueError: break
                    return tuple(parsed_numbers)

                def integer(tag: str) -> int:
                    tag_position = response_text.find(tag)
                    if tag_position < 0: return 0
                    tail = response_text[tag_position + len(tag):].split(":", 1)
                    if len(tail) < 2: return 0
                    digits = ""
                    for character in tail[1].strip():
                        if character.isdigit() or (character == "-" and not digits): digits += character
                        else: break
                    return int(digits) if digits.lstrip("-") else 0

                return Connect.Device.Robot.Status(
                    state=state,
                    angles_deg=numbers(self.robot_serial.gcode.report_angles_tag),
                    cartesian=numbers(self.robot_serial.gcode.report_cartesian_tag),
                    pump_pwm=integer(self.robot_serial.gcode.report_pump_tag),
                    valve_pwm=integer(self.robot_serial.gcode.report_valve_tag),
                    at=time.monotonic(),
                )

            def is_alarm(self, status: "Connect.Device.Robot.Status | None") -> bool:
                """호밍 전과 소프트 리셋 뒤의 정상 응답이다."""
                return status is not None and self.robot_serial.is_alarm(status.state)

        class Usb:
            """USB 장치를 VID/PID(/MI) 로 찾아 연다. 무슨 장치인지는 부르는 쪽이 정한다."""

            class Id(NamedTuple):
                """`VID_8086&PID_0B5C&MI_03`. MI 가 없으면 인터페이스를 가리지 않는다."""

                vid: str
                pid: str
                mi: str | None

                @classmethod
                def parse(cls, text: str) -> "Connect.Device.Usb.Id":
                    usb_match = re.search(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})(?:&MI_([0-9A-F]{2}))?", text.upper())
                    if usb_match is None: raise ValueError(f"USB 장치 식별자가 아니다: {text}")
                    return cls(*usb_match.groups())

                @property
                def text(self) -> str:
                    return f"VID_{self.vid}&PID_{self.pid}" + ("" if self.mi is None else f"&MI_{self.mi}")

                def matches(self, target_id: "Connect.Device.Usb.Id") -> bool:
                    return (self.vid, self.pid) == (target_id.vid, target_id.pid) and self.mi in (None, target_id.mi)

            class Entry(NamedTuple):
                """JSON 의 장치 한 건. 이름은 사람이 읽는 자리다."""

                id: "Connect.Device.Usb.Id"
                name: str

            @staticmethod
            def entries(device_ids: Sequence[Mapping[str, Any]]) -> tuple["Connect.Device.Usb.Entry", ...]:
                """설정의 장치 목록(항목마다 `id` · `name`)을 대장 항목으로 — 식별자 글자를 푼다."""
                return tuple(Connect.Device.Usb.Entry(Connect.Device.Usb.Id.parse(str(device["id"])), str(device["name"])) for device in device_ids)

            @staticmethod
            def _missing(entries: Sequence["Connect.Device.Usb.Entry"]) -> LookupError:
                return LookupError("연결된 USB 장치가 없다 :: " + " · ".join(entry.name for entry in entries))

            # ------------------------------------------------------ 시리얼

            @staticmethod
            def serial_port(entries: Sequence["Connect.Device.Usb.Entry"]) -> str:
                """맞는 시리얼 포트 이름. 목록 앞의 장치부터 찾는다."""
                from serial.tools.list_ports import comports as serial_comports

                available_ports = [port for port in serial_comports() if port.vid is not None]
                for entry in entries:
                    for port in available_ports:
                        if entry.id.matches(Connect.Device.Usb.Id(f"{port.vid:04X}", f"{port.pid:04X}", None)):
                            return port.device
                raise Connect.Device.Usb._missing(entries)

            @staticmethod
            def open_serial(entries: Sequence["Connect.Device.Usb.Entry"], baudrate_bps: int, dtr: bool, rts: bool) -> Any:
                """시리얼 포트를 연다. DTR · RTS 는 열기 전에 정한다."""
                from serial import Serial as serial_Serial

                link = serial_Serial()
                link.port = Connect.Device.Usb.serial_port(entries)
                link.baudrate = baudrate_bps
                link.dtr, link.rts = dtr, rts
                link.open()
                return link

            # ------------------------------------------------------ 카메라

            @staticmethod
            def camera_ids() -> tuple["Connect.Device.Usb.Id | None", ...]:
                """DirectShow 영상 장치 열거 순서대로의 식별자. OpenCV 장치 번호가 이 순서다. USB 가 아니면 `None`."""
                from comtypes import COMError as comtypes_COMError, GUID as comtypes_GUID
                from comtypes.persist import IPropertyBag as comtypes_IPropertyBag
                from pygrabber.dshow_graph import SystemDeviceEnum as pygrabber_SystemDeviceEnum
                from pygrabber.dshow_ids import DeviceCategories as pygrabber_DeviceCategories

                category = comtypes_GUID(pygrabber_DeviceCategories.VideoInputDevice)
                enum = pygrabber_SystemDeviceEnum().system_device_enum.CreateClassEnumerator(category, dwFlags=0)
                camera_device_ids = []
                moniker, count = enum.Next(1)
                while count > 0:
                    try:
                        bag = moniker.BindToStorage(0, 0, comtypes_IPropertyBag._iid_).QueryInterface(comtypes_IPropertyBag)
                        path = bag.Read("DevicePath", pErrorLog=None)
                    except comtypes_COMError:
                        path = ""
                    try: camera_device_ids.append(Connect.Device.Usb.Id.parse(path))
                    except ValueError: camera_device_ids.append(None)
                    moniker, count = enum.Next(1)
                return tuple(camera_device_ids)

            @staticmethod
            def find_camera(entries: Sequence["Connect.Device.Usb.Entry"]) -> tuple[int, "Connect.Device.Usb.Entry"]:
                """맞는 카메라의 OpenCV 장치 번호와 그 대장 항목. 목록 앞의 장치부터 찾는다."""
                camera_ids = Connect.Device.Usb.camera_ids()
                for entry in entries:
                    for index, device in enumerate(camera_ids):
                        if device is not None and entry.id.matches(device):
                            return index, entry
                raise Connect.Device.Usb._missing(entries)

            @staticmethod
            def open_camera(index: int, backend: str) -> Any:
                """카메라를 연다. `backend` 는 `CAP_DSHOW` 같은 OpenCV 상수 이름이다."""
                from cv2 import VideoCapture as cv2_VideoCapture
                return cv2_VideoCapture(index, getattr(__import__("cv2"), backend))

            class Controls:
                """DirectShow 영상 장치 하나의 속성 손잡이. OpenCV 가 감싸지 않은 범위 · 지원 여부 · 자동 플래그를 읽고 쓴다.

                OpenCV 가 같은 장치를 긁는 동안에도 읽고 쓴다. 장치 번호는 `camera_ids` 의 순서다.
                """

                #: `IAMVideoProcAmp` · `IAMCameraControl` 의 `Flags`. DirectShow 규격값이다
                FLAG_AUTO = 1
                FLAG_MANUAL = 2

                class Range(NamedTuple):
                    """장치가 밝힌 속성 범위. 장치 내부 눈금이다."""

                    low: int
                    high: int
                    step: int
                    default: int
                    can_auto: bool

                interfaces: dict[str, Any]  # 인터페이스 이름 → 그 장치의 COM 손잡이
                controls: dict[str, tuple[str, int]]  # 속성 이름 → (인터페이스 이름, 속성 번호)

                def __init__(self, index: int, controls: dict[str, tuple[str, int]]) -> None:
                    from pygrabber.dshow_graph import SystemDeviceEnum as pygrabber_SystemDeviceEnum
                    from pygrabber.dshow_ids import DeviceCategories as pygrabber_DeviceCategories

                    base, _ = pygrabber_SystemDeviceEnum().get_filter_by_index(pygrabber_DeviceCategories.VideoInputDevice, index)
                    self.interfaces = {name: base.QueryInterface(kind) for name, kind in self.kinds().items()}
                    self.controls = controls

                @staticmethod
                @cache
                def kinds() -> dict[str, type]:
                    """두 인터페이스의 COM 선언. 두 인터페이스는 메서드 꼴이 같다."""
                    from ctypes import POINTER, c_long
                    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

                    methods = [
                        COMMETHOD([], HRESULT, "GetRange", (["in"], c_long, "Property"), (["out"], POINTER(c_long), "pMin"),
                                  (["out"], POINTER(c_long), "pMax"), (["out"], POINTER(c_long), "pSteppingDelta"),
                                  (["out"], POINTER(c_long), "pDefault"), (["out"], POINTER(c_long), "pCapsFlags")),
                        COMMETHOD([], HRESULT, "Set", (["in"], c_long, "Property"), (["in"], c_long, "lValue"), (["in"], c_long, "Flags")),
                        COMMETHOD([], HRESULT, "Get", (["in"], c_long, "Property"), (["out"], POINTER(c_long), "lValue"), (["out"], POINTER(c_long), "Flags")),
                    ]
                    return {
                        "video_proc_amp": type("IAMVideoProcAmp", (IUnknown,), {"_iid_": GUID("{C6E13360-30AC-11d0-A18C-00A0C9118956}"), "_methods_": methods}),
                        "camera_control": type("IAMCameraControl", (IUnknown,), {"_iid_": GUID("{C6E13370-30AC-11d0-A18C-00A0C9118956}"), "_methods_": methods}),
                    }

                def _handle(self, name: str) -> tuple[Any, int]:
                    interface, number = self.controls[name]
                    return self.interfaces[interface], number

                def range(self, name: str) -> "Connect.Device.Usb.Controls.Range | None":
                    """속성 범위. 장치가 그 속성을 지원하지 않으면 `None`."""
                    from comtypes import COMError as comtypes_COMError

                    handle, number = self._handle(name)
                    try: low, high, step, default, caps = handle.GetRange(number)
                    except comtypes_COMError: return None
                    return self.Range(low, high, step, default, bool(caps & self.FLAG_AUTO))

                def is_auto(self, name: str) -> bool | None:
                    """그 속성을 장치가 자동으로 잡고 있는가. 지원하지 않으면 `None`."""
                    from comtypes import COMError as comtypes_COMError

                    handle, number = self._handle(name)
                    try: _, flags = handle.Get(number)
                    except comtypes_COMError: return None
                    return bool(flags & self.FLAG_AUTO)

                def set_auto(self, name: str, on: bool) -> None:
                    """자동을 켜고 끈다. 끌 때는 지금 값을 수동 값으로 둔다."""
                    handle, number = self._handle(name)
                    value, _ = handle.Get(number)
                    handle.Set(number, value, self.FLAG_AUTO if on else self.FLAG_MANUAL)

        class Sound:
            """마이크를 물고 최신 전력 스펙트럼 한 벌을 슬롯에 남긴다.

            윈도우 공유 믹서를 거치면 자동 게인 · 소음 억제 · 빔포밍이 원 신호를 고친다.
            실측에서 노트북 마이크 배열은 공유 모드로 열면 무음(−163 dBFS)이었고 배타 모드에서만 신호가 들어왔다.
            내장 마이크도 두 모드가 18 dB 벌어졌다.
            그래서 배타를 먼저 열고 거절당하면 공유로 물러선다.

            **표본율은 장치가 정한다.** 배타 모드는 하드웨어 고유 율만 받으므로 우리가 고를 수 없다.
            율이 바뀌면 주파수 축과 버퍼를 다시 만든다.

            무엇을 잴지는 모른다. 대역도 문턱도 여기 없다.
            """

            @staticmethod
            def devices() -> list[dict[str, Any]]:
                """쓸 수 있는 입력 장치 목록. 배타 모드를 받는 것이 앞에 온다."""
                from sounddevice import query_devices as sd_query_devices, query_hostapis as sd_query_hostapis

                found = []
                for index, device in enumerate(sd_query_devices()):
                    if device.get("max_input_channels", 0) <= 0: continue
                    host = sd_query_hostapis(device["hostapi"])["name"]
                    found.append(
                        {
                            "index": index,
                            "name": device["name"],
                            "host": host,
                            "native_fs": int(device["default_samplerate"]),
                            "exclusive_capable": "WASAPI" in host,
                        }
                    )
                return sorted(found, key=lambda device: not device["exclusive_capable"])

            block_size: int
            hop_size: int
            preferred_name: str | None
            exclusive: bool  # 배타 모드를 먼저 시도한다
            block_wait_s: float  # 분석 워커가 다음 덩어리를 한 번 기다리는 길이
            stop_wait_s: float  # 마이크를 놓을 때 분석 워커가 서기를 기다리는 상한
            dropped: int = 0  # 워커가 못 따라가 버린 덩어리 수. 0 이 아니면 부하를 의심한다
            slot: Tool.Slot
            _stream: Any = None
            _thread: Any = None
            _pointer: int = 0
            _fs: int = 0
            _running: bool
            _devices: list[dict[str, Any]]
            _queue: queue.Queue[Any]

            def __init__(self, block_size: int, hop_size: int, preferred_name: str | None, *, exclusive: bool, backlog_hops: int, block_wait_s: float, stop_wait_s: float) -> None:
                self.block_size, self.hop_size = block_size, hop_size
                self.preferred_name, self.exclusive = preferred_name, exclusive
                self.block_wait_s, self.stop_wait_s = block_wait_s, stop_wait_s
                self._running, self._devices = False, []
                self._queue: queue.Queue[Any] = queue.Queue(maxsize=backlog_hops)
                self.slot = Tool.Slot(None)

            @property
            def fs(self) -> int:
                """지금 물고 있는 표본율. 장치를 열기 전에는 0 이다."""
                return self._fs

            @property
            def is_running(self) -> bool: return self._running

            @property
            def latest(self) -> Any:
                """최신 관측 한 벌. 아직 한 장도 안 떴으면 `None`."""
                return self.slot.get()

            @property
            def device(self) -> dict[str, Any] | None:
                """지금 물고 있는 장치 정보."""
                if not self._devices: return None
                return self._devices[self._pointer]

            @staticmethod
            def choose(preferred_name: str | None = None) -> dict[str, Any]:
                """쓸 장치를 고르되 **열지는 않는다.**

                블록 크기는 표본율에서 나오고 표본율은 장치가 정하므로, 열기 전에 어느 장치를 쓸지 알아야 한다.
                고르는 규칙은 아래 `resolved` 와 같다.
                """
                devices, pointer = Connect.Device.Sound.resolved(preferred_name)
                return devices[pointer]

            @staticmethod
            def resolved(preferred_name: str | None) -> tuple[list[dict[str, Any]], int]:
                """물 장치를 고른다 — (장치 목록, 고른 차례). 지정한 이름 → 윈도우 기본 마이크 → 목록 맨 앞 차례로 본다.

                목록 맨 앞은 가상 오디오 장치일 수 있어(루프백 · 믹스) 기본값으로 삼으면 무음을 문다.
                윈도우가 기본으로 잡은 마이크를 **이름으로** 되찾아 배타 모드 항목에 맞춘다 — 같은 마이크라도 호스트 API 마다 다른 번호로 잡히기 때문이다.
                """
                from sounddevice import default as sd_default, query_devices as sd_query_devices

                devices = Connect.Device.Sound.devices()
                if not devices: raise Tool.Missing("입력으로 쓸 마이크가 없다. 장치 연결과 윈도우 소리 설정을 본다")

                wants = []
                if preferred_name:
                    wants.append(preferred_name.lower())
                default_index = sd_default.device[0]
                if isinstance(default_index, int) and default_index >= 0:
                    wants.append(sd_query_devices(default_index)["name"].lower())

                for want in wants:
                    for pointer, device in enumerate(devices):
                        if want in device["name"].lower() or device["name"].lower() in want:
                            return devices, pointer
                return devices, 0

            def _open_stream(self) -> Any:
                """배타를 먼저 시도하고 거절당하면 공유로 연다."""
                from sounddevice import InputStream as sd_InputStream, PortAudioError as sd_PortAudioError, WasapiSettings as sd_WasapiSettings

                device = self._devices[self._pointer]
                attempts = []
                if self.exclusive and device["exclusive_capable"]:
                    attempts.append(sd_WasapiSettings(exclusive=True))
                attempts.append(None)

                last_error: Exception | None = None
                for extra in attempts:
                    try:
                        stream = sd_InputStream(
                            device=device["index"],
                            samplerate=device["native_fs"],
                            blocksize=self.hop_size,
                            channels=1,
                            dtype="float32",
                            callback=self._on_audio,
                            extra_settings=extra,
                        )
                        stream.start()
                        self._fs = device["native_fs"]
                        return stream
                    except sd_PortAudioError as error:
                        # 장치가 그 표본율 · 배타 조합을 거절한 것만 받는다. 그 밖의 오류는 올린다
                        last_error = error
                raise Tool.Missing(f"마이크 '{device['name']}' 를 열지 못했다: {last_error}")

            def _on_audio(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
                try: self._queue.put_nowait(indata.copy())
                except queue.Full: self.dropped += 1

            def _worker_loop(self) -> None:
                from numpy import float64 as np_float64, roll as np_roll, zeros as np_zeros

                buffer = np_zeros(self.block_size, dtype=np_float64)
                while self._running:
                    try: chunk = self._queue.get(timeout=self.block_wait_s)
                    except queue.Empty: continue

                    samples = chunk.mean(axis=1) if chunk.ndim > 1 else chunk.reshape(-1)
                    if len(samples) > self.block_size: samples = samples[-self.block_size:]
                    count = len(samples)
                    buffer = np_roll(buffer, -count)
                    buffer[-count:] = samples

                    self.slot.put(self._frame(buffer, self._fs, time.monotonic()))

            @staticmethod
            def _frame(block: Any, sample_rate_hz: int, timestamp_s: float) -> "Entity.AcousticFrame":
                from numpy import asarray as np_asarray, float64 as np_float64

                freqs, power = Tool.Acoustic.power_spectrum(block, sample_rate_hz)
                mean_square = float((np_asarray(block, dtype=np_float64) ** 2).mean())
                total_db = float(10.0 * math.log10(mean_square + Tool.Acoustic.POWER_FLOOR))
                return Entity.AcousticFrame(freqs=freqs, power=power, total_power_db=total_db, fs=sample_rate_hz, at=timestamp_s)

            def start(self) -> None:
                """마이크를 열고 분석 워커를 띄운다. 이미 돌고 있으면 아무 일도 안 한다."""
                if self._running: return
                if not self._devices: self._devices, self._pointer = self.resolved(self.preferred_name)
                self._stream = self._open_stream()
                self._running = True
                self._thread = threading.Thread(target=self._worker_loop, daemon=True)
                self._thread.start()

            def stop(self) -> None:
                """워커를 세우고 마이크를 놓는다."""
                self._running = False
                if self._stream is not None:
                    self._stream.stop()
                    self._stream.close()
                    self._stream = None
                if self._thread is not None:
                    self._thread.join(timeout=self.stop_wait_s)
                    self._thread = None

            def next_device(self) -> dict[str, Any]:
                """다음 마이크로 옮겨 문다. 사람이 어느 마이크인지 눈으로 고르는 자리다."""
                if not self._devices: self._devices, self._pointer = self.resolved(self.preferred_name)
                was_running = self._running
                self.stop()
                self._pointer = (self._pointer + 1) % len(self._devices)
                self.slot.put(None)
                if was_running: self.start()
                return self._devices[self._pointer]

            def feed_block(self, block: Sequence[float], sample_rate_hz: int, timestamp_s: float) -> "Entity.AcousticFrame":
                """녹음 파일 한 덩어리를 밀어 넣는다. 마이크 없이 같은 경로를 태우는 자리다.

                덩어리가 짧으면 뒤를 0 으로 채운다. `at` 은 부르는 쪽이 정한다 — 녹음 시각이다.
                """
                from numpy import asarray as np_asarray, float64 as np_float64, pad as np_pad

                self._fs = sample_rate_hz
                audio_samples = np_asarray(block, dtype=np_float64)
                if len(audio_samples) != self.block_size:
                    audio_samples = np_pad(audio_samples, (0, max(0, self.block_size - len(audio_samples))))[: self.block_size]
                frame = self._frame(audio_samples, sample_rate_hz, timestamp_s)
                self.slot.put(frame)
                return frame

    class Code:
        """남이 만든 코드에 우리를 맞춘다."""

        class OpenCvPath:
            """Windows 의 OpenCV 가 한글 · 비ASCII 경로를 열지 못하는 문제를 덮는다.

            바이트는 numpy 로 읽고 쓰고 부호화만 OpenCV 에 맡긴다.
            반환 규약은 원래 함수와 같다 — 읽기 실패는 `None`, 쓰기 실패는 `False`.
            `cv2` 가 이미 불러와져 있으면 바로, 아니면 불러오는 순간 바꾼다.
            """

            @staticmethod
            def patch(cv2: Any) -> None:
                from numpy import fromfile as np_fromfile, uint8 as np_uint8

                def imread(filename: str | Path, flags: int = cv2.IMREAD_COLOR) -> Any:
                    try: image_bytes = np_fromfile(filename, dtype=np_uint8)
                    except OSError: return None
                    return None if image_bytes.size == 0 else cv2.imdecode(image_bytes, flags)

                def imwrite(filename: str | Path, image: Any, parameters: Sequence[int] = ()) -> bool:
                    encoded_ok, image_buffer = cv2.imencode(Path(filename).suffix, image, list(parameters))
                    if not encoded_ok: return False
                    try: image_buffer.tofile(filename)
                    except OSError: return False
                    return True

                cv2.imread, cv2.imwrite = imread, imwrite

            class Finder(importlib.abc.MetaPathFinder):
                """`cv2` 를 불러오는 순간 한 번 끼어들어 덮어쓰고 빠진다."""

                def find_spec(self, name: str, path: Any, target: Any = None) -> Any:
                    if name != "cv2": return None
                    sys.meta_path.remove(self)
                    spec = importlib.util.find_spec("cv2")
                    exec_module = spec.loader.exec_module

                    def exec_and_patch(module: Any) -> None:
                        exec_module(module)
                        Connect.Code.OpenCvPath.patch(sys.modules["cv2"])

                    spec.loader.exec_module = exec_and_patch
                    return spec

            @staticmethod
            def install() -> None:
                if "cv2" in sys.modules:
                    Connect.Code.OpenCvPath.patch(sys.modules["cv2"])
                else:
                    sys.meta_path.insert(0, Connect.Code.OpenCvPath.Finder())


#: 모듈 적재 시점에 실행된다. 이후 어디서 cv2를 불러오든 한글 경로 입출력 패치가 자동으로 먹힌다.
Connect.Code.OpenCvPath.install()

