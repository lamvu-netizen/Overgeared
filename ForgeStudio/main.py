"""
Overgeared Forge Studio (RimWorld 1.7 / Personal Forge)
- Full interactive Forge replica (Parts, Size, Pattern, Color, Place, Finish, Craft, Story, Enchant, Held Preview)
- Fast Image Importer & Part Splitter (4-Zone Weapon Slicer, Auto-Detect Sprites, Box/Lasso, Magic Wand BG Removal, Brush)
- C# 1.7 & XML Code Exporter / Importer
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
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
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from exporter import generate_csharp_code, generate_xml_custom_defs, update_language_xml
from forge_canvas import ForgePreviewCanvas, HeldPreviewWidget
from mod_data import (
    COLOR_PRESETS,
    CRAFTS,
    CRAFT_DESCRIPTIONS,
    ENCHANTMENTS,
    ENCHANTMENT_DESCRIPTIONS,
    FINISH_DESCRIPTIONS,
    GRIP_MATERIALS,
    KINDS,
    METALS,
    METAL_FINISHES,
    ModAssetStore,
    PATTERN_LAYOUTS,
    PATTERN_PARTS,
    WeaponDesignState,
)
from renderer import ComposedResult, compose_weapon
from splitter_widget import PartSplitterWorkspace
from theme import FORGE_QSS, ForgeSlider, pil_to_qpixmap


DEFAULT_MOD_ROOT = Path(r"d:\1IDK\Overgeared")


class PartCardButton(QPushButton):
    """2-column selectable part card showing thumbnail + part name + custom badge."""

    def __init__(self, title: str, pix: Optional[QPixmap], is_custom: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedHeight(96)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(3)

        thumb = QLabel()
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setFixedHeight(54)
        thumb.setStyleSheet("background: transparent; border: none;")
        if pix is not None and not pix.isNull():
            scaled = pix.scaled(120, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            thumb.setPixmap(scaled)
        lay.addWidget(thumb)

        lbl = QLabel(("★ " if is_custom else "") + title)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(False)
        lbl.setStyleSheet("background: transparent; border: none; font-size: 11px;")
        lay.addWidget(lbl)


class ForgeWorkspace(QWidget):
    """Tab 1: Exact RimWorld 1.7 Personal Forge Replica."""
    designChanged = None

    def __init__(self, store: ModAssetStore, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.store = store
        self.design = WeaponDesignState()
        self._last_composed: Optional[ComposedResult] = None
        self._blocking_ui = False

        # Debounce heavy composition slightly when dragging sliders fast
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(12)
        self._render_timer.timeout.connect(self._render_now)

        self._build_ui()
        self._rebuild_parts_grid()
        self._refresh_all_controls()
        self._render_now()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ---- Top Header Bar ----
        hdr = QHBoxLayout()
        title_box = QVBoxLayout()
        lbl_t = QLabel("Personal Forge 1.7 · Lò Rèn Thử Nghiệm")
        lbl_t.setObjectName("GoldTitle")
        lbl_sub = QLabel("Ghép part, phối màu, hoa văn, hiệu ứng bề mặt & test trực tiếp như trong game")
        lbl_sub.setObjectName("MutedLabel")
        title_box.addWidget(lbl_t)
        title_box.addWidget(lbl_sub)
        hdr.addLayout(title_box)
        hdr.addStretch()

        self.kind_group = QButtonGroup(self)
        for i, kname in enumerate(KINDS):
            b = QPushButton(kname)
            b.setCheckable(True)
            b.setFixedSize(82, 34)
            if i == 0:
                b.setChecked(True)
            self.kind_group.addButton(b, i)
            hdr.addWidget(b)
        self.kind_group.idClicked.connect(self._on_kind_changed)
        root.addLayout(hdr)

        # ---- Main 3-Column Body ----
        body = QHBoxLayout()
        body.setSpacing(10)

        # === LEFT COLUMN: Choices ===
        left_panel = QFrame()
        left_panel.setObjectName("Panel")
        left_panel.setFixedWidth(365)
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(8, 8, 8, 8)
        left_lay.setSpacing(8)

        self.page_group = QButtonGroup(self)
        page_bar = QHBoxLayout()
        page_bar.setSpacing(4)
        for idx, pname in enumerate(["Parts", "Look", "Craft", "Story", "Enchant"]):
            b = QPushButton(pname)
            b.setCheckable(True)
            b.setFixedHeight(32)
            if idx == 0:
                b.setChecked(True)
            self.page_group.addButton(b, idx)
            page_bar.addWidget(b)
        self.page_group.idClicked.connect(lambda i: self.left_stack.setCurrentIndex(i))
        left_lay.addLayout(page_bar)

        self.left_stack = QStackedWidget()
        left_lay.addWidget(self.left_stack, 1)

        self._build_page_parts()
        self._build_page_look()
        self._build_page_craft()
        self._build_page_story()
        self._build_page_enchant()

        body.addWidget(left_panel)

        # === CENTER COLUMN: Preview ===
        mid_panel = QFrame()
        mid_panel.setObjectName("Panel")
        mid_lay = QVBoxLayout(mid_panel)
        mid_lay.setContentsMargins(10, 10, 10, 10)
        mid_lay.setSpacing(6)

        mid_top = QHBoxLayout()
        name_col = QVBoxLayout()
        self.lbl_weapon_name = QLabel("Custom Sword")
        self.lbl_weapon_name.setStyleSheet("font-size: 17px; font-weight: 700; color: #f0cc87;")
        self.lbl_enchant_badge = QLabel("")
        self.lbl_enchant_badge.setObjectName("MutedLabel")
        name_col.addWidget(self.lbl_weapon_name)
        name_col.addWidget(self.lbl_enchant_badge)
        mid_top.addLayout(name_col, 1)

        self.combo_backdrop = QComboBox()
        self.combo_backdrop.addItems(["Nền: Lò Rèn Tối", "Nền: Sàn Đá", "Nền: Cỏ RimWorld", "Nền: Caro Trong Suốt"])
        self.combo_backdrop.currentIndexChanged.connect(lambda i: self.preview_canvas.set_backdrop_mode(i))
        mid_top.addWidget(self.combo_backdrop)

        self.btn_swing = QPushButton("⚔ Test Vung Vũ Khí")
        self.btn_swing.setCheckable(True)
        self.btn_swing.toggled.connect(lambda c: self.preview_canvas.set_swing_test(c))
        mid_top.addWidget(self.btn_swing)

        btn_rand = QPushButton("🎲 Ngẫu nhiên")
        btn_rand.clicked.connect(self._randomize_design)
        mid_top.addWidget(btn_rand)
        mid_lay.addLayout(mid_top)

        self.preview_canvas = ForgePreviewCanvas(self.store.get_sparkle_pil())
        mid_lay.addWidget(self.preview_canvas, 1)

        self.held_preview = HeldPreviewWidget()
        mid_lay.addWidget(self.held_preview)

        body.addWidget(mid_panel, 1)

        # === RIGHT COLUMN: Stats & Actions ===
        right_panel = QFrame()
        right_panel.setObjectName("Panel")
        right_panel.setFixedWidth(275)
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(10, 10, 10, 10)
        right_lay.setSpacing(6)

        lbl_st = QLabel("Thông số (Normal Quality)")
        lbl_st.setObjectName("GoldTitle")
        right_lay.addWidget(lbl_st)

        self.stats_container = QVBoxLayout()
        self.stats_container.setSpacing(4)
        self._stat_labels: Dict[str, QLabel] = {}
        for key, label in [
            ("damage", "Damage"),
            ("ap", "Armor penetration"),
            ("cooldown", "Attack interval"),
            ("dps", "Physical DPS"),
            ("mass", "Mass"),
            ("skill", "Crafting level"),
            ("work", "Work to make"),
            ("ench", "Enchant bonus"),
        ]:
            row = QHBoxLayout()
            k_lbl = QLabel(label)
            k_lbl.setObjectName("MutedLabel")
            v_lbl = QLabel("-")
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            v_lbl.setStyleSheet("font-weight: 600;")
            row.addWidget(k_lbl, 1)
            row.addWidget(v_lbl)
            self.stats_container.addLayout(row)
            self._stat_labels[key] = v_lbl

        right_lay.addLayout(self.stats_container)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #353f42;")
        right_lay.addWidget(sep)

        lbl_ing = QLabel("Nguyên liệu chế tạo")
        lbl_ing.setStyleSheet("font-weight: 600; color: #c49645;")
        right_lay.addWidget(lbl_ing)

        self.lbl_ingredients = QLabel("-")
        self.lbl_ingredients.setWordWrap(True)
        self.lbl_ingredients.setObjectName("MutedLabel")
        right_lay.addWidget(self.lbl_ingredients)

        right_lay.addStretch()

        btn_export_png = QPushButton("🖼 Xuất ảnh vũ khí (PNG 512px)")
        btn_export_png.clicked.connect(self._export_weapon_png)
        btn_save_json = QPushButton("💾 Lưu Preset (JSON)")
        btn_save_json.clicked.connect(self._save_preset_json)
        btn_load_json = QPushButton("📂 Mở Preset (JSON)")
        btn_load_json.clicked.connect(self._load_preset_json)

        right_lay.addWidget(btn_export_png)
        right_lay.addWidget(btn_save_json)
        right_lay.addWidget(btn_load_json)

        body.addWidget(right_panel)
        root.addLayout(body, 1)

    # ---- Left Page 0: Parts & Materials ----
    def _build_page_parts(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        cat_bar = QHBoxLayout()
        cat_bar.setSpacing(4)
        self.part_cat_group = QButtonGroup(self)
        for i, cname in enumerate(["Blade", "Guard", "Grip", "Pommel"]):
            b = QPushButton(cname)
            b.setCheckable(True)
            if i == 0:
                b.setChecked(True)
            self.part_cat_group.addButton(b, i)
            cat_bar.addWidget(b)
        self.part_cat_group.idClicked.connect(lambda _: self._rebuild_parts_grid())
        lay.addLayout(cat_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.parts_grid_host = QWidget()
        self.parts_grid = QGridLayout(self.parts_grid_host)
        self.parts_grid.setSpacing(6)
        self.parts_grid.setContentsMargins(2, 2, 2, 2)
        scroll.setWidget(self.parts_grid_host)
        lay.addWidget(scroll, 1)

        # Materials
        mat_box = QGroupBox("Materials (Chất liệu)")
        mg = QGridLayout(mat_box)
        mg.addWidget(QLabel("Blade:"), 0, 0)
        self.combo_mat_head = QComboBox()
        self.combo_mat_head.addItems([m.label for m in METALS])
        self.combo_mat_head.currentIndexChanged.connect(lambda i: self._set_attr("head_material_idx", i))
        mg.addWidget(self.combo_mat_head, 0, 1)

        mg.addWidget(QLabel("Guard / Pommel:"), 1, 0)
        self.combo_mat_guard = QComboBox()
        self.combo_mat_guard.addItems([m.label for m in METALS])
        self.combo_mat_guard.currentIndexChanged.connect(lambda i: self._set_attr("guard_material_idx", i))
        mg.addWidget(self.combo_mat_guard, 1, 1)

        mg.addWidget(QLabel("Grip:"), 2, 0)
        self.combo_mat_grip = QComboBox()
        self.combo_mat_grip.addItems([m.label for m in GRIP_MATERIALS])
        self.combo_mat_grip.currentIndexChanged.connect(lambda i: self._set_attr("grip_material_idx", i))
        mg.addWidget(self.combo_mat_grip, 2, 1)

        lay.addWidget(mat_box)
        self.left_stack.addWidget(w)

    def _rebuild_parts_grid(self) -> None:
        while self.parts_grid.count():
            item = self.parts_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cat_id = self.part_cat_group.checkedId()
        kind = self.design.kind
        if cat_id == 0:
            entries = self.store.get_heads(kind)
            selected = self.design.head
        elif cat_id == 1:
            entries = self.store.get_guards(kind)
            selected = self.design.guard
        elif cat_id == 2:
            entries = self.store.get_grips()
            selected = self.design.grip
        else:
            entries = self.store.get_pommels(kind)
            selected = self.design.pommel

        self._part_btn_group = QButtonGroup(self)
        for pos, (idx, pid, label) in enumerate(entries):
            tex_name = "guard_2" if (cat_id == 1 and idx == 4) else pid
            pil = self.store.get_part_pil(tex_name)
            pix = pil_to_qpixmap(pil) if pil is not None else None
            is_custom = pid in self.store.custom_parts or pid in self.store.temp_textures
            btn = PartCardButton(label, pix, is_custom=is_custom)
            if idx == selected:
                btn.setChecked(True)
            self._part_btn_group.addButton(btn, idx)
            self.parts_grid.addWidget(btn, pos // 2, pos % 2)

        self.parts_grid.setRowStretch((len(entries) + 1) // 2 + 1, 1)
        self._part_btn_group.idClicked.connect(lambda part_idx: self._on_part_selected(cat_id, part_idx))

    def _on_part_selected(self, cat_id: int, part_idx: int) -> None:
        if cat_id == 0:
            self.design.head = part_idx
        elif cat_id == 1:
            self.design.guard = part_idx
        elif cat_id == 2:
            self.design.grip = part_idx
        else:
            self.design.pommel = part_idx
        self.schedule_render()

    # ---- Left Page 1: Look (Size | Pattern | Color | Place | Finish) ----
    def _build_page_look(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        sub_bar = QHBoxLayout()
        sub_bar.setSpacing(3)
        self.look_group = QButtonGroup(self)
        for i, lname in enumerate(["Size", "Pattern", "Color", "Place", "Finish"]):
            b = QPushButton(lname)
            b.setCheckable(True)
            if i == 0:
                b.setChecked(True)
            self.look_group.addButton(b, i)
            sub_bar.addWidget(b)
        self.look_group.idClicked.connect(lambda i: self.look_stack.setCurrentIndex(i))
        lay.addLayout(sub_bar)

        self.look_stack = QStackedWidget()
        lay.addWidget(self.look_stack, 1)

        # 0: Size
        size_scroll = QScrollArea()
        size_scroll.setWidgetResizable(True)
        sw = QWidget()
        sl = QVBoxLayout(sw)
        self.sl_overall = ForgeSlider("Overall size", 0.65, 1.50, 0.05, 1.0)
        self.sl_head = ForgeSlider("Blade size", 0.75, 1.35, 0.05, 1.0)
        self.sl_grip = ForgeSlider("Grip length", 0.70, 1.40, 0.05, 1.0)
        self.sl_guard = ForgeSlider("Guard size", 0.75, 1.35, 0.05, 1.0)
        self.sl_pommel = ForgeSlider("Pommel size", 0.75, 1.40, 0.05, 1.0)
        self.sl_overall.valueChanged.connect(lambda v: self._set_attr("overall_size", v))
        self.sl_head.valueChanged.connect(lambda v: self._set_attr("head_size", v))
        self.sl_grip.valueChanged.connect(lambda v: self._set_attr("handle_length", v))
        self.sl_guard.valueChanged.connect(lambda v: self._set_attr("guard_size", v))
        self.sl_pommel.valueChanged.connect(lambda v: self._set_attr("pommel_size", v))
        for s in (self.sl_overall, self.sl_head, self.sl_grip, self.sl_guard, self.sl_pommel):
            sl.addWidget(s)
        sl.addStretch()
        size_scroll.setWidget(sw)
        self.look_stack.addWidget(size_scroll)

        # 1: Pattern
        pw = QWidget()
        pl = QVBoxLayout(pw)
        self.pattern_grid = QGridLayout()
        self.pattern_btn_group = QButtonGroup(self)
        self._rebuild_pattern_buttons()
        pl.addLayout(self.pattern_grid)
        self.sl_pat_str = ForgeSlider("Pattern strength", 0.0, 1.0, 0.05, 0.6)
        self.sl_pat_scale = ForgeSlider("Pattern density", 0.75, 2.0, 0.05, 1.0)
        self.sl_pat_str.valueChanged.connect(lambda v: self._set_attr("pattern_strength", v))
        self.sl_pat_scale.valueChanged.connect(lambda v: self._set_attr("pattern_scale", v))
        pl.addWidget(self.sl_pat_str)
        pl.addWidget(self.sl_pat_scale)
        pl.addWidget(QLabel("Pattern rotation"))
        rot_row = QHBoxLayout()
        self.pat_rot_group = QButtonGroup(self)
        for r_i in range(4):
            rb = QPushButton(f"{r_i * 90}°")
            rb.setCheckable(True)
            if r_i == 0:
                rb.setChecked(True)
            self.pat_rot_group.addButton(rb, r_i)
            rot_row.addWidget(rb)
        self.pat_rot_group.idClicked.connect(lambda r: self._set_attr("pattern_rotation", r))
        pl.addLayout(rot_row)
        pl.addStretch()
        self.look_stack.addWidget(pw)

        # 2: Color
        cw_scroll = QScrollArea()
        cw_scroll.setWidgetResizable(True)
        cw = QWidget()
        cl = QVBoxLayout(cw)
        cl.setSpacing(6)
        self.color_target_group = QButtonGroup(self)
        ct_grid = QGridLayout()
        for ci, cname in enumerate(["Blade", "Guard", "Grip", "Pattern", "Pommel"]):
            cb = QPushButton(cname)
            cb.setCheckable(True)
            if ci == 0:
                cb.setChecked(True)
            self.color_target_group.addButton(cb, ci)
            ct_grid.addWidget(cb, ci // 2, ci % 2)
        self.color_target_group.idClicked.connect(lambda _: self._sync_color_sliders_from_target())
        cl.addLayout(ct_grid)

        self.chk_link_pommel = QCheckBox("Match pommel to guard color")
        self.chk_link_pommel.setChecked(True)
        self.chk_link_pommel.toggled.connect(self._on_link_pommel_toggled)
        cl.addWidget(self.chk_link_pommel)

        preset_grid = QGridLayout()
        preset_grid.setSpacing(4)
        for pi, (pname, (pr, pg, pb)) in enumerate(COLOR_PRESETS):
            pbtn = QPushButton(pname)
            pbtn.setStyleSheet(
                f"text-align: left; padding-left: 10px; border-left: 5px solid rgb({int(pr*255)},{int(pg*255)},{int(pb*255)});"
            )
            pbtn.clicked.connect(lambda _, col=(pr, pg, pb): self._apply_color_to_target(col))
            preset_grid.addWidget(pbtn, pi // 3, pi % 3)
        cl.addLayout(preset_grid)

        self.sl_col_r = ForgeSlider("Red R", 0.0, 1.0, 1.0 / 255.0, 1.0, is_percent=False)
        self.sl_col_g = ForgeSlider("Green G", 0.0, 1.0, 1.0 / 255.0, 1.0, is_percent=False)
        self.sl_col_b = ForgeSlider("Blue B", 0.0, 1.0, 1.0 / 255.0, 1.0, is_percent=False)
        self.sl_col_r.valueChanged.connect(lambda _: self._on_rgb_sliders_moved())
        self.sl_col_g.valueChanged.connect(lambda _: self._on_rgb_sliders_moved())
        self.sl_col_b.valueChanged.connect(lambda _: self._on_rgb_sliders_moved())
        cl.addWidget(self.sl_col_r)
        cl.addWidget(self.sl_col_g)
        cl.addWidget(self.sl_col_b)

        swatch_row = QHBoxLayout()
        self.color_swatch = QFrame()
        self.color_swatch.setFixedHeight(22)
        self.color_swatch.setStyleSheet("background: #ffffff; border: 1px solid #485254;")
        btn_picker = QPushButton("🎨 Bảng màu...")
        btn_picker.clicked.connect(self._open_color_dialog)
        swatch_row.addWidget(self.color_swatch, 1)
        swatch_row.addWidget(btn_picker)
        cl.addLayout(swatch_row)
        cl.addStretch()
        cw_scroll.setWidget(cw)
        self.look_stack.addWidget(cw_scroll)

        # 3: Place
        plw = QWidget()
        pll = QVBoxLayout(plw)
        pll.addWidget(QLabel("Apply to (select multiple)"))
        ap_grid = QGridLayout()
        self.pat_part_chks: List[QPushButton] = []
        for idx, pname in enumerate(PATTERN_PARTS):
            pb = QPushButton(pname)
            pb.setCheckable(True)
            pb.setChecked(idx == 0)
            pb.toggled.connect(lambda chk, bit=idx: self._toggle_pattern_part(bit, chk))
            ap_grid.addWidget(pb, idx // 2, idx % 2)
            self.pat_part_chks.append(pb)
        pll.addLayout(ap_grid)

        pll.addWidget(QLabel("Pattern layout"))
        self.pat_layout_group = QButtonGroup(self)
        for li, lname in enumerate(PATTERN_LAYOUTS):
            lb = QPushButton(lname)
            lb.setCheckable(True)
            if li == 0:
                lb.setChecked(True)
            self.pat_layout_group.addButton(lb, li)
            pll.addWidget(lb)
        self.pat_layout_group.idClicked.connect(lambda i: self._set_attr("pattern_layout", i))

        self.sl_off_x = ForgeSlider("Horizontal offset", -0.5, 0.5, 0.05, 0.0)
        self.sl_off_y = ForgeSlider("Vertical offset", -0.5, 0.5, 0.05, 0.0)
        self.sl_off_x.valueChanged.connect(lambda v: self._set_attr("pattern_offset_x", v))
        self.sl_off_y.valueChanged.connect(lambda v: self._set_attr("pattern_offset_y", v))
        pll.addWidget(self.sl_off_x)
        pll.addWidget(self.sl_off_y)
        pll.addStretch()
        self.look_stack.addWidget(plw)

        # 4: Finish
        fw = QWidget()
        fl = QVBoxLayout(fw)
        fl.addWidget(QLabel("Metal finish"))
        self.finish_group = QButtonGroup(self)
        for fi, (fname, fdesc) in enumerate(zip(METAL_FINISHES, FINISH_DESCRIPTIONS)):
            fb = QPushButton(f"{fname}\n{fdesc}")
            fb.setCheckable(True)
            fb.setStyleSheet("text-align: left; padding: 8px;")
            if fi == 0:
                fb.setChecked(True)
            self.finish_group.addButton(fb, fi)
            fl.addWidget(fb)
        self.finish_group.idClicked.connect(lambda i: self._set_attr("metal_finish", i))
        fl.addStretch()
        self.look_stack.addWidget(fw)

        btn_reset_look = QPushButton("Reset appearance")
        btn_reset_look.clicked.connect(self._reset_appearance)
        lay.addWidget(btn_reset_look)
        self.left_stack.addWidget(w)

    def _rebuild_pattern_buttons(self) -> None:
        while self.pattern_grid.count():
            it = self.pattern_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for b in list(self.pattern_btn_group.buttons()):
            self.pattern_btn_group.removeButton(b)
        patterns = self.store.get_patterns()
        for pos, (idx, name) in enumerate(patterns):
            b = QPushButton(name)
            b.setCheckable(True)
            if idx == self.design.pattern:
                b.setChecked(True)
            self.pattern_btn_group.addButton(b, idx)
            self.pattern_grid.addWidget(b, pos // 2, pos % 2)
        self.pattern_btn_group.idClicked.connect(lambda i: self._set_attr("pattern", i))

    # ---- Left Page 2: Craft ----
    def _build_page_craft(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.craft_group = QButtonGroup(self)
        for i, (cname, cdesc) in enumerate(zip(CRAFTS, CRAFT_DESCRIPTIONS)):
            b = QPushButton(f"{cname}\n{cdesc}")
            b.setCheckable(True)
            b.setStyleSheet("text-align: left; padding: 10px;")
            if i == 0:
                b.setChecked(True)
            self.craft_group.addButton(b, i)
            lay.addWidget(b)
        self.craft_group.idClicked.connect(lambda i: self._set_attr("craft", i))
        lay.addStretch()
        self.left_stack.addWidget(w)

    # ---- Left Page 3: Story ----
    def _build_page_story(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Weapon name"))
        self.edit_wname = QLineEdit()
        self.edit_wname.setMaxLength(40)
        self.edit_wname.textChanged.connect(lambda t: self._set_attr("name", t))
        lay.addWidget(self.edit_wname)

        lay.addWidget(QLabel("Inscription"))
        self.edit_inscr = QLineEdit()
        self.edit_inscr.setMaxLength(100)
        self.edit_inscr.textChanged.connect(lambda t: self._set_attr("inscription", t))
        lay.addWidget(self.edit_inscr)

        lay.addWidget(QLabel("Background story"))
        self.edit_story = QTextEdit()
        self.edit_story.textChanged.connect(lambda: self._set_attr("story", self.edit_story.toPlainText()))
        lay.addWidget(self.edit_story, 1)
        self.left_stack.addWidget(w)

    # ---- Left Page 4: Enchant ----
    def _build_page_enchant(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        w = QWidget()
        lay = QVBoxLayout(w)
        self.enchant_group = QButtonGroup(self)
        for i, (ename, edesc) in enumerate(zip(ENCHANTMENTS, ENCHANTMENT_DESCRIPTIONS)):
            b = QPushButton(f"{ename}\n{edesc}")
            b.setCheckable(True)
            b.setStyleSheet("text-align: left; padding: 8px;")
            if i == 0:
                b.setChecked(True)
            self.enchant_group.addButton(b, i)
            lay.addWidget(b)
        self.enchant_group.idClicked.connect(lambda i: self._set_attr("enchantment", i))
        lay.addStretch()
        scroll.setWidget(w)
        self.left_stack.addWidget(scroll)

    # ---- State updates & Rendering ----
    def _on_kind_changed(self, kind: int) -> None:
        self.design.kind = kind
        # Clamp indices safely
        self.design.head = min(self.design.head, len(self.store.get_heads(kind)) - 1)
        self._rebuild_parts_grid()
        self.schedule_render()

    def _set_attr(self, attr: str, value) -> None:
        if self._blocking_ui:
            return
        setattr(self.design, attr, value)
        self.schedule_render()

    def _toggle_pattern_part(self, bit: int, checked: bool) -> None:
        if self._blocking_ui:
            return
        if checked:
            self.design.pattern_parts |= (1 << bit)
        else:
            self.design.pattern_parts &= ~(1 << bit)
        self.schedule_render()

    def _on_link_pommel_toggled(self, checked: bool) -> None:
        if self._blocking_ui:
            return
        if self.design.link_pommel_tint and not checked:
            self.design.pommel_tint = self.design.guard_tint
        self.design.link_pommel_tint = checked
        self._sync_color_sliders_from_target()
        self.schedule_render()

    def _get_target_color(self) -> Tuple[float, float, float]:
        t = self.color_target_group.checkedId()
        if t == 0:
            return self.design.head_tint
        if t == 1:
            return self.design.guard_tint
        if t == 2:
            return self.design.grip_tint
        if t == 3:
            return self.design.pattern_color
        return self.design.effective_pommel_tint

    def _apply_color_to_target(self, col: Tuple[float, float, float]) -> None:
        t = self.color_target_group.checkedId()
        min_c = 0.0 if t == 3 else 0.15
        clamped = (max(min_c, min(1.0, col[0])), max(min_c, min(1.0, col[1])), max(min_c, min(1.0, col[2])))
        if t == 0:
            self.design.head_tint = clamped
        elif t == 1:
            self.design.guard_tint = clamped
        elif t == 2:
            self.design.grip_tint = clamped
        elif t == 3:
            self.design.pattern_color = clamped
        else:
            self.design.link_pommel_tint = False
            self.design.pommel_tint = clamped
            self._blocking_ui = True
            self.chk_link_pommel.setChecked(False)
            self._blocking_ui = False
        self._sync_color_sliders_from_target()
        self.schedule_render()

    def _sync_color_sliders_from_target(self) -> None:
        t = self.color_target_group.checkedId()
        self.chk_link_pommel.setVisible(t == 4)
        col = self._get_target_color()
        self._blocking_ui = True
        self.sl_col_r.set_value(col[0], emit=False)
        self.sl_col_g.set_value(col[1], emit=False)
        self.sl_col_b.set_value(col[2], emit=False)
        self.color_swatch.setStyleSheet(
            f"background: rgb({int(col[0]*255)},{int(col[1]*255)},{int(col[2]*255)}); border: 1px solid #485254;"
        )
        self._blocking_ui = False

    def _on_rgb_sliders_moved(self) -> None:
        if self._blocking_ui:
            return
        col = (self.sl_col_r.value(), self.sl_col_g.value(), self.sl_col_b.value())
        self._apply_color_to_target(col)

    def _open_color_dialog(self) -> None:
        r, g, b = self._get_target_color()
        chosen = QColorDialog.getColor(QColor(int(r * 255), int(g * 255), int(b * 255)), self, "Chọn màu")
        if chosen.isValid():
            self._apply_color_to_target((chosen.redF(), chosen.greenF(), chosen.blueF()))

    def _reset_appearance(self) -> None:
        self.design.overall_size = self.design.head_size = self.design.handle_length = 1.0
        self.design.guard_size = self.design.pommel_size = self.design.pattern_scale = 1.0
        self.design.pattern_rotation = 0
        self.design.head_tint = self.design.guard_tint = self.design.grip_tint = (1.0, 1.0, 1.0)
        self.design.pattern = 0
        self.design.pattern_strength = 0.6
        self.design.pattern_color = (0.24, 0.22, 0.19)
        self.design.pattern_parts = 1
        self.design.pattern_layout = 0
        self.design.metal_finish = 0
        self.design.pattern_offset_x = self.design.pattern_offset_y = 0.0
        self.design.link_pommel_tint = True
        self.design.pommel_tint = (1.0, 1.0, 1.0)
        self._refresh_all_controls()
        self.schedule_render()

    def _refresh_all_controls(self) -> None:
        self._blocking_ui = True
        self.kind_group.button(self.design.kind).setChecked(True)
        self.combo_mat_head.setCurrentIndex(self.design.head_material_idx)
        self.combo_mat_guard.setCurrentIndex(self.design.guard_material_idx)
        self.combo_mat_grip.setCurrentIndex(self.design.grip_material_idx)

        self.sl_overall.set_value(self.design.overall_size, emit=False)
        self.sl_head.set_value(self.design.head_size, emit=False)
        self.sl_grip.set_value(self.design.handle_length, emit=False)
        self.sl_guard.set_value(self.design.guard_size, emit=False)
        self.sl_pommel.set_value(self.design.pommel_size, emit=False)

        if self.pattern_btn_group.button(self.design.pattern):
            self.pattern_btn_group.button(self.design.pattern).setChecked(True)
        self.sl_pat_str.set_value(self.design.pattern_strength, emit=False)
        self.sl_pat_scale.set_value(self.design.pattern_scale, emit=False)
        if self.pat_rot_group.button(self.design.pattern_rotation):
            self.pat_rot_group.button(self.design.pattern_rotation).setChecked(True)

        for bit, pb in enumerate(self.pat_part_chks):
            pb.setChecked(bool(self.design.pattern_parts & (1 << bit)))
        if self.pat_layout_group.button(self.design.pattern_layout):
            self.pat_layout_group.button(self.design.pattern_layout).setChecked(True)
        self.sl_off_x.set_value(self.design.pattern_offset_x, emit=False)
        self.sl_off_y.set_value(self.design.pattern_offset_y, emit=False)

        if self.finish_group.button(self.design.metal_finish):
            self.finish_group.button(self.design.metal_finish).setChecked(True)
        if self.craft_group.button(self.design.craft):
            self.craft_group.button(self.design.craft).setChecked(True)
        if self.enchant_group.button(self.design.enchantment):
            self.enchant_group.button(self.design.enchantment).setChecked(True)

        self.chk_link_pommel.setChecked(self.design.link_pommel_tint)
        self.edit_wname.setText(self.design.name)
        self.edit_inscr.setText(self.design.inscription)
        self.edit_story.setPlainText(self.design.story)
        self._blocking_ui = False
        self._sync_color_sliders_from_target()

    def _randomize_design(self) -> None:
        k = self.design.kind
        self.design.head = random.randint(0, max(0, len(self.store.get_heads(k)) - 1))
        self.design.guard = random.randint(0, max(0, len(self.store.get_guards(k)) - 1))
        self.design.grip = random.randint(0, max(0, len(self.store.get_grips()) - 1))
        self.design.pommel = random.randint(0, max(0, len(self.store.get_pommels(k)) - 1))
        self.design.pattern = random.randint(0, max(0, len(self.store.get_patterns()) - 1))
        self.design.metal_finish = random.randint(0, 3)
        self.design.head_tint = random.choice(COLOR_PRESETS)[1]
        self.design.guard_tint = random.choice(COLOR_PRESETS)[1]
        self.design.grip_tint = random.choice(COLOR_PRESETS)[1]
        self.design.pattern_color = random.choice(COLOR_PRESETS)[1]
        self.design.enchantment = random.randint(0, 6)
        self._rebuild_parts_grid()
        self._refresh_all_controls()
        self.schedule_render()

    def schedule_render(self) -> None:
        self._render_timer.start()

    def _render_now(self) -> None:
        res = compose_weapon(self.store, self.design, resolution=512)
        self._last_composed = res
        self.preview_canvas.set_composed(res, self.design.enchantment)
        self.held_preview.set_composed(res, self.design.enchantment)

        title = self.design.name.strip() or f"Custom {KINDS[self.design.kind]}"
        self.lbl_weapon_name.setText(title)
        self.lbl_enchant_badge.setText(
            f"Enchantment: {ENCHANTMENTS[self.design.enchantment]}" if self.design.enchantment > 0 else "No enchantment"
        )

        st = self.store.compute_stats(self.design)
        self._stat_labels["damage"].setText(f"{st['damage']:.1f}")
        self._stat_labels["ap"].setText(f"{st['armor_pen'] * 100:.1f}%")
        self._stat_labels["cooldown"].setText(f"{st['cooldown']:.2f} s")
        self._stat_labels["dps"].setText(f"{st['dps']:.2f}")
        self._stat_labels["mass"].setText(f"{st['mass']:.2f} kg")
        self._stat_labels["skill"].setText(str(st["req_skill"]))
        self._stat_labels["work"].setText(f"{st['work']:,.0f}")
        self._stat_labels["ench"].setText(f"+{st['ench_damage']} dmg" if st["ench_damage"] > 0 else "—")

        ing_lines = [f"• {k}: {v}" for k, v in st["ingredients"].items()]
        self.lbl_ingredients.setText("\n".join(ing_lines))

    def preview_custom_part(self, category: str, kind: int, slot_idx: int, pil_img: Image.Image, socket_x: float) -> None:
        """Applies a temporary in-memory part from the Splitter and renders it live."""
        if category == "pattern":
            pid = f"pattern_{slot_idx}"
            self.store.set_temp_part(pid, pil_img)
            self.design.pattern = slot_idx
            self.design.pattern_strength = max(self.design.pattern_strength, 0.7)
            self._rebuild_pattern_buttons()
        elif category == "head":
            pid = f"head_{kind}_{slot_idx}"
            self.store.set_temp_part(pid, pil_img, socket_x=socket_x)
            self.design.kind = kind
            self.design.head = slot_idx
            self.part_cat_group.button(0).setChecked(True)
        elif category == "guard":
            pid = f"master_guard_{kind}" if slot_idx == 3 else f"guard_{slot_idx}"
            self.store.set_temp_part(pid, pil_img)
            self.design.guard = slot_idx
            self.part_cat_group.button(1).setChecked(True)
        elif category == "grip":
            pid = f"grip_{slot_idx}"
            self.store.set_temp_part(pid, pil_img)
            self.design.grip = slot_idx
            self.part_cat_group.button(2).setChecked(True)
        elif category == "pommel":
            pid = f"master_pommel_{kind}" if slot_idx == 2 else f"pommel_{slot_idx}"
            self.store.set_temp_part(pid, pil_img)
            self.design.pommel = slot_idx
            self.part_cat_group.button(3).setChecked(True)

        self._rebuild_parts_grid()
        self._refresh_all_controls()
        self._render_now()

    def _export_weapon_png(self) -> None:
        if self._last_composed is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Lưu ảnh vũ khí (PNG)", str(self.store.mod_root / "weapon_preview.png"), "PNG (*.png)")
        if path:
            self._last_composed.image_rgba.save(path, "PNG")
            QMessageBox.information(self, "Đã xuất", f"Đã lưu ảnh vũ khí tại:\n{path}")

    def _save_preset_json(self) -> None:
        from dataclasses import asdict
        path, _ = QFileDialog.getSaveFileName(self, "Lưu Preset thiết kế", str(self.store.mod_root / "weapon_preset.json"), "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps(asdict(self.design), indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_preset_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Mở Preset thiết kế", str(self.store.mod_root), "JSON (*.json)")
        if path:
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                for k, v in data.items():
                    if hasattr(self.design, k):
                        if isinstance(v, list) and len(v) == 3:
                            v = tuple(v)
                        setattr(self.design, k, v)
                self._rebuild_parts_grid()
                self._refresh_all_controls()
                self._render_now()
            except Exception as exc:
                QMessageBox.warning(self, "Lỗi đọc Preset", str(exc))


class CodeSyncWorkspace(QWidget):
    """Tab 3: Export C#/XML into Overgeared 1.7 code & Import C# WeaponDesign snippets."""
    presetImported = None

    def __init__(self, store: ModAssetStore, forge: ForgeWorkspace, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.store = store
        self.forge = forge
        self._build_ui()

    def _build_ui(self) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # Left: Custom Parts Registry + Actions
        left = QFrame()
        left.setObjectName("Panel")
        left.setFixedWidth(360)
        ll = QVBoxLayout(left)

        lbl = QLabel("Quản lý Part đã thêm & Import vào Code (1.7)")
        lbl.setObjectName("GoldTitle")
        lbl.setWordWrap(True)
        ll.addWidget(lbl)

        self.parts_list = QListWidget()
        ll.addWidget(self.parts_list, 1)

        btn_del = QPushButton("🗑 Xóa Part đang chọn khỏi Registry")
        btn_del.clicked.connect(self._delete_selected_part)
        ll.addWidget(btn_del)

        btn_refresh = QPushButton("🔄 Tạo lại Code C# & XML")
        btn_refresh.clicked.connect(self.refresh_code)
        btn_copy = QPushButton("📋 Copy C# Code vào Clipboard")
        btn_copy.setObjectName("PrimaryBtn")
        btn_copy.clicked.connect(self._copy_cs)

        btn_export_mod = QPushButton("💾 Ghi C# + XML + Language vào Overgeared (1.7)")
        btn_export_mod.setObjectName("AccentGreenBtn")
        btn_export_mod.setFixedHeight(38)
        btn_export_mod.clicked.connect(self._write_to_mod)

        ll.addWidget(btn_refresh)
        ll.addWidget(btn_copy)
        ll.addWidget(btn_export_mod)

        # Import C# WeaponDesign snippet box
        imp_box = QGroupBox("Import ngược từ C# WeaponDesign snippet")
        il = QVBoxLayout(imp_box)
        self.txt_import = QPlainTextEdit()
        self.txt_import.setPlaceholderText("Dán đoạn C# 'new WeaponDesign { kind = 0, head = 2, headTint = new Color(0.8f, 0.2f, 0.2f), ... }' vào đây...")
        self.txt_import.setFixedHeight(110)
        btn_imp = QPushButton("📥 Load Snippet vào Lò Rèn")
        btn_imp.clicked.connect(self._import_csharp_snippet)
        il.addWidget(self.txt_import)
        il.addWidget(btn_imp)
        ll.addWidget(imp_box)

        lay.addWidget(left)

        # Right: Code Preview Tabs (C# / XML)
        right = QTabWidget()
        self.cs_view = QPlainTextEdit()
        self.cs_view.setReadOnly(True)
        self.cs_view.setFont(QFont("Consolas", 10))
        self.xml_view = QPlainTextEdit()
        self.xml_view.setReadOnly(True)
        self.xml_view.setFont(QFont("Consolas", 10))

        right.addTab(self.cs_view, "C# Code (PersonalForge 1.7)")
        right.addTab(self.xml_view, "XML Manifest (CustomParts)")
        lay.addWidget(right, 1)

        self.refresh_code()

    def refresh_code(self) -> None:
        self.parts_list.clear()
        for pid, e in sorted(self.store.custom_parts.items()):
            loc = "Atlas" if e.is_atlas_cell else e.texture_rel_path
            self.parts_list.addItem(QListWidgetItem(f"[{e.category.upper()}] {pid} — {e.name} ({loc})"))
        self.cs_view.setPlainText(generate_csharp_code(self.store, self.forge.design))
        self.xml_view.setPlainText(generate_xml_custom_defs(self.store))

    def _delete_selected_part(self) -> None:
        row = self.parts_list.currentRow()
        if row < 0:
            return
        keys = sorted(self.store.custom_parts.keys())
        pid = keys[row]
        self.store.custom_parts.pop(pid, None)
        self.store.save_custom_registry()
        self.store.clear_caches()
        self.forge._rebuild_parts_grid()
        self.refresh_code()

    def _copy_cs(self) -> None:
        QApplication.clipboard().setText(self.cs_view.toPlainText())
        QMessageBox.information(self, "Đã copy", "Đã copy toàn bộ code C# vào Clipboard!")

    def _write_to_mod(self) -> None:
        src_dir = self.store.mod_root / "1.7" / "Source" / "PersonalForge"
        src_dir.mkdir(parents=True, exist_ok=True)
        cs_path = src_dir / "CustomPartsGenerated.cs"
        cs_path.write_text(self.cs_view.toPlainText(), encoding="utf-8")

        xml_path = self.store.mod_root / "Defs" / "CustomParts_Manifest.xml"
        xml_path.write_text(self.xml_view.toPlainText(), encoding="utf-8")

        lang_paths = update_language_xml(self.store)
        msg = f"Đã xuất thành công vào Mod Overgeared (1.7):\n• {cs_path}\n• {xml_path}"
        for lp in lang_paths:
            msg += f"\n• {lp}"
        QMessageBox.information(self, "Xuất Code thành công", msg)

    def _import_csharp_snippet(self) -> None:
        txt = self.txt_import.toPlainText()
        if not txt.strip():
            return
        d = self.forge.design
        int_map = {
            "kind": "kind", "head": "head", "guard": "guard", "grip": "grip", "pommel": "pommel",
            "pattern": "pattern", "patternRotation": "pattern_rotation", "patternParts": "pattern_parts",
            "patternLayout": "pattern_layout", "metalFinish": "metal_finish",
            "craft": "craft", "enchantment": "enchantment",
        }
        float_map = {
            "overallSize": "overall_size", "headSize": "head_size", "handleLength": "handle_length",
            "guardSize": "guard_size", "pommelSize": "pommel_size", "patternScale": "pattern_scale",
            "patternStrength": "pattern_strength", "patternOffsetX": "pattern_offset_x", "patternOffsetY": "pattern_offset_y",
        }
        color_map = {
            "headTint": "head_tint", "guardTint": "guard_tint", "gripTint": "grip_tint",
            "pommelTint": "pommel_tint", "patternColor": "pattern_color",
        }
        for cs_k, py_k in int_map.items():
            m = re.search(rf"\b{cs_k}\s*=\s*(-?\d+)", txt)
            if m:
                setattr(d, py_k, int(m.group(1)))
        for cs_k, py_k in float_map.items():
            m = re.search(rf"\b{cs_k}\s*=\s*(-?\d+(?:\.\d+)?)f?", txt)
            if m:
                setattr(d, py_k, float(m.group(1)))
        for cs_k, py_k in color_map.items():
            m = re.search(rf"\b{cs_k}\s*=\s*new\s+Color\(\s*([\d.]+)f?\s*,\s*([\d.]+)f?\s*,\s*([\d.]+)f?", txt)
            if m:
                setattr(d, py_k, (float(m.group(1)), float(m.group(2)), float(m.group(3))))
        m_link = re.search(r"\blinkPommelTint\s*=\s*(true|false)", txt)
        if m_link:
            d.link_pommel_tint = (m_link.group(1) == "true")

        self.forge._rebuild_parts_grid()
        self.forge._refresh_all_controls()
        self.forge._render_now()
        QMessageBox.information(self, "Import thành công", "Đã nạp cấu hình từ C# snippet vào Lò Rèn!")


class ForgeStudioWindow(QMainWindow):
    def __init__(self, mod_root: Path):
        super().__init__()
        self.setWindowTitle("Overgeared Forge Studio · RimWorld 1.7 (Personal Forge)")
        self.resize(1380, 880)

        self.store = ModAssetStore(mod_root)

        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QVBoxLayout(central)
        main_lay.setContentsMargins(6, 6, 6, 6)
        main_lay.setSpacing(6)

        # Global Top Bar
        top = QHBoxLayout()
        badge = QLabel("RIMWORLD 1.7 · PERSONAL FORGE STUDIO")
        badge.setStyleSheet(
            "background: #3d3321; color: #f0cc87; border: 1px solid #c49645; "
            "padding: 4px 10px; border-radius: 3px; font-weight: 700;"
        )
        top.addWidget(badge)

        self.lbl_mod_path = QLabel(f"Thư mục Mod: {self.store.mod_root}")
        self.lbl_mod_path.setObjectName("MutedLabel")
        top.addWidget(self.lbl_mod_path, 1)

        btn_pick_mod = QPushButton("📁 Đổi thư mục Mod...")
        btn_pick_mod.clicked.connect(self._pick_mod_folder)
        top.addWidget(btn_pick_mod)
        main_lay.addLayout(top)

        # Tabs
        self.tabs = QTabWidget()
        self.forge_tab = ForgeWorkspace(self.store)
        self.splitter_tab = PartSplitterWorkspace(self.store)
        self.code_tab = CodeSyncWorkspace(self.store, self.forge_tab)

        self.tabs.addTab(self.forge_tab, "⚒️ Lò Rèn & Test Trang Bị (1.7)")
        self.tabs.addTab(self.splitter_tab, "✂️ Import Ảnh & Tách Part Nhanh")
        self.tabs.addTab(self.code_tab, "💻 Import vào Code (C# / XML 1.7)")
        main_lay.addWidget(self.tabs, 1)

        # Wire cross-tab signals
        self.splitter_tab.partTestedInForge.connect(self._on_test_part_in_forge)
        self.splitter_tab.modPartsUpdated.connect(self._on_mod_parts_updated)
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_test_part_in_forge(self, cat: str, kind: int, slot_idx: int, pil_img: Image.Image, sock: float) -> None:
        self.forge_tab.preview_custom_part(cat, kind, slot_idx, pil_img, sock)
        self.tabs.setCurrentIndex(0)

    def _on_mod_parts_updated(self, cat: str, kind: int, slot_idx: int) -> None:
        if cat == "head":
            self.forge_tab.design.kind = kind
            self.forge_tab.design.head = slot_idx
        elif cat == "guard":
            self.forge_tab.design.guard = slot_idx
        elif cat == "grip":
            self.forge_tab.design.grip = slot_idx
        elif cat == "pommel":
            self.forge_tab.design.pommel = slot_idx
        elif cat == "pattern":
            self.forge_tab.design.pattern = slot_idx
            self.forge_tab._rebuild_pattern_buttons()
        self.forge_tab._rebuild_parts_grid()
        self.forge_tab._refresh_all_controls()
        self.forge_tab._render_now()
        self.code_tab.refresh_code()

    def _on_tab_changed(self, idx: int) -> None:
        if idx == 2:
            self.code_tab.refresh_code()

    def _pick_mod_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục Mod Overgeared", str(self.store.mod_root))
        if folder:
            self.store.set_mod_root(folder)
            self.lbl_mod_path.setText(f"Thư mục Mod: {self.store.mod_root}")
            self.forge_tab._rebuild_parts_grid()
            self.forge_tab._rebuild_pattern_buttons()
            self.forge_tab._render_now()
            self.splitter_tab._refresh_slot_combo()
            self.code_tab.refresh_code()


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(FORGE_QSS)

    mod_root = DEFAULT_MOD_ROOT if DEFAULT_MOD_ROOT.exists() else Path(__file__).resolve().parent.parent / "Overgeared"
    win = ForgeStudioWindow(mod_root)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
