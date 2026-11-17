# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 kasingsing
"""命令入口：python3 -m linnet"""
import os
import subprocess
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication


def _gsettings_dark():
    """GNOME 的 color-scheme；Qt 在部分 Wayland 环境里会返回 Unknown。"""
    try:
        output = subprocess.check_output(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            text=True, stderr=subprocess.DEVNULL, timeout=3)
    except Exception:
        return None
    value = output.strip().strip("'\"").lower()
    if "dark" in value:
        return True
    if "light" in value or value == "default":
        return False
    return None


def _detect_dark_scheme(app):
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    return bool(_gsettings_dark())


def main():
    # 关闭 Wayland 的浅色系统窗口装饰；程序自己画深色顶栏
    os.environ.setdefault("QT_WAYLAND_DISABLE_WINDOWDECORATION", "1")
    requested = os.environ.get("LINNET_THEME", "auto").strip().lower()
    if requested not in ("auto", "light", "dark"):
        requested = "auto"

    app = QApplication(sys.argv)
    if requested == "auto":
        # 只在启动时做一次主题判断。不要在运行中监听 colorSchemeChanged
        # 或定时重启客户端：R6C 的 Wayland 会在启动阶段反复发出主题变化，
        # 从而产生多个自重启实例，表现为桌面图标/窗口持续抖动。
        os.environ["LINNET_THEME"] = (
            "dark" if _detect_dark_scheme(app) else "light")

    # 必须在确定主题后再导入，模块级颜色常量才会取到正确的一套
    from .app import MainWindow
    from .theme import QSS

    app.setApplicationName("linnet")
    app.setApplicationDisplayName("Linnet")
    app.setDesktopFileName("linnet")
    app.setStyleSheet(QSS)
    icon = QIcon.fromTheme("linnet")
    if icon.isNull():
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "assets", "linnet.png")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
