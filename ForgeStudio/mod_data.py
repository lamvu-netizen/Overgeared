"""
Data models, built-in RimWorld 1.7 / Personal Forge constants, elemental sockets,
texture loaders, and custom-part / custom-element persistence for Overgeared Forge Studio.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image


# Weapon kinds
KINDS = ["Sword", "Axe", "Hammer", "Spear"]
KINDS_VI = ["Kiếm (Sword)", "Rìu (Axe)", "Búa (Hammer)", "Giáo (Giáo / Spear)"]

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

VFX_STYLES: List[Tuple[str, str]] = [
    ("abyssal_miasma", "U Minh Tử Khí (Abyssal Miasma)"),
    ("shadow_strife", "Shadow Strife (Bạch Viêm Hắc Vụ · Chỉ Kiếm)"),
    ("eternal_alpha", "Eternal Alpha (Thần Quang Hoàng Kim · Chỉ Kiếm)"),
    ("nova_burn", "Nova Burn (Siêu Tân Tinh Tím · Chỉ Kiếm)"),
    ("azure_jet", "Thanh Diêm Kiếm (Blue Flame Jet)"),
    ("ember_tendrils", "U Hỏa Tàn Tro (Ember Crackle)"),
    ("sonic_slash", "Bạch Trảm Sóng Âm (Sonic Ripples)"),
    ("ice_armor", "Băng Giáp Tinh Thể (Ice Chevron Armor)"),
    ("plasma_web", "Huyền Lôi Mạng (Voronoi Plasma)"),
    ("water_sheath", "Thủy Lưu Bọt Biển (Water Sheath)"),
    ("eclipse_flare", "Nhật Thực Hắc Tâm (Eclipse Lance)"),
    ("flame", "Hỏa Long Xoắn 3D (Fire Swirl)"),
    ("thunder", "Sấm Sét Phân Nhánh (Fractal Lightning)"),
    ("slashes", "Vệt Chém Trăng Khuyết (Crescent Slash)"),
]


@dataclass
class VfxLayerSpec:
    """Modular, no-code VFX layer (procedural or imported image) for custom elements."""
    layer_type: str = "image_overlay"  # ribbon, lightning, particles, rings, rays, image_overlay, image_particles
    primary_rgb: Tuple[int, int, int] = (255, 130, 45)
    secondary_rgb: Tuple[int, int, int] = (255, 240, 190)
    scale: float = 1.0
    speed: float = 1.0
    opacity: float = 1.0
    count: int = 10
    direction: str = "pulse"           # pulse, flow_up, spin, wrap, up, down, orbit, inward
    shape: str = "ember"               # ember, crystal, petal, star, bubble, orb
    image_rel_path: str = ""           # relative to Textures/PersonalForge/
    keep_image_colors: bool = True
    behind_weapon: bool = False
    offset_y: float = 0.0
    enabled: bool = True


@dataclass
class ElementDef:
    id: int
    key: str
    name: str
    description: str
    damage_def: str
    damage: int
    cost_text: str
    ingredients: List[List]  # [[label, amount], ...]
    primary_rgb: Tuple[int, int, int]
    secondary_rgb: Tuple[int, int, int]
    vfx_style: str
    is_builtin: bool = True
    layers: List[Dict] = field(default_factory=list)  # Optional list of VfxLayerSpec dicts
    allowed_kinds: Optional[List[int]] = None  # None = all weapon kinds; [0] = Sword only


def is_element_allowed(elem: ElementDef, kind: int) -> bool:
    """Returns True if the element can be applied to the specified weapon kind index."""
    return elem.allowed_kinds is None or kind in elem.allowed_kinds


BUILTIN_ELEMENTS: List[ElementDef] = [
    ElementDef(0, "None", "None (Không khảm)", "Không có sát thương nguyên tố", "", 0, "No extra materials", [], (120, 130, 134), (180, 190, 195), "none"),
    ElementDef(1, "Flame", "Flame (Lửa)", "Đánh trúng: +4 sát thương lửa · Tàn lửa bùng cháy", "PF_FlameStrike", 4, "Chemfuel 20 · Gold 6", [["Chemfuel", 20], ["Gold", 6]], (255, 125, 43), (255, 224, 140), "flame"),
    ElementDef(2, "Frost", "Frost (Băng)", "Đánh trúng: +3 sát thương băng · Làm chậm 15% trong 2s", "PF_FrostStrike", 3, "Jade 12 · Gold 6", [["Jade", 12], ["Gold", 6]], (94, 209, 255), (215, 246, 255), "frost"),
    ElementDef(3, "Thunder", "Thunder (Sét)", "Đánh trúng: +3 sát thương sốc (+5 lên Mechanoid)", "PF_StormStrike", 3, "Component 2 · Gold 6", [["Component", 2], ["Gold", 6]], (76, 118, 255), (240, 248, 255), "thunder"),
    ElementDef(4, "Venom", "Venom (Độc)", "Đánh trúng: +2 độc · Rút 1 HP/s trong 3s", "PF_VenomStrike", 2, "Herbal med 12 · Gold 6", [["Herbal med", 12], ["Gold", 6]], (102, 255, 61), (205, 255, 175), "venom"),
    ElementDef(5, "Concussion", "Concussion (Chấn Động)", "Đánh trúng: +2 đòn nặng · Choáng 0.5s (hồi 4s)", "PF_ConcussionStrike", 2, "Uranium 10 · Gold 6", [["Uranium", 10], ["Gold", 6]], (255, 209, 82), (255, 245, 200), "concussion"),
    ElementDef(6, "Siphon", "Siphon (Hút Máu)", "Đánh trúng: +2 cắt · Hồi tối đa 1 HP (hồi 4s)", "PF_SiphonStrike", 2, "Medicine 6 · Gold 6", [["Medicine", 6], ["Gold", 6]], (255, 51, 92), (255, 165, 185), "siphon"),
    # --- 6 NEW GORGEOUS ELEMENTS FOR 1.7 ---
    ElementDef(7, "Radiant", "Radiant (Thánh Quang)", "Đánh trúng: +4 ánh sáng thiêng · Thiêu rụi thực thể bóng tối", "PF_RadiantStrike", 4, "Gold 10 · Silver 15", [["Gold", 10], ["Silver", 15]], (255, 218, 92), (255, 252, 224), "radiant"),
    ElementDef(8, "Void", "Void (Hư Không)", "Đánh trúng: +4 hư vô · Xuyên giáp năng lượng & gây nhiễu tâm trí", "PF_VoidStrike", 4, "Uranium 10 · Gold 8", [["Uranium", 10], ["Gold", 8]], (155, 77, 255), (56, 18, 110), "void"),
    ElementDef(9, "Starlight", "Starlight (Tinh Quang)", "Đánh trúng: +3 tinh tú · Tia sáng ngân hà đa sắc rực rỡ", "PF_StarlightStrike", 3, "Jade 10 · Silver 12 · Gold 6", [["Jade", 10], ["Silver", 12], ["Gold", 6]], (92, 225, 230), (255, 119, 233), "starlight"),
    ElementDef(10, "SpiritWind", "Sakura Wind (Phong Linh)", "Đánh trúng: +3 phong nhận · Cánh anh đào xoay theo đường chém", "PF_SpiritWindStrike", 3, "Jade 12 · Gold 6", [["Jade", 12], ["Gold", 6]], (255, 148, 194), (168, 255, 224), "sakura"),
    ElementDef(11, "Magma", "Magma (Dung Nham)", "Đánh trúng: +5 nham thạch · Mạch dung nham đỏ rực trên lưỡi", "PF_MagmaStrike", 5, "Chemfuel 25 · Steel 15 · Gold 6", [["Chemfuel", 25], ["Steel", 15], ["Gold", 6]], (255, 68, 18), (255, 196, 48), "magma"),
    ElementDef(12, "Frostfire", "Frostfire (Băng Hỏa)", "Đánh trúng: +4 băng hỏa · Song xoắn lam-cam làm chậm & thiêu đốt", "PF_FrostfireStrike", 4, "Chemfuel 12 · Jade 10 · Gold 6", [["Chemfuel", 12], ["Jade", 10], ["Gold", 6]], (60, 240, 255), (255, 110, 40), "frostfire"),
    # --- 7 STYLIZED BLADE COATINGS & FLARES ---
    ElementDef(13, "AzureJet", "Azure Jet (Thanh Diêm Kiếm)", "Đánh trúng: +5 thanh diêm · Luồng lửa lam phóng dọc mũi & gai chắn", "PF_AzureJetStrike", 5, "Chemfuel 20 · Plasteel 10 · Gold 6", [["Chemfuel", 20], ["Plasteel", 10], ["Gold", 6]], (30, 155, 255), (175, 242, 255), "azure_jet"),
    ElementDef(14, "EmberTendrils", "Ember Crackle (U Hỏa)", "Đánh trúng: +4 u hỏa · Vòng chắn & tia lửa nứt tàn tro", "PF_EmberTendrilsStrike", 4, "Chemfuel 18 · Gold 6", [["Chemfuel", 18], ["Gold", 6]], (245, 105, 25), (255, 215, 115), "ember_tendrils"),
    ElementDef(15, "SonicSlash", "Sonic Wind (Bạch Trảm)", "Đánh trúng: +4 trảm khí · Sóng âm bạc-đen & tia xuyên tốc", "PF_SonicSlashStrike", 4, "Silver 20 · Plasteel 8", [["Silver", 20], ["Plasteel", 8]], (190, 200, 215), (250, 252, 255), "sonic_slash"),
    ElementDef(16, "IceArmor", "Ice Armor (Băng Giáp)", "Đánh trúng: +4 băng giáp · Giáp tinh thể băng sắc nhọn bọc lưỡi", "PF_IceArmorStrike", 4, "Jade 18 · Silver 10", [["Jade", 18], ["Silver", 10]], (55, 175, 248), (225, 250, 255), "ice_armor"),
    ElementDef(17, "PlasmaWeb", "Plasma Web (Lôi Mạng)", "Đánh trúng: +5 lôi mạng · Màng năng lượng tế bào lam-trắng", "PF_PlasmaWebStrike", 5, "Component 3 · Plasteel 8", [["Component", 3], ["Plasteel", 8]], (40, 145, 255), (235, 250, 255), "plasma_web"),
    ElementDef(18, "WaterSheath", "Water Sheath (Thủy Lưu)", "Đánh trúng: +3 thủy lưu · Dòng nước bọt trắng uốn lượn quanh lưỡi", "PF_WaterSheathStrike", 3, "Jade 14 · Silver 8", [["Jade", 14], ["Silver", 8]], (55, 130, 215), (242, 250, 255), "water_sheath"),
    ElementDef(19, "EclipseFlare", "Eclipse Flare (Nhật Thực)", "Đánh trúng: +6 nhật thực · Tinh tú hắc tâm & thương quang đỏ vàng", "PF_EclipseFlareStrike", 6, "Gold 12 · Uranium 10", [["Gold", 12], ["Uranium", 10]], (220, 45, 25), (255, 232, 145), "eclipse_flare"),
    # --- 3 SWORD-ONLY LEGENDARY SHADERS ---
    ElementDef(20, "ShadowStrife", "Shadow Strife (Bạch Viêm Hắc Vụ)", "Đánh trúng: +6 hắc vụ · Bạch viêm bùng tại đốc & khói đen quấn lưỡi kiếm", "PF_ShadowStrifeStrike", 6, "Bioferrite 15 · Silver 12 · Gold 8", [["Bioferrite", 15], ["Silver", 12], ["Gold", 8]], (22, 23, 28), (242, 248, 255), "shadow_strife", allowed_kinds=[0]),
    ElementDef(21, "EternalAlpha", "Eternal Alpha (Thần Quang Hoàng Kim)", "Đánh trúng: +6 thần quang · Cánh hoàng kim & hào quang thiên giới cho kiếm", "PF_EternalAlphaStrike", 6, "Gold 20 · Plasteel 12 · Silver 10", [["Gold", 20], ["Plasteel", 12], ["Silver", 10]], (245, 198, 72), (255, 250, 228), "eternal_alpha", allowed_kinds=[0]),
    ElementDef(22, "NovaBurn", "Nova Burn (Siêu Tân Tinh Tím)", "Đánh trúng: +7 siêu tân tinh · Hắc tâm vòng quỹ đạo & thương tím trắng", "PF_NovaBurnStrike", 7, "Uranium 16 · Gold 12 · Component 3", [["Uranium", 16], ["Gold", 12], ["Component", 3]], (198, 86, 255), (255, 240, 220), "nova_burn", allowed_kinds=[0]),
    # --- SIGNATURE SPECIAL WEAPON VFX ---
    ElementDef(23, "AbyssalMiasma", "Abyssal Miasma (U Minh Tử Khí)", "Đánh trúng: +6 tử khí · Ngọn lửa tím họng kiếm chuyển khói đen hắc ám", "PF_AbyssalMiasmaStrike", 6, "Bioferrite 18 · Obsidian 10 · Gold 8", [["Bioferrite", 18], ["Silver", 10], ["Gold", 8]], (32, 14, 52), (225, 65, 255), "abyssal_miasma"),
    ElementDef(24, "InkVoid", "Thái Hư Mặc Khí (Void Ink Mist)", "Đánh trúng: +7 mặc khí · Hắc hỏa & sương bạc trắng quấn quanh kiếm", "PF_InkVoidStrike", 7, "Plasteel 16 · Bioferrite 12 · Gold 8", [["Plasteel", 16], ["Bioferrite", 12], ["Gold", 8]], (16, 16, 22), (228, 234, 248), "ink_void"),
]


@dataclass
class SpecialWeaponDef:
    """Standalone complete legendary weapon (no modular forge part assembly required)."""
    id: str
    def_name: str
    name: str
    subtitle: str
    kind: int
    description: str
    lore: str
    damage: float
    armor_pen: float
    cooldown: float
    mass: float
    work: float
    req_skill: int
    default_element_id: int
    ingredients: List[List]
    texture_rel_path: str
    exclusive_skills: List[str] = field(default_factory=list)


SPECIAL_WEAPONS: List[SpecialWeaponDef] = [
    SpecialWeaponDef(
        id="abyssal_skullblade",
        def_name="PF_Special_AbyssalSkullblade",
        name="Hắc Sọ Tử Viêm Kiếm (Abyssal Skullblade)",
        subtitle="Vũ Khí Đặc Biệt · Nguyên Khối Hoàn Chỉnh · 5 Skill Riêng",
        kind=0,
        description="Đại kiếm ma đầu lâu nguyên khối: chuôi vuốt kẹp mảnh tinh thể tím, chắn tay 3 hốc sọ thép tối và lưỡi hắc diện thạch rực tử khí chuyển sương đen.",
        lore="Được rèn nguyên khối từ thép ám ảnh và tinh thể hư không mà không cần ghép từng phôi rời. Ngọn lửa tử linh bùng ra từ khe sọ rồi hóa thành màn sương đen nuốt chửng mọi nhát chém.",
        damage=32.0,
        armor_pen=0.44,
        cooldown=2.35,
        mass=2.25,
        work=14500.0,
        req_skill=14,
        default_element_id=23,
        ingredients=[["Plasteel", 55], ["Bioferrite", 30], ["Gold", 12], ["Uranium", 15]],
        texture_rel_path="Special/AbyssalSkullblade.png",
        exclusive_skills=[
            "sk_abyssal_dragon_cleave",
            "sk_phantom_blink",
            "sk_cyclone_vortex",
            "sk_soaring_pierce",
            "sk_pentagram_cataclysm",
        ],
    ),
    SpecialWeaponDef(
        id="tran_ac_inkblade",
        def_name="PF_Special_TranAcInkblade",
        name="Trấn Ác · Thái Hư Hắc Kiếm (Void Inkblade)",
        subtitle="Vũ Khí Đặc Biệt · Nguyên Khối Hoàn Chỉnh · 5 Skill Hắc Ảnh",
        kind=0,
        description="Hắc kiếm nguyên khối thân hắc thiết hoa văn cổ điển khảm ngọc lam-tím, chuôi quấn da đen kết vương miện hắc thạch và lưỡi bạc sắc lạnh tỏa hắc khí sương trắng.",
        lore="Thanh trọng kiếm Trấn Ác mang Thái Hư Kiếm Ý, mỗi đường vung đều kéo theo những dải mặc ảnh đen đặc sắc bén cắt nát không gian.",
        damage=34.0,
        armor_pen=0.48,
        cooldown=2.15,
        mass=2.10,
        work=15200.0,
        req_skill=15,
        default_element_id=24,
        ingredients=[["Plasteel", 60], ["Bioferrite", 28], ["Silver", 20], ["Gold", 14]],
        texture_rel_path="Special/TranAcInkblade.png",
        exclusive_skills=[
            "sk_ink_eclipse_ring",
            "sk_ink_void_wave",
            "sk_ink_void_aegis",
            "sk_ink_shadow_spikes",
            "sk_ink_blood_eclipse",
        ],
    ),
]

# Legacy list accessors
ENCHANTMENTS: List[str] = [e.name for e in BUILTIN_ELEMENTS]
ENCHANTMENT_DESCRIPTIONS: List[str] = [e.description for e in BUILTIN_ELEMENTS]

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
    color: Tuple[float, float, float]
    sharp_damage_mult: float = 1.0
    blunt_damage_mult: float = 1.0
    cooldown_mult: float = 1.0
    density: float = 1.0
    market_value: float = 1.9


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
    part_id: str
    category: str
    kind: int
    index: int
    name: str
    damage: float = 1.0
    cooldown: float = 1.0
    mass: float = 1.0
    penetration: float = 0.0
    work_mult: float = 1.0
    cost: int = 10
    socket_x: Optional[float] = None
    tang_root: float = 0.08
    is_atlas_cell: bool = False
    atlas_cell: int = -1
    texture_rel_path: str = ""


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
    pattern_parts: int = 1
    pattern_layout: int = 0
    pattern_offset_x: float = 0.0
    pattern_offset_y: float = 0.0
    metal_finish: int = 0
    head_tint: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    guard_tint: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    grip_tint: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    link_pommel_tint: bool = True
    pommel_tint: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    craft: int = 0
    enchantment: int = 0
    socket_gem: bool = True
    vfx_intensity: float = 1.25
    head_material_idx: int = 0
    guard_material_idx: int = 0
    grip_material_idx: int = 0
    name: str = ""
    inscription: str = ""
    story: str = ""

    @property
    def effective_pommel_tint(self) -> Tuple[float, float, float]:
        return self.guard_tint if self.link_pommel_tint else self.pommel_tint

    def has_pattern_on(self, part_bit_index: int) -> bool:
        return self.pattern != 0 and (self.pattern_parts & (1 << part_bit_index)) != 0


class ModAssetStore:
    """Manages loading, caching, and saving textures, custom parts & elements for Overgeared (1.7)."""

    def __init__(self, mod_root: str | Path):
        self.mod_root = Path(mod_root)
        self.textures_root = self.mod_root / "Textures" / "PersonalForge"
        self.parts_dir = self.textures_root / "Parts"
        self.patterns_dir = self.textures_root / "Patterns"
        self.effects_dir = self.textures_root / "Effects"
        self.registry_path = self.mod_root / "ForgeStudio_CustomParts.json"
        self.elements_path = self.mod_root / "ForgeStudio_CustomElements.json"

        self._part_cache: Dict[str, np.ndarray] = {}
        self._head_socket_cache: Dict[str, float] = {}
        self._center_socket_cache: Dict[str, Tuple[float, float, float]] = {}
        self._pattern_sums_cache: Dict[int, np.ndarray] = {}
        self._atlas_arr: Optional[np.ndarray] = None
        self._sparkle_pil: Optional[Image.Image] = None
        self._effect_pil_cache: Dict[str, Image.Image] = {}

        self.temp_textures: Dict[str, np.ndarray] = {}
        self.temp_effect_pils: Dict[str, Image.Image] = {}
        self.custom_parts: Dict[str, CustomPartEntry] = {}
        self.custom_elements: List[ElementDef] = []

        self.load_custom_registry()
        self.load_custom_elements()

    def set_mod_root(self, new_root: str | Path) -> None:
        self.mod_root = Path(new_root)
        self.textures_root = self.mod_root / "Textures" / "PersonalForge"
        self.parts_dir = self.textures_root / "Parts"
        self.patterns_dir = self.textures_root / "Patterns"
        self.effects_dir = self.textures_root / "Effects"
        self.registry_path = self.mod_root / "ForgeStudio_CustomParts.json"
        self.elements_path = self.mod_root / "ForgeStudio_CustomElements.json"
        self.clear_caches()
        self.load_custom_registry()
        self.load_custom_elements()

    def clear_caches(self) -> None:
        self._part_cache.clear()
        self._head_socket_cache.clear()
        self._center_socket_cache.clear()
        self._pattern_sums_cache.clear()
        self._atlas_arr = None
        self._sparkle_pil = None
        self._effect_pil_cache.clear()

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

    # ---- Elements (0..12 built-in + user custom elements) ----
    def load_custom_elements(self) -> None:
        self.custom_elements.clear()
        if self.elements_path.exists():
            try:
                raw = json.loads(self.elements_path.read_text(encoding="utf-8"))
                for item in raw.get("elements", []):
                    item["primary_rgb"] = tuple(item["primary_rgb"])
                    item["secondary_rgb"] = tuple(item["secondary_rgb"])
                    item["is_builtin"] = False
                    self.custom_elements.append(ElementDef(**item))
            except Exception:
                pass

    def save_custom_elements(self) -> None:
        data = {
            "version": "1.7",
            "elements": [asdict(e) for e in self.custom_elements],
        }
        self.elements_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_all_elements(self) -> List[ElementDef]:
        return list(BUILTIN_ELEMENTS) + list(self.custom_elements)

    def get_elements_for_kind(self, kind: int) -> List[ElementDef]:
        return [e for e in self.get_all_elements() if is_element_allowed(e, kind)]

    def get_element(self, elem_id: int) -> ElementDef:
        for e in self.get_all_elements():
            if e.id == elem_id:
                return e
        return BUILTIN_ELEMENTS[0]

    def add_custom_element(
        self,
        name: str,
        description: str,
        damage: int,
        primary_rgb: Tuple[int, int, int],
        secondary_rgb: Tuple[int, int, int],
        vfx_style: str,
        cost_text: str = "Gold 8 · Jade 8",
        ingredients: Optional[List[List]] = None,
        layers: Optional[List[Dict]] = None,
        allowed_kinds: Optional[List[int]] = None,
    ) -> ElementDef:
        all_ids = {e.id for e in self.get_all_elements()}
        new_id = len(BUILTIN_ELEMENTS)
        while new_id in all_ids:
            new_id += 1
        safe_key = "".join(ch for ch in name.title() if ch.isalnum()) or f"Element{new_id}"
        ed = ElementDef(
            id=new_id,
            key=safe_key,
            name=name,
            description=description,
            damage_def=f"PF_{safe_key}Strike",
            damage=damage,
            cost_text=cost_text,
            ingredients=ingredients if ingredients is not None else [["Gold", 8], ["Jade", 8]],
            primary_rgb=primary_rgb,
            secondary_rgb=secondary_rgb,
            vfx_style=vfx_style,
            is_builtin=False,
            layers=layers if layers is not None else [],
            allowed_kinds=list(allowed_kinds) if allowed_kinds is not None else None,
        )
        self.custom_elements.append(ed)
        self.save_custom_elements()
        return ed

    def get_effect_pil(self, rel_path: str) -> Optional[Image.Image]:
        if not rel_path:
            return None
        if rel_path in self.temp_effect_pils:
            return self.temp_effect_pils[rel_path]
        if rel_path in self._effect_pil_cache:
            return self._effect_pil_cache[rel_path]
        p = self.textures_root / rel_path
        if p.exists():
            with Image.open(p) as im:
                rgba = im.convert("RGBA")
                self._effect_pil_cache[rel_path] = rgba
                return rgba
        return None

    def remove_custom_element(self, elem_id: int) -> None:
        self.custom_elements = [e for e in self.custom_elements if e.id != elem_id]
        self.save_custom_elements()

    # ---- Lists of available parts (built-in + custom) ----
    def get_heads(self, kind: int) -> List[Tuple[int, str, str]]:
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
        if name in self.temp_textures:
            return self.temp_textures[name]
        if name in self._part_cache:
            return self._part_cache[name]

        standalone = self.parts_dir / f"{name}.png"
        cell = self._atlas_cell(name)

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
                    scan_y = max(2, min(out_h - 3, round(out_h * 0.045)))
                    row_alpha = out[scan_y, :, 3] > (128.0 / 255.0)
                    opaque_xs = np.where(row_alpha)[0]
                    sock = float(np.mean(opaque_xs + 0.5) / out_w) if len(opaque_xs) > 0 else 0.5
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
        sample_y = max(0, min(h - 1, round(min_y + (max_y - min_y) * 0.84)))
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
        if index == 0:
            return None
        if index in self._pattern_sums_cache:
            return self._pattern_sums_cache[index]
        temp_key = f"pattern_{index}"
        if temp_key in self.temp_textures:
            arr = self.temp_textures[temp_key]
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
            h_dmg, h_cd, h_work, h_mass, h_cost = MASTER_DAMAGE[kind], MASTER_COOLDOWN[kind], HEAD_WORK[3], HEAD_MASS[3], HEAD_COST[3]
        elif head < len(HEAD_DAMAGE):
            h_dmg, h_cd, h_work, h_mass, h_cost = HEAD_DAMAGE[head], HEAD_COOLDOWN[head], HEAD_WORK[head], HEAD_MASS[head], HEAD_COST[head]
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

        elem = self.get_element(design.enchantment)
        if elem.id > 0:
            for ing_label, ing_amt in elem.ingredients:
                add_ing(ing_label, int(ing_amt))

        if adv_parts > 0:
            add_ing("Plasteel", 12 * adv_parts)
            add_ing("Gold", 4 * adv_parts)

        return {
            "damage": damage,
            "cooldown": cooldown,
            "dps": dps,
            "armor_pen": armor_pen,
            "mass": mass,
            "work": work,
            "req_skill": req_skill,
            "ench_damage": elem.damage,
            "ingredients": ingredients,
            "base_mat_damage": BASE_WEAPON_DAMAGE[kind] * mat_dmg,
            "base_mat_cooldown": BASE_WEAPON_COOLDOWN[kind] * mat_cd,
        }

    def _custom_stats(self, part_id: str) -> ComponentStats:
        e = self.custom_parts.get(part_id)
        if e is None:
            return ComponentStats()
        return ComponentStats(e.damage, e.cooldown, e.mass, e.penetration, e.cost, e.work_mult)
