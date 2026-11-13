"""页面翻译客户端：网络请求、缓存、批量调度与译文回填。

架构分工：
- **Rust 核心**（core/src/translate.rs）：语言检测、分句、术语统一、中文润色。
  这部分是「翻译得像人话」的关键，且是确定性规则，可单元测试。
- **Python 前端**（本模块）：负责网络 I/O。核心零依赖无法引入 HTTP/TLS 客户端，
  故由前端用标准库 urllib 发请求；本模块只用标准库，无第三方依赖。

后端策略（按可用性自动降级）：
1. `mymemory`   —— 公共免费接口，无需密钥，开箱即用（默认）。
2. `libretranslate` —— 自建/公共实例，可配置。
3. `google`     —— 官方公开的网页翻译端点（部分网络环境可达）。
4. 自定义端点   —— 用户在设置里填 HTTP(S) 地址 + 模板，占位符 {text}/{source}/{target}。

质量策略（对应「不要机翻直译」）：
- 逐句送译而非整段送译：短句歧义少、失败可局部回退；
- 译文回来后统一过一遍核心的术语统一 + 中文润色（去被动、拆长句、修标点）；
- 命中缓存则跳过网络请求（同一页面重复翻译零延迟）。
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

# 默认术语表：把机翻常见的冗长表达统一为简洁中文。
# 格式："英文或机翻表述,目标中文"，每行一条。
DEFAULT_GLOSSARY = """web browser,浏览器
web page,网页
web site,网站
browser engine,浏览器内核
operating system,操作系统
personal computer,电脑
application program,应用程序
software,软件
hardware,硬件
download,下载
upload,上传
setting,设置
configuration,配置
default,默认
folder,文件夹
directory,目录
file,文件
database,数据库
password,密码
username,用户名
account,账号
update,更新
upgrade,升级
install,安装
uninstall,卸载
extension,扩展
plugin,插件
bookmark,书签
history,历史记录
cookie,Cookie
cache,缓存
network,网络
server,服务器
client,客户端
protocol,协议
interface,界面
toolbar,工具栏
shortcut,快捷键
privacy,隐私
security,安全
performance,性能
memory,内存
processor,处理器
screen,屏幕
resolution,分辨率
error,错误
warning,警告
success,成功
failed,失败"""

# 语言代码映射（MyMemory 用 en|zh-CN 形式）
_LANG_CODES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-tw": "zh-TW",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "ru": "ru",
}


def _code(lang):
    """把内部语言标签映射为后端使用的语言代码。"""
    return _LANG_CODES.get(str(lang).lower(), str(lang))


class TranslationError(Exception):
    """翻译请求失败。"""


class TranslateClient:
    """翻译后端客户端（标准库实现，无第三方依赖）。"""

    def __init__(self, core=None, backend="mymemory", endpoint="", timeout=12.0):
        self.core = core
        self.backend = backend or "mymemory"
        self.endpoint = endpoint or ""
        self.timeout = timeout
        self._cache = {}
        self._last_error = ""

    # ---------------- 对外接口 ----------------
    def translate(self, text, source="auto", target="zh", glossary=None):
        """翻译单段文本，返回译文。失败时抛 TranslationError。"""
        text = (text or "").strip()
        if not text:
            return ""
        key = (self.backend, self.endpoint, _code(source), _code(target), text)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        raw = self._request(text, source, target)
        if not raw:
            raise TranslationError("后端返回空译文")
        out = self.polish(raw, glossary)
        self._cache[key] = out
        return out

    def translate_many(self, items, source="auto", target="zh", glossary=None,
                       progress=None):
        """批量翻译：返回 {原文: 译文} 映射。

        逐条串行请求以免被后端限流；进度回调用于 UI 反馈。
        """
        out = {}
        total = max(1, len(items))
        for i, item in enumerate(items, 1):
            t = (item or "").strip()
            if not t:
                continue
            try:
                out[item] = self.translate(t, source, target, glossary)
            except TranslationError as exc:
                self._last_error = str(exc)
                out[item] = ""  # 失败保留原文由调用方决定
            if progress:
                progress(i, total)
            # 轻微节流，避免触发后端限流
            if i < total:
                time.sleep(0.02)
        return out

    def polish(self, text, glossary=None):
        """把译文过一遍核心的术语统一 + 中文润色。"""
        if self.core is None:
            return text
        spec = glossary if glossary is not None else DEFAULT_GLOSSARY
        try:
            res = self.core.request("translate_polish", text=text, glossary=spec)
        except Exception:  # noqa: BLE001
            return text
        if isinstance(res, dict) and res.get("ok") is False:
            return text
        if isinstance(res, dict):
            return res.get("text") or text
        return text

    def detect_lang(self, text):
        if self.core is None:
            return "unknown"
        res = self.core.request("translate_detect_lang", text=text)
        if isinstance(res, dict):
            return res.get("lang", "unknown")
        return "unknown"

    def should_translate(self, text, target="zh"):
        if self.core is None:
            return bool(text and text.strip())
        res = self.core.request("translate_should", text=text, target=target)
        if isinstance(res, dict):
            return bool(res.get("should"))
        return False

    def split(self, text):
        if self.core is None:
            return [text] if text else []
        res = self.core.request("translate_split", text=text)
        if isinstance(res, dict):
            return res.get("sentences") or []
        return []

    @property
    def last_error(self):
        return self._last_error

    def cache_stats(self):
        return len(self._cache)

    # ---------------- 后端实现 ----------------
    def _request(self, text, source, target):
        backend = self.backend
        if backend == "custom":
            return self._request_custom(text, source, target)
        if backend == "libretranslate":
            return self._request_libre(text, source, target)
        if backend == "google":
            return self._request_google(text, source, target)
        return self._request_mymemory(text, source, target)

    def _request_mymemory(self, text, source, target):
        src = "en" if source in ("auto", "") else _code(source)
        dst = _code(target)
        url = ("https://api.mymemory.translated.net/get?"
               + urllib.parse.urlencode({
                   "q": text,
                   "langpair": f"{src}|{dst}",
               }))
        data = self._http_get_json(url)
        resp = data.get("responseData") or {}
        translated = resp.get("translatedText")
        if not translated:
            raise TranslationError(str(data.get("responseDetails") or "MyMemory 无译文"))
        # MyMemory 对无译文时返回原文并附 429 等状态，需识别
        if str(data.get("responseStatus")) not in ("200", "200.0", "None", ""):
            raise TranslationError(f"MyMemory 状态 {data.get('responseStatus')}")
        return _unescape_html(translated)

    def _request_libre(self, text, source, target):
        base = self.endpoint or "http://127.0.0.1:5000"
        payload = {
            "q": text,
            "source": "auto" if source in ("auto", "") else _code(source),
            "target": _code(target),
            "format": "text",
        }
        data = self._http_post_json(base.rstrip("/") + "/translate", payload)
        translated = data.get("translatedText")
        if not translated:
            raise TranslationError(str(data.get("error") or "LibreTranslate 无译文"))
        return translated

    def _request_google(self, text, source, target):
        src = "auto" if source in ("auto", "") else _code(source)
        dst = _code(target)
        url = ("https://translate.googleapis.com/translate_a/single?"
               + urllib.parse.urlencode({
                   "client": "gtx",
                   "sl": src,
                   "tl": dst,
                   "dt": "t",
                   "q": text,
               }))
        raw = self._http_get_text(url)
        try:
            data = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(f"Google 返回非 JSON: {exc}") from exc
        if not isinstance(data, list) or not data:
            raise TranslationError("Google 返回结构异常")
        chunks = data[0]
        if not isinstance(chunks, list) or not chunks:
            raise TranslationError("Google 无译文")
        out = "".join((c[0] or "") for c in chunks if isinstance(c, list) and c)
        return out

    def _request_custom(self, text, source, target):
        """自定义端点：地址中可用 {text} {source} {target} 占位符，否则按 JSON POST。

        JSON POST 约定：请求体 {"text":..,"source":..,"target":..}，
        响应体 {"translatedText": "..."} 或 {"translation": "..."} 或 {"data": {"translation": "..."}}。
        """
        if not self.endpoint:
            raise TranslationError("未配置自定义翻译端点")
        ep = self.endpoint
        if "{text}" in ep:
            url = (ep.replace("{text}", urllib.parse.quote(text, safe=""))
                      .replace("{source}", urllib.parse.quote(_code(source), safe=""))
                      .replace("{target}", urllib.parse.quote(_code(target), safe="")))
            return self._http_get_text(url)
        payload = {
            "text": text,
            "source": "auto" if source in ("auto", "") else _code(source),
            "target": _code(target),
        }
        data = self._http_post_json(ep, payload)
        for path in (("translatedText",), ("translation",), ("data", "translation"),
                     ("result", "translatedText"), ("data", "text")):
            node = data
            ok = True
            for key in path:
                if isinstance(node, dict) and key in node:
                    node = node[key]
                else:
                    ok = False
                    break
            if ok and isinstance(node, str) and node:
                return node
        raise TranslationError("自定义端点响应中未找到译文字段")

    # ---------------- HTTP ----------------
    def _http_get_text(self, url):
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) YcBrowser/1.0",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raise TranslationError(f"HTTP {exc.code}") from exc
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(f"网络错误：{exc}") from exc

    def _http_get_json(self, url):
        raw = self._http_get_text(url)
        try:
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(f"响应非 JSON：{exc}") from exc

    def _http_post_json(self, url, payload):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) YcBrowser/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raise TranslationError(f"HTTP {exc.code}") from exc
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(f"网络错误：{exc}") from exc
        try:
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(f"响应非 JSON：{exc}") from exc


def _unescape_html(s):
    """还原被 HTML 实体转义的译文（如 &amp; &#39;）。"""
    if "&" not in s:
        return s
    try:
        import html as _html

        return _html.unescape(s)
    except Exception:  # noqa: BLE001
        return re.sub(r"&[a-zA-Z#0-9]+;", "", s)


