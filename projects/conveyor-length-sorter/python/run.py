"""운전 화면 — 사람이 실행하는 유일한 파일.

화면의 나무를 클래스의 중첩으로 적는다.
정의 순서가 화면 순서이고 중첩이 포함관계다.
잎도 클래스라 글자가 그 자리에 붙는다.
세운 위젯은 선언을 덮지 않고 `Build` 가 든다 — 선언은 임포트 뒤로 변하지 않으므로 탭을 몇 번 갈아 끼워도 글자가 남는다.

선언이 드는 것은 소속 · 종류 · 글자다. 색은 테마가, 치수는 세운 뒤 그 위젯이 든다.

    [1] 마디와 잎
    [2] 선언 :: 화면 전체
    [3] 공장 · 세우기 · 묶기
    [4] 창
    [5] 기동

    python run.py
"""

import dataclasses
import queue
import time
import tkinter as tk
from collections.abc import Mapping
from concurrent.futures import Future
from enum import Enum, StrEnum
from typing import Any, NamedTuple
from functools import partial
from pathlib import Path
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

import cnv_alg_core
import vis_alg_core
import rbt_alg_core
from com_lib_core import Config, Connect, Entity, Tool


# =========================================================================
# 1. 마디와 잎
# =========================================================================

class Face(Enum):
    """글꼴 한 벌. 선언은 이 중 하나를 고르고 무엇으로 걸리는지는 모른다.

    tk 위젯은 `font` 옵션으로 받고 ttk 위젯은 스타일 이름으로만 받는다.
    그 갈림은 공장이 진다 (`Factory.wearing`).
    """

    plain = ("Malgun Gothic", 9)
    small = ("Malgun Gothic", 8)
    fixed = ("Consolas", 9)      # 자릿수가 맞아야 읽히는 것 — 좌표 · 기록

    @property
    def font(self) -> tuple[str, int]:
        return self.value


# -------------------------------------------------------------------- 잎


class Leaf:
    """위젯 하나. 종류는 상속이, 글자는 클래스 헤더가 정한다.

    헤더에 적는 이유는 중첩만 눈에 남기려는 것이다 — 속성이 본문에서 줄을 차지하면 나무가 안 읽힌다.
    없는 이름을 적으면 파이썬이 `TypeError` 로 잡는다.
    """

    text = ""
    grow = False   # 남는 자리를 먹는가. 종류가 정하는 성질이다
    px = 0
    face = Face.plain         # 글꼴 한 벌

    def __init_subclass__(cls, text=None, grow=None, px=None, face=None):
        for name, value in (("text", text), ("grow", grow), ("px", px), ("face", face)):
            if value is not None:
                setattr(cls, name, value)


class Button(Leaf): """누른다."""
class Radio(Leaf): """여럿 중 하나를 고른다."""
class Check(Leaf): """켜고 끈다."""
class Combo(Leaf): """목록에서 고른다."""
class EditCombo(Combo): """목록에서 고르거나 목록 밖 값을 친다."""
class Slider(Leaf): """값을 민다."""
class Value(Leaf):
    """읽기만 하는 한 줄. 이름 칸과 값 칸 둘로 선다.

    이름은 안 변하므로 손잡이를 주지 않는다. `build[선언]` 이 돌려주는 것은 값 칸이다.
    """
class Entry(Leaf): """사람이 글자를 치는 자리."""
class Note(Leaf): """고정된 글."""
class Log(Leaf): """지나간 일을 적어 두는 자리."""
class Strip(Leaf): """그때만 뜨는 띠. 평소에는 자리를 안 차지한다."""


class Stage(Leaf):
    """영상 한 장을 그리는 자리. 남는 자리를 다 먹는다."""

    grow = True


class _WasTabs(Leaf):
    """탭을 담는 자리. 탭은 한 번 세우고 갈아 끼울 때 헐지 않는다."""

    grow = True


# ------------------------------------------------------------------ 마디


class Flow(Enum):
    """자식을 놓는 방향. 화면의 모든 마디가 이 둘의 중첩으로 덮인다."""

    column = "column"
    row = "row"


class Node:
    """담는 자리.

    `ledger` :: 자식의 수를 바깥이 정할 때 그 출처 이름. 비어 있으면 본문이 전부다.
    `child` :: 장부 항목 하나가 될 잎 종류. 여러 위젯이면 `template` 마디를 대신 둔다.
    """

    text = ""
    flow = Flow.column
    ledger = ""
    child = None
    grow = False
    px = 0
    face = Face.plain         # 글꼴 한 벌. 자식이 따로 고르지 않으면 이것

    def __init_subclass__(cls, text=None, flow=None, ledger=None, child=None,
                          grow=None, px=None):
        for name, value in (("text", text), ("flow", flow), ("ledger", ledger),
                            ("child", child), ("grow", grow), ("px", px)):
            if value is not None:
                setattr(cls, name, value)

    @classmethod
    def items(cls):
        """자식을 정의 순서대로 낸다. 잎이든 마디든 한 줄기다.

        본문에서 정의된 것만 낸다.
        `child` 는 헤더가 받아 든 종류라 여기서 뺀다 — 나무를 훑는 쪽이 잎으로 센다.
        """
        head = cls.__qualname__ + "."
        for name, thing in vars(cls).items():
            if (isinstance(thing, type) and issubclass(thing, (Node, Leaf))
                    and thing.__qualname__.startswith(head)):
                yield name, thing


class Group(Node): """테두리 있는 상자."""
class Deck(Node):
    """탭을 담는 자리. 자식은 계통이고 계통의 자식이 탭이다.

    마디라서 자식을 담는다 — 그래야 탭을 누가 세우는지가 선언 안에 선다.
    """
class Swap(Node):
    """자식 하나만 서는 자리. 형제는 서로 배타다.

    `chooser` 는 어느 자식을 올릴지 정하는 라디오 무리다.
    짝을 선언이 말하므로 한 부모 아래 배타 자리가 둘이어도 엉키지 않는다 — 각자 제 고르개를 든다.

    자식의 `text` 는 상자 제목이 아니라 **고르개에 뜨는 이름**이다.
    배타 자리 안에서 테두리를 또 두르면 한 벌만 보이는데도 틀이 두 겹이 된다.
    """

    chooser = None

    def __init_subclass__(cls, chooser=None, **rest):
        super().__init_subclass__(**rest)
        if chooser is not None:
            cls.chooser = chooser

    @classmethod
    def labels(cls) -> list:
        """고르개에 낼 이름. 자식이 곧 목록이다."""
        return [child.text for _, child in cls.items()]


class Tab(Node): """탭 하나."""
class System(Node): """탭을 묶는 계통."""
class Window(Node): """창 하나."""


# =========================================================================
# 2. 선언 — 화면 전체
# =========================================================================

class Chrome(Window):
    """창의 뼈대. 창 자체를 이루는 것들이 여기 선다.

    고르개의 자식은 선언 자신이 정한다 — 계통 목록도 탭 목록도 위 선언에서 나온다.
    치수(조작 열의 폭 · 기록 줄 수)는 여기 적지 않는다. 세운 뒤 그 위젯을 만진다.
    """

    class SystemBar(Group, flow=Flow.row, ledger="screen.systems", child=Radio): pass

    class Body(Group, flow=Flow.row, grow=True):

        class Left(Group, grow=True):
            class stage(Stage): pass
            class alert(Strip): pass    # 붙어 있던 것이 끊겼을 때만 뜬다
            class busy(Strip): pass   # 바인딩 미완료 — 오래 걸리는 동작이 도는 중에만 뜬다
            class viewing(Note): pass   # 입력 · 장 · 고정 · 바탕
            class assets(Note): pass    # 회차가 가진 자산
            class log(Log): pass

        class Column(Group, px=300):

            class Source(Group, text="입력"):
                class pick(Combo): pass

                class Move(Group, flow=Flow.row):
                    class first(Button, text="|◀", px=40): pass
                    class prev(Button, text="◀", px=40): pass
                    class next(Button, text="▶", px=40): pass
                    class last(Button, text="▶|", px=40): pass

                class freeze(Check, text="⏸ 고정"): pass   # 바인딩 미완료

            class tabs(Deck):

                class Vision(System, text="비전"):

                    class Viewer(Tab, text="뷰어"):

                        class Base(Group, text="바탕 — 하나만"):
                            class pick(Combo): pass   # 바인딩 미완료

                        class Layers(Group, text="겹쳐 보기", ledger="ui.layers", child=Check): pass   # 바인딩 미완료

                        class Overlays(Group, text="오버레이", ledger="ui.overlays", child=Check): pass   # 바인딩 미완료

                    class Label(Tab, text="라벨"):

                        class ClickIs(Group, text="지금 클릭은", flow=Flow.row,
                                      ledger="label.click_modes", child=Radio): pass

                        class DrawWay(Group, text="찍는 방식",
                                      ledger="label.draw_modes", child=Radio): pass   # 몸통은 "클릭 그대로" 만

                        class Work(Group, text="작업", flow=Flow.row):
                            class suggest(Button, text="⚑ 자동 제안", px=128): pass   # 바인딩 미완료
                            class undo(Button, text="↶ 되돌리기", px=128): pass

                        class ThisFrame(Group, text="이 장"):
                            class count(Value, text="라벨 수"): pass
                            class by_spec(Value, text="규격별"): pass

                    class Setup(Tab, text="준비"):

                        class Steps(Group, text="단계"):

                            class WorkArea(Group, flow=Flow.row):
                                class number(Note, text="①"): pass
                                class run(Button, text="□ 작업영역 4점", grow=True): pass
                                class state(Value, text="—"): pass

                            class Homography(Group, flow=Flow.row):
                                class number(Note, text="②"): pass
                                class run(Button, text="◈ 사영 모델 산출", grow=True): pass
                                class state(Value, text="—"): pass

                            class Affine(Group, flow=Flow.row):
                                class number(Note, text="③"): pass
                                class run(Button, text="⌖ 아핀 대응점", grow=True): pass
                                class state(Value, text="—"): pass

                        class Diagnose(Group, text="진단", flow=Flow.row):
                            class coverage(Button, text="▦ 라벨 분포도"): pass

                        class EraPick(Group, text="회차"):
                            class source(Value, text="현행 값의 출처"): pass
                            class viewing(Value, text="보는 중"): pass

                    class Camera(Tab, text="카메라"):

                        class Device(Group, text="장치"):
                            class shot_by(Value, text="회차를 찍은 것"): pass
                            class attached(Value, text="지금 붙은 것"): pass

                        class Capture(Group, text="촬영", flow=Flow.row):
                            class one(Button, text="● 한 장", px=128): pass
                            class burst(Button, text="⏺ 버스트", px=128): pass

                        class Exposure(Group, text="노출"):

                            class Way(Group, flow=Flow.row,
                                      ledger="camera.exposure_modes", child=Radio): pass   # 바인딩 미완료

                            class Tune(Group, flow=Flow.row):
                                class sweep(Button, text="⚡ 노출 자동 맞춤"): pass   # 바인딩 미완료

                        class Props(Group, text="속성"):

                            class Values(Group, ledger="camera.property_ids"):

                                class template(Group, flow=Flow.row):
                                    class name(Note): pass
                                    class slider(Slider): pass   # 바인딩 미완료
                                    class value(Note, text="—"): pass

                            class Act(Group, flow=Flow.row):
                                class read(Button, text="↻ 갱신"): pass   # 바인딩 미완료

                        class EraDoc(Group, text="회차 문서", flow=Flow.row):
                            class load(Button, text="⎌ 불러오기", px=128): pass

                    class Score(Tab, text="채점"):

                        class Sample(Group, text="기준 표본"):
                            class era(Value, text="회차"): pass
                            class frames(Value, text="사진"): pass   # 바인딩 미완료
                            class labels(Value, text="라벨"): pass   # 바인딩 미완료

                        class ThisFrame(Group, text="이 장"):   # 바인딩 미완료
                            class frame(Value, text="프레임"): pass
                            class detect(Value, text="검출"): pass
                            class label(Value, text="라벨"): pass
                            class shape(Value, text="형상"): pass
                            class spec(Value, text="규격"): pass
                            class corner(Value, text="꼭짓점 거리"): pass

                        class Compare(Group, text="대조", flow=Flow.row):
                            class one(Button, text="이 장 채점", px=128): pass   # 바인딩 미완료
                            class all(Button, text="전체 채점", px=128): pass   # 바인딩 미완료

                class Equipment(System, text="설비"):

                    class Robot(Tab, text="로봇"):

                        #: 읽기만 하는 것. 사람이 "지금 어떤가" 를 보는 자리다
                        class Status(Group, text="상태"):
                            class Now(Group, flow=Flow.row):
                                class link(Button, px=84): pass
                                class state(Value, text=""): pass

                            class pump(Value, text="공압"): pass
                            class firmware(Value, text="펌웨어"): pass

                            #: 어느 마이크를 무는지는 연결 사정이다. 고르는 버튼도 여기 있다
                            class device(Value, text="마이크"): pass
                            class swap(Button, text="다음 마이크", px=196): pass

                        #: 누르면 설비가 무언가 한다
                        class Command(Group, text="조작"):
                            class Act(Group, flow=Flow.row):
                                class home(Button, text="⌂ 호밍", px=128): pass
                                class halt(Button, px=128): pass

                            class Air(Group, flow=Flow.row,
                                      ledger="robot.motion.pneumatics_pwm.State", child=Radio): pass

                            class teach(Button, text="티칭 창 열기", px=260): pass

                        #: 비전이 본 블록 하나를 집어 투입점에 놓는다. 무엇을 집을지가 버튼 아래 선다
                        class Cycle(Group, text="사이클"):
                            class run(Button, text="▶ 한 사이클", px=260): pass
                            class target(Value, text="다음 블록"): pass

                        #: 손으로 미는 일 한 덩이. 좌표가 버튼 옆에 있어야 보면서 민다
                        class Jog(Group, text="조그"):

                            class Mode(Group, flow=Flow.row):
                                class Kind(Group, flow=Flow.row,
                                           ledger="robot.jog_kinds", child=Radio): pass
                                class Way(Group, flow=Flow.row,
                                          ledger="robot.jog_ways", child=Radio): pass

                            #: 두 방식이 같이 쓰는 값이라 배타 자리 밖에 둔다.
                            #: 안에 넣으면 두 벌이 되어 고를 때마다 값이 갈린다
                            class Speed(Group, flow=Flow.row):
                                class speed(EditCombo, face=Face.small): pass
                                class rate(Note, text="mm/min", face=Face.small): pass

                            class Ways(Swap, chooser=Mode.Way):

                                class Step(Group, text="상대"):

                                    class Frame(Group, flow=Flow.row):
                                        class step_mm(EditCombo, face=Face.small): pass
                                        class mm(Note, text="mm", face=Face.small): pass
                                        class step_deg(EditCombo, face=Face.small): pass
                                        class deg(Note, text="도", face=Face.small): pass

                                    #: 축 하나가 한 줄이다.
                                    #: 이름은 값 안에 고정폭으로 들어간다 — 이름 칸을 따로 두면 열 하나가 날아간다
                                    class Axes(Group, ledger="gcode.command_axes"):

                                        class template(Group, flow=Flow.row):
                                            class at(Value, text="", face=Face.fixed): pass
                                            class minus(Button, text="−", px=30): pass
                                            class plus(Button, text="+", px=30): pass

                                class Goto(Group, text="절대"):

                                    class Axes(Group, ledger="gcode.command_axes"):

                                        class template(Group, flow=Flow.row):
                                            class name(Note, px=26, face=Face.fixed): pass
                                            class to(Entry, px=92, face=Face.fixed): pass

                                    class go(Button, text="이 자리로 간다", px=260): pass

                    class Plc(Tab, text="PLC"):

                        class Link(Group, text="연결"):
                            class state(Value, text="—"): pass

                            class Act(Group, flow=Flow.row):
                                class link(Button, px=128): pass

                        class Interlock(Group, text="상태 · 인터록"):
                            class entry(Value, text="투입 허가"): pass

                        class Direct(Group, text="직접"):

                            class Tag(Group):
                                class pick(EditCombo): pass

                            class Act(Group, flow=Flow.row):
                                class read(Button, text="읽기", px=56): pass
                                class value(Entry): pass
                                class write(Button, text="쓰기", px=56): pass

                    class Qr(Tab, text="QR"):

                        class Gate(Group, text="조건"):
                            class mode(Value, text="판정 방식"): pass
                            class entered(Value, text="자재 진입"): pass
                            class step(Value, text="단계"): pass

                        class Read(Group, text="판독"):
                            class spec(Value, text="규격"): pass
                            class previous(Value, text="직전 자재"): pass

class Teach(Window, text="티칭"):
    """티칭 창. 운전 창과 따로 선다.

    **바탕을 가리지도 입력을 가로채지도 않는다.**
    `가동범위 4점` 이 운전 창의 바탕에서 점을 찍는 동작이라 그 둘이 살아 있어야 한다.
    """

    #: 높이와 자리를 따로 담는다. 자리는 XY 만 담고 그 자리가 쓰는 Z 는 높이 표가 든다
    class Heights(Group, text="높이"):
        class Pick(Group, flow=Flow.row):
            class which(Combo, px=176): pass
            class save(Button, text="담기", px=72): pass
            class go(Button, text="이 높이로", px=104): pass

    class Places(Group, text="자리 — XY 만 담는다"):
        class Pick(Group, flow=Flow.row):
            class which(Combo, px=176): pass
            class save(Button, text="담기", px=72): pass
            class go(Button, text="이 자리로", px=104): pass

    #: 실물 조그로 네 귀퉁이를 찍는다. 영상에서 찍는 것이 아니다 — 로봇 기저 좌표다
    class Reach(Group, text="가동범위"):
        class state(Value, text="찍은 점"): pass
        class Act(Group, flow=Flow.row):
            class add(Button, text="지금 자리 담기", px=176): pass
            class clear(Button, text="다시", px=72): pass

    class Raw(Group, text="G코드 직접전송"):
        class Line(Group, flow=Flow.row):
            class line(Entry, grow=True): pass
            class send(Button, text="보내기", px=80): pass


