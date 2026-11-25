"""
Exact Python/NumPy port of PersonalForge (RimWorld 1.7) weapon composition,
surface finishes, pattern engraving, WeaponVisualStyle.Refine, and Enchantment VFX.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

from mod_data import (
    GRIP_MATERIALS,
    METALS,
    ModAssetStore,
    WeaponDesignState,
)


SWORD_TANG_ROOTS = [1.0 / 32.0, 5.0 / 64.0, 0.0625, 3.0 / 32.0]


@dataclass
class ComposedResult:
    image_rgba: Image.Image          # Top-down PIL RGBA (256x256 or 512x512)
    blade_mask_alpha: Image.Image    # Top-down PIL L mask of the blade/head region for rim-glow
    resolution: int
    draw_size: float
    grip_y_norm: float               # Normalized 0..1 from bottom
    socket_gem_y_norm: float         # Normalized 0..1 from bottom (guard/blade junction)
    equipped_angle: float            # 25 for sword/axe/hammer, 65 for spear
    enchant_span: Tuple[float, float]
    enchant_center_x: float
    enchant_half_width: float
    preview_anchors: List[Tuple[float, float]]  # local coords in [-0.5, 0.5]


def _smoothstep(edge0: float, edge1: float, x: np.ndarray | float) -> np.ndarray | float:
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _metal_color(mat_idx: int, is_grip: bool = False) -> Tuple[float, float, float]:
    if is_grip:
        mat = GRIP_MATERIALS[max(0, min(len(GRIP_MATERIALS) - 1, mat_idx))]
        if mat.def_name == "WoodLog":
            return (1.0, 1.0, 1.0)
    else:
        mat = METALS[max(0, min(len(METALS) - 1, mat_idx))]
        if mat.def_name == "Steel":
            return (1.0, 1.0, 1.0)
    r, g, b = mat.color
    m = max(r, g, b, 0.01)
    return (r / m, g / m, b / m)


def _mul_color(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (a[0] * b[0], a[1] * b[1], a[2] * b[2])


def _bilinear_sample(src: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Unity-compatible GetPixelBilinear with Clamp wrap mode on bottom-up RGBA [H, W, 4]."""
    sh, sw, _ = src.shape
    fx = np.clip(u * sw - 0.5, 0.0, max(0, sw - 1))
    fy = np.clip(v * sh - 0.5, 0.0, max(0, sh - 1))
    x0 = np.floor(fx).astype(np.int32)
    y0 = np.floor(fy).astype(np.int32)
    x1 = np.minimum(x0 + 1, sw - 1)
    y1 = np.minimum(y0 + 1, sh - 1)
    wx = (fx - x0)[..., None]
    wy = (fy - y0)[..., None]

    c00 = src[y0, x0]
    c10 = src[y0, x1]
    c01 = src[y1, x0]
    c11 = src[y1, x1]

    c0 = c00 * (1.0 - wx) + c10 * wx
    c1 = c01 * (1.0 - wx) + c11 * wx
    return c0 * (1.0 - wy) + c1 * wy


def _end_scale(y: np.ndarray, joins: Tuple[float, float, float, float], blend: float) -> np.ndarray:
    t1 = np.clip((y - joins[0]) / max(blend, 1e-6), 0.0, 1.0)
    t2 = np.clip((joins[1] - y) / max(blend, 1e-6), 0.0, 1.0)
    s1 = joins[2] + (1.0 - joins[2]) * (t1 * t1 * (3.0 - 2.0 * t1))
    s2 = joins[3] + (1.0 - joins[3]) * (t2 * t2 * (3.0 - 2.0 * t2))
    return np.minimum(s1, s2)


def _mount_scale(y: np.ndarray, mount: Tuple[float, float, float, float]) -> np.ndarray:
    dist = np.maximum(np.maximum(mount[0] - y, y - mount[1]), 0.0)
    t = np.clip(dist / max(mount[3], 1e-6), 0.0, 1.0)
    return mount[2] + (1.0 - mount[2]) * (t * t * (3.0 - 2.0 * t))


