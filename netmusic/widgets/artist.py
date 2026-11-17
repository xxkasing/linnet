"""歌手详情页"""
from datetime import datetime

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


class AlbumCard(QWidget):
    """歌手页的专辑卡片"""

    clicked = pyqtSignal(object)

    def __init__(self, album, parent=None):
        super().__init__(parent)
        self.album = album
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setObjectName("PlaylistCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(PLAYLIST_CARD_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 10)
        layout.setSpacing(6)

        self.cover = QLabel("♪")
        self.cover.setFixedSize(PLAYLIST_CARD_COVER, PLAYLIST_CARD_COVER)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet(
            f"background:{PANEL_2};border-radius:12px;color:{ICON};font-size:22px;")
        layout.addWidget(self.cover)

        name = QLabel(album.get("name", ""))
        name.setWordWrap(True)
        name.setFixedHeight(38)
        name.setStyleSheet(f"color:{TEXT};font-size:13px;font-weight:600;")
        name.setToolTip(album.get("name", ""))
        layout.addWidget(name)

        year = ""
        stamp = album.get("publish_time") or 0
        if stamp:
            try:
                year = str(datetime.fromtimestamp(int(stamp) / 1000).year)
            except (TypeError, ValueError, OSError, OverflowError):
                year = ""
        pieces = []
        if album.get("size"):
            pieces.append("%d 首" % album["size"])
        if year:
            pieces.append(year)
        meta = " · ".join(pieces) or "专辑"
        count = QLabel(meta)
        count.setStyleSheet(f"color:{SUB};font-size:11px;")
        count.setToolTip(meta)
        layout.addWidget(count)

        load_cover(self.cover, album.get("cover"),
                   PLAYLIST_CARD_COVER, radius=12)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.album.get("id"))
        super().mouseReleaseEvent(event)


