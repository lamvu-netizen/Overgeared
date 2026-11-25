"""
Data models, built-in RimWorld 1.7 / Personal Forge constants, texture loaders,
and custom-part persistence for Overgeared Forge Studio.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image


# Weapon kinds
KINDS = ["Sword", "Axe", "Hammer", "Spear"]
KINDS_VI = ["Kiếm (Sword)", "Rìu (Axe)", "Búa (Hammer)", "Giáo (Spear)"]

PART_CATEGORIES = ["head", "guard", "grip", "pommel"]
PART_CATEGORY_LABELS = ["Lưỡi / Đầu (Head)", "Chắn tay (Guard)", "Cán (Grip)", "Chuôi (Pommel)"]

# Built-in names (matching PersonalForge English localization)
BUILTIN_HEADS: List[List[str]] = [
    ["Narrow blade", "Broad blade", "Heavy blade", "Flameblade", "Curved blade", "Cleaver blade"],
    ["Hatchet", "Broad axe", "Double axe", "Raven beak", "Bearded axe", "Crescent axe"],
    ["Square hammer", "Heavy hammer", "Flanged hammer", "Armor pick", "Hex hammer", "Morning star"],
    ["Pointed spear", "Leaf spear", "Winged spear", "Master's spear", "Hooked spear", "Trident"],
]

BUILTIN_GUARDS: List[str] = [
    "Crossguard", "Curved guard", "Metal collar", "Master's guard",
    "Double rings", "Winged guard", "Crescent guard",
]

BUILTIN_GRIPS: List[str] = [
    "Leather wrap", "Wooden grip", "Cloth wrap", "Braided grip",
    "Riveted grip", "Spiral grip",
]

BUILTIN_POMMELS: List[str] = [
    "Round pommel", "Faceted pommel", "Master's pommel", "Ring pommel",
    "Hex pommel", "Pointed pommel",
]

PATTERNS: List[str] = ["Plain", "Fluting", "Diamonds", "Scrollwork", "Geometric"]
PATTERN_PARTS: List[str] = ["Blade", "Guard", "Pommel", "Grip"]
PATTERN_LAYOUTS: List[str] = ["All over", "Center motif", "Edge bands"]
METAL_FINISHES: List[str] = ["Natural", "Matte polish", "Blackened", "Antique bronze"]
FINISH_DESCRIPTIONS: List[str] = [
    "Retain the original shading of the materials and parts.",
    "Soften metallic highlights for a matte finish.",
    "Darken metal surfaces while preserving their structure and outline.",
    "Apply a warm, aged bronze tone.",
]
CRAFTS: List[str] = ["Balanced forging", "Light forging", "Forward balance", "Precision quench"]
CRAFT_DESCRIPTIONS: List[str] = [
    "No extra modifiers",
    "Interval -14% · Mass -15% · Damage -10% · Work +20% · Crafting 8",
    "Damage +18% · Interval +18% · Mass +12% · Blade material +6 · Work +20% · Crafting 8",
    "Damage +4% · Armor penetration +4 pp · Plasteel +8 · Work +40% · Crafting 10",
]

ENCHANTMENTS: List[str] = ["None", "Flame", "Frost", "Thunder", "Venom", "Concussion", "Siphon"]
ENCHANTMENT_DESCRIPTIONS: List[str] = [
    "No elemental damage",
    "On hit: +4 fire damage",
    "On hit: +3 frost damage · Slow 15% for 2s",
    "On hit: +3 shock damage; +5 vs. mechanoids",
    "Hit: +2 venom; 1/s for 3s",
    "Hit: +2 blunt; 0.5s stun (4s CD)",
    "Hit: +2 cut; heals up to 1 HP (4s CD)",
]

COLOR_PRESETS: List[Tuple[str, Tuple[float, float, float]]] = [
    ("Natural", (1.0, 1.0, 1.0)),
    ("Cold iron", (0.72, 0.79, 0.84)),
    ("Brass", (0.85, 0.68, 0.38)),
    ("Copper", (0.84, 0.49, 0.32)),
    ("Blue steel", (0.42, 0.6, 0.78)),
    ("Ink", (0.3, 0.31, 0.32)),
    ("Crimson", (0.78, 0.25, 0.26)),
    ("Pine", (0.36, 0.61, 0.39)),
    ("Amethyst", (0.63, 0.43, 0.8)),
    ("Ivory", (0.94, 0.88, 0.7)),
    ("Teal", (0.31, 0.76, 0.72)),
    ("Leather", (0.53, 0.36, 0.24)),
]


@dataclass
class MaterialInfo:
    def_name: str
    label: str
    color: Tuple[float, float, float]  # RimWorld stuffProps.color (0..1)
    sharp_damage_mult: float = 1.0
    blunt_damage_mult: float = 1.0
    cooldown_mult: float = 1.0
    density: float = 1.0
    market_value: float = 1.9


# RimWorld 1.7 standard metals & grip materials
METALS: List[MaterialInfo] = [
    MaterialInfo("Steel", "Steel", (1.0, 1.0, 1.0), 1.0, 1.0, 1.0, 1.0, 1.9),
    MaterialInfo("Silver", "Silver", (0.78, 0.80, 0.84), 0.9, 0.9, 1.0, 1.3, 1.0),
    MaterialInfo("Gold", "Gold", (0.98, 0.82, 0.28), 0.75, 0.9, 1.15, 1.8, 10.0),
    MaterialInfo("Uranium", "Uranium", (0.39, 0.45, 0.43), 1.15, 1.30, 1.15, 1.6, 6.0),
    MaterialInfo("Plasteel", "Plasteel", (0.63, 0.70, 0.72), 1.15, 1.0, 0.80, 0.75, 9.0),
    MaterialInfo("Bioferrite", "Bioferrite", (0.43, 0.35, 0.36), 1.25, 1.1, 0.92, 0.95, 7.0),
]

GRIP_MATERIALS: List[MaterialInfo] = [
    MaterialInfo("WoodLog", "Wood", (1.0, 1.0, 1.0), 1.0, 1.0, 1.0, 1.0, 1.2),
    MaterialInfo("Cloth", "Cloth", (0.76, 0.76, 0.76), 1.0, 1.0, 1.0, 0.65, 1.5),
    MaterialInfo("Leather_Plain", "Plainleather", (0.58, 0.40, 0.25), 1.0, 1.0, 1.0, 0.85, 2.1),
    MaterialInfo("DevilstrandCloth", "Devilstrand", (0.70, 0.22, 0.22), 1.0, 1.0, 1.0, 0.65, 5.5),
    MaterialInfo("Synthread", "Synthread", (0.47, 0.68, 0.82), 1.0, 1.0, 1.0, 0.65, 4.0),
    MaterialInfo("Hyperweave", "Hyperweave", (0.20, 0.45, 0.68), 1.0, 1.0, 1.0, 0.65, 9.0),
    MaterialInfo("Leather_Thrumbo", "Thrumbofur", (0.92, 0.92, 0.90), 1.0, 1.0, 1.0, 0.85, 14.0),
]


@dataclass
class ComponentStats:
    damage: float = 1.0
    cooldown: float = 1.0
    mass: float = 1.0
    penetration: float = 0.0
    cost: int = 10
    work_mult: float = 1.0


GUARD_PROFILES = [
    ComponentStats(1.0, 1.0, 1.0, 0.0, 10),
    ComponentStats(0.98, 0.97, 1.02, 0.0, 10),
    ComponentStats(0.95, 0.96, 0.92, 0.0, 10),
    ComponentStats(1.0, 0.96, 1.0, 0.02, 14),
    ComponentStats(1.0, 1.02, 1.07, 0.01, 10),
    ComponentStats(1.04, 1.04, 1.05, 0.0, 10),
    ComponentStats(0.98, 0.99, 1.02, 0.015, 10),
]

GRIP_PROFILES = [
    ComponentStats(1.0, 1.0, 1.0, 0.0, 8),
    ComponentStats(1.04, 1.05, 0.97, 0.0, 8),
    ComponentStats(0.96, 0.96, 0.94, 0.0, 8),
    ComponentStats(0.99, 0.98, 1.02, 0.0, 8),
    ComponentStats(1.05, 1.04, 1.06, 0.0, 8),
    ComponentStats(1.0, 1.03, 1.03, 0.01, 8),
]

POMMEL_PROFILES = [
    ComponentStats(1.0, 1.0, 1.0, 0.0, 4),
    ComponentStats(1.03, 1.03, 1.04, 0.0, 6),
    ComponentStats(1.1, 0.97, 1.05, 0.0, 8),
    ComponentStats(0.97, 0.97, 0.94, 0.0, 5),
    ComponentStats(1.02, 1.01, 1.05, 0.0, 4),
    ComponentStats(0.99, 1.02, 0.98, 0.015, 4),
]

HEAD_DAMAGE = [0.88, 1.0, 1.18, 1.0, 0.96, 1.12]
HEAD_COOLDOWN = [0.85, 1.0, 1.2, 1.0, 0.94, 1.14]
HEAD_WORK = [0.85, 1.0, 1.2, 1.1, 1.05, 1.18]
HEAD_MASS = [0.8, 1.0, 1.25, 1.15, 0.92, 1.2]
HEAD_COST = [28, 38, 48, 48, 36, 46]

MASTER_DAMAGE = [1.14, 1.2, 1.2, 1.1]
MASTER_COOLDOWN = [0.88, 1.08, 1.12, 0.9]
HEAD_PENETRATION = [0.035, 0.0, 0.12, 0.08]

BASE_WEAPON_DAMAGE = [18.0, 23.0, 21.0, 20.0]
BASE_WEAPON_COOLDOWN = [2.6, 3.1, 3.0, 2.8]
BASE_WORK = [6000.0, 5800.0, 6200.0, 6500.0]
BASE_MASS = [1.35, 1.8, 2.1, 1.7]

CRAFT_DAMAGE = [1.0, 0.9, 1.18, 1.04]
CRAFT_COOLDOWN = [1.0, 0.86, 1.18, 1.0]
CRAFT_WORK = [1.0, 1.2, 1.2, 1.4]
CRAFT_MASS = [1.0, 0.85, 1.12, 1.0]
CRAFT_SKILLS = [4, 8, 8, 10]


@dataclass
class CustomPartEntry:
    """User-added or overridden part entry."""
    part_id: str          # e.g. "head_0_6", "guard_7", "grip_6", "pommel_6"
    category: str         # "head", "guard", "grip", "pommel", "pattern"
    kind: int             # 0..3 for head, -1 for shared
    index: int            # slot index
    name: str             # display name
    damage: float = 1.0
    cooldown: float = 1.0
    mass: float = 1.0
    penetration: float = 0.0
    work_mult: float = 1.0
    cost: int = 10
    socket_x: Optional[float] = None  # override head socket X (0..1) if desired
    tang_root: float = 0.08           # sword tang root fraction
    is_atlas_cell: bool = False
    atlas_cell: int = -1
    texture_rel_path: str = ""        # relative to Textures/PersonalForge/


@dataclass
class WeaponDesignState:
    kind: int = 0
    head: int = 1
    guard: int = 0
    grip: int = 1
    pommel: int = 0
    overall_size: float = 1.0
    head_size: float = 1.0
    handle_length: float = 1.0
    guard_size: float = 1.0
    pommel_size: float = 1.0
    pattern: int = 0
    pattern_scale: float = 1.0
    pattern_strength: float = 0.6
    pattern_rotation: int = 0
    pattern_color: Tuple[float, float, float] = (0.24, 0.22, 0.19)
    pattern_parts: int = 1      # bitmask: 1=Blade, 2=Guard, 4=Pommel, 8=Grip
    pattern_layout: int = 0     # 0=All over, 1=Center, 2=Edge
    pattern_offset_x: float = 0.0
    pattern_offset_y: float = 0.0
    metal_finish: int = 0       # 0=Natural, 1=Matte, 2=Blackened, 3=Antique bronze
    head_tint: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    guard_tint: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    grip_tint: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    link_pommel_tint: bool = True
    pommel_tint: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    craft: int = 0
    enchantment: int = 0
    head_material_idx: int = 0  # Steel
    guard_material_idx: int = 0 # Steel
    grip_material_idx: int = 0  # WoodLog
    name: str = ""
    inscription: str = ""
    story: str = ""

    @property
    def effective_pommel_tint(self) -> Tuple[float, float, float]:
        return self.guard_tint if self.link_pommel_tint else self.pommel_tint

    def has_pattern_on(self, part_bit_index: int) -> bool:
        return self.pattern != 0 and (self.pattern_parts & (1 << part_bit_index)) != 0


class ModAssetStore:
    """Manages loading, caching, and saving textures & custom parts for Overgeared (1.7)."""

    def __init__(self, mod_root: str | Path):
        self.mod_root = Path(mod_root)
        self.textures_root = self.mod_root / "Textures" / "PersonalForge"
        self.parts_dir = self.textures_root / "Parts"
        self.patterns_dir = self.textures_root / "Patterns"
        self.effects_dir = self.textures_root / "Effects"
        self.registry_path = self.mod_root / "ForgeStudio_CustomParts.json"

        # Cache of bottom-up float32 RGBA arrays [H, W, 4] (0..1)
        self._part_cache: Dict[str, np.ndarray] = {}
        self._head_socket_cache: Dict[str, float] = {}
        self._center_socket_cache: Dict[str, Tuple[float, float, float]] = {}
        self._pattern_sums_cache: Dict[int, np.ndarray] = {}
        self._atlas_arr: Optional[np.ndarray] = None
        self._sparkle_pil: Optional[Image.Image] = None

        # Temporary in-memory override textures from Splitter ("Test ngay trong Lò Rèn")
        self.temp_textures: Dict[str, np.ndarray] = {}
        self.custom_parts: Dict[str, CustomPartEntry] = {}

        self.load_custom_registry()

    def set_mod_root(self, new_root: str | Path) -> None:
        self.mod_root = Path(new_root)
        self.textures_root = self.mod_root / "Textures" / "PersonalForge"
        self.parts_dir = self.textures_root / "Parts"
        self.patterns_dir = self.textures_root / "Patterns"
        self.effects_dir = self.textures_root / "Effects"
        self.registry_path = self.mod_root / "ForgeStudio_CustomParts.json"
        self.clear_caches()
        self.load_custom_registry()

    def clear_caches(self) -> None:
        self._part_cache.clear()
        self._head_socket_cache.clear()
        self._center_socket_cache.clear()
        self._pattern_sums_cache.clear()
        self._atlas_arr = None
        self._sparkle_pil = None

    def load_custom_registry(self) -> None:
        self.custom_parts.clear()
        if self.registry_path.exists():
            try:
                raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
                for item in raw.get("parts", []):
                    entry = CustomPartEntry(**item)
                    self.custom_parts[entry.part_id] = entry
            except Exception:
                pass

    def save_custom_registry(self) -> None:
        data = {
            "version": "1.7",
            "parts": [asdict(v) for v in self.custom_parts.values()],
        }
        self.registry_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- Lists of available parts (built-in + custom) ----
    def get_heads(self, kind: int) -> List[Tuple[int, str, str]]:
        """Returns list of (index, part_id, display_name)."""
        items: List[Tuple[int, str, str]] = []
        base_names = BUILTIN_HEADS[kind]
        max_idx = len(base_names) - 1
        for entry in self.custom_parts.values():
            if entry.category == "head" and entry.kind == kind:
                max_idx = max(max_idx, entry.index)
        for i in range(max_idx + 1):
            pid = f"head_{kind}_{i}"
            if pid in self.custom_parts:
                items.append((i, pid, self.custom_parts[pid].name))
            elif i < len(base_names):
                items.append((i, pid, base_names[i]))
            else:
                p = self.parts_dir / f"{pid}.png"
                if p.exists() or pid in self.temp_textures:
                    items.append((i, pid, f"Custom Head #{i}"))
        return items

    def get_guards(self, kind: int) -> List[Tuple[int, str, str]]:
        items: List[Tuple[int, str, str]] = []
        max_idx = len(BUILTIN_GUARDS) - 1
        for entry in self.custom_parts.values():
            if entry.category == "guard":
                max_idx = max(max_idx, entry.index)
        for i in range(max_idx + 1):
            pid = f"master_guard_{kind}" if i == 3 else f"guard_{i}"
            if pid in self.custom_parts:
                items.append((i, pid, self.custom_parts[pid].name))
            elif i < len(BUILTIN_GUARDS):
                items.append((i, pid, BUILTIN_GUARDS[i]))
            else:
                p = self.parts_dir / f"{pid}.png"
                if p.exists() or pid in self.temp_textures:
                    items.append((i, pid, f"Custom Guard #{i}"))
        return items

    def get_grips(self) -> List[Tuple[int, str, str]]:
        items: List[Tuple[int, str, str]] = []
        max_idx = len(BUILTIN_GRIPS) - 1
        for entry in self.custom_parts.values():
            if entry.category == "grip":
                max_idx = max(max_idx, entry.index)
        for i in range(max_idx + 1):
            pid = f"grip_{i}"
            if pid in self.custom_parts:
                items.append((i, pid, self.custom_parts[pid].name))
            elif i < len(BUILTIN_GRIPS):
                items.append((i, pid, BUILTIN_GRIPS[i]))
            else:
                p = self.parts_dir / f"{pid}.png"
                if p.exists() or pid in self.temp_textures:
                    items.append((i, pid, f"Custom Grip #{i}"))
        return items

    def get_pommels(self, kind: int) -> List[Tuple[int, str, str]]:
        items: List[Tuple[int, str, str]] = []
        max_idx = len(BUILTIN_POMMELS) - 1
        for entry in self.custom_parts.values():
            if entry.category == "pommel":
                max_idx = max(max_idx, entry.index)
        for i in range(max_idx + 1):
            pid = f"master_pommel_{kind}" if i == 2 else f"pommel_{i}"
            if pid in self.custom_parts:
                items.append((i, pid, self.custom_parts[pid].name))
            elif i < len(BUILTIN_POMMELS):
                items.append((i, pid, BUILTIN_POMMELS[i]))
            else:
                p = self.parts_dir / f"{pid}.png"
                if p.exists() or pid in self.temp_textures:
                    items.append((i, pid, f"Custom Pommel #{i}"))
        return items

    def get_patterns(self) -> List[Tuple[int, str]]:
        items = [(i, name) for i, name in enumerate(PATTERNS)]
        for i in range(len(PATTERNS), 32):
            pid = f"pattern_{i}"
            if pid in self.custom_parts or (self.patterns_dir / f"{pid}.png").exists() or pid in self.temp_textures:
                label = self.custom_parts[pid].name if pid in self.custom_parts else f"Custom Pattern #{i}"
                items.append((i, label))
        return items

    def next_free_index(self, category: str, kind: int = 0) -> int:
        if category == "head":
            existing = {idx for idx, _, _ in self.get_heads(kind)}
        elif category == "guard":
            existing = {idx for idx, _, _ in self.get_guards(kind)}
        elif category == "grip":
            existing = {idx for idx, _, _ in self.get_grips()}
        elif category == "pommel":
            existing = {idx for idx, _, _ in self.get_pommels(kind)}
        elif category == "pattern":
            existing = {idx for idx, _ in self.get_patterns()}
        else:
            existing = set()
        idx = 0
        while idx in existing:
            idx += 1
        return idx

    # ---- Image loading helpers ----
    @staticmethod
    def _pil_to_bottomup_f32(img: Image.Image) -> np.ndarray:
        rgba = img.convert("RGBA")
        arr = np.asarray(rgba, dtype=np.float32) / 255.0
        return np.ascontiguousarray(np.flipud(arr))

    @staticmethod
    def _atlas_cell(name: str) -> int:
        parts = name.split("_")
        if len(parts) == 3 and parts[0] == "head":
            try:
                k, h = int(parts[1]), int(parts[2])
                if 0 <= k <= 3 and 4 <= h <= 5:
                    return k * 2 + h - 4
            except ValueError:
                pass
        return {
            "guard_5": 8,
            "guard_6": 9,
            "grip_4": 10,
            "grip_5": 11,
            "pommel_4": 12,
            "pommel_5": 13,
        }.get(name, -1)

    def _load_atlas(self) -> Optional[np.ndarray]:
        if self._atlas_arr is not None:
            return self._atlas_arr
        p = self.parts_dir / "expansion_atlas.png"
        if not p.exists():
            return None
        with Image.open(p) as im:
            self._atlas_arr = self._pil_to_bottomup_f32(im)
        return self._atlas_arr

    def set_temp_part(self, name: str, pil_img: Image.Image, socket_x: Optional[float] = None) -> None:
        """Sets an in-memory preview part (top-down PIL RGBA) so Forge preview updates instantly."""
        arr = self._pil_to_bottomup_f32(pil_img)
        self.temp_textures[name] = arr
        self._part_cache.pop(name, None)
        self._center_socket_cache.pop(name, None)
        self._head_socket_cache.pop(name, None)
        if socket_x is not None:
            self._head_socket_cache[name] = float(socket_x)

    def clear_temp_part(self, name: str) -> None:
        self.temp_textures.pop(name, None)
        self._part_cache.pop(name, None)
        self._center_socket_cache.pop(name, None)
        self._head_socket_cache.pop(name, None)

    def get_part(self, name: str) -> Optional[np.ndarray]:
        """Returns bottom-up float32 RGBA [H, W, 4] matching WeaponArt.Part(name)."""
        if name in self.temp_textures:
            return self.temp_textures[name]
        if name in self._part_cache:
            return self._part_cache[name]

        # 1. Check standalone PNG first if user placed custom/override file
        standalone = self.parts_dir / f"{name}.png"
        cell = self._atlas_cell(name)

        # If it's an atlas cell AND no custom override file exists, slice from expansion_atlas
        # Wait: if user replaced an atlas cell via expansion_atlas, load from atlas;
        # if standalone file exists for a non-atlas part (or custom part >=6), load standalone.
        if cell >= 0 and not (name in self.custom_parts and not self.custom_parts[name].is_atlas_cell and standalone.exists()):
            atlas = self._load_atlas()
            if atlas is not None:
                ah, aw, _ = atlas.shape
                cw = aw // 4
                ch = ah // 4
                col = cell % 4
                row_bottom_up = 3 - (cell // 4)
                x0 = col * cw
                y0 = row_bottom_up * ch
                cell_arr = atlas[y0:y0 + ch, x0:x0 + cw]
                mask = cell_arr[:, :, 3] > (32.0 / 255.0)
                if np.any(mask):
                    ys, xs = np.where(mask)
                    min_y, max_y = int(ys.min()), int(ys.max())
                    min_x, max_x = int(xs.min()), int(xs.max())
                    out_h = max_y - min_y + 5
                    out_w = max_x - min_x + 5
                    out = np.zeros((out_h, out_w, 4), dtype=np.float32)
                    out[2:2 + (max_y - min_y + 1), 2:2 + (max_x - min_x + 1)] = cell_arr[min_y:max_y + 1, min_x:max_x + 1]
                    self._part_cache[name] = out
                    # Compute HeadSocket as in ExpandedParts.cs
                    scan_y = max(2, min(out_h - 3, round(out_h * 0.045)))
                    row_alpha = out[scan_y, :, 3] > (128.0 / 255.0)
                    opaque_xs = np.where(row_alpha)[0]
                    if len(opaque_xs) > 0:
                        sock = float(np.mean(opaque_xs + 0.5) / out_w)
                    else:
                        sock = 0.5
                    self._head_socket_cache[name] = sock
                    return out

        if standalone.exists():
            with Image.open(standalone) as im:
                arr = self._pil_to_bottomup_f32(im)
            self._part_cache[name] = arr
            return arr

        return None

    def get_part_pil(self, name: str) -> Optional[Image.Image]:
        arr = self.get_part(name)
        if arr is None:
            return None
        top_down = np.flipud(np.clip(arr * 255.0, 0, 255).astype(np.uint8))
        return Image.fromarray(top_down, "RGBA")

    def get_head_socket(self, kind: int, head: int) -> float:
        name = f"head_{kind}_{head}"
        if name in self.custom_parts and self.custom_parts[name].socket_x is not None:
            return float(self.custom_parts[name].socket_x)
        if name in self._head_socket_cache:
            return self._head_socket_cache[name]
        arr = self.get_part(name)
        if name in self._head_socket_cache:
            return self._head_socket_cache[name]
        if arr is not None and head >= 4:
            h, w, _ = arr.shape
            scan_y = max(2, min(h - 3, round(h * 0.045)))
            opaque_xs = np.where(arr[scan_y, :, 3] > (128.0 / 255.0))[0]
            sock = float(np.mean(opaque_xs + 0.5) / w) if len(opaque_xs) > 0 else 0.5
            self._head_socket_cache[name] = sock
            return sock
        if kind == 1 and head < 4:
            return [0.85, 0.88, 0.51, 0.6][head]
        if kind == 2 and head == 3:
            return 0.45
        return 0.5

    def get_center_socket(self, name: str) -> Tuple[float, float, float]:
        """Exact port of WeaponJoints.CenterSocket(Texture2D)."""
        if name in self._center_socket_cache:
            return self._center_socket_cache[name]
        arr = self.get_part(name)
        if arr is None:
            return (0.0, 1.0, 1.0)
        h, w, _ = arr.shape
        cx = w // 2
        col = arr[:, cx, 3] > (160.0 / 255.0)
        ys = np.where(col)[0]
        if len(ys) == 0:
            res = (0.0, 1.0, 1.0)
            self._center_socket_cache[name] = res
            return res
        min_y, max_y = int(ys[0]), int(ys[-1])
        sample_y = round(min_y + (max_y - min_y) * 0.84)
        sample_y = max(0, min(h - 1, sample_y))
        left = cx
        right = cx
        while left > 0 and arr[sample_y, left - 1, 3] > (160.0 / 255.0):
            left -= 1
        while right < w - 1 and arr[sample_y, right + 1, 3] > (160.0 / 255.0):
            right += 1
        res = (float(min_y) / h, float(max_y + 1) / h, float(right - left + 1) / w)
        self._center_socket_cache[name] = res
        return res

    def get_pattern_sums(self, index: int) -> Optional[np.ndarray]:
        """Exact 257x257 integral image from WeaponArt.PatternArea(index)."""
        if index == 0:
            return None
        if index in self._pattern_sums_cache:
            return self._pattern_sums_cache[index]
        temp_key = f"pattern_{index}"
        if temp_key in self.temp_textures:
            arr = self.temp_textures[temp_key]
            # Convert back to uint8 256x256
            h, w, _ = arr.shape
            r_chan = np.clip(arr[:, :, 0] * 255.0, 0, 255).astype(np.int32)
            ys = (np.arange(256) * h) // 256
            xs = (np.arange(256) * w) // 256
            sampled = r_chan[np.ix_(ys, xs)]
        else:
            p = self.patterns_dir / f"pattern_{index}.png"
            if not p.exists():
                return None
            with Image.open(p) as im:
                rgba = im.convert("RGBA")
                raw = np.flipud(np.asarray(rgba, dtype=np.int32))
            h, w, _ = raw.shape
            ys = (np.arange(256) * h) // 256
            xs = (np.arange(256) * w) // 256
            sampled = raw[np.ix_(ys, xs)][:, :, 0]

        sums = np.zeros((257, 257), dtype=np.int64)
        sums[1:, 1:] = np.cumsum(np.cumsum(sampled, axis=1), axis=0)
        self._pattern_sums_cache[index] = sums
        return sums

    def get_sparkle_pil(self) -> Optional[Image.Image]:
        if self._sparkle_pil is None:
            p = self.effects_dir / "Sparkle.png"
            if p.exists():
                self._sparkle_pil = Image.open(p).convert("RGBA")
        return self._sparkle_pil

    # ---- Stats calculation matching WeaponDesign.cs + Dialog_Forge.cs ----
    def compute_stats(self, design: WeaponDesignState) -> dict:
        kind = design.kind
        head = design.head
        guard = design.guard
        grip = design.grip
        pommel = design.pommel

        head_mat = METALS[max(0, min(len(METALS) - 1, design.head_material_idx))]
        guard_mat = METALS[max(0, min(len(METALS) - 1, design.guard_material_idx))]
        grip_mat = GRIP_MATERIALS[max(0, min(len(GRIP_MATERIALS) - 1, design.grip_material_idx))]

        gp = GUARD_PROFILES[guard] if guard < len(GUARD_PROFILES) else self._custom_stats(f"guard_{guard}")
        grp = GRIP_PROFILES[grip] if grip < len(GRIP_PROFILES) else self._custom_stats(f"grip_{grip}")
        pp = POMMEL_PROFILES[pommel] if pommel < len(POMMEL_PROFILES) else self._custom_stats(f"pommel_{pommel}")

        comp_dmg = gp.damage * grp.damage * pp.damage
        comp_cd = gp.cooldown * grp.cooldown * pp.cooldown
        comp_mass = gp.mass * grp.mass * pp.mass
        comp_pen = gp.penetration + grp.penetration + pp.penetration

        if head == 3:
            h_dmg = MASTER_DAMAGE[kind]
            h_cd = MASTER_COOLDOWN[kind]
            h_work = HEAD_WORK[3]
            h_mass = HEAD_MASS[3]
            h_cost = HEAD_COST[3]
        elif head < len(HEAD_DAMAGE):
            h_dmg = HEAD_DAMAGE[head]
            h_cd = HEAD_COOLDOWN[head]
            h_work = HEAD_WORK[head]
            h_mass = HEAD_MASS[head]
            h_cost = HEAD_COST[head]
        else:
            hc = self._custom_stats(f"head_{kind}_{head}")
            h_dmg, h_cd, h_work, h_mass, h_cost = hc.damage, hc.cooldown, hc.work_mult, hc.mass, hc.cost

        dmg_factor = h_dmg * comp_dmg * CRAFT_DAMAGE[design.craft]
        cd_factor = h_cd * comp_cd * CRAFT_COOLDOWN[design.craft]

        mat_dmg = head_mat.blunt_damage_mult if kind == 2 else head_mat.sharp_damage_mult
        mat_cd = head_mat.cooldown_mult

        damage = BASE_WEAPON_DAMAGE[kind] * dmg_factor * mat_dmg
        cooldown = BASE_WEAPON_COOLDOWN[kind] * cd_factor * mat_cd
        dps = damage / max(cooldown, 0.01)

        bonus_ap = (HEAD_PENETRATION[kind] if head == 3 else 0.0) + (0.04 if design.craft == 3 else 0.0) + comp_pen
        armor_pen = damage * 0.015 + bonus_ap

        mat_mass = 0.75 * head_mat.density + 0.15 * guard_mat.density + 0.10 * grip_mat.density
        mass = BASE_MASS[kind] * h_mass * mat_mass * CRAFT_MASS[design.craft] * comp_mass

        adv_parts = (1 if head == 3 else 0) + (1 if guard == 3 else 0) + (1 if pommel == 2 else 0)
        work = BASE_WORK[kind] * h_work * (1.0 + 0.55 * adv_parts) * CRAFT_WORK[design.craft] + (4500.0 if design.enchantment > 0 else 0.0)
        req_skill = max(10 if design.enchantment > 0 else 0, max(12 if adv_parts > 0 else 4, CRAFT_SKILLS[design.craft]))

        # Ingredients
        ingredients: Dict[str, int] = {}
        def add_ing(label: str, amt: int):
            ingredients[label] = ingredients.get(label, 0) + amt

        add_ing(head_mat.label, h_cost + (8 if kind == 2 else 0))
        add_ing(guard_mat.label, gp.cost + pp.cost)
        add_ing(grip_mat.label, 16 if kind == 3 else 8)
        if design.craft == 2:
            add_ing(head_mat.label, 6)
        if design.craft == 3:
            add_ing("Plasteel", 8)
        if design.enchantment > 0:
            add_ing("Gold", 6)
            ench_map = {
                1: ("Chemfuel", 20),
                2: ("Jade", 12),
                3: ("Component", 2),
                4: ("Herbal med", 12),
                5: ("Uranium", 10),
                6: ("Medicine", 6),
            }
            el, ea = ench_map[design.enchantment]
            add_ing(el, ea)
        if adv_parts > 0:
            add_ing("Plasteel", 12 * adv_parts)
            add_ing("Gold", 4 * adv_parts)

        ench_dmg = 0 if design.enchantment == 0 else (4 if design.enchantment == 1 else (2 if design.enchantment >= 4 else 3))

        return {
            "damage": damage,
            "cooldown": cooldown,
            "dps": dps,
            "armor_pen": armor_pen,
            "mass": mass,
            "work": work,
            "req_skill": req_skill,
            "ench_damage": ench_dmg,
            "ingredients": ingredients,
            "base_mat_damage": BASE_WEAPON_DAMAGE[kind] * mat_dmg,
            "base_mat_cooldown": BASE_WEAPON_COOLDOWN[kind] * mat_cd,
        }

    def _custom_stats(self, part_id: str) -> ComponentStats:
        e = self.custom_parts.get(part_id)
        if e is None:
            return ComponentStats()
        return ComponentStats(e.damage, e.cooldown, e.mass, e.penetration, e.cost, e.work_mult)