# =========================================================================
# 3. 공장 · 세우기 · 묶기
# =========================================================================

class Style(StrEnum):
    """ttk 스타일 이름. 앞 둘은 우리가 만든 것이고 나머지는 ttk 의 어휘다."""

    value = "Value.TLabel"
    note = "Note.TLabel"
    root = "."
    frame = "TFrame"
    labelframe = "TLabelframe"
    labelframe_text = "TLabelframe.Label"
    label = "TLabel"
    check = "TCheckbutton"
    radio = "TRadiobutton"
    combo = "TCombobox"
    entry = "TEntry"
    notebook = "TNotebook"
    notebook_tab = "TNotebook.Tab"
    slider = "TScale"
    toolbutton = "Toolbutton"   # 눌린 채로 남는 버튼. 계통과 탭을 고를 때 쓴다
    alert = "Alert.TLabel"      # 끊김
    busy = "Busy.TLabel"        # 도는 중


class State(StrEnum):
    """ttk 위젯이 처할 수 있는 상태. 색을 상태별로 걸 때 쓴다."""

    active = "active"          # 마우스를 얹었다
    disabled = "disabled"
    readonly = "readonly"
    normal = "normal"          # 글자를 칠 수 있다
    selected = "selected"
    unselected = "!selected"


class Life(Enum):
    """누른 뒤 화면이 무엇을 해야 하는가. 누르는 사람이 기다릴 시간을 뜻한다."""

    now = "즉시"
    frame = "프레임"      # 한 장을 다시 그린다
    long = "오래"         # 띠를 띄우고 기다린다
    waiting = "사람대기"   # 영상에서 점을 받는 중이라고 기록에 적는다


class Factory:
    """잎 종류마다 위젯을 하나 만든다.

    생김새는 여기서 묶는다. 선언은 종류와 글자만 알고 색도 치수도 모른다.
    색은 ttk 스타일이 들고 스타일은 테마를 입힐 때 한 번에 걸린다.
    """

    #: 잎 종류마다 위젯 생성자 하나. 런타임 값에 기대지 않으므로 여기 선다
    make = {
        #: 그림을 다는 버튼만 tk 다. ttk 는 `width` 를 문자 수로만 세서 픽셀을 못 받는다
        Button: partial(tk.Button, relief="flat", bd=0, highlightthickness=0, height=24),
        Radio: partial(ttk.Radiobutton),
        Check: partial(ttk.Checkbutton),
        Combo: partial(ttk.Combobox, state=State.readonly, values=()),
        EditCombo: partial(ttk.Combobox, state=State.normal, values=()),
        Slider: partial(ttk.Scale, from_=0, to=255),
        Value: partial(ttk.Label, style=Style.value, anchor="e"),
        Entry: partial(ttk.Entry),
        Note: partial(ttk.Label, style=Style.note, anchor="w", justify="left"),
        Strip: partial(ttk.Label, anchor="w", padding=6),
        Stage: partial(tk.Label, bd=0),
        Deck: partial(ttk.Notebook),
        Log: partial(tk.Text, bd=0, wrap="none", state="disabled"),
    }

    #: 크기를 픽셀로 받는 잎. 그림을 달아 둔 tk 위젯만 그렇고, ttk 는 문자 수로만 센다
    in_pixels = {Button}

    ui: "Config.Ui"
    style: ttk.Style                     # Tk 가 선 뒤에만 만들어진다
    theme: "Config.Ui.Theme.Theme"       # 지금 걸린 한 벌. tk 위젯을 칠할 때 본다
    images: dict[str, tk.PhotoImage]     # 그림은 여기 산다
    tinted: list[tuple[tk.Widget, type]] # ttk 스타일이 안 닿는 tk 위젯. 테마를 바꾸면 다시 칠한다

    def __init__(self, ui: "Config.Ui") -> None:
        self.ui = ui
        self.style = ttk.Style()
        self.style.theme_use(ui.theme.widget_theme)
        self.letter()
        self.theme = ui.theme.themes[ui.theme.default]
        self.tinted = []
        #: 그림은 부르는 쪽이 놓으면 사라진다 — 파이썬이 참조를 잃으면 tk 가 지운다.
        #: 공장이 창이 사는 동안 들고 있어야 화면에 남는다. 버튼 아이콘도 여기 넣는다.
        self.images = {"px": tk.PhotoImage(width=1, height=1)}

    def image(self, name: str, path: str) -> tk.PhotoImage:
        """그림 하나를 들여 둔다. 같은 이름이면 다시 읽지 않는다."""
        if name not in self.images:
            self.images[name] = tk.PhotoImage(file=path)
        return self.images[name]

    def paint(self, theme: "Config.Ui.Theme.Theme") -> None:
        """테마 한 벌을 모든 스타일에 건다. 위젯은 색을 직접 들지 않는다."""
        self.theme = theme
        colors = theme.colors
        st = self.style
        st.configure(Style.root, background=colors.surface, foreground=colors.ink,
                     fieldbackground=colors.surface2, bordercolor=colors.line)
        for name in (Style.frame, Style.labelframe):
            st.configure(name, background=colors.surface, bordercolor=colors.line)
        st.configure(Style.labelframe_text, background=colors.surface, foreground=colors.ink3)
        for name in (Style.label, Style.value):
            st.configure(name, background=colors.surface, foreground=colors.ink)
        st.configure(Style.note, background=colors.surface, foreground=colors.ink3)
        st.configure(Style.alert, background=colors.danger, foreground=colors.ground)
        st.configure(Style.busy, background=colors.warn, foreground=colors.ground)
        for name in (Style.check, Style.radio):
            st.configure(name, background=colors.surface, foreground=colors.ink)
            st.map(name,
                   background=[(State.active, colors.surface2)],
                   foreground=[(State.active, colors.accent), (State.disabled, colors.idle)],
                   indicatorbackground=[(State.selected, colors.accent),
                                        (State.unselected, colors.surface2)])
        st.configure(Style.combo, fieldbackground=colors.surface2, background=colors.surface2,
                     foreground=colors.ink, arrowcolor=colors.ink2, bordercolor=colors.line)
        st.map(Style.combo,
               fieldbackground=[(State.readonly, colors.surface2)],
               foreground=[(State.readonly, colors.ink), (State.disabled, colors.idle)],
               selectbackground=[(State.readonly, colors.surface2)],
               selectforeground=[(State.readonly, colors.ink)])
        st.configure(Style.entry, fieldbackground=colors.surface2, foreground=colors.ink,
                     insertcolor=colors.ink, bordercolor=colors.line)
        #: 펼친 목록은 tk 리스트박스다. 스타일이 안 닿아 옵션 데이터베이스로만 색이 간다
        for option, color in (("*TCombobox*Listbox.background", colors.surface2),
                              ("*TCombobox*Listbox.foreground", colors.ink),
                              ("*TCombobox*Listbox.selectBackground", colors.accent),
                              ("*TCombobox*Listbox.selectForeground", colors.ground)):
            st.master.option_add(option, color)
        st.configure(Style.slider, background=colors.surface, troughcolor=colors.surface2)
        st.configure(Style.notebook, background=colors.surface, bordercolor=colors.line)
        st.configure(Style.notebook_tab, background=colors.surface2, foreground=colors.ink2,
                     padding=(8, 4))
        st.map(Style.notebook_tab,
               background=[(State.selected, colors.surface)],
               foreground=[(State.selected, colors.accent)])
        st.configure(Style.toolbutton, background=colors.surface2, foreground=colors.ink)
        st.map(Style.toolbutton,
               background=[(State.selected, colors.accent), (State.active, colors.line)],
               foreground=[(State.selected, colors.ground)])
        for widget, kind in self.tinted:
            self.tint(widget, kind)

    #: tk 위젯 종류마다 걸 색. ttk 스타일이 안 닿으므로 위젯마다 직접 준다
    tints = {
        Button: lambda colors: dict(bg=colors.surface2, fg=colors.ink,
                                     activebackground=colors.line, activeforeground=colors.ink,
                                     disabledforeground=colors.idle),
        Stage: lambda colors: dict(bg=colors.stage),
        Log: lambda colors: dict(bg=colors.surface, fg=colors.ink2),
    }

    def tint(self, widget: tk.Widget, kind: type) -> None:
        """tk 위젯 하나를 지금 테마로 칠한다."""
        widget.configure(**self.tints[kind](self.theme.colors))

    def keep(self, widget: tk.Widget, kind: type) -> tk.Widget:
        """칠해서 내주고, 테마가 바뀌면 다시 칠하도록 적어 둔다."""
        self.tinted.append((widget, kind))
        self.tint(widget, kind)
        return widget

    def takes_px(self, kind: type) -> bool:
        """이 잎이 제 `width` 로 픽셀을 받는가. 아니면 세우는 쪽이 틀에 가둔다."""
        return next(one for one in kind.__mro__ if one in self.make) in self.in_pixels

    @staticmethod
    def wearing(base: str, face: Face) -> str:
        """그 스타일을 이 얼굴로 입혔을 때의 ttk 이름.

        ttk 이름은 점으로 상속하고 **끝 마디가 위젯 클래스여야** 한다.
        그래서 앞에만 붙인다 — `Note.TLabel` 에 `small` 을 입히면 `small.Note.TLabel` 이고, 색은 `Note` 것을 그대로 물려받는다.
        같은 이름을 공장이 미리 찍고 잎이 다시 부르므로 짓는 자리는 하나다.
        """
        return f"{face.name}.{base}"

    def letter(self) -> None:
        """얼굴마다 ttk 이름을 만들어 둔다.

        쓰는 종류가 `make` 로 닫혀 있어 미리 다 찍는다.
        기본 얼굴은 뿌리에 한 번 걸면 모든 ttk 위젯이 물려받으므로 파생 이름이 없다.
        """
        st = self.style
        st.configure(Style.root, font=Face.plain.font)
        #: 펼친 목록은 tk 리스트박스다. 스타일이 안 닿아 하나로만 걸린다 — 얼굴별로 못 나눈다
        st.master.option_add("*TCombobox*Listbox.font", Face.plain.font)
        for base in {mold.keywords.get("style") or f"T{mold.func.__name__}"
                     for kind, mold in self.make.items() if kind not in self.tints}:
            for face in Face:
                if face is not Face.plain:
                    st.configure(self.wearing(base, face), font=face.font)

    def leaf(self, kind: type, parent: tk.Widget, text: str) -> tuple[tk.Widget, tk.Widget]:
        """잎 하나를 만들어 (놓을 것, 만질 것) 둘을 돌려준다.

        놓지는 않는다 — 어디에 어떻게 놓을지는 부모의 배치가 정하므로 세우는 쪽 일이다.
        대개 둘은 같은 위젯이다.
        값 한 줄만 이름 칸과 값 칸 둘로 서서, 놓을 것은 그 틀이고 만질 것은 값이 들어올 칸이다.
        """
        base = next(one for one in kind.__mro__ if one in self.make)

        def wear(widget):
            """얼굴을 입힌다. 받는 꼴이 tk 와 ttk 가 달라 무엇을 받는지 물어보고 고른다."""
            if "font" in widget.keys():
                widget.configure(font=kind.face.font)
            elif kind.face is not Face.plain:
                widget.configure(style=self.wearing(widget.cget("style")
                                                    or widget.winfo_class(), kind.face))
            return widget

        if issubclass(base, Button):
            #: 그림이 보이면 tk 가 `width` 를 픽셀로 센다. 1x1 투명 그림이 그 스위치다
            #: 폭을 박았으면 그 값이 곧 폭이다. 글자에 맞출 때만 좌우 여백을 준다
            button = self.keep(self.make[base](parent, text=text, image=self.images["px"],
                                               compound="center",
                                               width=kind.px or None, font=kind.face.font,
                                               padx=0 if kind.px else 8), Button)
            return button, button
        if issubclass(base, Value):
            #: 이름이 없으면 이름 칸을 안 세운다. 좌표처럼 값 안에 이름이 든 것이 그렇다
            row = ttk.Frame(parent)
            if text:
                wear(ttk.Label(row, text=text, style=Style.note, anchor="w")).pack(side="left")
            reading = wear(self.make[base](row))
            reading.pack(side="right", fill="x", expand=True)
            return row, reading
        if issubclass(base, (Stage, Log)):
            widget = self.keep(self.make[base](parent), base)
            if issubclass(base, Log):
                widget.configure(font=Face.fixed.font)
            return widget, widget
        if issubclass(base, (Slider, Combo, Entry)):
            widget = wear(self.make[base](parent))
            return widget, widget
        widget = wear(self.make[base](parent, text=text))
        return widget, widget


class Build:
    """선언을 위젯으로 세운 결과. 선언은 그대로 두고 여기에만 쌓인다.

    `build[선언]` 으로 세운 것을 꺼낸다. 장부가 되풀이한 것은 `repeated` 에 항목 이름으로 있다.
    """

    #: 놓는 법. 부모의 배치와 그것이 늘어나는지가 정한다
    how = {(Flow.column, False): dict(fill="x", pady=1),
           (Flow.column, True): dict(fill="both", expand=True, pady=1),
           (Flow.row, False): dict(side="left", padx=2),
           (Flow.row, True): dict(side="left", fill="both", expand=True, padx=2)}

    @classmethod
    def how_of(cls, flow: Flow, thing: type) -> dict:
        """놓는 법. 가로로 놓인 담는 자리는 세로를 꽉 채운다 — 안 그러면 높이가 0 이 된다.

        **폭을 박은 잎은 안 늘린다.**
        세로로 놓인 것을 가로로 채우는 것이 기본이라, `px` 를 적어도 그 규칙이 이기면 선언이 무시된다.
        """
        way = dict(cls.how[(flow, thing.grow)])
        if flow is Flow.row and not thing.grow and issubclass(thing, Node):
            way["fill"] = "y"
        if flow is Flow.column and thing.px and issubclass(thing, Leaf):
            way.pop("fill", None)
            way["anchor"] = "w"
        return way

    factory: Factory
    ledger: dict                                # 장부 이름 → 항목 목록
    made: dict[type, tk.Widget]                 # 선언 → 세운 위젯
    repeated: dict[type, dict[str, tk.Widget]]  # 장부 마디 → 항목 이름 → 위젯
    windows: dict[type, tk.Toplevel]            # 창 선언 → 세운 창

    def __init__(self, factory: Factory, ledger: dict) -> None:
        self.factory = factory
        self.ledger = ledger
        self.made = {}
        self.repeated = {}
        self.windows = {}

    def __getitem__(self, node: type) -> tk.Widget:
        return self.made[node]

    def window(self, node: type, root: tk.Misc, title: str) -> tk.Toplevel:
        """창 하나를 세운다. 이미 서 있으면 앞으로 꺼내기만 한다.

        **모달로 만들지 않는다** — `grab_set` 을 걸면 운전 창의 바탕을 못 만진다.
        """
        made = self.windows.get(node)
        if made is not None and made.winfo_exists():
            made.deiconify(); made.lift()
            return made

        top = tk.Toplevel(root)
        top.title(title)
        top.flow = node.flow
        self.windows[node] = top
        for _, thing in node.items():
            self.put(thing, top)
        top.protocol("WM_DELETE_WINDOW", top.withdraw)   # 닫아도 헐지 않는다. 다시 꺼낸다
        return top

    def put(self, node: type, parent: tk.Widget, into: dict | None = None) -> tk.Widget:
        """마디 하나를 세우고 그 아래를 이어 세운다.

        `into` 가 있으면 세운 것을 거기에 담는다.
        되풀이되는 본은 항목마다 제 사전을 가져야 하기 때문이다 — 안 그러면 같은 선언이 앞의 위젯을 덮는다.
        """
        store = self.made if into is None else into
        if issubclass(node, Deck):
            #: 계통은 tk 에 자리가 없다 — 거르는 이름일 뿐이라 탭만 공책에 든다.
            #: 어느 계통을 보일지는 `Shell` 이 감췄다 꺼내며 정한다
            book = self.factory.make[Deck](parent)   # 공책은 글자를 안 받는다
            book.pack(**self.how_of(getattr(parent, "flow", Flow.column), node))
            book.flow = node.flow
            store[node] = book
            for _, system in node.items():
                for _, tab in system.items():
                    self.put(tab, book, into=into)
            return book
        if issubclass(node, Swap):
            #: 자식을 다 세우고 첫째만 올린다. 어느 것을 올릴지는 `Bind.link` 가 정한다
            frame = ttk.Frame(parent)
            frame.pack(**self.how_of(getattr(parent, "flow", Flow.column), node))
            frame.flow, frame.owner = node.flow, node
            store[node] = frame
            for order, (_, child) in enumerate(node.items()):
                made = self.put(child, frame, into=into)
                made.how = made.pack_info()
                if order:
                    made.pack_forget()
            return frame
        if isinstance(parent, ttk.Notebook):
            frame = ttk.Frame(parent)
            parent.add(frame, text=node.text)
        elif issubclass(getattr(parent, "owner", Node), Swap):
            #: 배타 자리의 자식. `text` 는 고르개 이름이라 테두리를 두르지 않는다
            frame = ttk.Frame(parent)
            frame.pack(**self.how_of(Flow.column, node))
        else:
            frame = (ttk.Labelframe(parent, text=node.text, padding=6) if node.text
                     else ttk.Frame(parent))
            if node.px:
                frame.configure(width=node.px)
                frame.pack_propagate(False)
            frame.pack(**self.how_of(getattr(parent, "flow", Flow.column), node))
        frame.flow = node.flow
        frame.owner = node
        store[node] = frame

        if node.ledger:
            template = getattr(node, "template", None)
            held = self.repeated.setdefault(node, {})
            held.clear()
            for item in self.ledger[node.ledger]:
                if template is not None:
                    bag: dict = {}
                    self.put(template, frame, into=bag)
                    held[item] = bag
                else:
                    held[item] = self._leaf(node.child, frame, node.flow, item)
            return frame

        for name, thing in node.items():
            if issubclass(thing, Node):
                if name != "template":
                    self.put(thing, frame, into=into)
            else:
                store[thing] = self._leaf(thing, frame, node.flow, thing.text)
        return frame

    def show(self, node: type, label: str) -> None:
        """배타 자리에서 하나만 올린다. 이름은 자식의 `text` 다."""
        for _, child in node.items():
            made = self.made[child]
            if child.text == label:
                made.pack(**made.how)
            else:
                made.pack_forget()

    def _leaf(self, thing: type, parent: tk.Widget, flow: Flow, text: str) -> tk.Widget:
        """잎 하나를 놓는다.

        글자는 밖에서 받는다 — 선언한 잎은 제 글자를 쓰고, 장부가 되풀이한 것은 항목 이름을 쓴다.
        가로를 픽셀로 박았을 때, 제 `width` 로 픽셀을 받는 잎은 그냥 서고 나머지는 그 폭의 틀에 가둔다.
        틀은 옆에 붙는 글자의 시작 위치를 맞추는 데도 쓴다.
        """
        if not thing.px or self.factory.takes_px(thing):
            placed, handle = self.factory.leaf(thing, parent, text)
            placed.pack(**self.how_of(flow, thing))
            return handle
        holder = ttk.Frame(parent, width=thing.px)
        holder.pack_propagate(False)
        holder.pack(**self.how_of(flow, thing))
        placed, handle = self.factory.leaf(thing, holder, text)
        placed.pack(fill="both", expand=True)
        holder.configure(height=placed.winfo_reqheight())
        return handle