class ArtistView(QWidget):
    play_requested = pyqtSignal(dict, list)
    open_album = pyqtSignal(object)
    back_requested = pyqtSignal()
    like_requested = pyqtSignal(dict)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.artist = {}
        self.artist_id = 0
        self.fallback_name = ""
        self.songs = []
        self.albums = []
        self._albums_loaded = False
        self._albums_loading = False
        self._bio_return_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(*PAGE_MARGINS)
        root.setSpacing(PAGE_SPACING)

        top = QHBoxLayout()
        self.back_btn = QPushButton("‹ 返回")
        self.back_btn.setObjectName("Link")
        self.back_btn.clicked.connect(self.back_requested.emit)
        top.addWidget(self.back_btn)
        top.addStretch()
        root.addLayout(top)

        card = QFrame()
        card.setObjectName("InfoCard")
        info_row = QHBoxLayout(card)
        info_row.setContentsMargins(*INFO_CARD_MARGINS)
        info_row.setSpacing(18)

        self.cover = QLabel("♪")
        self.cover.setFixedSize(INFO_CARD_COVER, INFO_CARD_COVER)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet(
            f"background:{PANEL_2};border-radius:14px;color:{ICON};font-size:24px;")
        info_row.addWidget(self.cover)

        info_col = QVBoxLayout()
        info_col.setSpacing(6)
        self.title = QLabel("歌手")
        self.title.setObjectName("Title")
        self.title.setWordWrap(True)
        info_col.addWidget(self.title)
        self.subtitle = QLabel("")
        self.subtitle.setStyleSheet(f"color:{TEXT};font-size:14px;font-weight:600;")
        info_col.addWidget(self.subtitle)
        self.meta = QLabel("")
        self.meta.setObjectName("Muted")
        info_col.addWidget(self.meta)
        info_col.addStretch()

        self.play_all = QPushButton("▶ 播放全部")
        self.play_all.setObjectName("Accent")
        self.play_all.setFixedWidth(ACTION_BUTTON_WIDTH)
        self.play_all.setEnabled(False)
        self.play_all.clicked.connect(self._play_all)
        self.bio_link = QPushButton("歌手介绍")
        self.bio_link.setObjectName("Link")
        self.bio_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bio_link.setToolTip("查看歌手介绍")
        self.bio_link.clicked.connect(self._show_bio)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.play_all)
        btn_row.addWidget(self.bio_link)
        btn_row.addStretch()
        info_col.addLayout(btn_row)
        info_row.addLayout(info_col, 1)
        root.addWidget(card)

        # 子页切换：热门歌曲 / 专辑
        self.tabs_bar = QWidget()
        tabs = QHBoxLayout(self.tabs_bar)
        tabs.setContentsMargins(0, 0, 0, 0)
        tabs.setSpacing(8)
        self.songs_tab = QPushButton("热门歌曲")
        self.songs_tab.setObjectName("PillTab")
        self.songs_tab.setCheckable(True)
        self.songs_tab.setChecked(True)
        self.songs_tab.clicked.connect(self._show_songs)
        self.albums_tab = QPushButton("专辑")
        self.albums_tab.setObjectName("PillTab")
        self.albums_tab.setCheckable(True)
        self.albums_tab.clicked.connect(self._show_albums)
        tabs.addWidget(self.songs_tab)
        tabs.addWidget(self.albums_tab)
        tabs.addStretch()
        root.addWidget(self.tabs_bar)

        self.body = QStackedWidget()

        # 歌曲子页
        self.songs_page = QWidget()
        songs_layout = QVBoxLayout(self.songs_page)
        songs_layout.setContentsMargins(0, 0, 0, 0)
        songs_layout.setSpacing(0)
        self.table = SongTable()
        self.table.play_requested.connect(self.play_requested.emit)
        self.table.album_requested.connect(self.open_album.emit)
        self.table.like_requested.connect(self.like_requested.emit)
        self.table.setVisible(False)
        songs_layout.addWidget(self.table, 1)
        self.hint = QLabel("")
        self.hint.setObjectName("Hint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        songs_layout.addWidget(self.hint)
        self.body.addWidget(self.songs_page)

        # 专辑子页
        self.albums_page = QWidget()
        albums_layout = QVBoxLayout(self.albums_page)
        albums_layout.setContentsMargins(0, 0, 0, 0)
        albums_layout.setSpacing(0)
        self.albums_scroll = QScrollArea()
        self.albums_scroll.setWidgetResizable(True)
        self.albums_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.albums_body = QWidget()
        self.albums_grid = QGridLayout(self.albums_body)
        self.albums_grid.setContentsMargins(0, 0, 0, 0)
        self.albums_grid.setSpacing(PLAYLIST_GRID_SPACING)
        self.albums_grid.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.albums_scroll.setWidget(self.albums_body)
        albums_layout.addWidget(self.albums_scroll, 1)
        self.albums_hint = QLabel("点击「专辑」查看歌手的全部专辑")
        self.albums_hint.setObjectName("Hint")
        self.albums_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        albums_layout.addWidget(self.albums_hint)
        self.albums_scroll.setVisible(False)
        self.body.addWidget(self.albums_page)

        # 歌手介绍子页
        self.bio_page = QWidget()
        bio_layout = QVBoxLayout(self.bio_page)
        bio_layout.setContentsMargins(0, 0, 0, 0)
        bio_layout.setSpacing(0)

        bio_head = QHBoxLayout()
        bio_head.setSpacing(10)
        self.bio_title = QLabel("歌手介绍")
        self.bio_title.setObjectName("Title")
        bio_head.addWidget(self.bio_title)
        bio_head.addStretch()
        self.bio_close_btn = QPushButton("× 关闭")
        self.bio_close_btn.setObjectName("Link")
        self.bio_close_btn.setFixedWidth(76)
        self.bio_close_btn.setToolTip("关闭歌手介绍")
        self.bio_close_btn.clicked.connect(self._close_bio)
        bio_head.addWidget(self.bio_close_btn)
        bio_layout.addLayout(bio_head)

        self.bio_scroll = QScrollArea()
        self.bio_scroll.setWidgetResizable(True)
        self.bio_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.bio_body = QWidget()
        bio_body_layout = QVBoxLayout(self.bio_body)
        bio_body_layout.setContentsMargins(0, 10, 0, 0)
        bio_body_layout.setSpacing(0)
        self.bio_text = QLabel("正在加载歌手介绍…")
        self.bio_text.setWordWrap(True)
        self.bio_text.setTextFormat(Qt.TextFormat.PlainText)
        self.bio_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.bio_text.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.bio_text.setStyleSheet(f"color:{TEXT};font-size:13px;")
        bio_body_layout.addWidget(self.bio_text, 0, Qt.AlignmentFlag.AlignTop)
        bio_body_layout.addStretch(1)
        self.bio_scroll.setWidget(self.bio_body)
        bio_layout.addWidget(self.bio_scroll, 1)
        self.body.addWidget(self.bio_page)

        root.addWidget(self.body, 1)
        self._show_songs()

    # ---------- 子页切换 ----------
    def _show_songs(self):
        self.tabs_bar.setVisible(True)
        self.songs_tab.setChecked(True)
        self.albums_tab.setChecked(False)
        self.body.setCurrentIndex(0)

    def _show_albums(self):
        self.tabs_bar.setVisible(True)
        self.songs_tab.setChecked(False)
        self.albums_tab.setChecked(True)
        self.body.setCurrentIndex(1)
        if self._albums_loaded or self._albums_loading or not self.artist_id:
            return
        self._albums_loading = True
        self.albums_scroll.setVisible(False)
        self.albums_hint.setVisible(True)
        self.albums_hint.setText("正在加载专辑…")
        run_async(lambda: self.client.artist_albums(self.artist_id),
                  self._on_albums_loaded, self._on_albums_error)

    def _show_bio(self):
        current = self.body.currentIndex()
        if current >= 2:
            return
        self._bio_return_index = current
        self.tabs_bar.setVisible(False)
        self.body.setCurrentIndex(2)
        self.bio_scroll.verticalScrollBar().setValue(0)

    def _close_bio(self):
        index = self._bio_return_index
        if index not in (0, 1):
            index = 0
        self.tabs_bar.setVisible(True)
        self.body.setCurrentIndex(index)
        if index == 1:
            self.songs_tab.setChecked(False)
            self.albums_tab.setChecked(True)
        else:
            self.songs_tab.setChecked(True)
            self.albums_tab.setChecked(False)

    def _clear_albums(self):
        while self.albums_grid.count():
            item = self.albums_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_albums_loaded(self, albums):
        self._albums_loading = False
        self._albums_loaded = True
        self.albums = albums or []
        self.albums_tab.setText(
            "专辑 · %d" % len(self.albums) if self.albums else "专辑")
        self._clear_albums()
        if not self.albums:
            self.albums_scroll.setVisible(False)
            self.albums_hint.setVisible(True)
            self.albums_hint.setText("这位歌手暂时没有可显示的专辑")
            return
        self.albums_hint.setVisible(False)
        self.albums_scroll.setVisible(True)
        available = self.albums_scroll.viewport().width()
        if available < 100:
            available = max(self.width() - PAGE_MARGINS[0] - PAGE_MARGINS[2], 0)
        cols = max(3, min(5, (available + PLAYLIST_GRID_SPACING)
                         // (PLAYLIST_CARD_WIDTH + PLAYLIST_GRID_SPACING)))
        for i, album in enumerate(self.albums):
            card = AlbumCard(album)
            card.clicked.connect(self.open_album.emit)
            self.albums_grid.addWidget(card, i // cols, i % cols)
        self.albums_page.layout().activate()

    def _on_albums_error(self, message):
        self._albums_loading = False
        self._albums_loaded = False
        self.albums_scroll.setVisible(False)
        self.albums_hint.setVisible(True)
        self.albums_hint.setText("专辑加载失败：%s" % message)

    # ---------- 歌手页 ----------
    def load(self, artist_id, name=""):
        self.artist = {}
        self.artist_id = artist_id or 0
        self.fallback_name = name or ""
        self.songs = []
        self.albums = []
        self._albums_loaded = False
        self._albums_loading = False
        self._bio_return_index = 0
        self._clear_albums()
        self.table.set_songs([])
        self.table.setVisible(False)
        self.title.setText(self.fallback_name or "正在加载歌手…")
        self.subtitle.setText("")
        self.meta.setText("")
        self.bio_text.setText("正在加载歌手介绍…")
        self.tabs_bar.setVisible(True)
        self.play_all.setEnabled(False)
        self.hint.setVisible(True)
        self.hint.setText("正在加载歌手…")
        self.albums_tab.setText("专辑")
        self.albums_scroll.setVisible(False)
        self.albums_hint.setVisible(True)
        self.albums_hint.setText("点击「专辑」查看歌手的全部专辑")
        self._show_songs()
        load_cover(self.cover, "", INFO_CARD_COVER, radius=14)
        if not self.artist_id:
            self._on_error("缺少歌手 ID")
            return
        run_async(lambda: self.client.artist_detail(self.artist_id,
                                                    self.fallback_name),
                  self._on_loaded, self._on_error)

    def _on_loaded(self, artist):
        self.artist = artist or {}
        self.songs = self.artist.get("songs") or []
        name = self.artist.get("name") or self.fallback_name or "未知歌手"
        self.title.setText(name)
        alias = self.artist.get("alias") or ""
        self.subtitle.setText(alias if alias else "歌手")
        pieces = []
        if self.artist.get("music_size"):
            pieces.append("%d 首作品" % self.artist["music_size"])
        if self.artist.get("album_size"):
            pieces.append("%d 张专辑" % self.artist["album_size"])
        if not pieces:
            pieces.append("%d 首热歌" % len(self.songs))
        self.meta.setText(" · ".join(pieces))
        desc = self.artist.get("description") or "暂无歌手介绍"
        self.bio_text.setText(desc)
        load_cover(self.cover, self.artist.get("cover"),
                   INFO_CARD_COVER, radius=14)
        self.table.set_songs(self.songs)
        self.table.setVisible(bool(self.songs))
        self.layout().activate()
        self.play_all.setEnabled(bool(self.songs))
        self.hint.setVisible(not self.songs)
        if not self.songs:
            self.hint.setText("这位歌手暂时没有可显示的歌曲")
        if self.artist.get("album_size"):
            self.albums_tab.setText("专辑 · %d" % self.artist["album_size"])

    def _on_error(self, message):
        self.title.setText("歌手加载失败")
        self.subtitle.setText("")
        self.meta.setText("")
        self.bio_text.setText("暂无歌手介绍")
        self.play_all.setEnabled(False)
        self.table.set_songs([])
        self.table.setVisible(False)
        self.hint.setVisible(True)
        self.hint.setText("歌手页加载失败：%s" % message)

    def _play_all(self):
        if self.songs:
            self.play_requested.emit(self.songs[0], self.songs)
