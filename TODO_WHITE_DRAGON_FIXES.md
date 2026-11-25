# Ghi Chú Tiến Độ & Danh Sách Cần Sửa Tiếp — Bạch Long Vũ Kiếm (White Feather Dragonblade)

Cập nhật: 2026-11-25  
Trạng thái hiện tại: **Đã dựng xong v1 toàn bộ code + XML + 130 frame PNG + Visual QA vòng 1 (2/9 PASS, 7/9 NEEDS_FIX).**  
Toàn bộ biên dịch Python (`py_compile`), kiểm tra XML (`ET.parse`), và xuất `generate_special_weapon_xml()` đều đã **PASS**.

---

## 1. Những gì ĐÃ làm xong (v1)

- **Vũ khí đặc biệt:** `white_dragon_featherblade` (`PF_Special_WhiteDragonFeatherblade`) — **Bạch Long Vũ Kiếm**
  - `ForgeStudio/special_weapon_renderer.py`: `_paint_white_dragon_featherblade()` + xuất `Overgeared/Textures/PersonalForge/Special/WhiteDragonFeatherblade.png`.
  - `ForgeStudio/mod_data.py`: `ElementDef(25, "PearlDragonMist", ...)` + `SpecialWeaponDef("white_dragon_featherblade", ...)`.
  - `ForgeStudio/forge_canvas.py`: `_draw_pearl_dragon_mist()` (hiệu ứng VFX trắng-đen + lông vũ).
- **5 Skill độc quyền + 130 frame PNG** (`ForgeStudio/skillfx_baker.py`, xuất vào `OvergearedCore/Textures/OvergearedCore/SkillFx/`):
  1. `sk_wdf_crescent_wave` → `OG_Fx_BachNguyetTramBa` (16 + 8 frame) — Chém bán nguyệt tầm xa *(Visual QA vòng 1: **PASS**)*
  2. `sk_wdf_planetary_cleave` → `OG_Fx_TinhCauBungNo` (18 + 8 frame) — Chém ngang + nổ hành tinh
  3. `sk_wdf_twin_dragon_aegis` → `OG_Fx_SongLongHoGiap` (18 + 8 frame, `centeredOnCaster=true`) — Khiên Trắng Đen có 2 con rồng bao bọc
  4. `sk_wdf_dragon_dash` → `OG_Fx_BachLongXungKich` (16 + 8 frame, `spawnAfterimages=true`) — Lướt nhanh tới kẻ địch kèm hiệu ứng hình con rồng
  5. `sk_wdf_cataclysm_5x5` → `OG_Fx_AmDuongDietGioi` (20 + 10 frame, `size=(5.0, 5.0)`, `aoeRadius=2.5`) — Vụ nổ lớn 5×5
- **RimWorld Core & Mod tích hợp:**
  - `OvergearedCore/Source/OvergearedCore/SkillFxDef.cs` & `MapComponent_OvergearedFx.cs`: đã thêm `public float aoeRadius = 0f;` để hỗ trợ sát thương AoE vuông 5×5 chuẩn theo ô.
  - `OvergearedCore/Defs/SkillFxDefs.xml`, `OvergearedCore/Patches/WhiteDragon_CorePatch.xml` (và fix 2 dòng tên cũ trong `TranAc_CorePatch.xml`).
  - `Overgeared/Defs/Enchantments.xml` (`PF_PearlDragonMistStrike`) & `Languages/English/Keyed/EnemyEnchants.xml`.
  - `SquishyMelee/Settings/Routines.xml` & `Languages/English/Keyed/SquishyMelee.xml` (5 routine `sk_wdf_*`).
  - `ForgeStudio/combat_arena_widget.py` & `ForgeStudio/special_weapons_widget.py` & `SETUP_AT_HOME.md`.

---

## 2. Danh Sách Cần Sửa Tiếp (Theo Kết Quả Visual QA Vòng 1)

