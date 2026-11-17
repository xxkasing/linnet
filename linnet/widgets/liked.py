"""我喜欢的音乐管理页"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                             QWidget)

from ..tasks import run_async
from ..theme import SUB
from ..ui_metrics import ACTION_BUTTON_WIDTH, PAGE_MARGINS, PAGE_SPACING
from .songtable import SongTable


class LikedSongsView(QWidget):
    play_requested = pyqtSignal(dict, list)
    open_album = pyqtSignal(object)
    like_requested = pyqtSignal(dict)
    like_changed = pyqtSignal(dict, bool)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.songs = []
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(*PAGE_MARGINS)
        root.setSpacing(PAGE_SPACING)

        head = QHBoxLayout()
        self.title = QLabel("我喜欢的音乐")
        self.title.setObjectName("Title")
        head.addWidget(self.title)
        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color:{SUB};font-size:12px;")
        head.addWidget(self.count_label)
        head.addStretch()

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.load)
        head.addWidget(self.refresh_btn)

        self.remove_btn = QPushButton("从喜欢中移除")
        self.remove_btn.setObjectName("Link")
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self._remove_selected)
        head.addWidget(self.remove_btn)

        self.play_all = QPushButton("▶ 播放全部")
        self.play_all.setObjectName("Accent")
        self.play_all.setFixedWidth(ACTION_BUTTON_WIDTH)
        self.play_all.setEnabled(False)
        self.play_all.clicked.connect(self._play_all)
        head.addWidget(self.play_all)
        root.addLayout(head)

        self.table = SongTable()
        self.table.play_requested.connect(self.play_requested.emit)
        self.table.album_requested.connect(self.open_album.emit)
        self.table.like_requested.connect(self.like_requested.emit)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.setVisible(False)
        root.addWidget(self.table, 1)

        self.hint = QLabel("登录后查看你喜欢的音乐")
        self.hint.setObjectName("Hint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.hint)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{SUB};font-size:12px;")
        root.addWidget(self.status)

    def load(self):
        if self._loading:
            return
        if not getattr(self.client, "account", None):
            self.songs = []
            self.table.set_songs([])
            self.table.setVisible(False)
            self.play_all.setEnabled(False)
            self.remove_btn.setEnabled(False)
            self.count_label.setText("")
            self.hint.setVisible(True)
            self.hint.setText("登录后查看你喜欢的音乐")
            self.status.setText("")
            return
        self._loading = True
        self.refresh_btn.setEnabled(False)
        self.play_all.setEnabled(False)
        self.remove_btn.setEnabled(False)
        self.hint.setVisible(True)
        self.hint.setText("正在加载喜欢的音乐…")
        self.status.setText("")
        run_async(self.client.liked_songs, self._on_loaded, self._on_error)

    def _on_loaded(self, songs):
        self._loading = False
        self.refresh_btn.setEnabled(True)
        self.songs = list(songs or [])
        self.table.set_songs(self.songs)
        self.table.setVisible(bool(self.songs))
        if self.songs:
            self.layout().activate()
        self.count_label.setText("共 %d 首" % len(self.songs))
        self.play_all.setEnabled(bool(self.songs))
        self.hint.setVisible(not self.songs)
        if not self.songs:
            self.hint.setText("喜欢的音乐是空的；在歌曲列表右键选择“喜欢”即可加入")
        self._update_buttons()
        self.status.setText("右键歌曲可喜欢 / 取消喜欢")

    def _on_error(self, message):
        self._loading = False
        self.refresh_btn.setEnabled(True)
        self.table.setVisible(bool(self.songs))
        self.play_all.setEnabled(bool(self.songs))
        self.hint.setVisible(True)
        self.hint.setText("喜欢的音乐加载失败：%s" % message)
        self.status.setText("")

    def _update_buttons(self):
        has_rows = bool(self.songs)
        has_selection = self.table.current_song() is not None
        self.remove_btn.setEnabled(has_rows and has_selection)
        self.play_all.setEnabled(has_rows)

    def _play_all(self):
        if self.songs:
            self.play_requested.emit(self.songs[0], self.songs)

    def _remove_selected(self):
        song = self.table.current_song()
        if not song:
            self.status.setText("先选中一首喜欢的歌曲")
            return
        if not getattr(self.client, "account", None):
            self.status.setText("请先登录")
            return
        self.remove_btn.setEnabled(False)
        self.status.setText("正在取消喜欢…")
        run_async(lambda: self.client.set_favorite(song.get("id"), False),
                  lambda _ok: self.apply_favorite(song, False),
                  lambda message: self._on_remove_error(message))

    def _on_remove_error(self, message):
        self._update_buttons()
        self.status.setText("取消喜欢失败：%s" % message)

    def apply_favorite(self, song, liked):
        """同步右键“喜欢/取消喜欢”造成的变化"""
        if not song:
            return
        song_id = song.get("id")
        if liked:
            if not any(s.get("id") == song_id for s in self.songs):
                self.songs.insert(0, song)
                self.table.set_songs(self.songs)
        else:
            self.songs = [s for s in self.songs if s.get("id") != song_id]
            self.table.set_songs(self.songs)
        self.table.setVisible(bool(self.songs))
        if self.songs:
            self.layout().activate()
        self.count_label.setText("共 %d 首" % len(self.songs))
        self.hint.setVisible(not self.songs)
        if not self.songs:
            self.hint.setText("喜欢的音乐是空的；在歌曲列表右键选择“喜欢”即可加入")
        self.status.setText("已喜欢《%s》" % song.get("name", "") if liked
                            else "已取消喜欢《%s》" % song.get("name", ""))
        self._update_buttons()
        self.like_changed.emit(song, bool(liked))