# ---------------- 页面内容提取与回填 ----------------

# 提取页面正文文本的 JS：遍历可见文本节点，跳过脚本/样式/代码/输入框等。
EXTRACT_JS = r"""
(function () {
  var SKIP = {SCRIPT:1, STYLE:1, NOSCRIPT:1, CODE:1, PRE:1, TEXTAREA:1,
              INPUT:1, SELECT:1, OPTION:1, SVG:1, CANVAS:1, IFRAME:1, HEAD:1, TITLE:1};
  var walker = document.createTreeWalker(document.body || document.documentElement,
      NodeFilter.SHOW_TEXT, {
        acceptNode: function (node) {
          if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
          var p = node.parentNode;
          while (p && p.nodeType === 1) {
            if (SKIP[p.nodeName]) return NodeFilter.FILTER_REJECT;
            if (p.getAttribute && p.getAttribute('translate') === 'no') return NodeFilter.FILTER_REJECT;
            if (p.classList && (p.classList.contains('notranslate'))) return NodeFilter.FILTER_REJECT;
            p = p.parentNode;
          }
          var txt = node.nodeValue.trim();
          if (txt.length < 2) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      });
  var out = [];
  var n;
  while ((n = walker.nextNode())) {
    var t = n.nodeValue.trim();
    if (t.length < 2) continue;
    out.push(t);
  }
  return out;
})();
"""

