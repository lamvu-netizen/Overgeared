"""
Fast image processing & part-splitting utilities:
- Background removal (corner auto-detect, eyedropper color-key, flood-fill magic wand)
- Auto-detect disconnected sprite islands (BFS connected components)
- Smart 4-zone weapon auto-slicer (Head / Guard / Grip / Pommel cut lines)
- Crop, polygon lasso cut, trim + 2px transparent border (matching ExpandedParts.cs)
- Head socket X & Center socket preview calculation
"""
from __future__ import annotations

from collections import deque
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image


def remove_background_color(
    img: Image.Image,
    key_rgb: Optional[Tuple[int, int, int]] = None,
    tolerance: int = 35,
    softness: int = 12,
    contiguous_only: bool = True,
    seed_xy: Optional[Tuple[int, int]] = None,
) -> Image.Image:
    """Removes background by color similarity (flood-fill from borders/seed or global)."""
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba, dtype=np.float32).copy()
    h, w, _ = arr.shape

    if key_rgb is None:
        # Sample 4 corners and pick median
        corners = np.array([
            arr[0, 0, :3],
            arr[0, w - 1, :3],
            arr[h - 1, 0, :3],
            arr[h - 1, w - 1, :3],
        ])
        key = np.median(corners, axis=0)
    else:
        key = np.array(key_rgb, dtype=np.float32)

    dist = np.sqrt(np.sum((arr[:, :, :3] - key[None, None, :]) ** 2, axis=2))
    tol = float(max(1, tolerance))
    soft = float(max(0, softness))

    if contiguous_only:
        visited = np.zeros((h, w), dtype=bool)
        bg_mask = np.zeros((h, w), dtype=bool)
        q: deque[Tuple[int, int]] = deque()
        if seed_xy is not None:
            sx, sy = max(0, min(w - 1, seed_xy[0])), max(0, min(h - 1, seed_xy[1]))
            if dist[sy, sx] <= tol + soft:
                visited[sy, sx] = True
                q.append((sx, sy))
        else:
            for x in range(w):
                for y in (0, h - 1):
                    if not visited[y, x] and dist[y, x] <= tol:
                        visited[y, x] = True
                        q.append((x, y))
            for y in range(h):
                for x in (0, w - 1):
                    if not visited[y, x] and dist[y, x] <= tol:
                        visited[y, x] = True
                        q.append((x, y))

        thresh = tol + soft
        while q:
            cx, cy = q.popleft()
            bg_mask[cy, cx] = True
            for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                if 0 <= nx < w and 0 <= ny < h and not visited[ny, nx]:
                    if dist[ny, nx] <= thresh:
                        visited[ny, nx] = True
                        q.append((nx, ny))

        alpha_factor = np.ones((h, w), dtype=np.float32)
        if soft > 0:
            edge_alpha = np.clip((dist - tol) / soft, 0.0, 1.0)
            alpha_factor = np.where(bg_mask, edge_alpha, 1.0)
        else:
            alpha_factor = np.where(bg_mask, 0.0, 1.0)
    else:
        if soft > 0:
            alpha_factor = np.clip((dist - tol) / soft, 0.0, 1.0)
        else:
            alpha_factor = (dist > tol).astype(np.float32)

    arr[:, :, 3] = arr[:, :, 3] * alpha_factor
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def trim_and_pad(img: Image.Image, pad: int = 2, alpha_thresh: int = 16, target_max_dim: int = 0) -> Image.Image:
    """Trims transparent borders and adds 2px margin (matching ExpandedParts.cs)."""
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba)
    ys, xs = np.where(arr[:, :, 3] > alpha_thresh)
    if len(ys) == 0:
        return rgba
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    cropped = rgba.crop((x0, y0, x1, y1))

    if target_max_dim > 0:
        cw, ch = cropped.size
        scale = min(1.0, target_max_dim / max(cw, ch))
        if scale < 1.0:
            cropped = cropped.resize((max(1, int(round(cw * scale))), max(1, int(round(ch * scale)))), Image.Resampling.LANCZOS)

    cw, ch = cropped.size
    out = Image.new("RGBA", (cw + pad * 2, ch + pad * 2), (0, 0, 0, 0))
    out.paste(cropped, (pad, pad))
    return out