def _pattern_coverage(sums: np.ndarray, u: np.ndarray, v: np.ndarray, width: float, height: float) -> np.ndarray:
    x0 = np.clip(np.floor((u - width * 0.5) * 256.0).astype(np.int32), 0, 255)
    y0 = np.clip(np.floor((v - height * 0.5) * 256.0).astype(np.int32), 0, 255)
    x1 = np.clip(np.ceil((u + width * 0.5) * 256.0).astype(np.int32), x0 + 1, 256)
    y1 = np.clip(np.ceil((v + height * 0.5) * 256.0).astype(np.int32), y0 + 1, 256)
    area_sum = sums[y1, x1] - sums[y0, x1] - sums[y1, x0] + sums[y0, x0]
    denom = 255.0 * (x1 - x0) * (y1 - y0)
    return np.clip(area_sum * 4.0 / denom, 0.0, 1.0).astype(np.float32)


def _ornament_layout(lx: np.ndarray, ly: np.ndarray, layout: int) -> np.ndarray:
    if layout == 1:
        d = np.maximum(np.abs(lx), np.abs(ly)) * 2.0
        return np.clip((0.78 - d) * 8.0, 0.0, 1.0)
    if layout == 2:
        d = np.maximum(np.abs(lx), np.abs(ly)) * 2.0
        return np.clip((d - 0.55) * 8.0, 0.0, 1.0) * np.clip((1.05 - d) * 10.0, 0.0, 1.0)
    return np.ones_like(lx, dtype=np.float32)


