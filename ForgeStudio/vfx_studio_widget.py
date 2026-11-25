"""
No-Code Canvas-Quality VFX & Element Builder Studio for Overgeared (1.7).
- 10 gorgeous 1-click Procedural Canvas Presets (Fire Swirl, Fractal Lightning,
  Crescent Slashes, Volumetric Smoke/Mist, 3D Rings, Sakura Wind, Cosmic Nebula...)
- Modular Layer Mixer: combine 3D Ribbons, Fractal Lightning, Crescent Slashes,
  Volumetric Smoke, 3D Rings, Rotating Rays, and Dynamic Particles
- "Palette & Style from Reference Image" (Ctrl+V / Drop any reference image ->
  extracts its glowing corona + core colors & generates Canvas-quality 3D VFX!)
- Also supports small custom Particle Sprites (petals, runes, stars)
"""
from __future__ import annotations

import copy
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from exporter import update_language_xml
from forge_canvas import ForgePreviewCanvas
from mod_data import ElementDef, KINDS, ModAssetStore, WeaponDesignState
from renderer import compose_weapon
from splitter import black_bg_to_glow_alpha, remove_background_color, trim_and_pad
from theme import ForgeSlider


MOTION_MODES_PARTICLE = [
    ("up", "Bay lên (Rise Up)"),
    ("down", "Rơi xuống (Fall Down)"),
    ("orbit", "Xoay quanh lưỡi (Orbit)"),
    ("inward", "Hút vào tâm ngọc (Spiral In)"),
]

PARTICLE_SHAPES = [
    ("ember", "Đốm lửa / Năng lượng (Ember Orb)"),
    ("crystal", "Tinh thể băng / Kim cương (Crystal)"),
    ("petal", "Cánh hoa (Sakura Petal)"),
    ("star", "Ngôi sao lấp lánh (Star)"),
]


def _make_layer(
    layer_type: str,
    primary_rgb: Tuple[int, int, int],
    secondary_rgb: Tuple[int, int, int],
    scale: float = 1.0,
    speed: float = 1.0,
    opacity: float = 1.0,
    count: int = 10,
    direction: str = "up",
    shape: str = "ember",
    turns: float = 1.2,
    wispiness: float = 1.0,
    image_rel_path: str = "",
    keep_image_colors: bool = True,
    behind_weapon: bool = False,
    offset_y: float = 0.0,
) -> Dict:
    return {
        "layer_type": layer_type,
        "primary_rgb": list(primary_rgb),
        "secondary_rgb": list(secondary_rgb),
        "scale": scale,
        "speed": speed,
        "opacity": opacity,
        "count": count,
        "direction": direction,
        "shape": shape,
        "turns": turns,
        "wispiness": wispiness,
        "image_rel_path": image_rel_path,
        "keep_image_colors": keep_image_colors,
        "behind_weapon": behind_weapon,
        "offset_y": offset_y,
        "enabled": True,
    }


SWORD_ONLY_LAYER_TYPES = {"shadow_strife", "eternal_alpha", "nova_burn"}


