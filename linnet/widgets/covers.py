"""封面图片异步加载（带缓存）"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap

from ..tasks import run_async
from ..theme import ICON, PANEL_2

_cache = {}


def rounded_pixmap(pixmap, size, radius):
    """按 iOS 圆角裁切封面，避免 QLabel 的 border-radius 只裁背景不裁图片"""
    scaled = pixmap.scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation)
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return canvas


def load_cover(label, url, size, radius=None, fallback="♪"):
    def show_fallback():
        label.setText(fallback)
        label.setPixmap(QPixmap())
        if radius:
            label.setStyleSheet(
                f"background:{PANEL_2};border-radius:{radius}px;color:{ICON};")

    if not url:
        show_fallback()
        return
    key = (url, size)
    pix = _cache.get(key)
    if pix is not None:
        _apply(label, pix, size, radius)
        return

    def fetch():
        import requests
        resp = requests.get("%s?param=%dy%d" % (url, size, size), timeout=8)
        resp.raise_for_status()
        return resp.content

    def done(data):
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if pixmap.isNull():
            show_fallback()
            return
        _cache[key] = pixmap
        _apply(label, pixmap, size, radius)

    label.setText("…")
    run_async(fetch, done, lambda _e: show_fallback())


def _apply(label, pixmap, size, radius):
    if radius:
        label.setStyleSheet("border-radius:%dpx;background:transparent;" % radius)
        label.setPixmap(rounded_pixmap(pixmap, size, radius))
    else:
        label.setPixmap(pixmap.scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation))
    label.setFixedSize(size, size)
