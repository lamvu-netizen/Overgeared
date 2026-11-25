# Ghi Chú Cài Đặt & Tương Thích Khi Mang Về Máy Nhà Có RimWorld 1.7

Máy hiện tại chưa cài sẵn game RimWorld, nên toàn bộ cấu trúc mod, XML, source C#, bộ PNG frame-by-frame và đấu trường mô phỏng đã được dựng sẵn trong workspace `d:\1IDK\`. Khi về máy nhà có RimWorld 1.7, bạn chỉ cần làm theo các bước dưới đây:

## 1. Các thư mục Mod trong `d:\1IDK\`
1. **`OvergearedCore/`** — **Core Mod Animation Riêng (`local.overgeared.core`)** kiến trúc **Fairycore multi-frame SkillFx**:
   - Chứa `Defs/SkillFxDefs.xml`:
     - Bộ 5 skill **Hắc Sọ Tử Viêm Kiếm**: `OG_Fx_PhongLongTram`, `OG_Fx_BaoTocAnhBo`, `OG_Fx_LongQuyenTanAnh`, `OG_Fx_LongPhongPhaKich`, `OG_Fx_NguMangTinhTran`.
     - Bộ 5 skill **Trấn Ác · Thái Hư Hắc Kiếm**: `OG_Fx_HacNhatTram`, `OG_Fx_ThaiHuTramBa`, `OG_Fx_HacGiapHoThe`, `OG_Fx_LeAnhPhaToai`, `OG_Fx_HuyetNguyetVoAnh`.
     - Bộ 5 skill **Bạch Long Vũ Kiếm**: `OG_Fx_BachNguyetTramBa`, `OG_Fx_TinhCauBungNo`, `OG_Fx_SongLongHoGiap`, `OG_Fx_BachLongXungKich`, `OG_Fx_AmDuongDietGioi` (AoE 5×5).
   - Chứa **386 texture PNG hoạt ảnh nhiều frame** tại `Textures/OvergearedCore/SkillFx/` (16–20 frame hiệu ứng chính `512x384` + 8–10 frame `HitFx` nổ va chạm `256x256` cho từng skill), tạo bằng `ForgeStudio/skillfx_baker.py`.
   - Chứa source C# RimWorld 1.7 + Harmony tại `Source/OvergearedCore/` (`SkillFxDef.cs`, `MapComponent_OvergearedFx.cs`, `CompOvergearedWeaponSkills.cs`, `HarmonyPatches.cs`, `OvergearedCoreMod.cs`) để làm tối nền đấu trường, rung camera, tạo tàn ảnh Pawn (afterimages), sát thương diện rộng 5×5 (`aoeRadius`), và gắn gizmo kích hoạt / tự proc skill cho vũ khí đặc biệt.
   - Chứa `Patches/Skullblade_CorePatch.xml` (`PF_Special_AbyssalSkullblade`), `Patches/TranAc_CorePatch.xml` (`PF_Special_TranAcInkblade`) & `Patches/WhiteDragon_CorePatch.xml` (`PF_Special_WhiteDragonFeatherblade`).
2. **`Overgeared/`** — Bản mod Personal Forge (Workshop `3837231051`) đã bổ sung:
   - Nguyên tố mới + DamageDef & Keyed XML (`Defs/Enchantments.xml`, `Languages/English/Keyed/EnemyEnchants.xml`), bao gồm `PF_AbyssalMiasmaStrike`, `PF_InkVoidStrike` & `PF_PearlDragonMistStrike`.
   - Patch tương thích `Patches/SquishyMeleeCompat.xml` + thứ tự tải `<loadAfter>` trong `About/About.xml` (`local.overgeared.core`, `local.gunrecoil`, `local.gunrecoil.melee`).
   - Texture vũ khí đặc biệt nguyên khối: `Textures/PersonalForge/Special/AbyssalSkullblade.png`, `Textures/PersonalForge/Special/TranAcInkblade.png` & `Textures/PersonalForge/Special/WhiteDragonFeatherblade.png`.
   - Khi bấm **"📦 Xuất XML vào Overgeared/Defs"** trong tab *Vũ Khí Đặc Biệt*, tool sẽ tạo `Defs/SpecialWeapons.xml` (đã nhúng sẵn `CompProperties_OvergearedWeaponSkills` ứng với 5 skill riêng của từng kiếm).
