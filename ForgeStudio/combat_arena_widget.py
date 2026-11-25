"""
Real RimWorld Pawn + Combat Dummy Arena with live SQUISHY Melee (3839642536)
animation & multi-hit combo simulation for Overgeared Forge Studio.

Loads authentic 128x128 RimWorld Pawn body & head sprites (bundled via cloned
SQUISHY Ranged HolsterPreview assets or RimWorld install when available) and
parses SquishyMelee/Settings/Routines.xml (15 base routines + 6 multi-hit combos).
"""
from __future__ import annotations

import math
import random
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mod_data import BUILTIN_ELEMENTS, ElementDef
from renderer import ComposedResult
from theme import pil_to_qpixmap


BODY_TYPES = ["Male", "Female", "Hulk", "Thin", "Fat"]
_ARENA_FONT_FAMILY: Optional[str] = None


def _get_arena_font(pixel_size: int = 12, bold: bool = False) -> QFont:
    global _ARENA_FONT_FAMILY
    if _ARENA_FONT_FAMILY is None:
        fams = QFontDatabase.families()
        if fams:
            _ARENA_FONT_FAMILY = "Segoe UI" if "Segoe UI" in fams else fams[0]
        else:
            for cand in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\tahoma.ttf"):
                if Path(cand).exists():
                    fid = QFontDatabase.addApplicationFont(cand)
                    loaded = QFontDatabase.applicationFontFamilies(fid)
                    if loaded:
                        _ARENA_FONT_FAMILY = loaded[0]
                        break
            if _ARENA_FONT_FAMILY is None:
                _ARENA_FONT_FAMILY = "SansSerif"
    f = QFont(_ARENA_FONT_FAMILY)
    f.setPixelSize(max(9, pixel_size))
    f.setBold(bold)
    return f

ROUTINE_DISPLAY_NAMES: Dict[str, str] = {
    "sk_abyssal_dragon_cleave": "🐉 [Skill 1] Phong Long Trảm (Abyssal Dragon Cleave)",
    "sk_phantom_blink": "💨 [Skill 2] Bạo Tốc Ảnh Bộ (Phantom Afterimage Rush · 2-Hit)",
    "sk_cyclone_vortex": "🌀 [Skill 3] Long Quyển Tàn Ảnh (Abyssal Cyclone · 3-Hit)",
    "sk_soaring_pierce": "⚡ [Skill 4] Long Phong Phá Kích (Dragon Fang Piercer · 2-Hit)",
    "sk_pentagram_cataclysm": "✡ [Skill 5] Ngũ Mang Hắc Tinh Trận (Void Pentagram Ult · 5-Hit)",
    "sk_ink_eclipse_ring": "🌑 [Hắc Ảnh I] Hắc Nhật Trảm (Black Eclipse Orbit Slash)",
    "sk_ink_void_wave": "🌙 [Hắc Ảnh II] Thái Hư Trảm Ba (Kiếm Khí Tầm Xa)",
    "sk_ink_void_aegis": "🛡️ [Hắc Ảnh III] Hắc Giáp Hộ Thể (Giáp Hư Không Quanh Thân)",
    "sk_ink_shadow_spikes": "🖤 [Hắc Ảnh IV] Lệ Ảnh Phá Toái (Shadow Spikes & 5-Wave · 3-Hit)",
    "sk_ink_blood_eclipse": "🌘 [Hắc Ảnh V] Huyết Nguyệt Vô Ảnh (Abyssal Eclipse Ult · 4-Hit)",
    "sk_wdf_crescent_wave": "🌙 [Bạch Long I] Bạch Nguyệt Trảm Ba (Bán Nguyệt Tầm Xa)",
    "sk_wdf_planetary_cleave": "🪐 [Bạch Long II] Tinh Cầu Bùng Nổ (Chém Ngang Nổ Hành Tinh)",
    "sk_wdf_twin_dragon_aegis": "☯️ [Bạch Long III] Song Long Hộ Giáp (Khiên Trắng Đen 2 Rồng)",
    "sk_wdf_dragon_dash": "🐉 [Bạch Long IV] Bạch Long Xung Kích (Lướt Rồng · 2-Hit)",
    "sk_wdf_cataclysm_5x5": "💥 [Bạch Long V] Âm Dương Diệt Giới (Vụ Nổ Lớn 5x5 · Ult)",
    "combo_cross_slash": "🔥 [Combo 2x] Song Trảm Chữ X (Cross Double Slash)",
    "combo_whirl_flurry": "🔥 [Combo 3x] Liên Hoàn Tam Trảm (Triple Flurry)",
    "combo_rising_tempest": "🔥 [Combo 3x] Thăng Long Phá (Rising Tempest)",
    "combo_pierce_barrage": "🔥 [Combo 3x] Liên Hoàn Đột Kích (Triple Thrust)",
    "combo_abyssal_execution": "💀 [Combo 4x] Ám Sát Đoạt Mệnh (Phantom Execution)",
    "combo_omni_verdict": "✨ [Combo 4x] Thiên Phạt Vĩnh Hằng (Eternal Verdict)",
    "classic": "Chém Cơ Bản (Classic Swing)",
    "overhead": "Bổ Đầu (Overhead Chop)",
    "crouch_dash": "Lướt Chém Thấp (Forward Slash)",
    "rising_cut": "Hất Ngược Lên (Rising Slash)",
    "leap_slam": "Nhảy Bổ Mạnh (Leaping Chop)",
    "leap_slash": "Nhảy Chém (Leaping Slash)",
    "back_thrust": "Lùi Đâm (Retreating Thrust)",
    "quick_thrust": "Đâm Nhanh (Quick Thrust)",
    "head_butt": "Húc Lao Thân (Body Slam)",
    "pounce": "Vồ Nhảy (Leaping Body Slam)",
    "sweep": "Quét Vòng Rộng (Wide Swing)",
    "swing_dash": "Nhử Rồi Lướt Chém (Feint & Slash)",
    "rise_chop": "Vung Cao Rồi Bổ (Delayed Chop)",
    "jab_lunge": "Đâm Đúp Lao Tới (Aim & Lunge)",
    "retreat_swing": "Vừa Lùi Vừa Chém (Retreat & Slash)",
    "snap": "Chém Nhanh Ngắn (Quick Snap)",
}


@dataclass
class MotionKey:
    t: float
    sw: float = 0.0
    up: float = 0.0
    wx: float = 0.0
    push: float = 0.0
    lean: float = 0.0
    sy: float = 0.0
    sx: float = 0.0
    hop: float = 0.0
    head: float = 0.0
    pt: float = 0.0
    stop: bool = False


@dataclass
class StrikeSpec:
    gap: float = 0.0
    amp: float = 1.0
    arc: int = 1
    push: float = 1.0
    hold: float = 3.0
    pull: float = 0.0


@dataclass
class RoutineDef:
    id: str
    weight: float = 1.0
    combo: bool = False
    mirror: bool = True
    cold: bool = True
    kinds: str = "all"
    hit: MotionKey = field(default_factory=lambda: MotionKey(0.0, sw=90.0))
    landing: float = 0.0
    strikes: List[StrikeSpec] = field(default_factory=list)
    pre: List[MotionKey] = field(default_factory=list)
    post: List[MotionKey] = field(default_factory=list)


def _kf(el: Optional[ET.Element], default_t: float = 0.0) -> MotionKey:
    if el is None:
        return MotionKey(default_t)
    def gf(attr: str, d: float = 0.0) -> float:
        try:
            return float(el.attrib.get(attr, d))
        except Exception:
            return d
    return MotionKey(
        t=gf("t", default_t),
        sw=gf("sw"),
        up=gf("up"),
        wx=gf("wx"),
        push=gf("push"),
        lean=gf("lean"),
        sy=gf("sy"),
        sx=gf("sx"),
        hop=gf("hop"),
        head=gf("head"),
        pt=gf("pt"),
        stop=(el.attrib.get("stop", "false").lower() == "true"),
    )


