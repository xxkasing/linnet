"""底部播放控制栏"""
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (QHBoxLayout, QFrame, QLabel, QPushButton,
                             QSizePolicy, QSlider, QVBoxLayout, QWidget)

from ..tasks import run_async
from ..theme import ACCENT, ICON, PANEL_2, SUB, TEXT
from ..ui_metrics import (CONTROL_BUTTON, PLAYER_COVER, PLAYER_HEIGHT,
                          PLAYER_SIDE_WIDTH, PLAY_BUTTON, VOLUME_WIDTH)
from .covers import rounded_pixmap


class CoverLabel(QLabel):
    """播放栏左侧专辑封面，点击后通知主窗口切换歌词栏"""

    clicked = pyqtSignal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ElidedLabel(QLabel):
    """单行歌名/歌手：宽度固定，长文本自动省略，不撑开播放控制区"""

    clicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = text or ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored,
                           QSizePolicy.Policy.Preferred)
        self.setText(self._full_text)

    def setFullText(self, text):
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._update_elide()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elide()

    def _update_elide(self):
        width = max(self.contentsRect().width() - 2, 10)
        metrics = QFontMetrics(self.font())
        self.setText(metrics.elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, width))



def fmt_time(ms):
    if not ms or ms < 0:
        ms = 0
    secs = int(ms) // 1000
    return "%02d:%02d" % (secs // 60, secs % 60)


class SeekSlider(QSlider):
    """点哪跳哪的进度条：单击任意位置立即跳转，按住拖动实时跟随"""

    seek = pyqtSignal(int, bool)   # (0~1000 的位置, 是否已松开)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(0, 1000)
        # 关掉 Qt 默认的“点轨道跳一页”行为，改由下面的鼠标事件接管
        self.setSingleStep(1)
        self.setPageStep(1)
        self.setFixedHeight(20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dragging = False

    def value_at(self, x):
        """把鼠标横坐标换算成滑块值，按手柄中心可移动范围对齐"""
        width = self.width()
        if width <= 0:
            return self.value()
        margin = 7                      # 手柄半径，和主题里的 14px 手柄对应
        span = max(width - margin * 2, 1)
        pos = min(max(x - margin, 0), span)
        return self.minimum() + round(pos / span * (self.maximum() - self.minimum()))

    def _send(self, x, final):
        value = self.value_at(x)
        self.setValue(value)
        self.seek.emit(value, final)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.setSliderDown(True)
            self._send(event.position().x(), False)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._send(event.position().x(), False)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setSliderDown(False)
            self._send(event.position().x(), True)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PlayerBar(QFrame):
    ended = pyqtSignal()
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()
    song_changed = pyqtSignal(dict)
    position_changed = pyqtSignal(int)
    mode_changed = pyqtSignal(str)
    cover_clicked = pyqtSignal()
    comments_requested = pyqtSignal()
    like_requested = pyqtSignal(dict)
    album_requested = pyqtSignal(object)
    artist_requested = pyqtSignal(dict)

    MODE_LABELS = {"order": "顺序", "repeat_one": "单曲", "shuffle": "随机",
                   "intelligence": "心动"}
    MODE_TIPS = {"order": "顺序播放", "repeat_one": "单曲循环",
                 "shuffle": "随机播放", "intelligence": "心动模式"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Player")
        self.setFixedHeight(PLAYER_HEIGHT)
        self._duration = 0
        self._seeking = False
        self._cover_cache = {}
        self.mode = "shuffle"
        self.current_song = None

        self._build()
        self._init_media()
        self.set_like_state(False, False)

    # ---------- UI ----------
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 进度条：单独一行，放在控制栏和上方滚动歌词之间，横向铺满整窗
        seek = QFrame()
        seek.setObjectName("SeekRow")
        seek.setFixedHeight(24)
        seek_row = QHBoxLayout(seek)
        seek_row.setContentsMargins(20, 2, 20, 0)
        seek_row.setSpacing(8)

        self.cur = QLabel("00:00")
        self.cur.setFixedWidth(38)
        self.cur.setAlignment(Qt.AlignmentFlag.AlignLeft |
                              Qt.AlignmentFlag.AlignVCenter)
        self.cur.setStyleSheet(f"color:{SUB};font-size:11px;")
        self.total = QLabel("00:00")
        self.total.setFixedWidth(38)
        self.total.setAlignment(Qt.AlignmentFlag.AlignRight |
                                Qt.AlignmentFlag.AlignVCenter)
        self.total.setStyleSheet(f"color:{SUB};font-size:11px;")
        self.slider = SeekSlider()
        self.slider.setFixedHeight(18)

        seek_row.addWidget(self.cur)
        seek_row.addWidget(self.slider, 1)
        seek_row.addWidget(self.total)
        outer.addWidget(seek)

        # 控制栏：左信息、中间播放键、右侧模式/音量
        controls = QWidget()
        controls.setObjectName("ControlRow")
        row = QHBoxLayout(controls)
        row.setContentsMargins(20, 8, 20, 10)
        row.setSpacing(0)

        # 左右固定同宽，中间运输区两侧等量留白，播放键严格落在窗口正中
        left = QWidget()
        left.setObjectName("PlayerLeft")
        left.setFixedWidth(PLAYER_SIDE_WIDTH)
        left_row = QHBoxLayout(left)
        left_row.setContentsMargins(0, 0, 0, 0)
        left_row.setSpacing(12)

        self.cover = CoverLabel("♪")
        self.cover.setFixedSize(PLAYER_COVER, PLAYER_COVER)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cover.setToolTip("点击把中间内容区切换为歌词页")
        self.cover.setStyleSheet(
            f"background:{PANEL_2};border-radius:10px;color:{ICON};font-size:20px;")
        self.cover.clicked.connect(self.cover_clicked.emit)
        left_row.addWidget(self.cover)

        info_panel = QWidget()
        info = QVBoxLayout(info_panel)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(3)
        self.title = ElidedLabel("未在播放")
        self.title.setStyleSheet(f"color:{TEXT};font-size:15px;font-weight:600;")
        self.title.clicked.connect(self._request_album)
        self.artist = ElidedLabel("")
        self.artist.setStyleSheet(f"color:{SUB};font-size:12px;")
        self.artist.clicked.connect(self._request_artist)
        info.addWidget(self.title)
        info.addWidget(self.artist)
        left_row.addWidget(info_panel, 1)

        transport = QWidget()
        transport.setObjectName("Transport")
        transport.setFixedWidth(132)
        btns = QHBoxLayout(transport)
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(12)
        btns.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prev_btn = QPushButton("◀◀")
        self.prev_btn.setObjectName("Flat")
        self.prev_btn.setFixedSize(32, 32)
        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("PlayBtn")
        self.play_btn.setFixedSize(PLAY_BUTTON, PLAY_BUTTON)
        self.next_btn = QPushButton("▶▶")
        self.next_btn.setObjectName("Flat")
        self.next_btn.setFixedSize(32, 32)
        btns.addWidget(self.prev_btn)
        btns.addWidget(self.play_btn)
        btns.addWidget(self.next_btn)

        right = QWidget()
        right.setObjectName("PlayerRight")
        right.setFixedWidth(PLAYER_SIDE_WIDTH)
        right_row = QHBoxLayout(right)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(0)
        right_row.addStretch(1)
        self.mode_btn = QPushButton(self.MODE_LABELS[self.mode])
        self.mode_btn.setObjectName("ModeBtn")
        self.mode_btn.setFixedSize(*CONTROL_BUTTON)
        self.mode_btn.setToolTip("播放模式：%s（点击切换）" % self.MODE_TIPS[self.mode])
        right_row.addWidget(self.mode_btn)
        right_row.addSpacing(8)
        self.comment_btn = QPushButton("评论")
        self.comment_btn.setObjectName("CommentBtn")
        self.comment_btn.setFixedSize(*CONTROL_BUTTON)
        self.comment_btn.setToolTip("查看/发表当前歌曲评论")
        right_row.addWidget(self.comment_btn)
        right_row.addSpacing(8)
        self.like_btn = QPushButton("♡ 喜欢")
        self.like_btn.setObjectName("LikeBtn")
        self.like_btn.setFixedSize(62, CONTROL_BUTTON[1])
        self.like_btn.setToolTip("喜欢当前歌曲")
        right_row.addWidget(self.like_btn)
        right_row.addSpacing(8)
        vol_icon = QLabel("音量")
        vol_icon.setStyleSheet(f"color:{SUB};font-size:12px;")
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setFixedWidth(VOLUME_WIDTH)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        right_row.addWidget(vol_icon)
        right_row.addSpacing(6)
        right_row.addWidget(self.volume)

        row.addWidget(left)
        row.addStretch(1)
        row.addWidget(transport)
        row.addStretch(1)
        row.addWidget(right)
        outer.addWidget(controls, 1)

        self.prev_btn.clicked.connect(self.prev_requested.emit)
        self.next_btn.clicked.connect(self.next_requested.emit)
        self.play_btn.clicked.connect(self._toggle)
        self.mode_btn.clicked.connect(self._cycle_mode)
        self.comment_btn.clicked.connect(self.comments_requested.emit)
        self.like_btn.clicked.connect(self._request_like)
        self.slider.seek.connect(self._on_seek)
        self.volume.valueChanged.connect(self._on_volume)

    def _init_media(self):
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.7)
        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(self._on_dur)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(self._on_error)

    # ---------- 播放 ----------
    def play_song(self, song, url):
        self.current_song = song
        self.set_like_state(False, True)
        self.title.setFullText(song.get("name", ""))
        self.artist.setFullText(song.get("artist", ""))
        album_id = song.get("album_id")
        if album_id:
            self.title.setToolTip("点击打开专辑：%s" % (song.get("album") or "当前专辑"))
            self.title.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.title.setToolTip("当前歌曲没有专辑信息")
            self.title.setCursor(Qt.CursorShape.ArrowCursor)
        artist_id = song.get("artist_id")
        if artist_id:
            self.artist.setToolTip("点击进入歌手页：%s" % (song.get("artist") or "当前歌手"))
            self.artist.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.artist.setToolTip("当前歌曲没有歌手信息")
            self.artist.setCursor(Qt.CursorShape.ArrowCursor)
        self.cur.setText("00:00")
        self.total.setText(fmt_time(song.get("duration") or 0))
        self._load_cover(song.get("cover"))
        self.player.setSource(QUrl(url))
        self.player.play()
        self.song_changed.emit(song)

    def set_like_state(self, liked, enabled=True):
        """同步播放栏喜欢按钮：空心/实心 + 可点击状态"""
        if not hasattr(self, "like_btn"):
            return
        liked = bool(liked)
        self.like_btn.setText("♥ 喜欢" if liked else "♡ 喜欢")
        self.like_btn.setToolTip("已喜欢，点击取消喜欢"
                                 if liked else "喜欢当前歌曲")
        self.like_btn.setProperty("liked", liked)
        self.like_btn.style().unpolish(self.like_btn)
        self.like_btn.style().polish(self.like_btn)
        self.like_btn.setEnabled(bool(enabled))

    def _request_like(self):
        if self.current_song:
            self.like_requested.emit(self.current_song)

    def _request_album(self):
        song = self.current_song or {}
        self.album_requested.emit(song.get("album_id") or 0)

    def _request_artist(self):
        self.artist_requested.emit(self.current_song or {})

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _toggle(self):
        self.toggle()

    def _cycle_mode(self):
        # 从默认的随机开始，依次切换 随机 → 顺序 → 单曲 → 心动
        order = ("shuffle", "order", "repeat_one", "intelligence")
        self.mode = order[(order.index(self.mode) + 1) % len(order)]
        self.mode_btn.setText(self.MODE_LABELS[self.mode])
        self.mode_btn.setToolTip("播放模式：%s（点击切换）"
                                 % self.MODE_TIPS[self.mode])
        self.mode_changed.emit(self.mode)

    def stop(self):
        self.player.stop()

    def set_volume(self, value):
        self.volume.setValue(value)

    # ---------- 状态回调 ----------
    def _on_pos(self, pos):
        if not self._seeking and self._duration:
            self.slider.setValue(int(pos / self._duration * 1000))
        self.cur.setText(fmt_time(pos))
        self.position_changed.emit(int(pos))

    def _on_dur(self, dur):
        self._duration = max(dur, 0)
        self.total.setText(fmt_time(dur))

    def _on_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("II")
        else:
            self.play_btn.setText("▶")

    def _on_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.ended.emit()

    def _on_error(self, *_):
        self.title.setFullText("播放失败，可能需要在应用内登录")
        self.play_btn.setText("▶")

    def _on_seek(self, value, final):
        """点哪播哪：按下即跳，拖动实时跟随，松开定稿"""
        if not self._duration:
            return
        target = max(int(value / 1000.0 * self._duration), 0)
        self._seeking = not final
        self.cur.setText(fmt_time(target))
        self.player.setPosition(target)

    def _on_volume(self, value):
        self.audio.setVolume(value / 100.0)

    # ---------- 封面 ----------
    def _load_cover(self, url):
        if not url:
            self._cover_placeholder()
            return
        cached = self._cover_cache.get(url)
        if cached is not None:
            self._apply_cover(cached)
            return
        self.cover.setText("…")

        def fetch():
            import requests
            resp = requests.get(url + "?param=120y120", timeout=8)
            resp.raise_for_status()
            return resp.content

        run_async(fetch, lambda data: self._cover_fetched(url, data),
                  lambda _e: self._cover_placeholder())

    def _cover_placeholder(self):
        self.cover.setText("♪")
        self.cover.setPixmap(QPixmap())
        self.cover.setStyleSheet(
            f"background:{PANEL_2};border-radius:10px;color:{ICON};font-size:20px;")

    def _cover_fetched(self, url, data):
        pix = QPixmap()
        pix.loadFromData(data)
        self._cover_cache[url] = pix
        self._apply_cover(pix)

    def _apply_cover(self, pix):
        if pix.isNull():
            self._cover_placeholder()
            return
        self.cover.setStyleSheet("background:transparent;border:none;")
        self.cover.setPixmap(rounded_pixmap(pix, 56, 10))
