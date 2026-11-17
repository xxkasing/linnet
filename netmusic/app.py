"""主窗口"""
import os
import random

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QColor, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMainWindow,
                             QPushButton, QSplitter, QStackedWidget,
                             QVBoxLayout, QWidget)

from .api import NeteaseClient
from .tasks import run_async
from .theme import ACCENT, SUB, TEXT
from .ui_metrics import (MIN_WINDOW_SIZE, SIDEBAR_WIDTH, TOPBAR_HEIGHT,
                         WINDOW_SIZE)
from .widgets.login import LoginDialog
from .widgets.comments import CommentsDialog
from .widgets.lyrics import FullLyricsView, LyricTicker
from .widgets.player import PlayerBar
from .widgets.playlists import PlaylistView
from .widgets.search import SearchView
from .widgets.album import AlbumView
from .widgets.artist import ArtistView
from .widgets.liked import LikedSongsView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.client = NeteaseClient()
        self.queue = []
        self.queue_index = -1
        self.play_mode = "shuffle"
        self._intel_busy = False
        self._lyrics_open = False
        self._last_content_index = 0
        self._album_return_index = 0
        self._artist_return_index = 0
        self._ticker_enabled = False

        self.setWindowTitle("Linnet")
        self.resize(*WINDOW_SIZE)
        self.setMinimumSize(*MIN_WINDOW_SIZE)
        # 不依赖 GNOME 的浅色窗口边框/标题栏，深色下保持整窗统一
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        self._build_ui()
        self._bind_signals()
        self._load_account()
        self.playlist_view.load_recommend()

        self.client.on_switch(self._on_route_switch)

    def _on_route_switch(self, capability, old, new):
        """接口自动切换时提示用户"""
        names = {"search": "搜索", "song_url": "播放地址", "lyric": "歌词",
                 "playlist": "歌单", "recommend": "推荐歌单",
                 "user_playlists": "我的歌单", "account": "账号",
                 "qr_unikey": "扫码登录", "qr_check": "扫码状态"}
        self.status_label.setText(
            "已自动切换接口：%s %s → %s" % (names.get(capability, capability), old, new))

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_topbar())

        body = QSplitter(Qt.Orientation.Horizontal)
        self.body = body

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFixedWidth(SIDEBAR_WIDTH)
        self._fill_nav()
        body.addWidget(self.nav)

        self.content = QStackedWidget()
        self.playlist_view = PlaylistView(self.client)
        self.search_view = SearchView(self.client)
        self.full_lyrics = FullLyricsView()
        self.album_view = AlbumView(self.client)
        self.artist_view = ArtistView(self.client)
        self.liked_view = LikedSongsView(self.client)
        self.content.addWidget(self.playlist_view)   # 0
        self.content.addWidget(self.search_view)     # 1
        self.content.addWidget(self.full_lyrics)     # 2
        self.content.addWidget(self.album_view)      # 3
        self.content.addWidget(self.liked_view)      # 4
        self.content.addWidget(self.artist_view)     # 5
        body.addWidget(self.content)

        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setSizes([SIDEBAR_WIDTH, WINDOW_SIZE[0] - SIDEBAR_WIDTH])
        root.addWidget(body, 1)

        self.lyric_ticker = LyricTicker()
        self.lyric_ticker.hide()
        root.addWidget(self.lyric_ticker)

        self.player = PlayerBar()
        root.addWidget(self.player)

    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(TOPBAR_HEIGHT)
        self.topbar = bar
        bar.installEventFilter(self)
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 10, 20, 10)
        row.setSpacing(14)

        brand_icon = QLabel()
        brand_icon.setFixedSize(26, 26)
        brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_icon.setStyleSheet("background:transparent;border:none;")
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "assets", "linnet.png")
        icon_pix = QPixmap(icon_path)
        if not icon_pix.isNull():
            brand_icon.setPixmap(icon_pix.scaled(
                26, 26, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            brand_icon.setText("♪")
            brand_icon.setStyleSheet(
                f"color:{ACCENT};font-size:24px;font-weight:700;")
        brand = QLabel("Linnet")
        brand.setStyleSheet(
            f"color:{TEXT};font-size:20px;font-weight:700;")
        for label in (brand_icon, brand):
            label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        row.addWidget(brand_icon)
        row.addWidget(brand)
        row.addStretch()

        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setPlaceholderText("搜索歌曲、歌手")
        self.search_box.setFixedWidth(300)
        self.search_box.returnPressed.connect(self._do_search)
        row.addWidget(self.search_box)

        search_btn = QPushButton("搜索")
        search_btn.setObjectName("Accent")
        search_btn.clicked.connect(self._do_search)
        row.addWidget(search_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color:{SUB};font-size:12px;")
        self.status_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        row.addWidget(self.status_label)

        self.login_btn = QPushButton("登录")
        self.login_btn.setObjectName("Link")
        self.login_btn.setFixedWidth(88)
        self.login_btn.clicked.connect(self._open_login)
        row.addWidget(self.login_btn)

        # 去掉系统标题栏后，保留最小化 / 最大化 / 关闭三个窗口按钮
        for text, slot, name in (
                ("—", self.showMinimized, "WindowBtn"),
                ("□", self._toggle_maximized, "WindowBtn"),
                ("×", self.close, "WindowBtnClose")):
            btn = QPushButton(text)
            btn.setObjectName(name)
            btn.setFixedSize(28, 28)
            btn.setToolTip({"—": "最小化", "□": "最大化/还原", "×": "关闭"}[text])
            btn.clicked.connect(slot)
            row.addWidget(btn)
        return bar

    def _toggle_maximized(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def eventFilter(self, obj, event):
        """顶部栏空白区域拖动窗口；双击最大化/还原"""
        if obj is getattr(self, "topbar", None):
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    handle = self.windowHandle()
                    if handle is not None:
                        handle.startSystemMove()
                    return True
            elif event.type() == QEvent.Type.MouseButtonDblClick:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._toggle_maximized()
                    return True
        return super().eventFilter(obj, event)

    def _fill_nav(self):
        self.nav.clear()
        fixed = [("发现音乐", "discover"), ("每日推荐", "daily"),
                 ("私人雷达", "radar"), ("搜索结果", "search"),
                 ("我喜欢的音乐", "liked")]
        for text, key in fixed:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(item)

        sep = QListWidgetItem("我的歌单")
        sep.setFlags(Qt.ItemFlag.NoItemFlags)
        sep.setForeground(QColor(SUB))
        self.nav.addItem(sep)
        self.nav_sep_index = len(fixed)
        self.nav.setCurrentRow(0)

    def _bind_signals(self):
        self.nav.currentRowChanged.connect(self._on_nav)
        self.search_view.play_requested.connect(self.play)
        self.search_view.open_album.connect(self._open_album)
        self.search_view.like_requested.connect(self._toggle_like_from_row)
        self.playlist_view.play_requested.connect(self.play)
        self.playlist_view.open_playlist.connect(self._open_playlist)
        self.playlist_view.open_album.connect(self._open_album)
        self.playlist_view.like_requested.connect(self._toggle_like_from_row)
        self.album_view.play_requested.connect(self.play)
        self.album_view.open_album.connect(self._open_album)
        self.album_view.back_requested.connect(self._close_album)
        self.album_view.like_requested.connect(self._toggle_like_from_row)
        self.artist_view.play_requested.connect(self.play)
        self.artist_view.open_album.connect(self._open_album)
        self.artist_view.back_requested.connect(self._close_artist)
        self.artist_view.like_requested.connect(self._toggle_like_from_row)
        self.liked_view.play_requested.connect(self.play)
        self.liked_view.open_album.connect(self._open_album)
        self.liked_view.like_requested.connect(self._toggle_like_from_row)
        self.liked_view.like_changed.connect(self._on_liked_changed)
        self.player.ended.connect(self._on_ended)
        self.player.next_requested.connect(self.play_next)
        self.player.prev_requested.connect(self.play_prev)
        self.player.mode_changed.connect(self._on_mode_changed)
        self.player.song_changed.connect(self._on_song_changed)
        self.player.cover_clicked.connect(self._toggle_full_lyrics)
        self.player.comments_requested.connect(self._open_comments)
        self.player.like_requested.connect(self._toggle_like_from_row)
        self.player.album_requested.connect(self._open_album)
        self.player.artist_requested.connect(self._open_artist_from_song)
        self.player.position_changed.connect(self._on_position)

        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)

    def keyPressEvent(self, event):
        """空格控制播放/暂停（输入框内不拦截）"""
        if event.key() == Qt.Key.Key_Space:
            focus = self.focusWidget()
            if not isinstance(focus, QLineEdit):
                self.player.toggle()
                return
        super().keyPressEvent(event)

    # ---------------- 账号 ----------------
    def _load_account(self):
        run_async(self.client.fetch_account, self._on_account)

    def _on_account(self, account):
        if account:
            name = account.get("nickname") or "已登录"
            self.login_btn.setText("退出登录")
            self.status_label.setText("已登录：%s" % name)
            self.login_btn.clicked.disconnect()
            self.login_btn.clicked.connect(self._logout)
            self._load_user_playlists()
            self._refresh_player_like_state()
        else:
            self.status_label.setText("未登录（部分歌曲无法播放）")

    def _open_login(self):
        dialog = LoginDialog(self.client, self)
        if dialog.exec():
            self._on_account(self.client.account)
            self.status_label.setText("登录成功")
        else:
            self._load_account()

    def _logout(self):
        self.client.logout()
        self.login_btn.clicked.disconnect()
        self.login_btn.clicked.connect(self._open_login)
        self.login_btn.setText("登录")
        self.status_label.setText("已退出登录")
        self._rebuild_nav_playlists([])
        self.liked_view.load()
        self._refresh_player_like_state()

    def _load_user_playlists(self):
        run_async(self.client.user_playlists, self._rebuild_nav_playlists,
                  lambda _e: None)

    def _rebuild_nav_playlists(self, playlists):
        while self.nav.count() > self.nav_sep_index + 1:
            self.nav.takeItem(self.nav.count() - 1)
        for playlist in playlists or []:
            item = QListWidgetItem("  " + playlist.get("name", ""))
            item.setData(Qt.ItemDataRole.UserRole, playlist.get("id"))
            item.setToolTip(playlist.get("name", ""))
            self.nav.addItem(item)

    # ---------------- 导航 ----------------
    def _on_nav(self, row):
        self._leave_lyrics_view()
        item = self.nav.item(row)
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key == "discover":
            self.content.setCurrentIndex(0)
            self.playlist_view.show_recommend()
        elif key == "daily":
            self.content.setCurrentIndex(0)
            self.playlist_view.load_daily()
        elif key == "radar":
            self.content.setCurrentIndex(0)
            self.playlist_view.load_radar()
        elif key == "search":
            self.content.setCurrentIndex(1)
        elif key == "liked":
            self.content.setCurrentIndex(4)
            self.liked_view.load()
        elif isinstance(key, int):
            self.content.setCurrentIndex(0)
            self.playlist_view.load_playlist(key)

    def _open_playlist(self, playlist_id):
        self._leave_lyrics_view()
        self.content.setCurrentIndex(0)
        self.playlist_view.load_playlist(playlist_id)

    def _open_album(self, album_id):
        if not album_id:
            self.status_label.setText("当前歌曲没有专辑信息")
            return
        self._leave_lyrics_view()
        current = self.content.currentIndex()
        if current != 3:
            self._album_return_index = (
                self._last_content_index if current == 2 else current)
        self.content.setCurrentIndex(3)
        self.album_view.load(album_id)

    def _close_album(self):
        self.content.setCurrentIndex(self._album_return_index
                                     if self._album_return_index != 3 else 0)

    def _open_artist_from_song(self, song):
        song = song or {}
        artist_id = song.get("artist_id")
        name = song.get("artist") or ""
        if not artist_id:
            self.status_label.setText("当前歌曲没有歌手信息")
            return
        self._open_artist(artist_id, name)

    def _open_artist(self, artist_id, name=""):
        if not artist_id:
            self.status_label.setText("当前歌曲没有歌手信息")
            return
        self._leave_lyrics_view()
        current = self.content.currentIndex()
        if current != 5:
            self._artist_return_index = (
                self._last_content_index if current == 2 else current)
        self.content.setCurrentIndex(5)
        self.artist_view.load(artist_id, name)

    def _close_artist(self):
        self.content.setCurrentIndex(self._artist_return_index
                                     if self._artist_return_index != 5 else 0)

    def _focus_search(self):
        self.search_box.setFocus()
        self.search_box.selectAll()

    def _do_search(self):
        keyword = self.search_box.text().strip()
        if not keyword:
            return
        self._leave_lyrics_view()
        self.content.setCurrentIndex(1)
        self.nav.setCurrentRow(3)
        self.search_view.search(keyword)

    # ---------------- 播放 ----------------
    def play(self, song, queue=None):
        if queue:
            self.queue = list(queue)
            self.queue_index = next(
                (i for i, s in enumerate(self.queue)
                 if s.get("id") == song.get("id")), 0)
        self.status_label.setText("正在获取播放地址：%s" % song.get("name", ""))

        def resolve():
            return self.client.song_url(song.get("id"))

        run_async(resolve, lambda url: self._start(song, url),
                  lambda message: self.status_label.setText("获取播放地址失败：%s" % message))

    def _start(self, song, url):
        if not url:
            self.status_label.setText("《%s》无法播放（需要登录或 VIP）" % song.get("name", ""))
            return
        self.status_label.setText("")
        self.player.play_song(song, url)

    def _on_mode_changed(self, mode):
        self.play_mode = mode
        tips = {"order": "顺序播放", "repeat_one": "单曲循环",
                "shuffle": "随机播放", "intelligence": "心动模式"}
        self.status_label.setText("播放模式：%s" % tips.get(mode, mode))
        if mode == "intelligence":
            self._start_intelligence()

    def _start_intelligence(self):
        """心动模式：以当前歌曲为种子，让服务端生成一组歌"""
        if not self.queue:
            self.status_label.setText("心动模式：先播放一首歌再切换过来")
            return
        if self._intel_busy:
            return
        seed = self.queue[self.queue_index]
        self._intel_busy = True
        self.status_label.setText(
            "心动模式：正在根据《%s》生成歌单…" % seed.get("name", ""))
        run_async(lambda: self.client.intelligence_list(seed.get("id")),
                  lambda songs: self._on_intelligence(songs, seed),
                  self._on_intelligence_error)

    def _on_intelligence(self, songs, seed):
        self._intel_busy = False
        if not songs:
            self.status_label.setText("心动模式：没拿到歌曲，已保持原队列")
            return
        ids = [song.get("id") for song in songs]
        if seed and seed.get("id") in ids:
            self.queue = list(songs)
            self.queue_index = ids.index(seed["id"])
        elif seed:
            self.queue = [seed] + list(songs)
            self.queue_index = 0
        else:
            self.queue = list(songs)
            self.queue_index = 0
        self.status_label.setText("心动模式：已生成 %d 首歌" % len(self.queue))

    def _on_intelligence_error(self, message):
        self._intel_busy = False
        self.status_label.setText("心动模式获取失败：%s" % message)

    def _on_ended(self):
        """一首歌自然播完后的行为，按当前播放模式决定"""
        if not self.queue:
            return
        if self.play_mode == "repeat_one":
            self.player.player.setPosition(0)
            self.player.player.play()
            return
        if self.play_mode == "shuffle":
            self.play_random()
            return
        if self.play_mode == "intelligence":
            self.play_next()
            return
        if self.queue_index + 1 >= len(self.queue):
            self.status_label.setText("已播放到列表末尾")
            return
        self.queue_index += 1
        self.play(self.queue[self.queue_index])

    def play_next(self):
        if not self.queue:
            return
        if self.play_mode == "shuffle":
            self.play_random()
            return
        self.queue_index = (self.queue_index + 1) % len(self.queue)
        self.play(self.queue[self.queue_index])

    def play_prev(self):
        if not self.queue:
            return
        if self.play_mode == "shuffle":
            self.play_random()
            return
        self.queue_index = max(0, self.queue_index - 1)
        self.play(self.queue[self.queue_index])

    def play_random(self):
        """随机挑一首，避免连续重复同一首"""
        if not self.queue:
            return
        if len(self.queue) == 1:
            index = 0
        else:
            index = self.queue_index
            while index == self.queue_index:
                index = random.randrange(len(self.queue))
        self.queue_index = index
        self.play(self.queue[index])

    def _on_song_changed(self, song):
        self._ticker_enabled = True
        self._refresh_player_like_state(song)
        if not self._lyrics_open:
            self.lyric_ticker.show()
        self.lyric_ticker.show_tip("正在加载歌词…")
        self.full_lyrics.show_tip("正在加载歌词…")
        run_async(lambda: self.client.lyric(song.get("id")),
                  self._on_lyrics,
                  self._on_lyrics_error)

    def _refresh_player_like_state(self, song=None):
        """播放栏喜欢按钮：按当前歌曲同步真实喜欢状态"""
        song = song or getattr(self.player, "current_song", None)
        if not song or not song.get("id"):
            self.player.set_like_state(False, False)
            return
        if not getattr(self.client, "account", None):
            self.player.set_like_state(False, True)
            return
        song_id = song.get("id")
        if self.client._liked_ids is None:
            self.player.set_like_state(False, True)
            run_async(lambda: (self.client.liked_song_ids(),
                               self.client.is_favorite(song_id))[1],
                      lambda active: self._apply_player_like_state(song_id, active),
                      lambda _error: None)
            return
        self.player.set_like_state(
            self.client.is_favorite(song_id), True)

    def _apply_player_like_state(self, song_id, liked):
        current = getattr(self.player, "current_song", None)
        if current and current.get("id") == song_id:
            self.player.set_like_state(bool(liked), True)

    def _on_liked_changed(self, song, liked):
        current = getattr(self.player, "current_song", None)
        if current and song and current.get("id") == song.get("id"):
            self.player.set_like_state(bool(liked), True)

    def _on_lyrics(self, raw):
        self.full_lyrics.set_lyric(raw)
        self.lyric_ticker.set_lyric(raw)

    def _on_lyrics_error(self, _error):
        self.full_lyrics.show_tip("暂无歌词")
        self.lyric_ticker.show_tip("暂无歌词")

    def _on_position(self, ms):
        self.full_lyrics.on_position(ms)
        self.lyric_ticker.on_position(ms)

    def _leave_lyrics_view(self):
        if self._lyrics_open:
            self._lyrics_open = False
            if self._ticker_enabled:
                self.lyric_ticker.show()

    def _toggle_full_lyrics(self):
        """点击播放栏专辑封面：把中间内容区切换成整块歌词页"""
        if self.content.currentIndex() == 2:
            self._lyrics_open = False
            self.content.setCurrentIndex(self._last_content_index)
            if self._ticker_enabled:
                self.lyric_ticker.show()
        else:
            self._last_content_index = self.content.currentIndex()
            self._lyrics_open = True
            self.lyric_ticker.hide()
            self.content.setCurrentIndex(2)

    def _open_comments(self):
        song = getattr(self.player, "current_song", None)
        if not song or not song.get("id"):
            self.status_label.setText("先播放一首歌，再查看评论")
            return
        dialog = CommentsDialog(self.client, song, self)
        dialog.exec()

    # ---------------- 我喜欢的音乐 ----------------
    def _toggle_like_from_row(self, song):
        """歌曲列表右键“喜欢 / 取消喜欢”"""
        if not song or not song.get("id"):
            return
        if not self.client.account:
            self.status_label.setText("请先登录后再管理喜欢的音乐")
            self._open_login()
            return
        song_id = song.get("id")
        if self.client._liked_ids is None:
            self.status_label.setText("正在同步喜欢的音乐…")
            run_async(lambda: (self.client.liked_song_ids(),
                               self.client.is_favorite(song_id))[1],
                      lambda active: self._apply_like_from_row(song, active),
                      lambda message: self._on_like_error(message))
            return
        self._apply_like_from_row(song, self.client.is_favorite(song_id))

    def _apply_like_from_row(self, song, current):
        liked = not bool(current)
        self.status_label.setText("正在%s《%s》…" % (
            "喜欢" if liked else "取消喜欢", song.get("name", "")))
        run_async(lambda: self.client.set_favorite(song.get("id"), liked),
                  lambda _result: self._on_like_result(song, liked),
                  lambda message: self._on_like_error(message))

    def _on_like_result(self, song, liked):
        self.liked_view.apply_favorite(song, bool(liked))
        current = getattr(self.player, "current_song", None)
        if current and song and current.get("id") == song.get("id"):
            self.player.set_like_state(bool(liked), True)
        self.status_label.setText("%s《%s》" % (
            "已喜欢" if liked else "已取消喜欢", song.get("name", "")))

    def _on_like_error(self, message):
        self.status_label.setText("喜欢操作失败：%s" % message)