CANVAS_TEMPLATES: List[Tuple[str, str, int, List[Dict]]] = [
    (
        "💀 U Minh Tử Khí (Abyssal Miasma)",
        "Ngọn lửa tím họng kiếm bùng chuyển khói đen hắc ám",
        6,
        [_make_layer("abyssal_miasma", (32, 14, 52), (225, 65, 255), scale=1.08, speed=1.0, opacity=1.0)],
    ),
    (
        "🌑 Bạch Viêm Hắc Vụ (Chỉ Kiếm)",
        "Bạch viêm bùng sáng tại đốc & khói đen quấn quanh lưỡi kiếm",
        6,
        [_make_layer("shadow_strife", (22, 23, 28), (242, 248, 255), scale=1.05, speed=1.0, opacity=1.0)],
    ),
    (
        "✨ Thần Quang Hoàng Kim (Chỉ Kiếm)",
        "Cánh hoàng kim thần thoại tại đốc & ánh vàng rực dọc lưỡi kiếm",
        6,
        [_make_layer("eternal_alpha", (245, 198, 72), (255, 250, 228), scale=1.05, speed=1.0, opacity=1.0)],
    ),
    (
        "💥 Siêu Tân Tinh Tím (Chỉ Kiếm)",
        "Hắc tâm vòng quỹ đạo & thương lửa siêu tân tinh tím trắng",
        7,
        [_make_layer("nova_burn", (198, 86, 255), (255, 240, 220), scale=1.05, speed=1.0, opacity=1.0)],
    ),
    (
        "🔵 Thanh Diêm Kiếm (Blue Jet)",
        "Luồng lửa lam phóng dọc mũi & gai lửa chắn tay",
        5,
        [_make_layer("azure_jet", (30, 155, 255), (175, 242, 255), scale=1.05, speed=1.0, opacity=1.0)],
    ),
    (
        "🔥 U Hỏa Tàn Tro (Embers)",
        "Vòng chắn lửa mỏng & tia lửa nứt tàn tro mờ ảo",
        4,
        [_make_layer("ember_tendrils", (245, 105, 25), (255, 215, 115), scale=1.05, speed=1.0, opacity=1.0)],
    ),
    (
        "⚪ Bạch Trảm Sóng Âm (Sonic)",
        "Sóng âm bạc-đen ở chắn tay & tia tốc độ sắc bén",
        4,
        [_make_layer("sonic_slash", (190, 200, 215), (250, 252, 255), scale=1.05, speed=1.0, opacity=1.0)],
    ),
    (
        "❄ Băng Giáp Tinh Thể (Ice)",
        "Giáp tinh thể băng góc cạnh xếp lớp bọc kín lưỡi",
        4,
        [_make_layer("ice_armor", (55, 175, 248), (225, 250, 255), scale=1.05, speed=1.0, opacity=1.0)],
    ),
    (
        "⚡ Huyền Lôi Mạng (Plasma)",
        "Màng năng lượng Voronoi lam-trắng cuộn quanh lưỡi",
        5,
        [_make_layer("plasma_web", (40, 145, 255), (235, 250, 255), scale=1.05, speed=1.0, opacity=1.0)],
    ),
    (
        "🌊 Thủy Lưu Bọt (Water)",
        "Lớp nước trong suốt viền bọt trắng uốn lượn",
        3,
        [_make_layer("water_sheath", (55, 130, 215), (242, 250, 255), scale=1.05, speed=1.0, opacity=1.0)],
    ),
    (
        "🌑 Nhật Thực Hắc Tâm (Eclipse)",
        "Sao 8 cánh lõi đen ở chắn tay & thương quang đỏ vàng",
        6,
        [_make_layer("eclipse_flare", (220, 45, 25), (255, 232, 145), scale=1.05, speed=1.0, opacity=1.0)],
    ),
    (
        "🔥 Hỏa Long Xoắn (Fire Swirl)",
        "Song dải lửa 3D bùng cháy quấn quanh vũ khí",
        5,
        [_make_layer("ribbon", (255, 115, 32), (255, 225, 115), scale=1.08, speed=1.0, opacity=1.0, count=2, turns=1.2, wispiness=1.0)],
    ),
    (
        "⚡ Lôi Thần (Lightning Web)",
        "Mạng lưới sét phân nhánh 5 cấp bọc quanh vũ khí",
        4,
        [_make_layer("lightning", (76, 118, 255), (240, 248, 255), scale=1.05, speed=1.0, opacity=1.0, count=6, turns=1.0, wispiness=0.60)],
    ),
    (
        "⚔ Kiếm Khí Trảm (Crescent)",
        "Các vệt chém trăng khuyết sắc bén chém ngang lưỡi",
        5,
        [_make_layer("slashes", (70, 220, 255), (235, 252, 255), scale=1.1, speed=1.15, opacity=1.0, count=4)],
    ),
]


