"""歌曲评论对话框：查看热门/最新评论，登录后发表评论"""
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel,
                             QPushButton, QPlainTextEdit, QScrollArea,
                             QVBoxLayout, QWidget)

from ..tasks import run_async
from ..theme import ACCENT, LINE, PANEL, PANEL_2, SUB, TEXT

_AVATAR_COLORS = (
    "#5B8FF9", "#61DDAA", "#65789B", "#F6BD16",
    "#7262FD", "#78D3F8", "#9661BC", "#F6903D",
)


def _short_count(value):
    try:
        value = int(value or 0)
    except (TypeError, ValueError):
        return "0"
    if value >= 10000:
        return "%.1f万" % (value / 10000.0)
    return str(value)


def _time_text(value, fallback=""):
    try:
        stamp = int(value or 0)
    except (TypeError, ValueError):
        stamp = 0
    if stamp > 10 ** 12:
        stamp //= 1000
    if not stamp:
        return fallback or ""
    try:
        moment = datetime.fromtimestamp(stamp)
    except (OverflowError, OSError, ValueError):
        return fallback or ""
    if moment.date() == datetime.now().date():
        return "今天 %02d:%02d" % (moment.hour, moment.minute)
    return moment.strftime("%Y-%m-%d")


def _avatar_color(name):
    return _AVATAR_COLORS[sum(ord(c) for c in (name or "云")) % len(_AVATAR_COLORS)]


class CommentCard(QFrame):
    """单条评论卡片"""

    def __init__(self, comment, parent=None):
        super().__init__(parent)
        self.setObjectName("CommentCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QFrame#CommentCard { background: %s; border: 1px solid %s; "
            "border-radius: 14px; }" % (PANEL, LINE))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(10)

        name = comment.get("nickname") or "网易云用户"
        avatar = QLabel((name[:1] or "云").upper())
        avatar.setFixedSize(34, 34)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            "background: %s; border-radius: 17px; color: #FFFFFF; "
            "font-size: 14px; font-weight: 600;" % _avatar_color(name))
        top.addWidget(avatar)

        meta = QVBoxLayout()
        meta.setSpacing(1)
        nick = QLabel(name)
        nick.setStyleSheet(
            "color: %s; font-size: 13px; font-weight: 600;" % TEXT)
        meta.addWidget(nick)
        when = _time_text(comment.get("time"), comment.get("time_text"))
        time_label = QLabel(when or "网易云音乐")
        time_label.setStyleSheet("color: %s; font-size: 11px;" % SUB)
        meta.addWidget(time_label)
        top.addLayout(meta)
        top.addStretch(1)

        liked = QLabel("%s 赞" % _short_count(comment.get("liked")))
        liked.setStyleSheet("color: %s; font-size: 11px;" % SUB)
        liked.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(liked)
        layout.addLayout(top)

        body = QLabel(comment.get("content") or "")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet("color: %s; font-size: 13px;" % TEXT)
        layout.addWidget(body)

        for reply in comment.get("reply") or []:
            text = "回复 %s：%s" % (reply.get("nickname") or "网易云用户",
                                    reply.get("content") or "")
            reply_label = QLabel(text)
            reply_label.setWordWrap(True)
            reply_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            reply_label.setStyleSheet(
                "background: %s; color: %s; border-radius: 8px; "
                "padding: 6px 9px; font-size: 12px;" % (PANEL_2, SUB))
            layout.addWidget(reply_label)


