"""
Standalone complete-weapon renderer for Overgeared Forge Studio Special Weapons.
Renders full bespoke weapons (no modular forge part assembly required) with crisp
1024x1024 -> 512x512 supersampling, exact blade_mask_alpha, and PNG asset export.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)

from mod_data import ModAssetStore, SpecialWeaponDef
from renderer import ComposedResult


_SPECIAL_CACHE: Dict[Tuple[str, int], Tuple[Image.Image, Image.Image]] = {}


def _apply_tint_and_finish(
    rgba_img: Image.Image,
    tint_rgb: Tuple[float, float, float],
    metal_finish: int,
) -> Image.Image:
    if tint_rgb == (1.0, 1.0, 1.0) and metal_finish == 0:
        return rgba_img
    arr = np.asarray(rgba_img, dtype=np.float32) / 255.0
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3:4]

    if metal_finish == 1:  # Matte polish
        lum = 0.299 * rgb[:, :, 0:1] + 0.587 * rgb[:, :, 1:2] + 0.114 * rgb[:, :, 2:3]
        rgb = rgb * 0.80 + lum * 0.20
    elif metal_finish == 2:  # Blackened
        rgb = np.power(np.clip(rgb, 0.0, 1.0), 1.35) * 0.72
    elif metal_finish == 3:  # Antique bronze
        bronze = np.array([[[1.08, 0.88, 0.62]]], dtype=np.float32)
        rgb = np.clip(rgb * bronze, 0.0, 1.0)

    tr, tg, tb = tint_rgb
    rgb = np.clip(rgb * np.array([[[tr, tg, tb]]], dtype=np.float32), 0.0, 1.0)
    out = np.concatenate([rgb, alpha], axis=2)
    return Image.fromarray(np.clip(out * 255.0, 0, 255).astype(np.uint8), "RGBA")


def _paint_abyssal_skullblade(res: int = 1024) -> Tuple[Image.Image, Image.Image]:
    """
    Paints the complete standalone Abyssal Skullblade at high resolution:
    - Clawed pommel cradling a glowing dark-violet crystal shard (bottom)
    - Ribbed spined vertebrae grip
    - Craggy weathered triple-skull cluster crossguard + asymmetric iron horn quillons
    - Undulating dark obsidian broadblade with clear slate-violet edge bevels & surging throat fissure
    """
    s = float(res)
    w_qimg = QImage(res, res, QImage.Format.Format_RGBA8888)
    w_qimg.fill(QColor(0, 0, 0, 0))
    m_qimg = QImage(res, res, QImage.Format.Format_RGBA8888)
    m_qimg.fill(QColor(0, 0, 0, 0))

    cx = 0.50 * s

    # --- 1. Build organic jagged obsidian broadblade polygon (tip y=0.055 .. throat y=0.635) ---
    blade_pts_l: List[QPointF] = []
    blade_pts_r: List[QPointF] = []
    ridge_pts: List[QPointF] = []
    y_tip = 0.055 * s
    y_throat = 0.632 * s
    n_b = 46
    for k in range(n_b + 1):
        t = k / float(n_b)
        py = y_throat + (y_tip - y_throat) * t
        base_env = (1.0 - t) ** 0.54 * (0.72 + 0.28 * math.sin(t * math.pi * 0.90))
        ripple = 0.075 * math.sin(t * 20.0) + 0.04 * math.cos(t * 34.0)
        notch = (
            -0.11 * math.exp(-((t - 0.68) ** 2) / 0.0014)
            - 0.08 * math.exp(-((t - 0.36) ** 2) / 0.0011)
        )
        hw = max(0.0, s * 0.059 * base_env * (1.0 + ripple + notch))
        if t < 0.09:
            hw *= 0.80 + 0.20 * (t / 0.09)
        sway_r = math.sin(t * 10.0) * 0.0022 * s * (1.0 - t)
        blade_pts_l.append(QPointF(cx - hw, py))
        blade_pts_r.append(QPointF(cx + hw, py))
        ridge_pts.append(QPointF(cx + sway_r, py))
    blade_poly = QPolygonF(blade_pts_l + list(reversed(blade_pts_r)))

    # Paint crisp blade mask
    mp = QPainter(m_qimg)
    mp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    mp.setPen(Qt.PenStyle.NoPen)
    mp.setBrush(QColor(255, 255, 255, 255))
    mp.drawPolygon(blade_poly)
    mp.end()

    p = QPainter(w_qimg)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # --- 2. Draw Obsidian Void Blade with readable bevels & edge catchlights ---
    p.save()
    b_path = QPainterPath()
    b_path.addPolygon(blade_poly)
    p.setClipPath(b_path)

    b_grad = QLinearGradient(QPointF(cx, y_throat), QPointF(cx, y_tip))
    b_grad.setColorAt(0.0, QColor(98, 28, 138))
    b_grad.setColorAt(0.28, QColor(48, 22, 74))
    b_grad.setColorAt(0.65, QColor(28, 22, 42))
    b_grad.setColorAt(1.0, QColor(22, 20, 34))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(b_grad))
    p.drawPolygon(blade_poly)

    # Illuminated left bevel + dark right bevel for clear 3D facet separation
    left_face = QPolygonF(blade_pts_l + list(reversed(ridge_pts)))
    bl_g = QLinearGradient(QPointF(cx - 0.06 * s, 0), QPointF(cx, 0))
    bl_g.setColorAt(0.0, QColor(135, 146, 178, 145))
    bl_g.setColorAt(0.45, QColor(62, 54, 88, 70))
    bl_g.setColorAt(1.0, QColor(18, 12, 28, 30))
    p.setBrush(QBrush(bl_g))
    p.drawPolygon(left_face)

    right_face = QPolygonF(ridge_pts + list(reversed(blade_pts_r)))
    br_g = QLinearGradient(QPointF(cx, 0), QPointF(cx + 0.06 * s, 0))
    br_g.setColorAt(0.0, QColor(8, 6, 14, 155))
    br_g.setColorAt(0.75, QColor(36, 28, 56, 85))
    br_g.setColorAt(1.0, QColor(115, 118, 150, 125))
    p.setBrush(QBrush(br_g))
    p.drawPolygon(right_face)

    # Central metallic fuller highlight extending cleanly toward tip
    p.setPen(QPen(QColor(150, 138, 185, 110), max(1.6, s * 0.0022)))
    for i in range(len(ridge_pts) - 1):
        p.drawLine(ridge_pts[i], ridge_pts[i + 1])

    # Glowing neon amethyst-magenta core flame rising cleanly inside lower blade throat
    core_pts_l: List[QPointF] = []
    core_pts_r: List[QPointF] = []
    y_core_top = 0.25 * s
    for k in range(25):
        u = k / 24.0
        py = y_throat + (y_core_top - y_throat) * u
        sway = math.sin(u * 9.0) * 0.004 * s
        root_taper = math.sin(min(1.0, u / 0.14) * math.pi * 0.5)
        hw_c = s * 0.017 * root_taper * ((1.0 - u) ** 0.72) * (0.75 + 0.25 * math.cos(u * 14.0))
        core_pts_l.append(QPointF(cx + sway - hw_c, py))
        core_pts_r.append(QPointF(cx + sway + hw_c, py))
    core_poly = QPolygonF(core_pts_l + list(reversed(core_pts_r)))
    c_grad = QLinearGradient(QPointF(cx, y_throat), QPointF(cx, y_core_top))
    c_grad.setColorAt(0.0, QColor(255, 178, 255, 250))
    c_grad.setColorAt(0.35, QColor(215, 62, 248, 220))
    c_grad.setColorAt(0.85, QColor(125, 28, 175, 110))
    c_grad.setColorAt(1.0, QColor(45, 12, 70, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(c_grad))
    p.drawPolygon(core_poly)
    p.restore()

    # Crisp pale-slate & violet edge rim outline so the entire blade pops on dark backgrounds!
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(138, 144, 176, 200), max(1.6, s * 0.0024)))
    p.drawPolygon(blade_poly)

    # --- 3. Spined Bone-Steel Ribbed Grip (y=0.68 .. 0.875) ---
    y_g0 = 0.675 * s
    y_g1 = 0.872 * s
    n_ribs = 7
    grip_w = 0.022 * s
    grip_bg = QPolygonF([
        QPointF(cx - grip_w * 0.78, y_g0),
        QPointF(cx + grip_w * 0.78, y_g0),
        QPointF(cx + grip_w * 0.62, y_g1),
        QPointF(cx - grip_w * 0.62, y_g1),
    ])
    g_grad = QLinearGradient(QPointF(cx - grip_w, 0), QPointF(cx + grip_w, 0))
    g_grad.setColorAt(0.0, QColor(96, 116, 124))
    g_grad.setColorAt(0.42, QColor(48, 56, 64))
    g_grad.setColorAt(1.0, QColor(20, 22, 28))
    p.setPen(QPen(QColor(10, 11, 14, 240), s * 0.0028))
    p.setBrush(QBrush(g_grad))
    p.drawPolygon(grip_bg)

    for r_i in range(n_ribs):
        t_r = (r_i + 0.5) / float(n_ribs)
        yr = y_g0 + (y_g1 - y_g0) * t_r
        spur_l = s * (0.027 if r_i % 2 == 0 else 0.017)
        spur_r = s * (0.016 if r_i % 2 == 0 else 0.026)
        rib = QPolygonF([
            QPointF(cx - spur_l, yr - s * 0.007),
            QPointF(cx + spur_r, yr + s * 0.004),
            QPointF(cx + spur_r * 0.75, yr + s * 0.015),
            QPointF(cx - spur_l * 0.82, yr + s * 0.005),
        ])
        rib_g = QLinearGradient(QPointF(cx - spur_l, yr), QPointF(cx + spur_r, yr))
        rib_g.setColorAt(0.0, QColor(138, 160, 168))
        rib_g.setColorAt(0.45, QColor(66, 78, 86))
        rib_g.setColorAt(1.0, QColor(24, 26, 32))
        p.setPen(QPen(QColor(10, 12, 15, 225), s * 0.0022))
        p.setBrush(QBrush(rib_g))
        p.drawPolygon(rib)
        if r_i % 2 == 1:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(180, 66, 225, 165))
            p.drawEllipse(QPointF(cx - s * 0.004, yr - s * 0.009), s * 0.0045, s * 0.003)

    # --- 4. Clawed Pommel Craddling Amethyst Shard (y=0.87 .. 0.945) ---
    y_p0 = 0.868 * s
    y_p1 = 0.942 * s
    shard = QPolygonF([
        QPointF(cx, y_p0 + s * 0.004),
        QPointF(cx + s * 0.018, y_p0 + s * 0.026),
        QPointF(cx + s * 0.006, y_p1 - s * 0.012),
        QPointF(cx - s * 0.015, y_p0 + s * 0.032),
    ])
    sh_g = QLinearGradient(QPointF(cx - s * 0.015, y_p0), QPointF(cx + s * 0.018, y_p1))
    sh_g.setColorAt(0.0, QColor(238, 150, 255))
    sh_g.setColorAt(0.5, QColor(155, 46, 205))
    sh_g.setColorAt(1.0, QColor(48, 16, 68))
    p.setPen(QPen(QColor(16, 10, 22), s * 0.0022))
    p.setBrush(QBrush(sh_g))
    p.drawPolygon(shard)

    claw_l = QPolygonF([
        QPointF(cx - s * 0.008, y_p0),
        QPointF(cx - s * 0.030, y_p0 + s * 0.022),
        QPointF(cx - s * 0.012, y_p1),
        QPointF(cx - s * 0.022, y_p0 + s * 0.028),
        QPointF(cx - s * 0.004, y_p0 + s * 0.014),
    ])
    claw_r = QPolygonF([
        QPointF(cx + s * 0.010, y_p0 + s * 0.005),
        QPointF(cx + s * 0.036, y_p0 + s * 0.018),
        QPointF(cx + s * 0.026, y_p0 + s * 0.046),
        QPointF(cx + s * 0.014, y_p0 + s * 0.056),
        QPointF(cx + s * 0.020, y_p0 + s * 0.026),
    ])
    for claw in (claw_l, claw_r):
        p.setPen(QPen(QColor(10, 12, 16, 235), s * 0.0022))
        p.setBrush(QColor(74, 88, 98))
        p.drawPolygon(claw)

    # --- 5. Craggy Weathered Triple-Skull Cluster Crossguard & Asymmetric Horn Quillons ---
    y_c = 0.642 * s
    # Asymmetric horn quillons (left hooks down steeper, right flares slightly out, matching artwork)
    horn_l = QPolygonF([
        QPointF(cx - 0.034 * s, y_c - 0.016 * s),
        QPointF(cx - 0.096 * s, y_c - 0.004 * s),
        QPointF(cx - 0.132 * s, y_c + 0.052 * s),
        QPointF(cx - 0.108 * s, y_c + 0.062 * s),
        QPointF(cx - 0.094 * s, y_c + 0.024 * s),
        QPointF(cx - 0.040 * s, y_c + 0.022 * s),
    ])
    horn_r = QPolygonF([
        QPointF(cx + 0.034 * s, y_c - 0.014 * s),
        QPointF(cx + 0.104 * s, y_c - 0.006 * s),
        QPointF(cx + 0.144 * s, y_c + 0.028 * s),
        QPointF(cx + 0.120 * s, y_c + 0.040 * s),
        QPointF(cx + 0.098 * s, y_c + 0.018 * s),
        QPointF(cx + 0.040 * s, y_c + 0.022 * s),
    ])
    for side, horn, tip_y in [(-1.0, horn_l, 0.042), (1.0, horn_r, 0.024)]:
        hg = QLinearGradient(QPointF(cx, y_c - 0.02 * s), QPointF(cx + side * 0.14 * s, y_c + 0.05 * s))
        hg.setColorAt(0.0, QColor(110, 134, 144))
        hg.setColorAt(0.55, QColor(56, 70, 78))
        hg.setColorAt(1.0, QColor(20, 24, 28))
        p.setPen(QPen(QColor(10, 12, 16, 240), s * 0.0028))
        p.setBrush(QBrush(hg))
        p.drawPolygon(horn)
        p.setPen(QPen(QColor(178, 204, 216, 190), s * 0.0024, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx + side * 0.044 * s, y_c - 0.011 * s), QPointF(cx + side * 0.125 * s, y_c + tip_y * s))

    # Craggy asymmetric skull cluster with brow ridges, cheekbones & jaw
    guard_body = QPolygonF([
        QPointF(cx - 0.068 * s, y_c - 0.002 * s),
        QPointF(cx - 0.050 * s, y_c - 0.030 * s),
        QPointF(cx - 0.022 * s, y_c - 0.038 * s),
        QPointF(cx, y_c - 0.026 * s),
        QPointF(cx + 0.026 * s, y_c - 0.040 * s),
        QPointF(cx + 0.054 * s, y_c - 0.024 * s),
        QPointF(cx + 0.070 * s, y_c + 0.008 * s),
        QPointF(cx + 0.046 * s, y_c + 0.032 * s),
        QPointF(cx + 0.016 * s, y_c + 0.042 * s),
        QPointF(cx - 0.020 * s, y_c + 0.040 * s),
        QPointF(cx - 0.048 * s, y_c + 0.028 * s),
    ])
    sk_grad = QRadialGradient(QPointF(cx - 0.012 * s, y_c - 0.012 * s), 0.088 * s)
    sk_grad.setColorAt(0.0, QColor(124, 150, 156))
    sk_grad.setColorAt(0.55, QColor(58, 72, 80))
    sk_grad.setColorAt(1.0, QColor(20, 24, 30))
    p.setPen(QPen(QColor(10, 12, 16, 245), s * 0.0032))
    p.setBrush(QBrush(sk_grad))
    p.drawPolygon(guard_body)

    # Organic angular skull sockets (eye hollows, nasal cavity & side cranium hollows)
    sockets = [
        [(-0.028, -0.008), (-0.010, -0.016), (-0.008, 0.002), (-0.024, 0.006)],  # Left main eye
        [(0.008, -0.016), (0.026, -0.006), (0.022, 0.007), (0.007, 0.001)],      # Right main eye
        [(-0.005, 0.010), (0.005, 0.010), (0.002, 0.022), (-0.004, 0.022)],      # Nasal slit
        [(-0.056, -0.002), (-0.042, -0.006), (-0.040, 0.009), (-0.054, 0.010)],  # Left flank skull
        [(0.040, -0.004), (0.054, 0.001), (0.052, 0.014), (0.039, 0.010)],       # Right flank skull
    ]
    for sock_pts in sockets:
        poly_s = QPolygonF([QPointF(cx + px_s * s, y_c + py_s * s) for px_s, py_s in sock_pts])
        p.setPen(QPen(QColor(145, 168, 176, 155), s * 0.0018))
        p.setBrush(QColor(8, 7, 12, 250))
        p.drawPolygon(poly_s)

    # Weathered skull suture cracks & brow highlights
    p.setPen(QPen(QColor(14, 16, 20, 210), s * 0.0020, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(cx - 0.036 * s, y_c - 0.026 * s), QPointF(cx - 0.022 * s, y_c - 0.014 * s))
    p.drawLine(QPointF(cx + 0.034 * s, y_c - 0.026 * s), QPointF(cx + 0.020 * s, y_c - 0.012 * s))

    # Glowing neon-magenta cleft cleanly nestled at top bridge of the skull guard (feeding the blade flame)
    mouth_glow = QPolygonF([
        QPointF(cx - 0.009 * s, y_c - 0.020 * s),
        QPointF(cx, y_c - 0.050 * s),
        QPointF(cx + 0.009 * s, y_c - 0.020 * s),
        QPointF(cx, y_c - 0.014 * s),
    ])
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(238, 102, 255, 225))
    p.drawPolygon(mouth_glow)

    p.end()

    w_pil = Image.frombytes("RGBA", (res, res), bytes(w_qimg.constBits())).resize((512, 512), Image.Resampling.LANCZOS)
    m_pil = Image.frombytes("RGBA", (res, res), bytes(m_qimg.constBits())).split()[3].resize((512, 512), Image.Resampling.LANCZOS)
    return w_pil, m_pil


def _paint_tran_ac_inkblade(res: int = 1024) -> Tuple[Image.Image, Image.Image]:
    """
    Paints Trấn Ác · Thái Hư Hắc Kiếm (Void Inkblade) at high resolution:
    - Crowned gothic black-iron lotus pommel cradling a glowing indigo-violet crystal
    - Sleek black diamond-wrapped grip with cold-iron collar rings
    - Intricate jet-black wrought-iron gothic crossguard with indigo-sapphire core gem & filigree spikes
    - Tall gleaming silver-steel tapered diamond blade with etched dark-iron ricasso filigree & crisp bevels
    """
    s = float(res)
    w_qimg = QImage(res, res, QImage.Format.Format_RGBA8888)
    w_qimg.fill(QColor(0, 0, 0, 0))
    m_qimg = QImage(res, res, QImage.Format.Format_RGBA8888)
    m_qimg.fill(QColor(0, 0, 0, 0))
    cx = 0.50 * s

    # --- 1. Sleek Tapered Silver-Steel Diamond Blade (y_throat=0.618 .. y_tip=0.056) ---
    blade_l: List[QPointF] = []
    blade_r: List[QPointF] = []
    ridge_pts: List[QPointF] = []
    y_tip = 0.056 * s
    y_throat = 0.618 * s
    n_b = 40
    for k in range(n_b + 1):
        t = k / float(n_b)
        py = y_throat + (y_tip - y_throat) * t
        if t < 0.08:
            # Slight graceful fuller waist above gothic throat
            hw = s * (0.044 - 0.006 * math.sin((t / 0.08) * math.pi))
        elif t < 0.88:
            u = (t - 0.08) / 0.80
            hw = s * (0.043 * (1.0 - 0.44 * u))
        else:
            u = (t - 0.88) / 0.12
            hw = s * (0.024 * ((1.0 - u) ** 0.78))
        blade_l.append(QPointF(cx - hw, py))
        blade_r.append(QPointF(cx + hw, py))
        ridge_pts.append(QPointF(cx, py))
    blade_poly = QPolygonF(blade_l + list(reversed(blade_r)))

    mp = QPainter(m_qimg)
    mp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    mp.setPen(Qt.PenStyle.NoPen)
    mp.setBrush(QColor(255, 255, 255, 255))
    mp.drawPolygon(blade_poly)
    mp.end()

    p = QPainter(w_qimg)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    p.save()
    b_path = QPainterPath()
    b_path.addPolygon(blade_poly)
    p.setClipPath(b_path)

    # Illuminated cold silver-white left bevel + dark gunmetal right bevel
    left_face = QPolygonF(blade_l + list(reversed(ridge_pts)))
    lg_l = QLinearGradient(QPointF(cx - 0.045 * s, 0), QPointF(cx, 0))
    lg_l.setColorAt(0.0, QColor(246, 250, 255))
    lg_l.setColorAt(0.45, QColor(194, 204, 222))
    lg_l.setColorAt(1.0, QColor(126, 134, 152))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(lg_l))
    p.drawPolygon(left_face)

    right_face = QPolygonF(ridge_pts + list(reversed(blade_r)))
    lg_r = QLinearGradient(QPointF(cx, 0), QPointF(cx + 0.045 * s, 0))
    lg_r.setColorAt(0.0, QColor(42, 46, 58))
    lg_r.setColorAt(0.65, QColor(96, 104, 122))
    lg_r.setColorAt(1.0, QColor(218, 226, 242))
    p.setBrush(QBrush(lg_r))
    p.drawPolygon(right_face)

    # Dark ink-iron etched ricasso gradient creeping up lower throat (y=0.52..0.618)
    ric_g = QLinearGradient(QPointF(cx, y_throat), QPointF(cx, 0.50 * s))
    ric_g.setColorAt(0.0, QColor(18, 20, 28, 245))
    ric_g.setColorAt(0.55, QColor(36, 40, 56, 175))
    ric_g.setColorAt(1.0, QColor(120, 130, 155, 0))
    p.setBrush(QBrush(ric_g))
    p.drawRect(QRectF(cx - 0.06 * s, 0.49 * s, 0.12 * s, 0.14 * s))

    # Crisp central metallic ridge highlight & fuller slit
    p.setPen(QPen(QColor(255, 255, 255, 210), max(1.8, s * 0.0024)))
    p.drawLine(QPointF(cx, y_throat - 0.04 * s), QPointF(cx, y_tip + 0.02 * s))
    p.setPen(QPen(QColor(26, 28, 38, 220), max(1.5, s * 0.0022)))
    p.drawLine(QPointF(cx, y_throat), QPointF(cx, 0.36 * s))

    # Small diamond engraved fuller ornament near upper tip
    p.setPen(QPen(QColor(24, 26, 36, 200), s * 0.0018))
    p.setBrush(QColor(34, 38, 52, 220))
    p.drawPolygon(QPolygonF([
        QPointF(cx, 0.120 * s),
        QPointF(cx + 0.005 * s, 0.132 * s),
        QPointF(cx, 0.145 * s),
        QPointF(cx - 0.005 * s, 0.132 * s),
    ]))
    p.restore()

    # Crisp steel edge outline
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(32, 36, 46, 235), max(1.6, s * 0.0022)))
    p.drawPolygon(blade_poly)

    # --- 2. Black Diamond-Leather Grip (y=0.655 .. 0.858) ---
    y_g0, y_g1 = 0.650 * s, 0.858 * s
    gw_top, gw_bot = 0.015 * s, 0.013 * s
    grip_poly = QPolygonF([
        QPointF(cx - gw_top, y_g0),
        QPointF(cx + gw_top, y_g0),
        QPointF(cx + gw_bot, y_g1),
        QPointF(cx - gw_bot, y_g1),
    ])
    gg = QLinearGradient(QPointF(cx - gw_top, 0), QPointF(cx + gw_top, 0))
    gg.setColorAt(0.0, QColor(56, 60, 74))
    gg.setColorAt(0.45, QColor(20, 22, 28))
    gg.setColorAt(1.0, QColor(8, 9, 12))
    p.setPen(QPen(QColor(6, 7, 10, 245), s * 0.0024))
    p.setBrush(QBrush(gg))
    p.drawPolygon(grip_poly)

    # Subtle silver-pewter crisscross grip wrap
    p.setPen(QPen(QColor(115, 124, 146, 155), s * 0.0018))
    n_wrap = 6
    for w_i in range(n_wrap):
        ya = y_g0 + (y_g1 - y_g0) * (w_i / float(n_wrap))
        yb = y_g0 + (y_g1 - y_g0) * ((w_i + 1.0) / float(n_wrap))
        p.drawLine(QPointF(cx - gw_top * 0.9, ya), QPointF(cx + gw_top * 0.9, yb))
        p.drawLine(QPointF(cx + gw_top * 0.9, ya), QPointF(cx - gw_top * 0.9, yb))

    # --- 3. Crowned Black-Spire Lotus Pommel & Indigo Gem (y=0.855 .. 0.948) ---
    y_p0 = 0.855 * s
    pom_outer = QPolygonF([
        QPointF(cx - 0.022 * s, y_p0),
        QPointF(cx + 0.022 * s, y_p0),
        QPointF(cx + 0.032 * s, y_p0 + 0.028 * s),
        QPointF(cx + 0.018 * s, y_p0 + 0.068 * s),
        QPointF(cx, 0.946 * s),
        QPointF(cx - 0.018 * s, y_p0 + 0.068 * s),
        QPointF(cx - 0.032 * s, y_p0 + 0.028 * s),
    ])
    p.setPen(QPen(QColor(102, 112, 134, 210), s * 0.0022))
    p.setBrush(QColor(16, 18, 24, 250))
    p.drawPolygon(pom_outer)
    pom_gem = QPolygonF([
        QPointF(cx, y_p0 + 0.018 * s),
        QPointF(cx + 0.010 * s, y_p0 + 0.038 * s),
        QPointF(cx, y_p0 + 0.064 * s),
        QPointF(cx - 0.010 * s, y_p0 + 0.038 * s),
    ])
    pg_g = QRadialGradient(QPointF(cx, y_p0 + 0.038 * s), 0.026 * s)
    pg_g.setColorAt(0.0, QColor(205, 198, 255))
    pg_g.setColorAt(0.5, QColor(88, 72, 225))
    pg_g.setColorAt(1.0, QColor(24, 20, 68))
    p.setPen(QPen(QColor(12, 14, 20), s * 0.0018))
    p.setBrush(QBrush(pg_g))
    p.drawPolygon(pom_gem)

    # --- 4. Ornate Jet-Black Wrought-Iron Crossguard & Indigo Core Jewel (y_c = 0.625) ---
    y_c = 0.625 * s
    guard_pts = QPolygonF([
        QPointF(cx - 0.118 * s, y_c - 0.012 * s),
        QPointF(cx - 0.072 * s, y_c + 0.002 * s),
        QPointF(cx - 0.044 * s, y_c - 0.038 * s),
        QPointF(cx - 0.022 * s, y_c - 0.022 * s),
        QPointF(cx, y_c - 0.066 * s),
        QPointF(cx + 0.022 * s, y_c - 0.022 * s),
        QPointF(cx + 0.044 * s, y_c - 0.038 * s),
        QPointF(cx + 0.072 * s, y_c + 0.002 * s),
        QPointF(cx + 0.118 * s, y_c - 0.012 * s),
        QPointF(cx + 0.082 * s, y_c + 0.024 * s),
        QPointF(cx + 0.036 * s, y_c + 0.028 * s),
        QPointF(cx + 0.016 * s, y_c + 0.044 * s),
        QPointF(cx - 0.016 * s, y_c + 0.044 * s),
        QPointF(cx - 0.036 * s, y_c + 0.028 * s),
        QPointF(cx - 0.082 * s, y_c + 0.024 * s),
    ])
    g_metal = QLinearGradient(QPointF(cx - 0.11 * s, y_c - 0.04 * s), QPointF(cx + 0.11 * s, y_c + 0.04 * s))
    g_metal.setColorAt(0.0, QColor(36, 40, 50))
    g_metal.setColorAt(0.5, QColor(14, 15, 20))
    g_metal.setColorAt(1.0, QColor(42, 46, 58))
    p.setPen(QPen(QColor(112, 122, 144, 215), s * 0.0024))
    p.setBrush(QBrush(g_metal))
    p.drawPolygon(guard_pts)

    # Central glowing indigo-sapphire crystal & tiny pinpoint filigree accents
    cg = QRadialGradient(QPointF(cx, y_c - 0.004 * s), 0.020 * s)
    cg.setColorAt(0.0, QColor(225, 232, 255))
    cg.setColorAt(0.45, QColor(92, 104, 245))
    cg.setColorAt(1.0, QColor(20, 22, 58))
    p.setPen(QPen(QColor(180, 195, 235, 195), s * 0.0016))
    p.setBrush(QBrush(cg))
    p.drawPolygon(QPolygonF([
        QPointF(cx, y_c - 0.022 * s),
        QPointF(cx + 0.011 * s, y_c - 0.002 * s),
        QPointF(cx, y_c + 0.016 * s),
        QPointF(cx - 0.011 * s, y_c - 0.002 * s),
    ]))
    for ax in (-0.036, 0.036):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(220, 228, 255, 230))
        p.drawEllipse(QPointF(cx + ax * s, y_c + 0.006 * s), s * 0.0032, s * 0.0032)

    p.end()

    w_pil = Image.frombytes("RGBA", (res, res), bytes(w_qimg.constBits())).resize((512, 512), Image.Resampling.LANCZOS)
    m_pil = Image.frombytes("RGBA", (res, res), bytes(m_qimg.constBits())).split()[3].resize((512, 512), Image.Resampling.LANCZOS)
    return w_pil, m_pil


def _paint_white_dragon_featherblade(res: int = 1024) -> Tuple[Image.Image, Image.Image]:
    """
    Paints Bạch Long Vũ Kiếm (White Feather Dragonblade) 100% faithful to reference:
    - Gently S-curved single-edged pearlescent ivory/smoky-taupe blade sweeping left at tip with jagged upper-left spine notches
    - Twin sculpted bone-white dragon-wing collars hugging the throat with fine black-ink scale hatching & dotwork
    - Asymmetrical lush wispy white feather-plume skirt with steep left quills (ink-outlined) & wide sweeping right pinions
    - Slender ivory handle adorned with curling black-ink filigree tendrils
    - Organic open-loop hollow teardrop pearl pommel
    """
    s = float(res)
    w_qimg = QImage(res, res, QImage.Format.Format_RGBA8888)
    w_qimg.fill(QColor(0, 0, 0, 0))
    m_qimg = QImage(res, res, QImage.Format.Format_RGBA8888)
    m_qimg.fill(QColor(0, 0, 0, 0))

    cx = 0.475 * s
    y_tip = 0.038 * s
    y_throat = 0.562 * s

    def _blade_axis_x(t: float) -> float:
        # Subtle graceful rightward bow in lower half, sweeping cleanly leftward toward sharp tip
        if t < 0.44:
            u = t / 0.44
            return cx + 0.012 * s * math.sin(u * math.pi * 0.5)
        u = (t - 0.44) / 0.56
        return cx + 0.012 * s * (1.0 - u) - 0.078 * s * (u ** 1.52)

    # --- 1. Build Organic Curved Pearl Blade Polygon ---
    blade_l: List[QPointF] = []
    blade_r: List[QPointF] = []
    ridge_pts: List[QPointF] = []
    n_b = 64
    for k in range(n_b + 1):
        t = k / float(n_b)
        py = y_throat + (y_tip - y_throat) * t
        ax = _blade_axis_x(t)

        # Smooth blade width profile swelling gently through mid-belly then tapering to needle tip
        belly = 0.78 + 0.30 * math.sin(min(1.0, t / 0.78) * math.pi * 0.85)
        tip_taper = 1.0 if t < 0.76 else max(0.0, ((1.0 - t) / 0.24) ** 0.72)
        base_w = s * 0.0225 * belly * tip_taper

        # Exact upper-left jagged organic notches & subtle hand-forged waviness on left spine
        spine_notch = (
            -0.36 * math.exp(-((t - 0.585) ** 2) / 0.00055)
            - 0.26 * math.exp(-((t - 0.685) ** 2) / 0.00045)
            - 0.20 * math.exp(-((t - 0.790) ** 2) / 0.00050)
            + 0.08 * math.sin(t * 26.0) * (1.0 - tip_taper * 0.25)
        )
        wl = max(0.0, base_w * (0.94 + spine_notch))
        # Right cutting edge is crisp, smooth, slightly convex
        wr = max(0.0, base_w * (1.08 + 0.08 * math.sin(t * math.pi)))
        if t > 0.985:
            wl = wr = 0.0

        blade_l.append(QPointF(ax - wl, py))
        blade_r.append(QPointF(ax + wr, py))
        ridge_pts.append(QPointF(ax + wr * 0.12, py))

    blade_poly = QPolygonF(blade_l + list(reversed(blade_r)))

    # Paint blade alpha mask for VFX engines
    mp = QPainter(m_qimg)
    mp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    mp.setPen(Qt.PenStyle.NoPen)
    mp.setBrush(QColor(255, 255, 255, 255))
    mp.drawPolygon(blade_poly)
    mp.end()

    p = QPainter(w_qimg)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # --- 2. Paint Handle Shaft + Black-Ink Filigree + Open Teardrop Loop Pommel (underneath feather skirt) ---
    hx = cx + 0.005 * s
    y_h0 = 0.640 * s
    y_h1 = 0.875 * s
    shaft_poly = QPolygonF([
        QPointF(hx - 0.0125 * s, y_h0),
        QPointF(hx + 0.0125 * s, y_h0),
        QPointF(hx + 0.0105 * s, 0.810 * s),
        QPointF(hx + 0.0135 * s, y_h1),
        QPointF(hx - 0.0135 * s, y_h1),
        QPointF(hx - 0.0105 * s, 0.810 * s),
    ])
    sh_grad = QLinearGradient(QPointF(hx - 0.015 * s, 0), QPointF(hx + 0.015 * s, 0))
    sh_grad.setColorAt(0.0, QColor(186, 184, 180))
    sh_grad.setColorAt(0.35, QColor(238, 238, 240))
    sh_grad.setColorAt(0.75, QColor(252, 252, 254))
    sh_grad.setColorAt(1.0, QColor(204, 204, 208))
    p.setPen(QPen(QColor(126, 126, 132, 185), s * 0.0018))
    p.setBrush(QBrush(sh_grad))
    p.drawPolygon(shaft_poly)

    # Organic Open-Loop Hollow Teardrop Pommel (y = 0.862 .. 0.958)
    pom_outer = QPainterPath()
    pom_outer.moveTo(hx - 0.011 * s, 0.864 * s)
    pom_outer.cubicTo(hx - 0.014 * s, 0.892 * s, hx - 0.036 * s, 0.916 * s, hx - 0.030 * s, 0.942 * s)
    pom_outer.cubicTo(hx - 0.024 * s, 0.962 * s, hx + 0.028 * s, 0.962 * s, hx + 0.033 * s, 0.938 * s)
    pom_outer.cubicTo(hx + 0.038 * s, 0.912 * s, hx + 0.015 * s, 0.890 * s, hx + 0.011 * s, 0.864 * s)
    pom_outer.closeSubpath()

    pom_inner = QPainterPath()
    pom_inner.moveTo(hx - 0.002 * s, 0.898 * s)
    pom_inner.cubicTo(hx - 0.016 * s, 0.912 * s, hx - 0.018 * s, 0.936 * s, hx - 0.004 * s, 0.944 * s)
    pom_inner.cubicTo(hx + 0.014 * s, 0.948 * s, hx + 0.020 * s, 0.922 * s, hx + 0.004 * s, 0.898 * s)
    pom_inner.closeSubpath()

    pom_ring = pom_outer.subtracted(pom_inner)
    pom_g = QLinearGradient(QPointF(hx - 0.034 * s, 0.88 * s), QPointF(hx + 0.034 * s, 0.95 * s))
    pom_g.setColorAt(0.0, QColor(202, 200, 198))
    pom_g.setColorAt(0.42, QColor(250, 250, 252))
    pom_g.setColorAt(0.78, QColor(225, 226, 232))
    pom_g.setColorAt(1.0, QColor(178, 178, 184))
    p.setPen(QPen(QColor(132, 132, 138, 200), s * 0.0020))
    p.setBrush(QBrush(pom_g))
    p.drawPath(pom_ring)

    # Inner highlight crescent along loop pommel
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 235), s * 0.0026, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    hl_arc = QPainterPath()
    hl_arc.moveTo(hx - 0.022 * s, 0.922 * s)
    hl_arc.cubicTo(hx - 0.022 * s, 0.946 * s, hx + 0.018 * s, 0.950 * s, hx + 0.024 * s, 0.924 * s)
    p.drawPath(hl_arc)

    # Delicate black-ink curling vine/rune markings along visible upper grip (y = 0.742 .. 0.855)
    p.setPen(QPen(QColor(24, 24, 28, 225), s * 0.0019, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    vine = QPainterPath()
    vine.moveTo(hx - 0.005 * s, 0.744 * s)
    vine.cubicTo(hx + 0.011 * s, 0.764 * s, hx - 0.012 * s, 0.786 * s, hx + 0.008 * s, 0.808 * s)
    vine.cubicTo(hx - 0.010 * s, 0.824 * s, hx + 0.007 * s, 0.840 * s, hx - 0.006 * s, 0.852 * s)
    p.drawPath(vine)
    for vy_f, side_v in [(0.758, -1.0), (0.775, 1.0), (0.794, -1.0), (0.814, 1.0), (0.834, -1.0)]:
        vy = vy_f * s
        curl = QPainterPath()
        curl.moveTo(hx, vy)
        curl.quadTo(hx + side_v * 0.012 * s, vy - 0.004 * s, hx + side_v * 0.008 * s, vy + 0.008 * s)
        p.drawPath(curl)

    # --- 3. Paint Painterly Pearlescent & Smoky-Ivory Blade ---
    p.save()
    b_path = QPainterPath()
    b_path.addPolygon(blade_poly)
    p.setClipPath(b_path)

    # Cross-blade luminous pearl-white right to warm smoky-taupe left
    b_grad = QLinearGradient(QPointF(cx - 0.075 * s, 0.25 * s), QPointF(cx + 0.045 * s, 0.25 * s))
    b_grad.setColorAt(0.0, QColor(126, 122, 116))
    b_grad.setColorAt(0.32, QColor(178, 174, 168))
    b_grad.setColorAt(0.66, QColor(238, 236, 234))
    b_grad.setColorAt(1.0, QColor(255, 255, 255))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(b_grad))
    p.drawPolygon(blade_poly)

    # Vertical smoky-taupe watercolor shading concentrated on upper curved spine (t = 0.50 .. 0.96)
    v_smoke = QLinearGradient(QPointF(cx, y_throat), QPointF(cx - 0.05 * s, y_tip))
    v_smoke.setColorAt(0.0, QColor(246, 244, 240, 120))
    v_smoke.setColorAt(0.38, QColor(255, 255, 255, 160))
    v_smoke.setColorAt(0.68, QColor(148, 140, 128, 130))
    v_smoke.setColorAt(0.92, QColor(102, 98, 94, 155))
    v_smoke.setColorAt(1.0, QColor(225, 224, 222, 140))
    p.setBrush(QBrush(v_smoke))
    p.drawPolygon(blade_poly)

    # Painterly smoky watercolor cloud mottles inside upper spine + luminous pearl sheen in lower-mid belly
    mottles = [
        (0.84, -0.008, 0.018, 0.034, QColor(92, 86, 80, 115)),
        (0.72, -0.006, 0.022, 0.042, QColor(115, 108, 98, 105)),
        (0.60, -0.004, 0.020, 0.036, QColor(138, 132, 122, 90)),
        (0.44, 0.005, 0.024, 0.058, QColor(255, 255, 255, 195)),
        (0.28, 0.004, 0.022, 0.055, QColor(255, 254, 252, 175)),
        (0.14, 0.002, 0.018, 0.042, QColor(230, 226, 220, 125)),
    ]
    for mt, ox_f, rx_f, ry_f, mc in mottles:
        mx = _blade_axis_x(mt) + ox_f * s
        my = y_throat + (y_tip - y_throat) * mt
        mg = QRadialGradient(QPointF(mx, my), max(rx_f, ry_f) * s)
        mg.setColorAt(0.0, mc)
        mg.setColorAt(1.0, QColor(mc.red(), mc.green(), mc.blue(), 0))
        p.setBrush(QBrush(mg))
        p.drawEllipse(QPointF(mx, my), rx_f * s, ry_f * s)

    # Glowing alabaster cutting edge highlight along entire right blade face
    right_strip = QPolygonF(ridge_pts + list(reversed(blade_r)))
    rg = QLinearGradient(QPointF(cx - 0.01 * s, 0), QPointF(cx + 0.04 * s, 0))
    rg.setColorAt(0.0, QColor(255, 255, 255, 45))
    rg.setColorAt(0.55, QColor(255, 255, 255, 175))
    rg.setColorAt(1.0, QColor(255, 255, 255, 245))
    p.setBrush(QBrush(rg))
    p.drawPolygon(right_strip)
    p.restore()

    # Crisp edge outlines: soft charcoal on jagged left spine, gleaming white on smooth right cutting edge
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(110, 108, 104, 185), max(1.4, s * 0.0018)))
    for i in range(len(blade_l) - 1):
        p.drawLine(blade_l[i], blade_l[i + 1])
    p.setPen(QPen(QColor(255, 255, 255, 245), max(1.8, s * 0.0024)))
    for i in range(len(blade_r) - 1):
        p.drawLine(blade_r[i], blade_r[i + 1])

    # --- 4. Long Sweeping Outer White Wing-Feathers / Pinions (Back Layer) ---
    def _draw_feather_quill(
        p0: Tuple[float, float],
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        w_base: float,
        w_mid: float,
        col_top: QColor,
        col_bot: QColor,
        ink_edge: bool = False,
    ) -> None:
        n_q = 18
        left_q: List[QPointF] = []
        right_q: List[QPointF] = []
        spine_q: List[QPointF] = []
        for k in range(n_q + 1):
            u = k / float(n_q)
            iu = 1.0 - u
            qx = (iu * iu) * p0[0] + 2 * iu * u * p1[0] + (u * u) * p2[0]
            qy = (iu * iu) * p0[1] + 2 * iu * u * p1[1] + (u * u) * p2[1]
            tx = 2 * iu * (p1[0] - p0[0]) + 2 * u * (p2[0] - p1[0])
            ty = 2 * iu * (p1[1] - p0[1]) + 2 * u * (p2[1] - p1[1])
            ln = math.hypot(tx, ty) or 1.0
            nx, ny = -ty / ln, tx / ln
            hw = (w_base * (1.0 - u) + w_mid * math.sin(u * math.pi)) * ((1.0 - u) ** 0.55)
            spine_q.append(QPointF(qx, qy))
            left_q.append(QPointF(qx + nx * hw, qy + ny * hw))
            right_q.append(QPointF(qx - nx * hw, qy - ny * hw))
        poly_q = QPolygonF(left_q + list(reversed(right_q)))
        qg = QLinearGradient(QPointF(p0[0], p0[1]), QPointF(p2[0], p2[1]))
        qg.setColorAt(0.0, col_top)
        qg.setColorAt(0.65, col_bot)
        qg.setColorAt(1.0, QColor(col_bot.red(), col_bot.green(), col_bot.blue(), 195))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qg))
        p.drawPolygon(poly_q)
        # Bright rachis highlight
        p.setPen(QPen(QColor(255, 255, 255, 210), max(1.0, s * 0.0014)))
        for j in range(len(spine_q) - 1):
            p.drawLine(spine_q[j], spine_q[j + 1])
        if ink_edge:
            p.setPen(QPen(QColor(30, 32, 36, 205), max(1.1, s * 0.0015), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for j in range(len(left_q) - 3):
                p.drawLine(left_q[j], left_q[j + 1])

    # Right sweeping dramatic long white pinions (matching Image 1's wide asymmetrical right plume!)
    right_pinions = [
        ((cx + 0.032 * s, 0.545 * s), (cx + 0.095 * s, 0.585 * s), (cx + 0.145 * s, 0.625 * s), 0.009 * s, 0.006 * s),
        ((cx + 0.025 * s, 0.625 * s), (cx + 0.175 * s, 0.700 * s), (cx + 0.305 * s, 0.895 * s), 0.015 * s, 0.012 * s),
        ((cx + 0.022 * s, 0.642 * s), (cx + 0.145 * s, 0.730 * s), (cx + 0.242 * s, 0.890 * s), 0.016 * s, 0.012 * s),
        ((cx + 0.018 * s, 0.655 * s), (cx + 0.112 * s, 0.742 * s), (cx + 0.185 * s, 0.865 * s), 0.014 * s, 0.010 * s),
        ((cx + 0.015 * s, 0.665 * s), (cx + 0.075 * s, 0.735 * s), (cx + 0.128 * s, 0.818 * s), 0.013 * s, 0.009 * s),
    ]
    for p0, p1, p2, wb, wm in right_pinions:
        _draw_feather_quill(p0, p1, p2, wb, wm, QColor(246, 246, 248, 242), QColor(218, 220, 226, 232), ink_edge=False)

    # Left steep downward-curving white pinions (with delicate black ink contour lines like Image 1!)
    left_pinions = [
        ((cx - 0.036 * s, 0.620 * s), (cx - 0.118 * s, 0.725 * s), (cx - 0.145 * s, 0.845 * s), 0.012 * s, 0.009 * s, False),
        ((cx - 0.028 * s, 0.635 * s), (cx - 0.095 * s, 0.752 * s), (cx - 0.092 * s, 0.868 * s), 0.014 * s, 0.010 * s, True),
        ((cx - 0.018 * s, 0.650 * s), (cx - 0.068 * s, 0.745 * s), (cx - 0.060 * s, 0.822 * s), 0.013 * s, 0.009 * s, True),
    ]
    for p0, p1, p2, wb, wm, ink_e in left_pinions:
        _draw_feather_quill(p0, p1, p2, wb, wm, QColor(244, 244, 246, 242), QColor(214, 216, 222, 230), ink_edge=ink_e)

    # --- 5. Lush Dense White Feather Skirt Cascade (3 overlapping tiers of fine wispy feathers!) ---
    rng_f = np.random.default_rng(717)
    for tier_idx, (n_tufts, len_mul, col_base) in enumerate([
        (42, 1.06, QColor(212, 214, 220, 225)),
        (54, 0.94, QColor(244, 245, 248, 238)),
        (46, 0.80, QColor(255, 255, 255, 248)),
    ]):
        for f_i in range(n_tufts):
            u = f_i / max(1.0, float(n_tufts - 1))
            # Fan angles from steep down-left (138 deg) through straight down (90 deg) to wide down-right (34 deg)
            ang_deg = 136.0 - u * 102.0 + float(rng_f.uniform(-3.2, 3.2))
            rad = math.radians(ang_deg)
            ox = cx + (0.5 - u) * -0.065 * s + float(rng_f.uniform(-0.008, 0.008)) * s
            oy = (0.618 + 0.022 * math.sin(u * math.pi)) * s
            # Asymmetric skirt length: fuller on left & wide right wings, shorter tucked over center grip
            side_boost = 1.0 + 0.28 * abs(u - 0.44) + (0.24 if u > 0.62 else 0.0)
            flen = s * (0.095 + 0.055 * float(rng_f.uniform(0.0, 1.0))) * side_boost * len_mul
            curve_dir = -1.0 if ang_deg > 92.0 else 1.0
            mid_x = ox + math.cos(rad) * flen * 0.52 + curve_dir * 0.010 * s
            mid_y = oy + math.sin(rad) * flen * 0.52
            tip_x = ox + math.cos(rad) * flen + curve_dir * 0.018 * s
            tip_y = oy + math.sin(rad) * flen
            fw = s * (0.0068 if tier_idx == 0 else (0.0052 if tier_idx == 1 else 0.0034))
            nx, ny = -math.sin(rad), math.cos(rad)
            f_poly = QPolygonF([
                QPointF(ox + nx * fw, oy + ny * fw),
                QPointF(mid_x + nx * fw * 0.72, mid_y + ny * fw * 0.72),
                QPointF(tip_x, tip_y),
                QPointF(mid_x - nx * fw * 0.72, mid_y - ny * fw * 0.72),
                QPointF(ox - nx * fw, oy - ny * fw),
            ])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col_base)
            p.drawPolygon(f_poly)

    # --- 6. Sculptural Bone-White Twin Dragon-Wing Guard Collars + Fine Black Ink Linework ---
    # Left dragon-wing collar (higher crest at y=0.498, sweeping down-left & sending ribbed tail across throat)
    left_collar = QPainterPath()
    left_collar.moveTo(cx - 0.018 * s, 0.500 * s)
    left_collar.cubicTo(cx - 0.032 * s, 0.494 * s, cx - 0.044 * s, 0.514 * s, cx - 0.048 * s, 0.548 * s)
    left_collar.cubicTo(cx - 0.068 * s, 0.592 * s, cx - 0.092 * s, 0.648 * s, cx - 0.098 * s, 0.692 * s)
    left_collar.cubicTo(cx - 0.072 * s, 0.668 * s, cx - 0.046 * s, 0.644 * s, cx - 0.022 * s, 0.616 * s)
    left_collar.cubicTo(cx - 0.006 * s, 0.648 * s, cx + 0.006 * s, 0.678 * s, cx + 0.028 * s, 0.706 * s)
    left_collar.cubicTo(cx + 0.012 * s, 0.662 * s, cx + 0.004 * s, 0.620 * s, cx - 0.008 * s, 0.578 * s)
    left_collar.cubicTo(cx - 0.012 * s, 0.546 * s, cx - 0.010 * s, 0.512 * s, cx - 0.018 * s, 0.500 * s)
    left_collar.closeSubpath()

    # Right dragon-wing collar (slightly lower crest at y=0.522, arching downward-right with slender spur)
    right_collar = QPainterPath()
    right_collar.moveTo(cx + 0.024 * s, 0.522 * s)
    right_collar.cubicTo(cx + 0.042 * s, 0.518 * s, cx + 0.056 * s, 0.546 * s, cx + 0.068 * s, 0.584 * s)
    right_collar.cubicTo(cx + 0.088 * s, 0.620 * s, cx + 0.106 * s, 0.654 * s, cx + 0.118 * s, 0.678 * s)
    right_collar.cubicTo(cx + 0.082 * s, 0.658 * s, cx + 0.046 * s, 0.632 * s, cx + 0.012 * s, 0.610 * s)
    right_collar.cubicTo(cx + 0.006 * s, 0.580 * s, cx + 0.012 * s, 0.542 * s, cx + 0.024 * s, 0.522 * s)
    right_collar.closeSubpath()

    for col_path, gx0, gx1 in [
        (right_collar, cx, cx + 0.11 * s),
        (left_collar, cx - 0.10 * s, cx + 0.03 * s),
    ]:
        cg = QLinearGradient(QPointF(gx0, 0.51 * s), QPointF(gx1, 0.68 * s))
        cg.setColorAt(0.0, QColor(208, 208, 212))
        cg.setColorAt(0.45, QColor(246, 246, 248))
        cg.setColorAt(0.85, QColor(224, 225, 230))
        cg.setColorAt(1.0, QColor(186, 186, 192))
        p.setPen(QPen(QColor(26, 28, 34, 232), s * 0.0020, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(QBrush(cg))
        p.drawPath(col_path)

    # Fine Black Ink Dragon-Scale Rib Hatching, Tendril Contours & Dotwork (Signature Image 1 Detail!)
    ink_pen = QPen(QColor(20, 22, 26, 235), s * 0.0017, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(ink_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    # Left dragon neck segmented rib scale bars
    for r_i in range(9):
        u = r_i / 8.0
        ry = (0.522 + u * 0.155) * s
        rx = cx + (-0.026 + u * 0.034) * s
        p.drawLine(QPointF(rx - 0.007 * s, ry), QPointF(rx + 0.006 * s, ry - 0.003 * s))
    # Right dragon neck segmented rib scale bars
    for r_i in range(7):
        u = r_i / 6.0
        ry = (0.538 + u * 0.092) * s
        rx = cx + (0.032 + u * 0.024) * s
        p.drawLine(QPointF(rx - 0.006 * s, ry - 0.002 * s), QPointF(rx + 0.007 * s, ry + 0.003 * s))

    # Graceful outer left black ink calligraphy line trailing down left wing feathers
    left_ink_trail = QPainterPath()
    left_ink_trail.moveTo(cx - 0.030 * s, 0.528 * s)
    left_ink_trail.cubicTo(cx - 0.064 * s, 0.610 * s, cx - 0.088 * s, 0.690 * s, cx - 0.104 * s, 0.778 * s)
    p.drawPath(left_ink_trail)

    # Delicate tiny black ink dots along the sculptural dragon-collar ridges
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(22, 24, 28, 235))
    dot_coords = [
        (-0.025, 0.508), (-0.032, 0.524), (-0.044, 0.578), (-0.056, 0.608),
        (-0.068, 0.642), (0.032, 0.532), (0.044, 0.562), (0.058, 0.596),
    ]
    for dx_d, dy_d in dot_coords:
        p.drawEllipse(QPointF(cx + dx_d * s, dy_d * s), s * 0.0023, s * 0.0023)

    p.end()

    w_pil = Image.frombytes("RGBA", (res, res), bytes(w_qimg.constBits())).resize((512, 512), Image.Resampling.LANCZOS)
    m_pil = Image.frombytes("RGBA", (res, res), bytes(m_qimg.constBits())).split()[3].resize((512, 512), Image.Resampling.LANCZOS)
    return w_pil, m_pil


def render_special_weapon(
    store: Optional[ModAssetStore],
    weapon: SpecialWeaponDef,
    resolution: int = 512,
    tint_rgb: Tuple[float, float, float] = (1.0, 1.0, 1.0),
    metal_finish: int = 0,
    save_asset: bool = True,
) -> ComposedResult:
    """Renders or loads a standalone complete special weapon as a ComposedResult."""
    key = (weapon.id, resolution)
    if key not in _SPECIAL_CACHE:
        if weapon.id == "tran_ac_inkblade":
            w_512, m_512 = _paint_tran_ac_inkblade(1024)
        elif weapon.id == "white_dragon_featherblade":
            w_512, m_512 = _paint_white_dragon_featherblade(1024)
        else:
            w_512, m_512 = _paint_abyssal_skullblade(1024)
        if resolution != 512:
            w_out = w_512.resize((resolution, resolution), Image.Resampling.LANCZOS)
            m_out = m_512.resize((resolution, resolution), Image.Resampling.LANCZOS)
        else:
            w_out, m_out = w_512, m_512
        _SPECIAL_CACHE[key] = (w_out, m_out)

        if save_asset and store is not None and weapon.texture_rel_path:
            out_path = store.textures_root / weapon.texture_rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            w_512.save(out_path, "PNG")

    base_rgba, blade_mask = _SPECIAL_CACHE[key]
    tinted_rgba = _apply_tint_and_finish(base_rgba, tint_rgb, metal_finish)

    anchors: List[Tuple[float, float]] = []
    for k in range(18):
        t = (k + 0.5) / 18.0
        ly = -0.11 + 0.54 * t
        lx = ((k % 3) - 1) * 0.028 * (1.0 - 0.55 * t)
        anchors.append((lx, ly))

    return ComposedResult(
        image_rgba=tinted_rgba,
        blade_mask_alpha=blade_mask,
        resolution=resolution,
        draw_size=1.35,
        grip_y_norm=0.22,
        socket_gem_y_norm=0.368,
        equipped_angle=25.0,
        enchant_span=(-0.132, 0.445),
        enchant_center_x=0.0,
        enchant_half_width=0.059,
        preview_anchors=anchors,
    )
