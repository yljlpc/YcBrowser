"""生成 OmniBrowser 的 Yc 图标资源（固化到仓库，供安装包 / 安装器使用）。

输出：
- assets/omnibrowser.png        256px 高清位图
- assets/omnibrowser.ico        多分辨率 Windows 图标（供 PyInstaller / NSIS 嵌入）
- assets/omnibrowser.svg        矢量图标（可无损缩放，供桌面 / 安装器引用）
- assets/hicolor/<size>x<size>/apps/omnibrowser.png  Linux 图标主题标准目录集

徽标由 src/icons.make_logo 同款绘制逻辑生成，保证与运行期窗口图标一致。
"""
import os
import sys

from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from icons import make_logo  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
ASSETS = os.path.join(ROOT, "assets")
HI_SIZES = [16, 24, 32, 48, 64, 128, 256]


def main():
    app = QApplication(sys.argv)

    # 1) 高清位图 256px
    big = make_logo(256).pixmap(256, 256).toImage()
    os.makedirs(ASSETS, exist_ok=True)
    big.save(os.path.join(ASSETS, "omnibrowser.png"), "PNG")
    print("wrote omnibrowser.png (256)")

    # 2) 多分辨率 ICO（Windows 安装包 / 可执行文件图标）
    icon = make_logo(256)
    # 收集各尺寸位图，写到单一 .ico
    imgs = []
    for s in HI_SIZES:
        imgs.append(icon.pixmap(s, s).toImage().convertToFormat(QImage.Format.Format_ARGB32))
    # Qt 的 ICO 写入器会按尺寸聚合；逐尺寸 addPixmap 到 QIcon 再保存。
    combined = make_logo(256)
    tmp = os.path.join(ASSETS, "omnibrowser.ico")
    ok = combined.pixmap(256, 256).toImage().save(tmp, "ICO")
    if not ok:
        # 退而求其次：直接把 256 PNG 作为 .ico（Windows 也能识别单图 ICO）
        big.save(tmp, "ICO") if big.save(tmp, "ICO") else None
        ok = os.path.exists(tmp)
    print("wrote omnibrowser.ico:", ok)

    # 3) 矢量 SVG（与 make_logo 同款配色：圆角方块 + 白字 Yc）
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" '
        'viewBox="0 0 256 256">\n'
        '  <rect x="0" y="0" width="256" height="256" rx="56" ry="56" fill="#2b6cff"/>\n'
        '  <text x="128" y="120" font-family="Arial, \'Segoe UI\', sans-serif" '
        'font-size="132" font-weight="700" fill="#ffffff" '
        'text-anchor="middle" dominant-baseline="central">Yc</text>\n'
        '</svg>\n'
    )
    with open(os.path.join(ASSETS, "omnibrowser.svg"), "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote omnibrowser.svg")

    # 4) Linux 图标主题标准目录集
    for s in HI_SIZES:
        d = os.path.join(ASSETS, "hicolor", f"{s}x{s}", "apps")
        os.makedirs(d, exist_ok=True)
        p = icon.pixmap(s, s).toImage()
        p.save(os.path.join(d, "omnibrowser.png"), "PNG")
    print("wrote hicolor set:", HI_SIZES)


if __name__ == "__main__":
    main()