3. **`SquishyRanged/`** — Bản mod gốc **SQUISHY Ranged** (Workshop `3833016652`) đã clone đầy đủ, bao gồm bộ sprite Pawn RimWorld chuẩn (`Textures/HolsterPreview/Bodies/` & `Heads/`).
4. **`SquishyMelee/`** — Bản mod **SQUISHY Melee** (Workshop `3839642536`) đã clone đầy đủ và bổ sung **6 moveset Combo nhiều hit** (`combo_*`) + **5 moveset độc quyền Hắc Sọ Tử Viêm Kiếm** (`sk_abyssal_dragon_cleave`, `sk_phantom_blink`, `sk_cyclone_vortex`, `sk_soaring_pierce`, `sk_pentagram_cataclysm`) vào `Settings/Routines.xml` & `Languages/English/Keyed/SquishyMelee.xml`.

## 2. Build `OvergearedCore.dll` và đưa vào RimWorld 1.7 trên máy nhà
> Máy hiện tại không có `Assembly-CSharp.dll` / `UnityEngine.CoreModule.dll` của RimWorld, nên trước khi bật game lần đầu trên máy nhà bạn chỉ cần chạy 1 dòng PowerShell để compile C# ra `OvergearedCore/Assemblies/OvergearedCore.dll`:

```powershell
dotnet build OvergearedCore\Source\OvergearedCore\OvergearedCore.csproj -c Release -p:RimWorldDir="C:\Program Files (x86)\Steam\steamapps\common\RimWorld\RimWorldWin64_Data\Managed"
```
*(Thay đường dẫn `RimWorldDir` nếu bạn cài RimWorld ở ổ khác, ví dụ `D:\SteamLibrary\steamapps\common\RimWorld\RimWorldWin64_Data\Managed`.)*

Sau đó:
1. Copy 4 thư mục `OvergearedCore`, `Overgeared`, `SquishyRanged`, `SquishyMelee` vào thư mục `Mods/` của RimWorld (hoặc giữ Workshop cho `3833016652`/`3839642536` và copy đè `Settings/Routines.xml` + `Languages/English/Keyed/SquishyMelee.xml`).
2. Thứ tự Mod (Mod List) chuẩn trong RimWorld:
   1. `Core` (+ DLCs)
   2. `Harmony` (`2009463077`)
   3. `Overgeared Core Engine` (`local.overgeared.core` -> `OvergearedCore`)
   4. `SQUISHY Ranged` (`3833016652`)
   5. `SQUISHY Melee` (`3839642536`)
   6. `专属锻造 · Personal Forge` (`Overgeared`)

## 3. Khởi chạy Forge Studio để test nhanh ngay trên máy này
- Chạy `run_forge_studio.bat`.
- Vào tab **✨ Vũ Khí Đặc Biệt** -> chọn **Hắc Sọ Tử Viêm Kiếm (Abyssal Skullblade)** -> dùng thanh **5 Skill Độc Quyền** ở đấu trường bên dưới (**Phong Long Trảm**, **Bạo Tốc Ảnh Bộ**, **Long Quyển Tàn Ảnh**, **Long Phong Phá Kích**, **Ngũ Mang Hắc Tinh Trận**) hoặc bật **`▶ Auto Đấu Tập`**.
- Đấu trường sẽ tự làm tối nền, chạy tàn ảnh Pawn, phát đúng chuỗi **PNG 16–20 frame** của `OvergearedCore/Textures/OvergearedCore/SkillFx/` kèm **HitFx explosion bursts**, slow-mo hitstop và rung camera.
