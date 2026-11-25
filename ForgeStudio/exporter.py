"""
Mod Asset & C# Code Exporter / Importer for Overgeared (PersonalForge 1.7).

Supports:
1. Direct PNG texture installation into Textures/PersonalForge/Parts/ or Patterns/
   (both replacing built-in slots and adding new part indices >=6 / >=7).
2. Packing directly into expansion_atlas.png when replacing slots head_*_4..5,
   guard_5..6, grip_4..5, pommel_4..5.
3. Updating Languages/English/Keyed/PersonalForge.xml & ChineseSimplified cleanly.
4. Generating C# 1.7 code snippets / full patch file (WeaponDesign + ExpandedParts +
   WeaponArt extension) ready to import into PersonalForge C# source.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

from mod_data import (
    BUILTIN_GRIPS,
    BUILTIN_GUARDS,
    BUILTIN_HEADS,
    BUILTIN_POMMELS,
    CustomPartEntry,
    KINDS,
    ModAssetStore,
    WeaponDesignState,
)
from splitter import trim_and_pad


def save_part_to_mod(
    store: ModAssetStore,
    pil_img: Image.Image,
    category: str,
    kind: int,
    index: int,
    name: str,
    damage: float = 1.0,
    cooldown: float = 1.0,
    mass: float = 1.0,
    penetration: float = 0.0,
    work_mult: float = 1.0,
    cost: int = 10,
    socket_x: Optional[float] = None,
    tang_root: float = 0.08,
    pack_into_atlas_if_builtin: bool = True,
) -> Tuple[str, Path]:
    """
    Saves a cropped/prepared part image into Overgeared/Textures/PersonalForge/
    and updates ForgeStudio_CustomParts.json + Language XML.
    Returns (part_id, saved_path).
    """
    cleaned = trim_and_pad(pil_img, pad=2, target_max_dim=256)

    if category == "pattern":
        part_id = f"pattern_{index}"
        store.patterns_dir.mkdir(parents=True, exist_ok=True)
        # Patterns work best at 256x256
        pat_img = pil_img.convert("RGBA").resize((256, 256), Image.Resampling.LANCZOS)
        out_path = store.patterns_dir / f"{part_id}.png"
        pat_img.save(out_path, "PNG")
        entry = CustomPartEntry(
            part_id=part_id,
            category="pattern",
            kind=-1,
            index=index,
            name=name,
            texture_rel_path=f"Patterns/{part_id}.png",
        )
        store.custom_parts[part_id] = entry
        store.save_custom_registry()
        store.clear_temp_part(part_id)
        store.clear_caches()
        return part_id, out_path

    if category == "head":
        part_id = f"head_{kind}_{index}"
    elif category == "guard":
        part_id = f"master_guard_{kind}" if index == 3 else f"guard_{index}"
    elif category == "grip":
        part_id = f"grip_{index}"
    elif category == "pommel":
        part_id = f"master_pommel_{kind}" if index == 2 else f"pommel_{index}"
    else:
        raise ValueError(f"Unknown category: {category}")

    store.parts_dir.mkdir(parents=True, exist_ok=True)
    atlas_cell = store._atlas_cell(part_id)
    wrote_atlas = False

    if pack_into_atlas_if_builtin and atlas_cell >= 0 and (store.parts_dir / "expansion_atlas.png").exists():
        atlas_path = store.parts_dir / "expansion_atlas.png"
        with Image.open(atlas_path) as aim:
            atlas = aim.convert("RGBA")
        aw, ah = atlas.size
        cw, ch = aw // 4, ah // 4
        col = atlas_cell % 4
        row_td = atlas_cell // 4
        x0, y0 = col * cw, row_td * ch

        # Clear cell and fit cleaned part inside cw x ch
        blank = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        pw, ph = cleaned.size
        scale = min((cw - 8) / max(pw, 1), (ch - 8) / max(ph, 1), 1.0)
        if scale < 1.0:
            fitted = cleaned.resize((max(1, int(round(pw * scale))), max(1, int(round(ph * scale)))), Image.Resampling.LANCZOS)
        else:
            fitted = cleaned
        fx = (cw - fitted.width) // 2
        fy = (ch - fitted.height) // 2
        blank.paste(fitted, (fx, fy))
        atlas.paste(blank, (x0, y0))
        atlas.save(atlas_path, "PNG")
        out_path = atlas_path
        wrote_atlas = True
    else:
        out_path = store.parts_dir / f"{part_id}.png"
        cleaned.save(out_path, "PNG")

    entry = CustomPartEntry(
        part_id=part_id,
        category=category,
        kind=kind if category == "head" else -1,
        index=index,
        name=name,
        damage=damage,
        cooldown=cooldown,
        mass=mass,
        penetration=penetration,
        work_mult=work_mult,
        cost=cost,
        socket_x=socket_x,
        tang_root=tang_root,
        is_atlas_cell=wrote_atlas,
        atlas_cell=atlas_cell if wrote_atlas else -1,
        texture_rel_path=f"Parts/{out_path.name}",
    )
    store.custom_parts[part_id] = entry
    store.save_custom_registry()
    store.clear_temp_part(part_id)
    store.clear_caches()
    return part_id, out_path


def update_language_xml(store: ModAssetStore) -> List[Path]:
    """Updates Keyed/PersonalForge_Custom.xml in English & ChineseSimplified with custom part names."""
    if not store.custom_parts:
        return []
    written: List[Path] = []
    for lang in ("English", "ChineseSimplified"):
        keyed_dir = store.mod_root / "Languages" / lang / "Keyed"
        if not keyed_dir.exists():
            continue
        out_xml = keyed_dir / "PersonalForge_Custom.xml"
        root = ET.Element("LanguageData")
        for pid, entry in sorted(store.custom_parts.items()):
            el = ET.SubElement(root, f"PF_Custom_{pid}")
            el.text = entry.name
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(out_xml, encoding="utf-8", xml_declaration=True)
        written.append(out_xml)
    return written


def generate_csharp_code(store: ModAssetStore, design: Optional[WeaponDesignState] = None) -> str:
    """
    Generates ready-to-import C# 1.7 code for PersonalForge (RimWorld 1.7)
    covering:
    - Extended WeaponDesign part arrays & stat profiles
    - Direct texture loading override (no 4x4 atlas limit)
    - Optional current WeaponDesign preset initializer
    """
    heads_by_kind: List[List[Tuple[int, str, float, float, float, float, int]]] = [[], [], [], []]
    for k in range(4):
        for idx, pid, label in store.get_heads(k):
            e = store.custom_parts.get(pid)
            if e:
                heads_by_kind[k].append((idx, label, e.damage, e.cooldown, e.work_mult, e.mass, e.cost))
            elif idx < 6:
                from mod_data import HEAD_DAMAGE, HEAD_COOLDOWN, HEAD_WORK, HEAD_MASS, HEAD_COST
                heads_by_kind[k].append((idx, label, HEAD_DAMAGE[idx], HEAD_COOLDOWN[idx], HEAD_WORK[idx], HEAD_MASS[idx], HEAD_COST[idx]))

    guards = store.get_guards(0)
    grips = store.get_grips()
    pommels = store.get_pommels(0)

    lines: List[str] = []
    lines.append("// ============================================================================")
    lines.append("// PersonalForge 1.7 - Generated Custom Parts & Preset Code (Overgeared Studio)")
    lines.append("// Import file này vào project C# PersonalForge (RimWorld 1.7) hoặc copy các mảng.")
    lines.append("// ============================================================================")
    lines.append("using System.Collections.Generic;")
    lines.append("using UnityEngine;")
    lines.append("")
    lines.append("namespace PersonalForge")
    lines.append("{")
    lines.append("    public static class CustomPartsGenerated")
    lines.append("    {")
    lines.append("        // 1. Tên các Head theo từng loại vũ khí (0: Sword, 1: Axe, 2: Hammer, 3: Spear)")
    lines.append("        public static readonly string[][] HeadNames = new string[4][]")
    lines.append("        {")
    for k in range(4):
        names_str = ", ".join(f'"{lbl}"' for _, lbl, *_ in heads_by_kind[k])
        lines.append(f"            new string[] {{ {names_str} }}, // {KINDS[k]}")
    lines.append("        };")
    lines.append("")

    # Extra heads (> 5)
    extra_heads = [e for e in store.custom_parts.values() if e.category == "head" and e.index >= 6]
    extra_guards = [e for e in store.custom_parts.values() if e.category == "guard" and e.index >= 7]
    extra_grips = [e for e in store.custom_parts.values() if e.category == "grip" and e.index >= 6]
    extra_pommels = [e for e in store.custom_parts.values() if e.category == "pommel" and e.index >= 6]

    lines.append("        // 2. Danh sách Guards / Grips / Pommels")
    lines.append("        public static readonly string[] GuardNames = new string[] { " + ", ".join(f'"{lbl}"' for _, _, lbl in guards) + " };")
    lines.append("        public static readonly string[] GripNames = new string[] { " + ", ".join(f'"{lbl}"' for _, _, lbl in grips) + " };")
    lines.append("        public static readonly string[] PommelNames = new string[] { " + ", ".join(f'"{lbl}"' for _, _, lbl in pommels) + " };")
    lines.append("")

    lines.append("        // 3. Socket X cho các Head mới (head >= 6) dùng trong WeaponArt.Compose")
    lines.append("        public static readonly Dictionary<string, float> CustomHeadSockets = new Dictionary<string, float>")
    lines.append("        {")
    for e in store.custom_parts.values():
        if e.category == "head" and e.socket_x is not None:
            lines.append(f'            ["{e.part_id}"] = {e.socket_x:.4f}f,')
    lines.append("        };")
    lines.append("")

    if extra_guards or extra_grips or extra_pommels:
        lines.append("        // 4. ComponentProfile mở rộng cho Guard / Grip / Pommel mới")
        if extra_guards:
            lines.append("        // Thêm vào WeaponDesign.GuardProfiles:")
            for e in sorted(extra_guards, key=lambda x: x.index):
                lines.append(f"        // [{e.index}] {e.name}: new ComponentProfile({e.damage:.2f}f, {e.cooldown:.2f}f, {e.mass:.2f}f, {e.penetration:.3f}f),")
        if extra_grips:
            lines.append("        // Thêm vào WeaponDesign.GripProfiles:")
            for e in sorted(extra_grips, key=lambda x: x.index):
                lines.append(f"        // [{e.index}] {e.name}: new ComponentProfile({e.damage:.2f}f, {e.cooldown:.2f}f, {e.mass:.2f}f, {e.penetration:.3f}f),")
        if extra_pommels:
            lines.append("        // Thêm vào WeaponDesign.PommelProfiles:")
            for e in sorted(extra_pommels, key=lambda x: x.index):
                lines.append(f"        // [{e.index}] {e.name}: new ComponentProfile({e.damage:.2f}f, {e.cooldown:.2f}f, {e.mass:.2f}f, {e.penetration:.3f}f),")
        lines.append("")

    if extra_heads:
        lines.append("        // 5. Head Stats mở rộng cho head >= 6 (Damage, Cooldown, Work, Mass, Cost)")
        for e in sorted(extra_heads, key=lambda x: (x.kind, x.index)):
            lines.append(f'        // {e.part_id} ("{e.name}"): dmg={e.damage:.2f}f, cd={e.cooldown:.2f}f, work={e.work_mult:.2f}f, mass={e.mass:.2f}f, cost={e.cost}')
        lines.append("")

    if design is not None:
        lines.append("        // 6. Preset WeaponDesign đang test trong Forge Studio")
        lines.append("        public static WeaponDesign CreatePreset()")
        lines.append("        {")
        lines.append("            return new WeaponDesign")
        lines.append("            {")
        lines.append(f"                kind = {design.kind},")
        lines.append(f"                head = {design.head},")
        lines.append(f"                guard = {design.guard},")
        lines.append(f"                grip = {design.grip},")
        lines.append(f"                pommel = {design.pommel},")
        lines.append(f"                overallSize = {design.overall_size:.2f}f,")
        lines.append(f"                headSize = {design.head_size:.2f}f,")
        lines.append(f"                handleLength = {design.handle_length:.2f}f,")
        lines.append(f"                guardSize = {design.guard_size:.2f}f,")
        lines.append(f"                pommelSize = {design.pommel_size:.2f}f,")
        lines.append(f"                pattern = {design.pattern},")
        lines.append(f"                patternScale = {design.pattern_scale:.2f}f,")
        lines.append(f"                patternStrength = {design.pattern_strength:.2f}f,")
        lines.append(f"                patternRotation = {design.pattern_rotation},")
        lines.append(f"                patternParts = {design.pattern_parts},")
        lines.append(f"                patternLayout = {design.pattern_layout},")
        lines.append(f"                patternOffsetX = {design.pattern_offset_x:.2f}f,")
        lines.append(f"                patternOffsetY = {design.pattern_offset_y:.2f}f,")
        lines.append(f"                metalFinish = {design.metal_finish},")
        lines.append(f"                headTint = new Color({design.head_tint[0]:.3f}f, {design.head_tint[1]:.3f}f, {design.head_tint[2]:.3f}f),")
        lines.append(f"                guardTint = new Color({design.guard_tint[0]:.3f}f, {design.guard_tint[1]:.3f}f, {design.guard_tint[2]:.3f}f),")
        lines.append(f"                gripTint = new Color({design.grip_tint[0]:.3f}f, {design.grip_tint[1]:.3f}f, {design.grip_tint[2]:.3f}f),")
        lines.append(f"                linkPommelTint = {'true' if design.link_pommel_tint else 'false'},")
        lines.append(f"                pommelTint = new Color({design.pommel_tint[0]:.3f}f, {design.pommel_tint[1]:.3f}f, {design.pommel_tint[2]:.3f}f),")
        lines.append(f"                patternColor = new Color({design.pattern_color[0]:.3f}f, {design.pattern_color[1]:.3f}f, {design.pattern_color[2]:.3f}f),")
        lines.append(f"                craft = {design.craft},")
        lines.append(f"                enchantment = {design.enchantment},")
        lines.append(f'                name = "{design.name.replace(chr(34), "")}",')
        lines.append(f'                inscription = "{design.inscription.replace(chr(34), "")}",')
        lines.append("            };")
        lines.append("        }")

    lines.append("    }")
    lines.append("}")
    return "\n".join(lines)


def generate_xml_custom_defs(store: ModAssetStore) -> str:
    """Generates a clean XML manifest of custom parts for Overgeared."""
    root = ET.Element("OvergearedCustomParts")
    root.set("rimWorldVersion", "1.7")
    for pid, e in sorted(store.custom_parts.items()):
        el = ET.SubElement(root, "Part")
        el.set("id", pid)
        for k, v in {
            "category": e.category,
            "kind": str(e.kind),
            "index": str(e.index),
            "name": e.name,
            "texture": e.texture_rel_path,
            "damage": f"{e.damage:.3f}",
            "cooldown": f"{e.cooldown:.3f}",
            "mass": f"{e.mass:.3f}",
            "penetration": f"{e.penetration:.4f}",
            "workMult": f"{e.work_mult:.3f}",
            "cost": str(e.cost),
        }.items():
            sub = ET.SubElement(el, k)
            sub.text = v
        if e.socket_x is not None:
            sub = ET.SubElement(el, "socketX")
            sub.text = f"{e.socket_x:.4f}"
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)
