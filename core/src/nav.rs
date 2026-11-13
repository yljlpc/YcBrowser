//! 地址栏输入 -> 导航意图的归一化。
//!
//! 这是浏览器最容易被做错的一块：用户输入既可能是 URL、可能是主机名、
//! 也可能是搜索词。规则必须单一确定（可测试），否则会出现把 localhost:8080
//! 送到搜索引擎、或把中文搜索词当域名的经典事故。

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NavIntent {
    /// 直接导航的 URL（已含 scheme）
    Url(String),
    /// 与搜索引擎拼好的查询 URL
    Search(String),
    /// 内部页面：about:/omni:/设置等
    Internal(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SearchEngine {
    Bing,
    Baidu,
    Google,
    DuckDuckGo,
}

impl SearchEngine {
    pub fn parse(s: &str) -> SearchEngine {
        match s.to_ascii_lowercase().as_str() {
            "baidu" => SearchEngine::Baidu,
            "google" => SearchEngine::Google,
            "duckduckgo" | "ddg" => SearchEngine::DuckDuckGo,
            _ => SearchEngine::Bing,
        }
    }

    pub fn query_url(&self, q: &str) -> String {
        let enc = percent_encode(q);
        match self {
            SearchEngine::Bing => format!("https://www.bing.com/search?q={enc}"),
            SearchEngine::Baidu => format!("https://www.baidu.com/s?wd={enc}"),
            SearchEngine::Google => format!("https://www.google.com/search?q={enc}"),
            SearchEngine::DuckDuckGo => format!("https://duckduckgo.com/?q={enc}"),
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            SearchEngine::Bing => "bing",
            SearchEngine::Baidu => "baidu",
            SearchEngine::Google => "google",
            SearchEngine::DuckDuckGo => "duckduckgo",
        }
    }
}

/// 把查询串做最基础的百分号编码（std-only，不依赖 url crate）。
pub fn percent_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len() * 3);
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char)
            }
            _ => {
                out.push('%');
                out.push(hex_digit(b >> 4));
                out.push(hex_digit(b & 0x0f));
            }
        }
    }
    out
}

fn hex_digit(n: u8) -> char {
    match n {
        0..=9 => (b'0' + n) as char,
        _ => (b'A' + (n - 10)) as char,
    }
}

fn is_internal_host(h: &str) -> bool {
    matches!(h, "omni" | "about" | "omni-home" | "settings" | "omni-settings")
}

/// 判定为搜索而非导航的启发式：有空格、无点且非 localhost、TLD 过短。
fn looks_like_search(host: &str) -> bool {
    if host.contains(' ') {
        return true;
    }
    if !host.contains('.') && host != "localhost" {
        return true;
    }
    let tld = host.rsplit('.').next().unwrap_or("");
    if tld.len() < 2 {
        return true;
    }
    false
}

/// 把地址栏原始输入归一化为导航意图。
pub fn resolve(input: &str, engine: SearchEngine) -> NavIntent {
    let raw = input.trim();
    if raw.is_empty() {
        return NavIntent::Internal("omni-home".into());
    }

    // 内部协议
    if let Some(rest) = raw.strip_prefix("omni://") {
        return NavIntent::Internal(format!("omni/{rest}"));
    }
    if raw == "about:blank" || raw == "about:home" {
        return NavIntent::Internal(raw.to_string());
    }

    // 显式 scheme
    if raw.contains("://") || raw.starts_with("file://") || raw.starts_with("data:") {
        return NavIntent::Url(raw.to_string());
    }

    // 形如 host:port（无 scheme、含冒号、纯数字端口、非搜索）
    if let Some((host, port)) = raw.split_once(':') {
        if !port.is_empty()
            && port.chars().all(|c| c.is_ascii_digit())
            && !host.contains(' ')
            && !looks_like_search(host)
        {
            return NavIntent::Url(format!("http://{raw}"));
        }
    }

    // 含空格一定是搜索
    if raw.contains(' ') {
        return NavIntent::Search(engine.query_url(raw));
    }

    // 取 host 部分（去尾杠与路径）
    let host = raw.split('/').next().unwrap_or(raw);
    if is_internal_host(host) {
        return NavIntent::Internal(format!("omni/{host}"));
    }
    if looks_like_search(host) {
        return NavIntent::Search(engine.query_url(raw));
    }

    // 看起来像域名 -> 补 https
    NavIntent::Url(format!("https://{raw}"))
}