### A. Ngoại hình vũ khí — `ForgeStudio/special_weapon_renderer.py` (`_paint_white_dragon_featherblade`)
*Mục tiêu: giống 100% thanh kiếm trắng bên trái ảnh mẫu.*

1. **Xóa khoảng trống xám ở gốc lưỡi kiếm:** Kéo dài gốc lưỡi xuống `y_throat = 0.595 * s` để 2 vảy cổ rồng ôm khít hình chữ V sát thân lưỡi kiếm, không để hở khoảng xám giữa lưỡi và chuôi.
2. **Sửa 2 vảy cổ rồng (dragon collars) mềm mại, hữu cơ hơn:**
   - Hiện tại viền đen quá dày và đều (`~2px`), vạch vảy thẳng tắp kiểu cơ khí, hình tam giác hơi cứng.
   - Đổi sang đường cong Bezier thanh mảnh, đổ bóng trắng ngà–xám ấm (`#FAF9F7 → #DCD9D3 → #ABA69F`), nét mực đen mảnh thay đổi độ dày (`0.5–1.2px`), vảy cong mềm + đuôi vảy chia đốt uốn xuống giữa chắn tay + 2 gai xương mảnh chĩa nhẹ sang phải trên.
3. **Sửa chất liệu lưỡi kiếm & vết khía mép trái:**
   - Phần thân giữa-dưới lưỡi đang bị cháy trắng (`#FFFFFF` phẳng). Thêm lớp vân khói nâu xám ấm painterly (`#746C64 → #A8A096 → #DDD8D0 → #F8F6F2`) dọc thân lưỡi, giữ viền sáng trắng gắt dọc mép cắt bên phải và sống giữa.
   - 3 vết khía trên 1/3 mép trái lưỡi đổi từ sóng mềm sang **khía lõm góc cạnh sắc nét** (có mấu nhọn nhô ra ở khoảng 2/3 chiều cao mép trái như ảnh mẫu).
4. **Sửa chùm lông vũ chắn tay:**
   - Các lông vũ dài bên phải hiện hơi thẳng/cứng như kim: bẻ cong Bezier **vòng ra ngoài rồi rủ mềm xuống gần ngang chuôi vòng**, đổ trong suốt nhẹ nhiều lớp.
   - Bên trái bỏ viền xám cứng thành mảng lông trắng mịn phủ lên trên bằng 2–3 nét mực đen uốn lượn thanh mảnh.
5. **Liền mạch chuôi → vòng giọt lệ (bỏ đường cắt ngang):**
   - Gộp thân chuôi và viền ngoài vòng giọt lệ thành **1 `QPainterPath` liên tục duy nhất** (`outer_path.subtracted(inner_hole)`) để tuyệt đối không còn vạch ngăn ngang.
   - Thu gọn vòng giọt lệ thon dài hơn một chút (`half-width ~ 0.025*s`), vẽ nhánh mực đen mảnh hữu cơ hơn quấn phần trên chuôi.

---

### B. VFX vũ khí & Lỗi font preview — `ForgeStudio/forge_canvas.py`
1. **Sửa lỗi ô vuông `□□□□...` ở dòng chữ đáy khung preview:** Trong `ForgePreviewCanvas.paintEvent` (dòng ~331), nạp font hỗ trợ UTF-8/tiếng Việt (`Segoe UI` / `Arial` qua `QFontDatabase`, giống `_get_arena_font` ở `combat_arena_widget.py`).
2. **Nâng cấp `_draw_pearl_dragon_mist()`:**
   - Thêm viền sáng bạc mảnh (`#cfd6e0`) cho dải mực đen để nổi bật rõ trên nền lò rèn tối.
   - Đổi hạt hình thoi thành hình **lông vũ trắng cong nhỏ** trôi lên.

---