class VfxStudioWorkspace(QWidget):
    """Tab 3: No-Code Canvas-Quality VFX & Element Builder."""
    elementSaved = Signal(int)

    def __init__(self, store: ModAssetStore, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.store = store
        self.preview_design = WeaponDesignState(kind=0, head=3, guard=3, grip=1, pommel=2, enchantment=999, vfx_intensity=1.25)
        self.layers: List[Dict] = []
        self._selected_layer: int = -1
        self._blocking_ui = False

        self._build_ui()
        self._apply_template(0)

        QShortcut(QKeySequence("Ctrl+V"), self, self._paste_palette_or_sprite)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # ---- Left Column: Live 60 FPS Canvas Preview ----
        left_panel = QFrame()
        left_panel.setObjectName("Panel")
        ll = QVBoxLayout(left_panel)
        ll.setContentsMargins(10, 10, 10, 10)
        ll.setSpacing(6)

        top_bar = QHBoxLayout()
        lbl = QLabel("✨ Studio Tạo Hiệu Ứng Canvas 3D (Tự thêm Nguyên Tố)")
        lbl.setObjectName("GoldTitle")
        top_bar.addWidget(lbl, 1)

        self.kind_group = QButtonGroup(self)
        for ki, kname in enumerate(KINDS):
            kb = QPushButton(kname)
            kb.setCheckable(True)
            if ki == 0:
                kb.setChecked(True)
            self.kind_group.addButton(kb, ki)
            top_bar.addWidget(kb)
        self.kind_group.idClicked.connect(self._on_kind_changed)

        btn_swing = QPushButton("⚔ Test Vung")
        btn_swing.setCheckable(True)
        btn_swing.toggled.connect(lambda c: self.preview.set_swing_test(c))
        top_bar.addWidget(btn_swing)
        ll.addLayout(top_bar)

        self.preview = ForgePreviewCanvas(self.store.get_sparkle_pil())
        self.preview.set_store(self.store)
        ll.addWidget(self.preview, 1)

        hint = QLabel("Chọn Mẫu có sẵn bên phải, ghép thêm Layer Canvas 3D, hoặc Ctrl+V ảnh mẫu để hút bảng màu tự động!")
        hint.setObjectName("MutedLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(hint)

        root.addWidget(left_panel, 1)

        # ---- Right Column: Templates + Layer Mixer + Parameters ----
        right_panel = QFrame()
        right_panel.setObjectName("Panel")
        right_panel.setFixedWidth(455)
        rl_outer = QVBoxLayout(right_panel)
        rl_outer.setContentsMargins(8, 8, 8, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        rw = QWidget()
        rl = QVBoxLayout(rw)
        rl.setSpacing(8)

        # 1. One-Click Gorgeous Canvas Templates
        tpl_box = QGroupBox("1. Chọn nhanh Mẫu Hiệu Ứng Canvas (1-Click)")
        tl = QVBoxLayout(tpl_box)
        tpl_grid = QGridLayout()
        tpl_grid.setSpacing(4)
        for idx, (tname, tdesc, _, _) in enumerate(CANVAS_TEMPLATES):
            b = QPushButton(tname)
            b.setToolTip(tdesc)
            b.clicked.connect(lambda _, ti=idx: self._apply_template(ti))
            tpl_grid.addWidget(b, idx // 2, idx % 2)
        tl.addLayout(tpl_grid)

        pal_row = QHBoxLayout()
        btn_pal_paste = QPushButton("🎨 Hút màu từ Ảnh (Ctrl+V)")
        btn_pal_paste.setObjectName("PrimaryBtn")
        btn_pal_paste.setToolTip("Dán bất kỳ ảnh hiệu ứng nào -> tool tự lấy màu Corona + màu Lõi áp dụng vào hiệu ứng Canvas 3D!")
        btn_pal_paste.clicked.connect(self._paste_palette_or_sprite)
        btn_pal_open = QPushButton("📂 Hút màu từ File...")
        btn_pal_open.clicked.connect(self._open_palette_image)
        pal_row.addWidget(btn_pal_paste)
        pal_row.addWidget(btn_pal_open)
        tl.addLayout(pal_row)
        rl.addWidget(tpl_box)

        # 2. Add Canvas Layers + Layer Stack
        stack_box = QGroupBox("2. Trộn các lớp Canvas 3D (Layer Mixer)")
        sl = QVBoxLayout(stack_box)

        add_grid = QGridLayout()
        add_grid.setSpacing(4)
        for idx, (label, ltype) in enumerate([
            ("+ 💀 U Minh Tử Khí", "abyssal_miasma"),
            ("+ 🌑 Bạch Viêm Hắc Vụ", "shadow_strife"),
            ("+ ✨ Thần Quang Hoàng Kim", "eternal_alpha"),
            ("+ 💥 Siêu Tân Tinh Tím", "nova_burn"),
            ("+ 🔵 Thanh Diêm Jet", "azure_jet"),
            ("+ 🔥 Tàn Tro U Hỏa", "ember_tendrils"),
            ("+ ⚪ Sóng Âm Bạch Trảm", "sonic_slash"),
            ("+ ❄ Giáp Băng Tinh Thể", "ice_armor"),
            ("+ ⚡ Mạng Plasma", "plasma_web"),
            ("+ 🌊 Thủy Lưu Bọt", "water_sheath"),
            ("+ 🌑 Nhật Thực Hắc Tâm", "eclipse_flare"),
            ("+ 🔥 Dải Lửa 3D", "ribbon"),
            ("+ ⚡ Sấm Sét 5 cấp", "lightning"),
        ]):
            b = QPushButton(label)
            b.clicked.connect(lambda _, lt=ltype: self._add_layer(lt))
            add_grid.addWidget(b, idx // 3, idx % 3)
        sl.addLayout(add_grid)

        self.layer_list = QListWidget()
        self.layer_list.setFixedHeight(105)
        self.layer_list.currentRowChanged.connect(self._on_layer_selected)
        sl.addWidget(self.layer_list)

        lbtn_row = QHBoxLayout()
        btn_toggle = QPushButton("👁 Bật/Tắt")
        btn_toggle.clicked.connect(self._toggle_layer)
        btn_dup = QPushButton("⎘ Nhân bản")
        btn_dup.clicked.connect(self._dup_layer)
        btn_sprite = QPushButton("🌸 Thêm Hạt Ảnh...")
        btn_sprite.setToolTip("Dùng ảnh icon nhỏ (hoa, cổ tự, ngôi sao) làm hạt bay")
        btn_sprite.clicked.connect(self._open_sprite_particle)
        btn_del = QPushButton("🗑 Xóa")
        btn_del.clicked.connect(self._del_layer)
        for b in (btn_toggle, btn_dup, btn_sprite, btn_del):
            lbtn_row.addWidget(b)
        sl.addLayout(lbtn_row)
        rl.addWidget(stack_box)

        # 3. Selected Layer Parameters
        self.edit_box = QGroupBox("3. Tinh chỉnh Layer đang chọn")
        el = QVBoxLayout(self.edit_box)

        col_row = QHBoxLayout()
        self.btn_l_prim = QPushButton("Màu chính (Aura / Corona)")
        self.btn_l_prim.clicked.connect(lambda: self._pick_layer_color(True))
        self.btn_l_sec = QPushButton("Màu lõi (Highlight / Core)")
        self.btn_l_sec.clicked.connect(lambda: self._pick_layer_color(False))
        col_row.addWidget(self.btn_l_prim)
        col_row.addWidget(self.btn_l_sec)
        el.addLayout(col_row)

        self.row_dir_w = QWidget()
        dr = QHBoxLayout(self.row_dir_w)
        dr.setContentsMargins(0, 0, 0, 0)
        dr.addWidget(QLabel("Hướng chuyển động:"))
        self.combo_dir = QComboBox()
        for dk, dl in MOTION_MODES_PARTICLE:
            self.combo_dir.addItem(dl, dk)
        self.combo_dir.currentIndexChanged.connect(self._on_layer_param_changed)
        dr.addWidget(self.combo_dir, 1)
        el.addWidget(self.row_dir_w)

        self.row_shape_w = QWidget()
        sr_l = QHBoxLayout(self.row_shape_w)
        sr_l.setContentsMargins(0, 0, 0, 0)
        sr_l.addWidget(QLabel("Kiểu hạt:"))
        self.combo_shape = QComboBox()
        for sk, slbl in PARTICLE_SHAPES:
            self.combo_shape.addItem(slbl, sk)
        self.combo_shape.currentIndexChanged.connect(self._on_layer_param_changed)
        sr_l.addWidget(self.combo_shape, 1)
        el.addWidget(self.row_shape_w)

        self.sl_l_scale = ForgeSlider("Độ lớn / Bán kính", 0.3, 2.2, 0.05, 1.0)
        self.sl_l_speed = ForgeSlider("Tốc độ", 0.2, 2.5, 0.1, 1.0)
        self.sl_l_op = ForgeSlider("Độ sáng (Opacity)", 0.2, 1.5, 0.05, 1.0)
        self.sl_l_cnt = ForgeSlider("Số lượng / Số cung / Số dải", 1.0, 20.0, 1.0, 6.0, is_percent=False)
        self.sl_l_cnt.spin.setRange(1, 20)
        self.sl_l_turns = ForgeSlider("Số vòng xoắn / Độ giật", 0.5, 2.4, 0.05, 1.2)
        self.sl_l_wisp = ForgeSlider("Độ gợn lửa / Phân nhánh", 0.0, 1.0, 0.05, 1.0)

        for s in (self.sl_l_scale, self.sl_l_speed, self.sl_l_op, self.sl_l_cnt, self.sl_l_turns, self.sl_l_wisp):
            s.valueChanged.connect(self._on_layer_param_changed)
            el.addWidget(s)

        rl.addWidget(self.edit_box)

        # 4. Save Element
        save_box = QGroupBox("4. Lưu thành Nguyên Tố Khảm mới (1.7)")
        svg = QGridLayout(save_box)
        svg.addWidget(QLabel("Tên nguyên tố:"), 0, 0)
        self.ed_elem_name = QLineEdit("Hỏa Long Kiếm")
        svg.addWidget(self.ed_elem_name, 0, 1)

        svg.addWidget(QLabel("Mô tả:"), 1, 0)
        self.ed_elem_desc = QLineEdit("Hiệu ứng tự tạo bọc quanh vũ khí")
        svg.addWidget(self.ed_elem_desc, 1, 1)

        svg.addWidget(QLabel("Sát thương +:"), 2, 0)
        self.sp_elem_dmg = QSpinBox()
        self.sp_elem_dmg.setRange(1, 25)
        self.sp_elem_dmg.setValue(4)
        svg.addWidget(self.sp_elem_dmg, 2, 1)

        svg.addWidget(QLabel("Nguyên liệu:"), 3, 0)
        self.ed_elem_cost = QLineEdit("Gold 8 · Jade 10")
        svg.addWidget(self.ed_elem_cost, 3, 1)

        self.chk_sword_only = QCheckBox("⚔ Chỉ dành cho Kiếm (Sword only)")
        self.chk_sword_only.toggled.connect(lambda _: self._sync_sword_only_ui())
        svg.addWidget(self.chk_sword_only, 4, 0, 1, 2)

        btn_save_elem = QPushButton("💾 Lưu & Gắn vào Lò Rèn ngay")
        btn_save_elem.setObjectName("AccentGreenBtn")
        btn_save_elem.setFixedHeight(38)
        btn_save_elem.clicked.connect(self._save_as_element)
        svg.addWidget(btn_save_elem, 5, 0, 1, 2)
        rl.addWidget(save_box)

        rl.addStretch()
        scroll.setWidget(rw)
        rl_outer.addWidget(scroll)
        root.addWidget(right_panel)

    # ---- Drag & Drop / Clipboard Palette Extraction ----
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        md = event.mimeData()
        if md.hasUrls():
            for url in md.urls():
                p = Path(url.toLocalFile())
                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                    with Image.open(p) as im:
                        self._extract_palette_into_layers(im)
                    break
        elif md.hasImage():
            qim: QImage = md.imageData()
            self._extract_palette_from_qimage(qim)

    def _paste_palette_or_sprite(self) -> None:
        cb = QApplication.clipboard()
        qim = cb.image()
        if not qim.isNull():
            self._extract_palette_from_qimage(qim)
            return
        md = cb.mimeData()
        if md.hasUrls():
            for url in md.urls():
                p = Path(url.toLocalFile())
                if p.exists():
                    with Image.open(p) as im:
                        self._extract_palette_into_layers(im)
                    break

    def _open_palette_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn ảnh mẫu để hút bảng màu VFX", str(self.store.mod_root),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if path:
            with Image.open(path) as im:
                self._extract_palette_into_layers(im)

    def _extract_palette_from_qimage(self, qim: QImage) -> None:
        qim = qim.convertToFormat(QImage.Format.Format_RGBA8888)
        ptr = qim.constBits()
        pil = Image.frombytes("RGBA", (qim.width(), qim.height()), bytes(ptr))
        self._extract_palette_into_layers(pil)

    def _extract_palette_into_layers(self, img: Image.Image) -> None:
        """Extracts saturated Aura color & bright Core color from any reference image and applies to Canvas layers."""
        thumb = img.convert("RGB")
        thumb.thumbnail((128, 128), Image.Resampling.BILINEAR)
        arr = np.asarray(thumb, dtype=np.float32)
        flat = arr.reshape(-1, 3)

        lum = np.max(flat, axis=1)
        sat = np.max(flat, axis=1) - np.min(flat, axis=1)

        # Saturated non-black pixels -> Aura/Corona color
        vivid_mask = (lum > 45) & (sat > 35)
        if np.any(vivid_mask):
            vivid = flat[vivid_mask]
            # Pick weighted brightest saturated tones
            weights = sat[vivid_mask] * (lum[vivid_mask] / 255.0)
            top_idx = np.argsort(weights)[-max(1, len(vivid) // 5):]
            prim_arr = np.median(vivid[top_idx], axis=0)
            prim = (int(prim_arr[0]), int(prim_arr[1]), int(prim_arr[2]))
        else:
            prim = (110, 195, 255)

        # Brightest core pixels -> Core color
        bright_mask = lum > 175
        if np.any(bright_mask):
            br = flat[bright_mask]
            top_b = np.argsort(lum[bright_mask])[-max(1, len(br) // 4):]
            sec_arr = np.median(br[top_b], axis=0)
            sec = (int(sec_arr[0]), int(sec_arr[1]), int(sec_arr[2]))
        else:
            sec = (min(255, prim[0] + 90), min(255, prim[1] + 90), min(255, prim[2] + 90))

        if not self.layers:
            self._apply_template(0)
        for l in self.layers:
            l["primary_rgb"] = list(prim)
            l["secondary_rgb"] = list(sec)

        self._on_layer_selected(max(0, self._selected_layer))
        self._refresh_preview()

    def _open_sprite_particle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn ảnh hạt nhỏ (cánh hoa, cổ tự, ngôi sao...)", str(self.store.mod_root),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not path:
            return
        with Image.open(path) as im:
            raw = im.convert("RGBA")
        if max(raw.size) > 128:
            raw.thumbnail((128, 128), Image.Resampling.LANCZOS)
        arr = raw.getchannel("A")
        if arr.getextrema()[0] >= 245:
            c_vals = [raw.getpixel((0, 0))[:3], raw.getpixel((raw.width - 1, 0))[:3]]
            if sum(sum(c) for c in c_vals) / 6.0 < 55:
                raw = black_bg_to_glow_alpha(raw, dark_cutoff=20)
            else:
                raw = remove_background_color(raw, tolerance=36, softness=12)
        cleaned = trim_and_pad(raw, pad=2)
        temp_key = f"Effects/Custom/particle_{int(time.time() * 1000)}.png"
        self.store.temp_effect_pils[temp_key] = cleaned
        self.preview.clear_custom_vfx_cache()

        self.layers.append(_make_layer(
            "image_particles", (255, 255, 255), (255, 255, 255),
            scale=1.15, speed=0.9, opacity=1.0, count=14, direction="orbit",
            image_rel_path=temp_key, keep_image_colors=True,
        ))
        self._rebuild_layer_list(select_idx=len(self.layers) - 1)
        self._refresh_preview()

    # ---- Templates & Layer Stack ----
    def _has_sword_only_layers(self) -> bool:
        return any(l.get("layer_type") in SWORD_ONLY_LAYER_TYPES for l in self.layers)

    def _sync_sword_only_ui(self) -> None:
        forced = self._has_sword_only_layers()
        sword_only = forced or self.chk_sword_only.isChecked()
        if forced and not self.chk_sword_only.isChecked():
            self.chk_sword_only.blockSignals(True)
            self.chk_sword_only.setChecked(True)
            self.chk_sword_only.blockSignals(False)
        for ki in range(len(KINDS)):
            btn = self.kind_group.button(ki)
            if btn is not None:
                btn.setEnabled(ki == 0 or not sword_only)
        if sword_only and self.preview_design.kind != 0:
            self.preview_design.kind = 0
            btn0 = self.kind_group.button(0)
            if btn0 is not None:
                btn0.setChecked(True)

    def _apply_template(self, idx: int) -> None:
        tname, tdesc, tdmg, tlayers = CANVAS_TEMPLATES[idx]
        self.layers = copy.deepcopy(tlayers)
        clean_name = tname.split(" ", 1)[1] if " " in tname else tname
        self.ed_elem_name.setText(clean_name)
        self.ed_elem_desc.setText(tdesc)
        self.sp_elem_dmg.setValue(tdmg)
        self.chk_sword_only.blockSignals(True)
        self.chk_sword_only.setChecked(self._has_sword_only_layers())
        self.chk_sword_only.blockSignals(False)
        self._sync_sword_only_ui()
        self._rebuild_layer_list(select_idx=0)
        self._refresh_preview()

    def _add_layer(self, ltype: str) -> None:
        defaults = {
            "abyssal_miasma": _make_layer("abyssal_miasma", (32, 14, 52), (225, 65, 255), scale=1.08, speed=1.0, opacity=1.0),
            "shadow_strife": _make_layer("shadow_strife", (22, 23, 28), (242, 248, 255), scale=1.05, speed=1.0, opacity=1.0),
            "eternal_alpha": _make_layer("eternal_alpha", (245, 198, 72), (255, 250, 228), scale=1.05, speed=1.0, opacity=1.0),
            "nova_burn": _make_layer("nova_burn", (198, 86, 255), (255, 240, 220), scale=1.05, speed=1.0, opacity=1.0),
            "azure_jet": _make_layer("azure_jet", (30, 155, 255), (175, 242, 255), scale=1.05, speed=1.0, opacity=1.0),
            "ember_tendrils": _make_layer("ember_tendrils", (245, 105, 25), (255, 215, 115), scale=1.05, speed=1.0, opacity=1.0),
            "sonic_slash": _make_layer("sonic_slash", (190, 200, 215), (250, 252, 255), scale=1.05, speed=1.0, opacity=1.0),
            "ice_armor": _make_layer("ice_armor", (55, 175, 248), (225, 250, 255), scale=1.05, speed=1.0, opacity=1.0),
            "plasma_web": _make_layer("plasma_web", (40, 145, 255), (235, 250, 255), scale=1.05, speed=1.0, opacity=1.0),
            "water_sheath": _make_layer("water_sheath", (55, 130, 215), (242, 250, 255), scale=1.05, speed=1.0, opacity=1.0),
            "eclipse_flare": _make_layer("eclipse_flare", (220, 45, 25), (255, 232, 145), scale=1.05, speed=1.0, opacity=1.0),
            "ribbon": _make_layer("ribbon", (255, 120, 40), (255, 225, 120), scale=1.0, speed=1.0, opacity=1.0, count=2, turns=1.2, wispiness=1.0),
            "lightning": _make_layer("lightning", (76, 118, 255), (240, 248, 255), scale=1.0, speed=1.0, opacity=1.0, count=6, turns=1.0, wispiness=0.55),
            "slashes": _make_layer("slashes", (70, 220, 255), (235, 252, 255), scale=1.1, speed=1.1, opacity=1.0, count=4),
            "smoke": _make_layer("smoke", (135, 55, 255), (200, 140, 255), scale=1.1, speed=0.9, opacity=0.9, count=12, direction="up"),
            "particles": _make_layer("particles", (255, 160, 210), (255, 240, 250), scale=1.15, speed=0.9, opacity=1.0, count=14, direction="orbit", shape="petal"),
            "rings": _make_layer("rings", (165, 90, 255), (235, 210, 255), scale=1.1, speed=1.0, opacity=0.95, count=3, direction="inward"),
            "rays": _make_layer("rays", (255, 215, 90), (255, 250, 210), scale=1.2, speed=1.0, opacity=0.9, count=8),
        }
        self.layers.append(defaults[ltype])
        self._sync_sword_only_ui()
        self._rebuild_layer_list(select_idx=len(self.layers) - 1)
        self._refresh_preview()

    def _rebuild_layer_list(self, select_idx: Optional[int] = None) -> None:
        self.layer_list.clear()
        type_names = {
            "abyssal_miasma": "💀 U Minh Tử Khí",
            "shadow_strife": "🌑 Bạch Viêm Hắc Vụ (Chỉ Kiếm)",
            "eternal_alpha": "✨ Thần Quang Hoàng Kim (Chỉ Kiếm)",
            "nova_burn": "💥 Siêu Tân Tinh Tím (Chỉ Kiếm)",
            "azure_jet": "🔵 Thanh Diêm Jet",
            "ember_tendrils": "🔥 Tàn Tro U Hỏa",
            "sonic_slash": "⚪ Sóng Âm Bạch Trảm",
            "ice_armor": "❄ Giáp Băng Tinh Thể",
            "plasma_web": "⚡ Mạng Plasma",
            "water_sheath": "🌊 Thủy Lưu Bọt",
            "eclipse_flare": "🌑 Nhật Thực Hắc Tâm",
            "ribbon": "🔥 Dải Xoắn 3D",
            "lightning": "⚡ Sấm Sét 5 cấp",
            "slashes": "⚔ Vệt Chém 3D",
            "smoke": "🌫 Khói / Sương Khí",
            "particles": "✨ Hạt Bay",
            "rings": "🌀 Vòng Xoáy 3D",
            "rays": "☀ Tia Sáng",
            "image_particles": "🌸 Hạt Ảnh",
        }
        for i, l in enumerate(self.layers):
            vis = "👁" if l.get("enabled", True) else "🚫"
            tname = type_names.get(l.get("layer_type", ""), l.get("layer_type", ""))
            self.layer_list.addItem(QListWidgetItem(f"{vis} #{i + 1}: {tname}"))
        if select_idx is not None and 0 <= select_idx < len(self.layers):
            self.layer_list.setCurrentRow(select_idx)
        elif self.layers:
            self.layer_list.setCurrentRow(0)

    def _on_layer_selected(self, row: int) -> None:
        self._selected_layer = row
        has_sel = 0 <= row < len(self.layers)
        self.edit_box.setEnabled(has_sel)
        if not has_sel:
            return

        l = self.layers[row]
        ltype = l.get("layer_type", "ribbon")
        self.row_dir_w.setVisible(ltype in ("particles", "image_particles", "smoke", "rings"))
        self.row_shape_w.setVisible(ltype == "particles")
        self.sl_l_turns.setVisible(ltype in ("ribbon", "lightning"))
        self.sl_l_wisp.setVisible(ltype in ("ribbon", "lightning"))

        self._blocking_ui = True
        d_idx = self.combo_dir.findData(l.get("direction", "up"))
        if d_idx >= 0:
            self.combo_dir.setCurrentIndex(d_idx)
        s_idx = self.combo_shape.findData(l.get("shape", "ember"))
        if s_idx >= 0:
            self.combo_shape.setCurrentIndex(s_idx)

        self.sl_l_scale.set_value(float(l.get("scale", 1.0)), emit=False)
        self.sl_l_speed.set_value(float(l.get("speed", 1.0)), emit=False)
        self.sl_l_op.set_value(float(l.get("opacity", 1.0)), emit=False)
        self.sl_l_cnt.set_value(float(l.get("count", 6)), emit=False)
        self.sl_l_turns.set_value(float(l.get("turns", 1.2)), emit=False)
        self.sl_l_wisp.set_value(float(l.get("wispiness", 1.0)), emit=False)

        pr = l.get("primary_rgb", [255, 130, 45])
        sr = l.get("secondary_rgb", [255, 240, 190])
        self.btn_l_prim.setStyleSheet(f"border-left: 8px solid rgb({pr[0]},{pr[1]},{pr[2]});")
        self.btn_l_sec.setStyleSheet(f"border-left: 8px solid rgb({sr[0]},{sr[1]},{sr[2]});")
        self._blocking_ui = False

    def _on_layer_param_changed(self, *_) -> None:
        if self._blocking_ui or not (0 <= self._selected_layer < len(self.layers)):
            return
        l = self.layers[self._selected_layer]
        l["direction"] = self.combo_dir.currentData() or "up"
        l["shape"] = self.combo_shape.currentData() or "ember"
        l["scale"] = self.sl_l_scale.value()
        l["speed"] = self.sl_l_speed.value()
        l["opacity"] = self.sl_l_op.value()
        l["count"] = int(round(self.sl_l_cnt.value()))
        l["turns"] = self.sl_l_turns.value()
        l["wispiness"] = self.sl_l_wisp.value()
        self._refresh_preview()

    def _pick_layer_color(self, is_primary: bool) -> None:
        if not (0 <= self._selected_layer < len(self.layers)):
            return
        l = self.layers[self._selected_layer]
        key = "primary_rgb" if is_primary else "secondary_rgb"
        cur = l.get(key, [255, 130, 45])
        c = QColorDialog.getColor(QColor(*cur), self, "Chọn màu Layer")
        if c.isValid():
            l[key] = [c.red(), c.green(), c.blue()]
            self._on_layer_selected(self._selected_layer)
            self._refresh_preview()

    def _toggle_layer(self) -> None:
        if 0 <= self._selected_layer < len(self.layers):
            self.layers[self._selected_layer]["enabled"] = not self.layers[self._selected_layer].get("enabled", True)
            self._rebuild_layer_list(select_idx=self._selected_layer)
            self._refresh_preview()

    def _dup_layer(self) -> None:
        if 0 <= self._selected_layer < len(self.layers):
            self.layers.append(copy.deepcopy(self.layers[self._selected_layer]))
            self._rebuild_layer_list(select_idx=len(self.layers) - 1)
            self._refresh_preview()

    def _del_layer(self) -> None:
        if 0 <= self._selected_layer < len(self.layers):
            self.layers.pop(self._selected_layer)
            self._sync_sword_only_ui()
            self._rebuild_layer_list(select_idx=min(self._selected_layer, len(self.layers) - 1))
            self._refresh_preview()

    def _on_kind_changed(self, kind: int) -> None:
        self.preview_design.kind = kind
        self._refresh_preview()

    def _build_temp_element(self) -> ElementDef:
        prim = (255, 140, 60)
        sec = (255, 240, 200)
        for l in self.layers:
            if l.get("enabled", True):
                prim = tuple(l.get("primary_rgb", prim))
                sec = tuple(l.get("secondary_rgb", sec))
                break
        return ElementDef(
            id=999 if self.layers else 0,
            key="Preview",
            name=self.ed_elem_name.text().strip() or "Preview",
            description="",
            damage_def="",
            damage=self.sp_elem_dmg.value(),
            cost_text="",
            ingredients=[],
            primary_rgb=prim,
            secondary_rgb=sec,
            vfx_style="custom",
            is_builtin=False,
            layers=self.layers,
        )

    def _refresh_preview(self) -> None:
        res = compose_weapon(self.store, self.preview_design, resolution=512)
        elem = self._build_temp_element()
        self.preview.set_composed(res, elem, True, 1.25)

    def _save_as_element(self) -> None:
        if not self.layers:
            QMessageBox.warning(self, "Chưa có Layer", "Hãy chọn 1 mẫu hoặc thêm ít nhất 1 layer trước khi lưu!")
            return
        name = self.ed_elem_name.text().strip() or "Custom Element"
        safe_slug = "".join(ch for ch in name.lower() if ch.isalnum() or ch == "_") or "custom_vfx"
        custom_dir = self.store.effects_dir / "Custom"

        saved_layers = copy.deepcopy(self.layers)
        for idx, l in enumerate(saved_layers):
            rel = l.get("image_rel_path", "")
            if rel and rel in self.store.temp_effect_pils:
                custom_dir.mkdir(parents=True, exist_ok=True)
                pil = self.store.temp_effect_pils[rel]
                fname = f"{safe_slug}_{int(time.time())}_{idx}.png"
                pil.save(custom_dir / fname, "PNG")
                l["image_rel_path"] = f"Effects/Custom/{fname}"
                self.store.clear_caches()

        prim = tuple(saved_layers[0].get("primary_rgb", (255, 140, 60)))
        sec = tuple(saved_layers[0].get("secondary_rgb", (255, 240, 200)))
        sword_only = self.chk_sword_only.isChecked() or self._has_sword_only_layers()
        elem = self.store.add_custom_element(
            name=name,
            description=self.ed_elem_desc.text().strip() or "Custom Canvas 3D VFX",
            damage=self.sp_elem_dmg.value(),
            primary_rgb=prim,
            secondary_rgb=sec,
            vfx_style="custom",
            cost_text=self.ed_elem_cost.text().strip() or "Gold 8 · Jade 10",
            layers=saved_layers,
            allowed_kinds=[0] if sword_only else None,
        )
        update_language_xml(self.store)
        self.preview.clear_custom_vfx_cache()
        self.elementSaved.emit(elem.id)
        QMessageBox.information(
            self,
            "Đã lưu Nguyên Tố Mới!",
            f"Đã lưu '{elem.name}' (ID #{elem.id}) và gắn vào Lò Rèn để bạn test ngay!",
        )
