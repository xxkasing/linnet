# Linnet

Linnet 是一个非官方、开源的 Linux 桌面音乐客户端，使用 PyQt6 编写。它可以登录网易云音乐账号，浏览推荐歌单、搜索歌曲、查看专辑和歌手、播放与评论歌曲，并管理「我喜欢的音乐」。

作者：**kasingsing**

> **免责声明**
>
> 本项目是非官方第三方客户端，与网易及其关联公司无任何关系，也未获得其授权。项目仅用于个人学习和自用，请遵守网易云音乐的服务条款及当地法律法规。接口可能随时变更或失效，作者不保证可用性，也不对账号风控、数据或服务中断承担责任。
>
> 本项目不提供音乐下载，不绕过付费、VIP 或 DRM 限制，不收集或上传用户的登录凭据。

## 功能

- 推荐歌单浏览（换一批）、歌单详情（完整曲目）
- 歌曲搜索、双击播放、播放全部
- 专辑查看：双击歌曲表的「专辑」列进入专辑页；播放栏点歌名进入当前专辑
- 歌手页：播放栏点歌手名进入；支持「热门歌曲 / 专辑」切换和带关闭按钮的「歌手介绍」子页
- 我喜欢的音乐：右键「喜欢 / 取消喜欢」；播放栏「♡ 喜欢」管理当前歌曲
- 歌曲评论：播放栏评论按钮打开评论对话框
- 播放控制：播放/暂停、上一首/下一首、进度拖动、音量
- 播放模式：随机 / 单曲循环 / 顺序播放，默认随机
- 歌词解析、跟随高亮、自动滚动；点播放栏封面可展开整页歌词
- 登录方式：扫码、短信验证码、手机号密码、导入浏览器 Cookie（当前平台风控下推荐 Cookie 登录）
- iOS 风格深浅色皮肤，跟随系统主题
- 接口多方案自动切换：单个接口失效时尝试下一套方案，并写入本地路由缓存
- 统一布局比例：窗口 1220×760、侧栏 216、顶栏 64、播放栏 96

## 运行

### 依赖

- Python 3.9+
- PyQt6（含 QtMultimedia）
- `requests`、`qrcode`、`Pillow`
- Debian / Ubuntu 可安装：

```bash
sudo apt install python3-pyqt6 python3-pyqt6.qtmultimedia \
  python3-requests python3-qrcode python3-pil ffmpeg fonts-noto-cjk
```

或使用虚拟环境：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### 从源码启动

```bash
# 在仓库根目录执行
PYTHONPATH=. python3 -m netmusic
```

无显示器环境可用 Qt 的 offscreen 后端做基础冒烟测试：

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 -m netmusic
```

### 安装到应用菜单（可选）

```bash
sudo install -d /opt/netmusic
sudo cp -r netmusic assets /opt/netmusic/
sudo cp packaging/linnet.desktop /usr/share/applications/
sudo cp assets/linnet.svg /usr/share/icons/hicolor/scalable/apps/
```

桌面入口默认从 `/opt/netmusic` 启动；如果安装目录不同，请同步修改 `packaging/linnet.desktop` 的 `Path` 和 `Icon`。

## 登录与数据

- 登录信息只保存在本机 `~/.config/netmusic/cookies.json`。
- 不要把自己的 `cookies.json` 提交到 Git 或发给他人；`.gitignore` 已排除该文件和日志。
- 扫码、短信验证码和手机号密码登录受平台风控影响，可能失败；当前最可靠的方式是导入自己浏览器的 Cookie。Cookie 只用于本机请求，不会上传到第三方服务器。
- 只播放当前账号本身有权限播放的内容。

## 常见问题

**登录失败 / 扫码后没有登录态**
平台对第三方客户端有风控；可尝试短信验证码或导入浏览器 Cookie。不要频繁重试同一登录方式。

**歌曲不能播放**
该曲目可能需要账号权限，或接口/版权限制；请先在官方客户端确认账号权限。

**没有声音**
确认系统输出设备是否正确；在 Linux 上可用 `alsamixer` 检查音量，或切换 PulseAudio/PipeWire 输出设备。

**界面字体显示为方块**
安装中文字体：

```bash
sudo apt install fonts-noto-cjk
```

**接口失效**
程序会自动尝试备用方案，详细日志在 `~/.config/netmusic/netmusic.log`。接口属于第三方非官方接口，可能随平台调整而变化。

## 项目结构

```text
netmusic/
├── netmusic/            # Python 包，内部包名保持 netmusic
│   ├── api.py           # 非官方接口适配与自动切换
│   ├── app.py           # 主窗口
│   ├── theme.py         # 深浅色 QSS
│   └── widgets/         # 页面与控件
├── assets/              # Linnet 图标
├── packaging/           # 桌面入口
├── requirements.txt
├── COPYRIGHT
├── LICENSE
└── THIRD_PARTY_NOTICES.md
```

## 许可证

本项目以 **GNU General Public License v3.0 or later** 发布，详见 [LICENSE](LICENSE)。

Copyright (C) 2026 kasingsing. 完整版权声明见 [COPYRIGHT](COPYRIGHT)。

项目使用 PyQt6，PyQt6 本身采用 GPLv3 / Riverbank 商业双许可。若你希望以 MIT 等宽松许可证分发，需要将 PyQt6 替换为 PySide6（LGPLv3），或取得 PyQt 商业许可；仅把本项目改成 MIT 并不能消除 PyQt6 的许可证义务。

第三方组件的许可信息见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
