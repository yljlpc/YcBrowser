//! 引擎抽象与调度：WebKit/Blink 主引擎 + Trident 兼容引擎的多后端分发。
//!
//! 设计要点（与 docs/01 的调研结论一一对应）：
//! - 前台只暴露一个 `Engine` 枚举，Shell 不关心渲染器细节；
//! - Trident 在 Linux 上不存在原生实现，因此以 `TridentCompat` 后端落地：
//!   * 文档模式（DocMode）按 X-UA-Compatible 协商，可被页面 meta / HTTP 头覆盖；
//!   * UA 随文档模式逐档伪装（MSIE 7.0 / 8.0 / 9.0 …），与 IE 的真实 UA 字串对齐；
//!   * 遗留 DOM 垫片（document.all / attachEvent / VBScript 拒绝执行 / ActiveX 占位）。
//! - 在 Windows 上若探测到原生 MSHTML，则后端被标记为 `hosted`，由 Shell 侧
//!   托管 `IWebBrowser2`（本 crate 只提供协商结果与注入脚本，不直接调 COM）。

/// 文档模式：Trident 的真实行为是"同一引擎按档位切换解析语义"，
/// 而不是多套引擎。这里把它建模成可持久化、可被页面覆盖的枚举。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DocMode {
    /// IE5.5 / 怪异模式（quirks）
    Ie55Quirks,
    Ie7,
    Ie8,
    Ie9,
    Ie10,
    Ie11,
    /// 现代标准：走 WebKit/Blink
    Edge,
}

impl DocMode {
    pub fn from_ua_compatible(token: &str) -> Option<DocMode> {
        let t = token.trim().trim_matches('"').to_ascii_lowercase();
        let t = t.strip_prefix("ie=").unwrap_or(&t);
        // 兼容页面真实发出的 "EmulateIE7" 这类值
        let t = t.strip_prefix("emulateie").unwrap_or(t);
        match t {
            "5" | "5.5" => Some(DocMode::Ie55Quirks),
            "7" => Some(DocMode::Ie7),
            "8" => Some(DocMode::Ie8),
            "9" => Some(DocMode::Ie9),
            "10" => Some(DocMode::Ie10),
            "11" => Some(DocMode::Ie11),
            "edge" => Some(DocMode::Edge),
            _ => None,
        }
    }

    /// 由命令行/配置串解析档位（ie7/ie8/ie11/edge 等）。
    pub fn from_cmd(s: &str) -> Option<DocMode> {
        match s.to_ascii_lowercase().as_str() {
            "ie55" | "ie5.5" | "quirks" => Some(DocMode::Ie55Quirks),
            "ie7" => Some(DocMode::Ie7),
            "ie8" => Some(DocMode::Ie8),
            "ie9" => Some(DocMode::Ie9),
            "ie10" => Some(DocMode::Ie10),
            "ie11" => Some(DocMode::Ie11),
            "edge" | "modern" => Some(DocMode::Edge),
            _ => None,
        }
    }

    pub fn label(&self) -> &'static str {
        match self {
            DocMode::Ie55Quirks => "IE5.5-quirks",
            DocMode::Ie7 => "IE7",
            DocMode::Ie8 => "IE8",
            DocMode::Ie9 => "IE9",
            DocMode::Ie10 => "IE10",
            DocMode::Ie11 => "IE11",
            DocMode::Edge => "Edge",
        }
    }

    /// Trident 的 MSIE 版本号。返回 None 表示该档位应使用现代引擎。
    pub fn msie_version(&self) -> Option<u32> {
        match self {
            DocMode::Ie55Quirks => Some(5),
            DocMode::Ie7 => Some(7),
            DocMode::Ie8 => Some(8),
            DocMode::Ie9 => Some(9),
            DocMode::Ie10 => Some(10),
            DocMode::Ie11 => Some(11),
            DocMode::Edge => None,
        }
    }

    /// 由 MSIE 版本反查档位（读配置/用户覆盖用）。
    pub fn from_msie(v: u32) -> DocMode {
        match v {
            55 => DocMode::Ie55Quirks,
            8 => DocMode::Ie8,
            9 => DocMode::Ie9,
            10 => DocMode::Ie10,
            11 => DocMode::Ie11,
            _ => DocMode::Ie7,
        }
    }

    /// 是否使用怪异模式（决定 CSS 盒模型，直接影响控件宽度）。
    pub fn is_quirks(&self) -> bool {
        matches!(self, DocMode::Ie55Quirks)
    }
}

/// 引擎后端选择。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Backend {
    /// WebKitGTK（WebCore + JavaScriptCore），WebKit2 多进程语义
    WebKit,
    /// Blink（Chromium content + V8），原生多进程 + Mojo
    Blink,
    /// Trident 兼容后端
    TridentCompat,
}

impl Backend {
    pub fn parse(s: &str) -> Option<Backend> {
        match s.to_ascii_lowercase().as_str() {
            "webkit" | "webkit2" | "webkitgtk" => Some(Backend::WebKit),
            "blink" | "chromium" | "qtwebengine" => Some(Backend::Blink),
            "trident" | "mshtml" | "ie" | "auto" => Some(Backend::TridentCompat),
            _ => None,
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            Backend::WebKit => "webkit2gtk",
            Backend::Blink => "blink-qtwebengine",
            Backend::TridentCompat => "trident-compat",
        }
    }
}

/// 一个标签页的运行时内核配置。
#[derive(Debug, Clone)]
pub struct EngineSpec {
    pub backend: Backend,
    pub doc_mode: DocMode,
    /// Trident 兼容模式是否伪装 UA（现代引擎不伪装）
    pub cloak_ua: bool,
    /// 是否注入遗留 DOM 垫片
    pub legacy_shims: bool,
}

impl EngineSpec {
    pub fn for_backend(backend: Backend) -> EngineSpec {
        match backend {
            Backend::TridentCompat => EngineSpec {
                backend,
                doc_mode: DocMode::Ie11,
                cloak_ua: true,
                legacy_shims: true,
            },
            _ => EngineSpec {
                backend,
                doc_mode: DocMode::Edge,
                cloak_ua: false,
                legacy_shims: false,
            },
        }
    }

    /// Trident 的默认 UA（与真实 IE11 Win64 对齐，便于老站识别）。
    pub fn trident_ua(&self) -> String {
        let v = self.doc_mode.msie_version().unwrap_or(11);
        if self.doc_mode == DocMode::Ie55Quirks {
            return "Mozilla/4.0 (compatible; MSIE 5.5; Windows NT 6.1; Trident/4.0)".into();
        }
        if v <= 7 {
            format!("Mozilla/4.0 (compatible; MSIE {v}.0; Windows NT 10.0; Trident/3.1)")
        } else if v == 8 {
            "Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.1; Trident/4.0)".into()
        } else if v == 9 {
            "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)".into()
        } else if v == 10 {
            "Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.2; Trident/6.0)".into()
        } else {
            "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko".into()
        }
    }

    /// 现代引擎的 UA（Blink 家族，收敛为 Chromium 串以减少站点对 WebKit 的歧路优化）。
    pub fn modern_ua(&self) -> String {
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) \
         OmniBrowser/1.0 Chrome/128.0.0.0 Safari/537.36"
            .into()
    }

    pub fn effective_ua(&self) -> String {
        if self.cloak_ua { self.trident_ua() } else { self.modern_ua() }
    }
}