### C. Root Cause Chung cho Skill 2, 3, 4, 5 — `ForgeStudio/skillfx_baker.py`
> **Nguyên nhân gốc khiến màu đen bị trắng xóa ở Skill 3 (thiếu Rồng Đen), Skill 4 (rồng trắng phẳng), Skill 5 (cột lõi bị trắng thay vì lõi đen):**
> Hàm `_finalize_frame` hiện tại vẽ `dark_arr` ở dưới cùng, rồi phủ `glow_arr` + `additive_glow(bloom)` + `additive_glow(core_arr)` đè lên trên. Vì vậy mọi lớp đen (`dd`) nằm dưới lớp trắng (`dg`/`dc`) đều bị cộng sáng biến thành trắng xóa!

**Cách sửa chuẩn:** Viết hàm compositing 4 lớp riêng `_finalize_mono_frame(im_back_glow, im_mid_white, im_ink_dark, im_top_core, ...)`:
1. `im_back_glow` (`db`): hào quang trắng viền ngoài + nửa sau vòng tròn 3D (blur bloom).
2. `im_mid_white` (`dw`): phần thân trắng chủ đạo (Bạch Long, tường plasma trắng, trăng sáng).
3. `im_ink_dark` (`dk`): **phủ đè LÊN TRÊN `dw` và `bloom`** — giữ màu đen tuyền `#06070b` tuyệt đối sắc nét (Hắc Long, lõi cột trụ đen 5×5, lõi hành tinh nhật thực, khoang miệng rồng, viền mực).
4. `im_top_core` (`dc`): **chỉ vẽ các chi tiết tiền cảnh sáng trắng có chủ đích** nằm trên `dk` (tia sét trắng chạy qua lõi đen, nửa trước 3 vòng rune 3D, mắt/sừng/nanh trắng của Hắc Long, tâm vụ nổ sao).

#### Chi tiết cần sửa từng skill:
1. **Skill 1 (`bake_bach_nguyet_tram_ba`) — Đã PASS, chỉ polish nhẹ:**
   - Đổi hạt hình thoi thành lông vũ cong mềm, uốn nhẹ 4 vệt gió kéo đuôi, thêm viền bạc mảnh `1.5px` ở mép lõm sau của lưỡi mực đen.
2. **Skill 2 (`bake_tinh_cau_bung_no`) — Sửa cả timing lẫn độ hoành tráng nổ hành tinh:**
   - **Pha chém ngang + hành tinh (`u = 0.00..0.46`):** Tăng kích thước hành tinh lên ~1.4×, vẽ kiểu **Nhật Thực Trắng-Đen** (lõi đen tuyền `#080a10` có vân miệng hố xám bạc + vành nhật hoa trắng rực), vòng quỹ đạo nét cọ dày mỏng biến thiên, 6 vệ tinh nửa đen–nửa trắng, và đường chém ngang lớn **lõi đen viền trắng rực** cắt đôi hành tinh (giống ảnh mẫu 2).
   - **Pha nổ hành tinh (`u = 0.46..1.00`, đạt đỉnh ở `u = 0.52..0.76`):** Xóa bỏ hành tinh nguyên vẹn ngay khi sang pha nổ; thay bằng **vụ nổ siêu tân tinh 12 tia sắc nhọn trắng-đen** (`r ~ 160–185px`), **18 mảnh vỡ hành tinh nửa đen–nửa trắng** văng tứ tung, và **2 vòng sóng xung kích** lan rộng.
