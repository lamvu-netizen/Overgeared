"""
Interactive Image Importer & Fast Part Splitter Studio for Overgeared (1.7).
Supports:
- Drag & Drop / File Open / Ctrl+V Clipboard paste
- Magic Wand background removal + Auto Corner BG removal + Eraser/Restore Brush
- 4-Zone Weapon Slicer (3 draggable cut lines -> extract Head/Guard/Grip/Pommel at once)
- Box Crop + Auto-Detect Sprite Islands
- Polygon / Lasso freehand cut
- Live Socket X alignment preview, "Test in Forge", and "Save to Mod (1.7)"
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from exporter import save_part_to_mod, update_language_xml
from mod_data import KINDS_VI, ModAssetStore, PART_CATEGORIES, PART_CATEGORY_LABELS
from splitter import (
    crop_polygon_mask,
    detect_sprite_islands,
    estimate_head_socket_x,
    remove_background_color,
    suggest_weapon_split_lines,
    trim_and_pad,
)
from theme import pil_to_qpixmap


@dataclass
class ExtractedPart:
    label: str
    image: Image.Image
    suggested_category: str = "head"
    socket_x: float = 0.5


class SplitterCanvas(QWidget):
    """Zoomable, pannable, interactive canvas for cutting & cleaning weapon images."""
    partExtracted = Signal(object)       # ExtractedPart
    multiExtracted = Signal(list)        # List[ExtractedPart]
    imageModified = Signal()

    MODE_SLICER = 0
    MODE_BOX = 1
    MODE_LASSO = 2
    MODE_WAND = 3
    MODE_ERASER = 4
    MODE_RESTORE = 5

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(460, 420)

        self.orig_img: Optional[Image.Image] = None
        self.work_img: Optional[Image.Image] = None
        self._pixmap: Optional[QPixmap] = None
        self._undo_stack: List[Image.Image] = []
        self._redo_stack: List[Image.Image] = []

        self.mode: int = self.MODE_SLICER
        self.zoom: float = 1.0
        self.pan: QPointF = QPointF(0, 0)
        self._panning: bool = False
        self._pan_start: QPointF = QPointF(0, 0)

        # Slicer Y lines in image coords
        self.cut_lines: List[float] = [120.0, 160.0, 260.0]
        self._drag_line_idx: int = -1

        # Box select / detected islands
        self.box_start: Optional[QPointF] = None
        self.box_rect: Optional[QRectF] = None
        self.detected_boxes: List[Tuple[int, int, int, int]] = []
        self.hovered_box_idx: int = -1

        # Lasso points
        self.lasso_points: List[QPointF] = []
        self._mouse_img_pos: Optional[QPointF] = None

        # Wand & Brush params
        self.wand_tolerance: int = 36
        self.wand_softness: int = 10
        self.wand_contiguous: bool = True
        self.brush_radius: int = 12
        self._brushing: bool = False
        self._last_brush_pt: Optional[Tuple[float, float]] = None

    def load_image(self, img: Image.Image) -> None:
        rgba = img.convert("RGBA")
        self.orig_img = rgba.copy()
        self.work_img = rgba.copy()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.detected_boxes.clear()
        self.box_rect = None
        self.lasso_points.clear()
        self._refresh_pixmap()
        self.fit_view()
        self.auto_suggest_cuts()
        self.imageModified.emit()

    def _push_undo(self) -> None:
        if self.work_img is not None:
            self._undo_stack.append(self.work_img.copy())
            if len(self._undo_stack) > 25:
                self._undo_stack.pop(0)
            self._redo_stack.clear()

    def undo(self) -> None:
        if not self._undo_stack or self.work_img is None:
            return
        self._redo_stack.append(self.work_img.copy())
        self.work_img = self._undo_stack.pop()
        self._refresh_pixmap()
        self.imageModified.emit()

    def redo(self) -> None:
        if not self._redo_stack or self.work_img is None:
            return
        self._undo_stack.append(self.work_img.copy())
        self.work_img = self._redo_stack.pop()
        self._refresh_pixmap()
        self.imageModified.emit()

    def _refresh_pixmap(self) -> None:
        if self.work_img is not None:
            self._pixmap = pil_to_qpixmap(self.work_img)
        else:
            self._pixmap = None
        self.update()

    def fit_view(self) -> None:
        if self.work_img is None:
            return
        iw, ih = self.work_img.size
        vw, vh = max(1, self.width() - 40), max(1, self.height() - 40)
        self.zoom = min(vw / max(iw, 1), vh / max(ih, 1), 6.0)
        self.pan = QPointF((self.width() - iw * self.zoom) * 0.5, (self.height() - ih * self.zoom) * 0.5)
        self.update()

    def auto_suggest_cuts(self) -> None:
        if self.work_img is None:
            return
        c1, c2, c3 = suggest_weapon_split_lines(self.work_img)
        self.cut_lines = [float(c1), float(c2), float(c3)]
        self.update()

    def auto_remove_corner_bg(self) -> None:
        if self.work_img is None:
            return
        self._push_undo()
        self.work_img = remove_background_color(
            self.work_img,
            key_rgb=None,
            tolerance=self.wand_tolerance,
            softness=self.wand_softness,
            contiguous_only=self.wand_contiguous,
        )
        self._refresh_pixmap()
        self.auto_suggest_cuts()
        self.imageModified.emit()

    def transform_image(self, op: str) -> None:
        if self.work_img is None or self.orig_img is None:
            return
        self._push_undo()
        if op == "rot_left":
            self.work_img = self.work_img.rotate(90, expand=True)
            self.orig_img = self.orig_img.rotate(90, expand=True)
        elif op == "rot_right":
            self.work_img = self.work_img.rotate(-90, expand=True)
            self.orig_img = self.orig_img.rotate(-90, expand=True)
        elif op == "flip_h":
            self.work_img = self.work_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            self.orig_img = self.orig_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        elif op == "flip_v":
            self.work_img = self.work_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            self.orig_img = self.orig_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        elif op == "trim":
            self.work_img = trim_and_pad(self.work_img, pad=4)
            self.orig_img = self.work_img.copy()
        self._refresh_pixmap()
        self.fit_view()
        self.auto_suggest_cuts()
        self.imageModified.emit()

    def detect_islands(self) -> int:
        if self.work_img is None:
            return 0
        self.detected_boxes = detect_sprite_islands(self.work_img, min_area=60)
        self.mode = self.MODE_BOX
        self.update()
        return len(self.detected_boxes)

    def extract_4_zones(self) -> None:
        if self.work_img is None:
            return
        w, h = self.work_img.size
        c1, c2, c3 = sorted(self.cut_lines)
        c1 = max(2, min(h - 6, int(round(c1))))
        c2 = max(c1 + 2, min(h - 4, int(round(c2))))
        c3 = max(c2 + 2, min(h - 2, int(round(c3))))

        regions = [
            ("Lưỡi / Đầu (Head)", "head", (0, 0, w, c1)),
            ("Chắn tay (Guard)", "guard", (0, c1, w, c2)),
            ("Cán (Grip)", "grip", (0, c2, w, c3)),
            ("Chuôi (Pommel)", "pommel", (0, c3, w, h)),
        ]
        results: List[ExtractedPart] = []
        for label, cat, box in regions:
            crop = self.work_img.crop(box)
            arr = np.asarray(crop)
            if np.any(arr[:, :, 3] > 20):
                cleaned = trim_and_pad(crop, pad=2, target_max_dim=256)
                sock = estimate_head_socket_x(cleaned) if cat == "head" else 0.5
                results.append(ExtractedPart(label=label, image=cleaned, suggested_category=cat, socket_x=sock))
        if results:
            self.multiExtracted.emit(results)

    def extract_whole_image(self) -> None:
        if self.work_img is None:
            return
        cleaned = trim_and_pad(self.work_img, pad=2, target_max_dim=256)
        sock = estimate_head_socket_x(cleaned)
        self.partExtracted.emit(ExtractedPart(label="Toàn bộ ảnh", image=cleaned, suggested_category="head", socket_x=sock))

    def _screen_to_img(self, pt: QPointF) -> QPointF:
        return QPointF((pt.x() - self.pan.x()) / self.zoom, (pt.y() - self.pan.y()) / self.zoom)

    def _img_to_screen(self, pt: QPointF) -> QPointF:
        return QPointF(pt.x() * self.zoom + self.pan.x(), pt.y() * self.zoom + self.pan.y())

    # ---- Drag & Drop ----
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        md = event.mimeData()
        if md.hasUrls():
            for url in md.urls():
                p = Path(url.toLocalFile())
                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga"):
                    with Image.open(p) as im:
                        self.load_image(im)
                    break
        elif md.hasImage():
            qim: QImage = md.imageData()
            self._load_qimage(qim)

    def _load_qimage(self, qim: QImage) -> None:
        qim = qim.convertToFormat(QImage.Format.Format_RGBA8888)
        ptr = qim.constBits()
        pil = Image.frombytes("RGBA", (qim.width(), qim.height()), bytes(ptr))
        self.load_image(pil)

    # ---- Mouse interactions ----
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.work_img is None:
            return
        pos = event.position()
        img_pt = self._screen_to_img(pos)

        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and (event.modifiers() & Qt.KeyboardModifier.AltModifier)
        ):
            self._panning = True
            self._pan_start = pos - self.pan
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode == self.MODE_SLICER:
                best_idx = -1
                best_dist = 10.0
                for idx, cy in enumerate(self.cut_lines):
                    sy = cy * self.zoom + self.pan.y()
                    d = abs(pos.y() - sy)
                    if d < best_dist:
                        best_dist = d
                        best_idx = idx
                self._drag_line_idx = best_idx

            elif self.mode == self.MODE_BOX:
                # Check if clicking a detected island box first
                for idx, (bx, by, bw, bh) in enumerate(self.detected_boxes):
                    if bx <= img_pt.x() <= bx + bw and by <= img_pt.y() <= by + bh:
                        crop = self.work_img.crop((bx, by, bx + bw, by + bh))
                        cleaned = trim_and_pad(crop, pad=2, target_max_dim=256)
                        sock = estimate_head_socket_x(cleaned)
                        self.partExtracted.emit(ExtractedPart(f"Vùng #{idx + 1}", cleaned, "head", sock))
                        return
                self.box_start = img_pt
                self.box_rect = QRectF(img_pt, img_pt)
                self.update()

            elif self.mode == self.MODE_LASSO:
                self.lasso_points.append(img_pt)
                self.update()

            elif self.mode == self.MODE_WAND:
                ix, iy = int(img_pt.x()), int(img_pt.y())
                iw, ih = self.work_img.size
                if 0 <= ix < iw and 0 <= iy < ih:
                    self._push_undo()
                    r, g, b, _ = self.work_img.getpixel((ix, iy))
                    self.work_img = remove_background_color(
                        self.work_img,
                        key_rgb=(r, g, b),
                        tolerance=self.wand_tolerance,
                        softness=self.wand_softness,
                        contiguous_only=self.wand_contiguous,
                        seed_xy=(ix, iy),
                    )
                    self._refresh_pixmap()
                    self.imageModified.emit()

            elif self.mode in (self.MODE_ERASER, self.MODE_RESTORE):
                self._push_undo()
                self._brushing = True
                self._last_brush_pt = (img_pt.x(), img_pt.y())
                self._apply_brush(img_pt.x(), img_pt.y(), img_pt.x(), img_pt.y())

        elif event.button() == Qt.MouseButton.RightButton:
            if self.mode == self.MODE_LASSO:
                if len(self.lasso_points) >= 3:
                    self._finish_lasso()
                else:
                    self.lasso_points.clear()
                    self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.mode == self.MODE_LASSO and len(self.lasso_points) >= 3:
            self._finish_lasso()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        img_pt = self._screen_to_img(pos)
        self._mouse_img_pos = img_pt

        if self._panning:
            self.pan = pos - self._pan_start
            self.update()
            return

        if self.work_img is None:
            return

        if self.mode == self.MODE_SLICER:
            if self._drag_line_idx >= 0:
                _, ih = self.work_img.size
                new_y = max(2.0, min(float(ih - 2), img_pt.y()))
                self.cut_lines[self._drag_line_idx] = new_y
                self.cut_lines.sort()
                self._drag_line_idx = self.cut_lines.index(new_y)
                self.update()
            else:
                near = any(abs(pos.y() - (cy * self.zoom + self.pan.y())) < 10.0 for cy in self.cut_lines)
                self.setCursor(Qt.CursorShape.SplitVCursor if near else Qt.CursorShape.ArrowCursor)

        elif self.mode == self.MODE_BOX:
            if self.box_start is not None:
                self.box_rect = QRectF(self.box_start, img_pt).normalized()
                self.update()
            else:
                self.hovered_box_idx = -1
                for idx, (bx, by, bw, bh) in enumerate(self.detected_boxes):
                    if bx <= img_pt.x() <= bx + bw and by <= img_pt.y() <= by + bh:
                        self.hovered_box_idx = idx
                        break
                self.update()

        elif self.mode in (self.MODE_ERASER, self.MODE_RESTORE):
            if self._brushing and self._last_brush_pt is not None:
                self._apply_brush(self._last_brush_pt[0], self._last_brush_pt[1], img_pt.x(), img_pt.y())
                self._last_brush_pt = (img_pt.x(), img_pt.y())
            self.update()
        else:
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self.mode == self.MODE_SLICER:
            self._drag_line_idx = -1

        elif self.mode == self.MODE_BOX and self.box_start is not None and self.work_img is not None:
            r = QRectF(self.box_start, self._screen_to_img(event.position())).normalized()
            self.box_start = None
            iw, ih = self.work_img.size
            x0 = max(0, int(math.floor(r.left())))
            y0 = max(0, int(math.floor(r.top())))
            x1 = min(iw, int(math.ceil(r.right())))
            y1 = min(ih, int(math.ceil(r.bottom())))
            if x1 - x0 >= 6 and y1 - y0 >= 6:
                crop = self.work_img.crop((x0, y0, x1, y1))
                cleaned = trim_and_pad(crop, pad=2, target_max_dim=256)
                sock = estimate_head_socket_x(cleaned)
                self.partExtracted.emit(ExtractedPart("Crop Box", cleaned, "head", sock))
            self.box_rect = None
            self.update()

        elif self._brushing:
            self._brushing = False
            self._last_brush_pt = None
            self.imageModified.emit()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.work_img is None:
            return
        pos = event.position()
        before = self._screen_to_img(pos)
        factor = 1.15 if event.angleDelta().y() > 0 else (1.0 / 1.15)
        self.zoom = max(0.15, min(20.0, self.zoom * factor))
        after = self._img_to_screen(before)
        self.pan += (pos - after)
        self.update()

    def keyPressEvent(self, event) -> None:
        if self.mode == self.MODE_LASSO:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and len(self.lasso_points) >= 3:
                self._finish_lasso()
                return
            if event.key() == Qt.Key.Key_Escape:
                self.lasso_points.clear()
                self.update()
                return
        super().keyPressEvent(event)

    def _finish_lasso(self) -> None:
        if self.work_img is None or len(self.lasso_points) < 3:
            return
        pts = [(p.x(), p.y()) for p in self.lasso_points]
        extracted = crop_polygon_mask(self.work_img, pts)
        sock = estimate_head_socket_x(extracted)
        self.lasso_points.clear()
        self.update()
        self.partExtracted.emit(ExtractedPart("Lasso Part", extracted, "head", sock))

    def _apply_brush(self, x0: float, y0: float, x1: float, y1: float) -> None:
        if self.work_img is None or self.orig_img is None:
            return
        w, h = self.work_img.size
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        r = max(1, self.brush_radius)
        draw.line([(x0, y0), (x1, y1)], fill=255, width=r * 2)
        draw.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=255)
        m_arr = np.asarray(mask) > 128

        w_arr = np.asarray(self.work_img, dtype=np.uint8).copy()
        if self.mode == self.MODE_ERASER:
            w_arr[m_arr, 3] = 0
        else:
            o_arr = np.asarray(self.orig_img, dtype=np.uint8)
            w_arr[m_arr] = o_arr[m_arr]
        self.work_img = Image.fromarray(w_arr, "RGBA")
        self._refresh_pixmap()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()

        # Checkerboard dark background
        p.fillRect(0, 0, w, h, QColor(18, 22, 24))
        sq = 16
        c_chk = QColor(26, 31, 34)
        for yy in range(0, h, sq):
            for xx in range(0, w, sq):
                if (xx // sq + yy // sq) % 2 == 0:
                    p.fillRect(xx, yy, sq, sq, c_chk)

        if self._pixmap is None or self.work_img is None:
            p.setPen(QColor(154, 166, 168))
            p.drawText(
                QRectF(20, 20, w - 40, h - 40),
                Qt.AlignmentFlag.AlignCenter,
                "Kéo thả ảnh vào đây, bấm 'Mở ảnh', hoặc nhấn Ctrl+V để dán ảnh từ Clipboard\n"
                "(Hỗ trợ PNG, JPG, WebP — tách nền & cắt part vũ khí cực nhanh)",
            )
            return

        iw, ih = self.work_img.size
        dst = QRectF(self.pan.x(), self.pan.y(), iw * self.zoom, ih * self.zoom)
        p.drawPixmap(dst.toRect(), self._pixmap)

        # Draw border around image
        p.setPen(QPen(QColor(100, 115, 120, 160), 1))
        p.drawRect(dst)

        # Draw 4-Zone slicer overlays
        if self.mode == self.MODE_SLICER:
            c1, c2, c3 = sorted(self.cut_lines)
            zones = [
                (0.0, c1, QColor(220, 160, 60, 28), "1. Lưỡi / Đầu (Head)"),
                (c1, c2, QColor(80, 190, 220, 28), "2. Chắn tay (Guard)"),
                (c2, c3, QColor(110, 210, 120, 28), "3. Cán (Grip)"),
                (c3, float(ih), QColor(200, 110, 220, 28), "4. Chuôi (Pommel)"),
            ]
            for zy0, zy1, col, label in zones:
                sy0 = zy0 * self.zoom + self.pan.y()
                sy1 = zy1 * self.zoom + self.pan.y()
                p.fillRect(QRectF(dst.left(), sy0, dst.width(), max(1.0, sy1 - sy0)), col)
                p.setPen(QColor(245, 245, 245, 220))
                p.drawText(QRectF(dst.left() + 8, sy0 + 4, 180, 20), Qt.AlignmentFlag.AlignLeft, label)

            for idx, cy in enumerate(self.cut_lines):
                sy = cy * self.zoom + self.pan.y()
                p.setPen(QPen(QColor(240, 204, 135), 2, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(0, sy), QPointF(w, sy))
                p.setBrush(QColor(196, 150, 69))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(QRectF(6, sy - 10, 58, 20), 4, 4)
                p.setPen(QColor(16, 20, 21))
                p.drawText(QRectF(6, sy - 10, 58, 20), Qt.AlignmentFlag.AlignCenter, f"Cắt {idx + 1}")

        # Draw detected island boxes
        if self.mode == self.MODE_BOX:
            for idx, (bx, by, bw, bh) in enumerate(self.detected_boxes):
                tl = self._img_to_screen(QPointF(bx, by))
                r_scr = QRectF(tl.x(), tl.y(), bw * self.zoom, bh * self.zoom)
                is_hov = (idx == self.hovered_box_idx)
                p.setPen(QPen(QColor(120, 235, 160) if is_hov else QColor(196, 150, 69, 200), 2 if is_hov else 1.5))
                p.setBrush(QColor(120, 235, 160, 40) if is_hov else QColor(196, 150, 69, 18))
                p.drawRect(r_scr)
                p.setPen(QColor(245, 245, 245))
                p.drawText(QPointF(r_scr.left() + 4, r_scr.top() + 14), f"#{idx + 1}")

            if self.box_rect is not None:
                tl = self._img_to_screen(self.box_rect.topLeft())
                br = self._img_to_screen(self.box_rect.bottomRight())
                p.setPen(QPen(QColor(240, 204, 135), 2))
                p.setBrush(QColor(240, 204, 135, 35))
                p.drawRect(QRectF(tl, br))

        # Draw Lasso polygon
        if self.mode == self.MODE_LASSO and self.lasso_points:
            pts_scr = [self._img_to_screen(pt) for pt in self.lasso_points]
            if self._mouse_img_pos is not None:
                pts_scr.append(self._img_to_screen(self._mouse_img_pos))
            p.setPen(QPen(QColor(240, 204, 135), 2))
            p.setBrush(QColor(240, 204, 135, 35))
            p.drawPolygon(QPolygonF(pts_scr))
            for pt in pts_scr[:-1]:
                p.setBrush(QColor(255, 220, 140))
                p.drawEllipse(pt, 4, 4)

        # Brush cursor circle
        if self.mode in (self.MODE_ERASER, self.MODE_RESTORE) and self._mouse_img_pos is not None:
            c = self._img_to_screen(self._mouse_img_pos)
            rad = self.brush_radius * self.zoom
            p.setPen(QPen(QColor(255, 110, 110) if self.mode == self.MODE_ERASER else QColor(110, 255, 150), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, rad, rad)


class PartPreviewThumb(QWidget):
    """Shows the extracted part with optional vertical HeadSocket alignment line."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(165)
        self._pix: Optional[QPixmap] = None
        self._socket_x: float = 0.5
        self._show_socket: bool = True

    def set_part(self, img: Optional[Image.Image], socket_x: float = 0.5, show_socket: bool = True) -> None:
        self._pix = pil_to_qpixmap(img) if img is not None else None
        self._socket_x = socket_x
        self._show_socket = show_socket
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(14, 18, 20))
        sq = 12
        for yy in range(0, h, sq):
            for xx in range(0, w, sq):
                if (xx // sq + yy // sq) % 2 == 0:
                    p.fillRect(xx, yy, sq, sq, QColor(24, 29, 31))
        p.setPen(QPen(QColor(53, 63, 66), 1))
        p.drawRect(0, 0, w - 1, h - 1)

        if self._pix is None:
            return
        pw, ph = self._pix.width(), self._pix.height()
        scale = min((w - 20) / max(pw, 1), (h - 20) / max(ph, 1))
        dw, dh = pw * scale, ph * scale
        dx, dy = (w - dw) * 0.5, (h - dh) * 0.5
        p.drawPixmap(QRectF(dx, dy, dw, dh).toRect(), self._pix)

        if self._show_socket:
            sx = dx + dw * self._socket_x
            p.setPen(QPen(QColor(240, 180, 75, 220), 1.5, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(sx, 4), QPointF(sx, h - 4))


class PartSplitterWorkspace(QWidget):
    """Complete workspace for importing images, splitting parts, and adding them to Overgeared 1.7."""
    partTestedInForge = Signal(str, int, int, object, float)  # category, kind, index, PIL.Image, socket_x
    modPartsUpdated = Signal(str, int, int)                   # category, kind, index

    def __init__(self, store: ModAssetStore, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.store = store
        self.extracted: List[ExtractedPart] = []
        self.selected_idx: int = -1

        self._build_ui()

        QShortcut(QKeySequence("Ctrl+V"), self, self.paste_clipboard)
        QShortcut(QKeySequence("Ctrl+Z"), self, lambda: self.canvas.undo())
        QShortcut(QKeySequence("Ctrl+Y"), self, lambda: self.canvas.redo())

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ---- Left Column: Canvas + Top/Bottom toolbars ----
        left_widget = QWidget()
        left_lay = QVBoxLayout(left_widget)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(6)

        # File & Quick-Cleanup bar
        top_bar = QHBoxLayout()
        btn_open = QPushButton("📂 Mở ảnh...")
        btn_open.clicked.connect(self.open_image_dialog)
        btn_paste = QPushButton("📋 Dán (Ctrl+V)")
        btn_paste.clicked.connect(self.paste_clipboard)
        btn_from_mod = QPushButton("📦 Mở Part/Atlas trong Mod")
        btn_from_mod.clicked.connect(self.open_mod_image_dialog)

        btn_auto_bg = QPushButton("✨ Tự xóa nền")
        btn_auto_bg.setToolTip("Lấy màu 4 góc để xóa nền nhanh")
        btn_auto_bg.clicked.connect(lambda: self.canvas.auto_remove_corner_bg())

        btn_rot_l = QPushButton("↺ 90°")
        btn_rot_l.clicked.connect(lambda: self.canvas.transform_image("rot_left"))
        btn_rot_r = QPushButton("↻ 90°")
        btn_rot_r.clicked.connect(lambda: self.canvas.transform_image("rot_right"))
        btn_flip_h = QPushButton("⇄ Lật")
        btn_flip_h.clicked.connect(lambda: self.canvas.transform_image("flip_h"))
        btn_undo = QPushButton("↩ Undo")
        btn_undo.clicked.connect(lambda: self.canvas.undo())
        btn_fit = QPushButton("⊡ Fit")
        btn_fit.clicked.connect(lambda: self.canvas.fit_view())

        for b in (btn_open, btn_paste, btn_from_mod, btn_auto_bg, btn_rot_l, btn_rot_r, btn_flip_h, btn_undo, btn_fit):
            top_bar.addWidget(b)
        top_bar.addStretch()
        left_lay.addLayout(top_bar)

        # Mode Toolbar
        mode_bar = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        modes = [
            (SplitterCanvas.MODE_SLICER, "🔪 Cắt 4 Part (Vũ khí)"),
            (SplitterCanvas.MODE_BOX, "▭ Kéo Khung Crop"),
            (SplitterCanvas.MODE_LASSO, "✂ Cắt Lasso (Đa giác)"),
            (SplitterCanvas.MODE_WAND, "🪄 Chấm Tẩy Nền"),
            (SplitterCanvas.MODE_ERASER, "🧽 Bút Tẩy"),
            (SplitterCanvas.MODE_RESTORE, "🖌 Khôi Phục"),
        ]
        for mid, mlabel in modes:
            btn = QPushButton(mlabel)
            btn.setCheckable(True)
            if mid == 0:
                btn.setChecked(True)
            self.mode_group.addButton(btn, mid)
            mode_bar.addWidget(btn)
        self.mode_group.idClicked.connect(self._on_mode_changed)

        mode_bar.addStretch()
        self.btn_detect = QPushButton("🔍 Tự tìm vùng ảnh")
        self.btn_detect.clicked.connect(self._on_detect_islands)
        mode_bar.addWidget(self.btn_detect)
        left_lay.addLayout(mode_bar)

        # Contextual Action / Parameter bar
        param_bar = QHBoxLayout()
        self.btn_extract_4 = QPushButton("⚡ Tách ngay 4 Part từ đường cắt →")
        self.btn_extract_4.setObjectName("PrimaryBtn")
        self.btn_extract_4.clicked.connect(lambda: self.canvas.extract_4_zones())

        self.btn_suggest_cuts = QPushButton("📐 Tự căn 3 đường cắt")
        self.btn_suggest_cuts.clicked.connect(lambda: self.canvas.auto_suggest_cuts())

        self.btn_extract_whole = QPushButton("➕ Lấy nguyên ảnh làm 1 Part →")
        self.btn_extract_whole.clicked.connect(lambda: self.canvas.extract_whole_image())

        param_bar.addWidget(self.btn_extract_4)
        param_bar.addWidget(self.btn_suggest_cuts)
        param_bar.addWidget(self.btn_extract_whole)

        param_bar.addSpacing(12)
        param_bar.addWidget(QLabel("Ngưỡng nền:"))
        self.slider_tol = QSlider(Qt.Orientation.Horizontal)
        self.slider_tol.setRange(5, 120)
        self.slider_tol.setValue(36)
        self.slider_tol.setFixedWidth(95)
        self.slider_tol.valueChanged.connect(lambda v: setattr(self.canvas, "wand_tolerance", v))
        param_bar.addWidget(self.slider_tol)

        param_bar.addWidget(QLabel("Cọ:"))
        self.slider_brush = QSlider(Qt.Orientation.Horizontal)
        self.slider_brush.setRange(2, 48)
        self.slider_brush.setValue(12)
        self.slider_brush.setFixedWidth(75)
        self.slider_brush.valueChanged.connect(lambda v: setattr(self.canvas, "brush_radius", v))
        param_bar.addWidget(self.slider_brush)
        param_bar.addStretch()
        left_lay.addLayout(param_bar)

        self.canvas = SplitterCanvas()
        self.canvas.partExtracted.connect(self._on_part_extracted)
        self.canvas.multiExtracted.connect(self._on_multi_extracted)
        left_lay.addWidget(self.canvas, 1)

        # ---- Right Column: Extracted Tray + Assign & Export ----
        right_panel = QFrame()
        right_panel.setObjectName("Panel")
        right_panel.setFixedWidth(400)
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(10, 10, 10, 10)
        right_lay.setSpacing(8)

        lbl_tray = QLabel("1. Danh sách Part đã tách")
        lbl_tray.setObjectName("GoldTitle")
        right_lay.addWidget(lbl_tray)

        self.tray_list = QListWidget()
        self.tray_list.setFixedHeight(135)
        self.tray_list.currentRowChanged.connect(self._on_tray_selected)
        right_lay.addWidget(self.tray_list)

        self.part_thumb = PartPreviewThumb()
        right_lay.addWidget(self.part_thumb)

        # Assignment form
        form_box = QGroupBox("2. Gán thông tin & Vị trí trong Mod 1.7")
        fg = QGridLayout(form_box)
        fg.setSpacing(6)

        fg.addWidget(QLabel("Loại Part:"), 0, 0)
        self.combo_cat = QComboBox()
        for label in PART_CATEGORY_LABELS + ["Hoa văn (Pattern)"]:
            self.combo_cat.addItem(label)
        self.combo_cat.currentIndexChanged.connect(self._refresh_slot_combo)
        fg.addWidget(self.combo_cat, 0, 1)

        fg.addWidget(QLabel("Loại vũ khí:"), 1, 0)
        self.combo_kind = QComboBox()
        for kv in KINDS_VI:
            self.combo_kind.addItem(kv)
        self.combo_kind.currentIndexChanged.connect(self._refresh_slot_combo)
        fg.addWidget(self.combo_kind, 1, 1)

        fg.addWidget(QLabel("Slot đích:"), 2, 0)
        self.combo_slot = QComboBox()
        fg.addWidget(self.combo_slot, 2, 1)

        fg.addWidget(QLabel("Tên hiển thị:"), 3, 0)
        self.edit_name = QLineEdit("Custom Part")
        fg.addWidget(self.edit_name, 3, 1)

        fg.addWidget(QLabel("Socket X (Khớp):"), 4, 0)
        sock_row = QHBoxLayout()
        self.slider_sock = QSlider(Qt.Orientation.Horizontal)
        self.slider_sock.setRange(5, 95)
        self.slider_sock.setValue(50)
        self.lbl_sock = QLabel("50%")
        self.lbl_sock.setFixedWidth(36)
        self.slider_sock.valueChanged.connect(self._on_socket_changed)
        sock_row.addWidget(self.slider_sock, 1)
        sock_row.addWidget(self.lbl_sock)
        fg.addLayout(sock_row, 4, 1)

        # Stats row
        fg.addWidget(QLabel("Dmg / CD / Mass:"), 5, 0)
        stat_row = QHBoxLayout()
        self.spin_dmg = QDoubleSpinBox()
        self.spin_dmg.setRange(0.5, 3.0)
        self.spin_dmg.setSingleStep(0.05)
        self.spin_dmg.setValue(1.0)
        self.spin_cd = QDoubleSpinBox()
        self.spin_cd.setRange(0.5, 3.0)
        self.spin_cd.setSingleStep(0.05)
        self.spin_cd.setValue(1.0)
        self.spin_mass = QDoubleSpinBox()
        self.spin_mass.setRange(0.5, 3.0)
        self.spin_mass.setSingleStep(0.05)
        self.spin_mass.setValue(1.0)
        stat_row.addWidget(self.spin_dmg)
        stat_row.addWidget(self.spin_cd)
        stat_row.addWidget(self.spin_mass)
        fg.addLayout(stat_row, 5, 1)

        fg.addWidget(QLabel("Xuyên giáp / Cost:"), 6, 0)
        ap_row = QHBoxLayout()
        self.spin_ap = QDoubleSpinBox()
        self.spin_ap.setRange(-0.2, 0.5)
        self.spin_ap.setSingleStep(0.01)
        self.spin_ap.setValue(0.0)
        self.spin_cost = QSpinBox()
        self.spin_cost.setRange(1, 200)
        self.spin_cost.setValue(24)
        ap_row.addWidget(self.spin_ap)
        ap_row.addWidget(self.spin_cost)
        fg.addLayout(ap_row, 6, 1)

        self.chk_atlas = QCheckBox("Đóng gói vào expansion_atlas.png nếu là slot 4..5 / 5..6")
        self.chk_atlas.setChecked(True)
        fg.addWidget(self.chk_atlas, 7, 0, 1, 2)

        right_lay.addWidget(form_box)

        # Action Buttons
        self.btn_test_forge = QPushButton("⚡ Test ngay trong Lò Rèn (Chưa ghi file)")
        self.btn_test_forge.setObjectName("PrimaryBtn")
        self.btn_test_forge.setFixedHeight(36)
        self.btn_test_forge.clicked.connect(self._test_in_forge)

        self.btn_save_mod = QPushButton("💾 Lưu Part này vào Mod Overgeared (1.7)")
        self.btn_save_mod.setObjectName("AccentGreenBtn")
        self.btn_save_mod.setFixedHeight(38)
        self.btn_save_mod.clicked.connect(self._save_current_part)

        self.btn_save_all_4 = QPushButton("🚀 Lưu tất cả Part vào Mod Overgeared")
        self.btn_save_all_4.setFixedHeight(34)
        self.btn_save_all_4.clicked.connect(self._save_all_parts)

        self.btn_test_all = QPushButton("⚡ Test ghép tất cả Part vào Lò Rèn")
        self.btn_test_all.setFixedHeight(34)
        self.btn_test_all.clicked.connect(self._test_all_in_forge)

        right_lay.addWidget(self.btn_test_forge)
        right_lay.addWidget(self.btn_test_all)
        right_lay.addWidget(self.btn_save_mod)
        right_lay.addWidget(self.btn_save_all_4)
        right_lay.addStretch()

        root.addWidget(left_widget, 1)
        root.addWidget(right_panel)

        self._refresh_slot_combo()

    def _on_mode_changed(self, mid: int) -> None:
        self.canvas.mode = mid
        self.canvas.update()

    def _on_detect_islands(self) -> None:
        count = self.canvas.detect_islands()
        self.mode_group.button(SplitterCanvas.MODE_BOX).setChecked(True)
        if count == 0:
            QMessageBox.information(self, "Tự tìm vùng", "Chưa tìm thấy vùng ảnh tách biệt. Hãy thử 'Tự xóa nền' trước nếu ảnh chưa trong suốt.")

    def open_image_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn ảnh vũ khí / part", str(self.store.mod_root),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tga)"
        )
        if path:
            with Image.open(path) as im:
                self.canvas.load_image(im)

    def open_mod_image_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn texture trong Mod Overgeared", str(self.store.textures_root),
            "PNG Files (*.png)"
        )
        if path:
            with Image.open(path) as im:
                self.canvas.load_image(im)

    def paste_clipboard(self) -> None:
        cb = QApplication.clipboard()
        qim = cb.image()
        if not qim.isNull():
            self.canvas._load_qimage(qim)
        else:
            md = cb.mimeData()
            if md.hasUrls():
                for url in md.urls():
                    p = Path(url.toLocalFile())
                    if p.exists():
                        with Image.open(p) as im:
                            self.canvas.load_image(im)
                        break

    def _on_part_extracted(self, part: ExtractedPart) -> None:
        self.extracted.append(part)
        self._rebuild_tray(select_last=True)

    def _on_multi_extracted(self, parts: List[ExtractedPart]) -> None:
        self.extracted.clear()
        self.extracted.extend(parts)
        self._rebuild_tray(select_last=False)
        if self.extracted:
            self.tray_list.setCurrentRow(0)

    def _rebuild_tray(self, select_last: bool = False) -> None:
        self.tray_list.clear()
        for p in self.extracted:
            w, h = p.image.size
            item = QListWidgetItem(f"{p.label}  [{w}x{h}]")
            self.tray_list.addItem(item)
        if select_last and self.extracted:
            self.tray_list.setCurrentRow(len(self.extracted) - 1)

    def _on_tray_selected(self, row: int) -> None:
        if row < 0 or row >= len(self.extracted):
            self.selected_idx = -1
            self.part_thumb.set_part(None)
            return
        self.selected_idx = row
        ep = self.extracted[row]
        cat_idx = 4 if ep.suggested_category == "pattern" else PART_CATEGORIES.index(ep.suggested_category)
        self.combo_cat.setCurrentIndex(cat_idx)
        self.edit_name.setText(ep.label)
        self.slider_sock.setValue(int(round(ep.socket_x * 100)))
        self.part_thumb.set_part(ep.image, ep.socket_x, show_socket=(ep.suggested_category == "head"))
        self._refresh_slot_combo()

    def _on_socket_changed(self, val: int) -> None:
        self.lbl_sock.setText(f"{val}%")
        if 0 <= self.selected_idx < len(self.extracted):
            self.extracted[self.selected_idx].socket_x = val / 100.0
            ep = self.extracted[self.selected_idx]
            self.part_thumb.set_part(ep.image, ep.socket_x, show_socket=(self.combo_cat.currentIndex() == 0))

    def _current_category(self) -> str:
        idx = self.combo_cat.currentIndex()
        return "pattern" if idx == 4 else PART_CATEGORIES[idx]

    def _refresh_slot_combo(self) -> None:
        cat = self._current_category()
        kind = self.combo_kind.currentIndex()
        self.combo_kind.setEnabled(cat == "head")
        self.combo_slot.clear()

        next_idx = self.store.next_free_index(cat, kind)
        self.combo_slot.addItem(f"✨ Thêm mới (Slot #{next_idx})", next_idx)

        if cat == "head":
            for idx, pid, name in self.store.get_heads(kind):
                self.combo_slot.addItem(f"Ghi đè #{idx}: {name} ({pid})", idx)
        elif cat == "guard":
            for idx, pid, name in self.store.get_guards(kind):
                self.combo_slot.addItem(f"Ghi đè #{idx}: {name} ({pid})", idx)
        elif cat == "grip":
            for idx, pid, name in self.store.get_grips():
                self.combo_slot.addItem(f"Ghi đè #{idx}: {name} ({pid})", idx)
        elif cat == "pommel":
            for idx, pid, name in self.store.get_pommels(kind):
                self.combo_slot.addItem(f"Ghi đè #{idx}: {name} ({pid})", idx)
        elif cat == "pattern":
            for idx, name in self.store.get_patterns():
                if idx > 0:
                    self.combo_slot.addItem(f"Ghi đè #{idx}: {name} (pattern_{idx})", idx)

    def _test_in_forge(self) -> None:
        if not (0 <= self.selected_idx < len(self.extracted)):
            QMessageBox.warning(self, "Chưa chọn Part", "Hãy tách ít nhất 1 Part ở khung bên trái trước!")
            return
        ep = self.extracted[self.selected_idx]
        cat = self._current_category()
        kind = self.combo_kind.currentIndex()
        slot_idx = self.combo_slot.currentData()
        sock = self.slider_sock.value() / 100.0
        self.partTestedInForge.emit(cat, kind, int(slot_idx), ep.image, sock)

    def _test_all_in_forge(self) -> None:
        if not self.extracted:
            QMessageBox.warning(self, "Danh sách trống", "Hãy tách các Part ở khung bên trái trước!")
            return
        kind = self.combo_kind.currentIndex()
        for ep in self.extracted:
            cat = ep.suggested_category
            slot_idx = self.store.next_free_index(cat, kind)
            self.partTestedInForge.emit(cat, kind, slot_idx, ep.image, ep.socket_x)

    def _save_current_part(self) -> None:
        if not (0 <= self.selected_idx < len(self.extracted)):
            QMessageBox.warning(self, "Chưa chọn Part", "Hãy tách ít nhất 1 Part ở khung bên trái trước!")
            return
        ep = self.extracted[self.selected_idx]
        cat = self._current_category()
        kind = self.combo_kind.currentIndex()
        slot_idx = int(self.combo_slot.currentData())
        name = self.edit_name.text().strip() or f"Custom {cat} #{slot_idx}"
        sock = self.slider_sock.value() / 100.0 if cat == "head" else None

        pid, out_path = save_part_to_mod(
            self.store,
            ep.image,
            category=cat,
            kind=kind,
            index=slot_idx,
            name=name,
            damage=self.spin_dmg.value(),
            cooldown=self.spin_cd.value(),
            mass=self.spin_mass.value(),
            penetration=self.spin_ap.value(),
            cost=self.spin_cost.value(),
            socket_x=sock,
            pack_into_atlas_if_builtin=self.chk_atlas.isChecked(),
        )
        update_language_xml(self.store)
        self._refresh_slot_combo()
        self.modPartsUpdated.emit(cat, kind, slot_idx)
        QMessageBox.information(
            self,
            "Đã lưu vào Mod Overgeared",
            f"Đã lưu part '{name}' ({pid}) vào:\n{out_path}\n\nBạn có thể qua tab Lò Rèn để xem ngay và xuất C# code ở tab Import vào Code!",
        )

    def _save_all_parts(self) -> None:
        if not self.extracted:
            return
        kind = self.combo_kind.currentIndex()
        saved_msgs: List[str] = []
        last_saved = ("head", kind, 0)
        for ep in self.extracted:
            cat = ep.suggested_category
            slot_idx = self.store.next_free_index(cat, kind)
            name = ep.label
            sock = ep.socket_x if cat == "head" else None
            pid, _ = save_part_to_mod(
                self.store,
                ep.image,
                category=cat,
                kind=kind,
                index=slot_idx,
                name=name,
                socket_x=sock,
                pack_into_atlas_if_builtin=self.chk_atlas.isChecked(),
            )
            saved_msgs.append(f"{pid} ({name})")
            last_saved = (cat, kind, slot_idx)
        update_language_xml(self.store)
        self._refresh_slot_combo()
        self.modPartsUpdated.emit(*last_saved)
        QMessageBox.information(
            self,
            "Đã lưu hàng loạt",
            "Đã lưu các part:\n- " + "\n- ".join(saved_msgs),
        )
