"""
60 FPS hardware-accelerated weapon preview canvas with:
- Drag-to-rotate, zoom, backdrop selector, swing test
- Contour-hugging Elemental Rim Aura (Gaussian edge glow around exact blade shape)
- Inlaid Elemental Gem Socket at guard/blade junction
- 12 distinct, gorgeous animated particle & shader VFX styles
- RimWorld-style Held Preview with active element glow & gem
"""
from __future__ import annotations

import math
import random
import time
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageFilter
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from mod_data import BUILTIN_ELEMENTS, ElementDef
from renderer import ComposedResult, enchantment_fade
from theme import pil_to_qpixmap


def _build_blade_aura_pixmap(
    blade_mask: Image.Image,
    primary_rgb: Tuple[int, int, int],
    secondary_rgb: Tuple[int, int, int],
) -> Tuple[QPixmap, QPixmap]:
    """
    Creates two contour-hugging aura layers from the blade alpha silhouette:
    1) Outer soft bloom (primary color)
    2) Crisp inner edge-highlight / magma-runic rim (secondary color)
    """
    # Downscale to 256 for fast blur & upscale smoothly
    m_small = blade_mask.resize((256, 256), Image.Resampling.BILINEAR)
    outer_blur = m_small.filter(ImageFilter.GaussianBlur(radius=9.5))
    inner_erode = m_small.filter(ImageFilter.MinFilter(size=5))
    edge_only = ImageChops.subtract(m_small, inner_erode).filter(ImageFilter.GaussianBlur(radius=1.8))

    pr, pg, pb = primary_rgb
    sr, sg, sb = secondary_rgb

    oa = np.asarray(outer_blur, dtype=np.float32) / 255.0
    outer_rgba = np.zeros((256, 256, 4), dtype=np.uint8)
    outer_rgba[:, :, 0] = pr
    outer_rgba[:, :, 1] = pg
    outer_rgba[:, :, 2] = pb
    outer_rgba[:, :, 3] = np.clip(oa * 215.0, 0, 255).astype(np.uint8)

    ea = np.asarray(edge_only, dtype=np.float32) / 255.0
    edge_rgba = np.zeros((256, 256, 4), dtype=np.uint8)
    edge_rgba[:, :, 0] = sr
    edge_rgba[:, :, 1] = sg
    edge_rgba[:, :, 2] = sb
    edge_rgba[:, :, 3] = np.clip(ea * 240.0, 0, 255).astype(np.uint8)

    return (
        pil_to_qpixmap(Image.fromarray(outer_rgba, "RGBA")),
        pil_to_qpixmap(Image.fromarray(edge_rgba, "RGBA")),
    )


