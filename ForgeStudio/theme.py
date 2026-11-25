"""
Dark Forge QSS Theme & reusable UI helper components matching Personal Forge.
"""
from __future__ import annotations

from typing import Callable, Optional
from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


FORGE_QSS = """
QMainWindow, QWidget {
    background-color: #101415;
    color: #e6eaeb;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QFrame#Panel, QGroupBox {
    background-color: #181d1f;
    border: 1px solid #353f42;
    border-radius: 4px;
}
QGroupBox {
    margin-top: 10px;
    padding-top: 12px;
    font-weight: 600;
    color: #c49645;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    background-color: #23282b;
    color: #e6eaeb;
    border: 1px solid #485254;
    border-radius: 3px;
    padding: 6px 10px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #2d3438;
    border-color: #707d80;
}
QPushButton:pressed {
    background-color: #1c2123;
}
QPushButton[selected="true"], QPushButton:checked {
    background-color: #3d3321;
    border: 1px solid #c49645;
    color: #f0cc87;
}
QPushButton#PrimaryBtn {
    background-color: #4a3a1e;
    border: 1px solid #c49645;
    color: #f5d89a;
    font-weight: 600;
}
QPushButton#PrimaryBtn:hover {
    background-color: #5e4a27;
}
QPushButton#AccentGreenBtn {
    background-color: #213b29;
    border: 1px solid #59a86d;
    color: #b8efc4;
    font-weight: 600;
}
QPushButton#AccentGreenBtn:hover {
    background-color: #2b4d35;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #0e1213;
    color: #e6eaeb;
    border: 1px solid #3c4648;
    border-radius: 3px;
    padding: 4px 6px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border-color: #c49645;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: #101415;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #364042;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #526063;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #0d1011;
    border: 1px solid #353f42;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #c49645;
    border: 1px solid #f0cc87;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: #7a5c28;
    border-radius: 3px;
}
QTabWidget::pane {
    border: 1px solid #353f42;
    background: #14191b;
}
QTabBar::tab {
    background: #1a2022;
    color: #9aa6a8;
    border: 1px solid #353f42;
    padding: 8px 18px;
    margin-right: 3px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #3d3321;
    color: #f0cc87;
    border-color: #c49645;
}
QLabel#MutedLabel {
    color: #9aa6a8;
}
QLabel#GoldTitle {
    color: #c49645;
    font-size: 16px;
    font-weight: 700;
}
"""


def pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    rgba = pil_img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class ForgeSlider(QWidget):
    """Numeric + Slider + Reset row matching Dialog_Forge.Slider."""
    valueChanged = Signal(float)

    def __init__(
        self,
        label: str,
        minimum: float,
        maximum: float,
        step: float,
        default_val: float,
        is_percent: bool = True,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.default_val = default_val
        self.is_percent = is_percent
        self.scale = 100 if is_percent else 255
        self._blocking = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 4)
        layout.setSpacing(4)

        top = QHBoxLayout()
        self.lbl = QLabel(label)
        self.spin = QSpinBox()
        self.spin.setRange(round(minimum * self.scale), round(maximum * self.scale))
        self.spin.setSuffix("%" if is_percent else "")
        self.spin.setFixedWidth(74)
        top.addWidget(self.lbl, 1)
        top.addWidget(self.spin)
        layout.addLayout(top)

        bot = QHBoxLayout()
        bot.setSpacing(5)
        self.btn_minus = QPushButton("−")
        self.btn_minus.setFixedSize(26, 24)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, max(1, round((maximum - minimum) / step)))
        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedSize(26, 24)
        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setFixedSize(48, 24)

        bot.addWidget(self.btn_minus)
        bot.addWidget(self.slider, 1)
        bot.addWidget(self.btn_plus)
        bot.addWidget(self.btn_reset)
        layout.addLayout(bot)

        self.slider.valueChanged.connect(self._on_slider)
        self.spin.valueChanged.connect(self._on_spin)
        self.btn_minus.clicked.connect(lambda: self.set_value(self.value() - self.step))
        self.btn_plus.clicked.connect(lambda: self.set_value(self.value() + self.step))
        self.btn_reset.clicked.connect(lambda: self.set_value(self.default_val))

        self.set_value(default_val, emit=False)

    def value(self) -> float:
        return self.minimum + self.slider.value() * self.step

    def set_value(self, val: float, emit: bool = True) -> None:
        val = max(self.minimum, min(self.maximum, val))
        self._blocking = True
        tick = round((val - self.minimum) / self.step)
        self.slider.setValue(tick)
        self.spin.setValue(round(val * self.scale))
        self._blocking = False
        if emit:
            self.valueChanged.emit(self.value())

    def _on_slider(self, tick: int) -> None:
        if self._blocking:
            return
        val = max(self.minimum, min(self.maximum, self.minimum + tick * self.step))
        self._blocking = True
        self.spin.setValue(round(val * self.scale))
        self._blocking = False
        self.valueChanged.emit(val)

    def _on_spin(self, s_val: int) -> None:
        if self._blocking:
            return
        val = max(self.minimum, min(self.maximum, s_val / self.scale))
        self._blocking = True
        self.slider.setValue(round((val - self.minimum) / self.step))
        self._blocking = False
        self.valueChanged.emit(val)
