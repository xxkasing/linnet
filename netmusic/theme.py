"""iOS 风格统一样式与配色

浅色 / 深色两套 iOS HIG 外观，由 NETMUSIC_THEME 环境变量在进程启动时决定：
- systemGroupedBackground 作为页面底色
- secondaryGroupedBackground（浅色白 / 深色 #1C1C1E）作为卡片、表格和工具栏
- systemBlue 作为可交互元素的主色
- 大圆角、胶囊按钮、细分割线、克制的层次
"""
import os

IS_DARK = os.environ.get("NETMUSIC_THEME", "light").strip().lower() == "dark"

if IS_DARK:
    BG = "#000000"            # 页面/分组背景
    PANEL = "#1C1C1E"         # 卡片、表格、导航栏
    PANEL_2 = "#2C2C2E"       # 输入框、次要按钮填充
    HOVER = "#3A3A3C"         # hover 填充
    PRESSED_BG = "#3A3A3C"    # 按钮按下
    ACCENT = "#0A84FF"        # iOS systemBlue（深色）
    ACCENT_HOVER = "#409CFF"
    ACCENT_PRESSED = "#0060DF"
    ACCENT_SOFT = "#102A43"   # 选中行/选中项的深蓝
    TEXT = "#FFFFFF"          # label
    SUB = "#98989F"           # secondaryLabel
    LINE = "#38383A"          # separator
    ICON = "#636366"          # 占位图标/滑块描边
    GREEN = "#30D158"
    RED = "#FF453A"
    ROW_LINE = "#2C2C2E"
else:
    BG = "#F2F2F7"            # 页面/分组背景
    PANEL = "#FFFFFF"         # 卡片、表格、导航栏
    PANEL_2 = "#F2F2F7"       # 输入框、次要按钮填充
    HOVER = "#E9E9EF"         # hover 填充
    PRESSED_BG = "#DCDCE3"    # 按钮按下
    ACCENT = "#007AFF"        # iOS systemBlue
    ACCENT_HOVER = "#0A84FF"
    ACCENT_PRESSED = "#0060DF"
    ACCENT_SOFT = "#E5F0FF"   # 选中行/选中项的浅蓝
    TEXT = "#1C1C1E"          # label
    SUB = "#8E8E93"           # secondaryLabel
    LINE = "#E5E5EA"          # separator
    ICON = "#C7C7CC"          # 占位图标/滑块描边
    GREEN = "#34C759"
    RED = "#FF3B30"
    ROW_LINE = "#F7F7FA"

ON_ACCENT = "#FFFFFF"         # 强调色按钮上的文字
QR_BG = "#FFFFFF"             # 二维码必须保持白底，方便手机扫描
SLIDER_HANDLE = "#FFFFFF"     # 滑块手柄在深浅色下都用白色

FONT = ('"SF Pro Display", "SF Pro Text", "Inter", "Noto Sans CJK SC", '
        '"Noto Sans SC", "PingFang SC", "DejaVu Sans", sans-serif')

