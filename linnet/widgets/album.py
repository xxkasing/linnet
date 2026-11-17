"""专辑详情页"""
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from ..tasks import run_async
from ..theme import ICON, PANEL_2, SUB, TEXT
from ..ui_metrics import (ACTION_BUTTON_WIDTH, INFO_CARD_COVER,
                          INFO_CARD_MARGINS, PAGE_MARGINS, PAGE_SPACING)
from .covers import load_cover
from .songtable import SongTable


class AlbumView(QWidget):
    play_requested = pyqtSignal(dict, list)
    open_album = pyqtSignal(object)
    back_requested = pyqtSignal()
    like_requested = pyqtSignal(dict)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.album = {}
        self.songs = []

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
        self.title = QLabel("专辑")
        self.title.setObjectName("Title")
        self.title.setWordWrap(True)
        info_col.addWidget(self.title)
        self.artist = QLabel("")
        self.artist.setStyleSheet(f"color:{TEXT};font-size:14px;font-weight:600;")
        info_col.addWidget(self.artist)
        self.meta = QLabel("")
        self.meta.setObjectName("Muted")
        info_col.addWidget(self.meta)
        self.description = QLabel("")
        self.description.setWordWrap(True)
        self.description.setMaximumHeight(60)
        self.description.setStyleSheet(f"color:{SUB};font-size:12px;")
        info_col.addWidget(self.description)
        info_col.addStretch()

        self.play_all = QPushButton("▶ 播放全部")
        self.play_all.setObjectName("Accent")
        self.play_all.setFixedWidth(ACTION_BUTTON_WIDTH)
        self.play_all.setEnabled(False)
        self.play_all.clicked.connect(self._play_all)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.play_all)
        btn_row.addStretch()
        info_col.addLayout(btn_row)
        info_row.addLayout(info_col, 1)
        root.addWidget(card)

        self.table = SongTable()
        self.table.play_requested.connect(self.play_requested.emit)
        self.table.album_requested.connect(self.open_album.emit)
        self.table.like_requested.connect(self.like_requested.emit)
        self.table.setVisible(False)
        root.addWidget(self.table, 1)

        self.hint = QLabel("双击歌曲列表中的专辑名，即可进入这里")
        self.hint.setObjectName("Hint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.hint)

    def load(self, album_id):
        self.album = {}
        self.songs = []
        self.table.set_songs([])
        self.table.setVisible(False)
        self.title.setText("正在加载专辑…")
        self.artist.setText("")
        self.meta.setText("")
        self.description.setText("")
        self.play_all.setEnabled(False)
        self.hint.setVisible(True)
        self.hint.setText("正在加载专辑…")
        load_cover(self.cover, "", INFO_CARD_COVER, radius=14)
        run_async(lambda: self.client.album_detail(album_id),
                  self._on_loaded, self._on_error)

    def _on_loaded(self, album):
        self.album = album or {}
        self.songs = self.album.get("songs") or []
        self.title.setText(self.album.get("name") or "未知专辑")
        self.artist.setText(self.album.get("artist") or "未知歌手")
        pieces = ["%d 首" % len(self.songs)]
        if self.album.get("company"):
            pieces.append(self.album["company"])
        stamp = self.album.get("publish_time") or 0
        if stamp:
            try:
                year = datetime.fromtimestamp(int(stamp) / 1000).year
                pieces.append("%d 年" % year)
            except (TypeError, ValueError, OSError, OverflowError):
                pass
        self.meta.setText(" · ".join(pieces))
        desc = self.album.get("description") or "暂无专辑介绍"
        self.description.setText(desc)
        self.description.setToolTip(desc)
        load_cover(self.cover, self.album.get("cover"),
                   INFO_CARD_COVER, radius=14)
        self.table.set_songs(self.songs)
        self.table.setVisible(bool(self.songs))
        self.play_all.setEnabled(bool(self.songs))
        self.hint.setVisible(not self.songs)
        if not self.songs:
            self.hint.setText("这张专辑没有可显示的歌曲")

    def _on_error(self, message):
        self.title.setText("专辑加载失败")
        self.artist.setText("")
        self.meta.setText("")
        self.description.setText("")
        self.play_all.setEnabled(False)
        self.hint.setVisible(True)
        self.hint.setText("专辑加载失败：%s" % message)

    def _play_all(self):
        if self.songs:
            self.play_requested.emit(self.songs[0], self.songs)