def load_squishy_routines(routines_xml: Path) -> List[RoutineDef]:
    """Parses SquishyMelee/Settings/Routines.xml into typed RoutineDefs."""
    if not routines_xml.exists():
        # Built-in fallback routine if XML not present
        return [
            RoutineDef(
                id="combo_cross_slash",
                combo=True,
                strikes=[StrikeSpec(0, 0.9, 1, 0.9, 2, 0), StrikeSpec(11, 1.2, -1, 1.15, 4, 0.35)],
                hit=MotionKey(0, sw=92, wx=0.22, push=0.34, lean=14, sy=0.07, sx=-0.05, hop=0.03, head=9),
                pre=[MotionKey(-24, sw=-20, lean=-3), MotionKey(-10, sw=-76, up=0.10, sy=-0.07, lean=-6, stop=True), MotionKey(0, sw=-4, push=0.16)],
                post=[MotionKey(22, sw=-30, stop=True), MotionKey(34, sw=0)],
            )
        ]

    routines: List[RoutineDef] = []
    tree = ET.parse(routines_xml)
    root = tree.getroot()
    for r_el in root.findall("Routine"):
        rid = r_el.attrib.get("id", "classic")
        hit_el = r_el.find("Hit")
        hit_kf = _kf(hit_el, 0.0)
        landing = float(hit_el.attrib.get("landing", "0")) if hit_el is not None else 0.0
        strikes: List[StrikeSpec] = []
        if hit_el is not None:
            for s_el in hit_el.findall("Strike"):
                strikes.append(StrikeSpec(
                    gap=float(s_el.attrib.get("gap", "0")),
                    amp=float(s_el.attrib.get("amp", "1")),
                    arc=int(float(s_el.attrib.get("arc", "1"))),
                    push=float(s_el.attrib.get("push", "1")),
                    hold=float(s_el.attrib.get("hold", "3")),
                    pull=float(s_el.attrib.get("pull", "0")),
                ))
        if not strikes:
            strikes.append(StrikeSpec())
        pre_keys = [_kf(k) for k in (r_el.find("Pre").findall("Key") if r_el.find("Pre") is not None else [])]
        post_keys = [_kf(k) for k in (r_el.find("Post").findall("Key") if r_el.find("Post") is not None else [])]
        routines.append(RoutineDef(
            id=rid,
            weight=float(r_el.attrib.get("weight", "1.0")),
            combo=(r_el.attrib.get("combo", "false").lower() == "true"),
            mirror=(r_el.attrib.get("mirror", "true").lower() == "true"),
            cold=(r_el.attrib.get("cold", "true").lower() == "true"),
            kinds=r_el.attrib.get("kinds", "all"),
            hit=hit_kf,
            landing=landing,
            strikes=strikes,
            pre=sorted(pre_keys, key=lambda x: x.t),
            post=sorted(post_keys, key=lambda x: x.t),
        ))

    # Put combo routines first in UI order for easy testing
    routines.sort(key=lambda r: (0 if r.id.startswith("combo_") else 1))
    return routines


def _tint_pawn_sprite(
    src_path: Path,
    tint_rgb: Tuple[int, int, int],
    clothing_rgb: Optional[Tuple[int, int, int]] = None,
    is_dummy: bool = False,
) -> Optional[QPixmap]:
    """Tints a genuine 128x128 RimWorld sprite while keeping ink outlines crisp."""
    if not src_path.exists():
        return None
    with Image.open(src_path) as im:
        arr = np.asarray(im.convert("RGBA"), dtype=np.float32)

    a = arr[:, :, 3:4] / 255.0
    rgb = arr[:, :, :3] / 255.0
    lum = np.mean(rgb, axis=2, keepdims=True)
    # Dark outlines stay ink-dark; bright skin pixels take tint cleanly
    shade = np.clip((lum - 0.14) / 0.86, 0.0, 1.0)
    tr, tg, tb = tint_rgb[0] / 255.0, tint_rgb[1] / 255.0, tint_rgb[2] / 255.0
    tinted = np.zeros_like(rgb)
    tinted[:, :, 0] = rgb[:, :, 0] * tr
    tinted[:, :, 1] = rgb[:, :, 1] * tg
    tinted[:, :, 2] = rgb[:, :, 2] * tb

    if clothing_rgb is not None:
        # Mask middle torso vertically (RimWorld 128x128 body torso sits y ~ 0.44..0.78)
        h, w, _ = rgb.shape
        ys = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
        xs = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :, None]
        torso_mask = np.clip((ys - 0.40) / 0.06, 0.0, 1.0) * np.clip((0.78 - ys) / 0.06, 0.0, 1.0)
        # Keep head/neck collar crisp; leave bright dark lines untouched
        collar = np.clip((np.abs(xs - 0.50) - 0.04) / 0.05, 0.0, 1.0)
        cloth_m = torso_mask * (0.65 + 0.35 * collar) * shade
        cr, cg, cb = clothing_rgb[0] / 255.0, clothing_rgb[1] / 255.0, clothing_rgb[2] / 255.0
        cloth_col = np.zeros_like(rgb)
        cloth_col[:, :, 0] = rgb[:, :, 0] * cr
        cloth_col[:, :, 1] = rgb[:, :, 1] * cg
        cloth_col[:, :, 2] = rgb[:, :, 2] * cb
        tinted = tinted * (1.0 - cloth_m) + cloth_col * cloth_m

        if is_dummy:
            # Add crimson target bullseye rings / cross-stitches onto the dummy torso!
            dx = (xs - 0.50)
            dy = (ys - 0.56)
            dist = np.sqrt(dx * dx + dy * dy)
            ring = (np.abs(dist - 0.085) < 0.015) | (dist < 0.032)
            ring_m = ring.astype(np.float32) * (a > 0.5).astype(np.float32) * shade
            tinted[:, :, 0:1] = tinted[:, :, 0:1] * (1.0 - ring_m) + 0.82 * ring_m
            tinted[:, :, 1:2] = tinted[:, :, 1:2] * (1.0 - ring_m) + 0.16 * ring_m
            tinted[:, :, 2:3] = tinted[:, :, 2:3] * (1.0 - ring_m) + 0.16 * ring_m

    out = np.concatenate([np.clip(tinted * 255.0, 0, 255), arr[:, :, 3:4]], axis=2).astype(np.uint8)
    return pil_to_qpixmap(Image.fromarray(out, "RGBA"))


@dataclass
class FloatingPopup:
    x: float
    y: float
    text: str
    color: QColor
    born: float
    life: float = 1.05
    scale: float = 1.0


@dataclass
class SlashSmear:
    cx: float
    cy: float
    radius: float
    arc_dir: int
    rgb: Tuple[int, int, int]
    core_rgb: Tuple[int, int, int]
    born: float
    life: float = 0.28


SKILLFX_SEQUENCE_MAP: Dict[str, Tuple[str, str, int, int, Tuple[float, float], Tuple[float, float], float, float, bool]] = {
    # skill_id: (texFolder, hitFolder, frameCount, hitCount, (wCells, hCells), (anchorX, anchorY), hitSizeCells, screenDarken, afterimages)
    "sk_abyssal_dragon_cleave": ("PhongLongTram", "PhongLongTramHit", 16, 8, (4.4, 3.2), (0.54, 0.54), 1.85, 0.42, False),
    "sk_phantom_blink": ("BaoTocAnhBo", "BaoTocAnhBoHit", 16, 8, (4.8, 2.9), (0.48, 0.52), 1.85, 0.48, True),
    "sk_cyclone_vortex": ("LongQuyenTanAnh", "LongQuyenTanAnhHit", 18, 8, (3.5, 3.0), (0.50, 0.78), 1.75, 0.45, False),
    "sk_soaring_pierce": ("LongPhongPhaKich", "LongPhongPhaKichHit", 16, 8, (4.6, 3.3), (0.44, 0.68), 1.85, 0.44, False),
    "sk_pentagram_cataclysm": ("NguMangTinhTran", "NguMangTinhTranHit", 20, 10, (3.6, 3.0), (0.50, 0.70), 1.35, 0.62, False),
    "sk_ink_eclipse_ring": ("HacNhatTram", "HacNhatTramHit", 16, 8, (4.3, 2.9), (0.48, 0.54), 1.85, 0.44, False),
    "sk_ink_void_wave": ("ThaiHuTramBa", "ThaiHuTramBaHit", 16, 8, (5.0, 2.7), (0.48, 0.54), 1.95, 0.44, False),
    "sk_ink_void_aegis": ("HacGiapHoThe", "HacGiapHoTheHit", 18, 8, (3.6, 2.95), (0.50, 0.74), 1.65, 0.48, False),
    "sk_ink_shadow_spikes": ("LeAnhPhaToai", "LeAnhPhaToaiHit", 16, 8, (4.4, 3.0), (0.46, 0.70), 1.85, 0.46, False),
    "sk_ink_blood_eclipse": ("HuyetNguyetVoAnh", "HuyetNguyetVoAnhHit", 20, 10, (3.7, 2.9), (0.50, 0.62), 1.45, 0.60, False),
    "sk_wdf_crescent_wave": ("BachNguyetTramBa", "BachNguyetTramBaHit", 16, 8, (5.0, 2.9), (0.48, 0.54), 1.95, 0.44, False),
    "sk_wdf_planetary_cleave": ("TinhCauBungNo", "TinhCauBungNoHit", 18, 8, (4.8, 3.1), (0.48, 0.54), 2.05, 0.52, False),
    "sk_wdf_twin_dragon_aegis": ("SongLongHoGiap", "SongLongHoGiapHit", 18, 8, (3.8, 3.05), (0.50, 0.72), 1.70, 0.46, False),
    "sk_wdf_dragon_dash": ("BachLongXungKich", "BachLongXungKichHit", 16, 8, (5.0, 2.9), (0.48, 0.52), 1.95, 0.48, True),
    "sk_wdf_cataclysm_5x5": ("AmDuongDietGioi", "AmDuongDietGioiHit", 20, 10, (4.4, 3.5), (0.50, 0.74), 2.25, 0.64, False),
}

