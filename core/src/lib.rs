//! OmniBrowser 原生核心：
//! 引擎抽象与调度（WebKit/Blink + Trident 兼容）、导航归一化、行式 JSON-RPC。
//!
//! 设计约束：零第三方依赖，任何离线机器 `cargo build` 均可过（见 docs/03）。

pub mod json;
pub mod engine;
pub mod nav;
pub mod ipc;
pub mod translate;
pub mod download;

#[cfg(test)]
mod tests {
    use crate::engine::{Backend, DocMode, EngineSpec};
    use crate::json::{parse, Json};
    use crate::nav::{resolve, NavIntent, SearchEngine};

    #[test]
    fn docmode_ua_alignment() {
        let spec = EngineSpec::for_backend(Backend::TridentCompat);
        assert!(spec.cloak_ua);
        // IE11 的真实 UA 已不含 MSIE 字串，改用 Trident 标记校验伪装生效。
        assert!(spec.effective_ua().contains("Trident"));
    }

    #[test]
    fn blink_uses_modern_ua() {
        let spec = EngineSpec::for_backend(Backend::Blink);
        assert!(!spec.cloak_ua);
        assert!(spec.effective_ua().contains("Chrome"));
    }

    #[test]
    fn resolve_url_keeps_scheme() {
        let i = resolve("https://example.com", SearchEngine::Bing);
        match i {
            NavIntent::Url(u) => assert_eq!(u, "https://example.com"),
            _ => panic!("expected url"),
        }
    }

    #[test]
    fn resolve_host_port() {
        let i = resolve("localhost:8080", SearchEngine::Bing);
        match i {
            NavIntent::Url(u) => assert!(u.starts_with("http://localhost:8080")),
            _ => panic!("expected url for host:port"),
        }
    }

    #[test]
    fn resolve_search_with_space() {
        let i = resolve("rust language", SearchEngine::Baidu);
        match i {
            NavIntent::Search(u) => assert!(u.contains("baidu.com")),
            _ => panic!("expected search"),
        }
    }

    #[test]
    fn resolve_naked_domain() {
        let i = resolve("example.org", SearchEngine::Bing);
        match i {
            NavIntent::Url(u) => assert!(u.starts_with("https://example.org")),
            _ => panic!("expected url"),
        }
    }

    #[test]
    fn internal_scheme() {
        let i = resolve("omni://settings", SearchEngine::Bing);
        match i {
            NavIntent::Internal(p) => assert!(p.starts_with("omni/")),
            _ => panic!("expected internal"),
        }
    }

    #[test]
    fn parse_roundtrip() {
        let j = parse("{\"ok\":true,\"n\":3}").unwrap();
        assert_eq!(j.get("n").and_then(|v| v.as_int()), Some(3));
        assert_eq!(j.get("ok").and_then(|v| v.as_bool()), Some(true));
    }

    #[test]
    fn docmode_from_cmd() {
        assert_eq!(DocMode::from_cmd("ie11"), Some(DocMode::Ie11));
        assert_eq!(DocMode::from_cmd("edge"), Some(DocMode::Edge));
        assert_eq!(DocMode::from_cmd("nonsense"), None);
    }

    #[test]
    fn ua_compatible_emulate_form() {
        // 真实页面常发 "IE=EmulateIE7"，必须正确解析而非回退到 IE11。
        assert_eq!(DocMode::from_ua_compatible("IE=EmulateIE7"), Some(DocMode::Ie7));
        assert_eq!(DocMode::from_ua_compatible("IE=edge"), Some(DocMode::Edge));
        assert_eq!(DocMode::from_ua_compatible("IE=9"), Some(DocMode::Ie9));
    }
}
