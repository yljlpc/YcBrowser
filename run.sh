#!/usr/bin/env bash
# OmniBrowser 启动脚本
# 自动拼接私有 PyQt6 前缀与 Chromium 运行参数，再拉起前端。
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

CORE="$ROOT/core/target/release/omnibrowser-core"
if [ ! -x "$CORE" ]; then
    echo "[OmniBrowser] 未找到 Rust 核心，请先构建："
    echo "  cd core && CARGO_HOME=../_stage/cargohome CARGO_TARGET_DIR=\$PWD/target cargo build --release"
    exit 1
fi

export PYTHONPATH="$ROOT/_stage/pyqt6root/usr/lib/python3/dist-packages:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
# 沙箱 / 无 GPU 环境必需；src/main.py 内置相同默认值，这里显式导出以便外部覆盖。
export QTWEBENGINE_CHROMIUM_FLAGS="${QTWEBENGINE_CHROMIUM_FLAGS:---no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer}"

exec /usr/bin/python3 -m src.main "$@"