def suggest_weapon_split_lines(img: Image.Image) -> Tuple[int, int, int]:
    """
    Analyzes vertical width profile of an upright weapon image and suggests
    3 horizontal Y cut lines: (head_guard_y, guard_grip_y, grip_pommel_y).
    """
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba)
    h, w, _ = arr.shape
    opaque = arr[:, :, 3] > 32
    ys = np.where(np.any(opaque, axis=1))[0]
    if len(ys) < 20:
        return (int(h * 0.48), int(h * 0.56), int(h * 0.86))
    top_y, bot_y = int(ys[0]), int(ys[-1])
    span = bot_y - top_y
    row_widths = np.sum(opaque, axis=1).astype(np.float32)

    # Guard is usually a local width spike in the middle region (35%..72% from top)
    g_start = top_y + int(span * 0.30)
    g_end = top_y + int(span * 0.72)
    if g_end > g_start + 4:
        guard_peak_y = g_start + int(np.argmax(row_widths[g_start:g_end]))
        peak_w = row_widths[guard_peak_y]
        # Walk up/down until width drops below 45% of peak
        cut1 = guard_peak_y
        while cut1 > top_y + int(span * 0.15) and row_widths[cut1] > peak_w * 0.45:
            cut1 -= 1
        cut2 = guard_peak_y
        while cut2 < bot_y - int(span * 0.12) and row_widths[cut2] > peak_w * 0.45:
            cut2 += 1
        if cut2 - cut1 < max(6, int(span * 0.03)):
            cut1 = max(top_y + 10, guard_peak_y - int(span * 0.04))
            cut2 = min(bot_y - 10, guard_peak_y + int(span * 0.04))
    else:
        cut1 = top_y + int(span * 0.48)
        cut2 = top_y + int(span * 0.56)

    cut3 = max(cut2 + 8, bot_y - int(span * 0.13))
    return (int(cut1), int(cut2), int(cut3))


def detect_sprite_islands(img: Image.Image, min_area: int = 80, alpha_thresh: int = 24) -> List[Tuple[int, int, int, int]]:
    """Finds bounding boxes (x, y, w, h) of disconnected non-transparent islands."""
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba)
    h, w, _ = arr.shape
    mask = arr[:, :, 3] > alpha_thresh
    visited = np.zeros((h, w), dtype=bool)
    boxes: List[Tuple[int, int, int, int]] = []

    ys, xs = np.where(mask)
    for sy, sx in zip(ys.tolist(), xs.tolist()):
        if visited[sy, sx]:
            continue
        q: deque[Tuple[int, int]] = deque([(sx, sy)])
        visited[sy, sx] = True
        min_x = max_x = sx
        min_y = max_y = sy
        count = 0
        while q:
            cx, cy = q.popleft()
            count += 1
            if cx < min_x:
                min_x = cx
            if cx > max_x:
                max_x = cx
            if cy < min_y:
                min_y = cy
            if cy > max_y:
                max_y = cy
            for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                if 0 <= nx < w and 0 <= ny < h and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    q.append((nx, ny))
        if count >= min_area:
            boxes.append((min_x, min_y, max_x - min_x + 1, max_y - min_y + 1))

    boxes.sort(key=lambda b: (b[1] // 64, b[0]))
    return boxes


def crop_polygon_mask(img: Image.Image, points: List[Tuple[float, float]]) -> Image.Image:
    """Extracts a region defined by polygon vertices [(x, y), ...] with transparent outside."""
    from PIL import ImageDraw
    rgba = img.convert("RGBA")
    mask = Image.new("L", rgba.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon([(float(x), float(y)) for x, y in points], fill=255)
    out = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    out.paste(rgba, (0, 0), mask)
    return trim_and_pad(out, pad=2)


def estimate_head_socket_x(pil_img: Image.Image) -> float:
    """Computes ExpandedParts.HeadSocket X ratio (0..1) near the bottom edge of a head sprite."""
    arr = np.asarray(pil_img.convert("RGBA"))
    h, w, _ = arr.shape
    if h < 5 or w < 3:
        return 0.5
    # ExpandedParts uses bottom-up scan_y = round(h * 0.045), clamped [2, h - 3]
    bu_y = max(2, min(h - 3, round(h * 0.045)))
    td_y = h - 1 - bu_y
    opaque_xs = np.where(arr[td_y, :, 3] > 128)[0]
    if len(opaque_xs) > 0:
        return float(np.mean(opaque_xs + 0.5) / w)
    return 0.5
