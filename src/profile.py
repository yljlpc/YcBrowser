"""共享的持久化 WebEngine profile。

性能关键点（见 Qt 官方文档）：
- 内置 defaultProfile() 默认是 off-the-record（仅内存缓存），重复访问同一页面会重复下载，
  明显拖慢“运行速度”；
- 给应用一个带 storageName 的持久化 profile，并启用 DiskHttpCache，可让重复加载
  直接命中磁盘缓存，速度提升显著；同时 cookie / 历史可被持久化。
- 缓存类型、路径必须在创建任何属于该 profile 的页面之前设置。
"""
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWebEngineCore import QWebEngineProfile

_app_profile = None


def get_app_profile():
    global _app_profile
    if _app_profile is None:
        p = QWebEngineProfile("omnibrowser")
        # 启用磁盘 HTTP 缓存，重复访问速度大幅提升（上限 200MB，0 表示交给引擎自动管理）。
        p.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        cache = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        p.setCachePath(f"{cache}/webengine")
        p.setPersistentStoragePath(f"{data}/webengine")
        p.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        p.setHttpCacheMaximumSize(200 * 1024 * 1024)
        _app_profile = p
    return _app_profile