def _draw_layer(
    target: np.ndarray,
    source: Optional[np.ndarray],
    anchor_x: float,
    bottom: float,
    height: float,
    anchor_frac: float,
    tint: Tuple[float, float, float],
    source_rect: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    clip_top: float = 256.0,
    preserve_accents: bool = False,
    pattern_sums: Optional[np.ndarray] = None,
    design: Optional[WeaponDesignState] = None,
    finish: int = 0,
    clip_bottom: float = 0.0,
    shaft_joins: Optional[Tuple[float, float, float, float]] = None,
    shaft_mount: Optional[Tuple[float, float, float, float]] = None,
) -> None:
    if source is None or height <= 0.0:
        return
    res = target.shape[0]
    scale = res / 256.0
    anchor_x *= scale
    bottom *= scale
    height *= scale
    clip_top *= scale
    clip_bottom *= scale

    sh, sw, _ = source.shape
    rx, ry, rw, rh = source_rect
    base_w = height * sw * rw / max(sh * rh, 1e-6)
    h_ceil = int(math.ceil(height))
    if h_ceil <= 0 or base_w <= 0.0:
        return

    y_start = int(round(bottom))
    i_idx = np.arange(h_ceil, dtype=np.int32)
    py = y_start + i_idx
    valid_y = (py >= 0) & (py < res) & (py < clip_top) & (py >= clip_bottom)
    if not np.any(valid_y):
        return
    i_idx = i_idx[valid_y]
    py = py[valid_y]

    if shaft_joins is not None:
        blend = min(7.0, (shaft_joins[1] - shaft_joins[0]) * 0.22)
        y_256 = (py.astype(np.float32) + 0.5) / scale
        row_scale = _end_scale(y_256, shaft_joins, blend)
        if shaft_mount is not None:
            row_scale = np.minimum(row_scale, _mount_scale(y_256, shaft_mount))
    else:
        row_scale = np.ones_like(py, dtype=np.float32)

    row_widths = base_w * row_scale
    max_w = int(math.ceil(float(np.max(row_widths))))
    if max_w <= 0:
        return

    if shaft_joins is not None:
        row_x_starts = np.round(anchor_x - row_widths * anchor_frac).astype(np.int32)
    else:
        x0_const = int(round(anchor_x - base_w * anchor_frac))
        row_x_starts = np.full_like(py, x0_const)

    # Bounding X range in target
    min_px = max(0, int(np.min(row_x_starts)))
    max_px = min(res - 1, int(np.max(row_x_starts + np.ceil(row_widths).astype(np.int32))) - 1)
    if max_px < min_px:
        return

    px_grid = np.arange(min_px, max_px + 1, dtype=np.int32)[None, :]  # (1, W_box)
    py_grid = py[:, None]                                              # (H_box, 1)
    j_grid = px_grid - row_x_starts[:, None]                           # (H_box, W_box)
    rw_grid = row_widths[:, None]
    in_bounds = (j_grid >= 0) & (j_grid < np.ceil(rw_grid))
    if not np.any(in_bounds):
        return

    u_local = (j_grid + 0.5) / np.maximum(rw_grid, 1e-6)
    v_local = (i_idx[:, None] + 0.5) / height
    u_src = rx + u_local * rw
    v_src = ry + v_local * rh

    col = _bilinear_sample(source, u_src, v_src)
    # Zero alpha out of layer row bounds
    col[~in_bounds, 3] = 0.0

    # Tint
    tr, tg, tb = tint
    t_max = max(tr, tg, tb)
    is_white = (abs(tr - 1.0) < 1e-5 and abs(tg - 1.0) < 1e-5 and abs(tb - 1.0) < 1e-5)
    t_min = min(tr, tg, tb)
    chroma = t_max - t_min
    denom = max(t_max, 0.001)
    # Color.Lerp(white, tint / denom, 0.8) * (0.35 + 0.65 * t_max)
    factor = 0.35 + 0.65 * t_max
    val_tint = np.array([
        (0.2 + 0.8 * (tr / denom)) * factor,
        (0.2 + 0.8 * (tg / denom)) * factor,
        (0.2 + 0.8 * (tb / denom)) * factor,
    ], dtype=np.float32)

    orig_lum = (col[:, :, 0] + col[:, :, 1] + col[:, :, 2]) / 3.0
    if preserve_accents:
        c_max = np.max(col[:, :, :3], axis=2)
        c_min = np.min(col[:, :, :3], axis=2)
        accent_mask = (c_max - c_min) > 0.12
    else:
        accent_mask = np.zeros(col.shape[:2], dtype=bool)

    if not is_white:
        tinted = col[:, :, :3] * val_tint[None, None, :]
        boost = np.maximum(0.0, orig_lum - 0.55) * 0.15 * chroma
        tinted += boost[:, :, None]
        w_tint = np.clip((orig_lum - 0.12) / 0.16, 0.0, 1.0)[:, :, None]
        blended_rgb = col[:, :, :3] * (1.0 - w_tint) + tinted * w_tint
        apply_tint = (~accent_mask)[:, :, None]
        col[:, :, :3] = np.where(apply_tint, blended_rgb, col[:, :, :3])

    # Metal finish
    lum2 = (col[:, :, 0] + col[:, :, 1] + col[:, :, 2]) / 3.0
    if finish != 0:
        f_mask = (~accent_mask) & (lum2 > 0.18)
        if np.any(f_mask):
            if finish == 1:
                mult = ((0.12 + lum2 * 0.65) / np.maximum(lum2, 1e-6))[:, :, None]
                col[:, :, :3] = np.where(f_mask[:, :, None], col[:, :, :3] * mult, col[:, :, :3])
            elif finish == 2:
                col[:, :, :3] = np.where(f_mask[:, :, None], col[:, :, :3] * 0.56, col[:, :, :3])
            elif finish == 3:
                bronze = np.array([0.9, 0.76, 0.56], dtype=np.float32)[None, None, :]
                col[:, :, :3] = np.where(f_mask[:, :, None], col[:, :, :3] * bronze, col[:, :, :3])

    # Pattern engraving
    if pattern_sums is not None and design is not None and design.pattern_strength > 0.0:
        p_mask = (
            (~accent_mask)
            & (col[:, :, 3] > 0.9)
            & (orig_lum > 0.28)
            & (orig_lum < 0.9)
            & (u_local > 0.12)
            & (u_local < 0.88)
            & (v_local > 0.2)
            & (v_local < 0.92)
        )
        if np.any(p_mask):
            pr, pg, pb = design.pattern_color
            p_max = max(pr, pg, pb)
            p_norm = np.array([pr / p_max, pg / p_max, pb / p_max], dtype=np.float32) if p_max > 0.001 else np.ones(3, dtype=np.float32)

            lx = (u_local - 0.12) / 0.76 - 0.5 - design.pattern_offset_x
            ly = (v_local - 0.2) / 0.72 - 0.5 - design.pattern_offset_y
            rx_p, ry_p = lx, ly
            for _ in range(design.pattern_rotation % 4):
                rx_p, ry_p = -ry_p, rx_p
            rx_p = rx_p * design.pattern_scale + 0.5
            ry_p = ry_p * design.pattern_scale + 0.5

            pw = 1.0 / max(base_w * 0.76, 1e-6)
            ph = 1.0 / max(height * 0.72, 1e-6)
            if (design.pattern_rotation % 2) == 1:
                pw, ph = ph, pw

            cov = _pattern_coverage(
                pattern_sums,
                np.mod(rx_p, 1.0),
                np.mod(ry_p, 1.0),
                pw * design.pattern_scale,
                ph * design.pattern_scale,
            )
            cov *= _ornament_layout(lx, ly, design.pattern_layout)
            cov *= design.pattern_strength
            cov = np.where(p_mask, cov, 0.0)[:, :, None]

            lum3 = (col[:, :, 0] + col[:, :, 1] + col[:, :, 2]) / 3.0
            p_shaded = p_norm[None, None, :] * (((0.12 + 0.88 * lum3) * (0.18 + 0.82 * p_max))[:, :, None])
            col[:, :, :3] = col[:, :, :3] * (1.0 - cov) + p_shaded * cov

    # Porter-Duff Over blend onto target[py, min_px:max_px+1]
    dst = target[py, min_px:max_px + 1]
    sa = col[:, :, 3:4]
    da = dst[:, :, 3:4]
    out_a = sa + da * (1.0 - sa)
    safe_a = np.maximum(out_a, 1e-6)
    out_rgb = (col[:, :, :3] * sa + dst[:, :, :3] * da * (1.0 - sa)) / safe_a
    mask_out = out_a[:, :, 0] > 0.0
    dst[:, :, :3] = np.where(mask_out[:, :, None], out_rgb, dst[:, :, :3])
    dst[:, :, 3:4] = np.where(mask_out[:, :, None], out_a, dst[:, :, 3:4])
    target[py, min_px:max_px + 1] = dst