SKILL_SHORT_LABELS: Dict[str, str] = {
    "sk_abyssal_dragon_cleave": "① Phong Long Trảm",
    "sk_phantom_blink": "② Bạo Tốc Ảnh Bộ",
    "sk_cyclone_vortex": "③ Long Quyển Tàn Ảnh",
    "sk_soaring_pierce": "④ Long Phong Phá Kích",
    "sk_pentagram_cataclysm": "⑤ Ngũ Mang Tinh Trận",
    "sk_ink_eclipse_ring": "① Hắc Nhật Trảm",
    "sk_ink_void_wave": "② Thái Hư Trảm Ba",
    "sk_ink_void_aegis": "③ Hắc Giáp Hộ Thể",
    "sk_ink_shadow_spikes": "④ Lệ Ảnh Phá Toái",
    "sk_ink_blood_eclipse": "⑤ Huyết Nguyệt Vô Ảnh",
    "sk_wdf_crescent_wave": "① Bạch Nguyệt Trảm Ba",
    "sk_wdf_planetary_cleave": "② Tinh Cầu Bùng Nổ",
    "sk_wdf_twin_dragon_aegis": "③ Song Long Hộ Giáp",
    "sk_wdf_dragon_dash": "④ Bạch Long Xung Kích",
    "sk_wdf_cataclysm_5x5": "⑤ Âm Dương Diệt Giới 5x5",
}


