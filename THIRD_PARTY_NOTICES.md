# Third-party notices

Linnet is distributed under the GNU General Public License v3.0 or later (see `LICENSE`). The following third-party components are used at runtime or during development. Their licenses remain in effect; this file does not replace the full license texts shipped by their authors.

| Component | Purpose | License | Upstream |
| --- | --- | --- | --- |
| PyQt6 | Qt bindings | GPL v3 / Riverbank commercial (dual) | https://www.riverbankcomputing.com/software/pyqt/ |
| Qt 6 / QtMultimedia | GUI, multimedia playback | LGPL v3 / GPL v3 / commercial (varies by module and build) | https://www.qt.io/licensing/ |
| requests | HTTP client | Apache License 2.0 | https://requests.readthedocs.io/ |
| qrcode | Local QR code generation | BSD License | https://github.com/lincolnloop/python-qrcode |
| Pillow | Image handling used by qrcode | HPND License | https://python-pillow.org/ |
| Python | Runtime | PSF License | https://www.python.org/ |
| FFmpeg | Media backend (system package) | LGPL v2.1+ / GPL v2+ depending on build | https://ffmpeg.org/ |

## PyQt6 licensing note

PyQt6 is not distributed under a permissive license. If you redistribute Linnet with PyQt6, the GPLv3 obligations apply to the combined work. To publish under MIT or another permissive license, replace PyQt6 with PySide6 (LGPLv3) and comply with the LGPL, or obtain a commercial PyQt license.

## Qt / FFmpeg note

The Qt and FFmpeg versions installed by the user's Linux distribution may have different license configurations. Check the licenses of the exact packages you distribute. If you ship binaries, include the corresponding license notices and source-offer/relinking information required by those licenses.