class CommentsDialog(QDialog):
    """围绕当前播放歌曲的评论页"""

    def __init__(self, client, song, parent=None):
        super().__init__(parent)
        self.client = client
        self.song = song or {}
        self.song_id = self.song.get("id")
        self._loading = False
        self._limit = 20
        self._closed = False

        self.setWindowTitle("歌曲评论")
        self.setFixedSize(720, 580)
        self.setStyleSheet("QDialog { background: %s; }" % PANEL)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("歌曲评论")
        title.setStyleSheet(
            "color: %s; font-size: 20px; font-weight: 700;" % TEXT)
        head.addWidget(title)
        head.addSpacing(8)
        subtitle = QLabel("%s · %s" % (self.song.get("name") or "当前歌曲",
                                        self.song.get("artist") or ""))
        subtitle.setStyleSheet("color: %s; font-size: 12px;" % SUB)
        head.addWidget(subtitle)
        head.addStretch(1)
        self.count_label = QLabel("正在加载…")
        self.count_label.setStyleSheet("color: %s; font-size: 12px;" % SUB)
        head.addWidget(self.count_label)
        root.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.list_layout = QVBoxLayout(self.body)
        self.list_layout.setContentsMargins(2, 2, 2, 6)
        self.list_layout.setSpacing(10)
        self.scroll.setWidget(self.body)
        root.addWidget(self.scroll, 1)

        footer = QFrame()
        footer.setObjectName("CommentFooter")
        footer.setStyleSheet(
            "QFrame#CommentFooter { background: %s; border-top: 1px solid %s; }"
            % (PANEL, LINE))
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 10, 0, 0)
        footer_layout.setSpacing(6)

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("说点什么…（最多 140 字）")
        self.input.setFixedHeight(58)
        footer_layout.addWidget(self.input)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: %s; font-size: 11px;" % SUB)
        bottom.addWidget(self.status_label, 1)
        self.send_btn = QPushButton("发表")
        self.send_btn.setObjectName("Accent")
        self.send_btn.setFixedWidth(92)
        self.send_btn.clicked.connect(self._submit)
        bottom.addWidget(self.send_btn)
        self.close_btn = QPushButton("关闭")
        self.close_btn.setObjectName("Link")
        self.close_btn.setFixedWidth(64)
        self.close_btn.setToolTip("关闭评论页")
        self.close_btn.clicked.connect(self.close)
        bottom.addWidget(self.close_btn)
        footer_layout.addLayout(bottom)
        root.addWidget(footer)

        self._update_login_state()
        self._load()

    def _update_login_state(self):
        logged_in = bool(getattr(self.client, "account", None))
        self.send_btn.setText("发表" if logged_in else "登录后评论")
        self.send_btn.setFixedWidth(92 if logged_in else 112)
        if logged_in:
            self.status_label.setText("已登录，可以发表评论")
        else:
            self.status_label.setText("当前未登录，只能查看公开评论")

    def _clear(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _section(self, text):
        label = QLabel(text)
        label.setStyleSheet(
            "color: %s; font-size: 13px; font-weight: 600; padding-top: 2px;"
            % TEXT)
        self.list_layout.addWidget(label)

    def _load(self):
        if self._loading or not self.song_id:
            return
        self._loading = True
        self.status_label.setText("正在加载评论…")
        run_async(
            lambda: self.client.comments(self.song_id, limit=self._limit, offset=0),
            self._on_loaded, self._on_error)

    def _on_loaded(self, data):
        if self._closed:
            return
        self._loading = False
        self._clear()
        hot = data.get("hot") or []
        latest = data.get("latest") or []
        total = int(data.get("total") or 0)
        self.count_label.setText("共 %d 条" % total)

        if hot:
            self._section("热门评论")
            for comment in hot:
                self.list_layout.addWidget(CommentCard(comment))

        self._section("最新评论")
        if latest:
            for comment in latest:
                self.list_layout.addWidget(CommentCard(comment))
        else:
            empty = QLabel("还没有评论，来抢沙发吧")
            empty.setStyleSheet(
                "color: %s; font-size: 13px; padding: 20px 0;" % SUB)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_layout.addWidget(empty)

        if total > len(latest) and self._limit < 50:
            more = QPushButton("加载更多")
            more.setObjectName("Link")
            more.clicked.connect(self._load_more)
            self.list_layout.addWidget(more)

        self.status_label.setText("")
        self._update_login_state()

    def _on_error(self, message):
        if self._closed:
            return
        self._loading = False
        self._clear()
        self.count_label.setText("加载失败")
        label = QLabel("评论加载失败：%s" % message)
        label.setWordWrap(True)
        label.setStyleSheet("color: %s; font-size: 13px;" % SUB)
        self.list_layout.addWidget(label)
        self.status_label.setText("可以稍后重试")

    def _load_more(self):
        if self._loading:
            return
        self._limit = min(self._limit + 20, 50)
        self._load()

    def _open_login(self):
        try:
            from .login import LoginDialog
        except ImportError:
            return False
        dialog = LoginDialog(self.client, self)
        if dialog.exec():
            self._update_login_state()
            return True
        return False

    def _submit(self):
        text = self.input.toPlainText().strip()
        if not text:
            self.status_label.setText("先写点什么吧")
            return
        if len(text) > 140:
            self.status_label.setText("评论最多 140 字")
            return
        if not getattr(self.client, "account", None):
            if not self._open_login():
                self.status_label.setText("需要登录后才能发表评论")
                return
            self._update_login_state()

        self.send_btn.setEnabled(False)
        self.status_label.setText("正在发表评论…")
        run_async(
            lambda: self.client.add_comment(self.song_id, text),
            self._on_posted, self._on_post_error)

    def _on_posted(self, _payload):
        if self._closed:
            return
        self.send_btn.setEnabled(True)
        self.input.clear()
        self.status_label.setText("评论已发表")
        self._limit = 20
        self._load()

    def _on_post_error(self, message):
        if self._closed:
            return
        self.send_btn.setEnabled(True)
        self.status_label.setText(message)

    def closeEvent(self, event):
        self._closed = True
        super().closeEvent(event)