3. **Skill 3 (`bake_song_long_ho_giap`) — Sửa vị trí tâm + vẽ đủ 2 rồng Trắng & Đen rõ đầu:**
   - **Căn đúng tâm Pawn:** Đặt `shield_cy = h * 0.52`, `base_y = h * 0.76`, `rx = w * 0.28`, `ry = h * 0.34`, và cập nhật `anchor = (0.50, 0.62)`, `size = (3.8, 3.10)` ở `combat_arena_widget.py` + `SkillFxDefs.xml` để khiên bao chuẩn giữa thân Pawn và vòng chân nằm đúng dưới chân Pawn.
   - **Đủ 2 con rồng đối lập (Âm Dương):**
     - **Bạch Long (nửa trên/trái):** thân trắng xà cừ (`dw`) viền mực đen (`dk`) + vảy sống lưng đen + đầu rồng to rõ (`scale ~ 44`), miệng mở lộ khoang miệng đen, nanh trắng, sừng phân nhánh, râu dài.
     - **Hắc Long (nửa dưới/phải):** hào quang viền trắng (`db`) + thân **đen tuyền `#07090d`** trên lớp `dk` + sống lưng/viền trắng sắc `2px` trên `dc` + đầu Hắc Long đen tuyền viền trắng, sừng trắng, mắt trắng phát sáng, nanh trắng rõ nét.
4. **Skill 4 (`bake_bach_long_xung_kich`) — Sửa tương phản trắng-đen & đầu rồng sắc nét:**
   - Dùng compositing 4 lớp: thân Bạch Long viền mực đen sắc + vảy lưng đen + thêm **1 dải rồng/khói mực đen xoắn quyện quanh thân Bạch Long**.
   - Đầu rồng phóng to rõ (`scale ~ 54`), khoang miệng đen tuyền (`dk`), nanh trắng, mắt sáng viền đen, sừng và râu trắng-đen rõ ràng; đẩy vòng sóng gió (`sonic rings`) lùi ra **sau cổ rồng** (`frac = 0.42, 0.62`) để không che mặt rồng.
   - Chỉnh `anchor_x = 0.44` để rồng ôm sát mũi kiếm của Pawn đang lướt tới.
5. **Skill 5 (`bake_am_duong_diet_gioi`) — Sửa đúng lõi cột ĐEN + 3 vòng rune 3D trước/sau cột + không cắt đỉnh:**
   - **Thứ tự vẽ 3D (Back → Front) chuẩn ảnh mẫu 3:**
     1. `db`: Xoáy mây trời ở `y = h * 0.10` (thấp xuống trong khung để không bị cắt đỉnh) + **nửa sau (`180°..360°`)** của 3 vòng rune (`y = 0.24h, 0.47h, 0.69h`) + hào quang trắng 2 bên cột.
     2. `dw`: 2 bức tường năng lượng trắng rực kẹp 2 bên cột (`[cx-56..cx-22]` và `[cx+22..cx+56]`) + gai năng lượng trắng bắn ra từ mặt đất.
     3. `dk` (đè lên `dw`): **Cột lõi hư không ĐEN TUYỀN `#05060a`** rộng ~58px chính giữa cột chạy thẳng từ xoáy mây xuống tâm hố nổ + **22 mảnh đá đen văng ra** quanh hố nổ 5×5.
     4. `dc` (đè lên `dk`): **Tia sét trắng sắc nhọn** chạy dọc/chéo cắt qua lõi cột đen + **nửa trước (`0°..180°`) của cả 3 vòng rune trắng** vắt ngang RÕ RÀNG phía trước cột lõi đen tạo chiều sâu 3D.
   - Chỉnh chiều cao arena `size = (4.4, 3.15)` và `anchor = (0.50, 0.72)` trong `combat_arena_widget.py` để cả xoáy mây đỉnh, 3 vòng rune và hố nổ đáy lọt trọn trong khung `260px` không bị cắt đầu.

---

## 3. Lệnh Kiểm Tra Nhanh Cho Phiên Sau

Sau khi sửa xong các mục ở phần 2, chạy lại 2 lệnh sau rồi gửi 9 ảnh trong `scratch/qa_white_dragon/` cho Visual QA kiểm tra đến khi đạt **9/9 PASS**:

```powershell
python d:\1IDK\ForgeStudio\skillfx_baker.py --white
python C:\Users\lamvu\.gemini\antigravity\brain\bb295acc-fd26-4c21-a15d-35d03f3c53c5\scratch\verify_white_dragon.py
```
