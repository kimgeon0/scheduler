#!/usr/bin/env python3
import json
import math
import os
import random
import subprocess
import sys
import time as pytime
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
    QLabel,
)


APP_NAME = "Scheduler"

def open_with_default_app(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)], cwd=str(path.parent))
    else:
        subprocess.Popen(["xdg-open", str(path)], cwd=str(path.parent))


def run_shell_script(path: Path) -> None:
    if sys.platform.startswith("win"):
        # Windows에서는 .bat/.cmd/.ps1 위주로 처리
        suffix = path.suffix.lower()
        if suffix in {".bat", ".cmd"}:
            subprocess.Popen([str(path)], cwd=str(path.parent), shell=True)
        elif suffix == ".ps1":
            subprocess.Popen(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(path)],
                cwd=str(path.parent),
            )
        else:
            open_with_default_app(path)
    else:
        subprocess.Popen(["bash", str(path)], cwd=str(path.parent))


def run_executable_file(path: Path) -> None:
    if sys.platform.startswith("win"):
        subprocess.Popen([str(path)], cwd=str(path.parent), shell=True)
    else:
        subprocess.Popen([str(path)], cwd=str(path.parent))


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_base_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def user_data_dir(app_name: str = APP_NAME) -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    target = base / app_name
    target.mkdir(parents=True, exist_ok=True)
    return target


BASE_DIR = app_base_dir()
DATA_DIR = user_data_dir(APP_NAME)
SCHEDULE_FILE = DATA_DIR / "schedules.json"
SETTINGS_FILE = DATA_DIR / "settings.json"


def two(n: int) -> str:
    return f"{n:02d}"


def hour12_display(h: int) -> int:
    hour12 = h % 12
    return 12 if hour12 == 0 else hour12


def format_ampm(h: int, m: int, s: Optional[int] = None) -> str:
    ampm = "오전" if h < 12 else "오후"
    hour12 = hour12_display(h)
    parts = [f"{ampm} {hour12}시", f"{m}분"]
    if s is not None:
        parts.append(f"{s}초")
    return " ".join(parts)


def format_no_ampm(h: int, m: int) -> str:
    hour12 = hour12_display(h)
    if m == 0:
        return f"{hour12}시"
    return f"{hour12}시 {m}분"


def blend_colors(color_a: QColor, color_b: QColor, ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, ratio))
    inv = 1.0 - ratio
    return QColor(
        int(color_a.red() * inv + color_b.red() * ratio),
        int(color_a.green() * inv + color_b.green() * ratio),
        int(color_a.blue() * inv + color_b.blue() * ratio),
        int(color_a.alpha() * inv + color_b.alpha() * ratio),
    )


def minutes_to_hhmm(total_minutes: int) -> str:
    total_minutes %= 24 * 60
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{two(h)}:{two(m)}"


def parse_hhmm(text: str) -> int:
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


def span_duration_minutes(start_minutes: int, end_minutes: int) -> int:
    duration = end_minutes - start_minutes
    if duration < 0:
        duration += 24 * 60
    return duration


def minutes_of_day_from_datetime(dt_value: datetime) -> int:
    return dt_value.hour * 60 + dt_value.minute


