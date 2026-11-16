#!/usr/bin/env bash
# 逐个用例独立进程执行真实点击测试，并汇总通过率。
#
# 为什么逐个进程：实测在同一个 Qt 进程内连续跑多个用例会互相污染
# （外站加载后同进程内其它标签页的 runJavaScript 回调被推迟甚至超时），
# 造成大面积假失败。独立进程才能得到可信结论。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

CASES="${*:-R1 R2 R3 R4 R5 R6}"
OUT_DIR="$ROOT/outputs"
mkdir -p "$OUT_DIR"

TOTAL_PASS=0
TOTAL_ALL=0
SUMMARY=""

for c in $CASES; do
    echo "==================== 用例 $c ===================="
    bash tools/run_xvfb.sh tools/test_click_real.py --case "$c" \
        2>&1 | grep -v "ERROR:\|Failed to create\|GLX:\|GPUInfo\|^js: "
    f="$OUT_DIR/click_case_${c}.txt"
    if [ -f "$f" ]; then
        line=$(grep -E "合计: [0-9]+/[0-9]+ 通过" "$f" | tail -1)
        echo ">>> $c: $line"
        p=$(echo "$line" | sed -E 's#.*合计: ([0-9]+)/([0-9]+).*#\1#')
        a=$(echo "$line" | sed -E 's#.*合计: ([0-9]+)/([0-9]+).*#\2#')
        TOTAL_PASS=$((TOTAL_PASS + ${p:-0}))
        TOTAL_ALL=$((TOTAL_ALL + ${a:-0}))
        SUMMARY="${SUMMARY}${c}: ${p:-0}/${a:-0}\n"
    else
        echo ">>> $c: 报告未生成"
        SUMMARY="${SUMMARY}${c}: 报告未生成\n"
    fi
    echo
done

{
    echo "================================================================"
    echo "Yc浏览器 真实输入（XTEST）点击响应测试 · 汇总"
    echo "================================================================"
    echo "执行方式：每个用例独立 Qt 进程（避免外站加载污染后续用例）"
    echo "DISPLAY=:99（独立 Xvfb，不影响用户桌面与输入法环境）"
    echo
    printf "%b" "$SUMMARY"
    echo
    echo "总计: ${TOTAL_PASS}/${TOTAL_ALL} 通过"
} | tee "$OUT_DIR/click_real_report.txt"

exit 0