def _draw_faceted_gem(
    p: QPainter,
    cx: float,
    cy: float,
    radius: float,
    primary: Tuple[int, int, int],
    secondary: Tuple[int, int, int],
    pulse: float,
) -> None:
    """Draws a crisp faceted elemental gem socketed into the weapon guard."""
    pr, pg, pb = primary
    sr, sg, sb = secondary
    p.save()
    p.translate(cx, cy)

    # Outer glow halo
    halo = QRadialGradient(QPointF(0, 0), radius * 2.4)
    halo.setColorAt(0.0, QColor(pr, pg, pb, int(140 * pulse)))
    halo.setColorAt(1.0, QColor(pr, pg, pb, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(halo))
    p.drawEllipse(QPointF(0, 0), radius * 2.4, radius * 2.4)

    # Gold/dark metallic bezel ring
    bezel = QPolygonF([
        QPointF(0, -radius * 1.25),
        QPointF(radius * 0.95, 0),
        QPointF(0, radius * 1.25),
        QPointF(-radius * 0.95, 0),
    ])
    p.setPen(QPen(QColor(215, 175, 95), max(1.2, radius * 0.16)))
    p.setBrush(QColor(28, 32, 34))
    p.drawPolygon(bezel)

    # Inner faceted gem body
    gem = QPolygonF([
        QPointF(0, -radius * 0.95),
        QPointF(radius * 0.72, 0),
        QPointF(0, radius * 0.95),
        QPointF(-radius * 0.72, 0),
    ])
    grad = QRadialGradient(QPointF(-radius * 0.18, -radius * 0.25), radius * 1.2)
    grad.setColorAt(0.0, QColor(min(255, sr + 40), min(255, sg + 40), min(255, sb + 40), 255))
    grad.setColorAt(0.55, QColor(pr, pg, pb, 245))
    grad.setColorAt(1.0, QColor(max(0, pr // 3), max(0, pg // 3), max(0, pb // 3), 255))
    p.setPen(QPen(QColor(255, 255, 255, 160), 0.9))
    p.setBrush(QBrush(grad))
    p.drawPolygon(gem)

    # Facet highlight glint
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, int(190 * pulse)))
    p.drawEllipse(QPointF(-radius * 0.18, -radius * 0.28), radius * 0.22, radius * 0.15)
    p.restore()


class ForgePreviewCanvas(QWidget):
    """Interactive Forge Preview with contour-hugging elemental aura & 12 VFX styles."""

    def __init__(self, sparkle_pil: Optional[Image.Image] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)
        self._weapon_pixmap: Optional[QPixmap] = None
        self._outer_aura_pix: Optional[QPixmap] = None
        self._edge_aura_pix: Optional[QPixmap] = None
        self._result: Optional[ComposedResult] = None
        self._element: ElementDef = BUILTIN_ELEMENTS[0]
        self._socket_gem: bool = True
        self._vfx_intensity: float = 1.0

        self._angle: float = 0.0
        self._zoom: float = 1.0
        self._swing_active: bool = False
        self._backdrop_mode: int = 0
        self._dragging: bool = False
        self._last_x: float = 0.0
        self._start_time = time.monotonic()

        self._sparkle_tinted: dict[Tuple[int, int, int], QPixmap] = {}
        self._sparkle_pil = sparkle_pil
        self._store = None
        self._custom_img_cache: dict[tuple, QPixmap] = {}

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def set_store(self, store) -> None:
        self._store = store
        self._custom_img_cache.clear()

    def clear_custom_vfx_cache(self) -> None:
        self._custom_img_cache.clear()

    def set_sparkle_image(self, sparkle_pil: Optional[Image.Image]) -> None:
        self._sparkle_pil = sparkle_pil
        self._sparkle_tinted.clear()

    def set_composed(
        self,
        result: ComposedResult,
        element: ElementDef,
        socket_gem: bool = True,
        vfx_intensity: float = 1.0,
    ) -> None:
        self._result = result
        self._element = element
        self._socket_gem = socket_gem
        self._vfx_intensity = vfx_intensity
        self._weapon_pixmap = pil_to_qpixmap(result.image_rgba)
        if element.id > 0:
            self._outer_aura_pix, self._edge_aura_pix = _build_blade_aura_pixmap(
                result.blade_mask_alpha, element.primary_rgb, element.secondary_rgb
            )
        else:
            self._outer_aura_pix = None
            self._edge_aura_pix = None
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
        if self._element.id > 0 or self._swing_active:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def _tick(self) -> None:
        self.update()

    def _get_tinted_sparkle(self, rgb: Tuple[int, int, int]) -> Optional[QPixmap]:
        if self._sparkle_pil is None:
            return None
        if rgb in self._sparkle_tinted:
            return self._sparkle_tinted[rgb]
        from PIL import ImageChops
        tint_im = Image.new("RGBA", self._sparkle_pil.size, (rgb[0], rgb[1], rgb[2], 255))
        tinted = ImageChops.multiply(self._sparkle_pil, tint_im)
        pix = pil_to_qpixmap(tinted)
        self._sparkle_tinted[rgb] = pix
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

        target_rect = QRectF(-size * 0.5, -size * 0.5, size, size)
        elem = self._element
        inten = max(0.2, min(2.5, self._vfx_intensity))
        pulse = 0.78 + 0.22 * math.sin(now * 3.1)

        # 1. Back Outer Contour Glow + Back-half 3D Ribbons / Lightning / Custom Layers (behind weapon)
        custom_aura_handled = ("ice_armor", "sonic_slash", "eclipse_flare", "shadow_strife", "eternal_alpha", "nova_burn", "abyssal_miasma", "ink_void")
        if elem.id > 0:
            if self._outer_aura_pix is not None and elem.vfx_style not in custom_aura_handled:
                p.save()
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
                p.setOpacity(min(1.0, 0.50 * pulse * inten))
                p.drawPixmap(target_rect.toRect(), self._outer_aura_pix)
                p.restore()
            if elem.layers:
                self._draw_custom_layers(p, elem, size, now, inten, back_pass=True)
            else:
                self._dispatch_builtin_style(p, elem, size, now, inten, back_pass=True)

        # 2. Weapon Base Sprite
        p.drawPixmap(target_rect.toRect(), self._weapon_pixmap)

        # 3. Contour Edge Highlight + Front-half 3D Ribbons / Lightning / Custom Layers + Elemental VFX
        if elem.id > 0:
            if self._edge_aura_pix is not None and elem.vfx_style not in custom_aura_handled:
                p.save()
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
                p.setOpacity(min(1.0, (0.50 + 0.25 * math.sin(now * 4.0)) * inten))
                p.drawPixmap(target_rect.toRect(), self._edge_aura_pix)
                p.restore()

            # Inlaid Elemental Gem at guard/blade junction
            if self._socket_gem and elem.vfx_style not in ("eclipse_flare", "ice_armor", "shadow_strife", "eternal_alpha", "nova_burn", "abyssal_miasma", "ink_void"):
                gem_y = (0.5 - self._result.socket_gem_y_norm) * size
                gem_r = max(6.0, size * 0.025)
                _draw_faceted_gem(p, 0.0, gem_y, gem_r, elem.primary_rgb, elem.secondary_rgb, pulse)

            if elem.layers:
                self._draw_custom_layers(p, elem, size, now, inten, back_pass=False)
            else:
                self._dispatch_builtin_style(p, elem, size, now, inten, back_pass=False)
                if elem.vfx_style not in ("azure_jet", "ember_tendrils", "sonic_slash", "ice_armor", "plasma_web", "water_sheath", "eclipse_flare", "shadow_strife", "eternal_alpha", "nova_burn", "abyssal_miasma", "ink_void"):
                    self._draw_element_vfx(p, elem, size, now, inten)

        p.restore()

        p.setPen(QColor(154, 166, 168, 170))
        p.drawText(
            QRectF(8, h - 22, w - 16, 18),
            Qt.AlignmentFlag.AlignCenter,
            f"Kéo chuột để xoay ({self._angle:.0f}°) · Cuộn để zoom ({self._zoom:.1f}x) · Double-click reset",
        )

    def _draw_helical_flame_ribbons(
        self,
        p: QPainter,
        elem: ElementDef,
        size: float,
        now: float,
        inten: float,
        back_pass: bool,
        bloom_overlay: bool = False,
        ribbon_count: int = 2,
        turns: float = 1.20,
        wispiness: float = 1.0,
        spread: float = 1.0,
    ) -> None:
        """
        Draws silky volumetric 3D helical ribbons spiraling around the weapon:
        - wispiness=1.0 -> blazing fire tongues + braided filaments + sparks
        - wispiness=0.0..0.3 -> sleek spirit/wind/water/energy ribbons
        """
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.05, self._result.enchant_half_width)

        y_bot = -(span_x + 0.005) * size
        y_top = -(span_y + 0.030) * size
        rad_x = max(hw_b * 2.05, 0.155) * size * spread
        tilt_y = rad_x * 0.14

        style = elem.vfx_style
        n_samples = 96

        rc = max(1, min(4, ribbon_count))
        ribbon_configs = []
        for ri in range(rc):
            ph = 0.25 + ri * (2.0 * math.pi / rc)
            spd_r = 2.3 - 0.18 * (ri % 2)
            amp_r = 1.04 - 0.14 * (ri % 2)
            yt0 = 0.0 if ri == 0 else min(0.25, 0.08 * ri)
            yt1 = 0.94 + 0.06 * (ri % 2)
            ribbon_configs.append((ph, turns * (1.0 - 0.06 * (ri % 2)), spd_r, amp_r, yt0, yt1))

        # Prepare blurred volumetric halo + soft filaments on 224x224 buffer
        buf_res = 224
        buf_scale = buf_res / max(size, 1.0)
        halo_qimg = QImage(buf_res, buf_res, QImage.Format.Format_RGBA8888)
        halo_qimg.fill(QColor(0, 0, 0, 0))
        hp = QPainter(halo_qimg)
        hp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        hp.translate(buf_res * 0.5, buf_res * 0.5)
        hp.setPen(Qt.PenStyle.NoPen)

        fil_qimg = QImage(buf_res, buf_res, QImage.Format.Format_RGBA8888)
        fil_qimg.fill(QColor(0, 0, 0, 0))
        fp = QPainter(fil_qimg)
        fp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fp.translate(buf_res * 0.5, buf_res * 0.5)
        fp.setBrush(Qt.BrushStyle.NoBrush)

        def build_taper_poly(pts_xyw: list[tuple[float, float, float]]) -> QPolygonF:
            if len(pts_xyw) < 2:
                return QPolygonF()
            left_pts: list[QPointF] = []
            right_pts: list[QPointF] = []
            m = len(pts_xyw)
            for idx, (x, y, hw) in enumerate(pts_xyw):
                p_prev = pts_xyw[max(0, idx - 1)]
                p_next = pts_xyw[min(m - 1, idx + 1)]
                dx = p_next[0] - p_prev[0]
                dy = p_next[1] - p_prev[1]
                ln = max(1e-4, math.hypot(dx, dy))
                nx, ny = -dy / ln, dx / ln
                left_pts.append(QPointF(x + nx * hw, y + ny * hw))
                right_pts.append(QPointF(x - nx * hw, y - ny * hw))
            return QPolygonF(left_pts + list(reversed(right_pts)))

        def ribbon_palette(r_idx: int) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
            if style == "frostfire":
                if r_idx == 0:
                    return (18, 130, 255), (60, 218, 255), (175, 248, 255), (242, 255, 255)
                return (220, 42, 8), (255, 118, 20), (255, 205, 80), (255, 245, 210)
            if style == "magma":
                return (195, 18, 4), (255, 68, 12), (255, 178, 42), (255, 238, 175)
            pr, pg, pb = elem.primary_rgb
            sr, sg, sb = elem.secondary_rgb
            return (
                (min(255, int(pr * 0.92)), max(16, int(pg * 0.34)), max(4, int(pb * 0.18))),
                (pr, min(255, int(pg * 1.02)), pb),
                (min(255, int(sr)), min(255, int(sg * 0.88)), min(255, int(sb * 0.48))),
                (255, 248, 212),
            )

        # Collect vector runs for front/back pass
        vector_runs: list[tuple[int, bool, list[tuple[float, float, float, float, float]]]] = []

        for r_idx, (phase_off, turns, speed, amp_s, yt0, yt1) in enumerate(ribbon_configs):
            c_halo, c_mid, c_fil, c_core = ribbon_palette(r_idx)
            pts: list[tuple[float, float, float, float, float]] = []
            for k in range(n_samples + 1):
                t = k / float(n_samples)
                theta = t * (turns * 2.0 * math.pi) - now * speed + phase_off
                env = (math.sin(t * math.pi) ** 0.78) * amp_s * (1.08 - 0.18 * t)
                sway = math.sin(t * 7.0 - now * 4.6 + r_idx * 1.9) * 0.011 * size * env
                px = cx_b + math.sin(theta) * rad_x * env + sway
                y_prog = yt0 + (yt1 - yt0) * (t ** 0.94)
                py = y_bot + (y_top - y_bot) * y_prog + math.cos(theta) * tilt_y * env
                pz = math.cos(theta)
                taper = (math.sin(t * math.pi) ** 1.15) * (1.05 - 0.25 * t)
                pts.append((px, py, pz, t, taper))

            # Split cleanly at exact interpolated z=0 crossing (no overlap double-blend!)
            cur_run: list[tuple[float, float, float, float, float]] = []
            cur_front: Optional[bool] = None
            for i_pt, pt in enumerate(pts):
                is_f = pt[2] >= 0.0
                if cur_front is None:
                    cur_front = is_f
                    cur_run.append(pt)
                elif is_f == cur_front:
                    cur_run.append(pt)
                else:
                    prev = cur_run[-1]
                    dz = pt[2] - prev[2]
                    frac = (-prev[2] / dz) if abs(dz) > 1e-6 else 0.5
                    cross = (
                        prev[0] + (pt[0] - prev[0]) * frac,
                        prev[1] + (pt[1] - prev[1]) * frac,
                        0.0,
                        prev[3] + (pt[3] - prev[3]) * frac,
                        prev[4] + (pt[4] - prev[4]) * frac,
                    )
                    cur_run.append(cross)
                    vector_runs.append((r_idx, cur_front, cur_run))
                    cur_run = [cross, pt]
                    cur_front = is_f
            if len(cur_run) >= 2 and cur_front is not None:
                vector_runs.append((r_idx, cur_front, cur_run))

        # Draw halo & soft-blurred braided filaments
        for r_idx, is_front, run in vector_runs:
            if not bloom_overlay and (back_pass == is_front):
                continue
            c_halo, c_mid, c_fil, _ = ribbon_palette(r_idx)
            # Smooth depth factor continuous at z=0 (0.85 on both sides!)
            avg_z = sum(pt[2] for pt in run) / max(len(run), 1)
            depth_mul = 0.24 if bloom_overlay else (0.85 + 0.15 * avg_z)

            halo_pts = [
                (px * buf_scale, py * buf_scale, max(1.2, size * 0.042 * taper * inten * buf_scale * (0.85 + 0.15 * pz if not bloom_overlay else 0.28)))
                for (px, py, pz, _, taper) in run
            ]
            hp.setBrush(QColor(*c_halo, int(min(255, 160 * min(1.2, inten) * depth_mul))))
            hp.drawPolygon(build_taper_poly(halo_pts))

            if wispiness > 0.15:
                for idx in range(5, len(run) - 5, 12):
                    px, py, pz, rt, taper = run[idx]
                    if taper < 0.25:
                        continue
                    lick_h = size * 0.050 * taper * inten * buf_scale * wispiness
                    lick_w = size * 0.013 * taper * inten * buf_scale
                    drift_x = math.sin(now * 5.5 + idx + r_idx) * lick_w * 0.75
                    lick = [
                        (px * buf_scale, py * buf_scale, lick_w),
                        (px * buf_scale + drift_x * 0.5, py * buf_scale - lick_h * 0.55, lick_w * 0.55),
                        (px * buf_scale + drift_x, py * buf_scale - lick_h, 0.3),
                    ]
                    hp.setBrush(QColor(*c_mid, int(min(255, 120 * min(1.2, inten) * depth_mul * wispiness))))
                    hp.drawPolygon(build_taper_poly(lick))

            if not bloom_overlay:
                for amp_f, freq_f, sp_f, w_f, al_f in (
                    (0.011, 12.0, 6.8, 0.0044, 175),
                    (-0.009, 15.0, 7.9, 0.0036, 155),
                    (0.005, 8.5, 5.4, 0.0030, 140),
                ):
                    fpath = QPainterPath()
                    for si, (px, py, _, rt, taper) in enumerate(run):
                        off = math.sin(rt * freq_f - now * sp_f + r_idx * 2.1) * size * amp_f * taper
                        fx, fy = (px + off) * buf_scale, (py + off * 0.28) * buf_scale
                        if si == 0:
                            fpath.moveTo(fx, fy)
                        else:
                            fpath.lineTo(fx, fy)
                    fp.setPen(QPen(QColor(*c_fil, int(min(255, al_f * min(1.2, inten) * depth_mul))), max(1.0, size * w_f * inten * buf_scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                    fp.drawPath(fpath)

        hp.end()
        fp.end()

        ptr = halo_qimg.constBits()
        pil_halo = Image.frombytes("RGBA", (buf_res, buf_res), bytes(ptr)).filter(ImageFilter.GaussianBlur(radius=4.5))
        halo_pix = pil_to_qpixmap(pil_halo)

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawPixmap(QRectF(-size * 0.5, -size * 0.5, size, size).toRect(), halo_pix)

        if bloom_overlay:
            p.restore()
            return

        # Soft-blurred silky filaments (zero crisp vector edges!)
        fptr = fil_qimg.constBits()
        pil_fil = Image.frombytes("RGBA", (buf_res, buf_res), bytes(fptr)).filter(ImageFilter.GaussianBlur(radius=0.85))
        fil_pix = pil_to_qpixmap(pil_fil)
        p.drawPixmap(QRectF(-size * 0.5, -size * 0.5, size, size).toRect(), fil_pix)

        # Draw crisp tapered mid-body & narrow white-hot core
        for r_idx, is_front, run in vector_runs:
            if back_pass == is_front:
                continue
            c_halo, c_mid, c_fil, c_core = ribbon_palette(r_idx)
            avg_z = sum(pt[2] for pt in run) / max(len(run), 1)
            depth_mul = 0.85 + 0.15 * avg_z
            a_mul = min(1.25, inten) * depth_mul

            body_pts = [
                (px, py, max(0.5, size * 0.017 * taper * inten * (0.85 + 0.15 * pz)))
                for (px, py, pz, _, taper) in run
            ]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(*c_mid, int(min(255, 115 * a_mul))))
            p.drawPolygon(build_taper_poly(body_pts))

            gold_pts = [
                (px, py, max(0.35, size * 0.0082 * taper * inten * (0.85 + 0.15 * pz)))
                for (px, py, pz, _, taper) in run
            ]
            p.setBrush(QColor(*c_fil, int(min(255, 138 * a_mul))))
            p.drawPolygon(build_taper_poly(gold_pts))

            core_pts = [
                (px, py, max(0.0, size * 0.0030 * (taper ** 1.7) * inten * (0.85 + 0.15 * pz)))
                for (px, py, pz, _, taper) in run
            ]
            p.setBrush(QColor(*c_core, int(min(255, 185 * a_mul))))
            p.drawPolygon(build_taper_poly(core_pts))

            for sp_i in range(len(run)):
                if sp_i % 5 != 2:
                    continue
                px, py, _, rt, taper = run[sp_i]
                if taper < 0.2:
                    continue
                p0 = run[max(0, sp_i - 1)]
                p1 = run[min(len(run) - 1, sp_i + 1)]
                dx, dy = p1[0] - p0[0], p1[1] - p0[1]
                ln = max(1e-4, math.hypot(dx, dy))
                ux, uy = dx / ln, dy / ln
                nx, ny = -uy, ux
                phase_sp = (now * 0.7 + sp_i * 0.37 + r_idx * 1.1) % 1.0
                spread = math.sin(sp_i * 4.7 + r_idx) * size * 0.028 * (0.4 + phase_sp)
                sx = px + nx * spread + ux * phase_sp * size * 0.025
                sy = py + ny * spread + uy * phase_sp * size * 0.025 - phase_sp * size * 0.025
                streak = size * (0.015 + 0.012 * (1.0 - phase_sp))
                al_sp = int(min(255, 210 * (1.0 - phase_sp) * taper * min(1.2, inten)))
                p.setPen(QPen(QColor(*c_fil, al_sp), max(1.0, size * 0.0032), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(sx, sy), QPointF(sx + ux * streak, sy + uy * streak))

        p.restore()

    def _draw_fractal_lightning(
        self,
        p: QPainter,
        elem: ElementDef,
        size: float,
        now: float,
        inten: float,
        back_pass: bool,
        arc_count: int = 6,
        jitter: float = 1.0,
        branch_prob: float = 0.55,
    ) -> None:
        """
        Draws a dramatic, large-scale branching fractal lightning network wrapping
        3D-around the weapon with deep Gaussian corona + white-hot core.
        """
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.055, self._result.enchant_half_width)

        y_bot = -(span_x - 0.02) * size
        y_top = -(span_y + 0.015) * size
        rad_x = max(hw_b * 2.25, 0.172) * size * min(1.35, 0.82 + 0.20 * inten) * (0.8 + 0.2 * jitter)

        pr, pg, pb = elem.primary_rgb
        sr, sg, sb = elem.secondary_rgb

        # Store raw point polylines so we can taper width & alpha smoothly toward tips
        main_bolts: list[tuple[list[tuple[float, float]], float]] = []
        branch_bolts: list[tuple[list[tuple[float, float]], float]] = []

        def build_bolt(
            x0: float,
            y0: float,
            x1: float,
            y1: float,
            disp: float,
            depth: int,
            rng: random.Random,
            is_branch: bool,
            alpha_scale: float,
        ) -> None:
            pts: list[tuple[float, float]] = [(x0, y0), (x1, y1)]
            cur_disp = disp
            for d in range(depth):
                nxt: list[tuple[float, float]] = [pts[0]]
                for k in range(len(pts) - 1):
                    ax, ay = pts[k]
                    bx, by = pts[k + 1]
                    dx, dy = bx - ax, by - ay
                    ln = max(1e-4, math.hypot(dx, dy))
                    nx, ny = -dy / ln, dx / ln
                    mx = (ax + bx) * 0.5 + nx * rng.uniform(-cur_disp, cur_disp)
                    my = (ay + by) * 0.5 + ny * rng.uniform(-cur_disp, cur_disp)
                    nxt.append((mx, my))
                    nxt.append((bx, by))

                    if d in (0, 1, 2) and rng.random() < (branch_prob * 0.62 if is_branch else branch_prob):
                        ang = math.atan2(dy, dx) + rng.choice([-1.0, 1.0]) * rng.uniform(0.42, 1.05)
                        blen = ln * rng.uniform(0.55, 1.12) * (0.72 if is_branch else 1.0)
                        if blen > size * 0.012:
                            build_bolt(
                                mx,
                                my,
                                mx + math.cos(ang) * blen,
                                my + math.sin(ang) * blen,
                                cur_disp * 0.55,
                                max(2, depth - d - 1),
                                rng,
                                True,
                                alpha_scale * rng.uniform(0.45, 0.78),
                            )
                pts = nxt
                cur_disp *= 0.56

            if is_branch:
                branch_bolts.append((pts, alpha_scale))
            else:
                main_bolts.append((pts, alpha_scale))

        def draw_tapered_polyline(
            painter: QPainter,
            pts: list[tuple[float, float]],
            base_w: float,
            rgb: tuple[int, int, int],
            base_alpha: float,
            taper_both: bool,
        ) -> None:
            n = len(pts)
            if n < 2:
                return
            # 4 progressive segments with smooth width & alpha fade toward tips
            chunks = 4
            for ci in range(chunks):
                i0 = (ci * (n - 1)) // chunks
                i1 = ((ci + 1) * (n - 1)) // chunks
                if i1 <= i0:
                    continue
                t_mid = (ci + 0.5) / chunks
                t_factor = (math.sin(t_mid * math.pi) ** 0.75) if taper_both else max(0.15, (1.0 - t_mid * 0.82))
                a_val = int(max(0, min(255, base_alpha * (0.35 + 0.65 * t_factor))))
                w_val = max(0.5, base_w * t_factor)
                sub = QPainterPath(QPointF(pts[i0][0], pts[i0][1]))
                for px, py in pts[i0 + 1:i1 + 1]:
                    sub.lineTo(px, py)
                painter.setPen(QPen(QColor(*rgb, a_val), w_val, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                painter.drawPath(sub)

        tick_seed = int(now * 11.0)
        base_specs = [
            (11, 0.00, 0.54, 1.0, False, 0.052),
            (23, 0.06, 0.66, -1.0, True, 0.058),
            (37, 0.28, 0.88, 1.0, True, 0.056),
            (53, 0.40, 0.96, -1.0, False, 0.052),
            (71, 0.14, 0.94, 0.75, True, 0.046),
            (89, 0.02, 0.44, -0.85, True, 0.048),
            (103, 0.22, 0.76, -0.95, False, 0.054),
            (127, 0.48, 0.99, 0.9, True, 0.050),
        ]
        arc_specs = base_specs[:max(2, min(len(base_specs), arc_count))]

        for a_idx, (s_off, t0, t1, x_dir, is_front, d_sc) in enumerate(arc_specs):
            d_sc *= jitter
            if back_pass == is_front:
                continue
            arc_tick = tick_seed + a_idx * 3
            rng = random.Random(arc_tick * 131 + s_off)
            flicker = 0.72 + 0.28 * math.sin(now * 28.0 + a_idx * 2.1)

            tm = (t0 + t1) * 0.5
            env0 = math.sin(t0 * math.pi) ** 0.58
            envm = math.sin(tm * math.pi) ** 0.58
            env1 = math.sin(t1 * math.pi) ** 0.58

            p0 = (
                cx_b + x_dir * rad_x * (0.22 + 0.62 * env0) * rng.uniform(0.75, 1.15),
                y_bot + (y_top - y_bot) * t0,
            )
            pm = (
                cx_b - x_dir * rad_x * (0.62 + 0.42 * envm) * rng.uniform(0.85, 1.22),
                y_bot + (y_top - y_bot) * tm,
            )
            p1 = (
                cx_b + x_dir * rad_x * (0.18 + 0.58 * env1) * rng.uniform(0.70, 1.12),
                y_bot + (y_top - y_bot) * t1,
            )
            build_bolt(p0[0], p0[1], pm[0], pm[1], size * d_sc, 5, rng, False, flicker)
            build_bolt(pm[0], pm[1], p1[0], p1[1], size * d_sc, 5, rng, False, flicker)

        if not main_bolts and not branch_bolts:
            return

        # 1) Padded 240x240 Gaussian corona buffer (size * 1.22 prevents any top/side clipping!)
        buf_res = 240
        pad_size = size * 1.22
        buf_scale = buf_res / max(pad_size, 1.0)
        corona_qimg = QImage(buf_res, buf_res, QImage.Format.Format_RGBA8888)
        corona_qimg.fill(QColor(0, 0, 0, 0))
        cp = QPainter(corona_qimg)
        cp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cp.translate(buf_res * 0.5, buf_res * 0.5)
        cp.scale(buf_scale, buf_scale)
        cp.setBrush(Qt.BrushStyle.NoBrush)

        a_inten = min(1.45, inten)
        for pts, al in main_bolts:
            draw_tapered_polyline(cp, pts, max(4.2, size * 0.020 * inten), (pr, pg, pb), 205 * al * a_inten, taper_both=True)
        for pts, al in branch_bolts:
            draw_tapered_polyline(cp, pts, max(2.4, size * 0.012 * inten), (pr, pg, pb), 165 * al * a_inten, taper_both=False)
        cp.end()

        cptr = corona_qimg.constBits()
        pil_corona = Image.frombytes("RGBA", (buf_res, buf_res), bytes(cptr)).filter(ImageFilter.GaussianBlur(radius=4.8))
        corona_pix = pil_to_qpixmap(pil_corona)

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        corona_rect = QRectF(-pad_size * 0.5, -pad_size * 0.5, pad_size, pad_size).toRect()
        p.drawPixmap(corona_rect, corona_pix)
        p.setOpacity(0.32 * min(1.25, inten))
        p.drawPixmap(corona_rect, corona_pix)
        p.setOpacity(1.0)

        # 2) Tapered mid electric blue-cyan arcs + crisp pure-white cores (no blunt tips!)
        p.setBrush(Qt.BrushStyle.NoBrush)
        mid_col = (min(255, pr + 65), min(255, pg + 65), 255)
        for pts, al in branch_bolts:
            draw_tapered_polyline(p, pts, max(1.1, size * 0.0028 * inten), mid_col, 150 * al * a_inten, taper_both=False)
            draw_tapered_polyline(p, pts, max(0.7, size * 0.0014), (sr, sg, sb), 185 * al * a_inten, taper_both=False)

        for pts, al in main_bolts:
            draw_tapered_polyline(p, pts, max(1.8, size * 0.0048 * inten), mid_col, 200 * al * a_inten, taper_both=True)
            draw_tapered_polyline(p, pts, max(1.0, size * 0.0023 * min(1.35, inten)), (255, 255, 255), 240 * al * a_inten, taper_both=True)

        p.restore()

    def _get_custom_effect_pixmap(self, rel_path: str, keep_colors: bool, tint_rgb: Tuple[int, int, int]) -> Optional[QPixmap]:
        if self._store is None or not rel_path:
            return None
        key = (rel_path, keep_colors, tint_rgb if not keep_colors else None)
        if key in self._custom_img_cache:
            return self._custom_img_cache[key]
        pil = self._store.get_effect_pil(rel_path)
        if pil is None:
            return None
        if not keep_colors:
            # Tint luminance with tint_rgb while keeping original alpha
            arr = np.asarray(pil.convert("RGBA"), dtype=np.float32)
            lum = np.max(arr[:, :, :3], axis=2) / 255.0
            out = np.zeros_like(arr, dtype=np.uint8)
            out[:, :, 0] = np.clip(lum * tint_rgb[0], 0, 255).astype(np.uint8)
            out[:, :, 1] = np.clip(lum * tint_rgb[1], 0, 255).astype(np.uint8)
            out[:, :, 2] = np.clip(lum * tint_rgb[2], 0, 255).astype(np.uint8)
            out[:, :, 3] = arr[:, :, 3].astype(np.uint8)
            pil = Image.fromarray(out, "RGBA")
        pix = pil_to_qpixmap(pil)
        self._custom_img_cache[key] = pix
        return pix

    def _draw_custom_layers(
        self,
        p: QPainter,
        elem: ElementDef,
        size: float,
        now: float,
        inten: float,
        back_pass: bool,
    ) -> None:
        """Renders modular, no-code VFX layers (imported images + procedural swirls/bolts/particles)."""
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.05, self._result.enchant_half_width)
        blade_mid_y = -((span_x + span_y) * 0.5) * size
        blade_h = max(0.2, (span_y - span_x)) * size
        anchors = self._result.preview_anchors

        for layer in elem.layers:
            if not layer.get("enabled", True):
                continue
            ltype = layer.get("layer_type", "image_overlay")
            pr = tuple(layer.get("primary_rgb", elem.primary_rgb))
            sr = tuple(layer.get("secondary_rgb", elem.secondary_rgb))
            sc = float(layer.get("scale", 1.0))
            spd = float(layer.get("speed", 1.0))
            op = float(layer.get("opacity", 1.0)) * inten
            cnt = int(layer.get("count", 10))
            direction = layer.get("direction", "pulse")
            shape = layer.get("shape", "ember")
            behind = bool(layer.get("behind_weapon", False))
            off_y = float(layer.get("offset_y", 0.0)) * size

            if ltype == "ribbon":
                tmp_e = ElementDef(elem.id, elem.key, elem.name, "", "", 0, "", [], pr, sr, "flame")
                turns_val = float(layer.get("turns", 1.2))
                wisp_val = float(layer.get("wispiness", 1.0))
                rc = max(1, min(4, cnt if cnt <= 4 else 2))
                self._draw_helical_flame_ribbons(
                    p, tmp_e, size, now * spd, op * sc * 0.85,
                    back_pass=back_pass, bloom_overlay=False,
                    ribbon_count=rc, turns=turns_val, wispiness=wisp_val, spread=sc,
                )
                if not back_pass:
                    self._draw_helical_flame_ribbons(
                        p, tmp_e, size, now * spd, op * sc * 0.85,
                        back_pass=False, bloom_overlay=True,
                        ribbon_count=rc, turns=turns_val, wispiness=wisp_val, spread=sc,
                    )
                continue

            if ltype == "lightning":
                tmp_e = ElementDef(elem.id, elem.key, elem.name, "", "", 0, "", [], pr, sr, "thunder")
                jit = float(layer.get("turns", 1.0))
                bprob = max(0.15, min(0.8, float(layer.get("wispiness", 0.55))))
                ac = max(2, min(8, cnt))
                self._draw_fractal_lightning(
                    p, tmp_e, size, now * spd, op * sc * 0.9, back_pass=back_pass,
                    arc_count=ac, jitter=jit, branch_prob=bprob,
                )
                continue

            if ltype == "slashes":
                self._draw_crescent_slashes(p, size, now * spd, op, sc, cnt, pr, sr, back_pass)
                continue

            if ltype == "smoke":
                self._draw_volumetric_smoke(p, size, now * spd, op, sc, cnt, pr, sr, direction, back_pass)
                continue

            if ltype == "azure_jet":
                self._draw_azure_jet(p, size, now * spd, op, sc, pr, sr, back_pass)
                continue

            if ltype == "ember_tendrils":
                self._draw_ember_tendrils(p, size, now * spd, op, sc, pr, sr, back_pass)
                continue

            if ltype == "sonic_slash":
                self._draw_sonic_ripples(p, size, now * spd, op, sc, pr, sr, back_pass)
                continue

            if ltype == "ice_armor":
                self._draw_ice_armor(p, size, now * spd, op, sc, pr, sr, back_pass)
                continue

            if ltype == "plasma_web":
                self._draw_plasma_web(p, size, now * spd, op, sc, pr, sr, back_pass)
                continue

            if ltype == "water_sheath":
                self._draw_water_sheath(p, size, now * spd, op, sc, pr, sr, back_pass)
                continue

            if ltype == "eclipse_flare":
                self._draw_eclipse_flare(p, size, now * spd, op, sc, pr, sr, back_pass)
                continue

            if ltype == "shadow_strife":
                self._draw_shadow_strife(p, size, now * spd, op, sc, pr, sr, back_pass)
                continue

            if ltype == "eternal_alpha":
                self._draw_eternal_alpha(p, size, now * spd, op, sc, pr, sr, back_pass)
                continue

            if ltype == "nova_burn":
                self._draw_nova_burn(p, size, now * spd, op, sc, pr, sr, back_pass)
                continue

            if ltype == "abyssal_miasma":
                self._draw_abyssal_miasma(p, size, now * spd, op, sc, pr, sr, back_pass)
                continue

            if ltype == "ink_void":
                self._draw_ink_void(p, size, now * spd, op, sc, pr, sr, back_pass)
                continue

            if ltype == "rings":
                # True 3D depth-split rings around the blade
                p.save()
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
                n_rings = max(1, min(6, cnt))
                for r_i in range(n_rings):
                    age = (now * 0.65 * spd + r_i / float(n_rings)) % 1.0
                    ly = -(span_x + (span_y - span_x) * (0.20 + 0.62 * (r_i / max(1.0, n_rings)))) * size + off_y
                    rad = size * (0.045 + 0.145 * (age if direction != "inward" else (1.0 - age))) * sc
                    al = int(enchantment_fade(age) * 215 * min(1.25, op))
                    ring_rect = QRectF(cx_b - rad, ly - rad * 0.42, rad * 2.0, rad * 0.84)
                    # Rear half in back_pass (0..180 deg in Qt), Front half in front_pass (180..360 deg)
                    start_ang = 0 * 16 if back_pass else 180 * 16
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(QPen(QColor(*pr, int(al * 0.45)), max(3.5, size * 0.012 * sc)))
                    p.drawArc(ring_rect, start_ang, 180 * 16)
                    p.setPen(QPen(QColor(*sr, al), max(1.4, size * 0.004 * sc)))
                    p.drawArc(ring_rect, start_ang, 180 * 16)
                p.restore()
                continue

            # Non-3D layers draw either in back_pass or front_pass
            if back_pass != behind:
                continue

            p.save()
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

            if ltype == "image_overlay":
                pix = self._get_custom_effect_pixmap(
                    layer.get("image_rel_path", ""),
                    bool(layer.get("keep_image_colors", True)),
                    pr,
                )
                if pix is not None and not pix.isNull():
                    pw, ph = pix.width(), pix.height()
                    aspect = pw / max(1.0, float(ph))
                    draw_h = blade_h * 1.18 * sc
                    draw_w = draw_h * aspect
                    cy_draw = blade_mid_y + off_y
                    p.setOpacity(max(0.0, min(1.0, op)))

                    if direction == "flow_up":
                        # Two overlapping vertical-scrolling copies faded smoothly near top/bottom
                        for copy_i in range(2):
                            age = (now * 0.55 * spd + copy_i * 0.5) % 1.0
                            fade = enchantment_fade(age)
                            y_shift = (0.5 - age) * blade_h * 0.65
                            p.save()
                            p.setOpacity(max(0.0, min(1.0, op * fade * 1.15)))
                            p.translate(cx_b, cy_draw + y_shift)
                            p.scale(1.0 + 0.04 * math.sin(now * 3.0 * spd), 1.0)
                            p.drawPixmap(QRectF(-draw_w * 0.5, -draw_h * 0.5, draw_w, draw_h).toRect(), pix)
                            p.restore()
                    elif direction == "spin":
                        p.translate(cx_b, cy_draw)
                        p.rotate((now * 55.0 * spd) % 360.0)
                        s_breathe = 1.0 + 0.06 * math.sin(now * 2.5 * spd)
                        p.scale(s_breathe, s_breathe)
                        p.drawPixmap(QRectF(-draw_w * 0.5, -draw_h * 0.5, draw_w, draw_h).toRect(), pix)
                    elif direction == "wrap":
                        # 3D swaying wrap effect
                        wob = math.sin(now * 2.4 * spd)
                        p.translate(cx_b + wob * size * 0.015, cy_draw)
                        p.rotate(wob * 8.0)
                        p.scale(0.88 + 0.16 * math.cos(now * 2.4 * spd), 1.0 + 0.05 * math.sin(now * 3.2 * spd))
                        p.drawPixmap(QRectF(-draw_w * 0.5, -draw_h * 0.5, draw_w, draw_h).toRect(), pix)
                    else:  # "pulse"
                        breathe = 1.0 + 0.07 * math.sin(now * 3.2 * spd)
                        p.setOpacity(max(0.0, min(1.0, op * (0.82 + 0.18 * math.sin(now * 4.0 * spd)))))
                        p.translate(cx_b, cy_draw)
                        p.rotate(math.sin(now * 1.8 * spd) * 3.5)
                        p.scale(breathe, breathe)
                        p.drawPixmap(QRectF(-draw_w * 0.5, -draw_h * 0.5, draw_w, draw_h).toRect(), pix)

            elif ltype in ("image_particles", "particles"):
                pix = None
                if ltype == "image_particles":
                    pix = self._get_custom_effect_pixmap(
                        layer.get("image_rel_path", ""),
                        bool(layer.get("keep_image_colors", True)),
                        pr,
                    )
                for i in range(max(1, cnt)):
                    clk = now * 0.78 * spd + i / float(max(1, cnt))
                    age = clk % 1.0
                    if anchors:
                        lx, ly = anchors[(i * 5 + int(math.floor(clk)) * 11) % len(anchors)]
                    else:
                        lx, ly = self._result.enchant_center_x, (span_x + span_y) * 0.5
                    if direction == "up":
                        ly += age * 0.09
                        lx += math.sin(now * 4.0 * spd + i) * 0.02
                    elif direction == "down":
                        ly -= age * 0.09
                        lx += math.sin(now * 3.0 * spd + i * 1.5) * 0.035
                    elif direction == "inward":
                        ly = ly * (1.0 - age * 0.5) + (self._result.socket_gem_y_norm - 0.5) * (age * 0.5)
                        lx *= (1.0 - age * 0.5)
                    else:  # orbit
                        ang = now * 2.5 * spd + i * (2.0 * math.pi / max(1, cnt))
                        lx += math.cos(ang) * 0.055
                        ly += math.sin(ang) * 0.035

                    px, py = lx * size, -ly * size + off_y
                    alpha = max(0.0, min(1.0, enchantment_fade(age) * op))
                    p_sz = max(0.05, min(0.14, hw_b * 1.5)) * sc * (1.0 - 0.25 * age) * size

                    if ltype == "image_particles" and pix is not None:
                        p.save()
                        p.setOpacity(alpha)
                        p.translate(px, py)
                        p.rotate((now * 45.0 * spd + i * 35.0) % 360.0)
                        p.drawPixmap(QRectF(-p_sz * 0.5, -p_sz * 0.5, p_sz, p_sz).toRect(), pix)
                        p.restore()
                    elif ltype == "particles":
                        p.save()
                        p.translate(px, py)
                        if shape == "petal":
                            p.rotate((now * 70.0 * spd + i * 42.0) % 360.0)
                            p.setPen(Qt.PenStyle.NoPen)
                            p.setBrush(QColor(*pr, int(alpha * 225)))
                            p.drawEllipse(QPointF(0, 0), p_sz * 0.30, p_sz * 0.15)
                        elif shape == "crystal":
                            p.rotate(45.0 + now * 25.0 * spd + i * 30.0)
                            p.setPen(QPen(QColor(*sr, int(alpha * 220)), 1.3))
                            p.setBrush(QColor(*pr, int(alpha * 110)))
                            d = p_sz * 0.26
                            p.drawRect(QRectF(-d, -d, d * 2, d * 2))
                        elif shape == "star":
                            sp = self._get_tinted_sparkle(pr)
                            if sp is not None:
                                p.setOpacity(alpha)
                                p.rotate((now * 40.0 * spd + i * 25.0) % 360.0)
                                p.drawPixmap(QRectF(-p_sz * 0.5, -p_sz * 0.5, p_sz, p_sz).toRect(), sp)
                        else:  # ember / orb / bubble
                            grad_e = QRadialGradient(QPointF(0, 0), p_sz * 0.32)
                            grad_e.setColorAt(0.0, QColor(*sr, int(alpha * 235)))
                            grad_e.setColorAt(0.5, QColor(*pr, int(alpha * 180)))
                            grad_e.setColorAt(1.0, QColor(*pr, 0))
                            p.setPen(Qt.PenStyle.NoPen)
                            p.setBrush(QBrush(grad_e))
                            p.drawEllipse(QPointF(0, 0), p_sz * 0.32, p_sz * 0.32)
                        p.restore()

            elif ltype == "rings":
                for r_i in range(max(1, min(6, cnt))):
                    age = (now * 0.65 * spd + r_i / float(max(1, min(6, cnt)))) % 1.0
                    ly = -(span_x + (span_y - span_x) * (0.25 + 0.55 * (r_i / max(1.0, min(6, cnt))))) * size + off_y
                    rad = size * (0.04 + 0.14 * (age if direction != "inward" else (1.0 - age))) * sc
                    al = int(enchantment_fade(age) * 195 * min(1.2, op))
                    p.setPen(QPen(QColor(*pr, al), 2.2))
                    p.setBrush(QColor(*sr, int(al * 0.18)))
                    p.drawEllipse(QPointF(cx_b, ly), rad, rad * 0.55)

            elif ltype == "rays":
                p.translate(cx_b, blade_mid_y + off_y)
                p.rotate(now * 22.0 * spd)
                n_rays = max(4, min(16, cnt))
                for ray in range(n_rays):
                    p.rotate(360.0 / n_rays)
                    ray_len = size * (0.14 + 0.04 * math.sin(now * 3.0 * spd + ray)) * sc
                    p.setPen(QPen(QColor(*sr, int(min(255, 115 * op))), 2.2))
                    p.drawLine(QPointF(0, 0), QPointF(0, -ray_len))

            p.restore()

    def _draw_crescent_slashes(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        count: int,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Draws glowing 3D crescent energy slashes orbiting/sweeping across the blade."""
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.055, self._result.enchant_half_width)
        y_bot = -(span_x + 0.02) * size
        y_top = -(span_y + 0.03) * size

        n_slashes = max(1, min(6, count))
        buf_res = 224
        pad_size = size * 1.18
        buf_scale = buf_res / max(pad_size, 1.0)

        halo_qimg = QImage(buf_res, buf_res, QImage.Format.Format_RGBA8888)
        halo_qimg.fill(QColor(0, 0, 0, 0))
        hp = QPainter(halo_qimg)
        hp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        hp.translate(buf_res * 0.5, buf_res * 0.5)
        hp.scale(buf_scale, buf_scale)
        hp.setPen(Qt.PenStyle.NoPen)

        slash_polys: list[tuple[QPolygonF, QPolygonF, float]] = []
        for s_i in range(n_slashes):
            clk = now * 0.85 + s_i / float(n_slashes)
            age = clk % 1.0
            # Alternate depth cleanly
            is_front = (s_i % 2 == 0)
            if back_pass == is_front:
                continue
            fade = enchantment_fade(age)
            if fade <= 0.03:
                continue

            cy = y_bot + (y_top - y_bot) * (0.20 + 0.72 * ((s_i * 0.37 + age * 0.45) % 1.0))
            rad = max(hw_b * 2.1, 0.165) * size * scale * (0.75 + 0.45 * age)
            sweep_start = (-1.1 + s_i * 1.4 + age * 1.8)
            tilt = 0.38 if (s_i % 2 == 0) else -0.35

            n_pts = 28
            outer_pts: list[QPointF] = []
            inner_pts: list[QPointF] = []
            core_outer: list[QPointF] = []
            core_inner: list[QPointF] = []
            for k in range(n_pts + 1):
                u = k / float(n_pts)
                ang = sweep_start + (u - 0.5) * 2.35
                taper = math.sin(u * math.pi) ** 0.85
                ox = cx_b + math.cos(ang) * rad
                oy = cy + math.sin(ang) * rad * 0.42 + math.cos(ang) * rad * tilt * 0.35
                w_cres = size * 0.026 * scale * taper
                c_cres = size * 0.008 * scale * taper
                nx, ny = math.cos(ang), math.sin(ang)
                outer_pts.append(QPointF(ox + nx * w_cres * 0.3, oy + ny * w_cres * 0.3))
                inner_pts.append(QPointF(ox - nx * w_cres * 0.7, oy - ny * w_cres * 0.7))
                core_outer.append(QPointF(ox + nx * c_cres * 0.3, oy + ny * c_cres * 0.3))
                core_inner.append(QPointF(ox - nx * c_cres * 0.7, oy - ny * c_cres * 0.7))

            poly_body = QPolygonF(outer_pts + list(reversed(inner_pts)))
            poly_core = QPolygonF(core_outer + list(reversed(core_inner)))
            hp.setBrush(QColor(*pr, int(min(255, 200 * fade * min(1.3, inten)))))
            hp.drawPolygon(poly_body)
            slash_polys.append((poly_body, poly_core, fade))

        hp.end()
        if not slash_polys:
            return

        ptr = halo_qimg.constBits()
        pil_halo = Image.frombytes("RGBA", (buf_res, buf_res), bytes(ptr)).filter(ImageFilter.GaussianBlur(radius=4.5))
        halo_pix = pil_to_qpixmap(pil_halo)

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawPixmap(QRectF(-pad_size * 0.5, -pad_size * 0.5, pad_size, pad_size).toRect(), halo_pix)
        p.setPen(Qt.PenStyle.NoPen)
        for poly_b, poly_c, fade in slash_polys:
            p.setBrush(QColor(*pr, int(min(255, 135 * fade * min(1.3, inten)))))
            p.drawPolygon(poly_b)
            p.setBrush(QColor(*sr, int(min(255, 235 * fade * min(1.3, inten)))))
            p.drawPolygon(poly_c)
        p.restore()

    def _draw_volumetric_smoke(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        count: int,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        direction: str,
        back_pass: bool,
    ) -> None:
        """Draws rising/swirling Gaussian-blurred volumetric mist/miasma/plasma around the blade."""
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.05, self._result.enchant_half_width)
        y_bot = -(span_x + 0.01) * size
        y_top = -(span_y + 0.04) * size

        buf_res = 200
        pad_size = size * 1.18
        buf_scale = buf_res / max(pad_size, 1.0)
        qimg = QImage(buf_res, buf_res, QImage.Format.Format_RGBA8888)
        qimg.fill(QColor(0, 0, 0, 0))
        sp = QPainter(qimg)
        sp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        sp.translate(buf_res * 0.5, buf_res * 0.5)
        sp.scale(buf_scale, buf_scale)
        sp.setPen(Qt.PenStyle.NoPen)

        n_puffs = max(4, min(20, count))
        drawn = 0
        for i in range(n_puffs):
            is_front = (i % 3 == 0)
            if back_pass == is_front:
                continue
            age = (now * 0.42 + i / float(n_puffs)) % 1.0
            fade = enchantment_fade(age)
            if fade <= 0.02:
                continue
            t_y = age if direction != "down" else (1.0 - age)
            py = y_bot + (y_top - y_bot) * t_y
            swirl_x = math.sin(now * 2.2 + i * 1.7 + t_y * 4.5) * max(hw_b * 1.4, 0.095) * size * scale
            px = cx_b + swirl_x
            rx = size * (0.045 + 0.055 * math.sin(t_y * math.pi)) * scale
            ry = rx * 1.35
            col = sr if (i % 3 == 1) else pr
            sp.setBrush(QColor(*col, int(min(255, 130 * fade * min(1.3, inten)))))
            sp.drawEllipse(QPointF(px, py), rx, ry)
            drawn += 1

        sp.end()
        if drawn == 0:
            return
        ptr = qimg.constBits()
        pil_sm = Image.frombytes("RGBA", (buf_res, buf_res), bytes(ptr)).filter(ImageFilter.GaussianBlur(radius=7.5))
        sm_pix = pil_to_qpixmap(pil_sm)

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawPixmap(QRectF(-pad_size * 0.5, -pad_size * 0.5, pad_size, pad_size).toRect(), sm_pix)
        p.restore()

    def _dispatch_builtin_style(
        self,
        p: QPainter,
        elem: ElementDef,
        size: float,
        now: float,
        inten: float,
        back_pass: bool,
    ) -> None:
        st = elem.vfx_style
        pr, sr = elem.primary_rgb, elem.secondary_rgb
        if st in ("flame", "magma", "frostfire"):
            self._draw_helical_flame_ribbons(p, elem, size, now, inten, back_pass=back_pass, bloom_overlay=False)
            if not back_pass:
                self._draw_helical_flame_ribbons(p, elem, size, now, inten, back_pass=False, bloom_overlay=True)
        elif st == "thunder":
            self._draw_fractal_lightning(p, elem, size, now, inten, back_pass=back_pass)
        elif st == "azure_jet":
            self._draw_azure_jet(p, size, now, inten, 1.0, pr, sr, back_pass)
        elif st == "ember_tendrils":
            self._draw_ember_tendrils(p, size, now, inten, 1.0, pr, sr, back_pass)
        elif st == "sonic_slash":
            self._draw_sonic_ripples(p, size, now, inten, 1.0, pr, sr, back_pass)
        elif st == "ice_armor":
            self._draw_ice_armor(p, size, now, inten, 1.0, pr, sr, back_pass)
        elif st == "plasma_web":
            self._draw_plasma_web(p, size, now, inten, 1.0, pr, sr, back_pass)
        elif st == "water_sheath":
            self._draw_water_sheath(p, size, now, inten, 1.0, pr, sr, back_pass)
        elif st == "eclipse_flare":
            self._draw_eclipse_flare(p, size, now, inten, 1.0, pr, sr, back_pass)
        elif st == "shadow_strife":
            self._draw_shadow_strife(p, size, now, inten, 1.0, pr, sr, back_pass)
        elif st == "eternal_alpha":
            self._draw_eternal_alpha(p, size, now, inten, 1.0, pr, sr, back_pass)
        elif st == "nova_burn":
            self._draw_nova_burn(p, size, now, inten, 1.0, pr, sr, back_pass)
        elif st == "abyssal_miasma":
            self._draw_abyssal_miasma(p, size, now, inten, 1.0, pr, sr, back_pass)
        elif st == "ink_void":
            self._draw_ink_void(p, size, now, inten, 1.0, pr, sr, back_pass)

    def _draw_azure_jet(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Image 1: Roaring directional cyan-blue flame jet along blade + spiky guard flare wings."""
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.05, self._result.enchant_half_width)
        gem_y = (0.5 - self._result.socket_gem_y_norm) * size
        y_bot = -span_x * size
        y_top = max(-size * 0.45, -(span_y + 0.045 * scale) * size)

        buf_res = 240
        pad_size = size * 1.24
        buf_scale = buf_res / max(pad_size, 1.0)
        qimg = QImage(buf_res, buf_res, QImage.Format.Format_RGBA8888)
        qimg.fill(QColor(0, 0, 0, 0))
        jp = QPainter(qimg)
        jp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        jp.translate(buf_res * 0.5, buf_res * 0.5)
        jp.scale(buf_scale, buf_scale)
        jp.setPen(Qt.PenStyle.NoPen)

        a_in = min(1.30, inten)
        if back_pass:
            # Smooth continuous flame plume shooting up along & slightly past blade tip
            for s_i, (w_mul, col, al) in enumerate([
                (1.90, pr, 130),
                (1.25, pr, 185),
                (0.62, sr, 200),
            ]):
                pts_l, pts_r = [], []
                for k in range(36):
                    t = k / 35.0
                    py = y_bot + (y_top - y_bot) * t
                    wave = math.sin(t * 7.5 - now * 10.5 + s_i) * hw_b * 0.25 * size * math.sin(t * math.pi)
                    taper_w = ((1.0 - t) ** 0.85) * (0.75 + 0.35 * math.sin(t * math.pi))
                    w_half = max(0.2, hw_b * size * scale * w_mul * taper_w)
                    pts_l.append(QPointF(cx_b + wave - w_half, py))
                    pts_r.append(QPointF(cx_b + wave + w_half, py))
                jp.setBrush(QColor(*col, int(min(255, al * a_in))))
                jp.drawPolygon(QPolygonF(pts_l + list(reversed(pts_r))))
        else:
            # Spiky anime guard flame flares erupting left & right of crossguard
            for side in (-1.0, 1.0):
                flare = QPainterPath(QPointF(cx_b + side * size * 0.015, gem_y + size * 0.01))
                spikes = [(0.055, 0.035), (0.095, -0.02), (0.068, -0.045), (0.125, -0.075), (0.075, -0.085), (0.105, -0.135), (0.035, -0.085)]
                for k_i, (sx, sy) in enumerate(spikes):
                    jit = 1.0 + 0.14 * math.sin(now * 9.5 + k_i * 1.7 + side)
                    flare.lineTo(cx_b + side * sx * size * scale * jit, gem_y + sy * size * scale * jit)
                flare.closeSubpath()
                jp.setBrush(QColor(*pr, int(min(255, 190 * a_in))))
                jp.drawPath(flare)
                jp.setBrush(QColor(*sr, int(min(255, 145 * a_in))))
                jp.drawEllipse(QPointF(cx_b + side * size * 0.03, gem_y - size * 0.015), size * 0.035, size * 0.025)

        jp.end()
        ptr = qimg.constBits()
        pil_blur = Image.frombytes("RGBA", (buf_res, buf_res), bytes(ptr)).filter(ImageFilter.GaussianBlur(radius=3.8 if back_pass else 1.8))
        pix = pil_to_qpixmap(pil_blur)

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawPixmap(QRectF(-pad_size * 0.5, -pad_size * 0.5, pad_size, pad_size).toRect(), pix)
        p.restore()

    def _draw_ember_tendrils(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Image 2: Thin glowing ember rim + guard ring + dark broken curling ember tendrils."""
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.05, self._result.enchant_half_width)
        gem_y = (0.5 - self._result.socket_gem_y_norm) * size
        y_bot = -span_x * size
        y_top = -span_y * size

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        # Tilted glowing guard ring (rear half in back_pass, front half in front_pass)
        ring_w = max(hw_b * 1.9, 0.13) * size * scale
        ring_rect = QRectF(cx_b - ring_w * 0.5, gem_y - ring_w * 0.16, ring_w, ring_w * 0.32)
        start_ang = 0 * 16 if back_pass else 180 * 16
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(*pr, int(min(255, 165 * inten))), max(2.5, size * 0.008)))
        p.drawArc(ring_rect, start_ang, 180 * 16)
        p.setPen(QPen(QColor(*sr, int(min(255, 225 * inten))), max(1.1, size * 0.003)))
        p.drawArc(ring_rect, start_ang, 180 * 16)

        if back_pass:
            # Tapered glowing ember tendrils curling upward off blade
            buf_res = 240
            pad_size = size * 1.22
            buf_scale = buf_res / max(pad_size, 1.0)
            qimg = QImage(buf_res, buf_res, QImage.Format.Format_RGBA8888)
            qimg.fill(QColor(0, 0, 0, 0))
            tp = QPainter(qimg)
            tp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            tp.translate(buf_res * 0.5, buf_res * 0.5)
            tp.scale(buf_scale, buf_scale)
            tp.setBrush(Qt.BrushStyle.NoBrush)

            tendril_pts_list: list[tuple[list[tuple[float, float]], float]] = []
            for i in range(14):
                age = (now * 0.34 + i / 14.0) % 1.0
                fade = enchantment_fade(age)
                side = 1.0 if (i % 2 == 0) else -1.0
                t_start = 0.06 + 0.84 * ((i * 0.31) % 1.0)
                y0 = y_bot + (y_top - y_bot) * t_start - age * size * 0.035
                x0 = cx_b + side * hw_b * 0.45 * size
                t_pts: list[tuple[float, float]] = [(x0, y0)]
                cur_x, cur_y = x0, y0
                rng = random.Random(i * 47 + 7)
                ang_cur = -math.pi * 0.5 + side * rng.uniform(0.35, 0.95)
                for seg in range(7):
                    ang_cur += side * rng.uniform(-0.45, 0.55) + math.sin(now * 2.8 + i + seg) * 0.22
                    step_l = rng.uniform(0.012, 0.026) * size * scale
                    cur_x += math.cos(ang_cur) * step_l
                    cur_y += math.sin(ang_cur) * step_l
                    t_pts.append((cur_x, cur_y))
                # Draw tapered glow in buffer
                for si in range(len(t_pts) - 1):
                    tf = 1.0 - si / float(len(t_pts))
                    tp.setPen(QPen(QColor(*pr, int(min(255, 210 * fade * inten * tf))), max(1.0, size * 0.011 * tf), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    tp.drawLine(QPointF(*t_pts[si]), QPointF(*t_pts[si + 1]))
                tendril_pts_list.append((t_pts, fade))
            tp.end()

            ptr = qimg.constBits()
            pil_t = Image.frombytes("RGBA", (buf_res, buf_res), bytes(ptr)).filter(ImageFilter.GaussianBlur(radius=3.4))
            p.drawPixmap(QRectF(-pad_size * 0.5, -pad_size * 0.5, pad_size, pad_size).toRect(), pil_to_qpixmap(pil_t))
            for t_pts, fade in tendril_pts_list:
                for si in range(len(t_pts) - 1):
                    tf = 1.0 - si / float(len(t_pts))
                    p.setPen(QPen(QColor(*sr, int(min(255, 210 * fade * inten * tf))), max(0.6, size * 0.0026 * tf), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    p.drawLine(QPointF(*t_pts[si]), QPointF(*t_pts[si + 1]))

        p.restore()

    def _draw_sonic_ripples(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Image 3: Monochrome high-contrast silver/ink guard shockwave ripples + tapered crescent & speed needles."""
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.05, self._result.enchant_half_width)
        gem_y = (0.5 - self._result.socket_gem_y_norm) * size
        mid_y = -((span_x + span_y) * 0.52) * size

        # Build tapered crescent slash & needle shapes once so we can render both soft bloom & crisp highlights
        crescent_poly: Optional[QPolygonF] = None
        needles: list[tuple[QPolygonF, float]] = []
        if not back_pass:
            arc_r = max(hw_b * 2.5, 0.21) * size * scale
            cy_arc = mid_y
            base_ang = math.radians(65.0 + math.sin(now * 2.0) * 16.0)
            arc_span = math.radians(150.0)
            outer_pts: list[QPointF] = []
            inner_pts: list[QPointF] = []
            n_seg = 24
            for k in range(n_seg + 1):
                t = k / float(n_seg)
                th = base_ang + arc_span * t
                taper = math.sin(t * math.pi) ** 1.15
                rx_o = arc_r * (1.0 + 0.04 * taper)
                ry_o = arc_r * 0.78 * (1.0 + 0.04 * taper)
                rx_i = arc_r * (1.0 - 0.11 * taper)
                ry_i = arc_r * 0.78 * (1.0 - 0.11 * taper)
                outer_pts.append(QPointF(cx_b + math.cos(th) * rx_o, cy_arc - math.sin(th) * ry_o))
                inner_pts.append(QPointF(cx_b + math.cos(th) * rx_i, cy_arc - math.sin(th) * ry_i))
            crescent_poly = QPolygonF(outer_pts + list(reversed(inner_pts)))

            for n_i in range(8):
                ang = (n_i * (math.pi / 4.0)) + 0.32 + math.sin(now * 1.8 + n_i) * 0.08
                r0 = size * (0.065 + 0.045 * ((now * 1.6 + n_i * 0.23) % 1.0)) * scale
                r1 = r0 + size * (0.19 + 0.08 * (n_i % 2)) * scale
                rm = r0 + (r1 - r0) * 0.28
                nx = -math.sin(ang)
                ny = math.cos(ang)
                half_w = max(1.1, size * (0.0042 + 0.0014 * (n_i % 2))) * scale
                poly = QPolygonF([
                    QPointF(cx_b + math.cos(ang) * r0, mid_y + math.sin(ang) * r0),
                    QPointF(cx_b + math.cos(ang) * rm + nx * half_w, mid_y + math.sin(ang) * rm + ny * half_w),
                    QPointF(cx_b + math.cos(ang) * r1, mid_y + math.sin(ang) * r1),
                    QPointF(cx_b + math.cos(ang) * rm - nx * half_w, mid_y + math.sin(ang) * rm - ny * half_w),
                ])
                al = 0.55 + 0.45 * math.sin(now * 5.0 + n_i)
                needles.append((poly, al))

            # Render soft monochrome silver bloom into 224x224 buffer
            res = 224
            buf = QImage(res, res, QImage.Format.Format_RGBA8888)
            buf.fill(QColor(0, 0, 0, 0))
            bp = QPainter(buf)
            bp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            bp.translate(res * 0.5, res * 0.5)
            s_fac = res / max(1.0, size)
            bp.scale(s_fac, s_fac)
            bp.setPen(Qt.PenStyle.NoPen)
            bp.setBrush(QColor(*sr, int(min(255, 195 * inten))))
            if crescent_poly is not None:
                bp.drawPolygon(crescent_poly)
            for poly, al in needles:
                bp.setBrush(QColor(*sr, int(min(255, 175 * inten * al))))
                bp.drawPolygon(poly)
            bp.end()
            glow_img = Image.frombytes("RGBA", (res, res), bytes(buf.constBits())).filter(ImageFilter.GaussianBlur(radius=3.2))
            glow_pix = pil_to_qpixmap(glow_img)

        p.save()
        # Concentric ink-and-silver guard ripples
        start_ang = 0 * 16 if back_pass else 180 * 16
        for r_i in range(2):
            age = (now * 1.1 + r_i * 0.5) % 1.0
            fade = enchantment_fade(age)
            pulse_r = (0.86 + 0.24 * age) * scale
            rw = size * (0.13 + 0.085 * r_i) * pulse_r
            rh = rw * 0.34
            rect = QRectF(cx_b - rw * 0.5, gem_y - rh * 0.5, rw, rh)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(15, 18, 22, int(205 * (0.45 + 0.55 * fade))), max(3.2, size * 0.010)))
            p.drawArc(rect, start_ang, 180 * 16)
            p.setPen(QPen(QColor(*sr, int(min(255, 235 * inten * (0.4 + 0.6 * fade)))), max(1.4, size * 0.0038)))
            p.drawArc(rect, start_ang, 180 * 16)

        if not back_pass:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            p.drawPixmap(QRectF(-size * 0.5, -size * 0.5, size, size).toRect(), glow_pix)
            p.setPen(QPen(QColor(18, 22, 28, 170), max(0.8, size * 0.0022)))
            p.setBrush(QColor(*sr, int(min(255, 225 * inten))))
            if crescent_poly is not None:
                p.drawPolygon(crescent_poly)
            p.setPen(Qt.PenStyle.NoPen)
            for poly, al in needles:
                p.setBrush(QColor(*sr, int(min(255, 220 * inten * al))))
                p.drawPolygon(poly)

        p.restore()

    def _draw_ice_armor(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Image 4b: Angular crystalline Voronoi ice facets encasing the actual weapon silhouette."""
        assert self._result is not None
        if back_pass:
            return
        res = 144
        m_small = self._result.blade_mask_alpha.resize((res, res), Image.Resampling.BILINEAR)
        m_arr = np.asarray(m_small, dtype=np.float32) / 255.0
        nz_y, nz_x = np.nonzero(m_arr > 0.15)
        if len(nz_y) < 4:
            return

        # Smooth Gaussian silhouette dilation so crystal armor hugs weapon contours without box artifacts
        blur = np.asarray(m_small.filter(ImageFilter.GaussianBlur(radius=2.6 * scale)), dtype=np.float32) / 255.0
        sheath = np.clip((blur - 0.13) / 0.15, 0.0, 1.0)
        inner_blur = np.asarray(
            Image.fromarray(np.clip(sheath * 255, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(radius=1.4)),
            dtype=np.float32,
        ) / 255.0
        inner = np.clip((inner_blur - 0.48) / 0.22, 0.0, 1.0)
        rim = np.clip((sheath - inner) * 1.35, 0.0, 1.0)

        # Sample crystal seed points deterministically along the weapon silhouette
        n_seeds = 26
        idxs = np.linspace(0, len(nz_y) - 1, n_seeds, dtype=np.int32)
        sy = nz_y[idxs].astype(np.float32) / float(res)
        sx = nz_x[idxs].astype(np.float32) / float(res)
        # Slight golden-angle jitter so facets interlock diagonally like chipped ice
        ang = np.arange(n_seeds, dtype=np.float32) * 2.39996
        sx = np.clip(sx + 0.022 * np.cos(ang), 0.02, 0.98)
        sy = np.clip(sy + 0.018 * np.sin(ang), 0.02, 0.98)

        ys = np.linspace(0.0, 1.0, res, dtype=np.float32)[:, None]
        xs = np.linspace(0.0, 1.0, res, dtype=np.float32)[None, :]
        d1 = np.full((res, res), 1e9, dtype=np.float32)
        d2 = np.full((res, res), 1e9, dtype=np.float32)
        facet_id = np.zeros((res, res), dtype=np.int32)

        for i in range(n_seeds):
            dx = np.abs(xs - sx[i])
            dy = np.abs(ys - sy[i]) * 0.82
            # Blended Euclidean + L1/Chebyshev distance gives sharp angular crystal planes
            dist = 0.55 * np.maximum(dx, dy) + 0.45 * (dx + dy) * 0.7
            mask1 = dist < d1
            d2 = np.where(mask1, d1, np.minimum(d2, dist))
            d1 = np.where(mask1, dist, d1)
            facet_id = np.where(mask1, i, facet_id)

        ridge = np.clip(1.0 - (d2 - d1) / 0.026, 0.0, 1.0) ** 1.55
        facet_shade = 0.42 + 0.58 * ((facet_id % 5) / 4.0)
        shimmer = 0.88 + 0.12 * math.sin(now * 2.8)
        specular = np.clip(ridge * 0.92 + rim * 0.85, 0.0, 1.0) * sheath * shimmer

        rgba = np.zeros((res, res, 4), dtype=np.float32)
        for ch in range(3):
            rgba[:, :, ch] = (pr[ch] * facet_shade * sheath * 0.78 + sr[ch] * specular * 0.95)
        rgba[:, :, 3] = np.clip((sheath * 0.54 + specular * 0.62) * min(1.25, inten), 0.0, 0.95) * 255.0
        pix = pil_to_qpixmap(Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA"))

        p.save()
        p.drawPixmap(QRectF(-size * 0.5, -size * 0.5, size, size).toRect(), pix)
        p.restore()

    def _draw_plasma_web(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Image 4c: Morphing cellular Voronoi blue-white plasma membrane hugging the blade."""
        assert self._result is not None
        if back_pass:
            return
        res = 128
        # Build smooth organic dilated blade silhouette mask via GaussianBlur + smoothstep (avoids square MaxFilter edges)
        mask_small = self._result.blade_mask_alpha.resize((res, res), Image.Resampling.BILINEAR)
        blur = np.asarray(mask_small.filter(ImageFilter.GaussianBlur(radius=3.2 * scale)), dtype=np.float32) / 255.0
        sheath_arr = np.clip((blur - 0.16) / 0.16, 0.0, 1.0)
        if not np.any(sheath_arr > 0.05):
            return

        # Fast vectorized 2D Voronoi cellular distance F2 - F1
        ys = np.linspace(0.0, 1.0, res, dtype=np.float32)[:, None]
        xs = np.linspace(0.0, 1.0, res, dtype=np.float32)[None, :]
        n_seeds = 20
        ang = np.arange(n_seeds, dtype=np.float32) * 2.39996
        sx = 0.5 + 0.14 * np.sin(ang + now * 1.6)
        sy = np.linspace(0.08, 0.92, n_seeds, dtype=np.float32) + 0.04 * np.cos(ang * 1.7 - now * 1.8)

        d1 = np.full((res, res), 1e9, dtype=np.float32)
        d2 = np.full((res, res), 1e9, dtype=np.float32)
        for i in range(n_seeds):
            dist = np.sqrt((xs - sx[i]) ** 2 + (ys - sy[i]) ** 2)
            mask1 = dist < d1
            d2 = np.where(mask1, d1, np.minimum(d2, dist))
            d1 = np.where(mask1, dist, d1)

        ridge = np.clip(1.0 - (d2 - d1) / 0.028, 0.0, 1.0)
        core_web = (ridge ** 1.7) * sheath_arr * 0.88
        body_glow = sheath_arr * 0.34

        rgba = np.zeros((res, res, 4), dtype=np.float32)
        for ch in range(3):
            rgba[:, :, ch] = pr[ch] * body_glow + sr[ch] * core_web
        rgba[:, :, 3] = np.clip((body_glow * 0.65 + core_web * 0.92) * min(1.15, inten), 0.0, 0.92) * 255.0
        rgba_u8 = np.clip(rgba, 0, 255).astype(np.uint8)
        pix = pil_to_qpixmap(Image.fromarray(rgba_u8, "RGBA"))

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawPixmap(QRectF(-size * 0.5, -size * 0.5, size, size).toRect(), pix)
        p.restore()

    def _draw_water_sheath(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Image 4d: Undulating translucent water sheath with crisp white surface-tension foam outline."""
        assert self._result is not None
        if back_pass:
            return
        res = 128
        m_small = self._result.blade_mask_alpha.resize((res, res), Image.Resampling.BILINEAR)
        m_arr = np.asarray(m_small, dtype=np.float32) / 255.0
        if not np.any(m_arr > 0.05):
            return

        # Smooth rounded dilation via GaussianBlur + smoothstep (prevents square MaxFilter T-block artifacts near tips)
        blur = np.asarray(m_small.filter(ImageFilter.GaussianBlur(radius=3.4 * scale)), dtype=np.float32) / 255.0
        w_arr = np.clip((blur - 0.18) / 0.14, 0.0, 1.0)

        ys = np.arange(res, dtype=np.float32)[:, None]
        xs = np.arange(res, dtype=np.float32)[None, :]
        shift_f = np.sin(ys * 0.22 + now * 4.8) * 2.1 * scale
        wave_fx = np.clip(xs + shift_f, 0.0, float(res - 1))
        x0 = np.floor(wave_fx).astype(np.int32)
        x1 = np.minimum(x0 + 1, res - 1)
        wx = wave_fx - x0.astype(np.float32)
        y_idx = np.arange(res, dtype=np.int32)[:, None]
        waved = w_arr[y_idx, x0] * (1.0 - wx) + w_arr[y_idx, x1] * wx

        waved_img = Image.fromarray(np.clip(waved * 255, 0, 255).astype(np.uint8), "L")
        inner_blur = np.asarray(waved_img.filter(ImageFilter.GaussianBlur(radius=1.45)), dtype=np.float32) / 255.0
        water_inner = np.clip((inner_blur - 0.48) / 0.22, 0.0, 1.0)
        foam_rim = np.clip((waved - water_inner) * 1.45, 0.0, 1.0)
        caustics = np.clip(np.sin(ys * 0.34 + xs * 0.24 + now * 4.2), 0.0, 1.0) ** 5 * waved * 0.72

        rgba = np.zeros((res, res, 4), dtype=np.float32)
        for ch in range(3):
            rgba[:, :, ch] = pr[ch] * waved * 0.72 + sr[ch] * np.clip(foam_rim + caustics, 0.0, 1.0)
        rgba[:, :, 3] = np.clip((waved * 0.52 + foam_rim * 0.92 + caustics * 0.65) * min(1.25, inten), 0.0, 0.96) * 255.0
        pix = pil_to_qpixmap(Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA"))

        p.save()
        p.drawPixmap(QRectF(-size * 0.5, -size * 0.5, size, size).toRect(), pix)
        p.restore()

    def _draw_eclipse_flare(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Image 5 (#3): Black-core starburst at guard + crimson-gold solar bloom & lance along blade."""
        assert self._result is not None
        if back_pass:
            return
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.05, self._result.enchant_half_width)
        gem_y = (0.5 - self._result.socket_gem_y_norm) * size
        y_top = max(-size * 0.45, -(span_y + 0.03 * scale) * size)

        pulse = 0.92 + 0.08 * math.sin(now * 5.0)
        lance_w = max(hw_b * 1.12, 0.058) * size * scale
        lance_outer = QPolygonF([
            QPointF(cx_b, y_top),
            QPointF(cx_b + lance_w * 0.85, gem_y),
            QPointF(cx_b, gem_y + size * 0.08 * scale),
            QPointF(cx_b - lance_w * 0.85, gem_y),
        ])
        lance_inner = QPolygonF([
            QPointF(cx_b, y_top + size * 0.022),
            QPointF(cx_b + lance_w * 0.44, gem_y),
            QPointF(cx_b, gem_y + size * 0.052 * scale),
            QPointF(cx_b - lance_w * 0.44, gem_y),
        ])

        star_pts: list[QPointF] = []
        n_spikes = 8
        for k in range(n_spikes * 2):
            ang = k * (math.pi / n_spikes) + math.sin(now * 2.5) * 0.04
            is_tip = (k % 2 == 0)
            rad = size * (0.115 if (is_tip and k % 4 == 0) else (0.082 if is_tip else 0.024)) * scale * pulse
            star_pts.append(QPointF(cx_b + math.cos(ang) * rad, gem_y + math.sin(ang) * rad))
        star_poly = QPolygonF(star_pts)

        # Render soft crimson-gold outer solar bloom buffer at 224x224
        res = 224
        buf = QImage(res, res, QImage.Format.Format_RGBA8888)
        buf.fill(QColor(0, 0, 0, 0))
        bp = QPainter(buf)
        bp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bp.translate(res * 0.5, res * 0.5)
        s_fac = res / max(1.0, size)
        bp.scale(s_fac, s_fac)
        bp.setPen(Qt.PenStyle.NoPen)
        bp.setBrush(QColor(*pr, int(min(255, 225 * inten))))
        bp.drawPolygon(lance_outer)
        bp.setBrush(QColor(*sr, int(min(255, 210 * inten))))
        bp.drawPolygon(star_poly)
        bp.end()
        bloom_img = Image.frombytes("RGBA", (res, res), bytes(buf.constBits())).filter(ImageFilter.GaussianBlur(radius=4.5))
        bloom_pix = pil_to_qpixmap(bloom_img)

        p.save()
        # 1) Additive solar bloom aura behind the sharp flare
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawPixmap(QRectF(-size * 0.5, -size * 0.5, size, size).toRect(), bloom_pix)

        # 2) Blazing lance beam along the blade (softened crimson ink outline + cream-gold core)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(QPen(QColor(42, 8, 8, 175), max(1.2, size * 0.0032)))
        p.setBrush(QColor(*pr, int(min(255, 205 * inten))))
        p.drawPolygon(lance_outer)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*sr, int(min(255, 238 * inten))))
        p.drawPolygon(lance_inner)

        # 3) Tapered curling crimson eclipse tendrils around the guard starburst
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*pr, int(min(255, 205 * inten))))
        arc_r = size * 0.11 * scale
        for s_i in (-1.0, 1.0):
            cx_a = cx_b + s_i * size * 0.02
            th0 = math.radians(20.0 if s_i > 0 else 160.0)
            th_span = math.radians(140.0 * s_i)
            outer_t: list[QPointF] = []
            inner_t: list[QPointF] = []
            for k in range(17):
                t = k / 16.0
                th = th0 + th_span * t
                w = math.sin(t * math.pi) ** 1.15 * size * 0.0085 * scale
                rx_o = arc_r + w * 0.5
                ry_o = arc_r * 0.72 + w * 0.4
                rx_i = max(1.0, arc_r - w * 0.5)
                ry_i = max(1.0, arc_r * 0.72 - w * 0.4)
                outer_t.append(QPointF(cx_a + math.cos(th) * rx_o, gem_y - math.sin(th) * ry_o))
                inner_t.append(QPointF(cx_a + math.cos(th) * rx_i, gem_y - math.sin(th) * ry_i))
            p.drawPolygon(QPolygonF(outer_t + list(reversed(inner_t))))

        # 4) 8-point starburst at guard with jet-black singularity core
        p.setPen(QPen(QColor(35, 6, 6, 185), max(1.2, size * 0.0032)))
        p.setBrush(QColor(*sr, 245))
        p.drawPolygon(star_poly)

        # Jet-black eclipse center
        core_r = size * 0.017 * scale
        p.setPen(QPen(QColor(*pr, 215), 1.4))
        p.setBrush(QColor(10, 8, 12, 255))
        p.drawEllipse(QPointF(cx_b, gem_y), core_r, core_r * 1.15)
        p.restore()

    def _draw_shadow_strife(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Sword-only (Dawn's Strife): Ghostly white guard flames + ash-rimmed pitch-black blade smoke + silver glints."""
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.05, self._result.enchant_half_width)
        gem_y = (0.5 - self._result.socket_gem_y_norm) * size
        y_bot = -span_x * size
        y_top = max(-size * 0.44, -span_y * size)

        # Build billowing charcoal-black ink smoke + silver-ash mist rims from blade_mask_alpha
        res = 144
        m_small = self._result.blade_mask_alpha.resize((res, res), Image.Resampling.BILINEAR)
        m_arr = np.asarray(m_small, dtype=np.float32) / 255.0
        ys = np.linspace(0.0, 1.0, res, dtype=np.float32)[:, None]
        xs = np.linspace(0.0, 1.0, res, dtype=np.float32)[None, :]

        guard_norm_y = 1.0 - self._result.socket_gem_y_norm
        blade_fade = np.clip((guard_norm_y - ys) / 0.13, 0.0, 1.0)
        blur_rad = (5.2 if back_pass else 2.6) * scale
        dil = np.asarray(m_small.filter(ImageFilter.GaussianBlur(radius=blur_rad)), dtype=np.float32) / 255.0
        envelope = np.clip((dil - 0.08) / 0.22, 0.0, 1.0) * blade_fade

        # Multi-octave swirling smoke waves wrapping from ricasso all the way to tip
        scroll = now * 1.9
        wisp1 = np.sin(ys * 26.0 + scroll * 2.2 + np.sin(xs * 22.0 - scroll) * 1.9)
        wisp2 = np.cos(ys * 42.0 - scroll * 1.6 + xs * 26.0)
        turbulence = 0.50 + 0.32 * wisp1 + 0.18 * wisp2

        # Allow dark mist to start right above the guard (small 0.05 blend) and stay strong across lower-mid blade
        blade_fade = np.clip((guard_norm_y - ys) / 0.07, 0.0, 1.0)
        envelope = np.clip((dil - 0.07) / 0.20, 0.0, 1.0) * blade_fade
        smoke_raw = np.clip(envelope * np.clip((turbulence - 0.20) * 1.55, 0.0, 1.0), 0.0, 1.0)
        smoke_blur = np.asarray(
            Image.fromarray(np.clip(smoke_raw * 255, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(radius=1.7)),
            dtype=np.float32,
        ) / 255.0
        ash_rim = np.clip((smoke_blur - smoke_raw * 0.65) * 2.8, 0.0, 1.0) * blade_fade

        if back_pass:
            smoke_density = np.clip(smoke_raw * 0.95 + ash_rim * 0.68, 0.0, 1.0)
        else:
            edge_ring = np.clip((dil - m_arr * 0.80) * 2.4, 0.0, 1.0)
            cross_wisps = np.clip((turbulence - 0.36) * 1.95, 0.0, 1.0)
            fg_mask = np.maximum(edge_ring * 0.90, cross_wisps * 0.80) * blade_fade
            smoke_density = np.clip(smoke_raw * fg_mask + ash_rim * 0.62, 0.0, 0.94)

        smoke_rgba = np.zeros((res, res, 4), dtype=np.float32)
        ash_col = (175.0, 185.0, 200.0)
        dark_mix = np.clip(smoke_raw * 1.25, 0.0, 1.0)
        rim_mix = np.clip(ash_rim * (1.55 if back_pass else 1.75), 0.0, 1.0)
        for ch in range(3):
            smoke_rgba[:, :, ch] = pr[ch] * 0.45 * dark_mix + ash_col[ch] * rim_mix * 0.88
        smoke_rgba[:, :, 3] = np.clip(smoke_density * min(1.30, inten) * (0.94 if back_pass else 0.88), 0.0, 0.96) * 255.0
        smoke_pix = pil_to_qpixmap(Image.fromarray(np.clip(smoke_rgba, 0, 255).astype(np.uint8), "RGBA"))

        # Explicit curling ink-and-ash smoke ribbons hugging lower-to-upper blade edges
        smoke_ribbons: list[QPolygonF] = []
        y_smoke_start = gem_y - size * 0.03
        for rb_i in range(4):
            phase_r = rb_i * 1.57 + now * 1.8
            side_r = -1.0 if rb_i % 2 == 0 else 1.0
            pts_l: list[QPointF] = []
            pts_r: list[QPointF] = []
            for s_i in range(22):
                u = s_i / 21.0
                py_s = y_smoke_start + (y_top - y_smoke_start) * (0.04 + 0.90 * u)
                sway = side_r * math.sin(u * math.pi * 2.2 - phase_r) * max(hw_b * 1.45, 0.055) * size * scale
                swirl = math.cos(u * 14.0 - now * 3.5 + rb_i) * size * 0.012 * scale
                px_s = cx_b + sway + swirl
                hw_s = size * 0.019 * scale * (math.sin(u * math.pi) ** 0.75) * (0.65 + 0.35 * math.sin(u * 10.0 + rb_i))
                pts_l.append(QPointF(px_s - hw_s, py_s))
                pts_r.append(QPointF(px_s + hw_s, py_s))
            smoke_ribbons.append(QPolygonF(pts_l + list(reversed(pts_r))))

        # Render asymmetric organic curling white fire wisps at crossguard/ricasso (NOT stiff fan blades!)
        buf_res = 240
        pad_size = size * 1.22
        buf_scale = buf_res / max(pad_size, 1.0)
        fq = QImage(buf_res, buf_res, QImage.Format.Format_RGBA8888)
        fq.fill(QColor(0, 0, 0, 0))
        fp = QPainter(fq)
        fp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fp.translate(buf_res * 0.5, buf_res * 0.5)
        fp.scale(buf_scale, buf_scale)
        fp.setPen(Qt.PenStyle.NoPen)

        flame_wisps: list[tuple[QPolygonF, int]] = []
        wisp_specs = [
            (-0.028, -118.0, 0.135, -1.0, 0.015),
            (-0.010, -96.0, 0.155, 1.0, 0.018),
            (0.014, -76.0, 0.140, -1.0, 0.016),
            (0.032, -52.0, 0.110, 1.0, 0.013),
            (-0.042, -148.0, 0.095, -1.0, 0.012),
            (0.045, -28.0, 0.088, 1.0, 0.011),
            (0.000, -108.0, 0.115, 1.0, 0.014),
        ]
        for k, (x_off, deg, flen_f, curl_dir, w_f) in enumerate(wisp_specs):
            base_ang = math.radians(deg + math.sin(now * 6.0 + k * 1.9) * 10.0)
            flen = size * (flen_f + 0.025 * math.sin(now * 8.2 + k * 2.1)) * scale
            p0 = QPointF(cx_b + x_off * size * scale, gem_y - size * 0.006)
            pts_l = []
            pts_r = []
            for s in range(11):
                u = s / 10.0
                curl = curl_dir * math.sin(u * math.pi * 1.7 - now * 6.5 + k * 1.3) * size * 0.022 * u * scale
                ang_u = base_ang + curl_dir * (u ** 1.2) * 0.42
                px_u = p0.x() + math.cos(ang_u) * flen * u + curl
                py_u = p0.y() + math.sin(ang_u) * flen * u
                hw_u = max(0.5, size * w_f * scale * ((1.0 - u) ** 0.68) * (0.4 + 0.6 * math.sin(u * math.pi)))
                nx_u, ny_u = -math.sin(ang_u), math.cos(ang_u)
                pts_l.append(QPointF(px_u + nx_u * hw_u, py_u + ny_u * hw_u))
                pts_r.append(QPointF(px_u - nx_u * hw_u, py_u - ny_u * hw_u))
            poly = QPolygonF(pts_l + list(reversed(pts_r)))
            al_w = int(min(255, (220 if k % 2 == 0 else 185) * inten))
            flame_wisps.append((poly, al_w))
            fp.setBrush(QColor(*sr, al_w))
            fp.drawPolygon(poly)
        fp.end()

        bloom_img = Image.frombytes("RGBA", (buf_res, buf_res), bytes(fq.constBits())).filter(ImageFilter.GaussianBlur(radius=3.8))
        white_bloom_pix = pil_to_qpixmap(bloom_img)

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.drawPixmap(QRectF(-size * 0.5, -size * 0.5, size, size).toRect(), smoke_pix)
        # Draw curling charcoal ink ribbons with ash-silver outlines along the blade
        for r_idx, rb_poly in enumerate(smoke_ribbons):
            if (r_idx % 2 == 0) == back_pass:
                p.setPen(QPen(QColor(155, 165, 180, int(min(255, 130 * inten))), max(1.1, size * 0.0030)))
                p.setBrush(QColor(12, 13, 17, int(min(255, 175 * inten))))
                p.drawPolygon(rb_poly)

        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawPixmap(QRectF(-pad_size * 0.5, -pad_size * 0.5, pad_size, pad_size).toRect(), white_bloom_pix)

        if not back_pass:
            # Sharp ghostly inner flame tongues + crackling white ember specks at ricasso
            p.setPen(Qt.PenStyle.NoPen)
            for poly, al_w in flame_wisps:
                p.setBrush(QColor(*sr, int(al_w * 0.85)))
                p.drawPolygon(poly)

            for m_i in range(11):
                age = (now * 1.55 + m_i / 11.0) % 1.0
                fade = enchantment_fade(age)
                mx = cx_b + math.sin(m_i * 2.4 + now * 3.6) * size * 0.095 * scale
                my = gem_y - age * size * 0.16 * scale + math.cos(m_i * 1.9) * size * 0.025
                mr = max(0.9, size * 0.0045 * (1.0 - 0.45 * age))
                p.setBrush(QColor(*sr, int(min(255, 240 * fade * inten))))
                p.drawEllipse(QPointF(mx, my), mr, mr)

            # Razor silver glint streaks along central sword ridge emerging through dark smoke
            for g_i in range(2):
                pulse_g = 0.5 + 0.5 * abs(math.sin(now * 2.8 + g_i * 1.6))
                yg0 = y_bot + (y_top - y_bot) * (0.28 + 0.36 * g_i)
                yg1 = yg0 + (y_top - y_bot) * 0.22
                ym_g = (yg0 + yg1) * 0.5
                gw = max(1.1, size * 0.0055 * scale)
                glint = QPolygonF([
                    QPointF(cx_b, yg0),
                    QPointF(cx_b + gw, ym_g),
                    QPointF(cx_b, yg1),
                    QPointF(cx_b - gw, ym_g),
                ])
                p.setBrush(QColor(*sr, int(min(255, 210 * pulse_g * inten))))
                p.drawPolygon(glint)
        p.restore()

    def _draw_eternal_alpha(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Sword-only (Eternal Alpha): Angelic gold wing-crest guard + molten gold blade sheen + 4-pt star glints."""
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.05, self._result.enchant_half_width)
        gem_y = (0.5 - self._result.socket_gem_y_norm) * size
        y_top = max(-size * 0.45, -span_y * size)
        y_pommel = min(size * 0.43, (0.5 - span_x * 0.35) * size)

        # Build golden blade rim + upward sweeping specular sheen from blade_mask_alpha
        res = 144
        m_small = self._result.blade_mask_alpha.resize((res, res), Image.Resampling.BILINEAR)
        m_arr = np.asarray(m_small, dtype=np.float32) / 255.0
        blur = np.asarray(m_small.filter(ImageFilter.GaussianBlur(radius=3.8 * scale)), dtype=np.float32) / 255.0
        inner = np.asarray(m_small.filter(ImageFilter.GaussianBlur(radius=1.35)), dtype=np.float32) / 255.0
        edge_rim = np.clip((m_arr - np.clip((inner - 0.52) / 0.25, 0.0, 1.0)) * 1.45, 0.0, 1.0)

        ys = np.linspace(0.0, 1.0, res, dtype=np.float32)[:, None]
        xs = np.linspace(0.0, 1.0, res, dtype=np.float32)[None, :]
        sweep_pos = 1.0 - ((now * 0.45) % 1.35) + 0.15
        sweep_band = np.exp(-((ys - sweep_pos) ** 2) / 0.018) * m_arr
        spine_band = np.exp(-((xs - (0.5 + self._result.enchant_center_x)) ** 2) / 0.0012) * m_arr

        gold_rgba = np.zeros((res, res, 4), dtype=np.float32)
        if back_pass:
            aura_f = np.clip(blur * 0.65, 0.0, 1.0)
            for ch in range(3):
                gold_rgba[:, :, ch] = pr[ch] * aura_f
            gold_rgba[:, :, 3] = np.clip(aura_f * 0.78 * min(1.3, inten), 0.0, 0.88) * 255.0
        else:
            # Subtle golden bevel rim + traveling shimmer without washing out steel contrast
            highlight = np.clip(edge_rim * 0.62 + sweep_band * 0.85 + spine_band * 0.45, 0.0, 1.0)
            for ch in range(3):
                gold_rgba[:, :, ch] = pr[ch] * 0.58 * highlight + sr[ch] * 0.42 * highlight
            gold_rgba[:, :, 3] = np.clip(highlight * 0.76 * min(1.3, inten), 0.0, 0.90) * 255.0
        sheen_pix = pil_to_qpixmap(Image.fromarray(np.clip(gold_rgba, 0, 255).astype(np.uint8), "RGBA"))

        # Sculpt graceful curved sweeping golden wing-horns at crossguard
        wings: list[QPolygonF] = []
        shimmer = 0.88 + 0.12 * math.sin(now * 3.6)
        wing_base_w = max(hw_b * 1.45, 0.070) * size * scale
        for s_i in (-1.0, 1.0):
            for ang_deg, r_len, w_sp, y_off, bend in [
                (-60.0, 0.185, 0.016, -0.022, 0.032),
                (-30.0, 0.145, 0.013, -0.004, 0.024),
                (16.0, 0.110, 0.011, 0.016, -0.020),
            ]:
                ang0 = math.radians(ang_deg)
                bx = cx_b + s_i * wing_base_w * 0.28
                by = gem_y + y_off * size * scale
                left_w: list[QPointF] = []
                right_w: list[QPointF] = []
                for k in range(11):
                    t = k / 10.0
                    cur_r = r_len * size * scale * t
                    cur_ang = ang0 + math.sin(t * math.pi * 0.7) * bend * 7.5
                    dx = s_i * math.cos(cur_ang)
                    dy = math.sin(cur_ang)
                    nx, ny = -dy * s_i, dx * s_i
                    hw_k = size * w_sp * scale * ((1.0 - t) ** 0.75) * (0.4 + 0.6 * math.sin(t * math.pi * 0.85))
                    px_k = bx + dx * cur_r
                    py_k = by + dy * cur_r
                    left_w.append(QPointF(px_k + nx * hw_k, py_k + ny * hw_k))
                    right_w.append(QPointF(px_k - nx * hw_k, py_k - ny * hw_k))
                wings.append(QPolygonF(left_w + list(reversed(right_w))))

        # Blurred golden glow buffer for the filigree wings & halo crest
        buf_res = 240
        pad_size = size * 1.22
        buf_scale = buf_res / max(pad_size, 1.0)
        gq = QImage(buf_res, buf_res, QImage.Format.Format_RGBA8888)
        gq.fill(QColor(0, 0, 0, 0))
        gp = QPainter(gq)
        gp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gp.translate(buf_res * 0.5, buf_res * 0.5)
        gp.scale(buf_scale, buf_scale)
        gp.setPen(Qt.PenStyle.NoPen)
        gp.setBrush(QColor(*pr, int(min(255, 225 * inten * shimmer))))
        for wp in wings:
            gp.drawPolygon(wp)
        halo_r = size * 0.068 * scale
        gp.setBrush(Qt.BrushStyle.NoBrush)
        gp.setPen(QPen(QColor(*sr, int(min(255, 235 * inten))), max(3.0, size * 0.010 * scale)))
        gp.drawEllipse(QPointF(cx_b, gem_y), halo_r, halo_r)
        gp.end()
        bloom_pix = pil_to_qpixmap(
            Image.frombytes("RGBA", (buf_res, buf_res), bytes(gq.constBits())).filter(ImageFilter.GaussianBlur(radius=4.2))
        )

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawPixmap(QRectF(-size * 0.5, -size * 0.5, size, size).toRect(), sheen_pix)
        p.drawPixmap(QRectF(-pad_size * 0.5, -pad_size * 0.5, pad_size, pad_size).toRect(), bloom_pix)

        if not back_pass:
            # Crisp celestial gold wing feathers with platinum-white ridge highlights
            p.setPen(QPen(QColor(*sr, int(min(255, 230 * inten))), max(0.9, size * 0.0024)))
            p.setBrush(QColor(*pr, int(min(255, 195 * inten * shimmer))))
            for wp in wings:
                p.drawPolygon(wp)

            # Illuminated celestial alpha crescent/ring at crossguard
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(*pr, int(min(255, 225 * inten))), max(2.2, size * 0.007 * scale)))
            p.drawArc(QRectF(cx_b - halo_r, gem_y - halo_r, halo_r * 2.0, halo_r * 2.0), 30 * 16, 120 * 16)
            p.setPen(QPen(QColor(*sr, int(min(255, 245 * inten))), max(1.2, size * 0.0036 * scale)))
            p.drawArc(QRectF(cx_b - halo_r, gem_y - halo_r, halo_r * 2.0, halo_r * 2.0), -150 * 16, 120 * 16)

            # 4-point celestial star glints at blade tip, guard core, and pommel
            for sx_g, sy_g, s_rad, ph_g in [
                (cx_b, gem_y, size * 0.065 * scale, 0.0),
                (cx_b, y_top, size * 0.048 * scale, 1.3),
                (cx_b, y_pommel, size * 0.036 * scale, 2.4),
            ]:
                tw = 0.65 + 0.35 * math.sin(now * 4.5 + ph_g)
                r_maj = s_rad * tw
                r_min = r_maj * 0.14
                star4 = QPolygonF([
                    QPointF(sx_g, sy_g - r_maj),
                    QPointF(sx_g + r_min, sy_g - r_min),
                    QPointF(sx_g + r_maj * 0.85, sy_g),
                    QPointF(sx_g + r_min, sy_g + r_min),
                    QPointF(sx_g, sy_g + r_maj),
                    QPointF(sx_g - r_min, sy_g + r_min),
                    QPointF(sx_g - r_maj * 0.85, sy_g),
                    QPointF(sx_g - r_min, sy_g - r_min),
                ])
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(*sr, int(min(255, 245 * inten * tw))))
                p.drawPolygon(star4)
        p.restore()

    def _draw_nova_burn(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Sword-only (Nova Burn): Black-core supernova + tilted orbital rings + blazing violet-white plasma lance."""
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.05, self._result.enchant_half_width)
        gem_y = (0.5 - self._result.socket_gem_y_norm) * size
        y_top = max(-size * 0.45, -(span_y + 0.04 * scale) * size)

        pulse = 0.92 + 0.08 * math.sin(now * 5.2)

        if back_pass:
            # Fine astrolabe / orbital calibration rings centered at crossguard singularity
            p.save()
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for ring_r_mul, al_r in [(0.19, 85), (0.26, 55)]:
                rr = size * ring_r_mul * scale
                p.setPen(QPen(QColor(*pr, int(min(255, al_r * inten))), max(0.9, size * 0.0020)))
                p.drawEllipse(QPointF(cx_b, gem_y), rr, rr)
            # Soft violet outer nova halo behind the crossguard
            nova_r = size * 0.24 * scale
            ng = QRadialGradient(QPointF(cx_b, gem_y), nova_r)
            ng.setColorAt(0.0, QColor(*pr, int(min(255, 165 * inten))))
            ng.setColorAt(0.55, QColor(pr[0], pr[1], pr[2], int(min(255, 65 * inten))))
            ng.setColorAt(1.0, QColor(pr[0], pr[1], pr[2], 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(ng))
            p.drawEllipse(QPointF(cx_b, gem_y), nova_r, nova_r)
            p.restore()
            return

        # Build undulating violet plasma flame wisps along edges (smoothly tapering to a sharp tip with NO notch!)
        n_seg = 30
        outer_l: list[QPointF] = []
        outer_r: list[QPointF] = []
        ribbon_l: list[QPointF] = []
        ribbon_r: list[QPointF] = []
        base_w = max(hw_b * 1.48, 0.070) * size * scale
        for k in range(n_seg + 1):
            t = k / float(n_seg)
            py = gem_y + (y_top - gem_y) * t
            tip_taper = (1.0 - t) ** 0.78
            wave = math.sin(t * 15.0 - now * 9.5) * size * 0.014 * scale * math.sin(t * math.pi)
            notch = 0.24 * math.sin(t * 22.0 - now * 11.5) * math.sin(t * math.pi)
            hw_o = base_w * tip_taper * (0.76 + 0.24 * math.sin(t * math.pi * 0.85) + notch)
            hw_o = max(0.0, hw_o)
            outer_l.append(QPointF(cx_b + wave - hw_o, py))
            outer_r.append(QPointF(cx_b + wave + hw_o, py))
            # Smooth continuous winding plasma filament (no discontinuous if/else jump!)
            edge_x = cx_b + wave * 1.10 - hw_o * 0.45 * math.cos(t * math.pi * 1.65 + now * 2.2)
            hw_f = base_w * 0.14 * tip_taper * (0.35 + 0.65 * math.sin(t * math.pi))
            ribbon_l.append(QPointF(edge_x - hw_f, py))
            ribbon_r.append(QPointF(edge_x + hw_f, py))
        lance_outer = QPolygonF(outer_l + list(reversed(outer_r)))
        lance_inner = QPolygonF(ribbon_l + list(reversed(ribbon_r)))

        # Asymmetric thin supernova rays & lens-flare streaks (avoid heavy downward spike over grip!)
        ray_angles_and_lens = [
            (-90.0, 0.22, True),
            (-128.0, 0.17, False),
            (-52.0, 0.19, True),
            (-162.0, 0.14, False),
            (-18.0, 0.15, True),
            (18.0, 0.14, False),
            (162.0, 0.13, True),
            (54.0, 0.11, False),
            (126.0, 0.10, False),
        ]
        shard_polys: list[tuple[QPolygonF, bool]] = []
        for r_i, (deg, len_fac, is_major) in enumerate(ray_angles_and_lens):
            ang = math.radians(deg) + math.sin(now * 2.4 + r_i) * 0.025
            r_len = size * len_fac * scale * pulse
            w_ray = size * (0.0068 if is_major else 0.0042) * scale
            nx, ny = -math.sin(ang), math.cos(ang)
            r0 = size * 0.012 * scale
            rm = r0 + (r_len - r0) * 0.22
            poly = QPolygonF([
                QPointF(cx_b + math.cos(ang) * r0, gem_y + math.sin(ang) * r0),
                QPointF(cx_b + math.cos(ang) * rm + nx * w_ray, gem_y + math.sin(ang) * rm + ny * w_ray),
                QPointF(cx_b + math.cos(ang) * r_len, gem_y + math.sin(ang) * r_len),
                QPointF(cx_b + math.cos(ang) * rm - nx * w_ray, gem_y + math.sin(ang) * rm - ny * w_ray),
            ])
            shard_polys.append((poly, is_major))

        # Soft violet-white supernova bloom in 240x240 padded buffer (modulated so blade isn't blown white!)
        buf_res = 240
        pad_size = size * 1.24
        buf_scale = buf_res / max(pad_size, 1.0)
        nq = QImage(buf_res, buf_res, QImage.Format.Format_RGBA8888)
        nq.fill(QColor(0, 0, 0, 0))
        np_p = QPainter(nq)
        np_p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        np_p.translate(buf_res * 0.5, buf_res * 0.5)
        np_p.scale(buf_scale, buf_scale)
        np_p.setPen(Qt.PenStyle.NoPen)
        np_p.setBrush(QColor(*pr, int(min(255, 165 * inten))))
        np_p.drawPolygon(lance_outer)
        for sp_poly, is_maj in shard_polys:
            np_p.setBrush(QColor(*(sr if is_maj else pr), int(min(255, 195 * inten))))
            np_p.drawPolygon(sp_poly)
        # Tilted orbital shockwave bloom
        np_p.save()
        np_p.translate(cx_b, gem_y)
        np_p.rotate(-22.0 + math.sin(now * 2.0) * 3.5)
        np_p.setBrush(Qt.BrushStyle.NoBrush)
        np_p.setPen(QPen(QColor(*pr, int(min(255, 200 * inten))), max(3.2, size * 0.011 * scale)))
        orb_rx = size * 0.145 * scale
        orb_ry = size * 0.048 * scale
        np_p.drawEllipse(QPointF(0, 0), orb_rx, orb_ry)
        np_p.restore()
        np_p.end()

        bloom_pix = pil_to_qpixmap(
            Image.frombytes("RGBA", (buf_res, buf_res), bytes(nq.constBits())).filter(ImageFilter.GaussianBlur(radius=4.2))
        )

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawPixmap(QRectF(-pad_size * 0.5, -pad_size * 0.5, pad_size, pad_size).toRect(), bloom_pix)

        # Semi-transparent violet flame envelope + crisp winding cream filament (steel fuller stays readable!)
        p.setPen(QPen(QColor(*pr, int(min(255, 175 * inten))), max(1.3, size * 0.004 * scale)))
        p.setBrush(QColor(*pr, int(min(255, 92 * inten))))
        p.drawPolygon(lance_outer)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*sr, int(min(255, 215 * inten))))
        p.drawPolygon(lance_inner)

        # Crisp tilted orbital white-hot shockwave rings around guard
        p.save()
        p.translate(cx_b, gem_y)
        p.rotate(-22.0 + math.sin(now * 2.0) * 3.5)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(*sr, int(min(255, 235 * inten))), max(1.5, size * 0.0042 * scale)))
        p.drawEllipse(QPointF(0, 0), orb_rx, orb_ry)
        p.setPen(QPen(QColor(*pr, int(min(255, 185 * inten))), max(1.0, size * 0.0026 * scale)))
        p.drawEllipse(QPointF(0, 0), orb_rx * 1.18, orb_ry * 1.25)
        p.restore()

        # Sharp supernova rays + orbiting magenta/cream plasma splinters around accretion ring
        p.setPen(Qt.PenStyle.NoPen)
        for sp_poly, is_maj in shard_polys:
            p.setBrush(QColor(*(sr if is_maj else pr), int(min(255, (235 if is_maj else 190) * inten))))
            p.drawPolygon(sp_poly)

        for sp_i in range(8):
            age_sp = (now * 1.15 + sp_i / 8.0) % 1.0
            fade_sp = enchantment_fade(age_sp)
            ang_sp = math.radians(-165.0 + sp_i * 44.0) + now * 0.65
            rad_sp = size * (0.08 + 0.13 * age_sp) * scale
            sx_p = cx_b + math.cos(ang_sp) * rad_sp
            sy_p = gem_y + math.sin(ang_sp) * rad_sp * 0.62
            p.setBrush(QColor(*(sr if sp_i % 2 == 0 else pr), int(min(255, 225 * fade_sp * inten))))
            p.drawEllipse(QPointF(sx_p, sy_p), max(1.0, size * 0.0045), max(1.0, size * 0.0045))

        core_halo_r = size * 0.036 * scale * pulse
        cg = QRadialGradient(QPointF(cx_b, gem_y), core_halo_r)
        cg.setColorAt(0.0, QColor(255, 252, 248, 255))
        cg.setColorAt(0.45, QColor(*sr, 220))
        cg.setColorAt(1.0, QColor(*pr, 0))
        p.setBrush(QBrush(cg))
        p.drawEllipse(QPointF(cx_b, gem_y), core_halo_r, core_halo_r)

        # Jet-black micro-singularity center (CompositionMode_SourceOver for deep black core)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        sing_r = size * 0.015 * scale
        p.setPen(QPen(QColor(*sr, 230), 1.2))
        p.setBrush(QColor(8, 6, 12, 255))
        p.drawEllipse(QPointF(cx_b, gem_y), sing_r, sing_r * 1.1)
        p.restore()

    def _draw_abyssal_miasma(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Abyssal Skullblade signature VFX: Teardrop neon violet throat flame + curling void-indigo blade smoke."""
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.05, self._result.enchant_half_width)
        gem_y = (0.5 - self._result.socket_gem_y_norm) * size
        y_top = max(-size * 0.45, -span_y * size)

        # 1) Rolling dark void-indigo smoke cloud with amethyst outer rim from blade_mask_alpha
        res = 144
        m_small = self._result.blade_mask_alpha.resize((res, res), Image.Resampling.BILINEAR)
        m_arr = np.asarray(m_small, dtype=np.float32) / 255.0
        ys = np.linspace(0.0, 1.0, res, dtype=np.float32)[:, None]
        xs = np.linspace(0.0, 1.0, res, dtype=np.float32)[None, :]

        guard_norm_y = 1.0 - self._result.socket_gem_y_norm
        blade_fade = np.clip((guard_norm_y - ys) / 0.08, 0.0, 1.0)
        blur_rad = (4.6 if back_pass else 2.4) * scale
        dil = np.asarray(m_small.filter(ImageFilter.GaussianBlur(radius=blur_rad)), dtype=np.float32) / 255.0
        envelope = np.clip((dil - 0.08) / 0.22, 0.0, 1.0) * blade_fade

        scroll = now * 1.7
        w1 = np.sin(ys * 26.0 + scroll * 2.1 + np.sin(xs * 22.0 - scroll) * 1.8)
        w2 = np.cos(ys * 44.0 - scroll * 1.5 + xs * 26.0)
        turb = 0.50 + 0.32 * w1 + 0.18 * w2

        smoke_raw = np.clip(envelope * np.clip((turb - 0.26) * 1.5, 0.0, 1.0), 0.0, 1.0)
        smoke_blur = np.asarray(
            Image.fromarray(np.clip(smoke_raw * 255, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(radius=1.6)),
            dtype=np.float32,
        ) / 255.0
        violet_rim = np.clip((smoke_blur - smoke_raw * 0.68) * 2.4, 0.0, 1.0) * blade_fade

        if back_pass:
            dens = np.clip(smoke_raw * 0.88 + violet_rim * 0.55, 0.0, 1.0)
        else:
            edge_ring = np.clip((dil - m_arr * 0.82) * 2.3, 0.0, 1.0)
            cross_wisps = np.clip((turb - 0.48) * 1.9, 0.0, 1.0)
            dens = np.clip(smoke_raw * np.maximum(edge_ring * 0.84, cross_wisps * 0.62) * blade_fade + violet_rim * 0.45, 0.0, 0.88)

        rim_col = (
            min(255.0, sr[0] * 0.62 + 18.0),
            min(255.0, sr[1] * 0.42 + 14.0),
            min(255.0, sr[2] * 0.80 + 24.0),
        )
        smoke_rgba = np.zeros((res, res, 4), dtype=np.float32)
        dark_mix = np.clip(smoke_raw * 1.25, 0.0, 1.0)
        rim_mix = np.clip(violet_rim * (1.35 if back_pass else 1.55), 0.0, 1.0)
        for ch in range(3):
            smoke_rgba[:, :, ch] = pr[ch] * 0.52 * dark_mix + rim_col[ch] * rim_mix * 0.78
        smoke_rgba[:, :, 3] = np.clip(dens * min(1.25, inten) * (0.90 if back_pass else 0.80), 0.0, 0.94) * 255.0
        smoke_pix = pil_to_qpixmap(Image.fromarray(np.clip(smoke_rgba, 0, 255).astype(np.uint8), "RGBA"))

        # Explicit curling void-black & neon-violet rimmed smoke wisps weaving along blade edges
        smoke_ribbons: list[QPolygonF] = []
        y_smoke_start = gem_y - size * 0.025
        for rb_i in range(4):
            phase_r = rb_i * 1.57 + now * 1.8
            side_r = -1.0 if rb_i % 2 == 0 else 1.0
            pts_rl: list[QPointF] = []
            pts_rr: list[QPointF] = []
            for s_i in range(22):
                u = s_i / 21.0
                py_s = y_smoke_start + (y_top - y_smoke_start) * (0.04 + 0.92 * u)
                sway = side_r * math.sin(u * math.pi * 2.1 - phase_r) * max(hw_b * 1.35, 0.052) * size * scale
                swirl = math.cos(u * 13.0 - now * 3.4 + rb_i) * size * 0.011 * scale
                px_s = cx_b + sway + swirl
                hw_s = size * 0.016 * scale * (math.sin(u * math.pi) ** 0.75) * (0.65 + 0.35 * math.sin(u * 10.0 + rb_i))
                pts_rl.append(QPointF(px_s - hw_s, py_s))
                pts_rr.append(QPointF(px_s + hw_s, py_s))
            smoke_ribbons.append(QPolygonF(pts_rl + list(reversed(pts_rr))))

        # 2) Surging teardrop neon violet flame tongue erupting cleanly from a pointed root at gem_y!
        flame_tip_y = gem_y + (y_top - gem_y) * 0.44
        n_seg = 24
        pts_l: list[QPointF] = []
        pts_r: list[QPointF] = []
        core_l: list[QPointF] = []
        core_r: list[QPointF] = []
        base_hw = max(hw_b * 0.56, 0.026) * size * scale
        for k in range(n_seg + 1):
            t = k / float(n_seg)
            py = gem_y + (flame_tip_y - gem_y) * t
            # Smooth teardrop root taper at t=0 -> 0.22 so bottom narrows to a point (NO horizontal cut!)
            root_env = math.sin(min(1.0, t / 0.22) * (math.pi * 0.5)) ** 0.85
            tip_env = (1.0 - t) ** 0.78
            flicker = math.sin(t * 14.0 - now * 9.0) * size * 0.0075 * scale * math.sin(t * math.pi)
            hw_o = base_hw * root_env * tip_env * (0.76 + 0.24 * math.sin(t * 12.0 - now * 7.5))
            hw_i = hw_o * 0.46
            pts_l.append(QPointF(cx_b + flicker - hw_o, py))
            pts_r.append(QPointF(cx_b + flicker + hw_o, py))
            core_l.append(QPointF(cx_b + flicker * 0.7 - hw_i, py))
            core_r.append(QPointF(cx_b + flicker * 0.7 + hw_i, py))
        flame_poly = QPolygonF(pts_l + list(reversed(pts_r)))
        core_poly = QPolygonF(core_l + list(reversed(core_r)))

        # Soft violet glow buffer
        buf_res = 224
        pad_size = size * 1.20
        buf_scale = buf_res / max(pad_size, 1.0)
        vq = QImage(buf_res, buf_res, QImage.Format.Format_RGBA8888)
        vq.fill(QColor(0, 0, 0, 0))
        vp = QPainter(vq)
        vp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        vp.translate(buf_res * 0.5, buf_res * 0.5)
        vp.scale(buf_scale, buf_scale)
        vp.setPen(Qt.PenStyle.NoPen)
        vp.setBrush(QColor(*sr, int(min(255, 220 * inten))))
        vp.drawPolygon(flame_poly)
        vp.end()
        bloom_pix = pil_to_qpixmap(
            Image.frombytes("RGBA", (buf_res, buf_res), bytes(vq.constBits())).filter(ImageFilter.GaussianBlur(radius=3.6))
        )

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.drawPixmap(QRectF(-size * 0.5, -size * 0.5, size, size).toRect(), smoke_pix)
        for r_idx, rb_poly in enumerate(smoke_ribbons):
            if (r_idx % 2 == 0) == back_pass:
                p.setPen(QPen(QColor(int(sr[0] * 0.65), int(sr[1] * 0.45), int(sr[2] * 0.78), int(min(255, 130 * inten))), max(1.0, size * 0.0028)))
                p.setBrush(QColor(16, 10, 26, int(min(255, 175 * inten))))
                p.drawPolygon(rb_poly)

        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawPixmap(QRectF(-pad_size * 0.5, -pad_size * 0.5, pad_size, pad_size).toRect(), bloom_pix)

        if not back_pass:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(*sr, int(min(255, 190 * inten))))
            p.drawPolygon(flame_poly)
            p.setBrush(QColor(255, 210, 255, int(min(255, 232 * inten))))
            p.drawPolygon(core_poly)

            for e_i in range(9):
                age = (now * 0.95 + e_i / 9.0) % 1.0
                fade = enchantment_fade(age)
                ex = cx_b + math.sin(e_i * 2.3 + now * 2.8) * max(hw_b * 1.35, 0.068) * size * scale
                ey = gem_y + (y_top - gem_y) * (0.06 + 0.88 * age)
                er = max(0.9, size * 0.0044 * (1.0 - 0.45 * age))
                p.setBrush(QColor(*sr, int(min(255, 220 * fade * inten))))
                p.drawEllipse(QPointF(ex, ey), er, er)
        p.restore()

    def _draw_ink_void(
        self,
        p: QPainter,
        size: float,
        now: float,
        inten: float,
        scale: float,
        pr: Tuple[int, int, int],
        sr: Tuple[int, int, int],
        back_pass: bool,
    ) -> None:
        """Trấn Ác Void Ink signature VFX: Pitch-black curling ink wisps + ghostly pale-silver flame halo."""
        assert self._result is not None
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x * size
        hw_b = max(0.045, self._result.enchant_half_width)
        gem_y = (0.5 - self._result.socket_gem_y_norm) * size
        y_top = max(-size * 0.46, -span_y * size)

        # 1) Flowing black ink clouds with luminous ghostly silver-white rim
        res = 144
        m_small = self._result.blade_mask_alpha.resize((res, res), Image.Resampling.BILINEAR)
        m_arr = np.asarray(m_small, dtype=np.float32) / 255.0
        ys = np.linspace(0.0, 1.0, res, dtype=np.float32)[:, None]
        xs = np.linspace(0.0, 1.0, res, dtype=np.float32)[None, :]

        guard_norm_y = 1.0 - self._result.socket_gem_y_norm
        blade_fade = np.clip((guard_norm_y - ys) / 0.08, 0.0, 1.0)
        blur_rad = (5.4 if back_pass else 2.8) * scale
        dil = np.asarray(m_small.filter(ImageFilter.GaussianBlur(radius=blur_rad)), dtype=np.float32) / 255.0
        envelope = np.clip((dil - 0.07) / 0.24, 0.0, 1.0) * blade_fade

        scroll = now * 1.9
        w1 = np.sin(ys * 28.0 + scroll * 2.2 + np.sin(xs * 24.0 - scroll) * 2.0)
        w2 = np.cos(ys * 48.0 - scroll * 1.6 + xs * 28.0)
        turb = 0.50 + 0.34 * w1 + 0.16 * w2

        smoke_raw = np.clip(envelope * np.clip((turb - 0.25) * 1.55, 0.0, 1.0), 0.0, 1.0)
        smoke_blur = np.asarray(
            Image.fromarray(np.clip(smoke_raw * 255, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(radius=1.8)),
            dtype=np.float32,
        ) / 255.0
        silver_rim = np.clip((smoke_blur - smoke_raw * 0.70) * 2.6, 0.0, 1.0) * blade_fade

        if back_pass:
            dens = np.clip(smoke_raw * 0.90 + silver_rim * 0.65, 0.0, 1.0)
        else:
            edge_ring = np.clip((dil - m_arr * 0.85) * 2.5, 0.0, 1.0)
            cross_wisps = np.clip((turb - 0.50) * 2.0, 0.0, 1.0)
            dens = np.clip(smoke_raw * np.maximum(edge_ring * 0.86, cross_wisps * 0.55) * blade_fade + silver_rim * 0.52, 0.0, 0.92)

        smoke_rgba = np.zeros((res, res, 4), dtype=np.float32)
        dark_mix = np.clip(smoke_raw * 1.35, 0.0, 1.0)
        rim_mix = np.clip(silver_rim * (1.45 if back_pass else 1.65), 0.0, 1.0)
        for ch in range(3):
            smoke_rgba[:, :, ch] = pr[ch] * 0.65 * dark_mix + sr[ch] * rim_mix * 0.92
        smoke_rgba[:, :, 3] = np.clip(dens * min(1.3, inten) * (0.92 if back_pass else 0.82), 0.0, 0.96) * 255.0
        smoke_pix = pil_to_qpixmap(Image.fromarray(np.clip(smoke_rgba, 0, 255).astype(np.uint8), "RGBA"))

        # 2) Rising ghostly silver-white + ink flames licking upward around crossguard & flanks
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.drawPixmap(QRectF(-size * 0.5, -size * 0.5, size, size).toRect(), smoke_pix)

        for rb_i in range(4):
            if (rb_i % 2 == 0) != back_pass:
                continue
            side_r = -1.0 if rb_i < 2 else 1.0
            phase_r = rb_i * 1.45 + now * 2.0
            pts_l: list[QPointF] = []
            pts_r: list[QPointF] = []
            y0_f = gem_y + size * 0.015
            for s_i in range(20):
                u = s_i / 19.0
                py_s = y0_f + (y_top - y0_f) * (0.02 + 0.86 * u)
                sway = side_r * (0.036 + 0.030 * math.sin(u * math.pi * 1.9 - phase_r)) * size * scale
                px_s = cx_b + sway + math.cos(u * 12.0 - now * 3.6 + rb_i) * size * 0.009 * scale
                hw_s = size * 0.014 * scale * (math.sin(u * math.pi) ** 0.72)
                pts_l.append(QPointF(px_s - hw_s, py_s))
                pts_r.append(QPointF(px_s + hw_s, py_s))
            poly_f = QPolygonF(pts_l + list(reversed(pts_r)))
            p.setPen(QPen(QColor(sr[0], sr[1], sr[2], int(min(255, 65 * inten))), max(2.2, size * 0.0055)))
            p.setBrush(QColor(12, 12, 18, int(min(255, 165 * inten))))
            p.drawPolygon(poly_f)

        # Soft silver-white mist flares off crossguard shoulders
        if not back_pass:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            for sx_g in (-0.055, 0.055):
                gx_s = cx_b + sx_g * size
                gr_s = max(14.0, size * 0.095)
                gg_s = QRadialGradient(QPointF(gx_s, gem_y - size * 0.03), gr_s)
                gg_s.setColorAt(0.0, QColor(sr[0], sr[1], sr[2], int(min(255, 125 * inten))))
                gg_s.setColorAt(0.5, QColor(sr[0], sr[1], sr[2], int(min(255, 55 * inten))))
                gg_s.setColorAt(1.0, QColor(sr[0], sr[1], sr[2], 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(gg_s))
                p.drawEllipse(QPointF(gx_s, gem_y - size * 0.03), gr_s, gr_s * 1.65)
            p.setPen(Qt.PenStyle.NoPen)
            for e_i in range(10):
                age = (now * 0.90 + e_i / 10.0) % 1.0
                fade = enchantment_fade(age)
                ex = cx_b + math.sin(e_i * 2.1 + now * 2.6) * max(hw_b * 1.45, 0.064) * size * scale
                ey = gem_y + (y_top - gem_y) * (0.04 + 0.90 * age)
                er = max(0.9, size * 0.0038 * (1.0 - 0.4 * age))
                p.setBrush(QColor(*sr, int(min(255, 225 * fade * inten))))
                p.drawEllipse(QPointF(ex, ey), er, er)
        p.restore()

    def _draw_element_vfx(self, p: QPainter, elem: ElementDef, size: float, now: float, inten: float) -> None:
        assert self._result is not None
        style = elem.vfx_style
        pr, pg, pb = elem.primary_rgb
        sr, sg, sb = elem.secondary_rgb
        anchors = self._result.preview_anchors
        span_x, span_y = self._result.enchant_span
        cx_b = self._result.enchant_center_x
        hw_b = max(0.03, self._result.enchant_half_width)

        spark_prim = self._get_tinted_sparkle(elem.primary_rgb)
        spark_sec = self._get_tinted_sparkle(elem.secondary_rgb)

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        def get_anchor(i: int, clk: float) -> Tuple[float, float]:
            if anchors:
                idx = (i * 5 + int(math.floor(clk)) * 11) % len(anchors)
                return anchors[idx]
            return (cx_b, (span_x + span_y) * 0.5)

        count = 12 if style in ("starlight", "sakura", "magma", "frostfire", "radiant", "void") else 9

        # Style-specific geometric overlays (Void vortex rings, Concussion rings, Radiant rays, Sakura wind ribbons)
        if style == "void":
            # Swirling singularity rings along the blade
            for r_i in range(3):
                age = (now * 0.55 + r_i / 3.0) % 1.0
                ly = span_x + (span_y - span_x) * (0.3 + 0.22 * r_i)
                rad = size * (0.04 + 0.085 * (1.0 - age))
                alpha = int(enchantment_fade(age) * 190 * min(1.0, inten))
                p.setPen(QPen(QColor(pr, pg, pb, alpha), 2.0))
                p.setBrush(QColor(18, 4, 34, int(alpha * 0.55)))
                p.drawEllipse(QPointF(cx_b * size, -ly * size), rad, rad * 0.55)

        elif style == "concussion":
            for r_i in range(3):
                age = (now * 0.9 + r_i / 3.0) % 1.0
                ly = (span_x + span_y) * 0.55
                rad = size * (0.04 + 0.16 * age)
                alpha = int((1.0 - age) * 185 * min(1.0, inten))
                p.setPen(QPen(QColor(pr, pg, pb, alpha), 2.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx_b * size, -ly * size), rad, rad * 0.7)

        elif style == "radiant":
            # Warm golden solar beams radiating from blade center
            mid_y = -((span_x + span_y) * 0.55) * size
            p.save()
            p.translate(cx_b * size, mid_y)
            p.rotate(now * 16.0)
            for ray in range(6):
                p.rotate(60.0)
                ray_len = size * (0.14 + 0.04 * math.sin(now * 3.0 + ray))
                p.setPen(QPen(QColor(sr, sg, sb, int(90 * min(1.0, inten))), 2.2))
                p.drawLine(QPointF(0, 0), QPointF(0, -ray_len))
            p.restore()

        elif style == "sakura":
            # Gentle swirling wind arcs
            p.setBrush(Qt.BrushStyle.NoBrush)
            for w_i in range(2):
                age = (now * 0.65 + w_i * 0.5) % 1.0
                wy = -(span_x + (span_y - span_x) * age) * size
                alpha = int(enchantment_fade(age) * 145 * min(1.0, inten))
                p.setPen(QPen(QColor(sr, sg, sb, alpha), 1.6))
                arc = QPainterPath(QPointF((cx_b - hw_b * 1.3) * size, wy + 12))
                arc.quadTo(QPointF(cx_b * size, wy - 14), QPointF((cx_b + hw_b * 1.3) * size, wy + 6))
                p.drawPath(arc)

        # Particle loop
        for i in range(count):
            speed = 1.35 if style in ("thunder", "magma", "flame") else 0.72
            clk = now * speed + i / float(count)
            age = clk % 1.0
            lx, ly = get_anchor(i, clk)
            alpha = enchantment_fade(age) * 0.92 * min(1.2, inten)
            alpha = max(0.0, min(1.0, alpha))

            # Motion offset by element style
            if style in ("flame", "magma"):
                ly += age * 0.075
                lx += math.sin(now * 6.0 + i) * 0.015
            elif style == "siphon":
                # Spiral inward toward guard gem
                t_in = age
                ly = ly * (1.0 - t_in * 0.45) + (self._result.socket_gem_y_norm - 0.5) * (t_in * 0.45)
                lx *= (1.0 - t_in * 0.5)
            elif style == "sakura":
                lx += math.sin(now * 2.5 + i * 1.7) * 0.055 + age * 0.03
                ly -= age * 0.045
            elif style == "frostfire":
                phase = now * 3.8 + i * 1.1
                sign = 1.0 if (i % 2 == 0) else -1.0
                lx += math.sin(phase) * hw_b * 0.75 * sign
                ly += age * 0.04
            elif style == "void":
                ang_v = now * 2.6 + i * (2.0 * math.pi / count)
                lx += math.cos(ang_v) * 0.035 * (1.0 - age)
                ly += math.sin(ang_v) * 0.035 * (1.0 - age)
            elif style == "venom":
                ly += age * 0.04
                lx += math.sin(now * 4.0 + i * 2.0) * 0.02

            px = lx * size
            py = -ly * size
            p_size = max(0.068, min(0.145, hw_b * 1.75)) * (1.0 - 0.22 * age) * size * min(1.5, 0.8 + 0.3 * inten)
            use_sec = (i % 2 == 1) and style in ("frostfire", "starlight", "sakura", "magma")

            if style == "sakura":
                # Draw delicate glowing petal ellipse
                p.save()
                p.translate(px, py)
                p.rotate((now * 75.0 + i * 42.0) % 360.0)
                col_p = QColor(sr, sg, sb, int(alpha * 220)) if use_sec else QColor(pr, pg, pb, int(alpha * 235))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col_p)
                p.drawEllipse(QPointF(0, 0), p_size * 0.28, p_size * 0.14)
                p.restore()
            elif style == "frost":
                # Crystal diamond + sparkle
                p.save()
                p.translate(px, py)
                p.rotate(45.0 + now * 25.0 + i * 30.0)
                p.setPen(QPen(QColor(sr, sg, sb, int(alpha * 220)), 1.2))
                p.setBrush(QColor(pr, pg, pb, int(alpha * 110)))
                d = p_size * 0.26
                p.drawRect(QRectF(-d, -d, d * 2, d * 2))
                p.restore()

            if style in ("flame", "magma", "frostfire"):
                # Soft glowing ember motes rising above/around the blade
                col_e = QColor(sr, sg, sb, int(alpha * 220)) if (style == "frostfire" and i % 2 == 1) else QColor(pr, min(255, pg + 55), pb, int(alpha * 220))
                if style == "frostfire" and i % 2 == 0:
                    col_e = QColor(120, 235, 255, int(alpha * 220))
                r_dot = max(1.6, p_size * 0.085)
                grad_e = QRadialGradient(QPointF(px, py), r_dot * 2.2)
                grad_e.setColorAt(0.0, QColor(255, 248, 220, int(alpha * 230)))
                grad_e.setColorAt(0.45, col_e)
                grad_e.setColorAt(1.0, QColor(col_e.red(), col_e.green(), col_e.blue(), 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(grad_e))
                p.drawEllipse(QPointF(px, py), r_dot * 2.2, r_dot * 2.8)
            elif style == "thunder":
                # Crisp electric discharge nodes along blade edges
                r_dot = max(1.6, p_size * 0.08)
                grad_e = QRadialGradient(QPointF(px, py), r_dot * 2.5)
                grad_e.setColorAt(0.0, QColor(255, 255, 255, int(alpha * 235)))
                grad_e.setColorAt(0.4, QColor(pr, pg, pb, int(alpha * 185)))
                grad_e.setColorAt(1.0, QColor(pr, pg, pb, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(grad_e))
                p.drawEllipse(QPointF(px, py), r_dot * 2.5, r_dot * 2.5)
            else:
                # Base Sparkle sprite for rich bloom
                sp = spark_sec if (use_sec and spark_sec is not None) else spark_prim
                if sp is not None:
                    p.save()
                    p.setOpacity(alpha * (0.65 if style == "sakura" else 0.95))
                    p.translate(px, py)
                    p.rotate((now * 3.0 + i * 2.4) * 20.0)
                    p.drawPixmap(
                        QRectF(-p_size * 0.5, -p_size * 0.5, p_size, p_size).toRect(),
                        sp,
                    )
                    if style in ("starlight", "radiant") and i % 3 == 0:
                        p.drawPixmap(
                            QRectF(-p_size * 0.10, -p_size * 0.72, p_size * 0.20, p_size * 1.44).toRect(),
                            sp,
                        )
                        p.drawPixmap(
                            QRectF(-p_size * 0.72, -p_size * 0.10, p_size * 1.44, p_size * 0.20).toRect(),
                            sp,
                        )
                    p.restore()

        p.restore()

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
    """Stylized RimWorld colonist holding the forged weapon with active element aura & gem."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(140)
        self._weapon_pixmap: Optional[QPixmap] = None
        self._outer_aura_pix: Optional[QPixmap] = None
        self._result: Optional[ComposedResult] = None
        self._element: ElementDef = BUILTIN_ELEMENTS[0]
        self._socket_gem: bool = True
        self._facing_left: bool = False

    def set_composed(self, result: ComposedResult, element: ElementDef, socket_gem: bool = True) -> None:
        self._result = result
        self._element = element
        self._socket_gem = socket_gem
        self._weapon_pixmap = pil_to_qpixmap(result.image_rgba)
        if element.id > 0:
            self._outer_aura_pix, _ = _build_blade_aura_pixmap(
                result.blade_mask_alpha, element.primary_rgb, element.secondary_rgb
            )
        else:
            self._outer_aura_pix = None
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

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawEllipse(QPointF(cx, cy + 36), 24, 9)

        p.setPen(QPen(QColor(22, 24, 26), 2.5))
        p.setBrush(QColor(72, 92, 108))
        p.drawRoundedRect(QRectF(cx - 17, cy - 8, 34, 42), 10, 10)

        p.setBrush(QColor(224, 185, 152))
        p.drawEllipse(QPointF(cx, cy - 22), 16, 17)
        p.setBrush(QColor(52, 40, 32))
        p.drawChord(QRectF(cx - 16, cy - 39, 32, 24), 0, 180 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(24, 24, 24))
        ex = -4 if self._facing_left else 4
        p.drawEllipse(QPointF(cx + ex - 4, cy - 20), 1.8, 2.2)
        p.drawEllipse(QPointF(cx + ex + 4, cy - 20), 1.8, 2.2)

        if self._weapon_pixmap is not None and self._result is not None:
            px_scale = 52.0
            draw_px = self._result.draw_size * px_scale
            grip_offset_px = (self._result.grip_y_norm - 0.5) * draw_px

            hand_x = cx + (-20.0 if self._facing_left else 20.0)
            hand_y = cy + 8.0
            angle = (-self._result.equipped_angle) if self._facing_left else self._result.equipped_angle

            p.save()
            p.translate(hand_x, hand_y)
            p.rotate(angle)
            dst_rect = QRectF(-draw_px * 0.5, -draw_px * 0.5 + grip_offset_px, draw_px, draw_px).toRect()

            if self._element.id > 0 and self._outer_aura_pix is not None:
                p.save()
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
                p.setOpacity(0.7)
                p.drawPixmap(dst_rect, self._outer_aura_pix)
                p.restore()

            p.drawPixmap(dst_rect, self._weapon_pixmap)

            if self._element.id > 0 and self._socket_gem:
                gem_y = (0.5 - self._result.socket_gem_y_norm) * draw_px + grip_offset_px
                _draw_faceted_gem(p, 0.0, gem_y, max(3.5, draw_px * 0.025), self._element.primary_rgb, self._element.secondary_rgb, 1.0)

            p.restore()

            p.setPen(QPen(QColor(22, 24, 26), 1.5))
            p.setBrush(QColor(224, 185, 152))
            p.drawEllipse(QPointF(hand_x, hand_y), 4.5, 4.5)

        p.setPen(QColor(145, 156, 158))
        p.drawText(QRectF(8, 5, w - 16, 18), Qt.AlignmentFlag.AlignLeft, "Held preview (click để đổi hướng)")
