"""右侧歌词面板 / 单行歌词跑马灯"""
import re

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (QFrame, QLabel, QScrollArea, QSizePolicy,
                             QVBoxLayout, QWidget)

from ..theme import ACCENT, SUB

LINE_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")


def parse_lrc(raw):
    """解析 LRC → [(秒, 文本)]"""
    lines = []
    if not raw:
        return lines
    for item in raw.splitlines():
        text = LINE_RE.sub("", item).strip()
        if not text:
            continue
        for m in LINE_RE.finditer(item):
            minute, second, frac = int(m.group(1)), int(m.group(2)), m.group(3)
            if frac:
                ms = int(frac.ljust(3, "0")[:3])
            else:
                ms = 0
            lines.append((minute * 60 + second + ms / 1000.0, text))
    lines.sort(key=lambda x: x[0])
    return lines


class LyricPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LyricPanel")
        self.setFixedWidth(260)
        self._labels = []
        self._times = []
        self._current = -1

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        head = QLabel("歌词")
        head.setStyleSheet(
            f"color:{SUB};font-size:12px;font-weight:600;padding:18px 0 10px 0;")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(18, 10, 18, 28)
        self.body_layout.setSpacing(12)
        self.body_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)

        self.show_tip("播放歌曲后显示歌词")

    def _clear(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._labels = []
        self._times = []
        self._current = -1

    def show_tip(self, text):
        self._clear()
        tip = QLabel(text)
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_layout.addSpacing(20)
        self.body_layout.addWidget(tip)

    def set_lyric(self, raw, fallback_title=""):
        self._clear()
        lines = parse_lrc(raw)
        if not lines:
            self.show_tip("暂无歌词")
            return
        for stamp, text in lines:
            # 在字符间插入零宽空格，保证超长英文/无空格句子也能换行，
            # 否则 QLabel 会把整行撑出面板，右侧被裁掉。
            label = QLabel("\u200b".join(text))
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Policy.Ignored,
                                QSizePolicy.Policy.Preferred)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(f"color:{SUB};font-size:13px;")
            label.setToolTip(text)
            self.body_layout.addWidget(label)
            self._labels.append(label)
            self._times.append(stamp)
        self._current = -1

    def on_position(self, ms):
        if not self._times:
            return
        pos = ms / 1000.0
        idx = -1
        for i, t in enumerate(self._times):
            if t <= pos + 0.15:
                idx = i
            else:
                break
        if idx == self._current:
            return
        if self._current >= 0 and self._current < len(self._labels):
            self._labels[self._current].setStyleSheet(
                f"color:{SUB};font-size:13px;")
        self._current = idx
        if idx < 0:
            return
        label = self._labels[idx]
        label.setStyleSheet(
            f"color:{ACCENT};font-size:14px;font-weight:600;")
        self._center_on(label)
        # 字号变化后 QLabel 的高度要等布局刷新，延后一次再居中，
        # 避免当前歌词刚切行时只露出半行。
        QTimer.singleShot(0, lambda label=label: self._center_deferred(label))

    def _center_deferred(self, label):
        # 如果这 0ms 内已经切歌、标签被 deleteLater，就不要碰它。
        if label in self._labels:
            self._center_on(label)

    def _center_on(self, label):
        bar = self.scroll.verticalScrollBar()
        y = label.mapTo(self.body, label.rect().topLeft()).y()
        viewport_h = self.scroll.viewport().height()
        target = max(0, y - viewport_h // 2 + label.height() // 2)
        bar.setValue(min(target, bar.maximum()))


class FullLyricsView(QFrame):
    """占据中间内容区的整块歌词页"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FullLyrics")
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self._labels = []
        self._times = []
        self._current = -1

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 22, 40, 14)
        outer.setSpacing(8)

        head = QLabel("歌词")
        head.setStyleSheet(
            f"color:{SUB};font-size:12px;font-weight:600;padding:0 4px 6px 4px;")
        outer.addWidget(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(36, 12, 36, 48)
        self.body_layout.setSpacing(16)
        self.body_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)

        self.show_tip("播放歌曲后显示歌词")

    def _clear(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._labels = []
        self._times = []
        self._current = -1

    def show_tip(self, text):
        self._clear()
        tip = QLabel(text)
        tip.setWordWrap(True)
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip.setStyleSheet(f"color:{SUB};font-size:18px;")
        self.body_layout.addSpacing(40)
        self.body_layout.addWidget(tip)

    def set_lyric(self, raw):
        self._clear()
        lines = parse_lrc(raw)
        if not lines:
            self.show_tip("暂无歌词")
            return
        for stamp, text in lines:
            label = QLabel("\u200b".join(text))
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Policy.Ignored,
                                QSizePolicy.Policy.Preferred)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(f"color:{SUB};font-size:18px;")
            label.setToolTip(text)
            self.body_layout.addWidget(label)
            self._labels.append(label)
            self._times.append(stamp)
        self._current = -1

    def on_position(self, ms):
        if not self._times:
            return
        pos = ms / 1000.0
        idx = -1
        for i, t in enumerate(self._times):
            if t <= pos + 0.15:
                idx = i
            else:
                break
        if idx == self._current:
            return
        if self._current >= 0 and self._current < len(self._labels):
            self._labels[self._current].setStyleSheet(
                f"color:{SUB};font-size:18px;")
        self._current = idx
        if idx < 0:
            return
        label = self._labels[idx]
        label.setStyleSheet(
            f"color:{ACCENT};font-size:22px;font-weight:600;")
        self._center_on(label)
        QTimer.singleShot(0, lambda label=label: self._center_deferred(label))

    def _center_deferred(self, label):
        if label in self._labels:
            self._center_on(label)

    def _center_on(self, label):
        bar = self.scroll.verticalScrollBar()
        y = label.mapTo(self.body, label.rect().topLeft()).y()
        viewport_h = self.scroll.viewport().height()
        target = max(0, y - viewport_h // 2 + label.height() // 2)
        bar.setValue(min(target, bar.maximum()))


class LyricTicker(QFrame):
    """播放栏上方的一行歌词：短句居中，长句自动横向滚动"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LyricTicker")
        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        font = QFont(self.font())
        font.setPixelSize(12)
        self.setFont(font)
        self._text = ""
        self._times = []
        self._texts = []
        self._current = -1
        self._offset = 0
        self._hold = 0
        self._timer = QTimer(self)
        self._timer.setInterval(35)
        self._timer.timeout.connect(self._tick)

    def _set_text(self, text):
        self._text = text or ""
        self.setToolTip(self._text)
        self._offset = 0
        self._hold = 24
        self._sync_timer()
        self.update()

    def show_tip(self, text):
        self._times = []
        self._texts = []
        self._current = -1
        self._set_text(text)

    def set_lyric(self, raw):
        lines = parse_lrc(raw)
        if not lines:
            self.show_tip("暂无歌词")
            return
        self._times = [stamp for stamp, _ in lines]
        self._texts = [text for _, text in lines]
        self._current = -1
        self._set_text("♪  " + self._texts[0])

    def on_position(self, ms):
        if not self._times:
            return
        pos = ms / 1000.0
        idx = -1
        for i, t in enumerate(self._times):
            if t <= pos + 0.15:
                idx = i
            else:
                break
        if idx == self._current:
            return
        self._current = idx
        if idx >= 0:
            self._set_text(self._texts[idx])

    def _text_width(self):
        return QFontMetrics(self.font()).horizontalAdvance(self._text)

    def _sync_timer(self):
        if not self.isVisible():
            self._timer.stop()
            return
        available = max(self.width() - 40, 1)
        if self._text and self._text_width() > available:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._offset = 0

    def _tick(self):
        if self._hold > 0:
            self._hold -= 1
            return
        self._offset += 1
        if self._offset > self._text_width() + 40:
            self._offset = 0
            self._hold = 24
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_timer()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_timer()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._text:
            return
        painter = QPainter(self)
        painter.setClipRect(self.contentsRect())
        metrics = QFontMetrics(self.font())
        area = self.contentsRect().adjusted(20, 0, -20, 0)
        text_w = metrics.horizontalAdvance(self._text)
        if text_w <= area.width():
            x = area.x() + (area.width() - text_w) // 2
        else:
            x = area.x() - self._offset
        baseline = area.y() + (area.height() + metrics.ascent()
                               - metrics.descent()) // 2
        painter.setPen(QColor(SUB))
        painter.drawText(x, baseline, self._text)
        painter.end()