class Tip:
    """마우스를 얹고 잠깐 기다리면 뜨는 쪽지.

    화면에는 자리가 좁아 못 적는 것이 있다.
    이 동작이 무엇인지, 단축키가 무엇인지, 잠겨 있다면 왜 잠겼는지가 그렇다.
    누르면 곧바로 사라진다 — 뜬 채로 두면 다음 클릭을 가린다.
    """

    colors: "Mapping[str, str]" = {}   # 지금 테마의 색(`theme.colors`). 화면이 테마를 바꿀 때 갈아 끼운다
    delay_ms = 400
    offset_px = (16, 20)
    wrap_px = 260

    widget: tk.Widget
    base: str                  # 평소 글
    text: str                  # 지금 보일 글. 잠기면 사유가 붙는다
    top: tk.Toplevel | None = None  # 떠 있는 것
    timer: str | None = None   # 기다리는 중인 시계

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.base = text
        self.text = text
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Button>", self._hide, add="+")

    def reason(self, why: str) -> None:
        """잠긴 사유를 얹는다. 풀리면 평소 글로 돌아간다."""
        self.text = f"{self.base}\n\n{why}" if why else self.base

    def _enter(self, event) -> None:
        self._hide()
        self.timer = self.widget.after(self.delay_ms,
                                       lambda: self._show(event.x_root, event.y_root))

    def _show(self, x: int, y: int) -> None:
        colors = self.colors
        self.top = tk.Toplevel(self.widget)
        self.top.overrideredirect(True)
        self.top.configure(bg=colors.line)
        tk.Label(self.top, text=self.text, justify="left", wraplength=self.wrap_px,
                 bg=colors.surface2, fg=colors.ink, padx=8, pady=5,
                 font=("Malgun Gothic", 9)).pack(padx=1, pady=1)
        dx, dy = self.offset_px
        self.top.wm_geometry(f"+{x + dx}+{y + dy}")

    def _hide(self, event=None) -> None:
        if self.timer is not None:
            self.widget.after_cancel(self.timer)
            self.timer = None
        if self.top is not None:
            self.top.destroy()
            self.top = None


class Bind:
    """선 위젯에 기능을 묶는다. 구조가 다 선 뒤에 하는 유일한 일이다.

    한 버튼의 사실이 한 줄에 모인다 — 무엇을 하고, 어떻게 설명되고, 얼마나 걸리고, 어떤 단축키인지.
    흩어 두면 버튼 하나를 이해하는 데 파일을 오가야 한다.
    """

    #: 글자를 치는 칸. 여기서 친 키는 그 칸의 글자라 단축키로 듣지 않는다 — ttk 의 입력칸 · 고르개 · 숫자칸은 `tk.Entry` 를 잇는다
    TYPING_WIDGETS = (tk.Entry, tk.Text, tk.Spinbox)

    root: tk.Tk
    bound: dict[tk.Widget, dict]   # 위젯 → 할 일 · 수명 · 쪽지

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.bound = {}

    def press(self, widget: tk.Widget, work, tip: str = "", key: str | None = None,
              life: Life = Life.now, gate=None) -> None:
        """누름 하나를 묶는다. `gate` 는 (눌러도 되는가, 안 되는 이유)를 낸다."""
        widget.configure(command=work)
        text = f"{tip}\n단축키 {key}" if key else tip
        self.bound[widget] = dict(work=work, life=life, gate=gate,
                                  tip=Tip(widget, text) if text else None)
        if key:
            self.root.bind(key, partial(self._shortcut, widget))

    def toggle(self, widget: tk.Widget, state, faces: dict, key: str | None = None,
               life: Life = Life.now, gate=None) -> None:
        """한 버튼이 두 얼굴을 갈아 낀다. 서로 배타적인 짝을 두 버튼으로 두지 않는다.

        `state()` 가 지금 어느 얼굴인지 말하고, `faces` 가 얼굴마다 (글자, 할 일, 쪽지)를 든다.
        얼굴을 갈아 끼우는 것은 `sweep` 이 주기마다 한다 — 상태가 우리 손 밖에서도 바뀌기 때문이다.
        연결이 끊기면 아무도 안 눌렀는데 버튼이 `연결` 로 돌아와야 한다.
        """
        self.bound[widget] = dict(work=None, life=life, gate=gate, tip=Tip(widget, ""),
                                  state=state, faces=faces)
        if key:
            self.root.bind(key, partial(self._shortcut, widget))

    def _shortcut(self, widget: tk.Widget, event: tk.Event) -> None:
        """단축키 하나. 버튼과 같은 문(`gate`)을 거친다 — 흐려진 버튼의 일은 단축키로도 안 한다.

        글자를 치는 칸(`TYPING_WIDGETS`)에서 친 키는 듣지 않는다 — 좌표 칸에 소수점을 치다가 다음 장으로 넘어가지 않는다.
        """
        if isinstance(event.widget, self.TYPING_WIDGETS): return
        one = self.bound[widget]
        if one["gate"] is not None and not one["gate"]()[0]: return
        faces = one.get("faces")
        work = faces[bool(one["state"]())][1] if faces is not None else one["work"]
        work()

    def choose(self, widget: tk.Widget, variable: tk.Variable, value: str, work, gate=None) -> None:
        """라디오 하나를 무리에 묶는다. 무엇을 고르는 무리인지는 변수가 정한다. `gate` 가 있으면 주기마다 묻고 흐리게 둔다(`sweep`)."""
        widget.configure(value=value, variable=variable, command=work)
        self.bound[widget] = dict(work=work, life=Life.now, gate=gate, tip=None)

    def link(self, build: "Build", variable: tk.Variable, node: type, work=None) -> None:
        """배타 자리와 그 고르개를 잇는다. 어느 고르개인지는 선언(`chooser`)이 말한다.

        `work` 는 갈아 끼운 **그때** 한 번 부른다.
        주기마다 할 일과 갈릴 때만 할 일이 다르기 때문이다 — 절대 칸을 지금 자리로 채우는 것이 뒤쪽이다.
        """
        #: 아직 고른 것이 없으면 선언의 첫째가 선다. `Build.put` 도 첫째를 올려 둔다
        if not variable.get():
            variable.set(node.labels()[0])

        def show() -> None:
            build.show(node, variable.get())
            if work is not None:
                work()

        for label, widget in build.repeated[node.chooser].items():
            self.choose(widget, variable, label, show)
        show()

    def sweep(self) -> None:
        """지금 뜻이 없는 것을 흐리게 두고 사유를 쪽지에 얹는다. 주기마다 부른다."""
        for widget, one in self.bound.items():
            faces = one.get("faces")
            if faces is not None:
                text, work, tip = faces[bool(one["state"]())]
                widget.configure(text=text, command=work)
                one["tip"].base = tip
            if one["gate"] is None:
                continue
            allowed, why = one["gate"]()
            widget.configure(state="normal" if allowed else "disabled")
            if one["tip"] is not None:
                one["tip"].reason("" if allowed else why)


# =========================================================================
# 4. 창
# =========================================================================

class Painter:
    """영상 위에 그린다.

    무슨 색으로 몇 픽셀로 그릴지가 여기 일이고, 어떤 층이 있고 무슨 뜻인지는 정의가 든다 (`ui.json` 의 `layers` · `overlays`).
    이름마다 그리는 함수 하나를 갖고, 정의에 있는데 여기 없으면 화면을 세울 때 걸린다.

    받을 값이 아직 없으면 그리지 않고 돌아간다 — 자리는 지금 서 있고 값만 나중에 온다.
    그리는 함수의 서명이 모두 같은 것은 아래 표가 한 가지 꼴로 부르기 때문이다.
    """

    LINE = 2            # 도형 선 두께
    THIN = 1            # 보조 도형 선 두께
    NAME_OFFSET_PX = 4
    PICK_RADIUS_PX = 3  # 받은 점 표시의 반지름
    OUTSIDE_DIM = 0.82  # 작업영역 밖을 덮을 검정의 세기

    def polygon(image, points, color, thickness=LINE) -> None:
        if not points:
            return
        pts = np.array([[int(round(x)), int(round(y))] for x, y in points], np.int32)
        cv2.polylines(image, [pts], True, color, thickness, cv2.LINE_AA)

    # ------------------------------------------------------------ 바탕 위의 층

    def mask(image, scene, key, color, alpha) -> None:
        """이진 마스크에 색을 입혀 섞는다. 두 층까지는 한 화면에서 읽힌다."""
        found = scene.mask(key)
        if found is None:
            return
        tint = np.zeros_like(image)
        tint[:] = color
        picked = found.astype(bool)
        image[picked] = cv2.addWeighted(image, 1.0 - alpha, tint, alpha, 0.0)[picked]

    def cuts(image, scene, key, color, alpha) -> None:
        """밀착을 가른 절단선."""
        for (x0, y0), (x1, y1) in scene.mask(key) or ():
            cv2.line(image, (int(x0), int(y0)), (int(x1), int(y1)),
                     color, Painter.LINE, cv2.LINE_AA)

    def silhouette(image, scene, key, color, alpha) -> None:
        """상면에서 내린 옆면 실루엣. 세로 소실점이 풀려야 값이 온다."""
        for hull in scene.mask(key) or ():
            Painter.polygon(image, hull, color, Painter.THIN)

    # ------------------------------------------------------------ 오버레이

    def work_area(image, data, project, color) -> None:
        """작업영역. 밖을 어둡게 덮는다 — 밝기 차이 하나로 안과 밖이 갈린다."""
        points = project(data.work_area_px)
        if not points:
            return
        pts = np.array([[int(round(x)), int(round(y))] for x, y in points], np.int32)
        inside = np.zeros(image.shape[:2], np.uint8)
        cv2.fillPoly(inside, [pts], 255)
        outside = inside == 0
        image[outside] = (image * (1.0 - Painter.OUTSIDE_DIM)).astype(image.dtype)[outside]

    def reach(image, data, project, color) -> None:
        """로봇이 집고 놓을 수 있는 곳(`Config.Robot.reachable_outlines_mm`). 블록 윗면 중심이 이 안이면 집힌다 — 그래서 H35 평면에 그린다."""
        for loop in data.reach_px:
            Painter.polygon(image, project(loop), color, Painter.THIN)

    def label(image, data, project, color) -> None:
        """사람이 그린 사각형. 규격을 옆에 적는다."""
        for corners, length_mm in data.quads:
            moved = project(corners)
            if not moved:
                continue
            Painter.polygon(image, moved, color, Painter.THIN)
            x, y = moved[0]
            cv2.putText(image, f"{length_mm:.0f}", (int(x), int(y) - Painter.NAME_OFFSET_PX),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, Painter.THIN, cv2.LINE_AA)

    def detection(image, data, project, color) -> None:
        for piece in data.scene.pieces:
            Painter.polygon(image, project(piece.corners_px), color)

    def spec_name(image, data, project, color) -> None:
        """규격과 각도. 검출 층에 딸린 글자다."""
        for piece in data.scene.pieces:
            moved = project(piece.corners_px)
            if not moved:
                continue
            x, y = moved[0]
            length = f"{piece.block.length__mm:.0f}" if piece.block else "—"
            cv2.putText(image, f"{length} · {piece.pose.angle_deg:.1f}",
                        (int(x), int(y) - Painter.NAME_OFFSET_PX),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, Painter.THIN, cv2.LINE_AA)

    def rejected(image, data, project, color) -> None:
        """규격에 맞지 않아 집지 않는 덩어리. 왜 안 집는지 화면에서 보이게 한다."""
        for lump in data.scene.rejected:
            Painter.polygon(image, project(lump.contour_px), color, Painter.THIN)

    def coverage(image, data, project, color) -> None:
        """회차 전체의 라벨이 화면 어디에 몰렸는지. 사각형이 겹친 수를 흐려, 진할수록 많다."""
        placed = [moved for corners, _ in data.coverage_quads if (moved := project(corners))]
        if not placed:
            return
        count = np.zeros(image.shape[:2], np.float32)
        for moved in placed:
            count += Tool.Vision.fill_polygons(image.shape[:2], [moved], 1)
        side = data.coverage.blur_kernel_odd_px
        density = cv2.GaussianBlur(count, (side, side), 0)
        weight = (data.coverage.alpha * density / density.max())[..., None]
        image[:] = (image * (1.0 - weight) + np.array(color, np.float32) * weight).astype(image.dtype)

    def picked(image, points, project, color) -> None:
        """점을 받는 중이면 받은 점과 그 사이 선. 오버레이가 아니라 받는 동안만 선다 — 어디까지 찍었는지 보면서 찍는다."""
        moved = project(points)
        if not moved:
            return
        pts = np.array([[int(round(x)), int(round(y))] for x, y in moved], np.int32)
        cv2.polylines(image, [pts], False, color, Painter.THIN, cv2.LINE_AA)
        for x, y in pts:
            cv2.circle(image, (int(x), int(y)), Painter.PICK_RADIUS_PX, color, Painter.THIN, cv2.LINE_AA)

    #: 층 · 오버레이 열쇠마다 그리는 함수 하나
    LAYER_DRAW = {"foreground": mask, "top_anchor": mask,
                  "cut": cuts, "silhouette": silhouette}
    OVERLAY_DRAW = {"work_area": work_area, "reach": reach, "label": label, "detection": detection,
                    "spec_name": spec_name, "rejected": rejected, "coverage": coverage}

    @classmethod
    def require(cls, ui: "Config.Ui") -> None:
        """정의에 있는데 그릴 줄 모르는 것이 있으면 화면을 세우다 멈춘다.

        그리는 중에 터지면 갱신 고리가 죽어 창이 굳는다. 세울 때 걸리면 무엇이 빠졌는지 남는다.
        """
        for defined, draw, what in ((ui.layers, cls.LAYER_DRAW, "층"),
                                    (ui.overlays, cls.OVERLAY_DRAW, "오버레이")):
            for key, one in defined.items():
                if key not in draw:
                    raise Tool.Missing(
                        f"ui.json 이 선언한 {what} '{key}'({one.name})를 그릴 줄 모른다")


class Base(NamedTuple):
    """화면 바탕 하나. 묶음(그대로 · 전처리)과 좌표계, 그리고 `Scene` 의 어느 자리에서 오는지.

    좌표계가 갈리는 것이 핵심이다 — 복원 바탕은 상면 mm 평면이라 화소로 저장된 작업영역과 라벨을 그대로 얹을 수 없다.
    """

    PIXEL = "화소"
    WORLD = "상면 mm"

    name: str
    group: str
    space: str
    field: str      # `Entity.Scene` 의 어느 자리에서 오는가

    @property
    def is_world(self) -> bool:
        return self.space == self.WORLD


class Pick(NamedTuple):
    """영상에서 점을 받는 중인 일 하나. 다 받으면 `then` 이 원본 화소 점들을 가져간다."""

    what: str
    need: int
    then: Any
    points: tuple = ()


class Draw(NamedTuple):
    """오버레이가 받을 한 벌. 그리는 함수마다 필요한 것이 달라 한 묶음으로 넘긴다."""

    scene: "Entity.Scene"
    quads: tuple                # 이 장의 정답 라벨
    work_area_px: tuple         # 회차 문서의 작업영역 다각형
    reach_px: tuple             # 로봇이 집고 놓을 수 있는 곳의 외곽선들 — H35 평면에 옮긴 화소
    coverage_quads: tuple       # 보고 있는 회차의 정답 라벨 전체
    coverage: "Config.Ui.Viewer.Coverage"