def _contact_shadow(target: np.ndarray, seat: float, depth: float, reverse: bool = False) -> None:
    res = target.shape[0]
    scale = res / 256.0
    seat *= scale
    depth *= scale
    y0 = max(0, int(math.floor(seat - depth)))
    y1 = min(res - 1, int(math.ceil(seat)))
    x0 = int(112.0 * scale)
    x1 = int(144.0 * scale)
    if y1 < y0 or x1 < x0:
        return
    ys = np.arange(y0, y1 + 1, dtype=np.float32)[:, None]
    t = np.clip((ys - seat + depth) / max(depth, 0.1), 0.0, 1.0)
    mul = 1.0 - 0.22 * ((1.0 - t) if reverse else t)
    region = target[y0:y1 + 1, x0:x1 + 1]
    has_alpha = region[:, :, 3:4] > 0.0
    region[:, :, :3] = np.where(has_alpha, region[:, :, :3] * mul[:, :, None], region[:, :, :3])
    target[y0:y1 + 1, x0:x1 + 1] = region


def _refine(target: np.ndarray) -> None:
    """Exact port of WeaponVisualStyle.Refine."""
    alpha_pos = target[:, :, 3:4] > 0.0
    rgb = target[:, :, :3]
    num = np.maximum(0.0, rgb * 1.28 - 0.035)
    toned = np.minimum(0.98, np.where(num <= 0.88, num, 0.88 + (num - 0.88) * 0.45))
    arr = target.copy()
    arr[:, :, :3] = np.where(alpha_pos, toned, rgb)

    luma = arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114
    a_ok = arr[:, :, 3] > 0.98
    interior = (
        a_ok[1:-1, 1:-1]
        & (luma[1:-1, 1:-1] > 0.17)
        & a_ok[1:-1, :-2]
        & a_ok[1:-1, 2:]
        & a_ok[:-2, 1:-1]
        & a_ok[2:, 1:-1]
    )
    avg_nbr = (luma[1:-1, :-2] + luma[1:-1, 2:] + luma[:-2, 1:-1] + luma[2:, 1:-1]) * 0.25
    delta = np.clip((luma[1:-1, 1:-1] - avg_nbr) * 0.42, -0.045, 0.045)
    delta = np.where(interior, delta, 0.0)[:, :, None]
    arr[1:-1, 1:-1, :3] = np.clip(arr[1:-1, 1:-1, :3] + delta, 0.0, 1.0)
    target[:] = arr


