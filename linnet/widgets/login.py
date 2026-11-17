"""扫码登录对话框"""
import io

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QPlainTextEdit, QPushButton, QVBoxLayout)

from ..tasks import run_async
from ..theme import ACCENT, LINE, PANEL, QR_BG, SUB


class LoginDialog(QDialog):
    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.unikey = None
        self._finished = False
        self._poll_errors = 0

        self.setWindowTitle("扫码登录")
        self.setFixedSize(320, 620)
        self.setStyleSheet(f"QDialog {{ background:{PANEL}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("登录网易云音乐")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel("用手机网易云音乐 App 扫码")
        desc.setStyleSheet(f"color:{SUB};font-size:12px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        self.qr = QLabel("正在获取二维码…")
        self.qr.setFixedSize(220, 220)
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr.setStyleSheet(
            f"background:{QR_BG};border:1px solid {LINE};border-radius:14px;"
            f"color:{SUB};font-size:12px;")
        layout.addWidget(self.qr, alignment=Qt.AlignmentFlag.AlignCenter)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{SUB};font-size:12px;")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        self.refresh = QPushButton("刷新二维码")
        self.refresh.setObjectName("Accent")
        self.refresh.clicked.connect(self._fetch_qr)
        self.refresh.setVisible(False)
        layout.addWidget(self.refresh, alignment=Qt.AlignmentFlag.AlignCenter)

        self.recheck = QPushButton("重新校验登录态")
        self.recheck.clicked.connect(self._recheck)
        self.recheck.setVisible(False)
        layout.addWidget(self.recheck, alignment=Qt.AlignmentFlag.AlignCenter)

        self.sms_btn = QPushButton("短信验证码登录（推荐）")
        self.sms_btn.setFlat(True)
        self.sms_btn.setStyleSheet(f"color:{ACCENT};font-size:12px;")
        self.sms_btn.clicked.connect(self._open_sms)
        layout.addWidget(self.sms_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.phone_btn = QPushButton("改用手机号密码登录")
        self.phone_btn.setFlat(True)
        self.phone_btn.setStyleSheet(f"color:{SUB};font-size:12px;")
        self.phone_btn.clicked.connect(self._open_phone)
        layout.addWidget(self.phone_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.email_btn = QPushButton("改用网易邮箱登录")
        self.email_btn.setFlat(True)
        self.email_btn.setStyleSheet(f"color:{SUB};font-size:12px;")
        self.email_btn.clicked.connect(self._open_email)
        layout.addWidget(self.email_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.cookie_btn = QPushButton("导入浏览器 Cookie 登录")
        self.cookie_btn.setFlat(True)
        self.cookie_btn.setStyleSheet(f"color:{SUB};font-size:12px;")
        self.cookie_btn.clicked.connect(self._open_cookie)
        layout.addWidget(self.cookie_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self._poll)
        self._fetch_qr()

    # ---------- 二维码 ----------
    def _fetch_qr(self):
        self.refresh.setVisible(False)
        self.recheck.setVisible(False)
        self._poll_errors = 0
        self.qr.setText("正在获取二维码…")
        self.status.setText("")
        run_async(self.client.qr_unikey, self._on_unikey, self._on_error)

    def _on_unikey(self, unikey):
        self.unikey = unikey
        url = self.client.qr_url(unikey)
        pix = self._make_qr(url)
        if pix is not None:
            self.qr.setPixmap(pix.scaled(
                200, 200, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            self.qr.setWordWrap(True)
            self.qr.setText("无法生成二维码\n%s" % url)
        self.status.setText("等待扫码…")
        self.timer.start()

    @staticmethod
    def _make_qr(text):
        try:
            import qrcode
            img = qrcode.make(text)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            pix = QPixmap()
            pix.loadFromData(buf.getvalue())
            return pix if not pix.isNull() else None
        except Exception:
            return None

    def _on_error(self, message):
        self.qr.setText("二维码获取失败")
        self.status.setText(message)
        self.refresh.setVisible(True)

    # ---------- 轮询 ----------
    def _poll(self):
        if not self.unikey or self._finished:
            return
        self.timer.stop()
        run_async(lambda: self.client.qr_check(self.unikey),
                  self._on_poll, self._on_poll_error)

    def _on_poll(self, payload):
        code, message = payload
        if self._finished:
            return
        self._poll_errors = 0
        if code == 800:
            self.qr.setText("二维码已过期")
            self.status.setText("请点击下方按钮刷新")
            self.refresh.setVisible(True)
            return
        if code == 802:
            self.status.setText("已扫码，请在手机上确认登录")
        elif code == 803:
            self.status.setText("登录成功，正在同步歌单…")
            self._finished = True
            run_async(self.client.after_login, self._on_login_ok, self._on_error)
            return
        elif code == 801:
            self.status.setText("等待扫码…")
        else:
            self.status.setText(message or ("扫码状态异常：%s" % code))
        self.timer.start()

    def _on_poll_error(self, message):
        self._poll_errors += 1
        if self._poll_errors >= 3:
            self.timer.stop()
            self.status.setText("扫码状态查询失败：%s" % message)
            self.refresh.setVisible(True)
            return
        self.timer.start()

    def _recheck(self):
        self.recheck.setVisible(False)
        self.status.setText("正在重新校验登录态…")
        run_async(self.client.after_login, self._on_login_ok, self._on_error)

    def _on_login_ok(self, account):
        if account:
            self.accept()
        else:
            self.status.setText("已扫码成功，但登录态还没生效\n可点“重新校验登录态”再试")
            self.recheck.setVisible(True)
            self.refresh.setVisible(True)

    def _open_sms(self):
        dialog = SmsLoginDialog(self.client, self)
        if dialog.exec():
            self.accept()

    def _open_phone(self):
        dialog = PhoneLoginDialog(self.client, self)
        if dialog.exec():
            self.accept()

    def _open_email(self):
        dialog = EmailLoginDialog(self.client, self)
        if dialog.exec():
            self.accept()

    def _open_cookie(self):
        dialog = CookieImportDialog(self.client, self)
        if dialog.exec():
            self.accept()

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)


class PhoneLoginDialog(QDialog):
    """备用登录：手机号 + 密码（同样走加密接口）"""

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.setWindowTitle("手机号登录")
        self.setFixedSize(320, 250)
        self.setStyleSheet(f"QDialog {{ background:{PANEL}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        title = QLabel("手机号登录")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.phone = QLineEdit()
        self.phone.setPlaceholderText("手机号")
        self.phone.setMaxLength(11)
        layout.addWidget(self.phone)

        self.password = QLineEdit()
        self.password.setPlaceholderText("密码")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self._submit)
        layout.addWidget(self.password)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{SUB};font-size:12px;")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        self.ok = QPushButton("登录")
        self.ok.setObjectName("Accent")
        self.ok.clicked.connect(self._submit)
        layout.addWidget(self.ok, alignment=Qt.AlignmentFlag.AlignCenter)

    def _submit(self):
        phone = self.phone.text().strip()
        password = self.password.text()
        if not phone or not password:
            self.status.setText("请填写手机号和密码")
            return
        self.ok.setEnabled(False)
        self.ok.setText("登录中…")
        self.status.setText("正在登录…")
        run_async(lambda: self.client.login_phone(phone, password),
                  self._done, self._fail)

    def _done(self, account):
        if account:
            self.accept()
        else:
            self.ok.setEnabled(True)
            self.ok.setText("登录")
            self.status.setText("登录未生效，请确认账号密码是否正确")

    def _fail(self, message):
        self.ok.setEnabled(True)
        self.ok.setText("登录")
        self.status.setText(str(message)[:120])


class EmailLoginDialog(QDialog):
    """备用登录：网易邮箱 + 密码"""

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.setWindowTitle("邮箱登录")
        self.setFixedSize(340, 250)
        self.setStyleSheet(f"QDialog {{ background:{PANEL}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        title = QLabel("网易邮箱登录")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.email = QLineEdit()
        self.email.setPlaceholderText("网易邮箱（如 xxx@163.com）")
        layout.addWidget(self.email)

        self.password = QLineEdit()
        self.password.setPlaceholderText("密码")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self._submit)
        layout.addWidget(self.password)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{SUB};font-size:12px;")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        self.ok = QPushButton("登录")
        self.ok.setObjectName("Accent")
        self.ok.clicked.connect(self._submit)
        layout.addWidget(self.ok, alignment=Qt.AlignmentFlag.AlignCenter)

    def _submit(self):
        email = self.email.text().strip()
        password = self.password.text()
        if not email or not password:
            self.status.setText("请填写邮箱和密码")
            return
        self.ok.setEnabled(False)
        self.ok.setText("登录中…")
        self.status.setText("正在登录…")
        run_async(lambda: self.client.login_email(email, password),
                  self._done, self._fail)

    def _done(self, account):
        if account:
            self.accept()
        else:
            self.ok.setEnabled(True)
            self.ok.setText("登录")
            self.status.setText("登录未生效，请确认邮箱密码是否正确")

    def _fail(self, message):
        self.ok.setEnabled(True)
        self.ok.setText("登录")
        self.status.setText(str(message)[:120])


class SmsLoginDialog(QDialog):
    """短信验证码登录：不用密码，绕开密码风控"""

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self._seconds = 0

        self.setWindowTitle("短信验证码登录")
        self.setFixedSize(360, 320)
        self.setStyleSheet(f"QDialog {{ background:{PANEL}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        title = QLabel("短信验证码登录")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        row = QHBoxLayout()
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("手机号（11 位）")
        self.phone.setMaxLength(11)
        row.addWidget(self.phone, 1)
        self.send = QPushButton("发送验证码")
        self.send.clicked.connect(self._send)
        row.addWidget(self.send)
        layout.addLayout(row)

        self.code = QLineEdit()
        self.code.setPlaceholderText("6 位验证码")
        self.code.setMaxLength(6)
        self.code.returnPressed.connect(self._submit)
        layout.addWidget(self.code)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{SUB};font-size:12px;")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        self.ok = QPushButton("登录")
        self.ok.setObjectName("Accent")
        self.ok.clicked.connect(self._submit)
        layout.addWidget(self.ok, alignment=Qt.AlignmentFlag.AlignCenter)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

    def _send(self):
        phone = self.phone.text().strip()
        if len(phone) != 11 or not phone.isdigit():
            self.status.setText("请输入 11 位手机号")
            return
        self.send.setEnabled(False)
        self.send.setText("发送中…")
        self.status.setText("正在发送验证码…")
        run_async(lambda: self.client.send_sms_code(phone),
                  self._sent, self._send_fail)

    def _sent(self, _payload):
        self._seconds = 60
        self.send.setText("重新发送(%ds)" % self._seconds)
        self.send.setEnabled(False)
        self.timer.start()
        self.status.setText("验证码已发送，请查看手机短信")
        self.code.setFocus()

    def _send_fail(self, message):
        self.send.setEnabled(True)
        self.send.setText("发送验证码")
        self.status.setText(str(message)[:150])

    def _tick(self):
        self._seconds -= 1
        if self._seconds <= 0:
            self.timer.stop()
            self.send.setText("发送验证码")
            self.send.setEnabled(True)
        else:
            self.send.setText("重新发送(%ds)" % self._seconds)

    def _submit(self):
        phone = self.phone.text().strip()
        code = self.code.text().strip()
        if len(phone) != 11 or not phone.isdigit():
            self.status.setText("请输入 11 位手机号")
            return
        if not code:
            self.status.setText("请输入短信里的验证码")
            return
        self.ok.setEnabled(False)
        self.ok.setText("登录中…")
        self.status.setText("正在登录…")
        run_async(lambda: self.client.login_sms(phone, code),
                  self._done, self._fail)

    def _done(self, account):
        if account:
            self.accept()
        else:
            self.ok.setEnabled(True)
            self.ok.setText("登录")
            self.status.setText("登录未生效，请确认验证码是否过期")

    def _fail(self, message):
        self.ok.setEnabled(True)
        self.ok.setText("登录")
        self.status.setText(str(message)[:150])


class CookieImportDialog(QDialog):
    """导入浏览器 cookie —— 网易风控收紧时的保底登录方式"""

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.setWindowTitle("导入 Cookie 登录")
        self.setFixedSize(440, 380)
        self.setStyleSheet(f"QDialog {{ background:{PANEL}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(8)

        title = QLabel("从浏览器导入登录态")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        tip = QLabel(
            "1. 电脑浏览器打开 music.163.com 并完成登录\n"
            "2. 按 F12 → Application（应用）→ Cookies → https://music.163.com\n"
            "3. 找到 MUSIC_U，复制它的值（也可以整串 cookie 一起复制）\n"
            "4. 粘贴到下面，点「导入」")
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{SUB};font-size:12px;")
        layout.addWidget(tip)

        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("MUSIC_U=xxxxx   或   只粘贴值")
        layout.addWidget(self.edit, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{SUB};font-size:12px;")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        self.ok = QPushButton("导入")
        self.ok.setObjectName("Accent")
        self.ok.clicked.connect(self._submit)
        layout.addWidget(self.ok, alignment=Qt.AlignmentFlag.AlignCenter)

    def _submit(self):
        text = self.edit.toPlainText().strip()
        if not text:
            self.status.setText("请先粘贴 cookie")
            return
        self.ok.setEnabled(False)
        self.ok.setText("校验中…")
        self.status.setText("正在校验登录态…")
        run_async(lambda: self.client.import_cookie(text),
                  self._done, self._fail)

    def _done(self, account):
        if account:
            self.accept()
        else:
            self.ok.setEnabled(True)
            self.ok.setText("导入")
            self.status.setText("cookie 未生效，请确认复制的是 MUSIC_U")

    def _fail(self, message):
        self.ok.setEnabled(True)
        self.ok.setText("导入")
        self.status.setText(str(message)[:160])