QSS = f"""
QWidget {{
    color: {TEXT};
    font-family: {FONT};
    font-size: 14px;
}}
QMainWindow, QStackedWidget, QSplitter {{ background: {BG}; }}

/* ---------- 结构 ---------- */
QFrame#TopBar {{
    background: {PANEL};
    border-bottom: 1px solid {LINE};
}}
QFrame#Player {{
    background: {PANEL};
    border-top: 1px solid {LINE};
}}
QFrame#LyricPanel {{
    background: {PANEL};
    border-left: 1px solid {LINE};
}}
QFrame#FullLyrics {{
    background: {BG};
}}
QFrame#LyricTicker {{
    background: {PANEL};
    border-top: 1px solid {LINE};
}}
QFrame#InfoCard {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 18px;
}}
QWidget#PlaylistCard {{
    background: {PANEL};
    border: 1px solid transparent;
    border-radius: 16px;
}}
QWidget#PlaylistCard:hover {{
    background: {PANEL};
    border-color: {LINE};
}}

/* ---------- 输入 ---------- */
QLineEdit#SearchBox {{
    background: {PANEL_2};
    border: 1px solid transparent;
    border-radius: 18px;
    padding: 8px 16px;
    color: {TEXT};
    selection-background-color: {ACCENT};
}}
QLineEdit#SearchBox:focus {{
    background: {PANEL};
    border-color: {ACCENT};
}}
QLineEdit, QPlainTextEdit {{
    background: {PANEL_2};
    border: 1px solid transparent;
    border-radius: 12px;
    padding: 9px 12px;
    color: {TEXT};
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    background: {PANEL};
    border-color: {ACCENT};
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: {PANEL_2};
    border: 1px solid transparent;
    border-radius: 18px;
    padding: 8px 16px;
    color: {TEXT};
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:pressed {{ background: {PRESSED_BG}; }}
QPushButton:disabled {{ color: {SUB}; }}
QPushButton#Accent {{
    background: {ACCENT};
    border: none;
    color: {ON_ACCENT};
    font-weight: 600;
}}
QPushButton#Accent:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Accent:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton#Accent:disabled {{ background: {ICON}; color: {ON_ACCENT}; }}
QPushButton#Link {{
    background: transparent;
    border: none;
    border-radius: 0;
    color: {ACCENT};
    padding: 6px 8px;
    font-weight: 500;
}}
QPushButton#Link:hover {{ color: {ACCENT_HOVER}; }}
QPushButton#PillTab {{
    background: transparent;
    border: none;
    border-radius: 14px;
    padding: 6px 14px;
    color: {SUB};
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#PillTab:hover {{ color: {TEXT}; }}
QPushButton#PillTab:checked {{
    background: {PANEL_2};
    color: {TEXT};
    font-weight: 600;
}}
QPushButton#Flat {{
    background: transparent;
    border: none;
    border-radius: 0;
    color: {SUB};
    font-size: 18px;
    padding: 0;
}}
QPushButton#Flat:hover {{ color: {ACCENT}; }}
QPushButton#PlayBtn {{
    background: {ACCENT};
    border: none;
    border-radius: 23px;
    color: {ON_ACCENT};
    font-size: 17px;
    font-weight: 700;
}}
QPushButton#PlayBtn:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#PlayBtn:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton#ModeBtn {{
    background: transparent;
    border: none;
    border-radius: 0;
    color: {SUB};
    font-size: 12px;
    font-weight: 500;
    padding: 0;
}}
QPushButton#ModeBtn:hover {{ color: {ACCENT}; }}
QPushButton#CommentBtn {{
    background: {PANEL_2};
    border: none;
    border-radius: 15px;
    color: {SUB};
    font-size: 12px;
    font-weight: 500;
    padding: 0;
}}
QPushButton#CommentBtn:hover {{ background: {HOVER}; color: {ACCENT}; }}
QPushButton#LikeBtn {{
    background: {PANEL_2};
    border: none;
    border-radius: 15px;
    color: {SUB};
    font-size: 12px;
    font-weight: 500;
    padding: 0;
}}
QPushButton#LikeBtn:hover {{ background: {HOVER}; color: {ACCENT}; }}
QPushButton#LikeBtn[liked="true"] {{
    background: {ACCENT_SOFT};
    color: {ACCENT};
    font-weight: 600;
}}
QPushButton#WindowBtn {{
    background: transparent;
    border: none;
    border-radius: 14px;
    color: {SUB};
    font-size: 15px;
    padding: 0;
}}
QPushButton#WindowBtn:hover {{ background: {HOVER}; color: {TEXT}; }}
QPushButton#WindowBtnClose {{
    background: transparent;
    border: none;
    border-radius: 14px;
    color: {SUB};
    font-size: 15px;
    padding: 0;
}}
QPushButton#WindowBtnClose:hover {{ background: {RED}; color: #FFFFFF; }}

/* ---------- 导航 ---------- */
QListWidget#Nav {{
    background: {BG};
    border: none;
    outline: none;
    padding: 8px;
}}
QListWidget#Nav::item {{
    padding: 10px 14px;
    color: {SUB};
    border: none;
    border-radius: 10px;
}}
QListWidget#Nav::item:hover {{
    background: {HOVER};
    color: {TEXT};
}}
QListWidget#Nav::item:selected {{
    background: {ACCENT_SOFT};
    color: {ACCENT};
    font-weight: 600;
}}

/* ---------- 表格 ---------- */
QTableWidget {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 16px;
    gridline-color: transparent;
    alternate-background-color: {PANEL};
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
}}
QTableWidget::item {{
    padding: 7px 10px;
    border: none;
    border-bottom: 1px solid {ROW_LINE};
}}
QTableWidget::item:selected {{
    background: {ACCENT_SOFT};
    color: {TEXT};
}}
QHeaderView::section {{
    background: {PANEL};
    color: {SUB};
    border: none;
    border-bottom: 1px solid {LINE};
    padding: 9px 10px;
    font-weight: 500;
    font-size: 12px;
}}
QTableCornerButton::section {{
    background: {PANEL};
    border: none;
}}

/* ---------- 滑块 ---------- */
QSlider::groove:horizontal {{
    height: 4px;
    background: {LINE};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: {SLIDER_HANDLE};
    border: 1px solid {ICON};
}}
QSlider::handle:horizontal:hover {{ border-color: {ACCENT}; }}
QSlider::add-page:horizontal, QSlider::sub-page:horizontal {{ border: none; }}

/* ---------- 滚动区 ---------- */
QScrollArea, QScrollArea QWidget#qt_scrollarea_viewport,
QScrollArea > QWidget > QWidget {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {ICON};
    border-radius: 3px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {SUB}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{
    height: 8px;
    background: transparent;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {ICON};
    border-radius: 3px;
    min-width: 32px;
}}

/* ---------- 其他 ---------- */
QSplitter::handle {{ background: {LINE}; width: 1px; }}
QToolTip {{
    background: {PANEL};
    color: {TEXT};
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 6px 10px;
}}
QDialog {{ background: {PANEL}; }}
QLabel#Title {{ font-size: 22px; font-weight: 700; }}
QLabel#DialogTitle {{ font-size: 18px; font-weight: 700; }}
QLabel#SectionTitle {{ color: {SUB}; font-size: 12px; font-weight: 600; }}
QLabel#Muted {{ color: {SUB}; font-size: 12px; }}
QLabel#Hint {{ color: {SUB}; font-size: 14px; }}
"""
