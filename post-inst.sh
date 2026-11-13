#!/bin/bash
# post-install 脚本 - 任务栏图标缓存刷新

# 更新桌面数据库和图标缓存
echo "正在刷新 Yc浏览器 图标缓存..."
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database -q /usr/share/applications 2>/dev/null || true
fi
if command -v update-icon-caches &> /dev/null; then
    update-icon-caches -q /usr/share/icons/hicolor 2>/dev/null || true
fi

# 通知用户
echo "✅ Yc浏览器 图标缓存已更新完成！"
echo "注意：如果任务栏仍未显示，请注销并重新登录桌面环境。"