def compose_weapon(
    store: ModAssetStore,
    design: WeaponDesignState,
    resolution: int = 512,
    visible_parts: int = 15,
) -> ComposedResult:
    """Composes the custom weapon exactly like WeaponArt.Compose in PersonalForge 1.7."""
    target = np.zeros((resolution, resolution, 4), dtype=np.float32)

    kind = design.kind
    head = design.head
    guard = design.guard
    grip = design.grip
    pommel = design.pommel

    num = 158.0 if (kind == 3 and head == 3) else [85.0, 143.0, 143.0, 175.0][kind]
    num2 = 32.0 + (num - 32.0) * design.handle_length
    grip_mat_col = _metal_color(design.grip_material_idx, is_grip=True)
    num3 = (88.0 if (kind == 3 and head == 3) else [152.0, 96.0, 96.0, 70.0][kind]) * design.head_size

    head_name = f"head_{kind}_{head}"
    head_tex = store.get_part(head_name)
    if head_tex is None:
        head_tex = np.zeros((64, 32, 4), dtype=np.float32)
    num4 = store.get_head_socket(kind, head)
    num5 = ([0.3, 0.37, 0.28][head] * num3) if (kind == 1 and head < 3) else 0.0
    num6 = num2 - 3.0 - num5

    flag = (guard == 2 or guard == 4)
    guard_part_name = f"master_guard_{kind}" if guard == 3 else f"guard_{guard}"
    guard_tex_name = "guard_2" if guard == 4 else guard_part_name
    guard_tex = store.get_part(guard_tex_name)
    if guard_tex is None:
        guard_tex = np.zeros((32, 64, 4), dtype=np.float32)

    if guard == 3:
        num7 = [90.0, 23.0, 24.0, 43.0][kind]
    else:
        num7 = 28.0 if flag else [81.0, 43.0, 38.0, 37.0][kind]
    num7 *= design.guard_size
    num8 = num7 * guard_tex.shape[0] / max(guard_tex.shape[1], 1)

    if flag:
        num9 = 52.0 + num8 * (1.4 if guard == 4 else 0.55)
        num2 = max(num2, num9)
        num6 = num2 - 3.0 - num5

    num10 = (num2 - num8 * 0.55) if flag else (num2 + 3.0)
    pommel_part_name = f"master_pommel_{kind}" if pommel == 2 else f"pommel_{pommel}"
    pommel_tex = store.get_part(pommel_part_name)
    if pommel_tex is None:
        pommel_tex = np.zeros((32, 32, 4), dtype=np.float32)
    num11 = 27.0 * design.pommel_size
    num12 = 47.0 - num11
    num13 = num2 + 14.0 * design.head_size

    socket = store.get_center_socket(guard_tex_name)
    socket2 = store.get_center_socket(pommel_part_name)
    num14 = num10 + num8 * socket[1]
    num15 = num10 + num8 * socket[0]
    num16 = 0.0

    if kind == 0:
        custom_entry = store.custom_parts.get(head_name)
        tang_root = custom_entry.tang_root if (custom_entry is not None) else (0.08 if head >= 4 else SWORD_TANG_ROOTS[head])
        num17 = num3 * tang_root
        num6 = (num10 + num8 * 0.78 if flag else (num14 - min(2.0, num8 * 0.12))) - num17
        num13 = (num10 + num8 * 0.4) if flag else (num15 + min(3.0, num8 * 0.35))
        if not flag:
            num16 = num15 + 0.5

    num18 = max(num6 + num3, num2 + 3.0 + num8, num13)
    num19 = min(num12, num6, num10 - (num8 * 0.85 if guard == 4 else 0.0))
    num20 = num3 * head_tex.shape[1] / max(head_tex.shape[0], 1)
    num21 = max(
        16.0,
        num7 / 2.0,
        num20 * num4,
        num20 * (1.0 - num4),
        num11 * pommel_tex.shape[1] / max(pommel_tex.shape[0], 1) / 2.0,
    )
    num22 = min(1.0, 224.0 / max(num18 - num19, 1.0), 224.0 / max(2.0 * num21, 1.0))
    num23 = ((256.0 - (num18 - num19) * num22) / 2.0 - num19 * num22) if num22 < 1.0 else 0.0

    pattern_sums = store.get_pattern_sums(design.pattern) if design.pattern != 0 else None

    # Collar back
    if flag and (visible_parts & 2) != 0:
        _draw_collar(target, guard_tex, num10 * num22 + num23, num8 * num22, design, pattern_sums, front=False)

    num24 = num12 + num11 * (socket2[0] + (socket2[1] - socket2[0]) * (0.86 if pommel == 3 else 0.8))
    num25 = 21.0 if kind == 0 else 16.0
    num26 = max(num25 * 0.4, min(num25, num11 * pommel_tex.shape[1] / max(pommel_tex.shape[0], 1) * socket2[2] * 0.88))
    num27 = max(num25 * 0.38, min(num25, num7 * socket[2] * 0.9)) if (kind == 0 and not flag) else num25
    num28 = max(0.38, min(1.0, num7 * (0.7 if flag else (socket[2] * 0.9)) / num25))
    mount = (
        (num10 - (num8 * 0.85 if guard == 4 else 0.0) if flag else num15) * num22 + num23,
        num14 * num22 + num23,
        num28,
        6.0 * num22,
    )

    if (visible_parts & 4) != 0:
        grip_tex = store.get_part(f"grip_{grip}")
        _draw_shaft(
            target,
            grip_tex,
            num24 * num22 + num23,
            num13 * num22 + num23,
            num25 * num22,
            _mul_color(grip_mat_col, design.grip_tint),
            pattern_sums if design.has_pattern_on(3) else None,
            design,
            num26 / num25,
            num27 / num25,
            mount if (visible_parts & 2) != 0 else None,
        )

    if (visible_parts & 6) == 6:
        _contact_shadow(target, (num10 if flag else num15) * num22 + num23, 2.5 * num22)
        if guard == 4:
            _contact_shadow(target, (num10 - num8 * 0.85) * num22 + num23, 3.0 * num22)

    if (visible_parts & 0xC) == 12:
        _contact_shadow(target, (num12 + num11 * socket2[1] + 2.0) * num22 + num23, 3.0 * num22, reverse=True)

    if (visible_parts & 8) != 0:
        _draw_layer(
            target,
            pommel_tex,
            128.0,
            num12 * num22 + num23,
            num11 * num22,
            0.5,
            _mul_color(_metal_color(design.guard_material_idx), design.effective_pommel_tint),
            preserve_accents=(pommel == 2),
            pattern_sums=pattern_sums if design.has_pattern_on(2) else None,
            design=design,
            finish=design.metal_finish,
        )

    if (visible_parts & 1) != 0:
        _draw_layer(
            target,
            head_tex,
            128.0,
            num6 * num22 + num23,
            num3 * num22,
            num4,
            _mul_color(_metal_color(design.head_material_idx), design.head_tint),
            preserve_accents=(head == 3),
            pattern_sums=pattern_sums if design.has_pattern_on(0) else None,
            design=design,
            finish=design.metal_finish,
            clip_bottom=(num16 * num22 + num23) if (visible_parts & 2) != 0 else 0.0,
        )

    if (visible_parts & 2) != 0:
        if flag:
            _draw_collar(target, guard_tex, num10 * num22 + num23, num8 * num22, design, pattern_sums, front=True)
        else:
            _draw_layer(
                target,
                guard_tex,
                128.0,
                num10 * num22 + num23,
                num8 * num22,
                0.5,
                _mul_color(_metal_color(design.guard_material_idx), design.guard_tint),
                preserve_accents=(guard == 3),
                pattern_sums=pattern_sums if design.has_pattern_on(1) else None,
                design=design,
                finish=design.metal_finish,
            )

    _refine(target)

    # Enchantment metadata
    enchant_span = (
        (num6 * num22 + num23) / 256.0 - 0.5,
        ((num6 + num3) * num22 + num23) / 256.0 - 0.5,
    )
    blade_w = num20 * num22
    enchant_center_x = (0.5 - num4) * blade_w / 256.0
    enchant_half_width = blade_w * 0.5 / 256.0

    # PreviewEnchantmentSurface anchors
    anchors: List[Tuple[float, float]] = []
    x_min_a = max(0, min(resolution - 1, math.floor((0.5 + enchant_center_x - enchant_half_width) * resolution)))
    x_max_a = max(0, min(resolution - 1, math.ceil((0.5 + enchant_center_x + enchant_half_width) * resolution)))
    for idx_a in range(28):
        t_a = 0.08 + 0.84 * idx_a / 27.0
        row_y = max(0, min(resolution - 1, round((0.5 + enchant_span[0] + (enchant_span[1] - enchant_span[0]) * t_a) * resolution)))
        target_x = (0.5 + enchant_center_x + math.sin(idx_a * 2.399963) * enchant_half_width * 0.7) * resolution
        best_x = -1
        best_d = 1e9
        row_alphas = target[row_y, x_min_a:x_max_a + 1, 3]
        valid_xs = np.where(row_alphas >= 0.9)[0] + x_min_a
        if len(valid_xs) > 0:
            diffs = np.abs(valid_xs.astype(np.float32) - target_x)
            best_x = int(valid_xs[int(np.argmin(diffs))])
            anchors.append(((best_x + 0.5) / resolution - 0.5, (row_y + 0.5) / resolution - 0.5))

    grip_y = (32.0 + ([62.0, 76.0, 76.0, 90.0][kind] - 32.0) * design.handle_length) * num22 + num23
    socket_gem_y = ((num10 + num8 * 0.52) * num22 + num23) / 256.0
    draw_size = (1.6 if kind == 3 else 1.05) * design.overall_size / max(num22, 1e-4)
    equipped_angle = 65.0 if kind == 3 else 25.0

    # Extract blade region alpha mask (top-down L) for rim-aura glow
    scale_res = resolution / 256.0
    blade_y_bot = max(0, int(math.floor((num6 * num22 + num23) * scale_res)))
    blade_y_top = min(resolution, int(math.ceil(((num6 + num3) * num22 + num23) * scale_res)))
    blade_alpha_bu = np.zeros((resolution, resolution), dtype=np.float32)
    blade_alpha_bu[blade_y_bot:blade_y_top, :] = target[blade_y_bot:blade_y_top, :, 3]
    blade_mask_u8 = np.flipud(np.clip(blade_alpha_bu * 255.0 + 0.5, 0, 255).astype(np.uint8))
    blade_mask_pil = Image.fromarray(blade_mask_u8, "L")

    # Flip bottom-up -> top-down RGBA8
    u8 = np.flipud(np.clip(target * 255.0 + 0.5, 0, 255).astype(np.uint8))
    img = Image.fromarray(u8, "RGBA")

    return ComposedResult(
        image_rgba=img,
        blade_mask_alpha=blade_mask_pil,
        resolution=resolution,
        draw_size=draw_size,
        grip_y_norm=grip_y / 256.0,
        socket_gem_y_norm=socket_gem_y,
        equipped_angle=equipped_angle,
        enchant_span=enchant_span,
        enchant_center_x=enchant_center_x,
        enchant_half_width=enchant_half_width,
        preview_anchors=anchors,
    )