def schedule_span_datetimes(base_date, start_minutes: int, end_minutes: int) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(base_date, time(start_minutes // 60, start_minutes % 60))
    duration = span_duration_minutes(start_minutes, end_minutes)
    end_dt = start_dt + timedelta(minutes=duration)
    return start_dt, end_dt


def to_minutes(ampm: str, hour12: int, minute: int) -> int:
    hour = hour12 % 12
    if ampm == "오후":
        hour += 12
    return hour * 60 + minute


def pick_contrasting_text_color(color: QColor) -> QColor:
    luminance = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
    return Qt.black if luminance >= 150 else Qt.white


def random_schedule_color() -> str:
    hue = random.randint(0, 359)
    return QColor.fromHsv(hue, random.randint(110, 180), random.randint(185, 240)).name()


@dataclass
class ScheduleInstance:
    source_index: int
    source: dict
    start_dt: datetime
    end_dt: datetime


@dataclass
class RenderedSchedule:
    source_index: int
    source: dict
    instance_start_dt: datetime
    instance_end_dt: datetime
    rect: QRectF


class ScheduleStorage:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.schedules: list[dict] = []
        self.load()

    def load(self) -> None:
        if self.file_path.exists():
            try:
                data = json.loads(self.file_path.read_text(encoding="utf-8"))
                self.schedules = data if isinstance(data, list) else []
            except Exception:
                self.schedules = []
        else:
            self.schedules = []

        for item in self.schedules:
            if isinstance(item, dict):
                item.setdefault("메모", "")
                item.setdefault("음악 파일", None)
                item.setdefault("음악 볼륨", 100)

    def save(self) -> None:
        self.file_path.write_text(
            json.dumps(self.schedules, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def sort_and_save(self) -> None:
        self.schedules.sort(key=lambda x: parse_hhmm(x["시작 시각"]))
        self.save()

    def add(self, schedule: dict) -> None:
        self.schedules.append(schedule)
        self.sort_and_save()

    def update_at(self, index: int, schedule: dict) -> None:
        self.schedules[index] = schedule
        self.sort_and_save()

    def delete_at(self, index: int) -> None:
        del self.schedules[index]
        self.sort_and_save()

    def replace_all(self, schedules: list[dict]) -> None:
        self.schedules = schedules
        for item in self.schedules:
            if isinstance(item, dict):
                item.setdefault("메모", "")
                item.setdefault("음악 파일", None)
                item.setdefault("음악 볼륨", 100)
        self.sort_and_save()



def default_settings() -> dict:
    default_font = QFont()
    font_size = default_font.pointSize() if default_font.pointSize() > 0 else 10
    return {
        "낮시간 색상": "#fffcd9",
        "저녁시간 색상": "#b8b5e6",
        "폰트 패밀리": default_font.family(),
        "폰트 크기": font_size,
        "테마 이름": "크림/보라",
    }


def load_settings(file_path: Path) -> dict:
    default = default_settings()
    if file_path.exists():
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in {"낮시간 색상", "저녁시간 색상", "폰트 패밀리", "테마 이름"} and isinstance(value, str):
                        default[key] = value
                    elif key == "폰트 크기":
                        try:
                            default[key] = int(value)
                        except Exception:
                            pass
        except Exception:
            pass
    return default


def save_settings(file_path: Path, settings: dict) -> None:
    file_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


THEME_PRESETS = [
    ("밝은 회색", "#ffffff", "#9a9996"),
    ("크림/보라", "#fffcd9", "#b8b5e6"),
    ("민트/네이비", "#eef7f2", "#9db4c0"),
    ("커스텀", None, None),
]

FONT_SIZE_PRESETS = [
    ("아주작게", 7),
    ("작게", 9),
    ("보통", 11),
    ("크게", 13),
    ("아주크게", 15),
]

class ThemeSwatchButton(QPushButton):
    def __init__(self, title: str, day_color: Optional[str], night_color: Optional[str], parent=None):
        super().__init__(parent)
        self.title = title
        self.day_color = QColor(day_color) if day_color else QColor("#ffffff")
        self.night_color = QColor(night_color) if night_color else QColor("#d0d0d0")
        self.setCheckable(True)
        self.setMinimumSize(120, 84)
        self.setCursor(Qt.PointingHandCursor)

    def set_colors(self, day_color: str, night_color: str) -> None:
        self.day_color = QColor(day_color)
        self.night_color = QColor(night_color)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        square = QRectF(10, 10, 34, 34)
        tri1 = QPainterPath()
        tri1.moveTo(square.left(), square.top())
        tri1.lineTo(square.right(), square.top())
        tri1.lineTo(square.left(), square.bottom())
        tri1.closeSubpath()

        tri2 = QPainterPath()
        tri2.moveTo(square.right(), square.top())
        tri2.lineTo(square.right(), square.bottom())
        tri2.lineTo(square.left(), square.bottom())
        tri2.closeSubpath()

        painter.fillPath(tri1, self.day_color)
        painter.fillPath(tri2, self.night_color)
        painter.setPen(QPen(QColor("#1f6feb") if self.isChecked() else QColor("#6b6b6b"), 2.0 if self.isChecked() else 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(square)

        text_rect = QRectF(52, 8, self.width() - 60, self.height() - 16)
        painter.setPen(self.palette().buttonText().color())
        font = painter.font()
        font.setPointSize(max(8, font.pointSize() - 1))
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, self.title)


class SettingsDialog(QDialog):
    RESET_RESULT = 2

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.setModal(True)
        self.resize(620, 420)

        self.day_color = QColor(settings.get("낮시간 색상", "#fffcd9"))
        self.night_color = QColor(settings.get("저녁시간 색상", "#b8b5e6"))
        self.theme_name = settings.get("테마 이름", "크림/보라")

        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(settings.get("폰트 패밀리", QFont().family())))

        self.font_size_buttons: list[QPushButton] = []
        self.selected_font_size = int(settings.get("폰트 크기", 10))
        self.font_size_container = QWidget()
        font_size_layout = QHBoxLayout(self.font_size_container)
        font_size_layout.setContentsMargins(0, 0, 0, 0)
        font_size_layout.setSpacing(6)
        for label, size in FONT_SIZE_PRESETS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, value=size: self.select_font_size(value))
            self.font_size_buttons.append(btn)
            font_size_layout.addWidget(btn)
        self.select_font_size(self.selected_font_size, initial=True)

        self.theme_buttons: list[ThemeSwatchButton] = []
        theme_grid = QGridLayout()
        theme_grid.setSpacing(8)
        for idx, (title, day, night) in enumerate(THEME_PRESETS):
            btn = ThemeSwatchButton(title, day, night)
            btn.clicked.connect(lambda checked=False, index=idx: self.select_theme(index))
            self.theme_buttons.append(btn)
            theme_grid.addWidget(btn, idx // 2, idx % 2)

        self.day_button = QPushButton()
        self.night_button = QPushButton()
        self.day_button.clicked.connect(lambda: self.choose_color("day"))
        self.night_button.clicked.connect(lambda: self.choose_color("night"))

        form = QFormLayout()
        form.addRow("폰트 스타일", self.font_combo)
        form.addRow("폰트 크기", self.font_size_container)

        theme_container = QWidget()
        theme_container.setLayout(theme_grid)
        form.addRow("테마 선택", theme_container)
        form.addRow("낮시간 색상", self.day_button)
        form.addRow("저녁시간 색상", self.night_button)

        self.reset_button = QPushButton("초기화")
        self.cancel_button = QPushButton("취소")
        self.save_button = QPushButton("저장")
        self.reset_button.clicked.connect(self.request_reset)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

        btns = QHBoxLayout()
        btns.addWidget(self.reset_button)
        btns.addStretch(1)
        btns.addWidget(self.cancel_button)
        btns.addWidget(self.save_button)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addStretch(1)
        root.addLayout(btns)

        self._sync_theme_selection_from_settings()
        self._refresh_color_buttons()

    def _sync_theme_selection_from_settings(self) -> None:
        matched_index = None
        for idx, (title, day, night) in enumerate(THEME_PRESETS[:-1]):
            if self.theme_name == title or (day == self.day_color.name() and night == self.night_color.name()):
                matched_index = idx
                break
        if matched_index is None:
            matched_index = len(THEME_PRESETS) - 1
            self.theme_name = "커스텀"
        self.select_theme(matched_index, apply_colors=False)

    def _refresh_color_buttons(self) -> None:
        for button, color in ((self.day_button, self.day_color), (self.night_button, self.night_color)):
            button.setText(color.name())
            button.setStyleSheet(f"background-color: {color.name()}; color: black; padding: 6px 12px;")
        self.theme_buttons[-1].set_colors(self.day_color.name(), self.night_color.name())

    def select_theme(self, index: int, apply_colors: bool = True) -> None:
        for i, btn in enumerate(self.theme_buttons):
            btn.setChecked(i == index)
        title, day, night = THEME_PRESETS[index]
        is_custom = index == len(THEME_PRESETS) - 1
        self.day_button.setEnabled(is_custom)
        self.night_button.setEnabled(is_custom)
        if apply_colors and not is_custom and day and night:
            self.day_color = QColor(day)
            self.night_color = QColor(night)
            self.theme_name = title
            self._refresh_color_buttons()
        elif is_custom:
            self.theme_name = "커스텀"

    def select_font_size(self, size: int, initial: bool = False) -> None:
        self.selected_font_size = int(size)

        matched = False
        for btn, (_, preset_size) in zip(self.font_size_buttons, FONT_SIZE_PRESETS):
            is_selected = (preset_size == self.selected_font_size)
            btn.setChecked(is_selected)
            matched = matched or is_selected

        if not matched and self.font_size_buttons:
            # 저장된 값이 프리셋과 정확히 안 맞으면 가장 가까운 값을 선택
            closest_index = min(
                range(len(FONT_SIZE_PRESETS)),
                key=lambda i: abs(FONT_SIZE_PRESETS[i][1] - self.selected_font_size),
            )
            self.selected_font_size = FONT_SIZE_PRESETS[closest_index][1]
            for i, btn in enumerate(self.font_size_buttons):
                btn.setChecked(i == closest_index)

    def choose_color(self, which: str) -> None:
        current = self.day_color if which == "day" else self.night_color
        color = QColorDialog.getColor(current, self, "색상 선택")
        if color.isValid():
            if which == "day":
                self.day_color = color
            else:
                self.night_color = color
            self.theme_name = "커스텀"
            self.select_theme(len(THEME_PRESETS) - 1, apply_colors=False)
            self._refresh_color_buttons()

    def request_reset(self) -> None:
        self.done(self.RESET_RESULT)

    def result_settings(self) -> dict:
        return {
            "낮시간 색상": self.day_color.name(),
            "저녁시간 색상": self.night_color.name(),
            "폰트 패밀리": self.font_combo.currentFont().family(),
            "폰트 크기": self.selected_font_size,
            "테마 이름": self.theme_name,
        }


class TimeSelector(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.ampm = QComboBox()
        self.ampm.addItems(["오전", "오후"])

        self.hour = QSpinBox()
        self.hour.setRange(0, 11)
        self.hour.setSuffix("시")

        self.minute = QSpinBox()
        self.minute.setRange(0, 59)
        self.minute.setSuffix("분")

        layout.addWidget(self.ampm)
        layout.addWidget(self.hour)
        layout.addWidget(self.minute)

    def set_from_minutes(self, total_minutes: int) -> None:
        total_minutes = max(0, min(24 * 60 - 1, total_minutes))
        h = total_minutes // 60
        m = total_minutes % 60
        self.ampm.setCurrentText("오전" if h < 12 else "오후")
        self.hour.setValue(h % 12)
        self.minute.setValue(m)

    def get_minutes(self) -> int:
        return to_minutes(self.ampm.currentText(), self.hour.value(), self.minute.value())


class ScheduleDialog(QDialog):
    def __init__(
        self,
        parent=None,
        schedule: Optional[dict] = None,
        preset_start_minutes: Optional[int] = None,
        preset_end_minutes: Optional[int] = None,
        test_callback=None,
    ):
        super().__init__(parent)
        editing = schedule is not None
        self.test_callback = test_callback
        self.setWindowTitle("스케줄 편집" if editing else "스케줄 추가")
        self.setModal(True)
        self.resize(620, 460)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("예: 기상 음악")

        self.start_selector = TimeSelector()
        self.end_selector = TimeSelector()
        self.start_selector.set_from_minutes(8 * 60)
        self.end_selector.set_from_minutes(9 * 60)

        self.selected_color = QColor(random_schedule_color() if not editing else "#4F8EF7")
        self.color_button = QPushButton("색상 선택")
        self.color_button.clicked.connect(self.choose_color)

        self.exec_path_edit = QLineEdit()
        self.exec_path_edit.setReadOnly(True)
        self.exec_path_edit.setPlaceholderText("선택하지 않으면 null")
        self.exec_browse_button = QPushButton("파일 선택")
        self.exec_browse_button.clicked.connect(self.choose_file)
        self.exec_clear_button = QPushButton("지우기")
        self.exec_clear_button.clicked.connect(lambda: self.exec_path_edit.setText(""))

        self.memo_edit = QPlainTextEdit()
        self.memo_edit.setPlaceholderText("메모를 입력하세요")
        self.memo_edit.setMinimumHeight(90)
        self.memo_edit.setMaximumHeight(130)

        exec_row = QWidget()
        exec_layout = QHBoxLayout(exec_row)
        exec_layout.setContentsMargins(0, 0, 0, 0)
        exec_layout.setSpacing(6)
        exec_layout.addWidget(self.exec_path_edit, 1)
        exec_layout.addWidget(self.exec_browse_button)
        exec_layout.addWidget(self.exec_clear_button)

        self.music_path_edit = QLineEdit()
        self.music_path_edit.setReadOnly(True)
        self.music_path_edit.setPlaceholderText("선택하지 않으면 재생 안 함")
        self.music_browse_button = QPushButton("음원 선택")
        self.music_browse_button.clicked.connect(self.choose_music_file)
        self.music_clear_button = QPushButton("지우기")
        self.music_clear_button.clicked.connect(lambda: self.music_path_edit.setText(""))

        self.music_volume_slider = QSlider(Qt.Horizontal)
        self.music_volume_slider.setRange(0, 100)
        self.music_volume_slider.setValue(100)
        self.music_volume_label = QLabel("100%")
        self.active_test_dialog = None
        self.music_volume_slider.valueChanged.connect(self._on_music_volume_changed)

        music_row = QWidget()
        music_layout = QHBoxLayout(music_row)
        music_layout.setContentsMargins(0, 0, 0, 0)
        music_layout.setSpacing(6)
        music_layout.addWidget(self.music_path_edit, 1)
        music_layout.addWidget(self.music_browse_button)
        music_layout.addWidget(self.music_clear_button)

        music_volume_row = QWidget()
        music_volume_layout = QHBoxLayout(music_volume_row)
        music_volume_layout.setContentsMargins(0, 0, 0, 0)
        music_volume_layout.setSpacing(6)
        music_volume_layout.addWidget(self.music_volume_slider, 1)
        music_volume_layout.addWidget(self.music_volume_label)

        form = QFormLayout()
        form.addRow("스케줄 제목", self.title_edit)
        form.addRow("시작 시각", self.start_selector)
        form.addRow("종료 시각", self.end_selector)
        form.addRow("표시 색상", self.color_button)
        form.addRow("실행 파일", exec_row)
        form.addRow("음악 파일", music_row)
        form.addRow("볼륨 조절", music_volume_row)
        form.addRow("메모", self.memo_edit)

        self.test_button = QPushButton("테스트")
        self.cancel_button = QPushButton("취소")
        self.submit_button = QPushButton("저장" if editing else "추가")
        self.test_button.clicked.connect(self.run_test)
        self.cancel_button.clicked.connect(self.reject)
        self.submit_button.clicked.connect(self.submit)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.test_button)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.cancel_button)
        btn_layout.addWidget(self.submit_button)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addStretch(1)
        root.addLayout(btn_layout)

        self.result_schedule: Optional[dict] = None

        if schedule:
            self.title_edit.setText(schedule.get("제목", ""))
            self.start_selector.set_from_minutes(parse_hhmm(schedule["시작 시각"]))
            self.end_selector.set_from_minutes(parse_hhmm(schedule["종료 시각"]))
            self.selected_color = QColor(schedule.get("표시 색상", "#4F8EF7"))
            self.exec_path_edit.setText(schedule.get("실행 파일") or "")
            self.music_path_edit.setText(schedule.get("음악 파일") or "")
            self.music_volume_slider.setValue(int(schedule.get("음악 볼륨", 100)))
            self.memo_edit.setPlainText(schedule.get("메모", ""))
        else:
            if preset_start_minutes is not None:
                self.start_selector.set_from_minutes(preset_start_minutes)
            if preset_end_minutes is not None:
                self.end_selector.set_from_minutes(preset_end_minutes)

        self._refresh_color_button()
        self._on_music_volume_changed(self.music_volume_slider.value())

    def _on_music_volume_changed(self, value: int) -> None:
        self.music_volume_label.setText(f"{value}%")
        if self.active_test_dialog is not None:
            self.active_test_dialog.set_volume(value)

    def _stop_active_test_dialog(self) -> None:
        if self.active_test_dialog is not None:
            try:
                self.active_test_dialog.stop_and_close()
            except Exception:
                pass
            self.active_test_dialog = None

    def closeEvent(self, event) -> None:
        self._stop_active_test_dialog()
        super().closeEvent(event)

    def _refresh_color_button(self) -> None:
        self.color_button.setStyleSheet(
            f"background-color: {self.selected_color.name()};"
            "color: black; padding: 6px 12px;"
        )
        self.color_button.setText(self.selected_color.name())

    def choose_color(self) -> None:
        color = QColorDialog.getColor(self.selected_color, self, "표시 색상 선택")
        if color.isValid():
            self.selected_color = color
            self._refresh_color_button()

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "실행 파일 선택",
            str(Path.home()),
            "모든 파일 (*)",
        )
        if path:
            self.exec_path_edit.setText(path)

    def choose_music_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "음악 파일 선택",
            str(Path.home()),
            "오디오 파일 (*.mp3 *.wav *.ogg *.flac *.m4a *.aac);;모든 파일 (*)",
        )
        if path:
            self.music_path_edit.setText(path)

    def _build_schedule_data(self, require_title: bool = True) -> Optional[dict]:
        title = self.title_edit.text().strip()
        if require_title and not title:
            QMessageBox.warning(self, "입력 오류", "스케줄 제목을 입력해 주세요.")
            return None

        start_minutes = self.start_selector.get_minutes()
        end_minutes = self.end_selector.get_minutes()
        if end_minutes == start_minutes:
            QMessageBox.warning(
                self,
                "입력 오류",
                "시작 시각과 종료 시각이 완전히 같을 수는 없습니다.",
            )
            return None

        exec_path = self.exec_path_edit.text().strip() or None
        music_path = self.music_path_edit.text().strip() or None
        return {
            "제목": title or "(테스트)",
            "시작 시각": minutes_to_hhmm(start_minutes),
            "종료 시각": minutes_to_hhmm(end_minutes),
            "표시 색상": self.selected_color.name(),
            "실행 파일": exec_path,
            "음악 파일": music_path,
            "음악 볼륨": int(self.music_volume_slider.value()),
            "메모": self.memo_edit.toPlainText().strip(),
        }

    def run_test(self) -> None:
        schedule = self._build_schedule_data(require_title=False)
        if schedule is None:
            return
        self._stop_active_test_dialog()
        if callable(self.test_callback):
            dialog = self.test_callback(schedule, self)
            if dialog is not None:
                self.active_test_dialog = dialog
                self.active_test_dialog.destroyed.connect(lambda *_: setattr(self, "active_test_dialog", None))
                self.active_test_dialog.raise_()
                self.active_test_dialog.activateWindow()

    def submit(self) -> None:
        self.result_schedule = self._build_schedule_data(require_title=True)
        if self.result_schedule is None:
            return
        self.accept()


class TimelineWidget(QWidget):
    scheduleEditRequested = Signal(int)
    scheduleDeleteRequested = Signal(int)
    scheduleDuplicateRequested = Signal(int)
    scheduleMoved = Signal(int, int, int)
    scheduleResized = Signal(int, int, int)
    scheduleAddRequested = Signal(int, int)
    scheduleTestRequested = Signal(int)
    visibleSpanChanged = Signal(int)

    LEFT_GUTTER = 190
    RIGHT_MARGIN = 24
    TOP_MARGIN = 16
    BOTTOM_MARGIN = 16
    MIN_LANE_WIDTH = 260
    LINE_OVERHANG = 4
    MIN_SIDE_MINUTES = 60
    MAX_SIDE_MINUTES = 720
    HANDLE_HEIGHT = 12
    MIN_DURATION_MINUTES = 1
    INERTIA_INTERVAL_MS = 16
    INERTIA_TIME_CONSTANT_SEC = 0.25
    INERTIA_SPEED_CONSTANT = 100000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.schedules: list[dict] = []
        self.full_day = False
        self.visible_side_minutes = 240
        self.pan_offset_minutes = 0.0
        self.current_time = datetime.now()
        self.day_color = QColor("#fffcd9")
        self.night_color = QColor("#b8b5e6")

        self.setMouseTracking(True)
        self.setMinimumSize(720, 520)

        self._press_timer = QTimer(self)
        self._press_timer.setSingleShot(True)
        self._press_timer.timeout.connect(self._activate_move_drag_if_needed)

        self._interaction_mode: Optional[str] = None
        self._press_pos = QPointF()
        self._current_mouse_pos = QPointF()
        self._pressed_render: Optional[RenderedSchedule] = None
        self._active_render: Optional[RenderedSchedule] = None

        self._drag_start_minutes = 0
        self._drag_end_minutes = 0
        self._drag_duration_minutes = 0
        self._drag_pointer_offset_minutes = 0.0
        self._drag_start_dt_abs: Optional[datetime] = None
        self._drag_end_dt_abs: Optional[datetime] = None

        self._pan_anchor_pos_y = 0.0
        self._pan_anchor_offset_minutes = 0

        self._return_button_rect = QRectF()
        self._inertia_timer = QTimer(self)
        self._inertia_timer.setInterval(self.INERTIA_INTERVAL_MS)
        self._inertia_timer.timeout.connect(self._advance_inertia)
        self._pan_velocity_minutes_per_sec = 0.0
        self._pan_deceleration_minutes_per_sec2 = 0.0
        self._last_inertia_ts = 0.0
        self._pan_samples: list[tuple[float, float]] = []

    def sizeHint(self) -> QSize:
        return QSize(980, 760)

    def lane_left(self) -> float:
        return float(self.LEFT_GUTTER)

    def lane_right(self) -> float:
        return max(self.lane_left() + self.MIN_LANE_WIDTH, float(self.width() - self.RIGHT_MARGIN))

    def lane_width(self) -> float:
        return self.lane_right() - self.lane_left()

    def set_theme_colors(self, day_color: str, night_color: str) -> None:
        self.day_color = QColor(day_color)
        self.night_color = QColor(night_color)
        self.update()

    def _stop_inertia(self) -> None:
        self._inertia_timer.stop()
        self._pan_velocity_minutes_per_sec = 0.0
        self._pan_deceleration_minutes_per_sec2 = 0.0
        self._last_inertia_ts = 0.0
        self._pan_samples.clear()

    def _record_pan_sample(self, pos_y: float) -> None:
        now_ts = pytime.monotonic()
        self._pan_samples.append((now_ts, pos_y))
        cutoff = now_ts - 0.12
        self._pan_samples = [(ts, y) for ts, y in self._pan_samples if ts >= cutoff]

    def _start_inertia_if_needed(self) -> None:
        if len(self._pan_samples) < 2:
            self._stop_inertia()
            return

        now_ts = pytime.monotonic()
        ts1, y1 = self._pan_samples[-1]
        if now_ts - ts1 > 0.3:
            self._stop_inertia()
            return

        target_dt = 0.1
        older_samples = [
            (ts, y) for ts, y in self._pan_samples[:-1]
            if 0.004 <= (ts1 - ts) <= 0.03
        ]
        if not older_samples:
            self._stop_inertia()
            return

        ts0, y0 = min(older_samples, key=lambda item: abs((ts1 - item[0]) - target_dt))
        dt = ts1 - ts0
        dy = y1 - y0
        if dt <= 0 or abs(dy) < 1.5:
            self._stop_inertia()
            return

        velocity = (-(dy) / self.pixels_per_minute()) / dt
        if abs(velocity) < 2.5:
            self._stop_inertia()
            return

        self._pan_velocity_minutes_per_sec = velocity
        speed = max(1.0, abs(velocity))
        stop_duration = self.INERTIA_TIME_CONSTANT_SEC + (math.log(speed) / 20)
        stop_duration = max(0.05, stop_duration)
        self._pan_deceleration_minutes_per_sec2 = abs(velocity) / stop_duration
        self._last_inertia_ts = now_ts
        self._inertia_timer.start()

    def _advance_inertia(self) -> None:
        if self.full_day:
            self._stop_inertia()
            return
        now_ts = pytime.monotonic()
        if self._last_inertia_ts == 0.0:
            self._last_inertia_ts = now_ts
            return
        dt = now_ts - self._last_inertia_ts
        self._last_inertia_ts = now_ts
        if dt <= 0:
            return

        v = self._pan_velocity_minutes_per_sec
        if v == 0:
            self._stop_inertia()
            return

        self.pan_offset_minutes += v * dt
        decel = self._pan_deceleration_minutes_per_sec2 * dt
        if v > 0:
            v = max(0.0, v - decel)
        else:
            v = min(0.0, v + decel)
        self._pan_velocity_minutes_per_sec = v
        self.update()
        if abs(v) < 1.0:
            self._stop_inertia()

    def _ampm_color(self, dt_value: datetime) -> QColor:
        day_color = QColor(self.day_color)
        night_color = QColor(self.night_color)
        minute_of_day = dt_value.hour * 60 + dt_value.minute + (dt_value.second / 60.0)

        # 낮 배경: 06:00 ~ 18:00
        # 밤 배경: 18:00 ~ 다음날 06:00
        # 경계 전후 60분(05:00~07:00, 17:00~19:00)은 자연스럽게 그라데이션 전환
        if 300 <= minute_of_day < 420:
            return blend_colors(night_color, day_color, (minute_of_day - 300) / 120.0)
        if 420 <= minute_of_day < 1020:
            return day_color
        if 1020 <= minute_of_day < 1140:
            return blend_colors(day_color, night_color, (minute_of_day - 1020) / 120.0)
        return night_color

    def _ampm_text(self, dt_value: datetime) -> str:
        return "오전" if dt_value.hour < 12 else "오후"

    def set_full_day(self, full_day: bool) -> None:
        self.full_day = full_day
        self._stop_inertia()
        if full_day:
            self.pan_offset_minutes = 0.0
        self._cancel_interaction()
        self.update()

    def set_schedules(self, schedules: list[dict]) -> None:
        self.schedules = schedules
        self.update()

    def set_current_time(self, current_time: datetime) -> None:
        self.current_time = current_time
        self.update()

    def center_on_now(self) -> None:
        self.pan_offset_minutes = 0.0
        self._stop_inertia()
        self._cancel_interaction()
        self.update()

    def is_detached_from_now(self) -> bool:
        return (not self.full_day) and abs(self.pan_offset_minutes) > 0.2

    def get_range(self) -> tuple[datetime, datetime]:
        if self.full_day:
            start = datetime.combine(self.current_time.date(), time(0, 0, 0))
            end = start + timedelta(days=1)
            return start, end

        anchor = self.current_time + timedelta(minutes=self.pan_offset_minutes)
        start = anchor - timedelta(minutes=self.visible_side_minutes)
        end = anchor + timedelta(minutes=self.visible_side_minutes)
        return start, end

    def drawable_height(self) -> float:
        return max(1.0, self.height() - self.TOP_MARGIN - self.BOTTOM_MARGIN)

    def total_range_minutes(self) -> float:
        start, end = self.get_range()
        return max(1.0, (end - start).total_seconds() / 60.0)

    def pixels_per_minute(self) -> float:
        return self.drawable_height() / self.total_range_minutes()

    def y_from_datetime(self, dt_value: datetime, range_start: datetime) -> float:
        delta_minutes = (dt_value - range_start).total_seconds() / 60.0
        return self.TOP_MARGIN + delta_minutes * self.pixels_per_minute()

    def datetime_from_y(self, y: float) -> datetime:
        range_start, _ = self.get_range()
        clamped = max(float(self.TOP_MARGIN), min(float(self.height() - self.BOTTOM_MARGIN), y))
        minutes = (clamped - self.TOP_MARGIN) / self.pixels_per_minute()
        return range_start + timedelta(minutes=minutes)

    def minute_of_day_from_y(self, y: float) -> int:
        dt_value = self.datetime_from_y(y)
        return dt_value.hour * 60 + dt_value.minute

    def _iter_instances(self, range_start: datetime, range_end: datetime) -> list[ScheduleInstance]:
        dates_to_check = set()
        cursor = range_start.date() - timedelta(days=1)
        last = range_end.date() + timedelta(days=1)
        while cursor <= last:
            dates_to_check.add(cursor)
            cursor += timedelta(days=1)

        instances: list[ScheduleInstance] = []
        for d in sorted(dates_to_check):
            for index, item in enumerate(self.schedules):
                start_min = parse_hhmm(item["시작 시각"])
                end_min = parse_hhmm(item["종료 시각"])
                start_dt, end_dt = schedule_span_datetimes(d, start_min, end_min)
                if end_dt <= range_start or start_dt >= range_end:
                    continue
                instances.append(ScheduleInstance(index, item, start_dt, end_dt))
        instances.sort(key=lambda x: (x.start_dt, x.source_index))
        return instances

    def _build_rendered_schedules(self) -> list[RenderedSchedule]:
        range_start, range_end = self.get_range()
        rendered: list[RenderedSchedule] = []
        for instance in self._iter_instances(range_start, range_end):
            start_y = self.y_from_datetime(max(instance.start_dt, range_start), range_start)
            end_y = self.y_from_datetime(min(instance.end_dt, range_end), range_start)
            if end_y <= start_y:
                continue
            rect = QRectF(self.lane_left(), start_y, self.lane_width(), max(1.0, end_y - start_y))
            rendered.append(
                RenderedSchedule(
                    source_index=instance.source_index,
                    source=instance.source,
                    instance_start_dt=instance.start_dt,
                    instance_end_dt=instance.end_dt,
                    rect=rect,
                )
            )
        return rendered

    def _is_render_hidden(self, render: RenderedSchedule) -> bool:
        if self._interaction_mode in {"move_drag", "resize_top", "resize_bottom"} and self._active_render:
            return (
                render.source_index == self._active_render.source_index
                and render.instance_start_dt == self._active_render.instance_start_dt
            )
        return False

    def _schedule_hit_test(self, pos: QPointF) -> tuple[Optional[RenderedSchedule], Optional[str]]:
        for render in reversed(self._build_rendered_schedules()):
            if render.rect.contains(pos):
                if pos.y() <= render.rect.top() + self.HANDLE_HEIGHT:
                    return render, "top_handle"
                if pos.y() >= render.rect.bottom() - self.HANDLE_HEIGHT:
                    return render, "bottom_handle"
                return render, "body"
        return None, None

    def _cancel_interaction(self) -> None:
        self._press_timer.stop()
        self._interaction_mode = None
        self._pressed_render = None
        self._active_render = None
        self._drag_start_dt_abs = None
        self._drag_end_dt_abs = None
        self.unsetCursor()

    def _update_hover_cursor(self, pos: QPointF) -> None:
        if self._interaction_mode == "move_drag":
            self.setCursor(Qt.ClosedHandCursor)
            return
        if self._interaction_mode in {"resize_top", "resize_bottom"}:
            self.setCursor(Qt.SizeVerCursor)
            return
        if self._return_button_rect.contains(pos):
            self.setCursor(Qt.PointingHandCursor)
            return
        render, part = self._schedule_hit_test(pos)
        if render and part in {"top_handle", "bottom_handle"}:
            self.setCursor(Qt.SizeVerCursor)
            return
        self.unsetCursor()

    def leaveEvent(self, event) -> None:
        if self._interaction_mode is None:
            self.unsetCursor()
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.full_day:
            event.accept()
            return

        self._stop_inertia()
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return

        if delta < 0:
            self.visible_side_minutes = min(self.MAX_SIDE_MINUTES, self.visible_side_minutes + 30)
        else:
            self.visible_side_minutes = max(self.MIN_SIDE_MINUTES, self.visible_side_minutes - 30)

        self.visibleSpanChanged.emit(self.visible_side_minutes)
        self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton and event.button() != Qt.RightButton:
            super().mousePressEvent(event)
            return

        pos = event.position()
        self._press_pos = pos
        self._current_mouse_pos = pos
        self._stop_inertia()

        if event.button() == Qt.LeftButton:
            if self._return_button_rect.contains(pos):
                self.center_on_now()
                event.accept()
                return

            render, part = self._schedule_hit_test(pos)
            if render and part in {"top_handle", "bottom_handle"}:
                self._active_render = render
                self._drag_start_minutes = parse_hhmm(render.source["시작 시각"])
                self._drag_end_minutes = parse_hhmm(render.source["종료 시각"])
                self._drag_start_dt_abs = render.instance_start_dt.replace(second=0, microsecond=0)
                self._drag_end_dt_abs = render.instance_end_dt.replace(second=0, microsecond=0)
                self._interaction_mode = "resize_top" if part == "top_handle" else "resize_bottom"
                event.accept()
                return

            if render and part == "body":
                self._pressed_render = render
                self._interaction_mode = "move_wait"
                self._press_timer.start(500)
                event.accept()
                return

            if not self.full_day:
                self._interaction_mode = "pan_wait"
                self._pan_anchor_pos_y = pos.y()
                self._pan_anchor_offset_minutes = self.pan_offset_minutes
                self._pan_samples = []
                self._record_pan_sample(pos.y())
                event.accept()
                return

        if event.button() == Qt.RightButton:
            render, _ = self._schedule_hit_test(pos)
            self.show_context_menu(render, event.globalPosition().toPoint(), pos)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        self._current_mouse_pos = pos

        if self._interaction_mode in {"resize_top", "resize_bottom"} and self._active_render:
            self._update_resize_from_pos(pos)
            self.setCursor(Qt.SizeVerCursor)
            self.update()
            event.accept()
            return

        if self._interaction_mode == "move_drag" and self._active_render:
            self._update_move_drag_from_pos(pos)
            self.setCursor(Qt.ClosedHandCursor)
            self.update()
            event.accept()
            return

        if self._interaction_mode == "pan_wait":
            moved = abs(pos.y() - self._press_pos.y())
            if moved > 3:
                self._interaction_mode = "pan"
            else:
                self._update_hover_cursor(pos)
                super().mouseMoveEvent(event)
                return

        if self._interaction_mode == "pan":
            delta_pixels = self._pan_anchor_pos_y - pos.y()
            delta_minutes = delta_pixels / self.pixels_per_minute()
            self.pan_offset_minutes = self._pan_anchor_offset_minutes + delta_minutes
            self._record_pan_sample(pos.y())
            self.unsetCursor()
            self.update()
            event.accept()
            return

        if self._interaction_mode == "move_wait":
            moved = (pos - self._press_pos).manhattanLength()
            if moved > 5:
                self._press_timer.stop()

        self._update_hover_cursor(pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._press_timer.stop()

            if self._interaction_mode == "move_drag" and self._active_render:
                self.scheduleMoved.emit(
                    self._active_render.source_index,
                    self._drag_start_minutes,
                    self._drag_end_minutes,
                )
                self._cancel_interaction()
                self._update_hover_cursor(event.position())
                self.update()
                event.accept()
                return

            if self._interaction_mode in {"resize_top", "resize_bottom"} and self._active_render:
                self.scheduleResized.emit(
                    self._active_render.source_index,
                    self._drag_start_minutes,
                    self._drag_end_minutes,
                )
                self._cancel_interaction()
                self._update_hover_cursor(event.position())
                self.update()
                event.accept()
                return

            if self._interaction_mode == "pan":
                self._record_pan_sample(event.position().y())
                self._start_inertia_if_needed()
                self._cancel_interaction()
                self._update_hover_cursor(event.position())
                self.update()
                event.accept()
                return

            if self._interaction_mode in {"pan_wait", "move_wait"}:
                self._cancel_interaction()
                self._update_hover_cursor(event.position())
                self.update()
                event.accept()
                return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._press_timer.stop()
            render, _ = self._schedule_hit_test(event.position())
            if render:
                self._cancel_interaction()
                self.scheduleEditRequested.emit(render.source_index)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def _activate_move_drag_if_needed(self) -> None:
        if self._interaction_mode != "move_wait" or not self._pressed_render:
            return
        self._interaction_mode = "move_drag"
        self._active_render = self._pressed_render
        self._drag_start_minutes = parse_hhmm(self._active_render.source["시작 시각"])
        self._drag_end_minutes = parse_hhmm(self._active_render.source["종료 시각"])
        self._drag_duration_minutes = span_duration_minutes(self._drag_start_minutes, self._drag_end_minutes)
        self._drag_start_dt_abs = self._active_render.instance_start_dt.replace(second=0, microsecond=0)
        self._drag_end_dt_abs = self._active_render.instance_end_dt.replace(second=0, microsecond=0)
        offset_pixels = max(0.0, self._press_pos.y() - self._active_render.rect.top())
        self._drag_pointer_offset_minutes = offset_pixels / self.pixels_per_minute()
        self._update_move_drag_from_pos(self._current_mouse_pos)
        self.setCursor(Qt.ClosedHandCursor)
        self.update()

    def _update_move_drag_from_pos(self, pos: QPointF) -> None:
        cursor_dt = self.datetime_from_y(pos.y()).replace(second=0, microsecond=0)
        proposed_start_dt = cursor_dt - timedelta(minutes=self._drag_pointer_offset_minutes)
        proposed_end_dt = proposed_start_dt + timedelta(minutes=self._drag_duration_minutes)
        self._drag_start_dt_abs = proposed_start_dt
        self._drag_end_dt_abs = proposed_end_dt
        self._drag_start_minutes = minutes_of_day_from_datetime(proposed_start_dt)
        self._drag_end_minutes = minutes_of_day_from_datetime(proposed_end_dt)

    def _update_resize_from_pos(self, pos: QPointF) -> None:
        pointer_dt = self.datetime_from_y(pos.y()).replace(second=0, microsecond=0)

        if self._interaction_mode == "resize_top" and self._drag_end_dt_abs is not None:
            latest_start = self._drag_end_dt_abs - timedelta(minutes=self.MIN_DURATION_MINUTES)
            new_start_dt = min(pointer_dt, latest_start)
            self._drag_start_dt_abs = new_start_dt
            self._drag_start_minutes = minutes_of_day_from_datetime(new_start_dt)
            self._drag_end_minutes = minutes_of_day_from_datetime(self._drag_end_dt_abs)
        elif self._interaction_mode == "resize_bottom" and self._drag_start_dt_abs is not None:
            earliest_end = self._drag_start_dt_abs + timedelta(minutes=self.MIN_DURATION_MINUTES)
            new_end_dt = max(pointer_dt, earliest_end)
            self._drag_end_dt_abs = new_end_dt
            self._drag_start_minutes = minutes_of_day_from_datetime(self._drag_start_dt_abs)
            self._drag_end_minutes = minutes_of_day_from_datetime(new_end_dt)

    def show_context_menu(self, render: Optional[RenderedSchedule], global_pos: QPoint, local_pos: QPointF) -> None:
        menu = QMenu(self)

        add_action = QAction("스케줄 추가", self)
        menu.addAction(add_action)

        edit_action = None
        duplicate_action = None
        test_action = None
        delete_action = None
        if render:
            menu.addSeparator()
            edit_action = QAction("편집", self)
            duplicate_action = QAction("복제", self)
            test_action = QAction("테스트", self)
            delete_action = QAction("삭제", self)
            menu.addAction(edit_action)
            menu.addAction(duplicate_action)
            menu.addAction(test_action)
            menu.addAction(delete_action)

        selected = menu.exec(global_pos)
        if selected == add_action:
            start_minutes = self.minute_of_day_from_y(local_pos.y())
            end_minutes = (start_minutes + 60) % (24 * 60)
            if end_minutes == start_minutes:
                end_minutes = (start_minutes + 1) % (24 * 60)
            self.scheduleAddRequested.emit(start_minutes, end_minutes)
        elif render and selected == edit_action:
            self.scheduleEditRequested.emit(render.source_index)
        elif render and selected == duplicate_action:
            self.scheduleDuplicateRequested.emit(render.source_index)
        elif render and selected == test_action:
            self.scheduleTestRequested.emit(render.source_index)
        elif render and selected == delete_action:
            self.scheduleDeleteRequested.emit(render.source_index)

    def _preview_rect_from_datetimes(self, start_dt: datetime, end_dt: datetime) -> Optional[QRectF]:
        range_start, range_end = self.get_range()
        clipped_start = max(start_dt, range_start)
        clipped_end = min(end_dt, range_end)
        if clipped_end <= clipped_start:
            return None
        top = self.y_from_datetime(clipped_start, range_start)
        bottom = self.y_from_datetime(clipped_end, range_start)
        clipped_top = max(float(self.TOP_MARGIN), top)
        clipped_bottom = min(float(self.height() - self.BOTTOM_MARGIN), bottom)
        if clipped_bottom <= clipped_top:
            return None
        return QRectF(self.lane_left(), clipped_top, self.lane_width(), clipped_bottom - clipped_top)

    def _draw_schedule_rect(
        self,
        painter: QPainter,
        rect: QRectF,
        source: dict,
        color: QColor,
        alpha: int,
        smaller: bool = False,
        show_memo: bool = True,
    ) -> None:
        draw_rect = QRectF(rect)
        if smaller:
            draw_rect.adjust(6, 4, -6, -4)

        fill = QColor(color)
        fill.setAlpha(alpha)
        painter.setPen(QPen(color.darker(130), 1.4))
        painter.setBrush(fill)
        painter.drawRoundedRect(draw_rect, 8, 8)

        content_rect = draw_rect.adjusted(10, 8, -10, -8)
        if content_rect.height() <= 0:
            return

        title = f"{source['제목']} ({source['시작 시각']} ~ {source['종료 시각']})"

        painter.save()
        painter.setClipRect(draw_rect.adjusted(2, 2, -2, -2))

        title_font = painter.font()
        title_fm = QFontMetrics(title_font)
        title_height = title_fm.height()
        available_width = max(16, int(content_rect.width() - 6))
        elided_title = title_fm.elidedText(title, Qt.ElideRight, available_width)
        title_width = min(available_width, title_fm.horizontalAdvance(elided_title))
        title_box = QRectF(
            content_rect.left() - 2,
            content_rect.top() - 1,
            title_width + 8,
            title_height + 4,
        )
        title_bg = QColor(color)
        title_bg.setAlpha(min(255, alpha + 35))
        painter.fillRect(title_box, title_bg)
        painter.setPen(pick_contrasting_text_color(title_bg))
        painter.drawText(
            title_box.adjusted(4, 0, -2, 0),
            Qt.AlignLeft | Qt.AlignVCenter,
            elided_title,
        )

        memo = (source.get("메모") or "").strip()
        if show_memo and (not smaller) and memo:
            memo_font = painter.font()
            memo_font.setPointSize(max(8, memo_font.pointSize() - 1))
            painter.setFont(memo_font)
            memo_fm = QFontMetrics(memo_font)
            memo_rect = QRectF(
                content_rect.left(),
                title_box.bottom() + 6,
                content_rect.width(),
                max(0.0, draw_rect.bottom() - 10 - (title_box.bottom() + 6)),
            )
            if memo_rect.height() >= memo_fm.height() + 2:
                painter.setPen(QColor(25, 25, 25))
                painter.drawText(memo_rect, Qt.AlignCenter | Qt.TextWordWrap, memo)
            painter.setFont(title_font)

        painter.restore()

    def _find_visible_current_time(self) -> Optional[datetime]:
        range_start, range_end = self.get_range()
        current_time_only = self.current_time.time().replace(microsecond=0)
        base_date = range_start.date()
        for offset in range(-1, 3):
            candidate = datetime.combine(base_date + timedelta(days=offset), current_time_only)
            if range_start <= candidate <= range_end:
                return candidate
        return None

    def _draw_current_time_label(self, painter: QPainter, y_now: float, visible_dt: datetime) -> None:
        current_label = format_ampm(
            self.current_time.hour,
            self.current_time.minute,
            self.current_time.second,
        )
        fm = QFontMetrics(painter.font())
        text_width = fm.horizontalAdvance(current_label)
        text_height = fm.height()
        left = self.LEFT_GUTTER - text_width - 14
        top = y_now - (text_height / 2) - 1
        bg_rect = QRectF(left - 6, top - 2, text_width + 12, text_height + 4)
        painter.fillRect(bg_rect, self._ampm_color(visible_dt))
        painter.setPen(QColor("#D11A1A"))
        painter.drawText(bg_rect.adjusted(6, 0, -6, 0), Qt.AlignCenter, current_label)

    def _draw_return_button(self, painter: QPainter) -> None:
        if not self.is_detached_from_now():
            self._return_button_rect = QRectF()
            return

        text = "되돌아가기"
        fm = QFontMetrics(painter.font())
        width = fm.horizontalAdvance(text) + 28
        height = fm.height() + 14
        rect = QRectF(
            (self.width() - width) / 2,
            self.height() - height - 16,
            width,
            height,
        )
        self._return_button_rect = rect
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(40, 40, 40, 120))
        painter.drawRoundedRect(rect, 12, 12)
        painter.setPen(Qt.white)
        painter.drawText(rect, Qt.AlignCenter, text)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), Qt.white)

        range_start, range_end = self.get_range()
        lane_left = self.lane_left()
        lane_right = self.lane_right()
        lane_width = self.lane_width()
        line_left = lane_left - self.LINE_OVERHANG
        line_right = lane_right + self.LINE_OVERHANG
        show_half_hour_label = (not self.full_day) and self.visible_side_minutes < 360
        show_ten_min_label = (not self.full_day) and self.visible_side_minutes <= 90

        # 오전/오후 배경
        strip_height = 3
        y = self.TOP_MARGIN
        while y < self.height() - self.BOTTOM_MARGIN:
            sample_dt = self.datetime_from_y(y + strip_height / 2)
            painter.fillRect(0, int(y), self.width(), strip_height + 1, self._ampm_color(sample_dt))
            y += strip_height

        # 좌측 상단/하단 오전·오후 표시
        base_font = painter.font()
        corner_font = QFont(base_font)
        corner_font.setBold(True)
        corner_font.setPointSize(base_font.pointSize() + 10)
        painter.setFont(corner_font)
        painter.setPen(QColor(50, 50, 50, 170))
        top_label_rect = QRectF(12, self.TOP_MARGIN + 6, self.LEFT_GUTTER - 24, 26)
        bottom_label_rect = QRectF(12, self.height() - self.BOTTOM_MARGIN - 32, self.LEFT_GUTTER - 24, 26)
        painter.drawText(top_label_rect, Qt.AlignLeft | Qt.AlignVCenter, self._ampm_text(range_start))
        painter.drawText(bottom_label_rect, Qt.AlignLeft | Qt.AlignVCenter, self._ampm_text(range_end - timedelta(seconds=1)))
        painter.setFont(base_font)

        first_tick = range_start.replace(second=0, microsecond=0)
        minute_mod = first_tick.minute % 10
        if minute_mod != 0:
            first_tick += timedelta(minutes=(10 - minute_mod))

        tick = first_tick
        while tick <= range_end:
            y = self.y_from_datetime(tick, range_start)
            minute = tick.minute
            if minute == 0:
                pen = QPen(Qt.black, 3.9)
            elif minute == 30:
                pen = QPen(Qt.black, 1.3)
            else:
                pen = QPen(QColor("#9A9A9A"), 1.0, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(line_left, y), QPointF(line_right, y))

            hour_label_rect = QRectF(10, y - 10, self.LEFT_GUTTER - 20, 24)
            if minute == 0 or (minute == 30 and show_half_hour_label):
                painter.setPen(Qt.black)
                label = format_no_ampm(tick.hour, tick.minute)
                painter.drawText(hour_label_rect, Qt.AlignRight | Qt.AlignVCenter, label)
            elif show_ten_min_label and minute in {10, 20, 40, 50}:
                painter.setPen(QColor("#555555"))
                painter.drawText(
                    10,
                    int(y) - 10,
                    self.LEFT_GUTTER - 24,
                    24,
                    Qt.AlignRight | Qt.AlignVCenter,
                    f"{minute}",
                )

            if minute == 0 and tick.hour in {0, 12}:
                guide_pen = QPen(QColor(35, 35, 35, 170), 1.1, Qt.DashLine)
                painter.setPen(guide_pen)
                gap_padding = 8

                # 왼쪽 보조선을 더 길게 보이도록, 라벨 오른쪽 일부까지 허용
                left_overlap_into_label = 36
                left_segment_end = max(
                    0.0,
                    min(float(self.width()), hour_label_rect.right() - left_overlap_into_label)
                )
                right_segment_start = min(float(self.width()), hour_label_rect.right() + gap_padding)

                if left_segment_end > 0:
                    painter.drawLine(QPointF(0.0, y), QPointF(left_segment_end, y))
                if right_segment_start < float(self.width()):
                    painter.drawLine(QPointF(right_segment_start, y), QPointF(float(self.width()), y))
            tick += timedelta(minutes=10)

        painter.setPen(QPen(QColor("#555555"), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(
            lane_left,
            self.TOP_MARGIN,
            lane_width,
            self.height() - self.TOP_MARGIN - self.BOTTOM_MARGIN,
        )

        rendered = self._build_rendered_schedules()
        for render in rendered:
            if self._is_render_hidden(render):
                continue
            color = QColor(render.source["표시 색상"])
            self._draw_schedule_rect(painter, render.rect, render.source, color, 170)

        visible_current = self._find_visible_current_time()
        if visible_current is not None:
            y_now = self.y_from_datetime(visible_current, range_start)
            painter.setPen(QPen(QColor("#D11A1A"), 4.8))
            painter.drawLine(QPointF(line_left, y_now), QPointF(line_right, y_now))
            self._draw_current_time_label(painter, y_now, visible_current)

        self._draw_return_button(painter)
        self._draw_active_schedule_preview(painter)

    def _draw_active_schedule_preview(self, painter: QPainter) -> None:
        if not self._active_render or not self._drag_start_dt_abs or not self._drag_end_dt_abs:
            return

        preview = dict(self._active_render.source)
        preview["시작 시각"] = minutes_to_hhmm(minutes_of_day_from_datetime(self._drag_start_dt_abs))
        preview["종료 시각"] = minutes_to_hhmm(minutes_of_day_from_datetime(self._drag_end_dt_abs))
        preview_rect = self._preview_rect_from_datetimes(self._drag_start_dt_abs, self._drag_end_dt_abs)
        if preview_rect is None:
            return

        if self._interaction_mode == "move_drag":
            self._draw_schedule_rect(
                painter,
                preview_rect,
                preview,
                QColor(preview["표시 색상"]).darker(115),
                180,
                smaller=True,
                show_memo=False,
            )
        elif self._interaction_mode in {"resize_top", "resize_bottom"}:
            self._draw_schedule_rect(
                painter,
                preview_rect,
                preview,
                QColor(preview["표시 색상"]).darker(108),
                185,
                smaller=False,
                show_memo=True,
            )



class MusicPlaybackDialog(QDialog):
    def __init__(self, schedule_item: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("음악 재생")
        self.setModal(False)
        self.setWindowModality(Qt.NonModal)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(420, 140)

        self.schedule_item = schedule_item
        self.audio_output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)

        title = schedule_item.get("제목", "(무제)")
        music_path = schedule_item.get("음악 파일") or ""
        volume = int(schedule_item.get("음악 볼륨", 100))
        volume = max(0, min(100, volume))
        self.audio_output.setVolume(volume / 100.0)

        self.title_label = QLabel(f"{title}")
        self.path_label = QLabel(Path(music_path).name if music_path else "")
        self.path_label.setWordWrap(True)
        self.stop_button = QPushButton("중지")
        self.stop_button.clicked.connect(self.stop_and_close)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("재생 중"))
        layout.addWidget(self.title_label)
        layout.addWidget(self.path_label)
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.stop_button)
        layout.addLayout(btns)

        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_error)

        if music_path:
            self.player.setSource(QUrl.fromLocalFile(str(Path(music_path).resolve())))

    def set_volume(self, volume: int) -> None:
        volume = max(0, min(100, int(volume)))
        self.audio_output.setVolume(volume / 100.0)

    def start(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.player.play()

    def stop_and_close(self) -> None:
        self.player.stop()
        self.close()

    def _on_media_status_changed(self, status) -> None:
        if status == QMediaPlayer.EndOfMedia:
            self.close()

    def _on_error(self, error, error_string=None) -> None:
        if error != QMediaPlayer.NoError:
            QMessageBox.warning(
                self,
                "음악 재생 오류",
                error_string or "음악 재생 중 오류가 발생했습니다.",
            )
            self.close()

    def closeEvent(self, event) -> None:
        self.player.stop()
        super().closeEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(980, 980)

        self.storage = ScheduleStorage(SCHEDULE_FILE)
        self.settings = load_settings(SETTINGS_FILE)
        self.apply_font_settings(self.settings)
        self.last_executed_keys: set[str] = set()
        self.active_music_dialogs: list[MusicPlaybackDialog] = []

        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top_bar = QHBoxLayout()
        self.toggle_all_button = QPushButton("전체")
        self.toggle_all_button.setCheckable(True)
        self.toggle_all_button.clicked.connect(self.toggle_full_day)

        self.import_button = QPushButton("불러오기")
        self.import_button.clicked.connect(self.import_schedules)
        self.export_button = QPushButton("내보내기")
        self.export_button.clicked.connect(self.export_schedules)

        self.add_button = QPushButton("추가")
        self.add_button.clicked.connect(self.open_add_dialog)

        top_bar.addWidget(self.toggle_all_button, 0, Qt.AlignLeft)
        top_bar.addStretch(1)
        top_bar.addWidget(self.import_button, 0, Qt.AlignCenter)
        top_bar.addWidget(self.export_button, 0, Qt.AlignCenter)
        top_bar.addStretch(1)
        top_bar.addWidget(self.add_button, 0, Qt.AlignRight)

        self.timeline = TimelineWidget()
        self.timeline.set_theme_colors(self.settings["낮시간 색상"], self.settings["저녁시간 색상"])
        self.timeline.set_schedules(self.storage.schedules)
        self.timeline.scheduleEditRequested.connect(self.open_edit_dialog)
        self.timeline.scheduleDeleteRequested.connect(self.delete_schedule)
        self.timeline.scheduleDuplicateRequested.connect(self.duplicate_schedule)
        self.timeline.scheduleMoved.connect(self.update_schedule_time)
        self.timeline.scheduleResized.connect(self.update_schedule_time)
        self.timeline.scheduleAddRequested.connect(self.open_add_dialog_with_preset)
        self.timeline.scheduleTestRequested.connect(self.test_schedule)
        self.timeline.visibleSpanChanged.connect(self.on_visible_span_changed)

        bottom_bar = QHBoxLayout()
        self.settings_button = QPushButton("설정")
        self.settings_button.clicked.connect(self.open_settings_dialog)
        bottom_bar.addWidget(self.settings_button, 0, Qt.AlignLeft)
        bottom_bar.addStretch(1)

        root.addLayout(top_bar)
        root.addWidget(self.timeline, 1)
        root.addLayout(bottom_bar)

        self.setCentralWidget(container)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("준비됨")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(1000)
        self.on_tick()

    def apply_font_settings(self, settings: dict) -> None:
        app = QApplication.instance()
        if app is None:
            return
        family = settings.get("폰트 패밀리", QFont().family())
        size = int(settings.get("폰트 크기", QFont().pointSize() if QFont().pointSize() > 0 else 10))
        font = QFont(family, size)
        app.setFont(font)

    def apply_visual_settings(self) -> None:
        self.apply_font_settings(self.settings)
        self.timeline.set_theme_colors(self.settings["낮시간 색상"], self.settings["저녁시간 색상"])
        self.update()

    def refresh_json_preview(self) -> None:
        pass

    def refresh_all_views(self) -> None:
        self.timeline.set_schedules(self.storage.schedules)
        self.refresh_json_preview()
        self.timeline.update()

    def toggle_full_day(self) -> None:
        full_day = self.toggle_all_button.isChecked()
        self.timeline.set_full_day(full_day)
        self.toggle_all_button.setText("현재" if full_day else "전체")
        if full_day:
            self.statusBar().showMessage("전체 보기: 0시부터 24시까지 표시", 4000)
        else:
            self.statusBar().showMessage(
                f"현재 기준 보기: 앞뒤 {self.timeline.visible_side_minutes // 60}시간 표시",
                4000,
            )

    def on_visible_span_changed(self, side_minutes: int) -> None:
        hours = side_minutes // 60
        half = side_minutes % 60
        label = f"앞뒤 표시 범위: {hours}시간"
        if half:
            label += f" {half}분"
        self.statusBar().showMessage(label, 2500)


    def open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        result = dialog.exec()
        if result == SettingsDialog.RESET_RESULT:
            answer = QMessageBox.question(
                self,
                "초기화",
                "정말 모든 데이터를 초기화 하겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                self.settings = default_settings()
                save_settings(SETTINGS_FILE, self.settings)
                self.storage.replace_all([])
                self.apply_visual_settings()
                self.refresh_all_views()
                self.statusBar().showMessage("모든 데이터를 초기화했습니다.", 4000)
            return
        if result == QDialog.Accepted:
            self.settings = dialog.result_settings()
            save_settings(SETTINGS_FILE, self.settings)
            self.apply_visual_settings()
            self.statusBar().showMessage("설정을 저장했습니다.", 3000)

    def export_schedules(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "스케줄 내보내기",
            str(BASE_DIR / "schedules_export.json"),
            "JSON 파일 (*.json);;모든 파일 (*)",
        )
        if not path:
            return False
        try:
            Path(path).write_text(
                json.dumps(self.storage.schedules, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.statusBar().showMessage(f"내보내기 완료: {path}", 5000)
            return True
        except Exception as e:
            QMessageBox.warning(self, "내보내기 오류", f"파일 저장에 실패했습니다.\n\n오류: {e}")
            return False

    def import_schedules(self) -> None:
        answer = QMessageBox.question(
            self,
            "스케줄 불러오기",
            "현재 스케줄을 저장하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Cancel:
            return
        if answer == QMessageBox.Yes and not self.export_schedules():
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "스케줄 불러오기",
            str(BASE_DIR),
            "JSON 파일 (*.json);;모든 파일 (*)",
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("JSON 최상위 구조가 리스트가 아닙니다.")
            normalized = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                if "제목" not in item or "시작 시각" not in item or "종료 시각" not in item or "표시 색상" not in item:
                    continue
                item = dict(item)
                item.setdefault("실행 파일", None)
                item.setdefault("메모", "")
                item.setdefault("음악 파일", None)
                item.setdefault("음악 볼륨", 100)
                item.setdefault("음악 파일", None)
                item.setdefault("음악 볼륨", 100)
                item.setdefault("음악 파일", None)
                parse_hhmm(item["시작 시각"])
                parse_hhmm(item["종료 시각"])
                normalized.append(item)
            self.storage.replace_all(normalized)
            self.refresh_all_views()
            self.statusBar().showMessage(f"불러오기 완료: {path}", 5000)
        except Exception as e:
            QMessageBox.warning(self, "불러오기 오류", f"JSON 파일을 불러오지 못했습니다.\n\n오류: {e}")


    def open_add_dialog(self) -> None:
        dialog = ScheduleDialog(self, test_callback=self.test_schedule_item)
        if dialog.exec() == QDialog.Accepted and dialog.result_schedule:
            self.storage.add(dialog.result_schedule)
            self.refresh_all_views()
            self.statusBar().showMessage(f"스케줄 추가: {dialog.result_schedule['제목']}", 5000)

    def open_add_dialog_with_preset(self, start_minutes: int, end_minutes: int) -> None:
        dialog = ScheduleDialog(
            self,
            preset_start_minutes=start_minutes,
            preset_end_minutes=end_minutes,
            test_callback=self.test_schedule_item,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result_schedule:
            self.storage.add(dialog.result_schedule)
            self.refresh_all_views()
            self.statusBar().showMessage(
                f"스케줄 추가: {dialog.result_schedule['제목']}",
                5000,
            )

    def open_edit_dialog(self, index: int) -> None:
        if not (0 <= index < len(self.storage.schedules)):
            return
        dialog = ScheduleDialog(self, self.storage.schedules[index], test_callback=self.test_schedule_item)
        if dialog.exec() == QDialog.Accepted and dialog.result_schedule:
            self.storage.update_at(index, dialog.result_schedule)
            self.refresh_all_views()
            self.statusBar().showMessage(f"스케줄 편집: {dialog.result_schedule['제목']}", 5000)

    def delete_schedule(self, index: int) -> None:
        if not (0 <= index < len(self.storage.schedules)):
            return
        item = self.storage.schedules[index]
        answer = QMessageBox.question(
            self,
            "스케줄 삭제",
            f"'{item['제목']}' 스케줄을 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.storage.delete_at(index)
            self.refresh_all_views()
            self.statusBar().showMessage(f"스케줄 삭제: {item['제목']}", 5000)

    def duplicate_schedule(self, index: int) -> None:
        if not (0 <= index < len(self.storage.schedules)):
            return

        original = dict(self.storage.schedules[index])
        start_minutes = parse_hhmm(original["시작 시각"])
        end_minutes = parse_hhmm(original["종료 시각"])
        duration = max(1, span_duration_minutes(start_minutes, end_minutes))

        new_start = (start_minutes + 30) % (24 * 60)
        new_end = (new_start + duration) % (24 * 60)

        duplicated = dict(original)
        duplicated["제목"] = f"{original['제목']}+"
        duplicated["시작 시각"] = minutes_to_hhmm(new_start)
        duplicated["종료 시각"] = minutes_to_hhmm(new_end)
        duplicated["표시 색상"] = random_schedule_color()
        duplicated.setdefault("메모", "")

        self.storage.add(duplicated)
        self.refresh_all_views()
        self.statusBar().showMessage(
            f"스케줄 복제: {duplicated['제목']} ({duplicated['시작 시각']} ~ {duplicated['종료 시각']})",
            5000,
        )

    def update_schedule_time(self, index: int, start_minutes: int, end_minutes: int) -> None:
        if not (0 <= index < len(self.storage.schedules)):
            return
        if start_minutes == end_minutes:
            end_minutes = (start_minutes + 1) % (24 * 60)

        item = dict(self.storage.schedules[index])
        item["시작 시각"] = minutes_to_hhmm(start_minutes)
        item["종료 시각"] = minutes_to_hhmm(end_minutes)
        self.storage.update_at(index, item)
        self.refresh_all_views()
        self.statusBar().showMessage(
            f"스케줄 갱신: {item['제목']} ({item['시작 시각']} ~ {item['종료 시각']})",
            5000,
        )


    def _cleanup_music_dialog(self, dialog: MusicPlaybackDialog) -> None:
        if dialog in self.active_music_dialogs:
            self.active_music_dialogs.remove(dialog)

    def test_schedule(self, index: int) -> None:
        if not (0 <= index < len(self.storage.schedules)):
            return
        self.test_schedule_item(dict(self.storage.schedules[index]))

    def test_schedule_item(self, item: dict, dialog_parent=None):
        dialog = self.play_schedule_music(item, parent_for_dialog=dialog_parent)
        self.execute_schedule_file(item)
        self.statusBar().showMessage(f"테스트 실행: {item.get('제목', '(테스트)')}", 4000)
        return dialog

    def on_tick(self) -> None:
        now = datetime.now()
        self.timeline.set_current_time(now)
        self.check_and_run_schedules(now)

    def check_and_run_schedules(self, now: datetime) -> None:
        current_key_prefix = now.strftime("%Y-%m-%d")
        self.last_executed_keys = {
            k for k in self.last_executed_keys if k.startswith(current_key_prefix)
        }

        for item in self.storage.schedules:
            start_minutes = parse_hhmm(item["시작 시각"])
            start_hour = start_minutes // 60
            start_minute = start_minutes % 60
            execution_key = f"{current_key_prefix}|{item['제목']}|{item['시작 시각']}"

            if execution_key in self.last_executed_keys:
                continue

            if now.hour == start_hour and now.minute == start_minute:
                self.last_executed_keys.add(execution_key)
                self.play_schedule_music(item)
                self.execute_schedule_file(item)

    def play_schedule_music(self, item: dict, parent_for_dialog=None):
        music_path = item.get("음악 파일")
        if not music_path:
            return None

        path = Path(music_path)
        if not path.exists():
            self.statusBar().showMessage(
                f"{item['제목']}: 음악 파일을 찾을 수 없음 - {music_path}",
                7000,
            )
            return None

        try:
            dialog_parent = parent_for_dialog if parent_for_dialog is not None else self
            dialog = MusicPlaybackDialog(item, dialog_parent)
            dialog.destroyed.connect(lambda _=None, d=dialog: self._cleanup_music_dialog(d))
            self.active_music_dialogs.append(dialog)
            dialog.start()
            self.statusBar().showMessage(
                f"{item['제목']}: 음악 재생 시작 - {music_path}",
                7000,
            )
            return dialog
        except Exception as e:
            QMessageBox.warning(
                self,
                "음악 재생 오류",
                f"음악 파일을 재생하지 못했습니다.\n\n{music_path}\n\n오류: {e}",
            )

    def execute_schedule_file(self, item: dict) -> None:
        exec_path = item.get("실행 파일")
        if not exec_path:
            self.statusBar().showMessage(
                f"{item['제목']}: 실행 파일이 없어 실행을 건너뜀",
                5000,
            )
            return

        path = Path(exec_path)
        if not path.exists():
            self.statusBar().showMessage(
                f"{item['제목']}: 실행 파일을 찾을 수 없음 - {exec_path}",
                7000,
            )
            return

        try:
            suffix = path.suffix.lower()

            if suffix == ".py":
                subprocess.Popen([sys.executable, str(path)], cwd=str(path.parent))

            elif suffix == ".sh":
                run_shell_script(path)

            elif sys.platform.startswith("win") and suffix in {".bat", ".cmd", ".ps1"}:
                run_shell_script(path)

            elif not sys.platform.startswith("win") and os.access(path, os.X_OK):
                run_executable_file(path)

            elif sys.platform.startswith("win") and suffix in {".exe", ".com"}:
                run_executable_file(path)

            else:
                open_with_default_app(path)

            self.statusBar().showMessage(
                f"{item['제목']}: 실행 파일 시작 - {exec_path}",
                7000,
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "실행 오류",
                f"실행 파일을 시작하지 못했습니다.\n\n{exec_path}\n\n오류: {e}",
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
