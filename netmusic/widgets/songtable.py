"""歌曲表格控件"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QHeaderView, QMenu, QTableWidget,
                             QTableWidgetItem)

from ..theme import SUB
from ..ui_metrics import TABLE_COLUMNS, TABLE_ROW_HEIGHT
from .player import fmt_time


class SongTable(QTableWidget):
    play_requested = pyqtSignal(dict, list)
    album_requested = pyqtSignal(object)
    like_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(0, 5, parent)
        self.setHorizontalHeaderLabels(["#", "歌曲", "歌手", "专辑", "时长"])
        # 表头与单元格内容按同一基准对齐：# 居中，歌曲/歌手/专辑左对齐，时长右对齐
        for index, alignment in enumerate((
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)):
            item = self.horizontalHeaderItem(index)
            if item is not None:
                item.setTextAlignment(int(alignment))
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setWordWrap(False)
        self.setToolTip("右键歌曲：喜欢 / 取消喜欢；双击专辑列：查看专辑")
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, TABLE_COLUMNS[0])
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, TABLE_COLUMNS[2])
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, TABLE_COLUMNS[3])
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(4, TABLE_COLUMNS[4])
        header.setHighlightSections(False)
        self.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._songs = []
        self.doubleClicked.connect(self._on_double)

    def set_songs(self, songs):
        self._songs = list(songs)
        self.setRowCount(len(self._songs))
        for i, song in enumerate(self._songs):
            self._set_row(i, song)
        if not self._songs:
            self.setRowCount(1)
            hint = QTableWidgetItem("没有内容")
            hint.setForeground(QColor(SUB))
            self.setItem(0, 0, hint)
            for col in range(1, 5):
                self.setItem(0, col, QTableWidgetItem(""))

    def _set_row(self, row, song):
        num = QTableWidgetItem(str(row + 1))
        num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setForeground(QColor(SUB))
        self.setItem(row, 0, num)

        name = QTableWidgetItem(song.get("name", ""))
        name.setToolTip(song.get("name", ""))
        self.setItem(row, 1, name)

        artist = QTableWidgetItem(song.get("artist", ""))
        artist.setForeground(QColor(SUB))
        self.setItem(row, 2, artist)

        album = QTableWidgetItem(song.get("album", ""))
        album.setForeground(QColor(SUB))
        if song.get("album_id"):
            album.setToolTip("双击打开专辑：%s" % song.get("album", ""))
        self.setItem(row, 3, album)

        dur = QTableWidgetItem(fmt_time(song.get("duration") or 0))
        dur.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dur.setForeground(QColor(SUB))
        self.setItem(row, 4, dur)

    def current_song(self):
        row = self.currentRow()
        if 0 <= row < len(self._songs):
            return self._songs[row]
        return None

    def _show_context_menu(self, pos):
        row = self.rowAt(pos.y())
        if not (0 <= row < len(self._songs)):
            return
        song = self._songs[row]
        menu = QMenu(self)
        like_action = menu.addAction("喜欢 / 取消喜欢")
        like_action.triggered.connect(lambda: self.like_requested.emit(song))
        if song.get("album_id"):
            album_action = menu.addAction("查看专辑")
            album_action.triggered.connect(
                lambda: self.album_requested.emit(song.get("album_id")))
        menu.exec(self.viewport().mapToGlobal(pos))

    def _on_double(self, index):
        row = index.row()
        if not (0 <= row < len(self._songs)):
            return
        song = self._songs[row]
        if index.column() == 3 and song.get("album_id"):
            self.album_requested.emit(song.get("album_id"))
            return
        self.play_requested.emit(song, self._songs)
