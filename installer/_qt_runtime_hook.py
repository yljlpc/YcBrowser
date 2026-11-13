"""PyInstaller 运行时钩子：显式告诉 Qt 去哪里找插件与资源。

为什么需要这个文件
------------------
PyInstaller 自带的 hook-PyQt6.py 会通过设置 QT_PLUGIN_PATH 等环境变量，
把 Qt 的插件、资源、WebEngine 子进程指向 bundle 内的正确位置。

但该 hook 依赖在隔离子进程中 import PyQt6.QtCore 来探测 Qt 路径。在启用了
Windows 应用控制策略（WDAC / AppLocker）的构建机上，这个 import 会被系统
策略拦截，hook 整段被跳过 —— 于是运行时没有任何环境变量指向 Qt 的
plugins 目录，程序启动即报：

    This application failed to start because no Qt platform plugin
    could be initialized.

本钩子不依赖任何探测，直接按已知的目录布局设置环境变量，双重保险。

设置的环境变量
--------------
QT_PLUGIN_PATH               Qt 插件根目录（Qt 在其下找 platforms/ 等子目录）
QT_QPA_PLATFORM_PLUGIN_PATH  平台插件目录的绝对路径
QTWEBENGINEPROCESS_PATH      WebEngine 渲染进程可执行文件
QTWEBENGINE_RESOURCES_PATH   WebEngine 资源包（pak / ICU / v8 快照）
QTWEBENGINE_LOCALES_PATH     WebEngine 的 locale 数据（en-US.pak 等）
"""
import os
import sys

_meipass = getattr(sys, "_MEIPASS", None)

if _meipass:
    _qt_root = os.path.join(_meipass, "PyQt6", "Qt6")

    # Qt 插件搜索根：Qt 会在其下寻找 platforms/、imageformats/ 等子目录
    os.environ["QT_PLUGIN_PATH"] = _qt_root

    # 平台插件（qwindows.dll）的绝对路径
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(
        _qt_root, "plugins", "platforms")

    # WebEngine 渲染进程：每个标签页会启动一个实例
    _proc = os.path.join(_qt_root, "bin", "QtWebEngineProcess.exe")
    if not os.path.isfile(_proc):
        _proc = os.path.join(_qt_root, "bin", "Qt6WebEngineProcess.exe")
    if os.path.isfile(_proc):
        os.environ["QTWEBENGINEPROCESS_PATH"] = _proc

    # WebEngine 资源：qtwebengine_resources.pak / icudtl.dat / v8 快照
    _res = os.path.join(_qt_root, "resources")
    if os.path.isdir(_res):
        os.environ["QTWEBENGINE_RESOURCES_PATH"] = _res

    # WebEngine locale 数据（en-US.pak 等），缺失会导致页面显示乱码方块
    _locales = os.path.join(_qt_root, "translations", "qtwebengine_locales")
    if os.path.isdir(_locales):
        os.environ["QTWEBENGINE_LOCALES_PATH"] = _locales
