"""
60 FPS hardware-accelerated weapon preview canvas with drag-to-rotate, zoom,
backdrop selector, animated Enchantment VFX, and RimWorld-style Held Preview.
"""
from __future__ import annotations

import math
import time
from typing import List, Optional, Tuple

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from renderer import ComposedResult, enchantment_core, enchantment_fade, enchantment_tint
from theme import pil_to_qpixmap


class ForgePreviewCanvas(QWidget):
    """Interactive Forge Preview matching Dialog_Forge.DrawPreview + EnchantmentVfx."""

    def __init__(self, sparkle_pil: Optional[Image.Image] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)
        self._weapon_pixmap: Optional[QPixmap] = None
        self._result: Optional[ComposedResult] = None
        self._enchantment: int = 0
        self._angle: float = 0.0
        self._zoom: float = 1.0
        self._swing_active: bool = False
        self._backdrop_mode: int = 0  # 0=Forge Dark, 1=Stone Floor, 2=Grass, 3=Checker
        self._dragging: bool = False
        self._last_x: float = 0.0
        self._start_time = time.monotonic()

        self._sparkle_tinted: dict[int, QPixmap] = {}
        self._sparkle_pil = sparkle_pil

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 fps
        self._timer.timeout.connect(self._tick)

    def set_sparkle_image(self, sparkle_pil: Optional[Image.Image]) -> None:
        self._sparkle_pil = sparkle_pil
        self._sparkle_tinted.clear()

    def set_composed(self, result: ComposedResult, enchantment: int) -> None:
        self._result = result
        self._enchantment = enchantment
        self._weapon_pixmap = pil_to_qpixmap(result.image_rgba)
        self._update_timer()
        self.update()

    def set_backdrop_mode(self, mode: int) -> None:
        self._backdrop_mode = mode
        self.update()

    def set_swing_test(self, active: bool) -> None:
        self._swing_active = active
        self._update_timer()
        if not active:
            self.update()

    def reset_view(self) -> None:
        self._angle = 0.0
        self._zoom = 1.0
        self.update()

    def _update_timer(self) -> None:
        if self._enchantment > 0 or self._swing_active:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def _tick(self) -> None:
        self.update()

    def _get_tinted_sparkle(self, element: int) -> Optional[QPixmap]:
        if self._sparkle_pil is None:
            return None
        if element in self._sparkle_tinted:
            return self._sparkle_tinted[element]
        cr, cg, cb = enchantment_core(element)
        im = self._sparkle_pil.copy()
        r, g, b, a = im.split()
        # Multiply white sparkle with core tint
        from PIL import ImageChops
        tint_im = Image.new("RGBA", im.size, (cr, cg, cb, 255))
        tinted = ImageChops.multiply(im, tint_im)
        pix = pil_to_qpixmap(tinted)
        self._sparkle_tinted[element] = pix
        return pix

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._last_x = event.position().x()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            dx = event.position().x() - self._last_x
            self._last_x = event.position().x()
            self._angle = (self._angle + dx) % 360.0
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 0.9
        self._zoom = max(0.5, min(3.0, self._zoom * factor))
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        w, h = self.width(), self.height()
        self._draw_backdrop(p, w, h)

        if self._weapon_pixmap is None or self._result is None:
            return

        now = time.monotonic() - self._start_time
        size = min(w - 28.0, h - 28.0) * self._zoom
        cx, cy = w * 0.5, h * 0.5

        angle = self._angle
        if self._swing_active:
            angle += math.sin(now * 4.2) * 52.0

        p.save()
        p.translate(cx, cy)
        p.rotate(angle)

        # Draw weapon
        target_rect = QRectF(-size * 0.5, -size * 0.5, size, size)
        p.drawPixmap(target_rect.toRect(), self._weapon_pixmap)

        # Enchantment aura + particles (matching Dialog_Forge.DrawEnchantmentPreview)
        if self._enchantment > 0:
            er, eg, eb = enchantment_tint(self._enchantment)
            span_x, span_y = self._result.enchant_span
            aura_top = -span_y * size
            aura_bot = -span_x * size

            # Soft glowing aura behind/over blade
            glow_alpha = int((0.18 + 0.06 * math.sin(now * 2.5)) * 255)
            grad = QRadialGradient(
                QPointF(self._result.enchant_center_x * size, (aura_top + aura_bot) * 0.5),
                max(20.0, (aura_bot - aura_top) * 0.65),
            )
            grad.setColorAt(0.0, QColor(er, eg, eb, glow_alpha))
            grad.setColorAt(1.0, QColor(er, eg, eb, 0))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            p.fillRect(
                QRectF(
                    -self._result.enchant_half_width * 2.2 * size + self._result.enchant_center_x * size,
                    aura_top - 20,
                    self._result.enchant_half_width * 4.4 * size,
                    (aura_bot - aura_top) + 40,
                ),
                QBrush(grad),
            )

            sparkle_pix = self._get_tinted_sparkle(self._enchantment)
            anchors = self._result.preview_anchors
            for i in range(7):
                speed = 1.5 if self._enchantment == 3 else 0.7
                clk = now * speed + i / 7.0
                age = clk % 1.0
                if anchors:
                    idx = (i * 5 + int(math.floor(clk)) * 11) % len(anchors)
                    lx, ly = anchors[idx]
                else:
                    lx = self._result.enchant_center_x
                    ly = (span_x + span_y) * 0.5

                # Slight float motion for flame/siphon
                if self._enchantment == 1:
                    ly += age * 0.04
                elif self._enchantment == 6:
                    ly -= age * 0.03

                px = lx * size
                py = -ly * size
                p_size = max(0.065, min(0.11, self._result.enchant_half_width * 1.4)) * (1.0 - 0.3 * age) * size
                stretch = 1.45 if self._enchantment == 1 else 1.0
                alpha = enchantment_fade(age) * 0.95

                if sparkle_pix is not None:
                    p.save()
                    p.setOpacity(alpha)
                    p.translate(px, py)
                    p.rotate((now * 3.0 + i * 2.4) * 20.0)
                    p.drawPixmap(
                        QRectF(-p_size * 0.5, -p_size * stretch * 0.5, p_size, p_size * stretch).toRect(),
                        sparkle_pix,
                    )
                    if self._enchantment == 3 and i < 3:
                        p.drawPixmap(
                            QRectF(-p_size * 0.12, -p_size * 0.65, p_size * 0.24, p_size * 1.3).toRect(),
                            sparkle_pix,
                        )
                    p.restore()

            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        p.restore()

        # Subtle HUD hint
        p.setPen(QColor(154, 166, 168, 170))
        p.drawText(
            QRectF(8, h - 22, w - 16, 18),
            Qt.AlignmentFlag.AlignCenter,
            f"Kéo chuột để xoay ({self._angle:.0f}°) · Cuộn để zoom ({self._zoom:.1f}x) · Double-click reset",
        )

    def _draw_backdrop(self, p: QPainter, w: int, h: int) -> None:
        if self._backdrop_mode == 0:
            p.fillRect(0, 0, w, h, QColor(14, 17, 19))
            p.setPen(QPen(QColor(30, 37, 39), 1))
            step = 32
            for x in range(0, w, step):
                p.drawLine(x, 0, x, h)
            for y in range(0, h, step):
                p.drawLine(0, y, w, y)
            p.setPen(QPen(QColor(55, 65, 68, 120), 1, Qt.PenStyle.DashLine))
            p.drawLine(w // 2, 0, w // 2, h)
            p.drawLine(0, h // 2, w, h // 2)
        elif self._backdrop_mode == 1:
            p.fillRect(0, 0, w, h, QColor(58, 60, 62))
            p.setPen(QPen(QColor(42, 44, 46), 2))
            step = 48
            for x in range(0, w, step):
                p.drawLine(x, 0, x, h)
            for y in range(0, h, step):
                p.drawLine(0, y, w, y)
        elif self._backdrop_mode == 2:
            p.fillRect(0, 0, w, h, QColor(49, 71, 44))
            p.setPen(QPen(QColor(58, 84, 52), 1))
            step = 48
            for x in range(0, w, step):
                p.drawLine(x, 0, x, h)
            for y in range(0, h, step):
                p.drawLine(0, y, w, y)
        else:
            sq = 16
            c1, c2 = QColor(42, 46, 48), QColor(56, 61, 64)
            for y in range(0, h, sq):
                for x in range(0, w, sq):
                    p.fillRect(x, y, sq, sq, c1 if ((x // sq + y // sq) % 2 == 0) else c2)


class HeldPreviewWidget(QWidget):
    """Stylized RimWorld colonist holding the forged weapon at accurate gripOffset & angle."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(140)
        self._weapon_pixmap: Optional[QPixmap] = None
        self._result: Optional[ComposedResult] = None
        self._enchantment: int = 0
        self._facing_left: bool = False

    def set_composed(self, result: ComposedResult, enchantment: int) -> None:
        self._result = result
        self._enchantment = enchantment
        self._weapon_pixmap = pil_to_qpixmap(result.image_rgba)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._facing_left = not self._facing_left
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(15, 19, 21))
        p.setPen(QPen(QColor(44, 53, 56), 1))
        p.drawRect(0, 0, w - 1, h - 1)

        cx, cy = w * 0.48, h * 0.54

        # Draw ground shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawEllipse(QPointF(cx, cy + 36), 24, 9)

        # Draw stylized RimWorld pawn torso (parka/tunic) & head
        p.setPen(QPen(QColor(22, 24, 26), 2.5))
        p.setBrush(QColor(72, 92, 108))
        p.drawRoundedRect(QRectF(cx - 17, cy - 8, 34, 42), 10, 10)

        # Pawn head
        p.setBrush(QColor(224, 185, 152))
        p.drawEllipse(QPointF(cx, cy - 22), 16, 17)
        # Hair
        p.setBrush(QColor(52, 40, 32))
        p.drawChord(QRectF(cx - 16, cy - 39, 32, 24), 0, 180 * 16)
        # Eyes
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(24, 24, 24))
        ex = -4 if self._facing_left else 4
        p.drawEllipse(QPointF(cx + ex - 4, cy - 20), 1.8, 2.2)
        p.drawEllipse(QPointF(cx + ex + 4, cy - 20), 1.8, 2.2)

        # Draw weapon anchored at hand/grip
        if self._weapon_pixmap is not None and self._result is not None:
            px_scale = 52.0  # 1 RimWorld tile ~= 52px in preview
            draw_px = self._result.draw_size * px_scale
            grip_offset_px = (self._result.grip_y_norm - 0.5) * draw_px

            hand_x = cx + (-20.0 if self._facing_left else 20.0)
            hand_y = cy + 8.0
            angle = (-self._result.equipped_angle) if self._facing_left else self._result.equipped_angle

            p.save()
            p.translate(hand_x, hand_y)
            p.rotate(angle)
            # Because weapon sprite tip is UP (-Y in Qt), gripOffset from center is +grip_offset_px downward
            if self._enchantment > 0:
                er, eg, eb = enchantment_tint(self._enchantment)
                grad = QRadialGradient(QPointF(0, 0), draw_px * 0.35)
                grad.setColorAt(0.0, QColor(er, eg, eb, 90))
                grad.setColorAt(1.0, QColor(er, eg, eb, 0))
                p.setBrush(QBrush(grad))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(0, -draw_px * 0.15 + grip_offset_px), draw_px * 0.28, draw_px * 0.38)

            p.drawPixmap(
                QRectF(-draw_px * 0.5, -draw_px * 0.5 + grip_offset_px, draw_px, draw_px).toRect(),
                self._weapon_pixmap,
            )
            p.restore()

            # Pawn hand circle over grip
            p.setPen(QPen(QColor(22, 24, 26), 1.5))
            p.setBrush(QColor(224, 185, 152))
            p.drawEllipse(QPointF(hand_x, hand_y), 4.5, 4.5)

        p.setPen(QColor(145, 156, 158))
        p.drawText(QRectF(8, 5, w - 16, 18), Qt.AlignmentFlag.AlignLeft, "Held preview (click để đổi hướng)")