class RimWorldCombatArenaCanvas(QWidget):
    """60 FPS RimWorld 2-Pawn Duel Arena running SQUISHY Melee keyframes & combos."""

    def __init__(self, mod_root: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(255)
        self.mod_root = Path(mod_root)
        self.squishy_tex_root = self._find_squishy_textures()
        self.routines = load_squishy_routines(self._find_routines_xml())

        self._result: Optional[ComposedResult] = None
        self._weapon_pixmap: Optional[QPixmap] = None
        self._aura_pixmap: Optional[QPixmap] = None
        self._element: ElementDef = BUILTIN_ELEMENTS[0]
        self._socket_gem: bool = True
        self._vfx_intensity: float = 1.25
        self._base_damage: float = 22.0
        self._cooldown_sec: float = 2.4

        self._body_type: str = "Male"
        self._selected_routine_id: str = "combo_whirl_flurry"
        self._allowed_exclusive_skills: List[str] = []
        self._auto_loop: bool = False
        self._skill_queue: List[str] = []
        self._mirror_flip: int = 1
        self._combo_count: int = 0
        self._total_dmg: float = 0.0
        self._dummy_hp: int = 500
        self._max_dummy_hp: int = 500

        # Active attack timeline state (ticks at 60 TPS like RimWorld!)
        self._playing: bool = False
        self._atk_routine: Optional[RoutineDef] = None
        self._atk_start: float = 0.0
        self._atk_total_ticks: float = 48.0
        self._hit_freeze_until: float = 0.0
        self._frozen_tick: float = 0.0
        self._strike_schedule: List[Tuple[float, StrikeSpec]] = []
        self._fired_strikes: set[int] = set()
        self._next_auto_time: float = 0.0

        # Dummy hit reaction spring physics (Compress -> Stretch -> Bounce)
        self._dummy_hit_time: float = -10.0
        self._dummy_hit_amp: float = 1.0
        self._dummy_flash: float = 0.0
        self._screen_shake: float = 0.0

        self._popups: List[FloatingPopup] = []
        self._smears: List[SlashSmear] = []
        self._active_hit_bursts: List[Tuple[str, float, float, float, float]] = []
        self._sprite_cache: Dict[tuple, Tuple[Optional[QPixmap], Optional[QPixmap]]] = {}
        self._dummy_cache: Optional[Tuple[Optional[QPixmap], Optional[QPixmap]]] = None
        self._skillfx_root = self._find_skillfx_root()
        self._skillfx_cache: Dict[str, List[QPixmap]] = {}

        self._start_time = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    def _find_skillfx_root(self) -> Path:
        for cand in [
            self.mod_root.parent / "OvergearedCore" / "Textures" / "OvergearedCore" / "SkillFx",
            Path(r"d:\1IDK\OvergearedCore\Textures\OvergearedCore\SkillFx"),
        ]:
            if cand.exists():
                return cand
        return Path(r"d:\1IDK\OvergearedCore\Textures\OvergearedCore\SkillFx")

    def _get_skillfx_frames(self, folder: str, count: int) -> List[QPixmap]:
        if folder in self._skillfx_cache:
            return self._skillfx_cache[folder]
        frames: List[QPixmap] = []
        fdir = self._skillfx_root / folder
        if fdir.exists():
            for i in range(count):
                fp = fdir / f"{i:02d}.png"
                if fp.exists():
                    frames.append(QPixmap(str(fp)))
        self._skillfx_cache[folder] = frames
        return frames

    def _find_squishy_textures(self) -> Path:
        for cand in [
            self.mod_root.parent / "SquishyRanged" / "Textures" / "HolsterPreview",
            Path(r"d:\1IDK\SquishyRanged\Textures\HolsterPreview"),
        ]:
            if cand.exists():
                return cand
        return Path(r"d:\1IDK\SquishyRanged\Textures\HolsterPreview")

    def _find_routines_xml(self) -> Path:
        for cand in [
            self.mod_root.parent / "SquishyMelee" / "Settings" / "Routines.xml",
            Path(r"d:\1IDK\SquishyMelee\Settings\Routines.xml"),
        ]:
            if cand.exists():
                return cand
        return Path(r"d:\1IDK\SquishyMelee\Settings\Routines.xml")

    def set_weapon(
        self,
        result: ComposedResult,
        element: ElementDef,
        socket_gem: bool = True,
        vfx_intensity: float = 1.25,
        base_damage: float = 22.0,
        cooldown_sec: float = 2.4,
    ) -> None:
        self._result = result
        self._element = element
        self._socket_gem = socket_gem
        self._vfx_intensity = vfx_intensity
        self._base_damage = base_damage
        self._cooldown_sec = max(0.8, cooldown_sec)
        self._weapon_pixmap = pil_to_qpixmap(result.image_rgba)
        if element.id > 0:
            # Reuse contour bloom around blade
            from forge_canvas import _build_blade_aura_pixmap
            self._aura_pixmap, _ = _build_blade_aura_pixmap(
                result.blade_mask_alpha, element.primary_rgb, element.secondary_rgb
            )
        else:
            self._aura_pixmap = None
        self.update()

    def set_body_type(self, body_type: str) -> None:
        if body_type in BODY_TYPES:
            self._body_type = body_type
            self.update()

    def set_routine_id(self, rid: str) -> None:
        self._selected_routine_id = rid

    def set_exclusive_skills(self, skill_ids: Optional[List[str]]) -> None:
        self._allowed_exclusive_skills = list(skill_ids) if skill_ids else []
        if self._allowed_exclusive_skills:
            self._selected_routine_id = self._allowed_exclusive_skills[0]
        elif self._selected_routine_id.startswith("sk_"):
            self._selected_routine_id = "combo_whirl_flurry"

    def set_auto_loop(self, enabled: bool) -> None:
        self._auto_loop = enabled
        if enabled and not self._playing:
            self.trigger_attack()

    def trigger_skill_sequence(self, skill_ids: List[str]) -> None:
        if not skill_ids:
            return
        self._skill_queue = list(skill_ids[1:])
        self._selected_routine_id = skill_ids[0]
        self.trigger_attack(override_rid=skill_ids[0])

    def reset_dummy(self) -> None:
        self._dummy_hp = self._max_dummy_hp
        self._total_dmg = 0.0
        self._combo_count = 0
        self._skill_queue.clear()
        self._popups.clear()
        self.update()

    def trigger_attack(self, force_combo: bool = False, override_rid: Optional[str] = None) -> None:
        now = time.monotonic()
        rid_req = override_rid or self._selected_routine_id
        r: Optional[RoutineDef] = None
        if rid_req == "__auto__":
            allowed_set = set(self._allowed_exclusive_skills)
            pool = [
                rt for rt in self.routines
                if (not rt.id.startswith("sk_") or rt.id in allowed_set) and (not force_combo or rt.combo)
            ]
            if not pool:
                pool = self.routines
            weights = [max(0.1, rt.weight) for rt in pool]
            r = random.choices(pool, weights=weights, k=1)[0]
        else:
            for rt in self.routines:
                if rt.id == rid_req:
                    r = rt
                    break
            if r is None and self.routines:
                r = self.routines[0]
        if r is None:
            return

        if r.mirror:
            self._mirror_flip *= -1
        else:
            self._mirror_flip = 1

        self._atk_routine = r
        self._atk_start = now
        self._hit_freeze_until = 0.0
        self._frozen_tick = 0.0
        self._fired_strikes.clear()
        self._active_hit_bursts.clear()
        self._smears.clear()
        self._playing = True

        self._strike_schedule = []
        cum_t = 0.0
        for st in r.strikes:
            cum_t += st.gap
            self._strike_schedule.append((cum_t, st))
        pre_s = abs(r.pre[0].t) if r.pre else 24.0
        post_e = max((cum_t + 16.0), (r.post[-1].t + cum_t) if r.post else 28.0)
        self._atk_total_ticks = pre_s + post_e
        self.update()

    def _get_pawn_pixmaps(self, body_type: str, is_dummy: bool = False) -> Tuple[Optional[QPixmap], Optional[QPixmap]]:
        if is_dummy:
            if self._dummy_cache is not None:
                return self._dummy_cache
            bp = self.squishy_tex_root / "Bodies" / "Naked_Male_east.png"
            hp = self.squishy_tex_root / "Heads" / "Male" / "Male_Average_Normal_east.png"
            b_pix = _tint_pawn_sprite(bp, (198, 168, 122), clothing_rgb=(162, 132, 86), is_dummy=True)
            h_pix = _tint_pawn_sprite(hp, (192, 162, 118))
            self._dummy_cache = (b_pix, h_pix)
            return self._dummy_cache

        key = (body_type, "east")
        if key in self._sprite_cache:
            return self._sprite_cache[key]
        is_fem = (body_type == "Female")
        bp = self.squishy_tex_root / "Bodies" / f"Naked_{body_type}_east.png"
        gender_dir = "Female" if is_fem else "Male"
        hp = self.squishy_tex_root / "Heads" / gender_dir / f"{gender_dir}_Average_Normal_east.png"
        b_pix = _tint_pawn_sprite(bp, (242, 198, 162), clothing_rgb=(74, 102, 124), is_dummy=False)
        h_pix = _tint_pawn_sprite(hp, (244, 202, 166))
        self._sprite_cache[key] = (b_pix, h_pix)
        return self._sprite_cache[key]

    @staticmethod
    def _eval_keys(keys: List[MotionKey], t_tick: float) -> MotionKey:
        if not keys:
            return MotionKey(t_tick)
        if t_tick <= keys[0].t:
            return keys[0]
        if t_tick >= keys[-1].t:
            return keys[-1]
        for i in range(len(keys) - 1):
            k0, k1 = keys[i], keys[i + 1]
            if k0.t <= t_tick <= k1.t:
                span = max(1e-4, k1.t - k0.t)
                u = (t_tick - k0.t) / span
                # Smoothstep easing (extra dampened if stop=True)
                s = u * u * (3.0 - 2.0 * u)
                return MotionKey(
                    t=t_tick,
                    sw=k0.sw + (k1.sw - k0.sw) * s,
                    up=k0.up + (k1.up - k0.up) * s,
                    wx=k0.wx + (k1.wx - k0.wx) * s,
                    push=k0.push + (k1.push - k0.push) * s,
                    lean=k0.lean + (k1.lean - k0.lean) * s,
                    sy=k0.sy + (k1.sy - k0.sy) * s,
                    sx=k0.sx + (k1.sx - k0.sx) * s,
                    hop=k0.hop + (k1.hop - k0.hop) * s,
                    head=k0.head + (k1.head - k0.head) * s,
                    pt=k0.pt + (k1.pt - k0.pt) * s,
                )
        return keys[-1]

    def _compute_attacker_pose(self, now: float, cell_px: float) -> Tuple[MotionKey, int, float]:
        """Returns (MotionKey in Squishy units, current arc_dir, swing_vel)."""
        idle_breath = math.sin(now * 2.5)
        if not self._playing or self._atk_routine is None:
            return MotionKey(0.0, sw=idle_breath * 2.5, sy=idle_breath * 0.015, sx=-idle_breath * 0.012, up=idle_breath * 0.01), 1, 0.0

        r = self._atk_routine
        pre_start = r.pre[0].t if r.pre else -24.0
        last_strike_t = self._strike_schedule[-1][0] if self._strike_schedule else 0.0
        post_end = max(last_strike_t + 16.0, r.post[-1].t if r.post else 28.0)

        if now < self._hit_freeze_until:
            t_tick = self._frozen_tick
        else:
            if self._hit_freeze_until > 0.0:
                # Advance past hitstop smoothly
                self._atk_start += (self._hit_freeze_until - self._atk_start) - (self._frozen_tick - pre_start) / 60.0
                self._hit_freeze_until = 0.0
            t_tick = pre_start + (now - self._atk_start) * 60.0

        # Trigger scheduled strikes on impact tick!
        active_arc = self._mirror_flip
        for idx, (st_t, st) in enumerate(self._strike_schedule):
            if t_tick >= st_t:
                active_arc = st.arc * self._mirror_flip
                if idx not in self._fired_strikes:
                    self._fired_strikes.add(idx)
                    self._on_strike_land(now, idx, st, cell_px)
                    if st.hold > 0:
                        self._frozen_tick = st_t
                        self._hit_freeze_until = now + (st.hold * 0.60) / 60.0

        if t_tick >= post_end:
            self._playing = False
            if self._skill_queue:
                next_sk = self._skill_queue.pop(0)
                self._selected_routine_id = next_sk
                self.trigger_attack(override_rid=next_sk)
                return self._compute_attacker_pose(now, cell_px)
            self._next_auto_time = now + min(1.0, max(0.32, self._cooldown_sec * 0.32))
            return MotionKey(0.0), 1, 0.0

        if t_tick <= 0.0 and r.pre:
            pose = self._eval_keys(r.pre, t_tick)
            if r.mirror and self._mirror_flip < 0 and r.hit.pt < 0.7:
                # Reverse slash windup comes up from low forward (+115 deg) rather than behind attacker!
                pose.sw = 115.0 - pose.sw * 0.25
            return pose, active_arc, 0.0

        # Handle single or multi-hit Strike progression between t=0 and last_strike_t
        if self._strike_schedule and t_tick <= last_strike_t + 5.0:
            cur_idx = 0
            for idx, (st_t, _) in enumerate(self._strike_schedule):
                if t_tick >= st_t - 4.0:
                    cur_idx = idx
            st_t, st = self._strike_schedule[cur_idx]
            dt = t_tick - st_t
            arc_s = float(st.arc * self._mirror_flip)
            is_thrust = (r.hit.pt >= 0.75)

            if is_thrust:
                # Forward horizontal thrust toward dummy (+X)
                thrust_sw = 64.0
                if dt < 0.0:
                    u = max(0.0, min(1.0, (dt + 6.0) / 6.0))
                    sw_v = thrust_sw - 10.0 * (1.0 - u)
                    wx_v = -0.18 * st.pull * (1.0 - u) + r.hit.wx * u
                else:
                    decay = math.exp(-dt * 0.18)
                    sw_v = thrust_sw + 6.0 * (1.0 - decay)
                    wx_v = r.hit.wx * decay
            elif arc_s >= 0.0:
                # Downward forward cleave: sweeps from -25 deg (high front) through +95 deg (forward cut!)
                sw_start = -25.0
                sw_end = min(112.0, abs(r.hit.sw) * min(1.22, st.amp))
                if dt < 0.0:
                    u = max(0.0, min(1.0, (dt + 5.0) / 5.0))
                    sw_v = sw_start + (sw_end * 0.45 - sw_start) * u
                    wx_v = r.hit.wx * u - st.pull * 0.12 * (1.0 - u)
                else:
                    decay = math.exp(-dt * 0.22)
                    sw_v = sw_end * (0.65 + 0.35 * (1.0 - decay))
                    wx_v = r.hit.wx * decay
            else:
                # Reverse upward forward cut: sweeps from +124 deg (low front) up through +28 deg (still in FRONT +X!)
                sw_start = 124.0
                sw_end = 28.0
                if dt < 0.0:
                    u = max(0.0, min(1.0, (dt + 5.0) / 5.0))
                    sw_v = sw_start + (86.0 - sw_start) * u
                    wx_v = r.hit.wx * u - st.pull * 0.12 * (1.0 - u)
                else:
                    decay = math.exp(-dt * 0.22)
                    sw_v = 86.0 + (sw_end - 86.0) * (1.0 - decay)
                    wx_v = r.hit.wx * decay

            if dt < 0.0:
                u = max(0.0, min(1.0, (dt + 5.0) / 5.0))
                pose = MotionKey(
                    t_tick,
                    sw=sw_v,
                    wx=wx_v,
                    push=min(0.45, r.hit.push * st.push * (0.4 + 0.6 * u)),
                    lean=r.hit.lean * (0.3 + 0.7 * u),
                    sy=r.hit.sy * u,
                    sx=r.hit.sx * u,
                    hop=r.hit.hop,
                    up=r.hit.up,
                    head=r.hit.head * u,
                    pt=0.0 if not is_thrust else r.hit.pt,
                )
            else:
                decay = math.exp(-dt * 0.20)
                pose = MotionKey(
                    t_tick,
                    sw=sw_v,
                    wx=wx_v,
                    push=min(0.45, r.hit.push * st.push * (0.65 + 0.35 * decay)),
                    lean=r.hit.lean * (0.45 + 0.55 * decay),
                    sy=r.hit.sy * decay,
                    sx=r.hit.sx * decay,
                    hop=r.hit.hop * max(0.0, 1.0 - dt * 0.08),
                    up=r.hit.up * (0.6 + 0.4 * decay),
                    head=r.hit.head * decay,
                    pt=0.0 if not is_thrust else r.hit.pt * decay,
                )
            return pose, int(arc_s if arc_s != 0 else 1), abs(r.hit.sw)

        # Follow-through Post keys returning smoothly to ready guard
        if r.post:
            base_post_sw = 92.0 if active_arc >= 0 else 36.0
            shifted_post = [MotionKey(k.t + last_strike_t, k.sw * (0.35 if active_arc >= 0 else -0.25), k.up, k.wx, k.push, k.lean, k.sy, k.sx, k.hop, k.head, k.pt) for k in r.post]
            hit_anchor = MotionKey(
                last_strike_t, base_post_sw, r.hit.up, r.hit.wx * 0.4,
                min(0.4, r.hit.push * 0.4), r.hit.lean * 0.4, 0.0, 0.0, 0.0, r.hit.head * 0.3, 0.0,
            )
            return self._eval_keys([hit_anchor] + shifted_post, t_tick), active_arc, 0.0
        return r.hit, active_arc, 0.0

    @staticmethod
    def _arena_metrics(w: float, h: float) -> Tuple[float, float, float, float]:
        cell_px = min(78.0, max(44.0, min(h * 0.28, w * 0.125)))
        atk_base_x = w * 0.5 - cell_px * 1.15
        dummy_base_x = w * 0.5 + cell_px * 1.15
        ground_y = h * 0.77
        return cell_px, atk_base_x, dummy_base_x, ground_y

    def _on_strike_land(self, now: float, strike_idx: int, st: StrikeSpec, cell_px: float) -> None:
        self._dummy_hit_time = now
        self._dummy_hit_amp = st.amp
        self._dummy_flash = 1.0
        self._screen_shake = min(5.5, 3.2 * st.amp)
        self._combo_count += 1

        dmg = round(self._base_damage * st.amp * (1.0 + 0.06 * min(5, strike_idx)), 1)
        elem_dmg = self._element.damage if self._element.id > 0 else 0
        self._total_dmg += dmg + elem_dmg
        self._dummy_hp -= int(round(dmg + elem_dmg))
        if self._dummy_hp <= 0:
            self._dummy_hp = self._max_dummy_hp

        w, h = float(self.width()), float(self.height())
        cell_m, _, dummy_x, ground_y = self._arena_metrics(w, h)

        # Clean staggered stair offsets & combined label so multi-hit popups never overlap!
        slot = self._combo_count % 4
        x_stagger = (-22.0, 26.0, -8.0, 34.0)[slot]
        y_stagger = (1.06, 1.24, 1.42, 1.60)[slot]
        col_main = QColor(255, 224, 130) if st.amp >= 1.15 else QColor(242, 246, 250)
        txt = f"-{dmg:.0f}" + (f" (+{elem_dmg})" if elem_dmg > 0 else "") + (" CRIT!" if st.amp >= 1.25 else "")
        self._popups.append(FloatingPopup(
            dummy_x + x_stagger,
            ground_y - cell_m * y_stagger,
            txt,
            col_main,
            now,
            life=0.85,
            scale=1.14 if st.amp >= 1.2 else 0.98,
        ))
        if len(self._popups) > 4:
            self._popups = self._popups[-4:]

        pr = self._element.primary_rgb if self._element.id > 0 else (210, 225, 240)
        sr = self._element.secondary_rgb if self._element.id > 0 else (255, 255, 255)
        rid = self._atk_routine.id if self._atk_routine else ""
        if rid in SKILLFX_SEQUENCE_MAP:
            _, hit_folder, _, _, _, _, hit_sz_c, _, _ = SKILLFX_SEQUENCE_MAP[rid]
            jx = (-0.18, 0.16, 0.0, -0.10, 0.12)[strike_idx % 5]
            jy = (-0.10, 0.08, -0.18, 0.12, 0.0)[strike_idx % 5]
            self._active_hit_bursts.append((hit_folder, jx, -0.56 + jy, now, max(0.85, st.amp)))
        else:
            self._smears.append(SlashSmear(
                cx=dummy_x - cell_m * 0.34,
                cy=ground_y - cell_m * 0.56,
                radius=cell_m * 0.72 * min(1.25, st.amp),
                arc_dir=st.arc * self._mirror_flip,
                rgb=pr,
                core_rgb=sr,
                born=now,
            ))

    def _draw_pawn(
        self,
        p: QPainter,
        cx: float,
        ground_y: float,
        cell_px: float,
        body_pix: Optional[QPixmap],
        head_pix: Optional[QPixmap],
        sx_mod: float,
        sy_mod: float,
        lean_deg: float,
        head_deg: float,
        facing: int,
        flash: float = 0.0,
        fallback_is_dummy: bool = False,
    ) -> Tuple[float, float]:
        """Draws a real RimWorld Pawn anchored at feet (cx, ground_y). Returns shoulder/hand origin."""
        # Shadow ellipse on ground tile
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 95))
        p.drawEllipse(QPointF(cx, ground_y + 2), cell_px * 0.36, cell_px * 0.11)
        p.restore()

        p.save()
        p.translate(cx, ground_y)
        p.rotate(lean_deg * facing)
        p.scale(facing * (1.0 + sx_mod), 1.0 + sy_mod)

        # RimWorld 128x128 body covers ~1.30 cells vertically, feet around bottom ~20% margin
        spr_px = cell_px * 1.42
        body_rect = QRectF(-spr_px * 0.5, -spr_px * 0.92, spr_px, spr_px).toRect()
        head_rect = QRectF(-spr_px * 0.5, -spr_px * 1.18, spr_px, spr_px).toRect()

        if body_pix is not None:
            p.drawPixmap(body_rect, body_pix)
        else:
            # Clean fallback if SquishyRanged assets aren't mounted
            p.setPen(QPen(QColor(18, 20, 22), 2.5))
            p.setBrush(QColor(162, 132, 86) if fallback_is_dummy else QColor(74, 102, 124))
            p.drawRoundedRect(QRectF(-cell_px * 0.24, -cell_px * 0.72, cell_px * 0.48, cell_px * 0.62), 10, 10)

        p.save()
        p.translate(0.0, -cell_px * 0.62)
        p.rotate(head_deg)
        p.translate(0.0, cell_px * 0.62)
        if head_pix is not None:
            p.drawPixmap(head_rect, head_pix)
        else:
            p.setPen(QPen(QColor(18, 20, 22), 2.5))
            p.setBrush(QColor(192, 162, 118) if fallback_is_dummy else QColor(244, 202, 166))
            p.drawEllipse(QPointF(0.0, -cell_px * 0.85), cell_px * 0.22, cell_px * 0.23)
        p.restore()

        if flash > 0.05:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            fg = QRadialGradient(QPointF(0.0, -cell_px * 0.48), cell_px * 0.24)
            fg.setColorAt(0.0, QColor(255, 242, 220, int(195 * min(1.0, flash))))
            fg.setColorAt(0.55, QColor(255, 195, 145, int(105 * min(1.0, flash))))
            fg.setColorAt(1.0, QColor(255, 195, 145, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(fg))
            p.drawEllipse(QPointF(0.0, -cell_px * 0.48), cell_px * 0.24, cell_px * 0.26)

        p.restore()
        return (cx + facing * cell_px * 0.16, ground_y - cell_px * 0.44)

    def _draw_dragon_skull_head(
        self,
        p: QPainter,
        x: float,
        y: float,
        angle_deg: float,
        sz: float,
        alpha: float = 1.0,
    ) -> None:
        """Draws a fierce horned Abyssal Dragon-Skull head with swept flame mane (no circular halo)."""
        p.save()
        p.translate(x, y)
        p.rotate(angle_deg)
        p.setOpacity(max(0.0, min(1.0, alpha)))

        # Swept-back violet-black neck & flame mane plumes blending seamlessly into trailing ribbons
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        mane_outer = QPolygonF([
            QPointF(-sz * 0.10, -sz * 0.18),
            QPointF(-sz * 0.78, -sz * 0.34),
            QPointF(-sz * 0.50, -sz * 0.08),
            QPointF(-sz * 0.92, sz * 0.04),
            QPointF(-sz * 0.54, sz * 0.22),
            QPointF(-sz * 0.72, sz * 0.34),
            QPointF(-sz * 0.08, sz * 0.16),
        ])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(175, 48, 242, 165))
        p.drawPolygon(mane_outer)

        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        # Upper cranium + fierce snout + twin curved dragon horns
        upper_skull = QPolygonF([
            QPointF(-sz * 0.54, -sz * 0.44),
            QPointF(-sz * 0.18, -sz * 0.24),
            QPointF(-sz * 0.38, -sz * 0.14),
            QPointF(-sz * 0.06, -sz * 0.12),
            QPointF(sz * 0.24, -sz * 0.24),
            QPointF(sz * 0.60, -sz * 0.05),
            QPointF(sz * 0.46, sz * 0.13),
            QPointF(sz * 0.28, sz * 0.04),
            QPointF(sz * 0.13, sz * 0.14),
            QPointF(-sz * 0.14, sz * 0.06),
        ])
        p.setPen(QPen(QColor(225, 110, 255, 225), max(1.4, sz * 0.045)))
        p.setBrush(QColor(24, 12, 42, 238))
        p.drawPolygon(upper_skull)

        # Lower open jawbone with upward fangs
        lower_jaw = QPolygonF([
            QPointF(-sz * 0.14, sz * 0.12),
            QPointF(sz * 0.38, sz * 0.26),
            QPointF(sz * 0.42, sz * 0.16),
            QPointF(sz * 0.22, sz * 0.34),
            QPointF(-sz * 0.22, sz * 0.26),
        ])
        p.setPen(QPen(QColor(185, 72, 245, 210), max(1.1, sz * 0.040)))
        p.setBrush(QColor(18, 10, 32, 230))
        p.drawPolygon(lower_jaw)

        # Blazing amethyst eye socket + inner core gleam
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 195, 255, 245))
        p.drawPolygon(QPolygonF([
            QPointF(sz * 0.08, -sz * 0.07),
            QPointF(sz * 0.24, -sz * 0.11),
            QPointF(sz * 0.18, -sz * 0.02),
        ]))
        p.restore()

    @staticmethod
    def _draw_crystal_spire(
        p: QPainter,
        bx: float,
        by: float,
        angle_rad: float,
        length: float,
        half_w: float,
        alpha: float = 1.0,
    ) -> None:
        """Draws a sharp obsidian-amethyst crystal prism erupting from ground or air."""
        dx, dy = math.cos(angle_rad), math.sin(angle_rad)
        nx, ny = -dy, dx
        tip = QPointF(bx + dx * length, by + dy * length)
        mid_l = QPointF(bx + dx * length * 0.32 + nx * half_w, by + dy * length * 0.32 + ny * half_w)
        mid_r = QPointF(bx + dx * length * 0.32 - nx * half_w, by + dy * length * 0.32 - ny * half_w)
        base_l = QPointF(bx + nx * half_w * 0.72, by + ny * half_w * 0.72)
        base_r = QPointF(bx - nx * half_w * 0.72, by - ny * half_w * 0.72)

        al = int(max(0, min(255, 235 * alpha)))
        p.save()
        # Left bright amethyst crystal facet
        p.setPen(QPen(QColor(242, 188, 255, al), 1.3))
        p.setBrush(QColor(158, 52, 228, int(al * 0.85)))
        p.drawPolygon(QPolygonF([base_l, mid_l, tip, QPointF(bx, by)]))
        # Right deep obsidian-violet shadow facet
        p.setBrush(QColor(34, 16, 62, int(al * 0.92)))
        p.drawPolygon(QPolygonF([QPointF(bx, by), tip, mid_r, base_r]))
        p.restore()

    def _draw_skullblade_skill_fx(
        self,
        p: QPainter,
        now: float,
        cell_px: float,
        atk_x: float,
        atk_y: float,
        dummy_x: float,
        ground_y: float,
        a_body: Optional[QPixmap],
        a_head: Optional[QPixmap],
    ) -> None:
        """Plays baked multi-frame Fairycore-architecture SkillFx + HitFx sequences & pawn afterimages."""
        if self._playing and self._atk_routine is not None and self._atk_routine.id in SKILLFX_SEQUENCE_MAP:
            rid = self._atk_routine.id
            tex_folder, _, frame_count, _, (w_cells, h_cells), (anch_x, anch_y), _, _, has_afterimages = SKILLFX_SEQUENCE_MAP[rid]

            pre_s = abs(self._atk_routine.pre[0].t) if self._atk_routine.pre else 24.0
            t_tick = pre_s + (now - self._atk_start) * 60.0
            if self._hit_freeze_until > 0.0 and now < self._hit_freeze_until:
                t_tick = pre_s + self._frozen_tick
            u_all = max(0.0, min(1.0, t_tick / max(1.0, self._atk_total_ticks)))
            fade = math.sin(min(1.0, u_all / 0.12) * math.pi * 0.5) * math.sin(min(1.0, (1.0 - u_all) / 0.20) * math.pi * 0.5)
            fade = max(0.0, min(1.0, fade))

            # Spectral pawn afterimage trails spaced behind high-speed dash (violet for Skullblade, ink-black for Trấn Ác, pearl-white+ink for Bạch Long)
            if has_afterimages and (a_body is not None or a_head is not None):
                spr_px = cell_px * 1.40
                ghost_offsets = [(-1.62, 0.28), (-1.08, 0.44), (-0.54, 0.62)]
                is_ink_ghost = rid.startswith("sk_ink_")
                is_wdf_ghost = rid.startswith("sk_wdf_")
                if is_wdf_ghost:
                    ghost_fill = QColor(242, 246, 255, 225)
                elif is_ink_ghost:
                    ghost_fill = QColor(14, 16, 24, 230)
                else:
                    ghost_fill = QColor(148, 62, 245, 195)
                for dx_mul, al_a in ghost_offsets:
                    gx = atk_x + dx_mul * cell_px
                    ghost_img = QPixmap(int(spr_px), int(spr_px * 1.25))
                    ghost_img.fill(Qt.GlobalColor.transparent)
                    gp = QPainter(ghost_img)
                    if a_body is not None:
                        gp.drawPixmap(QRectF(0, spr_px * 0.33, spr_px, spr_px).toRect(), a_body)
                    if a_head is not None:
                        gp.drawPixmap(QRectF(0, spr_px * 0.07, spr_px, spr_px).toRect(), a_head)
                    gp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
                    gp.fillRect(ghost_img.rect(), ghost_fill)
                    gp.end()

                    if is_ink_ghost or is_wdf_ghost:
                        rim_img = QPixmap(int(spr_px), int(spr_px * 1.25))
                        rim_img.fill(Qt.GlobalColor.transparent)
                        rp = QPainter(rim_img)
                        if a_body is not None:
                            rp.drawPixmap(QRectF(0, spr_px * 0.33, spr_px, spr_px).toRect(), a_body)
                        if a_head is not None:
                            rp.drawPixmap(QRectF(0, spr_px * 0.07, spr_px, spr_px).toRect(), a_head)
                        rp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
                        rp.fillRect(rim_img.rect(), QColor(14, 16, 22, 235) if is_wdf_ghost else QColor(215, 226, 248, 225))
                        rp.end()
                        p.save()
                        p.setOpacity(min(0.95, al_a * 1.15) * fade)
                        p.setCompositionMode(
                            QPainter.CompositionMode.CompositionMode_SourceOver if is_wdf_ghost
                            else QPainter.CompositionMode.CompositionMode_Plus
                        )
                        for ox_r, oy_r in ((-2.0, 0.0), (2.0, 0.0), (0.0, -2.0), (0.0, 2.0)):
                            p.drawPixmap(QPointF(gx - spr_px * 0.5 + ox_r, ground_y - spr_px * 1.25 + oy_r), rim_img)
                        p.restore()

                    p.save()
                    p.setOpacity((min(0.95, al_a + 0.25) if (is_ink_ghost or is_wdf_ghost) else al_a) * fade)
                    p.setCompositionMode(
                        QPainter.CompositionMode.CompositionMode_SourceOver if (is_ink_ghost or is_wdf_ghost)
                        else QPainter.CompositionMode.CompositionMode_Plus
                    )
                    p.drawPixmap(QPointF(gx - spr_px * 0.5, ground_y - spr_px * 1.25), ghost_img)
                    p.restore()

            # Play baked multi-frame SkillFx PNG sequence
            frames = self._get_skillfx_frames(tex_folder, frame_count)
            if frames:
                idx = min(len(frames) - 1, max(0, int(u_all * (len(frames) - 1) + 0.001)))
                fx_pix = frames[idx]
                fx_w = w_cells * cell_px
                fx_h = h_cells * cell_px
                if rid in ("sk_pentagram_cataclysm", "sk_ink_blood_eclipse", "sk_wdf_cataclysm_5x5"):
                    anchor_center_x = dummy_x
                elif rid in ("sk_ink_void_aegis", "sk_wdf_twin_dragon_aegis"):
                    anchor_center_x = atk_x
                else:
                    anchor_center_x = (atk_x + dummy_x) * 0.52
                anchor_center_y = ground_y - cell_px * 0.42
                dst = QRectF(
                    anchor_center_x - anch_x * fx_w,
                    anchor_center_y - anch_y * fx_h,
                    fx_w,
                    fx_h,
                )
                p.save()
                if rid in ("sk_cyclone_vortex", "sk_ink_panic_vortex"):
                    p.setOpacity(0.86)
                p.drawPixmap(dst.toRect(), fx_pix)
                p.restore()

        # Render all active HitFx explosion bursts anchored relative to Dummy (45ms/frame)
        hit_scale_cells = 1.80
        if self._atk_routine is not None and self._atk_routine.id in SKILLFX_SEQUENCE_MAP:
            hit_scale_cells = SKILLFX_SEQUENCE_MAP[self._atk_routine.id][6]
        alive_hits: List[Tuple[str, float, float, float, float]] = []
        for h_folder, ox_c, oy_c, born, h_amp in self._active_hit_bursts:
            h_frames = self._get_skillfx_frames(h_folder, 10)
            if not h_frames:
                h_frames = self._get_skillfx_frames(h_folder, 8)
            if not h_frames:
                continue
            h_idx = int((now - born) * 1000.0 / 45.0)
            if h_idx >= len(h_frames):
                continue
            alive_hits.append((h_folder, ox_c, oy_c, born, h_amp))
            h_sz = cell_px * hit_scale_cells * min(1.30, h_amp)
            hx = dummy_x + ox_c * cell_px
            hy = ground_y + oy_c * cell_px
            p.save()
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            p.drawPixmap(QRectF(hx - h_sz * 0.5, hy - h_sz * 0.5, h_sz, h_sz).toRect(), h_frames[h_idx])
            p.restore()
        self._active_hit_bursts = alive_hits

    def paintEvent(self, event) -> None:
        now = time.monotonic()
        if self._auto_loop and not self._playing and now >= self._next_auto_time:
            self.trigger_attack()

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        w, h = float(self.width()), float(self.height())
        cell_px, atk_base_x, dummy_base_x, ground_y = self._arena_metrics(w, h)

        # Decay screen shake & dummy flash smoothly
        self._screen_shake *= 0.84
        self._dummy_flash *= 0.80
        shake_x = math.sin(now * 58.0) * self._screen_shake
        shake_y = math.cos(now * 47.0) * self._screen_shake * 0.6

        # 1) RimWorld colony stone floor grid backdrop
        p.fillRect(0, 0, int(w), int(h), QColor(18, 22, 24))
        p.save()
        p.translate(shake_x, shake_y)
        tile_sz = cell_px * 0.85
        start_x = (w * 0.5) % tile_sz - tile_sz
        floor_y = h * 0.66
        p.fillRect(QRectF(-20, floor_y - 24, w + 40, h - floor_y + 40), QColor(28, 34, 36))
        p.setPen(QPen(QColor(44, 52, 55), 1))
        x = start_x
        while x < w + 20:
            p.drawLine(QPointF(x, floor_y - 24), QPointF(x, h + 20))
            x += tile_sz
        p.drawLine(QPointF(0, floor_y + 18), QPointF(w, floor_y + 18))

        # Fairycore dramatic arena screen-darken veil during active SkillFx ultimate/movesets
        if self._playing and self._atk_routine is not None and self._atk_routine.id in SKILLFX_SEQUENCE_MAP:
            _, _, _, _, _, _, _, screen_darken, _ = SKILLFX_SEQUENCE_MAP[self._atk_routine.id]
            pre_s = abs(self._atk_routine.pre[0].t) if self._atk_routine.pre else 24.0
            t_tick = pre_s + (now - self._atk_start) * 60.0
            if self._hit_freeze_until > 0.0 and now < self._hit_freeze_until:
                t_tick = pre_s + self._frozen_tick
            u_env = max(0.0, min(1.0, t_tick / max(1.0, self._atk_total_ticks)))
            env = math.sin(min(1.0, u_env / 0.14) * math.pi * 0.5) * math.sin(min(1.0, (1.0 - u_env) / 0.22) * math.pi * 0.5)
            p.fillRect(QRectF(-20, -20, w + 40, h + 40), QColor(6, 2, 14, int(255 * screen_darken * max(0.0, env))))

        # 2) Compute Attacker SQUISHY pose & Dummy Compress -> Stretch -> Bounce reaction
        pose, arc_dir, _ = self._compute_attacker_pose(now, cell_px)
        dt_hit = max(0.0, now - self._dummy_hit_time)
        if dt_hit < 0.45:
            u = dt_hit / 0.45
            d_bounce = math.sin(u * math.pi * 3.0) * math.exp(-u * 4.5) * 0.20 * self._dummy_hit_amp
            d_push = math.exp(-u * 6.0) * 0.22 * self._dummy_hit_amp * cell_px
            d_lean = math.exp(-u * 5.0) * 14.0 * self._dummy_hit_amp
            d_sx = d_bounce
            d_sy = -d_bounce * 0.85
        else:
            d_push = d_lean = d_sx = d_sy = 0.0

        # Draw wooden training dummy post anchored into the ground BEHIND dummy body
        post_x = dummy_base_x + d_push * 0.45
        p.setPen(QPen(QColor(32, 22, 14), 1.5))
        p.setBrush(QColor(96, 66, 42))
        p.drawRect(QRectF(post_x - 4, ground_y - cell_px * 0.30, 8, cell_px * 0.32))
        p.drawRoundedRect(QRectF(post_x - cell_px * 0.24, ground_y - 2, cell_px * 0.48, 6), 2, 2)

        # Draw Target Dummy Pawn (right)
        d_body, d_head = self._get_pawn_pixmaps("Male", is_dummy=True)
        self._draw_pawn(
            p, dummy_base_x + d_push, ground_y, cell_px, d_body, d_head,
            sx_mod=d_sx, sy_mod=d_sy, lean_deg=d_lean, head_deg=d_lean * 0.6,
            facing=-1, flash=self._dummy_flash, fallback_is_dummy=True,
        )

        # Draw Attacker RimWorld Pawn (left)
        a_body, a_head = self._get_pawn_pixmaps(self._body_type, is_dummy=False)
        atk_x = atk_base_x + pose.push * cell_px * 1.15
        atk_y = ground_y - pose.hop * cell_px * 1.25
        hand_x, hand_y = self._draw_pawn(
            p, atk_x, atk_y, cell_px, a_body, a_head,
            sx_mod=pose.sx * 1.2, sy_mod=pose.sy * 1.2, lean_deg=pose.lean * 1.15,
            head_deg=pose.head, facing=1, flash=0.0, fallback_is_dummy=False,
        )

        # 3) Draw Weapon in Attacker's Hand + Active Aura + RimWorld Hand Dot
        if self._weapon_pixmap is not None and self._result is not None:
            draw_px = self._result.draw_size * cell_px * 1.08
            grip_off = (self._result.grip_y_norm - 0.5) * draw_px
            wx = hand_x + (0.20 + pose.wx * 0.95) * cell_px
            wy = hand_y - pose.up * cell_px * 1.15
            w_angle = self._result.equipped_angle + pose.sw + (pose.pt * (65.0 - self._result.equipped_angle))

            p.save()
            p.translate(wx, wy)
            p.rotate(w_angle)
            dst_rect = QRectF(-draw_px * 0.5, -draw_px * 0.5 + grip_off, draw_px, draw_px).toRect()

            if self._element.id > 0 and self._aura_pixmap is not None:
                p.save()
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
                p.setOpacity(min(0.95, 0.72 * self._vfx_intensity))
                p.drawPixmap(dst_rect, self._aura_pixmap)
                p.restore()

            p.drawPixmap(dst_rect, self._weapon_pixmap)

            # Active stylized guard flare / sparkle hint on held weapon
            if self._element.id > 0 and self._socket_gem:
                gem_y = (0.5 - self._result.socket_gem_y_norm) * draw_px + grip_off
                sr, sg, sb = self._element.secondary_rgb
                pr, pg, pb = self._element.primary_rgb
                rad_g = max(3.5, draw_px * 0.045)
                gg = QRadialGradient(QPointF(0.0, gem_y), rad_g * 2.2)
                gg.setColorAt(0.0, QColor(sr, sg, sb, 230))
                gg.setColorAt(0.5, QColor(pr, pg, pb, 120))
                gg.setColorAt(1.0, QColor(pr, pg, pb, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(gg))
                p.drawEllipse(QPointF(0.0, gem_y), rad_g * 2.2, rad_g * 2.2)

            p.restore()

            # Authentic Show-Me-Your-Hands / SquishyMelee hand gripping weapon handle
            p.setPen(QPen(QColor(18, 20, 22), 1.6))
            p.setBrush(QColor(242, 198, 162))
            p.drawEllipse(QPointF(wx, wy), max(4.2, cell_px * 0.072), max(4.2, cell_px * 0.072))

        # 4) Active Slash Smear Arcs on Impact
        alive_smears: List[SlashSmear] = []
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        for sm in self._smears:
            age = (now - sm.born) / sm.life
            if age >= 1.0:
                continue
            alive_smears.append(sm)
            fade = (1.0 - age) ** 1.4
            pts_o: List[QPointF] = []
            pts_i: List[QPointF] = []
            ang0 = -0.95 if sm.arc_dir > 0 else 0.95
            ang1 = 0.85 if sm.arc_dir > 0 else -0.85
            for k in range(18):
                u = k / 17.0
                th = ang0 + (ang1 - ang0) * u
                w_arc = math.sin(u * math.pi) * cell_px * 0.22 * (1.0 - 0.5 * age)
                ro = sm.radius
                ri = max(4.0, ro - w_arc)
                pts_o.append(QPointF(sm.cx + math.cos(th) * ro, sm.cy + math.sin(th) * ro))
                pts_i.append(QPointF(sm.cx + math.cos(th) * ri, sm.cy + math.sin(th) * ri))
            poly = QPolygonF(pts_o + list(reversed(pts_i)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(*sm.rgb, int(195 * fade)))
            p.drawPolygon(poly)
            p.setBrush(QColor(*sm.core_rgb, int(235 * fade)))
            p.drawPolygon(poly)
        p.restore()
        self._smears = alive_smears

        # 5) Exclusive Skullblade 5-Skill Special Effects (baked multi-frame SkillFx + HitFx + afterimages)
        self._draw_skullblade_skill_fx(p, now, cell_px, atk_x, atk_y, dummy_base_x + d_push, ground_y, a_body, a_head)

        # 5.5) Floating Damage & Elemental Popups (rendered strictly ABOVE VFX so numbers stay legible!)
        alive_popups: List[FloatingPopup] = []
        for pop in self._popups:
            age = (now - pop.born) / pop.life
            if age >= 1.0:
                continue
            alive_popups.append(pop)
            al = int(255 * min(1.0, (1.0 - age) * 1.4))
            p.setFont(_get_arena_font(int(13 * pop.scale), bold=True))
            py = pop.y - age * cell_px * 0.55
            c = QColor(pop.color.red(), pop.color.green(), pop.color.blue(), al)
            outline_c = QColor(8, 10, 14, al)
            p.setPen(outline_c)
            for dx_t, dy_t in ((-1.2, 0.0), (1.2, 0.0), (0.0, -1.2), (0.0, 1.2), (1.5, 1.5)):
                p.drawText(QPointF(pop.x + dx_t, py + dy_t), pop.text)
            p.setPen(c)
            p.drawText(QPointF(pop.x, py), pop.text)
        self._popups = alive_popups
        p.restore()

        # 6) Compact Arena HUD Bar (Routine, Combo Counter, Dummy HP)
        p.setFont(_get_arena_font(12, bold=False))
        p.setPen(QColor(195, 206, 210))
        r_label = self._atk_routine.id if (self._playing and self._atk_routine) else self._selected_routine_id
        hud_left = f"Pawn ({self._body_type}) vs Bù Nhìn · Moveset: {r_label} · Tổng Dmg: {self._total_dmg:.0f}"
        if self._combo_count > 1:
            hud_left += f" · COMBO x{self._combo_count}"
        p.drawText(QRectF(10, 6, w - 165, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, hud_left)

        # Dummy HP bar
        hp_w = 135.0
        hp_x = w - hp_w - 12.0
        p.setPen(QPen(QColor(55, 65, 68), 1))
        p.setBrush(QColor(22, 26, 28))
        p.drawRoundedRect(QRectF(hp_x, 8, hp_w, 12), 2, 2)
        ratio = max(0.0, min(1.0, self._dummy_hp / float(self._max_dummy_hp)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(196, 62, 62))
        p.drawRoundedRect(QRectF(hp_x + 1, 9, (hp_w - 2) * ratio, 10), 2, 2)
        p.setFont(_get_arena_font(10, bold=True))
        p.setPen(QColor(240, 240, 240))
        p.drawText(QRectF(hp_x, 6, hp_w, 15), Qt.AlignmentFlag.AlignCenter, f"Dummy HP {self._dummy_hp}/{self._max_dummy_hp}")


class RimWorldCombatArenaWidget(QFrame):
    """Full drop-in bottom combat test panel (RimWorld Pawns + SQUISHY Melee moveset player)."""

    def __init__(self, mod_root: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        bar = QHBoxLayout()
        bar.setSpacing(6)

        lbl_m = QLabel("Moveset (SQUISHY Melee):")
        lbl_m.setStyleSheet("color: #f0cc87; font-weight: 700;")
        bar.addWidget(lbl_m)

        self.arena = RimWorldCombatArenaCanvas(mod_root)

        self.combo_routine = QComboBox()
        self.combo_routine.addItem("🎲 Auto Chain (Xoay vòng SQUISHY)", "__auto__")
        for rt in self.arena.routines:
            label = ROUTINE_DISPLAY_NAMES.get(rt.id, rt.id)
            self.combo_routine.addItem(label, rt.id)
        # Default to triple flurry combo so combos shine immediately!
        def_idx = self.combo_routine.findData("combo_whirl_flurry")
        if def_idx >= 0:
            self.combo_routine.setCurrentIndex(def_idx)
        self.combo_routine.currentIndexChanged.connect(self._on_routine_changed)
        bar.addWidget(self.combo_routine, 1)

        bar.addWidget(QLabel("Pawn:"))
        self.combo_body = QComboBox()
        for bt in BODY_TYPES:
            self.combo_body.addItem(bt)
        self.combo_body.currentTextChanged.connect(self.arena.set_body_type)
        bar.addWidget(self.combo_body)

        btn_atk = QPushButton("⚔ Chém / Combo")
        btn_atk.setObjectName("PrimaryBtn")
        btn_atk.clicked.connect(lambda: self.arena.trigger_attack(False))
        bar.addWidget(btn_atk)

        self.chk_auto = QCheckBox("▶ Auto Đấu Tập")
        self.chk_auto.toggled.connect(self.arena.set_auto_loop)
        bar.addWidget(self.chk_auto)

        btn_reset = QPushButton("↺ Reset Dummy")
        btn_reset.clicked.connect(self.arena.reset_dummy)
        bar.addWidget(btn_reset)

        lay.addLayout(bar)

        # Exclusive Special-Weapon Skill Bar (shown only when weapon defines 5 exclusive movesets)
        self.skill_bar_frame = QFrame()
        self.skill_bar_frame.setStyleSheet("background: #1a1424; border: 1px solid #6b3ea8; border-radius: 3px;")
        sb_lay = QHBoxLayout(self.skill_bar_frame)
        sb_lay.setContentsMargins(6, 4, 6, 4)
        sb_lay.setSpacing(4)
        lbl_sk = QLabel("⚔ Skill Riêng:")
        lbl_sk.setStyleSheet("color: #e4aaff; font-weight: 700; border: none; background: transparent;")
        sb_lay.addWidget(lbl_sk)
        self._skill_btns: List[QPushButton] = []
        self._skill_ids: List[str] = []
        skill_short_labels = [
            "① Phong Long Trảm",
            "② Bạo Tốc Ảnh Bộ",
            "③ Long Quyển Tàn Ảnh",
            "④ Long Phong Phá Kích",
            "⑤ Ngũ Mang Tinh Trận",
        ]
        for i_s, lbl_s in enumerate(skill_short_labels):
            bs = QPushButton(lbl_s)
            bs.setStyleSheet("font-size: 11px; padding: 4px 7px;")
            bs.clicked.connect(lambda _, idx=i_s: self._trigger_skill_idx(idx))
            sb_lay.addWidget(bs)
            self._skill_btns.append(bs)
        self.btn_skill_chain = QPushButton("⚡ Full 1→5")
        self.btn_skill_chain.setObjectName("PrimaryBtn")
        self.btn_skill_chain.clicked.connect(lambda: self.arena.trigger_skill_sequence(self._skill_ids))
        sb_lay.addWidget(self.btn_skill_chain)
        self.skill_bar_frame.setVisible(False)
        lay.addWidget(self.skill_bar_frame)

        lay.addWidget(self.arena, 1)

    def _trigger_skill_idx(self, idx: int) -> None:
        if 0 <= idx < len(self._skill_ids):
            rid = self._skill_ids[idx]
            c_idx = self.combo_routine.findData(rid)
            if c_idx >= 0:
                self.combo_routine.setCurrentIndex(c_idx)
            self.arena.trigger_attack(override_rid=rid)

    def set_exclusive_skills(self, skill_ids: Optional[List[str]]) -> None:
        self._skill_ids = list(skill_ids) if skill_ids else []
        has_sk = bool(self._skill_ids)
        self.skill_bar_frame.setVisible(has_sk)
        self.arena.set_exclusive_skills(self._skill_ids)
        for i_b, btn in enumerate(self._skill_btns):
            if i_b < len(self._skill_ids):
                sid = self._skill_ids[i_b]
                btn.setText(SKILL_SHORT_LABELS.get(sid, sid))
                btn.setToolTip(ROUTINE_DISPLAY_NAMES.get(sid, sid))
                btn.setVisible(True)
            else:
                btn.setVisible(False)

        cur_data = self.combo_routine.currentData()
        self.combo_routine.blockSignals(True)
        self.combo_routine.clear()
        self.combo_routine.addItem("🎲 Auto Chain (Xoay vòng SQUISHY)", "__auto__")
        allowed_set = set(self._skill_ids)
        for rt in self.arena.routines:
            if rt.id.startswith("sk_") and rt.id not in allowed_set:
                continue
            self.combo_routine.addItem(ROUTINE_DISPLAY_NAMES.get(rt.id, rt.id), rt.id)
        target_rid = self._skill_ids[0] if has_sk else (cur_data if cur_data and not str(cur_data).startswith("sk_") else "combo_whirl_flurry")
        idx = self.combo_routine.findData(target_rid)
        if idx >= 0:
            self.combo_routine.setCurrentIndex(idx)
            self.arena.set_routine_id(str(target_rid))
        self.combo_routine.blockSignals(False)

    def _on_routine_changed(self, _idx: int) -> None:
        rid = str(self.combo_routine.currentData() or "__auto__")
        self.arena.set_routine_id(rid)

    def set_composed(
        self,
        result: ComposedResult,
        element: ElementDef,
        socket_gem: bool = True,
        vfx_intensity: float = 1.25,
        base_damage: float = 22.0,
        cooldown_sec: float = 2.4,
    ) -> None:
        self.arena.set_weapon(result, element, socket_gem, vfx_intensity, base_damage, cooldown_sec)
