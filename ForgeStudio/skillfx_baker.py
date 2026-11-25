"""
Multi-frame Painterly SkillFx PNG Sequence Baker for OvergearedCore (Fairycore-tier architecture).
Generates progressive 16-20 frame RGBA SkillFx sequences + 8-10 frame HitFx impact bursts
into OvergearedCore/Textures/OvergearedCore/SkillFx/<Folder>/<frame:02d>.png.

Uses multi-octave turbulent FBM field warping + multi-layer inked smoke backing +
radiant neon amethyst/lilac-white energy ribbons + anime dragon skull + faceted crystals.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

DEFAULT_SKILLFX_ROOT = Path(r"d:\1IDK\OvergearedCore\Textures\OvergearedCore\SkillFx")


def _smooth_grid_noise(h: int, w: int, grid_h: int, grid_w: int, rng: np.random.Generator) -> np.ndarray:
    small = rng.uniform(-1.0, 1.0, size=(grid_h, grid_w)).astype(np.float32)
    img = Image.fromarray(((small * 0.5 + 0.5) * 255.0).clip(0, 255).astype(np.uint8), mode="L")
    up = img.resize((w, h), resample=Image.Resampling.BICUBIC)
    return (np.asarray(up, dtype=np.float32) / 255.0) * 2.0 - 1.0


def build_fbm_pair(h: int, w: int, seed: int) -> Tuple[np.ndarray, np.ndarray]:
    """Generates smooth multi-octave 2D turbulent noise fields (nx, ny) in [-1, 1]."""
    rng = np.random.default_rng(seed)
    nx = np.zeros((h, w), dtype=np.float32)
    ny = np.zeros((h, w), dtype=np.float32)
    amp = 0.55
    for gh, gw in [(6, 8), (12, 16), (24, 32), (48, 64)]:
        nx += _smooth_grid_noise(h, w, gh, gw, rng) * amp
        ny += _smooth_grid_noise(h, w, gh, gw, rng) * amp
        amp *= 0.52
    return nx, ny


def warp_layer(rgba_arr: np.ndarray, dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
    """Bilinearly warps an RGBA uint8/float image by float displacement fields (dx, dy)."""
    h, w, _ = rgba_arr.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sx = np.clip(xx + dx, 0.0, w - 1.001)
    sy = np.clip(yy + dy, 0.0, h - 1.001)
    x0 = np.floor(sx).astype(np.int32)
    y0 = np.floor(sy).astype(np.int32)
    fx = (sx - x0)[..., None]
    fy = (sy - y0)[..., None]
    x1 = np.minimum(w - 1, x0 + 1)
    y1 = np.minimum(h - 1, y0 + 1)
    c00 = rgba_arr[y0, x0]
    c10 = rgba_arr[y0, x1]
    c01 = rgba_arr[y1, x0]
    c11 = rgba_arr[y1, x1]
    return (
        c00 * (1.0 - fx) * (1.0 - fy)
        + c10 * fx * (1.0 - fy)
        + c01 * (1.0 - fx) * fy
        + c11 * fx * fy
    )


def alpha_over(dst: np.ndarray, src: np.ndarray) -> np.ndarray:
    """Premultiplied-safe straight-RGBA alpha compositing on float32 [0..255] arrays."""
    sa = np.clip(src[..., 3:4] / 255.0, 0.0, 1.0)
    da = np.clip(dst[..., 3:4] / 255.0, 0.0, 1.0)
    out_a = sa + da * (1.0 - sa)
    denom = np.maximum(out_a, 1e-5)
    out_rgb = (src[..., :3] * sa + dst[..., :3] * da * (1.0 - sa)) / denom
    out = np.empty_like(dst)
    out[..., :3] = out_rgb
    out[..., 3:4] = out_a * 255.0
    return out


def additive_glow(dst: np.ndarray, src: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """Adds luminous energy bloom over dark/mid backing with alpha preservation."""
    sa = np.clip(src[..., 3:4] / 255.0, 0.0, 1.0) * strength
    out = dst.copy()
    out[..., :3] = np.clip(out[..., :3] + src[..., :3] * sa, 0.0, 255.0)
    out[..., 3:4] = np.clip(np.maximum(out[..., 3:4], src[..., 3:4] * strength * 0.85), 0.0, 255.0)
    return out


def _blur_arr(arr: np.ndarray, radius: float) -> np.ndarray:
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGBA")
    im = im.filter(ImageFilter.GaussianBlur(radius=radius))
    return np.asarray(im, dtype=np.float32)


def _new_canvas(w: int, h: int) -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im, "RGBA")


def _draw_tapered_ribbon(
    draw: ImageDraw.ImageDraw,
    pts: List[Tuple[float, float]],
    widths: List[float],
    fill_rgba: Tuple[int, int, int, int],
) -> None:
    """Draws a smooth variable-width calligraphy ribbon polygon along centerline pts."""
    if len(pts) < 2:
        return
    left: List[Tuple[float, float]] = []
    right: List[Tuple[float, float]] = []
    n = len(pts)
    for i, (px, py) in enumerate(pts):
        x0, y0 = pts[max(0, i - 1)]
        x1, y1 = pts[min(n - 1, i + 1)]
        tx, ty = x1 - x0, y1 - y0
        ln = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / ln, tx / ln
        hw = max(0.6, widths[i])
        left.append((px + nx * hw, py + ny * hw))
        right.append((px - nx * hw, py - ny * hw))
    poly = left + list(reversed(right))
    draw.polygon(poly, fill=fill_rgba)


def _paint_dragon_head(
    draw_dark: ImageDraw.ImageDraw,
    draw_glow: ImageDraw.ImageDraw,
    draw_core: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    angle_deg: float,
    scale: float,
    jaw_open: float,
    fade: float,
) -> None:
    """Paints an anime Abyssal Dragon skull/head roaring along angle_deg with mane tendrils, fangs & eye flare."""
    rad = math.radians(angle_deg)
    ca, sa = math.cos(rad), math.sin(rad)

    def xform(lx: float, ly: float) -> Tuple[float, float]:
        rx = (lx * ca - ly * sa) * scale + cx
        ry = (lx * sa + ly * ca) * scale + cy
        return (rx, ry)

    a_dark = int(235 * fade)
    a_mid = int(215 * fade)
    a_core = int(250 * fade)

    # Flowing shadowy smoke mane plumes flaring behind skull
    mane_paths = [
        [(-0.20, -0.30), (-0.75, -0.58), (-1.45, -0.78), (-2.10, -0.62)],
        [(-0.15, -0.10), (-0.82, -0.32), (-1.62, -0.40), (-2.30, -0.22)],
        [(-0.18, 0.15), (-0.78, 0.34), (-1.42, 0.44), (-1.95, 0.32)],
    ]
    for mpts in mane_paths:
        wpts = [xform(x, y) for x, y in mpts]
        ws = [0.22 * scale, 0.16 * scale, 0.09 * scale, 0.02 * scale]
        _draw_tapered_ribbon(draw_dark, wpts, ws, (24, 10, 44, int(215 * fade)))
        _draw_tapered_ribbon(draw_glow, wpts[:3], [w * 0.55 for w in ws[:3]], (165, 45, 245, int(175 * fade)))

    # Swept-back twin dragon horns (ink silhouette + crisp violet rim)
    horn_upper = [(-0.08, -0.24), (-0.52, -0.56), (-1.05, -0.78), (-1.38, -0.86), (-0.85, -0.50), (-0.28, -0.16)]
    horn_lower = [(-0.18, -0.14), (-0.64, -0.34), (-1.08, -0.44), (-0.62, -0.24)]
    horn_rim = [xform(x, y) for x, y in [(-0.14, -0.25), (-0.60, -0.56), (-1.28, -0.83)]]
    draw_dark.polygon([xform(x, y) for x, y in horn_upper], fill=(22, 8, 42, a_dark))
    draw_glow.polygon([xform(x, y) for x, y in horn_lower], fill=(165, 48, 240, a_mid))
    _draw_tapered_ribbon(draw_glow, horn_rim, [0.06 * scale, 0.04 * scale, 0.015 * scale], (220, 92, 255, int(235 * fade)))
    _draw_tapered_ribbon(draw_core, horn_rim[:2], [0.025 * scale, 0.015 * scale], (248, 212, 255, int(215 * fade)))

    # Upper skull & fierce hooked snout
    snout_pts = [
        (-0.34, -0.26), (0.04, -0.34), (0.52, -0.24), (0.98, -0.10),
        (1.06, -0.02), (0.88, 0.08), (0.74, 0.00), (0.56, 0.08),
        (0.36, 0.02), (0.06, 0.06), (-0.26, -0.04),
    ]
    draw_dark.polygon([xform(x, y) for x, y in snout_pts], fill=(26, 10, 48, a_dark))

    # Glowing violet skull plate highlights & ridge
    ridge_pts = [(-0.12, -0.24), (0.28, -0.24), (0.74, -0.11), (0.94, -0.05), (0.58, -0.04), (0.14, -0.08)]
    draw_glow.polygon([xform(x, y) for x, y in ridge_pts], fill=(182, 52, 248, int(205 * fade)))
    core_ridge = [(0.05, -0.20), (0.52, -0.14), (0.90, -0.06), (0.50, -0.09)]
    draw_core.polygon([xform(x, y) for x, y in core_ridge], fill=(246, 204, 255, a_core))

    # Roaring lower jaw rotated open by jaw_open
    jo = 0.16 + jaw_open * 0.28
    jaw_pts = [
        (-0.22, 0.04), (0.14, 0.08 + jo * 0.4), (0.64, 0.14 + jo * 0.9),
        (0.84, 0.08 + jo * 0.8), (0.62, 0.24 + jo), (0.12, 0.24 + jo * 0.65), (-0.28, 0.14),
    ]
    draw_dark.polygon([xform(x, y) for x, y in jaw_pts], fill=(24, 9, 44, a_dark))
    draw_glow.polygon([xform(x * 0.92, y - 0.02) for x, y in jaw_pts[1:6]], fill=(145, 42, 225, int(165 * fade)))

    # Sharp upper & lower fangs
    for fx, fy, dy in [(0.78, 0.03, 0.12), (0.54, 0.04, 0.10), (0.34, 0.03, 0.08)]:
        draw_core.polygon([xform(fx - 0.04, fy), xform(fx + 0.04, fy), xform(fx + 0.01, fy + dy)], fill=(252, 232, 255, a_core))
    for fx, fy, dy in [(0.68, 0.11 + jo * 0.85, -0.10), (0.44, 0.13 + jo * 0.72, -0.09)]:
        draw_core.polygon([xform(fx - 0.035, fy), xform(fx + 0.035, fy), xform(fx + 0.02, fy + dy)], fill=(245, 200, 255, int(225 * fade)))

    # Piercing glowing eye slit + trailing eye-flare streak!
    eye_c = xform(0.22, -0.12)
    draw_core.polygon([xform(0.08, -0.11), xform(0.24, -0.17), xform(0.38, -0.11), xform(0.22, -0.07)], fill=(255, 245, 255, 255))
    _draw_tapered_ribbon(
        draw_core,
        [eye_c, xform(-0.18, -0.22), xform(-0.68, -0.34)],
        [0.05 * scale, 0.03 * scale, 0.005 * scale],
        (245, 195, 255, int(235 * fade)),
    )


def _paint_crystal_spire(
    draw_dark: ImageDraw.ImageDraw,
    draw_glow: ImageDraw.ImageDraw,
    draw_core: ImageDraw.ImageDraw,
    bx: float,
    by: float,
    angle_rad: float,
    length: float,
    half_w: float,
    fade: float,
) -> None:
    """Paints a faceted dark-obsidian & glowing amethyst crystal shard."""
    ca, sa = math.cos(angle_rad), math.sin(angle_rad)
    tip = (bx + ca * length, by + sa * length)
    mid_l = (bx + ca * length * 0.62 - sa * half_w, by + sa * length * 0.62 + ca * half_w)
    mid_r = (bx + ca * length * 0.56 + sa * half_w * 0.92, by + sa * length * 0.56 - ca * half_w * 0.92)
    base_l = (bx - sa * half_w * 0.52, by + ca * half_w * 0.52)
    base_r = (bx + sa * half_w * 0.48, by - ca * half_w * 0.48)

    # Dark obsidian body + left lit amethyst bevel + bright inner spine
    draw_dark.polygon([base_l, mid_l, tip, mid_r, base_r], fill=(32, 12, 58, int(235 * fade)))
    draw_glow.polygon([base_l, mid_l, tip, (bx + ca * length * 0.48, by + sa * length * 0.48)], fill=(185, 58, 255, int(210 * fade)))
    draw_core.polygon([
        (bx + ca * length * 0.18, by + sa * length * 0.18),
        mid_l,
        tip,
    ], fill=(246, 205, 255, int(225 * fade)))


def _draw_spark(
    draw_core: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    angle_rad: float,
    length: float,
    width: float,
    rgba: Tuple[int, int, int, int],
) -> None:
    ca, sa = math.cos(angle_rad), math.sin(angle_rad)
    px, py = -sa * width, ca * width
    pts = [
        (cx - ca * length * 0.4, cy - sa * length * 0.4),
        (cx + px, cy + py),
        (cx + ca * length, cy + sa * length),
        (cx - px, cy - py),
    ]
    draw_core.polygon(pts, fill=rgba)


def _finalize_frame(
    im_dark: Image.Image,
    im_glow: Image.Image,
    im_core: Image.Image,
    fbm_x: np.ndarray,
    fbm_y: np.ndarray,
    t_norm: float,
    warp_amp: float,
    glow_radius: float = 5.5,
) -> Image.Image:
    """Applies swirling FBM painterly displacement, blooms glow & core, composites final RGBA frame."""
    phase = t_norm * 2.0 * math.pi
    dx = fbm_x * warp_amp * math.cos(phase) - fbm_y * (warp_amp * 0.5) * math.sin(phase)
    dy = fbm_y * warp_amp * math.sin(phase) + fbm_x * (warp_amp * 0.5) * math.cos(phase)

    dark_arr = warp_layer(np.asarray(im_dark, dtype=np.float32), dx * 1.15, dy * 1.15)
    glow_arr = warp_layer(np.asarray(im_glow, dtype=np.float32), dx * 0.72, dy * 0.72)
    core_arr = warp_layer(np.asarray(im_core, dtype=np.float32), dx * 0.30, dy * 0.30)

    bloom = _blur_arr(glow_arr, glow_radius)
    dark_halo = _blur_arr(dark_arr, 7.5)
    dark_halo[..., 3] *= 0.68
    out = alpha_over(dark_halo, dark_arr)
    out = alpha_over(out, glow_arr)
    out = additive_glow(out, bloom, 0.85)
    out = additive_glow(out, core_arr, 0.96)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGBA")


def bake_phong_long_tram(out_dir: Path, fbm_x: np.ndarray, fbm_y: np.ndarray) -> None:
    """16 frames: Overhead sweeping crescent dragon void cleave roaring forward into ground impact."""
    w, h = 512, 384
    n_frames = 16
    rng = np.random.default_rng(101)
    for fi in range(n_frames):
        u = fi / (n_frames - 1)
        im_d, dd = _new_canvas(w, h)
        im_g, dg = _new_canvas(w, h)
        im_c, dc = _new_canvas(w, h)

        fade = min(1.0, u / 0.14) * min(1.0, (1.0 - u) / 0.22)
        fade = max(0.05, fade)

        # Crescent sweeps dynamically across frames 0..11, lingers & tears apart on 12..15
        sweep = min(1.0, max(0.08, u / 0.68))
        trail = max(0.0, (u - 0.55) / 0.45)
        ang0 = math.radians(-172.0 + trail * 95.0)
        ang1 = math.radians(-155.0 + sweep * 208.0)

        cx, cy = w * 0.45, h * 0.56
        rad_x, rad_y = w * 0.36, h * 0.39

        # Outer dark shadow smoke arc + glowing amethyst arc + razor core
        pts, w_dark, w_glow, w_core = [], [], [], []
        segs = 38
        for k in range(segs + 1):
            s = k / segs
            th = ang0 + (ang1 - ang0) * s
            pts.append((cx + math.cos(th) * rad_x, cy + math.sin(th) * rad_y))
            bell = (s ** 0.58) * math.sin(min(1.0, 0.10 + 0.90 * s) * math.pi * 0.92)
            base_w = 54.0 * bell * (1.0 - trail * 0.55)
            w_dark.append(base_w * 1.15)
            w_glow.append(base_w * 0.65)
            w_core.append(base_w * 0.24)

        _draw_tapered_ribbon(dd, pts, w_dark, (22, 8, 42, int(230 * fade)))
        _draw_tapered_ribbon(dg, pts, w_glow, (185, 52, 248, int(225 * fade)))
        _draw_tapered_ribbon(dc, pts, w_core, (248, 214, 255, int(248 * fade)))

        # Secondary parallel wind-blade sliver inside the main arc
        inner_pts = [(cx + math.cos(ang0 + (ang1 - ang0) * (k / 24.0)) * (rad_x * 0.78),
                      cy + math.sin(ang0 + (ang1 - ang0) * (k / 24.0)) * (rad_y * 0.78)) for k in range(25)]
        inner_w = [14.0 * math.sin((k / 24.0) * math.pi) * fade for k in range(25)]
        _draw_tapered_ribbon(dg, inner_pts, inner_w, (150, 42, 235, int(175 * fade)))

        # Abyssal Dragon Skull roaring at the leading tip of the slash!
        head_th = ang1
        hx = cx + math.cos(head_th) * (rad_x * 0.94)
        hy = cy + math.sin(head_th) * (rad_y * 0.94)
        jaw_o = math.sin(min(1.0, u / 0.6) * math.pi)
        _paint_dragon_head(dd, dg, dc, hx, hy, math.degrees(head_th) + 92.0, 56.0 * (0.85 + 0.25 * fade), jaw_o, fade)

        # Impact ground shockwave ring on frames 5..12
        if 0.32 <= u <= 0.88:
            su = (u - 0.32) / 0.56
            ix, iy = w * 0.72, h * 0.72
            rx_s = 32.0 + su * 95.0
            ry_s = 12.0 + su * 28.0
            a_s = int(215 * (1.0 - su))
            dg.ellipse([ix - rx_s, iy - ry_s, ix + rx_s, iy + ry_s], outline=(215, 78, 255, a_s), width=4)
            dc.ellipse([ix - rx_s * 0.85, iy - ry_s * 0.85, ix + rx_s * 0.85, iy + ry_s * 0.85], outline=(250, 225, 255, int(a_s * 0.9)), width=2)

        # Void sparks flying tangentially off the slash arc
        for _ in range(18):
            st = ang0 + rng.uniform(0.15, 0.98) * (ang1 - ang0)
            sr = rng.uniform(0.84, 1.14)
            _draw_spark(dc, cx + math.cos(st) * rad_x * sr, cy + math.sin(st) * rad_y * sr,
                        st + math.pi * 0.5, rng.uniform(12.0, 28.0), rng.uniform(1.6, 3.4), (244, 195, 255, int(225 * fade)))

        frame_img = _finalize_frame(im_d, im_g, im_c, fbm_x, fbm_y, u, warp_amp=9.5 + u * 5.0)
        frame_img.save(out_dir / f"{fi:02d}.png")


def bake_bao_toc_anh_bo(out_dir: Path, fbm_x: np.ndarray, fbm_y: np.ndarray) -> None:
    """16 frames: Supersonic horizontal dash gale slashes + Mach cone + rushing dragon wake."""
    w, h = 512, 384
    n_frames = 16
    rng = np.random.default_rng(202)
    for fi in range(n_frames):
        u = fi / (n_frames - 1)
        im_d, dd = _new_canvas(w, h)
        im_g, dg = _new_canvas(w, h)
        im_c, dc = _new_canvas(w, h)

        fade = min(1.0, u / 0.12) * min(1.0, (1.0 - u) / 0.20)
        fade = max(0.05, fade)

        front_x = w * (0.20 + min(1.0, u / 0.65) * 0.72)
        tail_x = max(w * 0.04, front_x - w * (0.48 + 0.16 * math.sin(u * math.pi)))

        # Twin-tier horizontal gale slash waves + ink wind-stream backing
        for tier_y, amp_w, is_main in [(h * 0.52, 34.0, True), (h * 0.36, 18.0, False), (h * 0.66, 20.0, False)]:
            pts, wd, wg, wc = [], [], [], []
            for k in range(28):
                s = k / 27.0
                px = tail_x + (front_x - tail_x) * s
                py = tier_y + math.sin(s * 6.0 - u * 10.0) * (9.0 if is_main else 6.0)
                bell = math.sin(s * math.pi) ** 0.75
                pts.append((px, py))
                wd.append(amp_w * bell * fade)
                wg.append(amp_w * 0.58 * bell * fade)
                wc.append(amp_w * 0.22 * bell * fade)
            _draw_tapered_ribbon(dd, pts, wd, (22, 9, 44, int(225 * fade)))
            _draw_tapered_ribbon(dg, pts, wg, (190, 58, 250, int(218 * fade)))
            _draw_tapered_ribbon(dc, pts, wc, (250, 218, 255, int(245 * fade)))

        # Tapered sonic-boom crescent wave curving behind the speed rush
        if u < 0.72:
            mu = u / 0.72
            mx = w * 0.25 + mu * 62.0
            my = h * 0.52
            c_pts, c_wd, c_wg, c_wc = [], [], [], []
            for k in range(21):
                ks = (k / 20.0) * 2.0 - 1.0
                ang_s = ks * 1.15
                px_c = mx + math.cos(ang_s) * (28.0 + mu * 38.0) - (ks * ks) * 18.0
                py_c = my + math.sin(ang_s) * (62.0 + mu * 42.0)
                w_bell = math.cos(ks * math.pi * 0.5) ** 1.1
                c_pts.append((px_c, py_c))
                c_wd.append(22.0 * w_bell * (1.0 - mu))
                c_wg.append(12.0 * w_bell * (1.0 - mu))
                c_wc.append(4.5 * w_bell * (1.0 - mu))
            _draw_tapered_ribbon(dd, c_pts, c_wd, (22, 8, 44, int(210 * (1.0 - mu))))
            _draw_tapered_ribbon(dg, c_pts, c_wg, (205, 76, 255, int(225 * (1.0 - mu))))
            _draw_tapered_ribbon(dc, c_pts, c_wc, (248, 222, 255, int(240 * (1.0 - mu))))

        # Staggered jagged needle speed-streaks across the corridor
        for idx_s in range(14):
            y_s = h * (0.20 + (idx_s / 13.0) * 0.62)
            x0_s = w * rng.uniform(0.06, 0.38) + u * 70.0
            ln_s = rng.uniform(85.0, 210.0)
            _draw_spark(dc, x0_s, y_s, 0.0, ln_s, rng.uniform(1.5, 3.2), (242, 195, 255, int(220 * fade)))

        # Dragon skull rushing horizontally along top slipstream
        dhx = min(w * 0.80, front_x - 18.0)
        dhy = h * 0.34
        _paint_dragon_head(dd, dg, dc, dhx, dhy, 4.0, 44.0 * (0.85 + 0.2 * fade), 0.55, fade * 0.92)

        frame_img = _finalize_frame(im_d, im_g, im_c, fbm_x, fbm_y, u, warp_amp=7.5)
        frame_img.save(out_dir / f"{fi:02d}.png")


def bake_long_quyen_tan_anh(out_dir: Path, fbm_x: np.ndarray, fbm_y: np.ndarray) -> None:
    """18 frames: 3D braided void cyclone funnel spiraling upward with Abyssal Dragon bursting from crown."""
    w, h = 512, 384
    n_frames = 18
    rng = np.random.default_rng(303)
    for fi in range(n_frames):
        u = fi / (n_frames - 1)
        im_d, dd = _new_canvas(w, h)
        im_g, dg = _new_canvas(w, h)
        im_c, dc = _new_canvas(w, h)

        fade = min(1.0, u / 0.14) * min(1.0, (1.0 - u) / 0.22)
        fade = max(0.05, fade)

        cx = w * 0.50
        base_y = h * 0.80
        height_scale = min(1.0, 0.35 + u * 1.15)
        spin = u * 3.4 * 2.0 * math.pi

        # Ground vortex seal ellipse
        grx = w * (0.18 + 0.06 * math.sin(u * math.pi))
        gry = h * 0.065
        dd.ellipse([cx - grx, base_y - gry, cx + grx, base_y + gry], outline=(24, 10, 48, int(220 * fade)), width=8)
        dg.ellipse([cx - grx * 0.86, base_y - gry * 0.86, cx + grx * 0.86, base_y + gry * 0.86], outline=(205, 65, 255, int(215 * fade)), width=3)

        # 3 interwoven helical tornado bands climbing bottom -> crown
        for strand_idx, (ph, col_g, is_core) in enumerate([
            (0.0, (165, 42, 238), False),
            (2.09, (218, 86, 255), True),
            (4.18, (138, 35, 215), False),
        ]):
            pts, wd, wg, wc = [], [], [], []
            steps = 46
            for k in range(steps + 1):
                t = k / steps
                th = t * (2.8 * 2.0 * math.pi) - spin + ph
                rad_t = w * (0.075 + 0.24 * (t ** 0.72))
                px = cx + math.sin(th) * rad_t
                py = base_y - t * (h * 0.60 * height_scale) + math.cos(th) * rad_t * 0.19
                # Front-facing ribbon swells slightly larger than back-facing side
                depth_mod = 0.65 + 0.35 * math.cos(th)
                bell = (math.sin(t * math.pi) ** 0.62) * depth_mod
                pts.append((px, py))
                wd.append(24.0 * bell * fade)
                wg.append(14.0 * bell * fade)
                wc.append((5.5 if is_core else 3.2) * bell * fade)
            _draw_tapered_ribbon(dd, pts, wd, (22, 8, 42, int(220 * fade)))
            _draw_tapered_ribbon(dg, pts, wg, (*col_g, int(215 * fade)))
            if is_core:
                _draw_tapered_ribbon(dc, pts, wc, (248, 214, 255, int(240 * fade)))

        # Dragon skull bursting dynamically out of top crown ring
        top_th = 2.8 * 2.0 * math.pi - spin + 2.09
        dhx = cx + math.sin(top_th) * (w * 0.25)
        dhy = base_y - h * 0.58 * height_scale + math.cos(top_th) * 18.0
        _paint_dragon_head(dd, dg, dc, dhx, dhy, 16.0 + math.cos(top_th) * 28.0, 52.0 * fade + 14.0, 0.72, fade)

        # Orbiting wind-cut shards
        for _ in range(14):
            kt = rng.uniform(0.1, 0.92)
            kth = kt * 14.0 - spin + rng.uniform(0, 6.28)
            kr = w * (0.10 + 0.26 * kt)
            _draw_spark(dc, cx + math.sin(kth) * kr, base_y - kt * h * 0.58 * height_scale,
                        kth + 1.5, rng.uniform(10.0, 22.0), 2.2, (240, 185, 255, int(215 * fade)))

        frame_img = _finalize_frame(im_d, im_g, im_c, fbm_x, fbm_y, u, warp_amp=8.5)
        frame_img.save(out_dir / f"{fi:02d}.png")


def bake_long_phong_pha_kich(out_dir: Path, fbm_x: np.ndarray, fbm_y: np.ndarray) -> None:
    """16 frames: Rising J-curve dragon surge + shattering obsidian-amethyst ground crystal spikes."""
    w, h = 512, 384
    n_frames = 16
    rng = np.random.default_rng(404)
    for fi in range(n_frames):
        u = fi / (n_frames - 1)
        im_d, dd = _new_canvas(w, h)
        im_g, dg = _new_canvas(w, h)
        im_c, dc = _new_canvas(w, h)

        fade = min(1.0, u / 0.12) * min(1.0, (1.0 - u) / 0.22)
        fade = max(0.05, fade)

        prog = min(1.0, 0.15 + u / 0.65)
        pts, wd, wg, wc = [], [], [], []
        segs = 32
        for k in range(segs + 1):
            s = (k / segs) * prog
            px = w * 0.12 + (s ** 0.88) * (w * 0.72)
            py = h * 0.80 - (s ** 1.48) * (h * 0.64)
            bell = math.sin((k / segs) * math.pi)
            pts.append((px, py))
            wd.append(44.0 * bell * fade)
            wg.append(26.0 * bell * fade)
            wc.append(10.0 * bell * fade)

        _draw_tapered_ribbon(dd, pts, wd, (24, 9, 44, int(230 * fade)))
        _draw_tapered_ribbon(dg, pts, wg, (200, 62, 255, int(225 * fade)))
        _draw_tapered_ribbon(dc, pts, wc, (250, 218, 255, int(248 * fade)))

        # Progressive eruption of jagged crystal spires along the upward cleave vector
        spike_specs = [
            (0.24, 0.81, -74.0, 42.0, 9.0, 0.08),
            (0.32, 0.78, -62.0, 62.0, 12.0, 0.14),
            (0.41, 0.74, -52.0, 84.0, 15.0, 0.20),
            (0.50, 0.70, -40.0, 74.0, 13.0, 0.26),
            (0.59, 0.65, -55.0, 108.0, 18.0, 0.34),
            (0.68, 0.60, -34.0, 94.0, 14.0, 0.42),
            (0.76, 0.56, -46.0, 118.0, 19.0, 0.48),
            (0.84, 0.53, -28.0, 76.0, 12.0, 0.55),
        ]
        for bx_f, by_f, deg_s, len_s, hw_s, delay_u in spike_specs:
            if u < delay_u:
                continue
            grow = min(1.0, (u - delay_u) / 0.16)
            _paint_crystal_spire(
                dd, dg, dc,
                w * bx_f, h * by_f,
                math.radians(deg_s), len_s * grow, hw_s, fade,
            )

        # Lunging dragon skull at apex of J-surge
        tx, ty = pts[-1]
        _paint_dragon_head(dd, dg, dc, tx, ty, -34.0, 56.0 * (0.85 + 0.2 * fade), 0.78, fade)

        for _ in range(16):
            st = rng.uniform(0.15, 0.95) * prog
            sx = w * 0.12 + (st ** 0.88) * (w * 0.72) + rng.uniform(-18, 18)
            sy = h * 0.80 - (st ** 1.48) * (h * 0.64) + rng.uniform(-18, 18)
            _draw_spark(dc, sx, sy, math.radians(-38.0), rng.uniform(14.0, 32.0), 2.5, (246, 206, 255, int(230 * fade)))

        frame_img = _finalize_frame(im_d, im_g, im_c, fbm_x, fbm_y, u, warp_amp=8.0)
        frame_img.save(out_dir / f"{fi:02d}.png")


def bake_ngu_mang_tinh_tran(out_dir: Path, fbm_x: np.ndarray, fbm_y: np.ndarray) -> None:
    """20 frames: Void Pentagram reality-cuts etching star sequentially + huge amethyst crystal cataclysm!"""
    w, h = 512, 384
    n_frames = 20
    rng = np.random.default_rng(505)
    cx, cy = w * 0.50, h * 0.53
    star_r = h * 0.36
    verts = []
    for vi in range(5):
        av = math.radians(-90.0 + vi * 72.0 + 12.0)
        verts.append((cx + math.cos(av) * star_r * 1.06, cy + math.sin(av) * star_r * 0.96))
    order = [0, 2, 4, 1, 3, 0]

    for fi in range(n_frames):
        u = fi / (n_frames - 1)
        im_d, dd = _new_canvas(w, h)
        im_g, dg = _new_canvas(w, h)
        im_c, dc = _new_canvas(w, h)

        fade = min(1.0, u / 0.10) * min(1.0, (1.0 - u) / 0.18)
        fade = max(0.05, fade)

        # Outer dark ritual seal aura ring
        ring_r = star_r * (1.08 + 0.08 * math.sin(u * math.pi))
        dd.ellipse([cx - ring_r, cy - ring_r * 0.88, cx + ring_r, cy + ring_r * 0.88], outline=(24, 8, 48, int(195 * fade)), width=10)
        dg.ellipse([cx - ring_r, cy - ring_r * 0.88, cx + ring_r, cy + ring_r * 0.88], outline=(168, 45, 240, int(180 * fade)), width=3)

        # Giant Obsidian-Amethyst crystal cataclysm erupts from beneath starting frame 8!
        cryst_grow = min(1.0, max(0.08, (u - 0.25) / 0.38))
        base_y = h * 0.86
        for ci in range(15):
            cf = (ci - 7) / 7.0
            ang_c = math.radians(-90.0 + cf * 54.0)
            len_c = (135.0 - 52.0 * abs(cf) + 22.0 * (ci % 2)) * cryst_grow
            hw_c = 17.0 - 4.0 * abs(cf)
            _paint_crystal_spire(dd, dg, dc, cx + cf * 115.0, base_y, ang_c, len_c, hw_c, fade)

        # Hovering shattered crystals ringing the outer pentagram
        if u >= 0.35:
            su = min(1.0, (u - 0.35) / 0.35)
            for si in range(8):
                ang_s = math.radians(-155.0 + si * 44.0)
                dist_s = star_r * (1.16 + 0.20 * su)
                _paint_crystal_spire(
                    dd, dg, dc,
                    cx + math.cos(ang_s) * dist_s, cy + math.sin(ang_s) * dist_s * 0.82,
                    ang_s, 42.0 * su, 7.5, fade,
                )

        # Etch 5 pentagram laser-blades sequentially over frames 1..10, blaze all 5 brightly 10..16!
        edges_lit = min(5, max(1, (fi // 2) + 1))
        for ei in range(edges_lit):
            x0, y0 = verts[order[ei]]
            x1, y1 = verts[order[ei + 1]]
            # Over-extend laser tips beyond vertices like anime blade cuts!
            dx_e, dy_e = x1 - x0, y1 - y0
            ln_e = math.hypot(dx_e, dy_e) or 1.0
            ex0, ey0 = x0 - (dx_e / ln_e) * 26.0, y0 - (dy_e / ln_e) * 26.0
            ex1, ey1 = x1 + (dx_e / ln_e) * 26.0, y1 + (dy_e / ln_e) * 26.0
            _draw_tapered_ribbon(dd, [(ex0, ey0), ((ex0 + ex1) * 0.5, (ey0 + ey1) * 0.5), (ex1, ey1)], [4.0, 15.0, 4.0], (28, 10, 54, int(235 * fade)))
            _draw_tapered_ribbon(dg, [(ex0, ey0), ((ex0 + ex1) * 0.5, (ey0 + ey1) * 0.5), (ex1, ey1)], [2.5, 9.5, 2.5], (212, 68, 255, int(240 * fade)))
            _draw_tapered_ribbon(dc, [(ex0, ey0), ((ex0 + ex1) * 0.5, (ey0 + ey1) * 0.5), (ex1, ey1)], [1.0, 3.8, 1.0], (252, 224, 255, int(252 * fade)))

        # Center Reality-Rift white-violet crossflare during peak frames 11..15!
        if 0.52 <= u <= 0.85:
            pu = math.sin(((u - 0.52) / 0.33) * math.pi)
            _draw_spark(dc, cx, cy, 0.0, 130.0 * pu, 6.0 * pu, (255, 240, 255, int(250 * pu)))
            _draw_spark(dc, cx, cy, math.pi * 0.5, 110.0 * pu, 5.5 * pu, (255, 240, 255, int(250 * pu)))
            _draw_spark(dc, cx, cy, math.radians(-38.0), 165.0 * pu, 4.5 * pu, (240, 175, 255, int(225 * pu)))

        for _ in range(14):
            _draw_spark(dc, cx + rng.uniform(-145, 145), cy + rng.uniform(-110, 95),
                        rng.uniform(0, 6.28), rng.uniform(12.0, 30.0), 2.2, (246, 200, 255, int(220 * fade)))

        frame_img = _finalize_frame(im_d, im_g, im_c, fbm_x, fbm_y, u, warp_amp=5.5, glow_radius=6.5)
        frame_img.save(out_dir / f"{fi:02d}.png")


def bake_hit_fx(out_dir: Path, n_frames: int, seed: int, fbm_x: np.ndarray, fbm_y: np.ndarray, heavy: bool = False) -> None:
    """8-10 frame high-impact HitFx sequence (`256x256`) for strike impacts."""
    w, h = 256, 256
    rng = np.random.default_rng(seed)
    cx, cy = w * 0.5, h * 0.5
    n_rays = 10 if heavy else 7
    ray_angles = [rng.uniform(0, math.tau) for _ in range(n_rays)]
    ray_lens = [rng.uniform(55.0, 108.0 if heavy else 88.0) for _ in range(n_rays)]

    for fi in range(n_frames):
        u = fi / max(1, n_frames - 1)
        im_d, dd = _new_canvas(w, h)
        im_g, dg = _new_canvas(w, h)
        im_c, dc = _new_canvas(w, h)

        fade = (1.0 - u) ** 1.15
        expand = 0.25 + u * 0.85

        # Shockwave impact ring
        rr = 20.0 + u * (88.0 if heavy else 72.0)
        dd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(32, 10, 62, int(215 * fade)), width=8)
        dg.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(215, 72, 255, int(235 * fade)), width=4)

        # Jagged diagonal impact slash cross (controlled brightness so pentagram center stays sharp!)
        c_alpha = int((185 if heavy else 235) * fade)
        g_col = (190, 200, 224, c_alpha) if seed >= 920 else (200, 58, 255, c_alpha)
        c_col = (248, 250, 255, c_alpha) if seed >= 920 else (248, 220, 255, c_alpha)
        ring_dark = (12, 12, 16, int(230 * fade)) if seed >= 920 else (32, 10, 62, int(215 * fade))
        ring_glow = (210, 220, 240, int(225 * fade)) if seed >= 920 else (215, 72, 255, int(235 * fade))
        dd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=ring_dark, width=8)
        dg.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=ring_glow, width=4)
        for ang_c in (-0.65, 0.82):
            ln = (72.0 if heavy else 64.0) * (0.6 + 0.5 * u)
            ca, sa = math.cos(ang_c), math.sin(ang_c)
            p0 = (cx - ca * ln, cy - sa * ln)
            p1 = (cx + ca * ln, cy + sa * ln)
            _draw_tapered_ribbon(dg, [p0, (cx, cy), p1], [1.4, (7.2 if heavy else 9.0) * fade, 1.4], g_col)
            _draw_tapered_ribbon(dc, [p0, (cx, cy), p1], [0.7, (2.6 if heavy else 3.8) * fade, 0.7], c_col)

        # Bursting sparks & dark smoke puffs
        for ra, rl in zip(ray_angles, ray_lens):
            dist = rl * expand * 0.45
            _draw_spark(dc, cx + math.cos(ra) * dist, cy + math.sin(ra) * dist, ra, rl * 0.42 * (1.0 - u * 0.5), 3.4 * (1.0 - u * 0.4), c_col)

        frame_img = _finalize_frame(im_d, im_g, im_c, fbm_x, fbm_y, u, warp_amp=6.5, glow_radius=5.0)
        frame_img.save(out_dir / f"{fi:02d}.png")


def _draw_ink_barb(
    draw_dark: ImageDraw.ImageDraw,
    draw_core: ImageDraw.ImageDraw,
    bx: float,
    by: float,
    angle_rad: float,
    length: float,
    curve: float,
    width: float,
    fade: float,
) -> None:
    """Draws a sharp curved black-ink thorn tendril with subtle silver-white rim highlight."""
    pts: List[Tuple[float, float]] = []
    ws: List[float] = []
    for k in range(8):
        s = k / 7.0
        a = angle_rad + curve * s
        dist = length * s
        pts.append((bx + math.cos(a) * dist, by + math.sin(a) * dist))
        ws.append(max(0.5, width * ((1.0 - s) ** 0.8)))
    _draw_tapered_ribbon(draw_dark, pts, ws, (10, 10, 14, int(240 * fade)))
    _draw_tapered_ribbon(draw_core, pts[:5], [w * 0.24 for w in ws[:5]], (225, 232, 246, int(190 * fade)))


def _draw_ink_ribbon_layered(
    dd: ImageDraw.ImageDraw,
    dg: ImageDraw.ImageDraw,
    dc: ImageDraw.ImageDraw,
    pts: List[Tuple[float, float]],
    widths: List[float],
    fade: float,
) -> None:
    """Renders sumi-e ink blade arc: broad charcoal halo + crisp pitch-black ink body + stark silver rim."""
    _draw_tapered_ribbon(dd, pts, [w * 1.18 for w in widths], (14, 14, 20, int(238 * fade)))
    _draw_tapered_ribbon(dg, pts, [w * 0.72 for w in widths], (52, 56, 70, int(205 * fade)))
    # Offset crisp silver-white highlight along top edge of arc
    rim_pts = [(px, py - max(1.0, widths[i] * 0.34)) for i, (px, py) in enumerate(pts)]
    _draw_tapered_ribbon(dc, rim_pts, [w * 0.16 for w in widths], (238, 244, 255, int(240 * fade)))


def bake_hac_nhat_tram(out_dir: Path, fbm_x: np.ndarray, fbm_y: np.ndarray) -> None:
    """16 frames: Form 1 — Tilted horizontal black-ink orbital slash ring + thorny tendrils + silver rim."""
    w, h = 512, 384
    n_frames = 16
    rng = np.random.default_rng(601)
    for fi in range(n_frames):
        u = fi / (n_frames - 1)
        im_d, dd = _new_canvas(w, h)
        im_g, dg = _new_canvas(w, h)
        im_c, dc = _new_canvas(w, h)

        fade = max(0.05, min(1.0, u / 0.12) * min(1.0, (1.0 - u) / 0.20))
        sweep = min(1.0, max(0.10, u / 0.65))
        trail = max(0.0, (u - 0.52) / 0.48)
        cx, cy = w * 0.50, h * 0.56
        rx, ry = w * 0.38, h * 0.12
        tilt = math.radians(-16.0)
        ct, st = math.cos(tilt), math.sin(tilt)

        ang0 = math.radians(170.0 - trail * 130.0)
        ang1 = math.radians(170.0 - sweep * 335.0)
        pts, ws = [], []
        for k in range(38):
            s = k / 37.0
            th = ang0 + (ang1 - ang0) * s
            lx, ly = math.cos(th) * rx, math.sin(th) * ry
            pts.append((cx + lx * ct - ly * st, cy + lx * st + ly * ct))
            ws.append(24.0 * math.sin(s * math.pi) * (1.0 - trail * 0.5) * fade + 3.0)
        _draw_ink_ribbon_layered(dd, dg, dc, pts, ws, fade)

        # Thorny curling black ink tendrils bursting outward along ring
        for b_i in range(12):
            bt = b_i / 11.0
            if bt > sweep:
                continue
            th = ang0 + (ang1 - ang0) * bt
            lx, ly = math.cos(th) * rx, math.sin(th) * ry
            bx, by = cx + lx * ct - ly * st, cy + lx * st + ly * ct
            _draw_ink_barb(dd, dc, bx, by, th + tilt, 28.0 + 18.0 * (b_i % 2), 0.75 * (-1 if b_i % 2 else 1), 6.5, fade)

        # Pale silver ink droplets trailing the cut
        for _ in range(14):
            dt_r = rng.uniform(0.05, sweep)
            th = ang0 + (ang1 - ang0) * dt_r
            lx, ly = math.cos(th) * rx * rng.uniform(0.92, 1.15), math.sin(th) * ry * rng.uniform(0.9, 1.2)
            _draw_spark(dc, cx + lx * ct - ly * st, cy + lx * st + ly * ct, th + math.pi * 0.5, rng.uniform(8.0, 22.0), 1.8, (238, 244, 255, int(225 * fade)))

        frame_img = _finalize_frame(im_d, im_g, im_c, fbm_x, fbm_y, u, warp_amp=7.0, glow_radius=4.5)
        frame_img.save(out_dir / f"{fi:02d}.png")


def _draw_four_point_star(
    draw_core: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    arm_x: float,
    arm_y: float,
    waist: float,
    rgba: Tuple[int, int, int, int],
) -> None:
    """Draws a crisp 4-point Cosmic Void cross-star flare."""
    pts = [
        (cx, cy - arm_y),
        (cx + waist, cy - waist),
        (cx + arm_x, cy),
        (cx + waist, cy + waist),
        (cx, cy + arm_y),
        (cx - waist, cy + waist),
        (cx - arm_x, cy),
        (cx - waist, cy - waist),
    ]
    draw_core.polygon(pts, fill=rgba)


def bake_thai_hu_tram_ba(out_dir: Path, fbm_x: np.ndarray, fbm_y: np.ndarray) -> None:
    """16 frames: Form 2 — Ranged Cosmic-Void crescent missile slash wave flying into chest-high impact burst."""
    w, h = 512, 384
    n_frames = 16
    rng = np.random.default_rng(602)
    for fi in range(n_frames):
        u = fi / (n_frames - 1)
        im_d, dd = _new_canvas(w, h)
        im_g, dg = _new_canvas(w, h)
        im_c, dc = _new_canvas(w, h)

        fade = max(0.05, min(1.0, u / 0.10) * min(1.0, (1.0 - u) / 0.16))
        cy = h * 0.54

        # Phase A (u = 0.0..0.38): Launch slash wave muzzle flash at caster sword (left)
        if u <= 0.42:
            lu = min(1.0, u / 0.42)
            l_fade = math.sin(lu * math.pi)
            lx0, ly0 = w * 0.18, cy
            m_pts = [
                (lx0 - 18.0, ly0 - 76.0 * (0.4 + 0.6 * lu)),
                (lx0 + 18.0, ly0),
                (lx0 - 14.0, ly0 + 72.0 * (0.4 + 0.6 * lu)),
            ]
            _draw_ink_ribbon_layered(dd, dg, dc, m_pts, [4.0, 18.0 * l_fade, 4.0], l_fade)
            _draw_four_point_star(dc, lx0 + 8.0, ly0, 32.0 * l_fade, 44.0 * l_fade, 4.5, (245, 250, 255, int(235 * l_fade)))

        # Phase B (u = 0.08..0.76): Streamlined flying black-void crescent missile wave rushing left -> dummy!
        if 0.06 <= u <= 0.80:
            fly = min(1.0, max(0.0, (u - 0.06) / 0.56))
            fly_fade = min(1.0, (u - 0.06) / 0.10) * min(1.0, (0.80 - u) / 0.16)
            fly_fade = max(0.05, fly_fade)
            nose_x = w * (0.24 + fly * 0.42)
            tail_x = max(w * 0.08, nose_x - w * 0.42)

            # Aerodynamic hooked dark void missile silhouette + long tapering wispy ink tail
            top_pts, bot_pts = [], []
            for k in range(28):
                s = k / 27.0  # 0 = tail tip, 1 = nose tip
                px = tail_x + (nose_x - tail_x) * s
                thick = (s ** 1.40) * math.sin(min(1.0, s * 0.96) * math.pi * 0.58) * 42.0
                wave_y = math.sin(s * 7.5 - u * 11.0) * (1.0 - s) * 8.0
                top_pts.append((px, cy + wave_y - thick * 0.85))
                bot_pts.append((px, cy + wave_y + thick * 0.45))
            hook_nose = (nose_x + 22.0, cy - 2.0)
            missile_poly = top_pts + [hook_nose] + list(reversed(bot_pts))
            dd.polygon(missile_poly, fill=(10, 10, 15, int(245 * fly_fade)))
            # Inner dense silver-slate luminous nebula core inside the void crescent wave
            inner_poly = [((px + nose_x * 0.25) / 1.25, (py + cy * 0.25) / 1.25) for px, py in top_pts[10:]] + [(nose_x + 8.0, cy - 1.0)] + [((px + nose_x * 0.25) / 1.25, (py + cy * 0.25) / 1.25) for px, py in reversed(bot_pts[10:])]
            dg.polygon(missile_poly, fill=(68, 76, 104, int(135 * fly_fade)), outline=(205, 216, 240, int(225 * fly_fade)))
            if len(inner_poly) >= 3:
                dg.polygon(inner_poly, fill=(118, 132, 168, int(145 * fly_fade)))

            # Stark silver-white leading nose bevel + inner void crackle stars
            _draw_tapered_ribbon(dc, top_pts[8:] + [hook_nose], [2.8] * len(top_pts[8:]) + [1.2], (244, 248, 255, int(248 * fly_fade)))
            _draw_tapered_ribbon(dc, bot_pts[14:] + [hook_nose], [1.8] * len(bot_pts[14:]) + [1.0], (218, 228, 248, int(195 * fly_fade)))
            for s_i in range(12):
                st = 0.25 + (s_i / 11.0) * 0.70
                sx = tail_x + (nose_x - tail_x) * st + rng.uniform(-8, 8)
                sy = cy + rng.uniform(-12, 8) * st
                _draw_four_point_star(dc, sx, sy, 6.0 + 5.0 * st, 6.0 + 5.0 * st, 1.5, (245, 250, 255, int(225 * fly_fade)))
            _draw_ink_barb(dd, dc, nose_x - 36.0, cy - 18.0, math.radians(-162.0), 42.0, -0.35, 6.0, fly_fade)
            _draw_ink_barb(dd, dc, nose_x - 44.0, cy + 12.0, math.radians(164.0), 38.0, 0.30, 5.5, fly_fade)

        # Phase C (u = 0.46..1.0): Chest-high Cosmic Void Starburst dead-center on Dummy (w*0.70)!
        if u >= 0.46:
            iu = (u - 0.46) / 0.54
            ifade = math.sin(min(1.0, iu / 0.20) * math.pi * 0.5) * min(1.0, (1.0 - iu) / 0.35)
            ifade = max(0.05, ifade)
            ix, iy = w * 0.655, cy
            rad_d = 34.0 + iu * 44.0
            # Dense dark ink puff + soft silver mist aura behind 4-point Cosmic Star
            dd.ellipse([ix - rad_d * 1.15, iy - rad_d * 1.15, ix + rad_d * 1.15, iy + rad_d * 1.15], fill=(8, 8, 12, int(225 * ifade)))
            dg.ellipse([ix - rad_d * 1.25, iy - rad_d * 1.25, ix + rad_d * 1.25, iy + rad_d * 1.25], fill=(125, 138, 175, int(145 * ifade)), outline=(235, 242, 255, int(225 * ifade)), width=4)
            dc.ellipse([ix - 24.0, iy - 24.0, ix + 24.0, iy + 24.0], fill=(248, 252, 255, int(175 * ifade)))
            _draw_four_point_star(dc, ix, iy, 74.0 * (1.0 - 0.18 * iu), 54.0 * (1.0 - 0.18 * iu), 8.5, (254, 255, 255, int(252 * ifade)))
            for t_i in range(7):
                ta = math.radians(-155.0 + t_i * 52.0 + iu * 16.0)
                td = 42.0 + iu * 36.0
                tx, ty = ix + math.cos(ta) * td, iy + math.sin(ta) * td
                _draw_spark(dc, tx, ty, ta, 18.0, 4.8, (242, 248, 255, int(235 * ifade)))

        frame_img = _finalize_frame(im_d, im_g, im_c, fbm_x, fbm_y, u, warp_amp=5.8, glow_radius=4.8)
        frame_img.save(out_dir / f"{fi:02d}.png")


def bake_hac_giap_ho_the(out_dir: Path, fbm_x: np.ndarray, fbm_y: np.ndarray) -> None:
    """18 frames: Form 3 — Protective Cosmic-Void Nova Shield Dome + obsidian claw petals wrapping caster!"""
    w, h = 512, 384
    n_frames = 18
    rng = np.random.default_rng(603)
    cx = w * 0.50
    base_y = h * 0.77
    dome_rx, dome_ry = w * 0.31, h * 0.44
    for fi in range(n_frames):
        u = fi / (n_frames - 1)
        im_d, dd = _new_canvas(w, h)
        im_g, dg = _new_canvas(w, h)
        im_c, dc = _new_canvas(w, h)

        fade = max(0.05, min(1.0, u / 0.14) * min(1.0, (1.0 - u) / 0.20))
        open_env = min(1.0, 0.35 + u * 2.2)

        # 1) Concentric silver-white & ink ground shockwave rings under caster feet
        for ring_k, scale_r in enumerate((1.0, 1.24)):
            rrx = dome_rx * (1.02 + 0.14 * math.sin(u * math.pi * 2.0)) * scale_r
            rry = h * (0.085 if ring_k == 0 else 0.105)
            dd.ellipse([cx - rrx, base_y - rry, cx + rrx, base_y + rry], outline=(12, 12, 18, int(215 * fade)), width=8)
            dg.ellipse([cx - rrx, base_y - rry, cx + rrx, base_y + rry], outline=(235, 242, 255, int((225 if ring_k == 0 else 155) * fade)), width=3)

        # 2) Hemispherical translucent Cosmic-Void barrier shell (leaves interior readable so Pawn shines inside!)
        cr_x = dome_rx * open_env
        cr_y = dome_ry * open_env
        dome_pts: List[Tuple[float, float]] = []
        for k in range(37):
            th = math.radians(-180.0 + (k / 36.0) * 180.0)
            dome_pts.append((cx + math.cos(th) * cr_x, base_y + math.sin(th) * cr_y))
        dome_pts.extend([(cx + cr_x * 0.94, base_y + 12.0), (cx - cr_x * 0.94, base_y + 12.0)])
        dg.polygon(dome_pts, fill=(48, 54, 72, int(92 * fade)), outline=(238, 245, 255, int(235 * fade)))
        # Crisp bright outer dome arc rib
        _draw_tapered_ribbon(dc, dome_pts[:37], [3.6 * math.sin((k / 36.0) * math.pi) + 1.4 for k in range(37)], (246, 250, 255, int(245 * fade)))

        # 3) Cracked crystal barrier fracture seams along shell shoulders + dark ink aura crown inside dome
        crack_chains = [
            [(-0.82, -0.25), (-0.64, -0.42), (-0.72, -0.58), (-0.48, -0.74), (-0.28, -0.66)],
            [(0.78, -0.28), (0.60, -0.48), (0.68, -0.64), (0.42, -0.80)],
            [(-0.46, -0.30), (-0.24, -0.44), (-0.18, -0.66)],
        ]
        for chain in crack_chains:
            cpts = [(cx + px * cr_x, base_y + py * cr_y) for px, py in chain]
            dc.line(cpts, fill=(235, 242, 255, int(195 * fade)), width=2)

        # 4) Smooth curved tapering Black-Ink Claw Petals hugging the dome ("NOVA HIGH")
        for side_s, ang_a, ang_b in [(-1.0, -184.0, -116.0), (1.0, 4.0, -64.0)]:
            p_outer, p_inner = [], []
            for k in range(22):
                s = k / 21.0
                th = math.radians(ang_a + (ang_b - ang_a) * s)
                thick = (1.0 - s) ** 0.78 * 0.16 * (0.65 + 0.35 * math.sin(s * math.pi))
                ro_x = cr_x * (1.06 + thick * 0.4)
                ro_y = cr_y * (1.06 + thick * 0.4)
                ri_x = cr_x * (1.06 - thick * 1.15)
                ri_y = cr_y * (1.06 - thick * 1.15)
                p_outer.append((cx + math.cos(th) * ro_x, base_y + math.sin(th) * ro_y))
                p_inner.append((cx + math.cos(th) * ri_x, base_y + math.sin(th) * ri_y))
            claw_poly = p_outer + list(reversed(p_inner))
            dd.polygon(claw_poly, fill=(10, 10, 14, int(242 * fade)))
            _draw_tapered_ribbon(dc, p_outer, [2.2 * (1.0 - (k / 21.0) * 0.6) for k in range(22)], (232, 240, 255, int(220 * fade)))

        # 5) Subtle floating starlight flecks & top crest 4-point Void Star above helmet
        _draw_four_point_star(dc, cx, base_y - cr_y * 0.92, 24.0, 18.0, 3.2, (250, 252, 255, int(235 * fade)))
        for _ in range(14):
            ang_f = rng.uniform(-math.pi * 0.95, -0.05)
            rf = rng.uniform(0.55, 1.08)
            fx = cx + math.cos(ang_f) * cr_x * rf
            fy = base_y + math.sin(ang_f) * cr_y * rf
            _draw_four_point_star(dc, fx, fy, 4.5, 4.5, 1.2, (242, 248, 255, int(215 * fade)))

        frame_img = _finalize_frame(im_d, im_g, im_c, fbm_x, fbm_y, u, warp_amp=4.5, glow_radius=5.2)
        frame_img.save(out_dir / f"{fi:02d}.png")


def bake_le_anh_pha_toai(out_dir: Path, fbm_x: np.ndarray, fbm_y: np.ndarray) -> None:
    """16 frames: Form 4 — Jagged obsidian shadow ground spikes + 5 overlapping sweeping ink crescents."""
    w, h = 512, 384
    n_frames = 16
    rng = np.random.default_rng(604)
    for fi in range(n_frames):
        u = fi / (n_frames - 1)
        im_d, dd = _new_canvas(w, h)
        im_g, dg = _new_canvas(w, h)
        im_c, dc = _new_canvas(w, h)

        fade = max(0.05, min(1.0, u / 0.12) * min(1.0, (1.0 - u) / 0.20))

        # Erupting pitch-black thorny shadow spikes across floor (left -> right) with full silver rims
        spike_xs = [0.20, 0.29, 0.39, 0.49, 0.59, 0.69, 0.79]
        spike_hs = [58.0, 82.0, 74.0, 102.0, 126.0, 94.0, 112.0]
        base_y = h * 0.84
        for idx_sp, (xf, sh) in enumerate(zip(spike_xs, spike_hs)):
            if u < idx_sp * 0.04:
                continue
            gr = min(1.0, (u - idx_sp * 0.04) / 0.16)
            sx = w * xf
            sh_c = sh * gr
            sp_poly = [(sx - 24.0, base_y), (sx - 6.0, base_y - sh_c * 0.55), (sx + 4.0, base_y - sh_c), (sx + 22.0, base_y)]
            dd.polygon(sp_poly, fill=(10, 10, 14, int(244 * fade)))
            dg.polygon(sp_poly, outline=(190, 200, 224, int(215 * fade)))
            _draw_tapered_ribbon(dc, [(sx - 18.0, base_y - 4.0), (sx - 6.0, base_y - sh_c * 0.55), (sx + 4.0, base_y - sh_c)], [2.0, 3.2, 1.0], (238, 245, 255, int(235 * fade)))
            _draw_tapered_ribbon(dc, [(sx + 4.0, base_y - sh_c), (sx + 18.0, base_y - 6.0)], [1.2, 2.2], (205, 215, 238, int(185 * fade)))

        # 5 overlapping forward-sweeping black-ink slash blades cutting across mid-air!
        for sl_i in range(5):
            delay = sl_i * 0.07
            if u < delay:
                continue
            su = min(1.0, (u - delay) / 0.42)
            ox = w * (0.28 + sl_i * 0.085)
            oy = h * (0.50 - sl_i * 0.025)
            pts, ws = [], []
            for k in range(24):
                s = k / 23.0
                th = math.radians(-110.0 + s * 190.0 * su)
                pts.append((ox + math.cos(th) * (w * 0.17), oy + math.sin(th) * (h * 0.28)))
                ws.append(22.0 * math.sin(s * math.pi) * fade + 2.0)
            _draw_ink_ribbon_layered(dd, dg, dc, pts, ws, fade)

        frame_img = _finalize_frame(im_d, im_g, im_c, fbm_x, fbm_y, u, warp_amp=6.5, glow_radius=4.5)
        frame_img.save(out_dir / f"{fi:02d}.png")


def bake_huyet_nguyet_vo_anh(out_dir: Path, fbm_x: np.ndarray, fbm_y: np.ndarray) -> None:
    """20 frames: Form 5 — Massive intersecting 3D spherical black-ink eclipse rings + radiant white-silver core."""
    w, h = 512, 384
    n_frames = 20
    rng = np.random.default_rng(605)
    cx, cy = w * 0.50, h * 0.52
    for fi in range(n_frames):
        u = fi / (n_frames - 1)
        im_d, dd = _new_canvas(w, h)
        im_g, dg = _new_canvas(w, h)
        im_c, dc = _new_canvas(w, h)

        fade = max(0.05, min(1.0, u / 0.10) * min(1.0, (1.0 - u) / 0.18))
        # Dark void eclipse orb glow in background
        orb_r = 68.0 * (0.6 + 0.45 * math.sin(u * math.pi))
        dd.ellipse([cx - orb_r, cy - orb_r, cx + orb_r, cy + orb_r], fill=(8, 8, 12, int(215 * fade)))
        dg.ellipse([cx - orb_r, cy - orb_r, cx + orb_r, cy + orb_r], outline=(220, 228, 245, int(205 * fade)), width=4)

        # 4 gigantic intersecting 3D black-ink orbital slash rings spinning across the sphere
        rings = [
            (0.0, 26.0, 155.0, 62.0),
            (0.10, -34.0, 162.0, 56.0),
            (0.20, 68.0, 148.0, 50.0),
            (0.32, 4.0, 172.0, 44.0),
        ]
        for delay, tilt_d, rx, ry in rings:
            if u < delay:
                continue
            su = min(1.0, (u - delay) / 0.36)
            tl = math.radians(tilt_d + u * 22.0)
            ct, st = math.cos(tl), math.sin(tl)
            pts, ws = [], []
            for k in range(36):
                s = k / 35.0
                th = math.radians(-165.0 + s * 320.0 * su)
                lx, ly = math.cos(th) * rx, math.sin(th) * ry
                pts.append((cx + lx * ct - ly * st, cy + lx * st + ly * ct))
                ws.append(24.0 * math.sin(s * math.pi) * fade + 3.0)
            _draw_ink_ribbon_layered(dd, dg, dc, pts, ws, fade)
            _draw_ink_barb(dd, dc, pts[-1][0], pts[-1][1], tl, 38.0, 0.9, 8.0, fade)

        # Radiant pale silver-white eclipse crossflare in peak frames
        if 0.45 <= u <= 0.88:
            pu = math.sin(((u - 0.45) / 0.43) * math.pi)
            _draw_spark(dc, cx, cy, 0.0, 145.0 * pu, 6.0 * pu, (250, 252, 255, int(248 * pu)))
            _draw_spark(dc, cx, cy, math.pi * 0.5, 118.0 * pu, 5.2 * pu, (250, 252, 255, int(248 * pu)))

        for _ in range(16):
            ang_p = rng.uniform(0, math.tau)
            dist_p = rng.uniform(45.0, 165.0)
            _draw_ink_barb(dd, dc, cx + math.cos(ang_p) * dist_p, cy + math.sin(ang_p) * dist_p * 0.72,
                           ang_p, rng.uniform(20.0, 38.0), 0.7, 5.0, fade * 0.85)

        frame_img = _finalize_frame(im_d, im_g, im_c, fbm_x, fbm_y, u, warp_amp=7.0, glow_radius=5.5)
        frame_img.save(out_dir / f"{fi:02d}.png")


def bake_all_skillfx(skillfx_root: Path = DEFAULT_SKILLFX_ROOT, only_ink: bool = False) -> dict[str, int]:
    """Bakes all Skullblade + Trấn Ác Inkblade SkillFx & HitFx PNG sequences. Returns frame count map."""
    fbm_x, fbm_y = build_fbm_pair(384, 512, seed=777)
    hit_x, hit_y = build_fbm_pair(256, 256, seed=888)

    skull_specs = [
        ("PhongLongTram", 16, bake_phong_long_tram),
        ("BaoTocAnhBo", 16, bake_bao_toc_anh_bo),
        ("LongQuyenTanAnh", 18, bake_long_quyen_tan_anh),
        ("LongPhongPhaKich", 16, bake_long_phong_pha_kich),
        ("NguMangTinhTran", 20, bake_ngu_mang_tinh_tran),
    ]
    ink_specs = [
        ("HacNhatTram", 16, bake_hac_nhat_tram),
        ("ThaiHuTramBa", 16, bake_thai_hu_tram_ba),
        ("HacGiapHoThe", 18, bake_hac_giap_ho_the),
        ("LeAnhPhaToai", 16, bake_le_anh_pha_toai),
        ("HuyetNguyetVoAnh", 20, bake_huyet_nguyet_vo_anh),
    ]
    specs = ink_specs if only_ink else (skull_specs + ink_specs)

    counts: dict[str, int] = {}
    for folder, n_f, fn in specs:
        target = skillfx_root / folder
        target.mkdir(parents=True, exist_ok=True)
        fn(target, fbm_x, fbm_y)
        counts[folder] = n_f

    skull_hits = [
        ("PhongLongTramHit", 8, 911, False),
        ("BaoTocAnhBoHit", 8, 912, False),
        ("LongQuyenTanAnhHit", 8, 913, False),
        ("LongPhongPhaKichHit", 8, 914, True),
        ("NguMangTinhTranHit", 10, 915, True),
    ]
    ink_hits = [
        ("HacNhatTramHit", 8, 921, False),
        ("ThaiHuTramBaHit", 8, 922, False),
        ("HacGiapHoTheHit", 8, 923, False),
        ("LeAnhPhaToaiHit", 8, 924, True),
        ("HuyetNguyetVoAnhHit", 10, 925, True),
    ]
    hit_specs = ink_hits if only_ink else (skull_hits + ink_hits)

    for folder, n_f, seed, heavy in hit_specs:
        target = skillfx_root / folder
        target.mkdir(parents=True, exist_ok=True)
        bake_hit_fx(target, n_f, seed, hit_x, hit_y, heavy=heavy)
        counts[folder] = n_f

    return counts


if __name__ == "__main__":
    import sys
    only_ink_flag = "--ink" in sys.argv
    res = bake_all_skillfx(only_ink=only_ink_flag)
    total = sum(res.values())
    print(f"Baked {total} painterly SkillFx/HitFx frames across {len(res)} folders: {res}")