# 回填译文的 JS：按文本节点内容查译文并替换，同时按序号保存原文以支持"显示原文"切换。
#
# 注意：译文映射以「原文」为键（前端 translate_many 返回 {原文: 译文}），
# 因此这里必须按节点文本查表，而不是按序号——两者键类型不一致会导致回填静默失效。
FILL_JS = r"""
(function (pairs) {
  if (!window.__omni_translate__) {
    window.__omni_translate__ = {originals: {}, index: 0};
  }
  var store = window.__omni_translate__;
  var walker = document.createTreeWalker(document.body || document.documentElement,
      NodeFilter.SHOW_TEXT, {
        acceptNode: function (node) {
          if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
          var p = node.parentNode;
          while (p && p.nodeType === 1) {
            var n = p.nodeName;
            if (n === 'SCRIPT' || n === 'STYLE' || n === 'NOSCRIPT' || n === 'CODE' ||
                n === 'PRE' || n === 'TEXTAREA' || n === 'INPUT' || n === 'SELECT' ||
                n === 'OPTION' || n === 'SVG' || n === 'CANVAS' || n === 'IFRAME' ||
                n === 'HEAD' || n === 'TITLE') return NodeFilter.FILTER_REJECT;
            if (p.getAttribute && p.getAttribute('translate') === 'no') return NodeFilter.FILTER_REJECT;
            p = p.parentNode;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      });
  var i = 0, applied = 0;
  var n;
  while ((n = walker.nextNode())) {
    var key = String(i);
    i += 1;
    var raw = n.nodeValue;
    var trimmed = raw.trim();
    var val = pairs[trimmed];
    if (val === undefined || val === null || val === '') continue;
    // 保存原文（首次替换时），并按原文的空白样式套回译文
    if (store.originals[key] === undefined) {
      store.originals[key] = raw;
    }
    var lead = raw.slice(0, raw.length - raw.replace(/^\s+/, '').length);
    var tail = raw.slice(raw.replace(/\s+$/, '').length);
    n.nodeValue = lead + val + tail;
    applied += 1;
  }
  return applied;
})(__PAIRS__);
"""

# 还原原文的 JS：按与 FILL_JS 相同的遍历顺序，依次写回保存的原文。
RESTORE_JS = r"""
(function () {
  var store = window.__omni_translate__;
  if (!store || !store.originals) return 0;
  var walker = document.createTreeWalker(document.body || document.documentElement,
      NodeFilter.SHOW_TEXT, {
        acceptNode: function (node) {
          if (!node.nodeValue) return NodeFilter.FILTER_REJECT;
          var p = node.parentNode;
          while (p && p.nodeType === 1) {
            var n = p.nodeName;
            if (n === 'SCRIPT' || n === 'STYLE' || n === 'NOSCRIPT' || n === 'CODE' ||
                n === 'PRE' || n === 'TEXTAREA' || n === 'INPUT' || n === 'SELECT' ||
                n === 'OPTION' || n === 'SVG' || n === 'CANVAS' || n === 'IFRAME' ||
                n === 'HEAD' || n === 'TITLE') return NodeFilter.FILTER_REJECT;
            p = p.parentNode;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      });
  var i = 0, restored = 0;
  var n;
  while ((n = walker.nextNode())) {
    var key = String(i);
    i += 1;
    if (store.originals[key] !== undefined) {
      n.nodeValue = store.originals[key];
      restored += 1;
    }
  }
  return restored;
})();
"""