def _draw_shaft(
    target: np.ndarray,
    source: Optional[np.ndarray],
    bottom: float,
    top: float,
    width: float,
    tint: Tuple[float, float, float],
    pattern_sums: Optional[np.ndarray],
    design: WeaponDesignState,
    bottom_scale: float,
    top_scale: float,
    mount: Optional[Tuple[float, float, float, float]],
) -> None:
    if source is None:
        return
    rect = (0.04, 0.17, 0.92, 0.66)
    sh, sw, _ = source.shape
    seg_h = width * sh * rect[3] / max(sw * rect[2], 1e-6)
    step = max(seg_h - 2.0, 1.0)
    y = bottom
    while y < top:
        _draw_layer(
            target,
            source,
            128.0,
            y,
            seg_h,
            0.5,
            tint,
            source_rect=rect,
            clip_top=top,
            preserve_accents=False,
            pattern_sums=pattern_sums,
            design=design,
            finish=0,
            clip_bottom=0.0,
            shaft_joins=(bottom, top, bottom_scale, top_scale),
            shaft_mount=mount,
        )
        y += step


def _draw_collar(
    target: np.ndarray,
    source: Optional[np.ndarray],
    bottom: float,
    height: float,
    design: WeaponDesignState,
    pattern_sums: Optional[np.ndarray],
    front: bool,
) -> None:
    rect = (0.0, 0.0, 1.0, 0.57) if front else (0.0, 0.57, 1.0, 0.43)
    count = 2 if design.guard == 4 else 1
    tint = _mul_color(_metal_color(design.guard_material_idx), design.guard_tint)
    ps = pattern_sums if design.has_pattern_on(1) else None
    for n in range(count - 1, -1, -1):
        _draw_layer(
            target,
            source,
            128.0,
            bottom - n * height * 0.85 + rect[1] * height,
            height * rect[3],
            0.5,
            tint,
            source_rect=rect,
            clip_top=256.0,
            preserve_accents=False,
            pattern_sums=ps,
            design=design,
            finish=design.metal_finish,
        )


def enchantment_tint(element: int) -> Tuple[int, int, int]:
    return {
        1: (255, 125, 43),   # Flame
        2: (94, 209, 255),   # Frost
        3: (189, 122, 255),  # Thunder
        4: (102, 255, 61),   # Venom
        5: (255, 209, 82),   # Concussion
        6: (255, 51, 92),    # Siphon
    }.get(element, (189, 122, 255))


def enchantment_core(element: int) -> Tuple[int, int, int]:
    r, g, b = enchantment_tint(element)
    return (
        int(r * 0.52 + 255 * 0.48),
        int(g * 0.52 + 255 * 0.48),
        int(b * 0.52 + 255 * 0.48),
    )


def enchantment_fade(age: float) -> float:
    t1 = max(0.0, min(1.0, age / 0.16))
    t2 = max(0.0, min(1.0, (1.0 - age) / 0.38))
    s1 = t1 * t1 * (3.0 - 2.0 * t1)
    s2 = t2 * t2 * (3.0 - 2.0 * t2)
    return s1 * s2
