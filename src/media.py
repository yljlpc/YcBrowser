"""媒体嗅探：从页面捕获视频/音频直链，供浏览器内置下载。

移植自 SwiftDL（MIT）的扩展 content.js：其做法是在页面里监听媒体加载、
收集 <video>/<audio> 的 currentSrc 与网络层捕获的媒体 URL，
再在播放器旁显示「下载视频」按钮。

本模块的移植与取舍：
- SwiftDL 依赖浏览器扩展的 chrome.webRequest 监听网络请求，
  PyQt6/QtWebEngine 没有等价 API，因此改为**在页面上下文内**嗅探：
  用 MutationObserver + 定时扫描捕获媒体元素的 src，
  并对 <video>/<audio> 的 currentSrc 做实时跟踪。
- 捕获结果保存在 `window.__omni_media`，前端用 runJavaScript 取回，
  在「下载媒体」对话框中列出，用户点击即可用多连接引擎下载。
"""

MEDIA_SNIFF_JS = r"""
(function () {
  if (window.__omni_media) return window.__omni_media;
  var store = window.__omni_media = { items: [], seen: {} };

  function kindOf(url, mime) {
    var u = (url || '').toLowerCase();
    var m = (mime || '').toLowerCase();
    if (m.indexOf('video') === 0) return 'video';
    if (m.indexOf('audio') === 0) return 'audio';
    if (/\.(m3u8|mpd)(\?|$)/.test(u)) return 'stream';
    if (/\.(mp4|webm|mkv|mov|avi|flv|m4v|mpg|mpeg|ts)(\?|$)/.test(u)) return 'video';
    if (/\.(mp3|m4a|aac|ogg|opus|flac|wav|wma)(\?|$)/.test(u)) return 'audio';
    return 'other';
  }

  function extOf(url) {
    var m = (url || '').split('?')[0].split('#')[0].match(/\.([a-z0-9]{2,5})$/i);
    return m ? m[1].toLowerCase() : '';
  }

  function add(url, mime, label) {
    if (!url) return;
    if (!/^https?:/i.test(url)) return;
    if (store.seen[url]) return;
    var kind = kindOf(url, mime);
    if (kind === 'other') return;
    store.seen[url] = 1;
    store.items.push({
      url: url,
      mime: mime || '',
      kind: kind,
      ext: extOf(url),
      label: label || ''
    });
  }

  function scan() {
    try {
      var els = document.querySelectorAll('video, audio, source');
      for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var mime = el.getAttribute('type') || (el.type || '');
        var src = el.currentSrc || el.src || el.getAttribute('src');
        add(src, mime, el.tagName.toLowerCase());
      }
      // 常见的内嵌播放源（blob: 需还原为真实地址）
      var iframes = document.querySelectorAll('iframe[src]');
      for (var j = 0; j < iframes.length; j++) {
        add(iframes[j].getAttribute('src'), 'text/html', 'iframe');
      }
    } catch (e) { /* 忽略 */ }
  }

  // 捕获 fetch/XHR 得到的媒体地址（覆盖 blob 流背后的真实分片）
  try {
    var origFetch = window.fetch;
    window.fetch = function () {
      var p = origFetch.apply(this, arguments);
      try {
        p.then(function (resp) {
          var u = resp && resp.url;
          var ct = resp && resp.headers && resp.headers.get && resp.headers.get('content-type');
          add(u, ct || '', 'fetch');
          return resp;
        });
      } catch (e) { /* 忽略 */ }
      return p;
    };
  } catch (e) { /* 忽略 */ }

  try {
    var origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url) {
      try { add(url, '', 'xhr'); } catch (e) { /* 忽略 */ }
      return origOpen.apply(this, arguments);
    };
  } catch (e) { /* 忽略 */ }

  scan();
  var timer = setInterval(scan, 1200);
  try {
    new MutationObserver(scan).observe(document.documentElement, {childList: true, subtree: true});
  } catch (e) { /* 忽略 */ }
  window.addEventListener('beforeunload', function () { clearInterval(timer); });
  return store;
})();
"""


def parse_media_items(raw):
    """把 JS 返回的媒体列表整理成结构化结果。

    返回 [(kind, url, ext, label)]，kind ∈ {video, audio, stream}。
    非媒体类型（HTML 页面、JS 链接等）一律过滤——只保留可下载的真实媒体。
    """
    out = []
    if not isinstance(raw, list):
        return out
    for it in raw:
        if not isinstance(it, dict):
            continue
        url = str(it.get("url") or "")
        if not url or not url.startswith(("http://", "https://")):
            continue
        kind = str(it.get("kind") or "other")
        if kind not in ("video", "audio", "stream"):
            continue
        ext = str(it.get("ext") or "")
        label = str(it.get("label") or "")
        out.append((kind, url, ext, label))
    return out


def media_filename(url, kind, ext, label=""):
    """为媒体流生成合适的文件名。"""
    base = ""
    if url:
        path = url.split("?")[0].split("#")[0]
        base = path.rsplit("/", 1)[-1]
    if not base or "." not in base:
        if label:
            base = f"{label}.{ext}" if ext else label
        else:
            base = f"media.{ext}" if ext else "media"
    if not ext:
        ext = "mp4" if kind == "video" else ("mp3" if kind == "audio" else "bin")
        if "." not in base:
            base = f"{base}.{ext}"
    return base


def is_stream(kind):
    """流媒体（m3u8/mpd）需要合并工具，不适合直接分片下载。"""
    return kind == "stream"
