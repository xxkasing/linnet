"""搜索结果页"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                             QWidget)

from ..tasks import run_async
from ..ui_metrics import PAGE_MARGINS, PAGE_SPACING
from .songtable import SongTable


class SearchView(QWidget):
    play_requested = pyqtSignal(dict, list)
    open_album = pyqtSignal(object)
    like_requested = pyqtSignal(dict)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.songs = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*PAGE_MARGINS)
        layout.setSpacing(PAGE_SPACING)

        head = QHBoxLayout()
        self.title = QLabel("搜索")
        self.title.setObjectName("Title")
        head.addWidget(self.title)
        head.addStretch()

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        head.addWidget(self.status)

        self.play_all = QPushButton("▶ 播放全部")
        self.play_all.setObjectName("Accent")
        self.play_all.clicked.connect(self._play_all)
        self.play_all.setVisible(False)
        head.addWidget(self.play_all)
        layout.addLayout(head)
        self.table = SongTable()
        self.table.play_requested.connect(self.play_requested.emit)
        self.table.album_requested.connect(self.open_album.emit)
        self.table.like_requested.connect(self.like_requested.emit)
        layout.addWidget(self.table, 1)

        self.hint = QLabel("在右上角输入歌名、歌手，回车搜索")
        self.hint.setObjectName("Hint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint)

    def search(self, keyword):
        self.title.setText("搜索：%s" % keyword)
        self.status.setText("搜索中…")
        self.table.setRowCount(0)
        self.play_all.setVisible(False)
        run_async(lambda: self.client.search_songs(keyword),
                  self._on_result, self._on_error)

    def _on_result(self, songs):
        self.songs = songs
        self.table.set_songs(songs)
        self.status.setText("共 %d 首" % len(songs))
        self.play_all.setVisible(bool(songs))
        self.hint.setVisible(not songs)
        if not songs:
            self.hint.setText("没有搜到结果，换个关键词试试")

    def _on_error(self, message):
        self.status.setText("搜索失败")
        self.hint.setVisible(True)
        self.hint.setText("搜索失败：%s" % message)

    def _play_all(self):
        if self.songs:
            self.play_requested.emit(self.songs[0], self.songs)