class Shell:
    """창 하나. 뼈대를 세우고 계통과 탭을 갈아 끼운다."""

    LIVE = "실시간"          # 카메라에서 바로 들어오는 것

    #: 바탕 목록. 묶음과 좌표계가 함께 온다 — 복원 바탕은 mm 평면이라 오버레이도 함께 옮겨야 한다
    BASES = (Base("원본", "그대로", Base.PIXEL, "image"),
             Base("H35 복원", "그대로", Base.WORLD, "rectified"),
             Base("플랫필드 보정", "전처리", Base.PIXEL, "preprocessed"),
             Base("CLAHE 대비 강화", "전처리", Base.PIXEL, "preprocessed"),
             Base("조명 배경 제거", "전처리", Base.PIXEL, "preprocessed"),
             Base("간극 강조", "전처리", Base.PIXEL, "preprocessed"))
    BASE_BY_NAME = {one.name: one for one in BASES}

    width_px = 1080
    height_px = 760
    log_lines = 4
    log_keep = 200           # 기록에 남겨 두는 줄 수. 넘으면 위부터 밀려 나간다

    root: tk.Tk
    factory: Factory
    ledger: dict
    build: Build
    bind: Bind
    system_name: tk.StringVar      # 고른 계통의 글자
    source: tk.StringVar           # 보고 있는 것. 회차 이름이거나 카메라 입력 항목이다
    live_names: tuple              # 카메라 입력 항목. 붙은 카메라의 이름이고, 하나도 없으면 실시간 하나다
    frozen: tk.BooleanVar          # 화면을 붙잡아 둔다
    base: tk.StringVar             # 바탕으로 무엇을 보는가
    layer: dict                    # 층 이름 → 켜짐
    overlay: dict                  # 오버레이 이름 → 켜짐
    scene: Any = None              # 바탕에 올린 장면. 크기가 바뀌면 이것으로 다시 그린다
    quads: tuple = ()              # 그 장의 정답 라벨
    coverage_quads: tuple = ()     # 보고 있는 회차의 정답 라벨 전체. 실시간이면 비어 있다
    work_area_px: tuple = ()       # 회차의 작업영역 다각형
    reach_px: tuple = ()           # 로봇이 집고 놓을 수 있는 곳의 외곽선들. 아핀이 없으면 비어 있다
    scale: float = 1.0            # 원본 화소 → 화면. 좌표를 되돌릴 때 쓴다
    missing_base: str = ""         # 고른 바탕이 아직 없으면 그 이름
    picking: Any = None            # 점을 받는 중이면 그 진행
    listeners: list                # 기록 한 줄을 함께 받는 쪽. 수집이 워커들의 말을 제 기록에 남기고, 자동 순서가 단계를 넘긴다
    waiting: list                  # 맡긴 일 가운데 끝나기를 기다리는 것 — (표, 끝나면 화면이 할 일)
    panels: dict                   # 탭 선언 → 그 탭의 기능
    chrome: Any = None             # 상주 영역. 탭이 회차 값을 고친 뒤 다시 그리게 한다
    shown: dict                    # tk 위젯 이름 → 탭 선언
    drawn_size: tuple[int, int] = (0, 0)  # 바탕에 실제로 놓인 그림 크기

    def __init__(self, root: tk.Tk, factory: Factory, ledger: dict) -> None:
        self.root = root
        self.factory = factory
        self.ledger = ledger
        self.build = Build(factory, ledger)
        self.bind = Bind(root)
        self.panels = {}
        self.shown = {}
        self.listeners = []
        self.waiting = []
        self._put()

    def when_done(self, future: Future, then) -> None:
        """맡긴 일이 끝나면 화면이 할 일(`then(돌려준 값)`)을 건다. 다른 스레드가 끝내도 화면 일은 화면 스레드에서 한다(`sweep_done`)."""
        self.waiting.append((future, then))

    def sweep_done(self) -> None:
        """주기마다 — 끝난 일의 화면 일을 맡긴 차례대로 한다. 실패한 일은 맡은 워커가 이미 알렸다."""
        done = [one for one in self.waiting if one[0].done()]
        for one in done:
            self.waiting.remove(one)
        for future, then in done:
            if future.exception() is None: then(future.result())

    def _put(self) -> None:
        theme = self.factory.ui.theme
        colors = theme.themes[theme.default].colors
        self.root.geometry(f"{self.width_px}x{self.height_px}")
        self.root.configure(bg=colors.ground)
        self.root.flow = Flow.column

        self.system_name = tk.StringVar(value=next(iter(Chrome.Body.Column.tabs.items()))[1].text)
        self.source = tk.StringVar(value=self.LIVE)
        self.live_names = (self.LIVE,)
        self.frozen = tk.BooleanVar(value=False)
        ui = self.factory.ui
        self.base = tk.StringVar(value=self.BASES[0].name)
        self.layer = {one.name: tk.BooleanVar(value=one.on) for one in ui.layers.values()}
        self.overlay = {one.name: tk.BooleanVar(value=one.on) for one in ui.overlays.values()}
        self.ledger["screen.systems"] = [thing.text for _, thing in Chrome.Body.Column.tabs.items()]

        self.build.put(Chrome.SystemBar, self.root)
        self.build.put(Chrome.Body, self.root)

        # 치수는 여기서 건다. 세운 뒤 그 위젯을 만지면 되는 것들이다
        self.build[Chrome.Body.Left].pack_propagate(False)
        self.build[Chrome.Body.Column].configure(padding=8)
        self.log.configure(height=2 + self.log_lines)
        self.stage.bind("<Configure>", self._stage_resized)
        self.stage.bind("<Button-1>", self._stage_clicked)
        self.stage.bind("<Button-3>", self._stage_right_clicked)
        for leaf, style in ((Chrome.Body.Left.alert, Style.alert),
                            (Chrome.Body.Left.busy, Style.busy)):
            self.build[leaf].configure(style=style)
            self.build[leaf].pack_forget()

        self.shown = {str(self.build[tab]): tab
                      for _, system in Chrome.Body.Column.tabs.items() for _, tab in system.items()}
        for name, widget in self.build.repeated[Chrome.SystemBar].items():
            self.bind.choose(widget, self.system_name, name, self._system_changed)
        self._system_changed()
        self.notebook.bind("<<NotebookTabChanged>>", self._tab_shown)

    # ------------------------------------------------------------ 갈아 끼우기

    @property
    def stage(self) -> tk.Label:
        return self.build[Chrome.Body.Left.stage]

    @property
    def log(self) -> tk.Text:
        return self.build[Chrome.Body.Left.log]

    @property
    def notebook(self) -> ttk.Notebook:
        return self.build[Chrome.Body.Column.tabs]

    def _system(self) -> type:
        return {thing.text: thing for _, thing in Chrome.Body.Column.tabs.items()}[self.system_name.get()]

    def tab(self) -> type:
        """지금 보이는 탭의 선언."""
        return self.shown[self.notebook.select()]

    def live(self) -> bool:
        """지금 보는 것이 카메라 입력인가. 회차 사진을 볼 때는 못 하는 일이 있다."""
        return self.source.get() in self.live_names

    def _system_changed(self) -> None:
        """계통이 바뀌면 그 계통의 탭만 띄운다. 헐지 않고 감췄다 꺼낸다."""
        mine = [node for _, node in self._system().items()]
        for _, system in Chrome.Body.Column.tabs.items():
            for _, node in system.items():
                frame = self.build[node]
                if node in mine:
                    self.notebook.add(frame, text=node.text)
                else:
                    self.notebook.hide(frame)
        self.notebook.select(self.build[mine[0]])

    def _tab_shown(self, _event=None) -> None:
        """탭이 바뀌면 그 탭의 값을 한 번 채운다. 다음은 주기가 맡는다."""
        self.panels[self.tab()].refresh()

    # ------------------------------------------------------------ 바탕

    def alert(self, text: str) -> None:
        """끊김을 알리는 띠. 글이 없으면 자리를 아예 비운다."""
        self._strip(Chrome.Body.Left.alert, text)

    def busy(self, text: str) -> None:
        """오래 걸리는 동작이 도는 중임을 알리는 띠."""
        self._strip(Chrome.Body.Left.busy, text)

    def _strip(self, leaf: type, text: str) -> None:
        """띠 하나를 올리거나 내린다.
        늘 깔려 있는 첫 줄을 기준으로 끼운다 — 기준이 내려가 있으면 tk 가 자리를 못 잡는다.
        """
        widget = self.build[leaf]
        if not text:
            widget.pack_forget()
            return
        widget.configure(text=text)
        widget.pack(fill="x", before=self.build[Chrome.Body.Left.viewing])

    def status(self, viewing: str, assets: str) -> None:
        """바탕 아래 두 줄. 그 값을 볼 다른 데가 없는 것만 적는다."""
        self.build[Chrome.Body.Left.viewing].configure(text=viewing)
        self.build[Chrome.Body.Left.assets].configure(text=assets)

    def say(self, text: str) -> None:
        """기록에 한 줄 쌓는다. 오래된 줄은 위부터 밀려 나간다."""
        self.log.configure(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {text}\n")
        self.log.delete("1.0", f"end-{self.log_keep}l")
        self.log.see("end")
        self.log.configure(state="disabled")
        for listener in self.listeners:
            listener(text)

    # ----------------------------------------------------- 무대 그리기

    def show(self, scene: Any, quads: tuple = (), work_area_px: tuple = (), reach_px: tuple = ()) -> None:
        """장면 하나를 바탕에 건다. 이후 다시 그릴 때도 이 한 벌을 쓴다."""
        self.scene = scene
        self.quads = quads
        self.work_area_px = work_area_px
        self.reach_px = reach_px
        self.draw()

    def draw(self) -> None:
        """건 장면을 그린다. 바탕을 고르고 층과 오버레이를 얹은 뒤 창에 맞춰 줄인다.

        창을 키우면 같이 커진다 — 그것이 확대다.
        그림은 공장이 든다: 파이썬 쪽 참조가 끊기면 tk 가 지워서 바탕이 빈 칸이 된다.
        """
        ui = self.factory.ui
        theme = self.factory.theme
        spec = self.BASE_BY_NAME[self.base.get()]
        source = getattr(self.scene, spec.field, None)
        self.missing_base = "" if source is not None else spec.name
        image = (source if source is not None else self.scene.image).copy()

        for key, one in ui.layers.items():
            if self.layer[one.name].get():
                Painter.LAYER_DRAW[key](image, self.scene, key,
                                        theme.bgr(one.color), ui.viewer.overlay_alpha)
        #: 복원 바탕인데 편 그림이 아직 없으면 오버레이를 얹지 않는다. 좌표계가 다르다
        if source is not None or not spec.is_world:
            data = Draw(scene=self.scene, quads=self.quads, work_area_px=self.work_area_px, reach_px=self.reach_px,
                        coverage_quads=self.coverage_quads, coverage=ui.viewer.coverage)
            project = partial(self._project, scene=self.scene, spec=spec)
            for key, one in ui.overlays.items():
                if self.overlay[one.name].get():
                    Painter.OVERLAY_DRAW[key](image, data, project, theme.bgr(one.color))
            if self.picking is not None:
                Painter.picked(image, self.picking.points, project, theme.bgr("accent"))

        self.scale = self.fit_scale(image.shape[1], image.shape[0])
        size = (max(1, round(image.shape[1] * self.scale)),
                max(1, round(image.shape[0] * self.scale)))
        picture = Image.fromarray(image[:, :, ::-1]).resize(size, Image.LANCZOS)
        self.factory.images["stage"] = ImageTk.PhotoImage(picture)
        self.stage.configure(image=self.factory.images["stage"])
        self.drawn_size = size

    def clear(self) -> None:
        """바탕을 비운다. 볼 것이 없을 때다."""
        self.scene = None
        self.stage.configure(image="")
        self.drawn_size = (0, 0)

    def _stage_resized(self, _event) -> None:
        """바탕이 커지거나 작아지면 그 크기에 맞춰 다시 그린다."""
        if self.scene is not None:
            self.draw()

    @staticmethod
    def _project(points, scene: Any, spec: Base):
        """화소로 저장된 도형을 지금 바탕의 좌표계로 옮긴다.

        화소 바탕이면 그대로다.
        복원 바탕은 mm 평면이므로 그 그림을 만든 변환을 함께 받아야 한다 — 없으면 그리지 않는다.
        """
        if not spec.is_world:
            return points
        if scene.rectify_matrix is None or not points:
            return ()
        return tuple(map(tuple, Tool.Fit.Homography.project(points, scene.rectify_matrix).tolist()))

    # ----------------------------------------------------- 좌표와 찍기

    def fit_scale(self, width_px: int, height_px: int) -> float:
        """영상 한 장이 바탕에 통째로 들어가는 축척. 가로 세로 중 모자란 쪽이 정한다."""
        return min(self.stage.winfo_height() / height_px, self.stage.winfo_width() / width_px)

    def origin(self) -> tuple[int, int]:
        """그림의 왼쪽 위가 바탕의 어디인가. 바탕이 더 크면 그림이 가운데 놓인다."""
        width_px, height_px = self.drawn_size
        return ((self.stage.winfo_width() - width_px) // 2,
                (self.stage.winfo_height() - height_px) // 2)

    def begin_pick(self, what: str, need: int, then) -> None:
        """영상에서 점을 받기 시작한다. 진행은 바탕 아래 줄이 적는다."""
        self.picking = Pick(what, need, then)
        self.say(f"{what} :: 영상에서 {need}점을 찍는다")

    def _stage_clicked(self, event) -> None:
        """영상 위 좌클릭. 점을 받는 중이면 그 점이 된다."""
        if self.picking is None:
            return
        u, v = self.to_source(event.x, event.y)
        self.picking = self.picking._replace(points=self.picking.points + ((u, v),))
        if len(self.picking.points) < self.picking.need:
            self._redraw_picks()
            return
        done, self.picking = self.picking, None
        done.then(done.points)
        self._redraw_picks()

    def _stage_right_clicked(self, _event) -> None:
        """영상 위 우클릭. 점을 받는 중이면 그만둔다."""
        if self.picking is None:
            return
        self.say(f"{self.picking.what} :: 그만뒀다")
        self.picking = None
        self._redraw_picks()

    def _redraw_picks(self) -> None:
        """받은 점이 바뀌면 다시 그린다. 실시간은 주기가 다시 그리지만 회차 사진은 그대로 멈춰 있다."""
        if self.scene is not None:
            self.draw()

    def to_source(self, x: int, y: int) -> tuple[int, int]:
        """화면 좌표 → 원본 화소. 라벨과 작업영역은 원본 화소로 저장한다."""
        left, top = self.origin()
        return self.factory.ui.viewer.to_source_px((x - left, y - top), self.scale)

    def to_screen(self, u: float, v: float) -> tuple[float, float]:
        """원본 화소 → 화면 좌표."""
        left, top = self.origin()
        return (u * self.scale + left, v * self.scale + top)


# =========================================================================
# 5. 기능 — 탭마다 하나
# =========================================================================

class RobotPanel:
    """로봇 탭의 기능. 선언은 `Chrome.Body.Column.tabs.Equipment.Robot` 이, 동작은 `rbt_alg_core` 가 든다.

    여기 있는 것은 둘을 잇는 일뿐이다 — 어느 위젯이 무엇을 보내고, 언제 잠기고, 무엇을 보이나.
    """

    #: 걸음 크기 목록. 사람이 고르는 눈금이라 화면이 든다
    STEP_MM = (0.5, 1.0, 5.0, 10.0, 25.0)
    STEP_DEG = (0.5, 1.0, 5.0, 10.0)
    #: 이송 속도 눈금(mm/min). 절대 · 상대 · 지정동작이 이 하나를 같이 쓴다.
    #: 호밍만 빼는데 `o105=8` 이 속도 인자를 안 받기 때문이다. 목록 밖도 칠 수 있다
    SPEED = (500.0, 1000.0, 1500.0, 2000.0)
    Kind = Config.Robot.Route.Kind

    class Face(NamedTuple):
        """좌표 방식 하나가 화면에 내놓는 것."""

        name: str                # 사람이 읽는 이름
        axes: tuple[str, ...]    # 그 방식의 축 이름. 명령 글자와 달리 사람이 읽는 것이다

    #: 좌표 방식 표. 장부도 되찾기도 축 이름도 여기 하나를 본다
    JOG = {Kind.CART: Face("직교", Config.Robot.Route.AXIS_NAMES[Kind.CART]),
           Kind.JOINT: Face("관절", Config.Robot.Route.AXIS_NAMES[Kind.JOINT])}

    #: 소리가 답한 것을 사람 말로. 흡착 지령일 때만 쓴다
    GRIP = {True: "붙음", False: "누설", None: "모름"}

    node = Chrome.Body.Column.tabs.Equipment.Robot

    @staticmethod
    def labelled(names: tuple, values) -> str:
        """이름을 붙여 늘어놓는다. 자리를 세어 어느 축인지 알아내게 하지 않는다."""
        if not values:
            return "—"
        return "  ".join(f"{name} {value:7.2f}" for name, value in zip(names, values))

    @classmethod
    def kind_of(cls, name: str) -> "Config.Robot.Route.Kind":
        """사람이 읽는 이름에서 좌표 방식을 되찾는다."""
        return next(kind for kind, face in cls.JOG.items() if face.name == name)

    shell: "Shell"
    bus: "rbt_alg_core.RobotBus"
    ear: "rbt_alg_core.VacuumEar"
    robot: Tool.Slot  # 현행 `Config.Robot`. 준비 탭 · 오버레이와 같은 슬롯이고, 티칭 뒤 `_taught` 가 갈아 끼운다
    sight: "vis_alg_core.CalcBus"
    writer: "Tool.Writer"  # 쓰기 주인. 티칭(`robot.json`)을 맡긴다
    used_grabbed: int | None = None  # 사이클 지령을 낸 관측. 한 관측으로는 한 번만 집는다 — 투입할 때마다 다시 본다
    jog_kind: tk.StringVar
    jog_way: tk.StringVar  # 어느 배타 자리를 올릴지. 값은 자식의 `text` 다
    goto: tuple[tk.StringVar, ...]  # 절대 칸에 사람이 친 값. 축마다 하나
    height_name: tk.StringVar  # 티칭 창이 고른 높이. 창을 닫았다 열어도 살아 있어야 해서 패널이 든다
    place_name: tk.StringVar  # 티칭 창이 고른 자리. 창을 닫았다 열어도 살아 있어야 해서 패널이 든다
    raw_line: tk.StringVar  # 티칭 창에 친 줄. 창을 닫았다 열어도 살아 있어야 해서 패널이 든다
    corners: list  # 둘레를 찍는 중에 모이는 점. 넷이 차면 정본으로 간다
    step_mm: tk.DoubleVar
    step_deg: tk.DoubleVar
    speed: tk.DoubleVar
    air_state: tk.StringVar
    height_key: str
    place_key: str

    def __init__(self, shell: "Shell", bus: "rbt_alg_core.RobotBus",
                 ear: "rbt_alg_core.VacuumEar", robot: Tool.Slot, sight: "vis_alg_core.CalcBus", writer: "Tool.Writer") -> None:
        self.shell = shell
        self.bus = bus
        self.ear = ear
        self.robot = robot
        self.sight = sight
        self.writer = writer
        self.jog_kind = tk.StringVar(value=Config.Robot.Route.Kind.CART)
        self.jog_way = tk.StringVar()
        self.goto = tuple(tk.StringVar() for _ in range(len(self.JOG[self.Kind.CART].axes)))
        self.height_name = tk.StringVar()
        self.place_name = tk.StringVar()
        self.raw_line = tk.StringVar()
        self.corners = []
        self.step_mm = tk.DoubleVar(value=self.STEP_MM[1])
        self.step_deg = tk.DoubleVar(value=self.STEP_DEG[1])
        self.speed = tk.DoubleVar(value=self.SPEED[-1])
        #: 설비는 정지에서 시작한다. 선언 첫 줄(흡착)을 쓰면 화면이 사실과 다르다
        self.air_state = tk.StringVar(value=self.robot.get().motion.pneumatics_pwm.State.IDLE.name)

    # ------------------------------------------------------------ 묶기

    #: 좌표 한 줄의 글자 수. 이름 셋(`Rx `) + 값 아홉(`-1234.56` 여덟이 최악).
    #: 박아 두지 않으면 값이 폭을 정해서 줄마다 버튼 자리가 어긋난다
    AT_CHARS = 12

    #: 가동범위 둘레를 이루는 점 수. 네 귀퉁이를 조그로 돈다
    REACH_POINTS = 4

    def bind(self) -> None:
        Job, Stop = self.bus.Job, self.bus.Stop
        put, bind, node = self.shell.build, self.shell.bind, self.node

        bind.toggle(put[node.Status.Now.link], self._linked, life=Life.long, faces={
            False: ("연결", partial(self.bus.submit, Job.CONNECT), "시리얼을 연다"),
            True: ("해제", partial(self.bus.submit, Job.DISCONNECT),
                   "시리얼을 닫는다. 전원 투입 시점처럼 되돌린다")})
        #: `알람 해제`(`$X`) 버튼을 두지 않는다.
        #: 알람이 뜨는 경우는 전원 투입 · 복전 · 비상정지 뒤 · 소프트웨어 재시작이고 매뉴얼이 넷 다 호밍을 지시한다.
        #: `$X` 가 맞는 자리는 소프트 리셋 뒤인데 그 리셋을 쓰지 않는다 호밍은 `_can_move` 를 쓰지 않는다.
        #: 이 로봇은 **호밍 전이 늘 알람**이고 호밍이 그 알람을 벗어나는 유일한 길이라, 알람으로 막으면 영영 못 빠져나온다
        bind.press(put[node.Command.Act.home], self._home,
                   "전 축 원점 복귀. 알람을 벗어나는 길이다", life=Life.long,
                   gate=self._needs_link)
        #: 편의 제어다 — 통신을 타므로 통신이 끊기면 같이 죽는다.
        #: 사람을 지키는 것은 설비의 물리 비상정지다
        bind.toggle(put[node.Command.Act.halt], self._held, gate=self._needs_link, faces={
            False: ("⏸ 일시 정지", partial(self.bus.halt_now, Stop.HOLD), "지금 이송만 멈춘다"),
            True: ("▶ 재개", partial(self.bus.halt_now, Stop.RESUME), "멈춘 이송을 이어 간다")})

        bind.press(put[node.Command.teach], self._teach,
                   "티칭 창을 연다. 운전 창과 따로 선다")
        bind.press(put[node.Cycle.run], self._cycle,
                   "다음 블록 하나를 집어 투입점에 놓는다 — 로봇이 움직인다", life=Life.long, gate=self._can_cycle)

        for name, widget in put.repeated[node.Jog.Mode.Kind].items():
            bind.choose(widget, self.jog_kind, self.kind_of(name), self._relabel)
        bind.link(put, self.jog_way, node.Jog.Ways, self._way_changed)
        for leaf, hold, seen, wide in (
                (node.Jog.Ways.Step.Frame.step_mm, self.step_mm, self.STEP_MM, 4),
                (node.Jog.Ways.Step.Frame.step_deg, self.step_deg, self.STEP_DEG, 4),
                (node.Jog.Speed.speed, self.speed, self.SPEED, 5)):
            put[leaf].configure(textvariable=hold, values=seen, width=wide)

        axis = node.Jog.Ways.Step.Axes.template
        for index, bag in enumerate(put.repeated[node.Jog.Ways.Step.Axes].values()):
            for sign, leaf in ((-1.0, axis.minus), (+1.0, axis.plus)):
                bind.press(bag[leaf], partial(self._jog, index, sign),
                           "한 걸음 민다", gate=self._can_move)
        for bag in put.repeated[node.Jog.Ways.Step.Axes].values():
            bag[axis.at].configure(width=self.AT_CHARS, anchor="w")

        aim = node.Jog.Ways.Goto.Axes.template
        for index, bag in enumerate(put.repeated[node.Jog.Ways.Goto.Axes].values()):
            bag[aim.to].configure(textvariable=self.goto[index], justify="right")
        bind.press(put[node.Jog.Ways.Goto.go], self._goto,
                   "친 좌표로 간다", life=Life.long, gate=self._can_move)
        self._relabel()

        bind.press(put[node.Status.swap], self.ear.next_device,
                   "다음 마이크로 옮겨 문다. 기준을 새로 잡는다", gate=self._hearing)

        for name, widget in put.repeated[node.Command.Air].items():
            state = next(one for one in self.robot.get().motion.pneumatics_pwm.State if one.value == name)
            bind.choose(widget, self.air_state, state.name, self._air, gate=self._air_free)

    # ------------------------------------------------------------ 잠금

    def _linked(self) -> bool:
        return bool(self.bus.connected.get())

    def _needs_link(self) -> tuple[bool, str]:
        return self._linked(), "로봇 미연결"

    def _air_free(self) -> tuple[bool, str]:
        """공압 고르개를 쓸 수 있는가. 일감(사이클 · 수집 · 호밍 · 이동)이 도는 동안은 프로그램이 공압을 다룬다."""
        if not self._linked():
            return False, "로봇 미연결"
        if self.bus.busy.get():
            return False, "로봇이 일하는 중이다"
        return True, ""

    def _held(self) -> bool:
        """지금 멈춰 있는가. 컨트롤러가 상태 문자로 말한다 — 우리가 따로 안 든다."""
        status = self.bus.status.get()
        return status is not None and status.state.strip().lower().startswith("hold")

    def _hearing(self) -> tuple[bool, str]:
        return self.ear.sound is not None, "마이크 미연결"

    def _can_move(self) -> tuple[bool, str]:
        if not self._linked():
            return False, "로봇 미연결"
        if self.bus.link.is_alarm(self.bus.status.get()):
            return False, "알람 상태"
        return True, ""

    def _teach(self) -> None:
        """티칭 창을 연다. 창 안의 위젯은 **창이 선 뒤에** 묶는다."""
        first = Teach not in self.shell.build.windows
        self.shell.build.window(Teach, self.shell.root, Teach.text)
        if not first:
            return
        put, bind = self.shell.build, self.shell.bind

        robot = self.robot.get()
        #: 고르개에 뜨는 이름은 정본이 든다. 여기서 이름 -> 키 로 되짚는다
        self.height_key = {one.label: key for key, one in robot.motion.heights.items() if isinstance(one, Tool.JsonNode)}
        self.place_key = {one.label: key for key, one in robot.motion.positions.items()}
        for group, table, hold in ((Teach.Heights, self.height_key, self.height_name),
                                   (Teach.Places, self.place_key, self.place_name)):
            names = list(table)
            hold.set(names[0])
            put[group.Pick.which].configure(textvariable=hold, values=names,
                                            state=State.readonly)
        bind.press(put[Teach.Heights.Pick.save], self._save_height,
                   "지금 Z 를 그 높이로 담는다", gate=self._needs_link)
        bind.press(put[Teach.Heights.Pick.go], self._go_height,
                   "담아 둔 높이로 Z 를 옮긴다", life=Life.long, gate=self._can_move)
        bind.press(put[Teach.Places.Pick.save], self._save_place,
                   "지금 XY 를 그 자리로 담는다", gate=self._needs_link)
        bind.press(put[Teach.Places.Pick.go], self._go_place,
                   "안전 고도에서 그 자리로 옮긴다", life=Life.long, gate=self._can_move)

        bind.press(put[Teach.Reach.Act.add], self._add_corner,
                   "지금 XY 를 둘레 한 점으로 담는다", gate=self._needs_link)
        bind.press(put[Teach.Reach.Act.clear], self._clear_corners, "찍던 것을 버린다")
        self._show_corners()

        put[Teach.Raw.Line.line].configure(textvariable=self.raw_line)
        bind.press(put[Teach.Raw.Line.send], self._send_raw,
                   "친 줄을 그대로 보낸다", gate=self._needs_link)

    # ------------------------------------------------------------ 티칭

    def _taught(self, said: str) -> None:
        """담기가 끝난 뒤 — 담은 것을 알리고 정본을 다시 읽는다. 안 읽으면 다음 기동까지 옛 값으로 움직인다."""
        self.shell.say(said)
        self.robot.put(Config.Robot.load(self.robot.get().vision_algorithm))

    def _save_height(self) -> None:
        self.shell.when_done(self.writer.submit(Config.Robot.Teaching.height, self.height_key[self.height_name.get()], self.bus.status.get()), self._taught)

    def _save_place(self) -> None:
        self.shell.when_done(self.writer.submit(Config.Robot.Teaching.place, self.place_key[self.place_name.get()], self.bus.status.get()), self._taught)

    def _go_height(self) -> None:
        key = self.height_key[self.height_name.get()]
        z_mm = getattr(self.robot.get().motion.heights, key).z__mm
        if z_mm is None:
            self.shell.say(f"{self.height_name.get()} 를 아직 안 담았다")
            return
        self._go(self.bus.route.height(z_mm, int(self.speed.get()), self.bus.status.get()))

    def _go_place(self) -> None:
        """고른 자리로 XY 만 옮긴다. **Z 는 안 따라간다** — 높이는 따로 고른다."""
        robot = self.robot.get()
        key = self.place_key[self.place_name.get()]
        if robot.motion.positions[key].xy is None:
            self.shell.say(f"{self.place_name.get()} 를 아직 안 담았다")
            return
        self._go(self.bus.route.plane(robot.motion.positions[key].xy,
                                      int(self.speed.get()), self.bus.status.get(),
                                      robot.motion.heights.z_safe.z__mm))

    def _add_corner(self) -> None:
        """지금 XY 를 둘레 한 점으로 담는다. 넷이 차면 정본에 쓴다."""
        seen = self.bus.status.get()
        if seen is None:
            self.shell.say("좌표를 못 읽어 담지 못했다")
            return
        self.corners.append((seen.cartesian[0], seen.cartesian[1]))
        if len(self.corners) >= self.REACH_POINTS:
            self.shell.when_done(self.writer.submit(Config.Robot.Teaching.reach, tuple(self.corners)), self._taught)
            self.corners.clear()
        self._show_corners()

    def _clear_corners(self) -> None:
        self.corners.clear()
        self._show_corners()

    def _show_corners(self) -> None:
        put = self.shell.build
        if Teach not in put.windows:
            return
        put[Teach.Reach.state].configure(
            text=f"{len(self.corners)} / {self.REACH_POINTS} 점")

    def _send_raw(self) -> None:
        line = self.raw_line.get().strip()
        if line:
            self.bus.submit(self.bus.Job.LINE, text=line)

    # ------------------------------------------------------------ 보내기

    def _home(self) -> None:
        robot = self.robot.get()
        self.bus.submit(self.bus.Job.HOME, robot=robot)

    def _jog(self, axis: int, sign: float) -> None:
        kind = self.Kind(self.jog_kind.get())
        step = self.step_mm.get() if Config.Robot.Route.is_mm_axis(kind, axis) else self.step_deg.get()
        self._go(self.bus.route.step(kind, axis, sign * step, int(self.speed.get())))

    def _go(self, plan: "Config.Robot.Route.Plan") -> None:
        """푼 것을 보낸다. 못 가면 까닭만 말하고 아무것도 안 보낸다."""
        if plan.refused:
            self.shell.say(plan.refused)
            return
        if plan.legs:
            self.bus.submit(self.bus.Job.MOVE, legs=plan.legs)

    def _air(self) -> None:
        pneumatics = self.robot.get().motion.pneumatics_pwm
        state = pneumatics.State[self.air_state.get()]
        self.bus.submit(self.bus.Job.AIR, level=pneumatics.level(state), label=state.value)

    def _show_axes(self, seen: tuple = ()) -> None:
        """축마다 `이름   값` 한 줄. 고정폭 글꼴이라 자릿수가 세로로 맞는다."""
        names = self.JOG[self.Kind(self.jog_kind.get())].axes
        axis = self.node.Jog.Ways.Step.Axes.template
        for index, bag in enumerate(self.shell.build.repeated[self.node.Jog.Ways.Step.Axes].values()):
            value = f"{seen[index]:.2f}" if index < len(seen) else "—"
            bag[axis.at].configure(text=f"{names[index]:<3}{value:>9}")

    def _relabel(self) -> None:
        """좌표 방식이 바뀌면 축 이름도 바뀐다. 같은 버튼이 다른 축을 민다."""
        names = self.JOG[self.Kind(self.jog_kind.get())].axes
        aim = self.node.Jog.Ways.Goto.Axes.template
        for index, bag in enumerate(self.shell.build.repeated[self.node.Jog.Ways.Goto.Axes].values()):
            bag[aim.name].configure(text=names[index])
        self._show_axes()

    def _way_changed(self) -> None:
        """방식을 갈아 끼웠다. 절대로 넘어왔으면 칸을 지금 자리로 채운다."""
        if self.jog_way.get() == self.node.Jog.Ways.Goto.text:
            self._fill_goto()

    def _fill_goto(self) -> None:
        """절대 칸을 지금 자리로 채운다.

        **넘어가는 그 순간 한 번만이다.** 주기마다 채우면 사람이 치는 동안 덮어쓴다.
        """
        seen = self.bus.route.at(self.Kind(self.jog_kind.get()), self.bus.status.get())
        if seen is None:
            return
        for hold, value in zip(self.goto, seen):
            hold.set(f"{value:.2f}")

    def _goto(self) -> None:
        """친 좌표로 간다. 올라가고 · 가로지르고 · 내려간다."""
        try:
            want = tuple(float(hold.get()) for hold in self.goto)
        except ValueError:
            self.shell.say("좌표 칸에 숫자가 아닌 것이 있다")
            return
        if self.Kind(self.jog_kind.get()) is not self.Kind.CART:
            self.shell.say("절대 이동은 직교 좌표에서만 낸다")
            return
        self._go(self.bus.route.travel(want[:2], want[2], int(self.speed.get()),
                                       self.bus.status.get(),
                                       self.robot.get().motion.heights.z_safe.z__mm))

    # ------------------------------------------------------------ 사이클

    def _target(self) -> tuple[Any, str]:
        """다음에 집을 블록 — ((지령, 기구 규격, 개체), "") 이거나 (None, 못 집는 까닭). 판정 루프의 마지막 관측에서 `RobotBus.next_sighting` 이 고른다."""
        seen = self.sight.seen.get()
        if seen is None:
            return None, "관측이 없다 — 실시간 · 작업영역 · H35 가 있고 로봇이 쉬고 있어야 한다"
        if seen.grabbed == self.used_grabbed:
            return None, "이 관측으로 이미 집었다 — 다음 관측을 기다린다"
        robot = self.robot.get()
        found, why = rbt_alg_core.RobotBus.next_sighting(seen, robot)
        if found is None:
            return None, why
        sighting, piece = found
        return (sighting, robot, piece), ""

    def _can_cycle(self) -> tuple[bool, str]:
        allowed, why = self._can_move()
        if not allowed:
            return False, why
        if self.bus.busy.get():
            return False, "로봇이 일하는 중이다"
        entry = self.robot.get().motion.positions.conveyor_entry
        if entry.xy is None:
            return False, f"{entry.label} 자리를 아직 안 담았다 — 티칭 창 자리 담기"
        found, why = self._target()
        return found is not None, why

    def _cycle(self) -> None:
        """한 사이클. 누른 순간의 관측으로 지령을 세워 보낸다."""
        found, why = self._target()
        if found is None:
            self.shell.say(f"사이클 :: {why}")
            return
        sighting, robot, piece = found
        self.used_grabbed = self.sight.seen.get().grabbed
        self.shell.say(f"사이클 :: 꼬리표 {piece.tag} · {piece.block.length__mm:.0f} mm")
        self.bus.submit(self.bus.Job.CYCLE, sighting=sighting, robot=robot, speed=int(self.speed.get()))

    # ------------------------------------------------------------ 보이기

    def refresh(self) -> None:
        put, node = self.shell.build, self.node
        status = self.bus.status.get()
        #: 끊긴 것과 붙었는데 상태를 못 읽는 것이 갈려야 한다. 한 줄로 둘 다 말한다
        put[node.Status.Now.state].configure(
            text=status.state if status is not None
            else ("연결됨 · 상태 없음" if self._linked() else "미연결"))
        put[node.Status.pump].configure(
            text=self._air_text(status.pump_pwm) if status is not None else "—")
        put[node.Status.firmware].configure(text=self.bus.firmware.get() or "—")
        #: 쉬는 동안 공압 고르개를 되읽은 펌프 PWM 에 맞춘다 — 프로그램이 공압을 바꾼 뒤에도 고른 것이 실제를 따른다
        if status is not None and status.pump_pwm is not None and not self.bus.busy.get():
            self.air_state.set(self.robot.get().motion.pneumatics_pwm.nearest_state(status.pump_pwm).name)

        #: 좌표는 축 버튼 바로 위에 선다. 지금 고른 좌표계가 무엇을 보일지 정한다
        kind = self.Kind(self.jog_kind.get())
        if status is None:
            seen = ()
        elif kind is self.Kind.CART:
            seen = status.cartesian
        else:
            #: 축마다 보고에서 제 자리를 골라 읽는다 (`angle_slots`)
            seen = tuple(status.angles_deg[one] for one in self.bus.gcode.angle_slots
                         if one < len(status.angles_deg))
        self._show_axes(seen)

        device = self.ear.sound.device if self.ear.sound is not None else None
        put[node.Status.device].configure(text=device["name"] if device else "—")

        found, why = self._target()
        if found is None:
            put[node.Cycle.target].configure(text=why)
        else:
            sighting, _, piece = found
            put[node.Cycle.target].configure(
                text=f"#{piece.tag} {piece.block.length__mm:.0f} mm ({sighting.x_mm:.1f}, {sighting.y_mm:.1f}) "
                     f"손목 {sighting.wrist_deg:.1f}→{sighting.place_wrist_deg:.1f}")

    def _air_text(self, pwm: int | None) -> str:
        """공압 한 줄. 무엇을 지령했는지는 되읽은 PWM 이, 붙었는지는 소리가 말한다.

        지령은 되읽은 값에서 지금 다시 읽고, 소리는 제가 그때 본 지령을 같이 들고 온다.
        둘이 다르면 답을 버린다 — 파기로 넘어간 직후의 한 홉 동안 `붙음` 이 남아 있게 두지 않는다.
        """
        if pwm is None:
            return "—"
        pneumatics = self.robot.get().motion.pneumatics_pwm
        state = pneumatics.nearest_state(pwm)
        if state is not pneumatics.State.VACUUM:
            return f"{state.value} {pwm}"
        heard = self.ear.heard.get()
        fresh = heard is not None and heard.commanded is state
        return f"{state.value} {pwm} · {self.GRIP[heard.gripped if fresh else None]}"


class PlcPanel:
    """PLC 탭의 기능. 읽기가 본업이고 쓰기는 사람이 태그와 값을 적어 한 번씩 보낸다."""

    node = Chrome.Body.Column.tabs.Equipment.Plc

    shell: "Shell"
    bus: "cnv_alg_core.PlcBus"
    tag: tk.StringVar
    value: tk.StringVar

    def __init__(self, shell: "Shell", bus: "cnv_alg_core.PlcBus") -> None:
        self.shell = shell
        self.bus = bus
        #: 고를 목록이 아직 없다. 사람이 표기를 직접 친다 (`cnv_alg_core` 머리말 ①)
        self.tag = tk.StringVar()
        self.value = tk.StringVar()

    def bind(self) -> None:
        Job = self.bus.Job
        put, bind, node = self.shell.build, self.shell.bind, self.node
        host = self.bus.communication.plc_controller[self.bus.which].transport.host   # 이 워커가 맡은 PLC 한 대

        bind.toggle(put[node.Link.Act.link], self._linked, life=Life.long, faces={
            False: ("연결", partial(self.bus.submit, Job.CONNECT), f"PLC 에 붙는다 :: {host}"),
            True: ("해제", partial(self.bus.submit, Job.DISCONNECT), "연결을 닫는다")})

        put[node.Direct.Tag.pick].configure(textvariable=self.tag)
        put[node.Direct.Act.value].configure(textvariable=self.value, width=8)
        bind.press(put[node.Direct.Act.read],
                   lambda: self.bus.submit(Job.READ, device=self.tag.get()),
                   "태그 하나를 읽는다", gate=self._needs_link)
        bind.press(put[node.Direct.Act.write],
                   lambda: self.bus.submit(Job.WRITE, device=self.tag.get(),
                                           value=self.value.get()),
                   "태그 하나에 값을 쓴다. BIT 는 0 · 1, WORD 는 정수",
                   gate=self._needs_link)

    def _linked(self) -> bool:
        return bool(self.bus.connected.get())

    def _needs_link(self) -> tuple[bool, str]:
        return self._linked(), "PLC 미연결"

    def refresh(self) -> None:
        put, node = self.shell.build, self.node
        put[node.Link.state].configure(text="연결됨" if self._linked() else "미연결")
        seen = self.bus.reading.get()
        put[node.Interlock.entry].configure(
            text="—" if seen is None else ("허가" if cnv_alg_core.PlcRead.is_feed_permitted(seen) else "대기"))


class QrPanel:
    """QR 탭. 누를 것이 없다 — 조건은 PLC 가 정하고 판독은 카메라가 한다."""

    STEP_TEXT = {cnv_alg_core.QrSort.Step.OFF: "센서 측정 모드다",
                 cnv_alg_core.QrSort.Step.WAIT: "자재를 기다린다",
                 cnv_alg_core.QrSort.Step.SCAN: "읽는 중",
                 cnv_alg_core.QrSort.Step.SENT: "보냈다. 자재가 나가기를 기다린다"}

    node = Chrome.Body.Column.tabs.Equipment.Qr

    shell: "Shell"
    bus: "cnv_alg_core.PlcBus"

    def __init__(self, shell: "Shell", bus: "cnv_alg_core.PlcBus") -> None:
        self.shell = shell
        self.bus = bus

    def bind(self) -> None:
        pass

    def refresh(self) -> None:
        put, node = self.shell.build, self.node
        seen = self.bus.special.get()
        if seen is None:
            put[node.Gate.mode].configure(text="—")
            put[node.Gate.entered].configure(text="—")
            put[node.Gate.step].configure(text="—")
        else:
            special_bit = cnv_alg_core.PlcRead.AddressRule.Type.SpecialBit
            reading_qr, entered = seen[special_bit.FLAG_DetectMode_QR], seen[special_bit.SIG_GET_CHK_L0]
            put[node.Gate.mode].configure(text="QR 판독" if reading_qr else "센서 측정")
            put[node.Gate.entered].configure(text="있다" if entered else "없다")
            put[node.Gate.step].configure(text=self.STEP_TEXT[self.bus.sorter.step])
        put[node.Read.spec].configure(text=self.bus.sorter.code.name if self.bus.sorter.code else "—")
        put[node.Read.previous].configure(
            text=self.bus.sorter.previous.name if self.bus.sorter.previous else "—")


class CameraPanel:
    """카메라 탭. 장치가 내주는 것만 만지고, 되읽어 보지 않고 값을 밀지 않는다."""

    node = Chrome.Body.Column.tabs.Vision.Camera

    class Exposure(StrEnum):
        """노출을 사람이 잡는가 장치가 잡는가."""

        MANUAL = "수동"
        AUTO = "자동"

    shell: "Shell"
    state: "vis_alg_core.EraState"
    eye: "vis_alg_core.CameraBus"
    camera: "Config.Camera"  # 회차 밖 규격(버스트 · 자동 문턱 · DirectShow 대응). 회차 값은 현행 값이 든다
    exposure: tk.StringVar
    found: list              # 붙어 있는 카메라 식별자. 열거는 한 번만 한다
    _burst: tuple = (0.0, 0.0, 0)  # 진행 중인 버스트 (시작 시각, 마지막 촬영 시각, 찍은 장 수)
    _synced: Any = None      # 슬라이더 손잡이를 맞춘 설정 한 벌

    def __init__(self, shell: "Shell", state: "vis_alg_core.EraState",
                 eye: "vis_alg_core.CameraBus", camera: "Config.Camera") -> None:
        self.shell = shell
        self.state = state
        self.eye = eye
        self.camera = camera
        self.exposure = tk.StringVar(value=self.Exposure.MANUAL)
        self.found = Connect.Device.Usb.camera_ids()

    def _attached(self, camera: "Config.Dataset.EraValues.Camera | None") -> str:
        """식별자를 화면에 내지 않는다 — 사람이 알아야 하는 것은 같은 장치인가 아닌가다."""
        if not any(one is not None for one in self.found):
            return "USB 카메라가 없다"
        if camera is None:
            return "현행 값이 없다 — 카메라를 열면 올린다"
        if camera.device is None:
            return "회차가 장치를 안 적어 견줄 수 없다"
        return "이력 장치" if camera.device.is_among(self.found) else "다른 장치"

    def bind(self) -> None:
        put, bind, node = self.shell.build, self.shell.bind, self.node
        not_live = lambda: (self.shell.live(), "카메라 입력 아님")
        has_source = lambda: (self.shell.live() and self.state.current.get() is not None, "실시간에 현행 값이 있어야 한다")
        bind.press(put[node.Capture.one], lambda: self.eye.submit(self.eye.Job.CAPTURE, state=self.state),
                   "한 장 찍어 회차에 넣는다", gate=not_live)
        bind.press(put[node.Capture.burst], self._burst_begin, "연속 촬영", gate=not_live)
        bind.press(put[node.Exposure.Tune.sweep], lambda: None, "목표 밝기로 스윕한다", gate=not_live)
        bind.press(put[node.Props.Act.read], self._read,
                   "장치에서 지금 값과 조정 범위를 읽어 온다. 슬라이더가 열린다", gate=not_live)
        bind.press(put[node.EraDoc.load], self._revert,
                   "현행 값의 출처 회차 설정으로 장치를 되돌린다", gate=has_source)
        for name, widget in put.repeated[node.Exposure.Way].items():
            bind.choose(widget, self.exposure, name, self._exposure_chosen)
        template = node.Props.Values.template
        for name, bag in put.repeated[node.Props.Values].items():
            bag[template.slider].bind("<ButtonRelease-1>", partial(self._slid, name))

    # ------------------------------------------------------------ 촬영

    def _burst_begin(self) -> None:
        """버스트 한 회. 한 장 캡처를 간격을 두고 되풀이한다."""
        self._burst = (time.monotonic(), 0.0, 0)
        self._burst_step()

    def _burst_step(self) -> None:
        """`should_capture` 의 장 수는 이번에 찍을 장의 번호다(1 부터)."""
        spec = self.camera.roles.BLOCK.burst_capture
        started, last, taken = self._burst
        now = time.monotonic()
        if now - started >= spec.duration__s or taken >= spec.max_frames: return
        if spec.should_capture(now - started, now - last, taken + 1):
            self.eye.submit(self.eye.Job.CAPTURE, state=self.state)
            self._burst = (started, now, taken + 1)
        self.shell.root.after(int(spec.interval__s * 1000), self._burst_step)

    # ------------------------------------------------------------ 설정

    def _read(self) -> None:
        self.eye.submit(self.eye.Job.READ_SETTINGS)
        self.eye.submit(self.eye.Job.READ_RANGES)

    def _exposure_chosen(self) -> None:
        """자동 노출을 켜고 끈다. 켜짐 1 · 꺼짐 0 이다."""
        auto = self.exposure.get() == self.Exposure.AUTO
        self.eye.submit(self.eye.Job.APPLY_SETTINGS, state=self.state, settings={"auto_exposure": float(auto)})

    def _slid(self, name: str, _event) -> None:
        """슬라이더를 놓으면 그 값을 장치의 단계에 맞춰 쓴다."""
        span = (self.eye.ranges.get() or {}).get(name)
        if span is None: return
        slider = self.shell.build.repeated[self.node.Props.Values][name][self.node.Props.Values.template.slider]
        value = span.low + round((float(slider.get()) - span.low) / span.step) * span.step
        self.eye.submit(self.eye.Job.APPLY_SETTINGS, state=self.state, settings={name: float(value)})

    def _revert(self) -> None:
        source = self.state.current.get().source_era
        recorded = self.state.dataset.read_era(source.path)["camera"]["settings"]
        if recorded is None:
            self.shell.say(f"{source.name} 에 카메라 설정이 없어 되돌릴 것이 없다")
            return
        self.eye.submit(self.eye.Job.APPLY_SETTINGS, state=self.state, settings=recorded)

    def refresh(self) -> None:
        put, node = self.shell.build, self.node
        current = self.state.current.get()
        camera = None if current is None else current.era_values.camera
        device = None if camera is None else camera.device
        put[node.Device.shot_by].configure(text=device.name if device else "적어 두지 않았다")
        put[node.Device.attached].configure(text=self._attached(camera))
        recorded = {} if camera is None else camera.settings or {}
        read = self.eye.settings.get() or {}
        auto = read.get("auto_exposure")
        if auto is not None:
            self.exposure.set(self.Exposure.AUTO if auto > self.camera.settings_apply.auto_on_min else self.Exposure.MANUAL)
        ranges = self.eye.ranges.get()
        #: 슬라이더 손잡이는 새로 읽은 값이 들어올 때만 옮긴다. 매 주기 옮기면 끄는 손을 이긴다
        moved, self._synced = read is not self._synced, read
        template = node.Props.Values.template
        for name, bag in put.repeated[node.Props.Values].items():
            span = None if ranges is None else ranges.get(name)
            bag[template.name].configure(text=name)
            unsupported = ranges is not None and name in self.camera.directshow.controls and span is None
            bag[template.value].configure(text="지원 안 함" if unsupported else self._value_text(read.get(name), recorded.get(name)))
            slider = bag[template.slider]
            if span is None:
                slider.state(["disabled"])
                continue
            slider.state(["!disabled"])
            slider.configure(from_=span.low, to=span.high)
            if moved and read.get(name) is not None: slider.set(read[name])

    @staticmethod
    def _value_text(device: float | None, recorded: float | None) -> str:
        """장치의 지금 값. 현행 값과 다르면 현행 값을 곁에 적는다. 못 읽으면 "—"."""
        if device is None: return "—" if recorded is None else f"— (현행 {recorded:g})"
        return f"{device:g}" if device == recorded else f"{device:g} (현행 {'—' if recorded is None else f'{recorded:g}'})"


class ViewerPanel:
    """뷰어 탭. 바탕 하나와 그 위에 겹치는 것들. 그리는 쪽은 시각 계측 부품이 선 뒤에 붙는다."""

    node = Chrome.Body.Column.tabs.Vision.Viewer

    shell: "Shell"
    ui: "Config.Ui"

    def __init__(self, shell: "Shell", ui: "Config.Ui") -> None:
        self.shell = shell
        self.ui = ui

    def bind(self) -> None:
        """바탕에 무엇이 보일지는 창이 든다 — 어느 탭에 있든 바탕은 하나이기 때문이다."""
        put, shell, node = self.shell.build, self.shell, self.node
        put[node.Base.pick].configure(textvariable=shell.base,
                                      values=[one.name for one in shell.BASES])
        put[node.Base.pick].bind("<<ComboboxSelected>>", self._redraw)
        for group, flags in ((node.Layers, shell.layer), (node.Overlays, shell.overlay)):
            for name, widget in put.repeated[group].items():
                widget.configure(variable=flags[name], command=self._redraw)

    def _redraw(self, _event=None) -> None:
        """보일 것이 바뀌면 다시 그린다."""
        if self.shell.scene is not None:
            self.shell.draw()

    def refresh(self) -> None:
        pass


class LabelPanel:
    """라벨 탭. 커서가 필요한 동작은 버튼을 두지 않는다.

    편집 모드에서는 영상 클릭이 곧 라벨이다 — 네 점을 받을 때마다 보고 있는 장에 사각형 하나를 더하고, 다음 네 점을 기다린다.
    받는 중에 우클릭하면 그 사각형만 그만두고 새로 받는다. 멈추려면 보기 모드로 돌린다.
    규격은 네 점의 종횡비로 고른다(`Config.Product.block_by_aspect`) — 라벨이 그 라벨로 풀 H35 에 기대지 않는다.
    라벨은 회차 사진에 붙으므로 실시간에서는 편집이 열리지 않는다.
    """

    class Mode(StrEnum):
        """지금 클릭이 무엇을 하는가. tk 변수가 값을 들고 다니므로 StrEnum 이다."""

        VIEW = "보기"
        EDIT = "편집"

    class Way(StrEnum):
        """네 점을 어떻게 찍는가."""

        SNAP = "네 점 · 경계에 맞춤"
        RAW = "네 점 · 클릭 그대로"
        AUTO = "한 점 · 사각형 자동"

    #: 방식마다 사람이 알아야 하는 것. 쪽지가 여기서 온다
    WHY = {Way.SNAP: "찍은 점을 블록 테두리로 끌어당긴다",
           Way.RAW: "끌어당기지 않는다. 사람이 찍은 자리가 그대로 남는다",
           Way.AUTO: "네 번 찍는 수고를 던다"}

    #: 몸통이 선 방식. 나머지는 고르면 이것으로 되돌린다
    READY_WAYS = (Way.RAW,)
    #: 점 받기의 이름. 다른 탭의 점 받기와 가른다
    PICK = "라벨"
    #: 사각형 한 개가 받는 점 수
    CORNERS = 4

    node = Chrome.Body.Column.tabs.Vision.Label

    shell: "Shell"
    product: "Config.Product"
    writer: "Tool.Writer"          # 쓰기 주인. 라벨을 더하고 빼는 일을 맡긴다
    mode: tk.StringVar
    draw: tk.StringVar
    armed_for: tuple | None = None  # 지금 받는 네 점이 붙을 (회차 폴더, 장 이름)

    def __init__(self, shell: "Shell", product: "Config.Product", writer: "Tool.Writer") -> None:
        self.shell = shell
        self.product = product
        self.writer = writer
        self.mode = tk.StringVar(value=self.Mode.VIEW)
        self.draw = tk.StringVar(value=self.Way.RAW)

    def bind(self) -> None:
        put, bind, node = self.shell.build, self.shell.bind, self.node
        editing = lambda: (self.mode.get() == self.Mode.EDIT, "편집 모드 아님")
        bind.press(put[node.Work.suggest], lambda: None, "초안 사각형을 제안한다",
                   life=Life.frame, gate=editing)
        bind.press(put[node.Work.undo], self._undo, "이 장의 마지막 사각형을 뺀다", gate=editing)
        for name, widget in put.repeated[node.ClickIs].items():
            bind.choose(widget, self.mode, name, self._mode_changed)
        for name, widget in put.repeated[node.DrawWay].items():
            bind.choose(widget, self.draw, name, self._mode_changed)
        for way, why in self.WHY.items():
            Tip(put.repeated[node.DrawWay][way], why)

    def _frame(self) -> tuple | None:
        """보고 있는 회차 사진 (회차 폴더, 장 이름). 실시간이거나 사진이 없으면 `None`."""
        chrome = self.shell.chrome
        if self.shell.live() or not len(chrome.photos): return None
        return chrome.photos.era_dir, chrome.photos.frame_name(chrome.index)

    def _ours(self) -> bool:
        return self.shell.picking is not None and self.shell.picking.what == self.PICK

    def _arm(self) -> None:
        """다음 네 점을 받기 시작한다. 받은 점은 지금 보는 장에 붙는다."""
        self.armed_for = self._frame()
        self.shell.begin_pick(self.PICK, self.CORNERS, partial(self._picked, self.armed_for))

    def _mode_changed(self) -> None:
        """편집을 켜면 받기 시작하고, 끄면 받던 점을 버린다."""
        if self.draw.get() not in self.READY_WAYS:
            self.shell.say(f"라벨 :: '{self.draw.get()}' 는 아직 안 묶였다 — '{self.Way.RAW}' 로 찍는다")
            self.draw.set(self.Way.RAW)
        if self.mode.get() == self.Mode.VIEW:
            if self._ours(): self.shell.picking = None
            return
        if self._frame() is None:
            self.mode.set(self.Mode.VIEW)
            self.shell.say("라벨 :: 회차 사진을 볼 때만 찍는다")
            return
        if not self._ours(): self._arm()

    def _picked(self, frame: tuple, points: tuple) -> None:
        """네 점을 받아 그 장에 라벨로 더한다(`Config.Dataset.Labels.append`).

        받는 사이 장이 바뀌었으면 버린다.
        """
        if frame != self._frame():
            self.shell.say("라벨 :: 찍는 사이 장이 바뀌어 버렸다")
        else:
            era_dir, frame_name = frame

            def added(class_mm: float) -> None:
                self.shell.say(f"라벨 :: {frame_name} 에 {class_mm:g} mm 를 더했다")
                self.shell.chrome.reload()

            self.shell.when_done(self.writer.submit(Config.Dataset.Labels.append, era_dir, frame_name, points, product=self.product), added)
        if self.mode.get() == self.Mode.EDIT and self._frame() is not None: self._arm()

    def _undo(self) -> None:
        frame = self._frame()
        if frame is None:
            self.shell.say("라벨 :: 회차 사진을 볼 때만 뺀다")
            return
        era_dir, frame_name = frame

        def dropped(was_there: bool) -> None:
            if was_there:
                self.shell.say(f"라벨 :: {frame_name} 의 마지막 사각형을 뺐다")
                self.shell.chrome.reload()
            else:
                self.shell.say(f"라벨 :: {frame_name} 에 뺄 사각형이 없다")

        self.shell.when_done(self.writer.submit(Config.Dataset.Labels.drop_last, era_dir, frame_name), dropped)

    def refresh(self) -> None:
        """이 장의 라벨 수와 규격별 수. 편집 중이면 받는 점이 지금 장에 붙게 다시 건다 — 장을 옮겼거나 다른 탭이 점 받기를 가져갔다 돌아온 때다."""
        put, node, quads = self.shell.build, self.node, self.shell.quads
        put[node.ThisFrame.count].configure(text=str(len(quads)))
        lengths = sorted({length_mm for _, length_mm in quads})
        put[node.ThisFrame.by_spec].configure(
            text=" · ".join(f"{length_mm:g} × {sum(1 for _, one in quads if one == length_mm)}" for length_mm in lengths) or "—")
        if self.mode.get() != self.Mode.EDIT or self._frame() is None: return
        if self.shell.picking is None or (self._ours() and self.armed_for != self._frame()):
            self._arm()


class SetupPanel:
    """준비 탭. 앞 단계가 안 됐으면 다음이 열리지 않는다."""

    node = Chrome.Body.Column.tabs.Vision.Setup

    shell: "Shell"
    state: "vis_alg_core.EraState"
    robot_bus: "rbt_alg_core.RobotBus"
    eye: "vis_alg_core.CameraBus"
    sight: "vis_alg_core.CalcBus"  # 판정 루프. 사영 모델 풀기를 맡긴다
    vision_algorithm: "Config.VisionAlgorithm"
    robot: Tool.Slot  # 현행 `Config.Robot`. 티칭 뒤 `RobotPanel._taught` 가 갈아 끼운다
    route: "vis_alg_core.Calc.Pre.Route"
    speed: tk.DoubleVar  # 로봇 탭 조그 속도. 수집도 사람이 고른 빠르기로 돈다
    collector: "vis_alg_core.Calibration.Collector | None" = None  # 수집을 시작한 뒤에 선다
    fitting: Future | None = None  # 판정 루프에 맡긴 사영 모델 풀기의 표. 맡긴 뒤에 선다

    def __init__(self, shell: "Shell", state: "vis_alg_core.EraState", robot_bus: "rbt_alg_core.RobotBus", eye: "vis_alg_core.CameraBus", sight: "vis_alg_core.CalcBus",
                 vision_algorithm: "Config.VisionAlgorithm", robot: Tool.Slot, route: "vis_alg_core.Calc.Pre.Route", speed: tk.DoubleVar) -> None:
        self.shell = shell
        self.state = state
        self.robot_bus = robot_bus
        self.eye = eye
        self.sight = sight
        self.vision_algorithm = vision_algorithm
        self.robot = robot
        self.route = route
        self.speed = speed

    def bind(self) -> None:
        put, bind, node = self.shell.build, self.shell.bind, self.node
        writable = lambda: (not self.shell.live() or self.state.current.get() is not None, "실시간에 현행 값이 없다 — 카메라를 열면 올린다")
        #: 화면이 푸는 동안 멎지 않으므로 다시 누를 수 있다 — 맡긴 풀기가 끝나기 전에는 닫는다
        can_fit = lambda: (False, "판정 루프가 사영 모델을 푸는 중이다") if self.fitting is not None and not self.fitting.done() else (not self.shell.live(), "라벨은 회차 사진에 붙는다 — 회차를 열고 푼다")
        bind.press(put[node.Steps.WorkArea.run],
                   partial(self.shell.begin_pick, "작업영역 4점", 4, self._work_area_picked),
                   "① 영상에서 네 점을 찍는다. 실시간이면 현행 값에만, 회차를 보고 있으면 그 회차에 적는다",
                   life=Life.waiting, gate=writable)
        bind.press(put[node.Steps.Homography.run], self._homography_fitted,
                   "② 보고 있는 회차의 라벨에서 사영 행렬을 푼다", life=Life.long, gate=can_fit)
        bind.press(put[node.Steps.Affine.run], self.collect,
                   "③ 투입점의 블록을 로봇이 가운데부터 놓아 보고, 카메라가 온전히 보는 곳에 자리를 펴 아핀을 푼다 — 로봇이 움직인다",
                   life=Life.long, gate=self.can_collect)
        has_labels = lambda: (bool(self.shell.coverage_quads), "라벨이 있는 회차를 보고 있어야 한다")
        bind.press(put[node.Diagnose.coverage], self._toggle_coverage,
                   "라벨이 한쪽에 몰렸는지 본다. 뷰어 탭의 오버레이 \"라벨 분포도\" 를 켜고 끈다",
                   life=Life.frame, gate=has_labels)

    def _toggle_coverage(self) -> None:
        name = self.shell.factory.ui.overlays.coverage.name
        flag = self.shell.overlay[name]
        flag.set(not flag.get())
        if self.shell.scene is not None:
            self.shell.draw()

    def _era(self) -> "Config.Dataset.Era":
        """보고 있는 회차. 회차 파일을 고치는 갱신은 이 회차에 쓴다 — 실시간은 메모리(현행 값), 회차 파일은 그 회차를 열었을 때다."""
        return next(era for era in self.state.dataset.eras() if era.name == self.shell.source.get())

    def _work_area_picked(self, points: tuple) -> None:
        """실시간이면 현행 값에만 적는다 — 다음 촬영이 이 값을 든 새 회차를 만든다. 회차를 보고 있으면 그 회차 파일에 적는다."""
        work_area = {"polygon__px": Config.Dataset.EraValues.WorkArea.picked(points)}
        if self.shell.live():
            self.shell.when_done(self.state.edit("work_area", work_area), lambda _: self.shell.say("작업영역 4점 :: 현행 값에 적었다 — 회차 파일은 그대로다. 다음 촬영이 이 값을 든 새 회차를 만든다"))
            return
        era = self._era()

        def written(_: None) -> None:
            self.shell.say(f"작업영역 4점 :: {era.name} 에 적었다")
            self.shell.chrome.reload()

        self.shell.when_done(self.state.update(era, "work_area", work_area), written)

    def can_collect(self) -> tuple[bool, str]:
        """③ 을 시작할 수 있는가. 지금 장면을 보는 카메라 · 현행 값의 H35 · 호밍을 마친 로봇 · 담아 둔 투입점과 카메라 기준 장면 자리가 있어야 한다."""
        current, status, robot = self.state.current.get(), self.robot_bus.status.get(), self.robot.get()
        if not self.shell.live(): return False, "실시간에서 모은다 — 카메라가 지금 장면을 봐야 한다"
        if robot.motion.heights.z_place.z__mm is None: return False, "내려놓는 높이를 아직 안 담았다 — 로봇 탭 높이 담기"
        entry = robot.motion.positions.conveyor_entry
        if entry.xy is None: return False, f"{entry.label} 자리를 아직 안 담았다 — 티칭 창 자리 담기"
        reference = robot.motion.positions.camera_reference
        if reference.xy is None: return False, f"{reference.label} 자리를 아직 안 담았다 — 티칭 창 자리 담기"
        if current is None or not vis_alg_core.Calc.is_ready(current.era_values): return False, "현행 값에 작업영역 · H35 가 없다"
        if not self.robot_bus.connected.get(): return False, "로봇이 연결돼야 한다"
        if status is None or self.robot_bus.link.is_alarm(status): return False, "로봇 호밍 전이다"
        if self.collector is not None and self.collector.result.get() is None: return False, "수집 중이다"
        return True, ""

    def collect(self) -> None:
        """③ 대응점 수집을 시작한다. 첫 단계 자리는 `Config.Robot.bootstrap_points`, 둘째 단계 자리는 `Config.Robot.calibration_points`(보는 쪽이 첫 단계 관측으로 정한다), 순서는 `RobotBus.Job.COLLECT`, 보는 쪽은 `vis_alg_core.Calibration.Collector` 다.

        기록(영상 · 단계 · 자리마다 본 장 · 끝의 카메라 기준 장면 · 결과)은 회차 폴더 옆 `_calib/<시각>/` 에 남는다.
        """
        robot = self.robot.get()
        block = self.state.product.block(robot.motion.calibration.supply_length__mm)
        try:
            first = robot.bootstrap_points(block)
        except Tool.Missing as missing:
            self.shell.say(f"③ :: {missing}")
            return
        folder = self.state.dataset.captures_dir / Config.Dataset.CALIBRATION_DIR / time.strftime("%y%m%d_%H%M%S")
        #: 폴더를 만드는 일이 쓰기 주인의 줄 맨 앞에 선다 — 녹화 파일 · 단계 기록 · 장은 그 뒤에 맡겨지므로 기다리지 않는다
        self.state.writer.submit(folder.mkdir, parents=True)
        self.eye.submit(self.eye.Job.RECORD, path=folder / "video.mp4")
        self.collector = vis_alg_core.Calibration.Collector(self.eye, self.state, self.vision_algorithm, self.state.current.get().era_values, self.route,
                                                            robot, folder, layout=partial(robot.calibration_points, block))
        self.shell.listeners.append(self.collector.hear)
        self.robot_bus.submit(self.robot_bus.Job.COLLECT, points=first, robot=robot, speed=int(self.speed.get()),
                          look=self.collector.look, note=self.collector.note, finish=self.collector.finish, more=self.collector.more,
                          regrab=self.collector.regrab, snap=self.collector.snap, reference_scene=self.collector.reference_scene)
        self.shell.say(f"③ 대응점 수집 시작 :: 가운데 {len(first)} 자리부터 — 기록 {Config.Dataset.CALIBRATION_DIR}/{folder.name}")

    def _collected(self, result: "vis_alg_core.Calibration.Collector.Result") -> None:
        """수집이 끝났다. 수집 기록(`Calibration.Collector.finish`)이 현행 값에 담은 것을 알린다."""
        self.shell.listeners.remove(self.collector.hear)
        self.eye.submit(self.eye.Job.RECORD_STOP)
        worst = lambda distances: f"{max(distances):.2f} mm" if distances else "—"
        offset = "—" if result.offset_mm is None else f"{result.offset_mm:.2f} mm"
        self.shell.say(f"③ 끝 :: {result.reason} · 대응점 {len(result.pairs)} · 적합 최대 {worst(result.fit_mm)} · 확인점 최대 {worst(result.holdout_mm)}"
                       f" · 재방문 {', '.join(f'{one:.2f}' for one in result.revisit_px) or '—'} px · 패드 어긋남 {offset}")
        self.shell.say("③ :: 현행 값에 담았다 — ● 한 장으로 회차에 남긴다" if result.accepted
                       else "③ :: 확인점 · 이동 성분 관측이 없거나 허용 잔차 밖이라 행렬은 안 담았다 — 대응점 원본만 담았다")

    def poll(self) -> None:
        """주기마다 — 어느 탭에 있든. 수집이 끝났으면 한 번 거둔다."""
        collector = self.collector
        if collector is not None and collector.result.get() is not None and collector.hear in self.shell.listeners:
            self._collected(collector.result.get())

    def _homography_fitted(self) -> None:
        """보고 있는 회차의 사영 모델 풀기를 판정 루프에 맡기고(`CalcBus.Job.FIT_PROJECTIVE_MODEL`), 다 적은 뒤 알린다."""
        era = self._era()

        def fitted(model: "vis_alg_core.Calibration.ProjectiveModel | None") -> None:
            if model is None:
                self.shell.say(f"사영 모델 :: {era.name} 에 라벨이 없다")
                return
            said = f"사영 모델 :: {era.name} 에 H35 를 적었다 — 라벨 {model.label_frames}장/{model.label_quads}개"
            if model.outline_photos is not None:
                said += f" · 세로 소실점은 사진 {model.outline_photos}장의 외곽으로 냈다" if model.outline_photos else " · 떨어진 블록이 든 사진이 없어 세로 소실점은 못 냈다"
            self.shell.say(said)
            self.shell.chrome.reload()

        self.fitting = self.sight.submit(self.sight.Job.FIT_PROJECTIVE_MODEL, era=era)
        self.shell.when_done(self.fitting, fitted)
        self.shell.say(f"사영 모델 :: {era.name} 풀기를 판정 루프에 맡겼다")

    def refresh(self) -> None:
        put, node = self.shell.build, self.node
        era_values = self.shell.chrome.shown_era_values()
        put[node.Steps.WorkArea.state].configure(
            text="✔" if era_values is not None and era_values.work_area.polygon__px else "—")
        put[node.Steps.Homography.state].configure(
            text="✔" if era_values is not None and era_values.homography.matrix else "—")
        collector = self.collector
        running = collector is not None and collector.result.get() is None
        put[node.Steps.Affine.state].configure(
            text=f"수집 중 {len(collector.pairs)}" if running else "✔" if era_values is not None and era_values.affine.matrix else "—")
        current = self.state.current.get()
        source = ("없음" if current is None
                  else current.source_era.name + (" · 출처와 다름 — 다음 촬영은 새 회차" if current.differs_from_source or current.settings_missed else ""))
        put[node.EraPick.source].configure(text=source)
        put[node.EraPick.viewing].configure(text=self.shell.source.get())


class ScorePanel:
    """채점 탭. 통과는 형상이고 수치는 그 판단을 돕는 표시다."""

    node = Chrome.Body.Column.tabs.Vision.Score

    shell: "Shell"

    def __init__(self, shell: "Shell") -> None:
        self.shell = shell

    def bind(self) -> None:
        put, bind, node = self.shell.build, self.shell.bind, self.node
        nothing = lambda: (False, "검출 결과 없음")
        bind.press(put[node.Compare.one], lambda: None, "검출과 라벨을 맞춰 본다",
                   life=Life.frame, gate=nothing)
        bind.press(put[node.Compare.all], lambda: None, "제외를 뺀 모든 장",
                   life=Life.long, gate=nothing)

    def refresh(self) -> None:
        put, node = self.shell.build, self.node
        put[node.Sample.era].configure(text=self.shell.source.get())


class ChromePanel:
    """상주 영역. 어느 탭에 있든 늘 보이는 것들이다 — 무엇을 보고 있나, 몇 번째 장인가."""

    class Move(Enum):
        """장을 옮기는 방향."""

        FIRST = "처음"
        PREV = "이전"
        NEXT = "다음"
        LAST = "마지막"

    node = Chrome.Body.Column.Source

    shell: "Shell"
    dataset: "Config.Dataset"
    state: "vis_alg_core.EraState"
    eye: "vis_alg_core.CameraBus"
    sight: "vis_alg_core.CalcBus"            # 실시간 검출을 내는 판정 루프
    route: "vis_alg_core.Calc.Pre.Route"     # 회차 사진을 계산할 때의 전처리 경로
    vision_algorithm: "Config.VisionAlgorithm"              # 회차 값을 화소로 옮기는 계산
    robot: Tool.Slot                        # 현행 `Config.Robot`. 로봇이 집고 놓을 수 있는 곳을 낸다. 티칭 뒤 `RobotPanel._taught` 가 갈아 끼운다
    cameras: dict                            # 카메라 입력 항목 이름 → 대장 항목
    photos: "Config.Dataset.Photos | None" = None  # 보고 있는 회차. 실시간이면 없다
    labels: "Config.Dataset.Labels | None" = None  # 그 회차의 정답 라벨
    viewed_era_values: "Config.Dataset.EraValues | None" = None  # 보고 있는 회차의 값. 실시간이면 없다
    index: int = 0                           # 그 회차에서 몇 번째 장인가

    def __init__(self, shell: "Shell", dataset: "Config.Dataset", state: "vis_alg_core.EraState", eye: "vis_alg_core.CameraBus",
                 sight: "vis_alg_core.CalcBus", route: "vis_alg_core.Calc.Pre.Route", vision_algorithm: "Config.VisionAlgorithm", robot: Tool.Slot) -> None:
        self.eye = eye
        self.sight = sight
        self.route = route
        self.vision_algorithm = vision_algorithm
        self.robot = robot
        self.shell = shell
        self.dataset = dataset
        self.state = state
        self.cameras = {entry.name: entry for entry in eye.connected()}
        if self.cameras:
            shell.live_names = tuple(self.cameras)
        shell.source.set(shell.live_names[0])   # 실사용 입력이 실시간이다

    def shown_era_values(self) -> "Config.Dataset.EraValues | None":
        """화면이 그릴 회차 값. 실시간이면 현행 값이고, 회차를 보고 있으면 그 회차의 사본이다. 현행 값이 없으면 `None`."""
        if not self.shell.live(): return self.viewed_era_values
        current = self.state.current.get()
        return None if current is None else current.era_values

    def reach_px(self, era_values: "Config.Dataset.EraValues | None") -> tuple:
        """로봇이 집고 놓을 수 있는 곳의 화소 외곽선들(`Config.Robot.reachable_outlines_px`). 그릴 회차 값이 없으면 비어 있다."""
        return () if era_values is None else self.robot.get().reachable_outlines_px(era_values)

    def bind(self) -> None:
        put, bind, node = self.shell.build, self.shell.bind, self.node
        put[node.pick].configure(textvariable=self.shell.source, width=22, postcommand=self._fill_sources)
        self._fill_sources()
        put[node.pick].bind("<<ComboboxSelected>>", self._source_changed)
        put[node.freeze].configure(variable=self.shell.frozen)
        no_frames = lambda: (not self.shell.live(), "실시간 입력에는 장 없음")
        for leaf, move, tip, key in ((node.Move.first, self.Move.FIRST, "첫 장", None),
                                     (node.Move.prev, self.Move.PREV, "이전 장", ","),
                                     (node.Move.next, self.Move.NEXT, "다음 장", "."),
                                     (node.Move.last, self.Move.LAST, "마지막 장", None)):
            bind.press(put[leaf], partial(self._go, move), tip, key=key, gate=no_frames)
        self._source_changed()

    # ------------------------------------------------------------ 보는 것

    def _fill_sources(self) -> None:
        """입력 목록. 펼칠 때마다 회차를 다시 훑는다 — 촬영이 가동 중에 새 회차를 만든다."""
        self.shell.build[self.node.pick].configure(values=list(self.shell.live_names) + [one.name for one in self.dataset.eras()])

    def _read_labels(self, era_dir: "Path") -> None:
        """그 회차의 정답 라벨과 분포도가 쓰는 전체 목록."""
        self.labels = Config.Dataset.Labels.load(era_dir)
        self.shell.coverage_quads = tuple(quad for quads in self.labels.quads_by_frame.values() for quad in quads)

    def _source_changed(self, _event=None) -> None:
        """보는 것이 바뀌면 그 회차를 열고 첫 장을 띄운다."""
        if self.shell.live():
            self.photos = None
            self.labels = None
            self.shell.coverage_quads = ()
            self.viewed_era_values = None
            self.shell.clear()
            self.eye.submit(self.eye.Job.OPEN, entry=self.cameras.get(self.shell.source.get()))
            self.eye.submit(self.eye.Job.STARTUP, state=self.state)
            return
        self.eye.submit(self.eye.Job.CLOSE)
        era_dir = self.dataset.captures_dir / self.shell.source.get()
        self.photos = Config.Dataset.Photos(era_dir)
        self._read_labels(era_dir)
        self.viewed_era_values = self.state.era_values_of(self.dataset.read_era(era_dir))
        self.index = 0
        self.shell.say(f"{self.photos.name} :: {len(self.photos)}장")
        self.show()

    def reload(self) -> None:
        """회차 값이나 라벨이 바뀐 뒤 다시 그린다. 회차를 보고 있으면 그 회차 문서와 라벨을 다시 읽는다. 실시간은 현행 값이 이미 바뀌었다."""
        if self.shell.live(): return
        era_dir = self.dataset.captures_dir / self.shell.source.get()
        self.viewed_era_values = self.state.era_values_of(self.dataset.read_era(era_dir))
        self._read_labels(era_dir)
        self.show()

    def _go(self, move: "ChromePanel.Move") -> None:
        """장을 옮긴다. 끝에서는 더 안 간다."""
        last = len(self.photos) - 1
        self.index = {self.Move.FIRST: 0,
                      self.Move.PREV: max(0, self.index - 1),
                      self.Move.NEXT: min(last, self.index + 1),
                      self.Move.LAST: last}[move]
        self.show()

    def refresh(self) -> None:
        """바탕 아래 두 줄. 상주 영역이라 어느 탭에 있든 매 주기 채운다."""
        shell, era_values = self.shell, self.shown_era_values()
        #: 실시간이면 매 주기 최신 한 장을 바탕에 건다. 탭과 무관하게 여기가 돈다
        if shell.live():
            frame = self.eye.frame.get()
            if frame is not None:
                seen = self.sight.seen.get()
                shell.show(Entity.Scene(source_name=shell.source.get(), index=0,
                                        frame_name=self.eye.role, image=frame,
                                        pieces=seen.pieces if seen is not None else (),
                                        rejected=seen.unsplit if seen is not None else ()),
                           work_area_px=tuple(era_values.work_area.polygon__px or ()) if era_values is not None else (),
                           reach_px=self.reach_px(era_values))
        where = f"{self.index + 1}/{len(self.photos)}" if self.photos else "—"
        base = shell.base.get() + (" 없음 — 원본으로 그린다" if shell.missing_base else "")
        viewing = (f"입력 {shell.source.get()} · {where} · "
                   f"{'고정' if shell.frozen.get() else '따라감'} · 바탕 {base}")
        if shell.picking is not None:
            viewing += (f" · {shell.picking.what} {len(shell.picking.points)}"
                        f"/{shell.picking.need}점 (우클릭으로 그만둠)")
        quads = sum(len(one) for one in self.labels.quads_by_frame.values()) if self.labels else 0
        frames = len(self.labels.quads_by_frame) if self.labels else 0
        if era_values is None:
            shell.status(viewing, f"현행 값 없음 · 라벨 {frames}장/{quads}개")
            return
        area = "✔" if era_values.work_area.polygon__px else "—"
        h35 = "✔" if era_values.homography.matrix else "—"
        shell.status(viewing, f"작업영역 {area} · H35 {h35} · 아핀 "
                              f"{'✔' if era_values.affine.matrix else '—'} · "
                              f"집는 곳 {'✔' if shell.reach_px else '—'} · "
                              f"라벨 {frames}장/{quads}개")

    def show(self) -> None:
        """지금 자리의 장을 바탕에 올린다. 볼 것이 없으면 비운다.

        작업영역은 보고 있는 회차의 것을 그린다 — 회차는 그 사진을 찍은 순간의 값을 든다.
        검출도 그 회차의 값으로 그 장 하나만 계산한다(`Calc.photo`).
        """
        if not len(self.photos):
            self.shell.clear()
            return
        scene = self.photos.scene(self.index)
        if vis_alg_core.Calc.is_ready(self.viewed_era_values):
            photo = vis_alg_core.Calc.photo(self.vision_algorithm, self.viewed_era_values, self.route, scene.image)
            scene = dataclasses.replace(scene, pieces=photo.pieces, rejected=photo.unsplit)
        self.shell.show(scene, quads=self.labels.of(scene.frame_name),
                        work_area_px=tuple(self.viewed_era_values.work_area.polygon__px or ()),
                        reach_px=self.reach_px(self.viewed_era_values))


# =========================================================================
# 6. 기동
# =========================================================================

class Settings(NamedTuple):
    """일곱 계통 한 벌. 주입 사슬은 Product -> VisionAlgorithm -> Robot."""

    product: "Config.Product"
    camera: "Config.Camera"
    vision_algorithm: "Config.VisionAlgorithm"
    robot: "Config.Robot"
    communication: "Config.Communication"
    ui: "Config.Ui"
    dataset: "Config.Dataset"

    @classmethod
    def load(cls) -> "Settings":
        product = Config.Product.load()
        vision_algorithm = Config.VisionAlgorithm.load(product)
        settings = cls(product=product, camera=Config.Camera.load(), vision_algorithm=vision_algorithm,
                       robot=Config.Robot.load(vision_algorithm),
                       communication=Config.Communication.load(),
                       ui=Config.Ui.load(), dataset=Config.Dataset.load())
        for config in settings: config.warm()
        return settings


def ledger_of(settings: Settings) -> dict:
    """자식의 수를 바깥이 정하는 마디에 댈 목록. 선언은 이름만 알고 값은 여기서 온다."""
    return {
        "ui.layers": [one.name for one in settings.ui.layers.values()],
        "ui.overlays": [one.name for one in settings.ui.overlays.values()],
        "camera.property_ids": list(settings.camera.property_ids),
        "gcode.command_axes": list(settings.communication.robot_serial.gcode.command_axes),
        "robot.motion.pneumatics_pwm.State": [one.value for one in settings.robot.motion.pneumatics_pwm.State],
        "label.click_modes": list(LabelPanel.Mode),
        "label.draw_modes": list(LabelPanel.Way),
        "camera.exposure_modes": list(CameraPanel.Exposure),
        "robot.jog_kinds": [face.name for face in RobotPanel.JOG.values()],
        #: 배타 자리의 자식이 곧 목록이다. 손으로 또 적으면 한쪽만 갱신되어 어긋난다
        "robot.jog_ways": Chrome.Body.Column.tabs.Equipment.Robot.Jog.Ways.labels(),
    }


def panels_of(shell: Shell, settings: Settings, robot_bus: "rbt_alg_core.RobotBus",
              ear: "rbt_alg_core.VacuumEar", plc: "cnv_alg_core.PlcBus",
              state: "vis_alg_core.EraState", eye: "vis_alg_core.CameraBus",
              sight: "vis_alg_core.CalcBus", route: "vis_alg_core.Calc.Pre.Route", robot: Tool.Slot, writer: "Tool.Writer") -> dict:
    """탭 선언마다 그 탭의 기능 하나."""
    robot_panel = RobotPanel(shell, robot_bus, ear, robot, sight, writer)
    return {
        Chrome.Body.Column.tabs.Vision.Viewer: ViewerPanel(shell, settings.ui),
        Chrome.Body.Column.tabs.Vision.Label: LabelPanel(shell, settings.product, writer),
        Chrome.Body.Column.tabs.Vision.Setup: SetupPanel(shell, state, robot_bus, eye, sight, settings.vision_algorithm, robot, route, robot_panel.speed),
        Chrome.Body.Column.tabs.Vision.Camera: CameraPanel(shell, state, eye, settings.camera),
        Chrome.Body.Column.tabs.Vision.Score: ScorePanel(shell),
        Chrome.Body.Column.tabs.Equipment.Robot: robot_panel,
        Chrome.Body.Column.tabs.Equipment.Plc: PlcPanel(shell, plc),
        Chrome.Body.Column.tabs.Equipment.Qr: QrPanel(shell, plc),
    }


def main() -> None:
    settings = Settings.load()
    theme = settings.ui.theme.themes[settings.ui.theme.default]

    #: 쓰기 주인. 화면 · 카메라 · 로봇 · 판정 루프가 쓸 것을 모두 이 줄에 맡긴다
    writer = Tool.Writer()
    robot_bus = rbt_alg_core.RobotBus(
        settings.communication,
        robot=settings.robot,
        route=Config.Robot.Route(settings.robot, communication=settings.communication))
    ear = rbt_alg_core.VacuumEar(settings.robot, status=robot_bus.status)
    plc = cnv_alg_core.PlcBus(settings.communication)
    eye = vis_alg_core.CameraBus(settings.camera, "BLOCK", writer)
    state = vis_alg_core.EraState(settings.dataset, settings.product, writer)
    route = vis_alg_core.Calc.Pre.Route.of(settings.vision_algorithm.calc.route)
    robot = Tool.Slot(settings.robot)
    sight = vis_alg_core.CalcBus(eye, state, settings.vision_algorithm, route, idle=lambda: not robot_bus.busy.get(), robot=settings.robot)
    robot_bus.start()
    plc.start()
    eye.start()
    sight.start()
    try:
        ear.start()
    except (Tool.Missing, ImportError) as error:
        #: 마이크가 없어도 나머지는 돌아야 한다. 공압 지령은 그대로 나가고 흡착 판정만 빈다 — 무는 동작은 닿은 뒤 진공 체결 대기만큼 쉰다
        ear.events.put(Tool.Event(f"수음 :: {error}", time.monotonic()))
    else:
        robot_bus.hearing = ear.heard

    root = tk.Tk()
    root.title("운전 화면")
    factory = Factory(settings.ui)
    factory.paint(theme)
    Painter.require(settings.ui)
    Tip.colors = theme.colors

    shell = Shell(root, factory, ledger_of(settings))
    shell.panels = panels_of(shell, settings, robot_bus, ear, plc, state, eye, sight, route, robot, writer)
    chrome = ChromePanel(shell, settings.dataset, state, eye, sight, route, settings.vision_algorithm, robot)
    shell.chrome = chrome
    chrome.bind()
    watched = {"로봇": robot_bus.connected, "PLC": plc.connected}
    was = {name: bool(slot.get()) for name, slot in watched.items()}
    for panel in shell.panels.values():
        panel.bind()
    shell.panels[shell.tab()].refresh()

    tick_ms = settings.ui.viewer.tick_ms()

    def beat() -> None:
        for bus in (robot_bus, ear, plc, eye, state, sight, writer):
            while True:
                try:
                    shell.say(bus.events.get_nowait().text)
                except queue.Empty:
                    break
        shell.sweep_done()
        #: 붙어 있던 것이 끊기면 띠로 알린다. 정상은 각 탭이 이미 말한다
        for name, slot in watched.items():
            now = bool(slot.get())
            if was[name] and not now:
                shell.alert(f"{name} 연결이 끊겼다. {name} 탭에서 다시 연결한다")
            elif now and not was[name]:
                shell.alert("")
            was[name] = now
        chrome.refresh()
        shell.panels[shell.tab()].refresh()
        shell.panels[Chrome.Body.Column.tabs.Vision.Setup].poll()
        shell.bind.sweep()
        root.after(tick_ms, beat)

    beat()
    #: 쓰기 주인은 맨 뒤에 세운다 — 앞의 워커가 서면서 맡긴 쓰기(녹화 닫기 같은 것)까지 다 쓴다
    root.protocol("WM_DELETE_WINDOW", lambda: (robot_bus.shutdown(), ear.shutdown(), plc.shutdown(), sight.shutdown(), eye.shutdown(), writer.shutdown(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
