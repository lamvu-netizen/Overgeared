"""
Special Weapons Workspace Tab for Overgeared Forge Studio (RimWorld 1.7).
Displays standalone complete legendary weapons (no modular forge part assembly required)
with full interactive preview, Colonist Held Preview, signature VFX toggle / alternate VFX
experimentation, and 1-click PNG + RimWorld ThingDef XML export.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from combat_arena_widget import RimWorldCombatArenaWidget
from forge_canvas import ForgePreviewCanvas
from mod_data import (
    BUILTIN_ELEMENTS,
    COLOR_PRESETS,
    KINDS,
    METAL_FINISHES,
    ModAssetStore,
    SPECIAL_WEAPONS,
    SpecialWeaponDef,
    is_element_allowed,
)
from special_weapon_renderer import render_special_weapon
from theme import ForgeSlider, pil_to_qpixmap


SKILL_FX_DEF_MAP: Dict[str, str] = {
    "sk_abyssal_dragon_cleave": "OG_Fx_PhongLongTram",
    "sk_phantom_blink": "OG_Fx_BaoTocAnhBo",
    "sk_cyclone_vortex": "OG_Fx_LongQuyenTanAnh",
    "sk_soaring_pierce": "OG_Fx_LongPhongPhaKich",
    "sk_pentagram_cataclysm": "OG_Fx_NguMangTinhTran",
    "sk_ink_eclipse_ring": "OG_Fx_HacNhatTram",
    "sk_ink_void_wave": "OG_Fx_ThaiHuTramBa",
    "sk_ink_void_aegis": "OG_Fx_HacGiapHoThe",
    "sk_ink_shadow_spikes": "OG_Fx_LeAnhPhaToai",
    "sk_ink_blood_eclipse": "OG_Fx_HuyetNguyetVoAnh",
}


def generate_special_weapon_xml(weapon: SpecialWeaponDef, elem_damage_def: str) -> str:
    """Generates a complete RimWorld 1.7 ThingDef XML snippet for a standalone special weapon."""
    root = ET.Element("Defs")
    td = ET.SubElement(root, "ThingDef", ParentName="BaseMeleeWeapon_Sharp_Quality")
    ET.SubElement(td, "defName").text = weapon.def_name
    ET.SubElement(td, "label").text = weapon.name.split("(")[0].strip()
    ET.SubElement(td, "description").text = weapon.lore
    ET.SubElement(td, "techLevel").text = "Ultra"

    gd = ET.SubElement(td, "graphicData")
    ET.SubElement(gd, "texPath").text = f"PersonalForge/{weapon.texture_rel_path.replace('.png', '')}"
    ET.SubElement(gd, "graphicClass").text = "Graphic_Single"
    ET.SubElement(gd, "drawSize").text = "1.35"

    stat_bases = ET.SubElement(td, "statBases")
    ET.SubElement(stat_bases, "WorkToMake").text = f"{int(weapon.work)}"
    ET.SubElement(stat_bases, "Mass").text = f"{weapon.mass:.2f}"

    ET.SubElement(td, "equippedAngleOffset").text = "-25"
    ET.SubElement(td, "weaponClasses").append(ET.Element("li"))
    td.find("weaponClasses/li").text = "MeleePiercer"

    cost_list = ET.SubElement(td, "costList")
    for mat_name, amt in weapon.ingredients:
        ET.SubElement(cost_list, mat_name).text = str(int(amt))

    recipe = ET.SubElement(td, "recipeMaker")
    sr = ET.SubElement(recipe, "skillRequirements")
    ET.SubElement(sr, "Crafting").text = str(weapon.req_skill)

    tools = ET.SubElement(td, "tools")
    for lbl, cap, power, cd in [
        ("handle", "Poke", 9.0, 2.0),
        ("point", "Stab", round(weapon.damage * 0.92, 1), weapon.cooldown),
        ("edge", "Cut", round(weapon.damage, 1), weapon.cooldown),
    ]:
        li = ET.SubElement(tools, "li")
        ET.SubElement(li, "label").text = lbl
        caps = ET.SubElement(li, "capacities")
        ET.SubElement(caps, "li").text = cap
        ET.SubElement(li, "power").text = str(power)
        ET.SubElement(li, "cooldownTime").text = str(cd)
        if lbl != "handle":
            ET.SubElement(li, "armorPenetration").text = f"{weapon.armor_pen:.2f}"

    if elem_damage_def:
        me = ET.SubElement(td, "modExtensions")
        ext = ET.SubElement(me, "li", Class="PersonalForge.SpecialWeaponVfxExtension")
        ET.SubElement(ext, "enchantmentDamageDef").text = elem_damage_def

    if weapon.exclusive_skills:
        comps = ET.SubElement(td, "comps")
        c_li = ET.SubElement(comps, "li", Class="OvergearedCore.CompProperties_OvergearedWeaponSkills")
        ET.SubElement(c_li, "cooldownTicks").text = "180"
        sk_list = ET.SubElement(c_li, "skills")
        for sid in weapon.exclusive_skills:
            fx_def = SKILL_FX_DEF_MAP.get(sid)
            if fx_def:
                ET.SubElement(sk_list, "li").text = fx_def

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


class SpecialWeaponsWorkspace(QWidget):
    """Tab: Vũ Khí Đặc Biệt — Complete standalone weapons (no forge part assembly)."""

    def __init__(self, store: ModAssetStore, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.store = store
        self._selected_idx = 0
        self._tint_rgb: Tuple[float, float, float] = (1.0, 1.0, 1.0)
        self._metal_finish: int = 0
        self._use_signature_vfx: bool = True
        self._override_elem_id: int = SPECIAL_WEAPONS[0].default_element_id
        self._vfx_intensity: float = 1.25
        self._last_result = None

        self._build_ui()
        self._select_weapon(0)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # ---- LEFT COLUMN: Catalog & Effect Controls ----
        left_panel = QFrame()
        left_panel.setObjectName("Panel")
        left_panel.setFixedWidth(365)
        ll = QVBoxLayout(left_panel)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(8)

        hdr = QLabel("🗡️ Kho Vũ Khí Đặc Biệt (Nguyên Khối)")
        hdr.setObjectName("GoldTitle")
        sub = QLabel("Trang bị hoàn chỉnh ngoại hình & hiệu ứng riêng, không cần ghép các phôi")
        sub.setObjectName("MutedLabel")
        sub.setWordWrap(True)
        ll.addWidget(hdr)
        ll.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        cat_host = QWidget()
        self.catalog_lay = QVBoxLayout(cat_host)
        self.catalog_lay.setContentsMargins(2, 2, 2, 2)
        self.catalog_lay.setSpacing(6)
        self.weapon_group = QButtonGroup(self)
        self.weapon_group.idClicked.connect(self._select_weapon)

        for idx, sw in enumerate(SPECIAL_WEAPONS):
            res_thumb = render_special_weapon(self.store, sw, resolution=192, save_asset=False)
            pix = pil_to_qpixmap(res_thumb.image_rgba).scaled(
                54, 54, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            card = QPushButton(f"{sw.name}\n{sw.subtitle} · Dmg {sw.damage:.0f} · AP {sw.armor_pen*100:.0f}%")
            card.setCheckable(True)
            card.setIcon(pix)
            card.setIconSize(pix.size())
            card.setStyleSheet("text-align: left; padding: 8px 10px;")
            if idx == 0:
                card.setChecked(True)
            self.weapon_group.addButton(card, idx)
            self.catalog_lay.addWidget(card)
        self.catalog_lay.addStretch()
        scroll.setWidget(cat_host)
        ll.addWidget(scroll, 1)

        # Appearance tint / finish & VFX testing controls
        ctrl_frame = QFrame()
        ctrl_frame.setStyleSheet("background: #131718; border: 1px solid #353f42; border-radius: 4px;")
        cl = QVBoxLayout(ctrl_frame)
        cl.setContentsMargins(8, 8, 8, 8)
        cl.setSpacing(6)

        cl.addWidget(QLabel("Thử nghiệm Hiệu Ứng & Màu Sắc:"))
        self.chk_vfx = QCheckBox("Bật hiệu ứng nguyên bản (U Minh Tử Khí)")
        self.chk_vfx.setChecked(True)
        self.chk_vfx.toggled.connect(self._on_vfx_toggled)
        cl.addWidget(self.chk_vfx)

        vfx_row = QHBoxLayout()
        vfx_row.addWidget(QLabel("Hiệu ứng VFX:"))
        self.combo_vfx = QComboBox()
        self.combo_vfx.currentIndexChanged.connect(self._on_vfx_combo_changed)
        vfx_row.addWidget(self.combo_vfx, 1)
        cl.addLayout(vfx_row)

        self.sl_vfx_int = ForgeSlider("Cường độ VFX", 0.3, 2.2, 0.05, 1.25)
        self.sl_vfx_int.valueChanged.connect(self._on_intensity_changed)
        cl.addWidget(self.sl_vfx_int)

        fin_row = QHBoxLayout()
        fin_row.addWidget(QLabel("Bề mặt kim loại:"))
        self.combo_finish = QComboBox()
        for fn in METAL_FINISHES:
            self.combo_finish.addItem(fn)
        self.combo_finish.currentIndexChanged.connect(self._on_finish_changed)
        fin_row.addWidget(self.combo_finish, 1)
        cl.addLayout(fin_row)

        tint_row = QHBoxLayout()
        btn_tint = QPushButton("🎨 Đổi màu thử")
        btn_tint.clicked.connect(self._pick_tint)
        btn_reset_tint = QPushButton("↺ Màu gốc")
        btn_reset_tint.clicked.connect(self._reset_appearance)
        tint_row.addWidget(btn_tint)
        tint_row.addWidget(btn_reset_tint)
        cl.addLayout(tint_row)
        ll.addWidget(ctrl_frame)
        root.addWidget(left_panel)

        # ---- CENTER COLUMN: 60 FPS Preview & Colonist Held Preview ----
        mid_panel = QFrame()
        mid_panel.setObjectName("Panel")
        mid_lay = QVBoxLayout(mid_panel)
        mid_lay.setContentsMargins(10, 10, 10, 10)
        mid_lay.setSpacing(6)

        mid_top = QHBoxLayout()
        title_col = QVBoxLayout()
        self.lbl_title = QLabel("")
        self.lbl_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #f0cc87;")
        self.lbl_badge = QLabel("")
        self.lbl_badge.setObjectName("MutedLabel")
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_badge)
        mid_top.addLayout(title_col, 1)

        self.combo_backdrop = QComboBox()
        self.combo_backdrop.addItems(["Nền: Lò Rèn Tối", "Nền: Sàn Đá", "Nền: Cỏ RimWorld", "Nền: Caro Trong Suốt"])
        self.combo_backdrop.currentIndexChanged.connect(lambda i: self.preview_canvas.set_backdrop_mode(i))
        mid_top.addWidget(self.combo_backdrop)

        self.btn_swing = QPushButton("⚔ Test Vung Vũ Khí")
        self.btn_swing.setCheckable(True)
        self.btn_swing.toggled.connect(lambda c: self.preview_canvas.set_swing_test(c))
        mid_top.addWidget(self.btn_swing)
        mid_lay.addLayout(mid_top)

        self.preview_canvas = ForgePreviewCanvas(self.store.get_sparkle_pil())
        self.preview_canvas.set_store(self.store)
        mid_lay.addWidget(self.preview_canvas, 1)

        self.combat_arena = RimWorldCombatArenaWidget(self.store.mod_root)
        mid_lay.addWidget(self.combat_arena)
        root.addWidget(mid_panel, 1)

        # ---- RIGHT COLUMN: Stats, Lore & RimWorld Export ----
        right_panel = QFrame()
        right_panel.setObjectName("Panel")
        right_panel.setFixedWidth(300)
        rl = QVBoxLayout(right_panel)
        rl.setContentsMargins(10, 10, 10, 10)
        rl.setSpacing(6)

        lbl_st = QLabel("Thông Số Vũ Khí Đặc Biệt")
        lbl_st.setObjectName("GoldTitle")
        rl.addWidget(lbl_st)

        grid = QGridLayout()
        self._stat_labels: Dict[str, QLabel] = {}
        for r_i, (k, txt) in enumerate([
            ("damage", "Damage"),
            ("ap", "Armor penetration"),
            ("cooldown", "Cooldown"),
            ("dps", "DPS"),
            ("mass", "Mass"),
            ("skill", "Required skill"),
            ("work", "Work to make"),
            ("ench", "Bonus element dmg"),
        ]):
            k_lbl = QLabel(txt)
            k_lbl.setObjectName("MutedLabel")
            v_lbl = QLabel("—")
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            v_lbl.setStyleSheet("font-weight: 700; color: #e2eaec;")
            grid.addWidget(k_lbl, r_i, 0)
            grid.addWidget(v_lbl, r_i, 1)
            self._stat_labels[k] = v_lbl
        rl.addLayout(grid)

        rl.addWidget(QLabel("Nguyên liệu rèn:"))
        self.lbl_ingredients = QLabel("—")
        self.lbl_ingredients.setObjectName("MutedLabel")
        self.lbl_ingredients.setWordWrap(True)
        rl.addWidget(self.lbl_ingredients)

        rl.addWidget(QLabel("Mô tả & Truyền thuyết:"))
        self.lbl_lore = QLabel("")
        self.lbl_lore.setWordWrap(True)
        self.lbl_lore.setStyleSheet("color: #cfd9dc; font-size: 11px;")
        rl.addWidget(self.lbl_lore)

        rl.addWidget(QLabel("XML ThingDef (RimWorld 1.7):"))
        self.ed_xml = QTextEdit()
        self.ed_xml.setReadOnly(True)
        self.ed_xml.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        rl.addWidget(self.ed_xml, 1)

        btn_save_png = QPushButton("💾 Lưu Sprite PNG (512px)")
        btn_save_png.setObjectName("PrimaryBtn")
        btn_save_png.clicked.connect(self._export_png)
        rl.addWidget(btn_save_png)

        btn_save_xml = QPushButton("📦 Xuất XML vào Overgeared/Defs")
        btn_save_xml.setObjectName("AccentGreenBtn")
        btn_save_xml.clicked.connect(self._export_xml_to_mod)
        rl.addWidget(btn_save_xml)

        root.addWidget(right_panel)

    def refresh_vfx_list(self) -> None:
        sw = SPECIAL_WEAPONS[self._selected_idx]
        cur_id = self._override_elem_id
        self.combo_vfx.blockSignals(True)
        self.combo_vfx.clear()
        for el in self.store.get_elements_for_kind(sw.kind):
            self.combo_vfx.addItem(el.name, el.id)
        idx = self.combo_vfx.findData(cur_id)
        if idx < 0:
            idx = self.combo_vfx.findData(sw.default_element_id)
        if idx >= 0:
            self.combo_vfx.setCurrentIndex(idx)
            self._override_elem_id = int(self.combo_vfx.currentData())
        self.combo_vfx.blockSignals(False)

    def _select_weapon(self, idx: int) -> None:
        self._selected_idx = max(0, min(len(SPECIAL_WEAPONS) - 1, idx))
        sw = SPECIAL_WEAPONS[self._selected_idx]
        self._override_elem_id = sw.default_element_id
        self._use_signature_vfx = True
        self.chk_vfx.blockSignals(True)
        self.chk_vfx.setChecked(True)
        sig_elem = self.store.get_element(sw.default_element_id)
        self.chk_vfx.setText(f"Bật hiệu ứng nguyên bản ({sig_elem.name.split('(')[0].strip()})")
        self.chk_vfx.blockSignals(False)
        self.refresh_vfx_list()
        self.combat_arena.set_exclusive_skills(sw.exclusive_skills)
        self._render_now()

    def _on_vfx_toggled(self, checked: bool) -> None:
        self._use_signature_vfx = checked
        self.combo_vfx.setEnabled(checked)
        self._render_now()

    def _on_vfx_combo_changed(self, _idx: int) -> None:
        data = self.combo_vfx.currentData()
        if data is not None:
            self._override_elem_id = int(data)
            self._render_now()

    def _on_intensity_changed(self, val: float) -> None:
        self._vfx_intensity = val
        self._render_now()

    def _on_finish_changed(self, idx: int) -> None:
        self._metal_finish = idx
        self._render_now()

    def _pick_tint(self) -> None:
        r, g, b = self._tint_rgb
        chosen = QColorDialog.getColor(QColor(int(r * 255), int(g * 255), int(b * 255)), self, "Chọn màu thử cho vũ khí")
        if chosen.isValid():
            self._tint_rgb = (max(0.2, chosen.redF()), max(0.2, chosen.greenF()), max(0.2, chosen.blueF()))
            self._render_now()

    def _reset_appearance(self) -> None:
        self._tint_rgb = (1.0, 1.0, 1.0)
        self._metal_finish = 0
        self.combo_finish.setCurrentIndex(0)
        self._render_now()

    def _render_now(self) -> None:
        sw = SPECIAL_WEAPONS[self._selected_idx]
        res = render_special_weapon(
            self.store,
            sw,
            resolution=512,
            tint_rgb=self._tint_rgb,
            metal_finish=self._metal_finish,
            save_asset=True,
        )
        self._last_result = res

        elem_id = self._override_elem_id if self._use_signature_vfx else 0
        elem = self.store.get_element(elem_id)
        if not is_element_allowed(elem, sw.kind):
            elem = BUILTIN_ELEMENTS[0]

        self.preview_canvas.set_composed(res, elem, socket_gem=False, vfx_intensity=self._vfx_intensity)
        self.combat_arena.set_composed(
            res, elem, socket_gem=False, vfx_intensity=self._vfx_intensity,
            base_damage=float(sw.damage), cooldown_sec=float(sw.cooldown),
        )

        self.lbl_title.setText(sw.name)
        self.lbl_badge.setText(
            f"{sw.subtitle} · Hiệu ứng: {elem.name}" if elem.id > 0 else f"{sw.subtitle} · Không hiệu ứng"
        )
        dps = sw.damage / max(sw.cooldown, 0.01)
        self._stat_labels["damage"].setText(f"{sw.damage:.1f}")
        self._stat_labels["ap"].setText(f"{sw.armor_pen * 100:.1f}%")
        self._stat_labels["cooldown"].setText(f"{sw.cooldown:.2f} s")
        self._stat_labels["dps"].setText(f"{dps:.2f}")
        self._stat_labels["mass"].setText(f"{sw.mass:.2f} kg")
        self._stat_labels["skill"].setText(str(sw.req_skill))
        self._stat_labels["work"].setText(f"{sw.work:,.0f}")
        self._stat_labels["ench"].setText(f"+{elem.damage} dmg" if elem.damage > 0 else "—")
        self.lbl_ingredients.setText(" · ".join(f"{k}: {v}" for k, v in sw.ingredients))
        self.lbl_lore.setText(f"{sw.description}\n\n{sw.lore}")
        self.ed_xml.setPlainText(generate_special_weapon_xml(sw, elem.damage_def))

    def _export_png(self) -> None:
        if self._last_result is None:
            return
        sw = SPECIAL_WEAPONS[self._selected_idx]
        default_path = str(self.store.textures_root / sw.texture_rel_path)
        path, _ = QFileDialog.getSaveFileName(self, "Lưu PNG Vũ Khí Đặc Biệt", default_path, "PNG (*.png)")
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._last_result.image_rgba.save(path, "PNG")
            QMessageBox.information(self, "Đã xuất PNG", f"Đã lưu tại:\n{path}")

    def _export_xml_to_mod(self) -> None:
        sw = SPECIAL_WEAPONS[self._selected_idx]
        elem = self.store.get_element(self._override_elem_id if self._use_signature_vfx else 0)
        xml_txt = generate_special_weapon_xml(sw, elem.damage_def)
        out_xml = self.store.mod_root / "Defs" / "SpecialWeapons.xml"
        out_xml.parent.mkdir(parents=True, exist_ok=True)
        out_xml.write_text(xml_txt, encoding="utf-8")
        if self._last_result is not None and sw.texture_rel_path:
            tex_p = self.store.textures_root / sw.texture_rel_path
            tex_p.parent.mkdir(parents=True, exist_ok=True)
            self._last_result.image_rgba.save(tex_p, "PNG")
        QMessageBox.information(
            self,
            "Đã xuất Vũ Khí Đặc Biệt!",
            f"Đã xuất XML:\n{out_xml}\nvà texture PNG vào Textures/PersonalForge/{sw.texture_rel_path}",
        )
