"""歌单页：推荐歌单网格 + 歌单详情"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QStackedWidget,
                             QVBoxLayout, QWidget)

from ..tasks import run_async
from ..theme import ICON, PANEL_2, SUB, TEXT
from ..ui_metrics import (ACTION_BUTTON_WIDTH, INFO_CARD_COVER,
                          INFO_CARD_MARGINS, PAGE_MARGINS, PAGE_SPACING,
                          PLAYLIST_CARD_COVER, PLAYLIST_CARD_WIDTH,
                          PLAYLIST_GRID_SPACING)
from .covers import load_cover
from .songtable import SongTable


class PlaylistCard(QWidget):
    # 歌单 id 已经超过 32 位有符号整数范围，用 int 信号会被截断成负数
    clicked = pyqtSignal(object)

    def __init__(self, playlist, parent=None):
        super().__init__(parent)
        self.playlist = playlist
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setObjectName("PlaylistCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(PLAYLIST_CARD_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 10)
        layout.setSpacing(8)

        self.cover = QLabel("♪")
        self.cover.setFixedSize(PLAYLIST_CARD_COVER, PLAYLIST_CARD_COVER)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet(
            f"background:{PANEL_2};border-radius:12px;color:{ICON};font-size:22px;")
        layout.addWidget(self.cover)

        name = QLabel(playlist.get("name", ""))
        name.setWordWrap(True)
        name.setFixedHeight(38)
        name.setStyleSheet(f"color:{TEXT};font-size:13px;font-weight:600;")
        layout.addWidget(name)

        count = QLabel("%d 首 · %s" % (playlist.get("track_count") or 0,
                                       playlist.get("creator") or "推荐"))
        count.setStyleSheet(f"color:{SUB};font-size:11px;")
        count.setToolTip(count.text())
        layout.addWidget(count)

        load_cover(self.cover, playlist.get("cover"),
                   PLAYLIST_CARD_COVER, radius=12)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.playlist["id"])
        super().mouseReleaseEvent(event)


class PlaylistView(QWidget):
    play_requested = pyqtSignal(dict, list)
    open_playlist = pyqtSignal(object)
    open_album = pyqtSignal(object)
    like_requested = pyqtSignal(dict)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client

        root = QVBoxLayout(self)
        root.setContentsMargins(*PAGE_MARGINS)
        root.setSpacing(PAGE_SPACING)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # --- 推荐页 ---
        self.recommend_page = QWidget()
        rec_layout = QVBoxLayout(self.recommend_page)
        rec_layout.setContentsMargins(0, 0, 0, 0)
        rec_layout.setSpacing(PAGE_SPACING)

        rec_head = QHBoxLayout()
        rec_title = QLabel("推荐歌单")
        rec_title.setObjectName("Title")
        rec_head.addWidget(rec_title)
        rec_head.addStretch()
        self.refresh_btn = QPushButton("换一批")
        self.refresh_btn.clicked.connect(self.load_recommend)
        rec_head.addWidget(self.refresh_btn)
        rec_layout.addLayout(rec_head)

        self.rec_scroll = QScrollArea()
        self.rec_scroll.setWidgetResizable(True)
        self.rec_body = QWidget()
        self.rec_grid = QGridLayout(self.rec_body)
        self.rec_grid.setContentsMargins(0, 0, 0, 0)
        self.rec_grid.setSpacing(PLAYLIST_GRID_SPACING)
        self.rec_scroll.setWidget(self.rec_body)
        rec_layout.addWidget(self.rec_scroll, 1)

        self.rec_hint = QLabel("正在加载推荐歌单…")
        self.rec_hint.setObjectName("Hint")
        self.rec_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rec_layout.addWidget(self.rec_hint)
        self.stack.addWidget(self.recommend_page)

        # --- 详情页 ---
        self.detail_page = QWidget()
        det_layout = QVBoxLayout(self.detail_page)
        det_layout.setContentsMargins(0, 0, 0, 0)
        det_layout.setSpacing(PAGE_SPACING)

        back_row = QHBoxLayout()
        back_btn = QPushButton("‹ 返回推荐")
        back_btn.setObjectName("Link")
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        back_row.addWidget(back_btn)
        back_row.addStretch()
        det_layout.addLayout(back_row)

        info_row = QHBoxLayout()
        info_row.setSpacing(18)
        self.detail_cover = QLabel("♪")
        self.detail_cover.setFixedSize(INFO_CARD_COVER, INFO_CARD_COVER)
        self.detail_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_cover.setStyleSheet(
            f"background:{PANEL_2};border-radius:14px;color:{ICON};font-size:24px;")
        info_row.addWidget(self.detail_cover)

        info_col = QVBoxLayout()
        info_col.setSpacing(6)
        self.detail_title = QLabel("")
        self.detail_title.setObjectName("Title")
        self.detail_title.setWordWrap(True)
        self.detail_title.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        info_col.addWidget(self.detail_title)
        self.detail_meta = QLabel("")
        self.detail_meta.setObjectName("Muted")
        info_col.addWidget(self.detail_meta)
        info_col.addStretch()

        self.detail_play_all = QPushButton("▶ 播放全部")
        self.detail_play_all.setObjectName("Accent")
        self.detail_play_all.clicked.connect(self._play_all)
        self.detail_play_all.setFixedWidth(ACTION_BUTTON_WIDTH)
        # 按钮外包一层可伸展的行，避免固定宽度把整列宽度也压到 130px，
        # 导致歌单标题被挤成多行再裁切（看起来像乱码）
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.detail_play_all)
        btn_row.addStretch()
        info_col.addLayout(btn_row)
        info_row.addLayout(info_col, 1)

        info_card = QFrame()
        info_card.setObjectName("InfoCard")
        card_layout = QVBoxLayout(info_card)
        card_layout.setContentsMargins(*INFO_CARD_MARGINS)
        card_layout.setSpacing(0)
        card_layout.addLayout(info_row)
        det_layout.addWidget(info_card)

        self.detail_table = SongTable()
        self.detail_table.play_requested.connect(self.play_requested.emit)
        self.detail_table.album_requested.connect(self.open_album.emit)
        self.detail_table.like_requested.connect(self.like_requested.emit)
        det_layout.addWidget(self.detail_table, 1)
        self.stack.addWidget(self.detail_page)

        self._detail_songs = []
        self.stack.setCurrentIndex(0)

    # ---------- 推荐 ----------
    def load_recommend(self):
        self.rec_hint.setVisible(True)
        self.rec_hint.setText("正在加载推荐歌单…")
        self.refresh_btn.setEnabled(False)
        run_async(lambda: self.client.recommend_playlists(12),
                  self._on_recommend, self._on_recommend_error)

    def _clear_grid(self):
        while self.rec_grid.count():
            item = self.rec_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _on_recommend(self, playlists):
        self.refresh_btn.setEnabled(True)
        self._clear_grid()
        if not playlists:
            self.rec_hint.setVisible(True)
            self.rec_hint.setText("没有拿到推荐歌单，稍后再试")
            return
        self.rec_hint.setVisible(False)
        available = self.rec_scroll.viewport().width()
        if available < 100:
            available = max(self.width() - PAGE_MARGINS[0] - PAGE_MARGINS[2], 0)
        cols = max(3, min(5, (available + PLAYLIST_GRID_SPACING)
                         // (PLAYLIST_CARD_WIDTH + PLAYLIST_GRID_SPACING)))
        for i, playlist in enumerate(playlists):
            card = PlaylistCard(playlist)
            card.clicked.connect(self.open_playlist.emit)
            self.rec_grid.addWidget(card, i // cols, i % cols)

    def _on_recommend_error(self, message):
        self.refresh_btn.setEnabled(True)
        self.rec_hint.setVisible(True)
        self.rec_hint.setText("加载失败：%s" % message)

    # ---------- 每日推荐 / 私人雷达 ----------
    def show_recommend(self):
        self.stack.setCurrentIndex(0)

    def load_daily(self):
        self.stack.setCurrentIndex(1)
        self.detail_title.setText("每日推荐")
        self.detail_meta.setText("正在加载…")
        self.detail_table.set_songs([])
        self._detail_songs = []
        load_cover(self.detail_cover, "", INFO_CARD_COVER, radius=14)
        run_async(self.client.daily_songs, self._on_daily, self._on_daily_error)

    def _on_daily(self, songs):
        if not songs:
            self._on_daily_error("可能未登录，或今天还没生成推荐")
            return
        self._show_songs("每日推荐", "根据你的口味每天更新", songs)

    def _on_daily_error(self, message):
        self.detail_title.setText("每日推荐")
        self.detail_meta.setText("加载失败：%s" % message)

    def load_radar(self):
        self.stack.setCurrentIndex(1)
        self.detail_title.setText("私人雷达")
        self.detail_meta.setText("正在查找今天的雷达歌单…")
        self.detail_table.set_songs([])
        self._detail_songs = []
        run_async(self.client.radar_playlist, self._on_radar, self._on_daily_error)

    def _on_radar(self, playlist_id):
        if not playlist_id:
            self.detail_title.setText("私人雷达")
            self.detail_meta.setText("没有找到雷达歌单，可能未登录或今天还没生成")
            return
        self.load_playlist(playlist_id)

    def _show_songs(self, title, subtitle, songs, cover=""):
        """不走歌单详情的纯歌曲页（每日推荐用）"""
        self.stack.setCurrentIndex(1)
        self.detail_title.setText(title)
        count = len(songs)
        self.detail_meta.setText("%d 首 · %s" % (count, subtitle) if subtitle
                                 else "%d 首" % count)
        self._detail_songs = list(songs)
        self.detail_table.set_songs(self._detail_songs)
        load_cover(self.detail_cover, cover, INFO_CARD_COVER, radius=14)

    # ---------- 详情 ----------
    def load_playlist(self, playlist_id):
        self.stack.setCurrentIndex(1)
        self.detail_title.setText("正在加载…")
        self.detail_meta.setText("")
        self.detail_table.set_songs([])
        self._detail_songs = []
        load_cover(self.detail_cover, "", INFO_CARD_COVER, radius=14)
        run_async(lambda: self.client.playlist_detail(playlist_id),
                  self._on_detail, self._on_detail_error)

    def _on_detail(self, detail):
        if not detail:
            self.detail_title.setText("歌单加载失败")
            return
        self.detail_title.setText(detail.get("name", ""))
        self.detail_meta.setText("%d 首 · %s" % (len(detail.get("tracks") or []),
                                                 detail.get("creator") or "网易云音乐"))
        self._detail_songs = detail.get("tracks") or []
        self.detail_table.set_songs(self._detail_songs)
        load_cover(self.detail_cover, detail.get("cover"),
                   INFO_CARD_COVER, radius=14)

    def _on_detail_error(self, message):
        self.detail_title.setText("歌单加载失败：%s" % message)

    def _play_all(self):
        if self._detail_songs:
            self.play_requested.emit(self._detail_songs[0], self._detail_songs)
