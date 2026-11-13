#!/bin/sh
# OmniBrowser 启动器（openKylin / deepin 通用）。
#
# 关键点（踩过的坑）：
# 1. **不能用 dirname "$0"/.. 推算安装目录** —— 启动器装在 /usr/bin/omnibrowser，
#    而程序在 /opt/omnibrowser，推算会得到 /usr，导致 "No module named src.main"。
#    这里直接使用固定安装路径，并允许用 OMNIBROWSER_HOME 覆盖（便携/测试用）。
# 2. **解释器要探测，不能写死单一路径**：
#    - openKylin 变体自带私有 PyQt6 绑定（abi3，兼容任意 Python 3.x），
#      用系统 python3 + PYTHONPATH 即可；
#    - deepin 变体依赖系统 python3-pyqt6，同样用系统 python3。
# 3. 任何失败都要把原因打到 stderr 并以非零码退出，
#    否则从桌面图标点击后毫无反应，用户无从排查。
set -e

HOME_DIR="${OMNIBROWSER_HOME:-/opt/omnibrowser}"

if [ ! -d "$HOME_DIR/src" ]; then
    echo "OmniBrowser：程序目录缺失（$HOME_DIR/src 不存在）" >&2
    exit 1
fi

# 私有 PyQt6 绑定优先（openKylin 变体）
if [ -d "$HOME_DIR/lib/python3/dist-packages" ]; then
    PYTHONPATH="$HOME_DIR/lib/python3/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
    export PYTHONPATH
fi

# Rust 核心（行式 JSON-RPC 子进程）
if [ -x "$HOME_DIR/omnibrowser-core" ]; then
    OMNIBROWSER_CORE="$HOME_DIR/omnibrowser-core"
    export OMNIBROWSER_CORE
fi

# 解释器探测：优先 python3
PY=""
for c in /usr/bin/python3 python3 /usr/bin/python python; do
    if command -v "$c" >/dev/null 2>&1; then
        PY="$c"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "OmniBrowser：未找到 Python 3 解释器" >&2
    exit 1
fi

# 让 src 包可被导入
cd "$HOME_DIR"
exec "$PY" -m src.main "$@"
