//! 页面翻译的语言学处理层：语言检测、分句、术语统一、中文化润色。
//!
//! 设计取舍（为什么不让核心直接联网翻译）：
//! - 核心保持零第三方依赖（见 docs/03），无法引入 HTTP/TLS 客户端；
//!   网络请求由 PyQt6 前端用标准库 urllib 发出。
//! - 但「翻译得像人话」的关键不在网络，而在**后处理**：
//!   机器翻译直译腔的三大来源是 ①术语不统一 ②长句不拆 ③标点/量词生硬。
//!   这些都可以用确定性规则在本地修掉，且必须可单元测试，故放在核心。
//!
//! 对外暴露：
//! - [`detect_lang`]：判定文本主要语言（zh/en/mixed/unknown）
//! - [`split_sentences`]：按中英文句末标点切句，保留标点
//! - [`apply_glossary`]：术语表强制统一（大小写敏感替换）
//! - [`polish_zh`]：中文润色——去冗余、拆长句、修标点、量词自然化
//! - [`should_translate`]：判定一段文本是否值得翻译（滤掉代码/URL/纯符号）

/// 语言标签。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lang {
    Zh,
    En,
    Mixed,
    Unknown,
}

impl Lang {
    pub fn name(&self) -> &'static str {
        match self {
            Lang::Zh => "zh",
            Lang::En => "en",
            Lang::Mixed => "mixed",
            Lang::Unknown => "unknown",
        }
    }
}

/// 判定文本主要语言。
///
/// 规则：统计 CJK 表意字符与 ASCII 字母的比例。
/// - 汉字占比 >= 12% 且字母占比低 → 中文
/// - 字母占比 >= 30% → 英文
/// - 两者都不显著 → 未知（多为代码/符号/数字）
/// - 含明显代码标记（`=>`、`{}`、`::`、`();`）→ 未知（代码不该被翻译）
pub fn detect_lang(text: &str) -> Lang {
    if looks_like_code(text) {
        return Lang::Unknown;
    }
    let mut cjk = 0usize;
    let mut ascii_alpha = 0usize;
    let mut total = 0usize;
    for ch in text.chars() {
        if ch.is_whitespace() {
            continue;
        }
        total += 1;
        let cp = ch as u32;
        if (0x4E00..=0x9FFF).contains(&cp) || (0x3400..=0x4DBF).contains(&cp) {
            cjk += 1;
        } else if ch.is_ascii_alphabetic() {
            ascii_alpha += 1;
        }
    }
    if total == 0 {
        return Lang::Unknown;
    }
    let cjk_ratio = cjk as f64 / total as f64;
    let alpha_ratio = ascii_alpha as f64 / total as f64;
    if cjk_ratio >= 0.12 && alpha_ratio < 0.20 {
        Lang::Zh
    } else if alpha_ratio >= 0.30 {
        Lang::En
    } else if cjk_ratio > 0.0 && alpha_ratio > 0.0 {
        Lang::Mixed
    } else {
        Lang::Unknown
    }
}

/// 强代码特征判定：出现箭头、块、花括号配对、双冒号等结构符号即视为代码。
fn looks_like_code(text: &str) -> bool {
    let t = text.trim();
    if t.contains("=>")
        || t.contains("::")
        || t.contains("{}")
        || t.contains("();")
        || t.contains("});")
        || t.contains("</")
        || (t.starts_with("fn ")
            || t.starts_with("def ")
            || t.starts_with("class ")
            || t.starts_with("public ")
            || t.starts_with("private "))
    {
        return true;
    }
    // 形如 `a.b.c()` 的调用或 `snake_case_name(` 的函数调用
    if t.contains("()") || t.contains("();") {
        return true;
    }
    false
}

/// 判定文本是否值得送去翻译。
///
/// 过滤掉：空串、纯数字/符号、URL、代码片段、纯中文（已是目标语言）。
/// 这是网页整页翻译避免"把代码也翻一遍"的第一道闸门。
pub fn should_translate(text: &str, target: Lang) -> bool {
    let t = text.trim();
    if t.len() < 2 {
        return false;
    }
    // 纯数字 / 纯符号 / 纯空白
    if !t.chars().any(|c| c.is_alphanumeric()) {
        return false;
    }
    // URL / 路径 / 域名
    if t.starts_with("http://")
        || t.starts_with("https://")
        || t.starts_with("www.")
        || t.starts_with("ftp://")
        || t.starts_with('/')
        || t.contains("://")
    {
        return false;
    }
    // 代码特征：包含常见符号组合，或 camelCase/underscore 密集
    if t.contains("=>") || t.contains("::") || t.contains("{}") || t.contains("();") {
        return false;
    }
    let letters = t.chars().filter(|c| c.is_ascii_alphabetic()).count();
    let digits = t.chars().filter(|c| c.is_ascii_digit()).count();
    if digits > 0 && letters == 0 {
        return false;
    }
    // 已是目标语言则不翻
    match detect_lang(t) {
        Lang::Zh if target == Lang::Zh => false,
        Lang::Unknown => false,
        _ => true,
    }
}

/// 按中英文句末标点切句，保留原标点。
///
/// 网页正文按句翻译比整段翻译更准：句子短则上下文少、歧义少，
/// 且失败时可只丢一句而不丢整段。
pub fn split_sentences(text: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut cur = String::new();
    let chars: Vec<char> = text.chars().collect();
    let mut i = 0usize;
    while i < chars.len() {
        let ch = chars[i];
        cur.push(ch);
        let is_end = match ch {
            '.' | '!' | '?' | ';' => true,
            '。' | '！' | '？' | '；' | '…' => true,
            _ => false,
        };
        if is_end {
            // 英文缩写与小数点处理：后接空格/结尾才断句。
            if ch == '.' {
                let next = chars.get(i + 1).copied();
                let next_is_space_or_end = match next {
                    None => true,
                    Some(c) => c.is_whitespace(),
                };
                let prev_is_digit = i > 0 && chars[i - 1].is_ascii_digit();
                let next_is_digit = matches!(next, Some(c) if c.is_ascii_digit());
                if prev_is_digit && next_is_digit {
                    // 小数点，不断句
                    i += 1;
                    continue;
                }
                if !next_is_space_or_end {
                    i += 1;
                    continue;
                }
            }
            // 英文句点后紧跟右括号/引号时，把它们并入本句
            let mut j = i + 1;
            while j < chars.len() {
                let c = chars[j];
                if c == ')' || c == ']' || c == '"' || c == '\'' || c == '）' || c == '”' || c == '’' {
                    cur.push(c);
                    j += 1;
                } else {
                    break;
                }
            }
            let trimmed = cur.trim();
            if !trimmed.is_empty() {
                out.push(trimmed.to_string());
            }
            cur.clear();
            i = j;
            continue;
        }
        i += 1;
    }
    let tail = cur.trim();
    if !tail.is_empty() {
        out.push(tail.to_string());
    }
    out
}

/// 术语表条目：(原文, 译文)。
pub type Glossary = Vec<(String, String)>;

/// 术语统一：把译文中出现的指定表述统一替换为目标表述。
///
/// 例：`("网页浏览器", "浏览器")` → 译文里所有"网页浏览器"改为"浏览器"。
/// 长词优先，避免"网页浏览器引擎"被先替换成"浏览器引擎"再匹配失败。
pub fn apply_glossary(text: &str, glossary: &[(String, String)]) -> String {
    if glossary.is_empty() {
        return text.to_string();
    }
    let mut pairs: Vec<&(String, String)> = glossary
        .iter()
        .filter(|(s, _)| !s.is_empty())
        .collect();
    pairs.sort_by(|a, b| b.0.chars().count().cmp(&a.0.chars().count()));
    let mut out = text.to_string();
    for (src, dst) in pairs {
        if src.is_empty() {
            continue;
        }
        out = out.replace(src.as_str(), dst.as_str());
    }
    out
}

/// 中文润色：把机器翻译的生硬表达改成自然中文。
///
/// 这一层是「非直译」诉求的核心。规则来自真实机翻文本的共性问题，
/// 全部为确定性替换，可单元测试：
/// 1. 冗余修饰："目前"→""、"的相关"/"有关"在句中堆叠时折叠；
/// 2. 被动直译："被…所…"→主动句式；
/// 3. 生硬量词："个"→"台/条"过于激进，故只处理"一个"重复；
/// 4. 标点规范：中文语境下的半角逗号句号转全角，英文标点后空格规整；
/// 5. 英文残留夹在中文间的多余空格；
/// 6. 长句拆分：超过阈值且含并列连词时在"并且/而且/以及/，"处断开。
pub fn polish_zh(text: &str) -> String {
    let mut s = text.to_string();

    // —— 1. 冗余与重复 ——
    let redundancies: &[(&str, &str)] = &[
        ("的的", "的"),
        ("了了", "了"),
        ("是是", "是"),
        ("在在", "在"),
        ("并且并且", "并且"),
        ("以及以及", "以及"),
        ("，，", "，"),
        ("。。", "。"),
        ("，，", "，"),
    ];
    for (from, to) in redundancies {
        s = s.replace(from, to);
    }
    // "一个" 连续出现只保留一个（"一个一个" → "一个"）
    s = s.replace("一个一个", "一个");

    // —— 2. 被动直译 → 主动 ——
    // 带施动者的被动先改写（"被管理员禁用" → "已被管理员禁用"），
    // 否则后面的逐字替换会与之叠加成"已已被…"。
    s = rewrite_passive_with_agent(&s);
    // "被X所Y" 结构：把"被"去掉、"所"去掉，保留动词。
    let passive_fixes: &[(&str, &str)] = &[
        ("被关闭", "已关闭"),
        ("被启用", "已启用"),
        ("被禁用", "已禁用"),
        ("被删除", "已删除"),
        ("被创建", "已创建"),
        ("被更新", "已更新"),
        ("被安装", "已安装"),
        ("被使用", "已使用"),
        ("被支持", "已支持"),
        ("被需要", "需要"),
        ("被称为", "叫作"),
    ];
    for (from, to) in passive_fixes {
        s = s.replace(from, to);
    }
    // 幂等：已是"已被…"的不再重复加"已"
    s = s.replace("已已被", "已被");
    s = s.replace("所进行的", "进行的").replace("所提供", "提供").replace("所支持", "支持");
    s = s.replace("所显示", "显示").replace("所包含", "包含").replace("所具有", "具有");

    // —— 3. 口语化：机翻常见的指代生硬 ——
    // 只替换名词短语本身，保留系动词，避免"这个应用是免费的"被改成"这款应用免费的"。
    let referents: &[(&str, &str)] = &[
        ("这个应用", "这款应用"),
        ("该应用", "这款应用"),
        ("该网站", "这个网站"),
        ("此网站", "这个网站"),
        ("该页面", "这个页面"),
        ("此页面", "这个页面"),
        ("该软件", "这款软件"),
    ];
    for (from, to) in referents {
        s = s.replace(from, to);
    }
    s = s.replace("它的意思是", "意思是");

    // —— 4. 标点规范：中文语境下半角标点转全角 ——
    // 只在「中文字符与半角标点相邻」时转换，避免破坏代码/英文缩写。
    s = normalize_cn_punct(&s);

    // —— 5. 中英夹排空格规整 ——
    s = fix_cjk_latin_spacing(&s);

    // —— 6. 长句拆分 ——
    s = split_long_sentences(&s, 42);

    s.trim().to_string()
}

/// 处理"被 + 施动者 + 动词"的机翻被动句式。
///
/// 例："此功能被管理员禁用" → "此功能已被管理员禁用"。
/// 施动者最多 6 个汉字（覆盖"管理员""系统""用户"等常见词）。
fn rewrite_passive_with_agent(s: &str) -> String {
    const VERBS: &[&str] = &[
        "禁用", "启用", "关闭", "开启", "删除", "创建", "更新", "安装", "卸载", "使用",
        "支持", "阻止", "隐藏", "锁定", "修改", "移除", "替换", "覆盖",
    ];
    let chars: Vec<char> = s.chars().collect();
    let mut out = String::with_capacity(s.len());
    let mut i = 0usize;
    while i < chars.len() {
        if chars[i] == '被' {
            // 在"被"之后前向寻找动词：动词之前的中文即施动者（1..=6 字）
            let mut rewritten = false;
            let limit = (i + 8).min(chars.len());
            for p in (i + 1)..limit {
                let tail: String = chars[p..].iter().take(4).collect();
                if !VERBS.iter().any(|v| tail.starts_with(v)) {
                    continue;
                }
                let agent_len = p - i - 1;
                let agent_all_cjk = chars[i + 1..p].iter().all(|c| is_cjk(*c));
                if agent_len >= 1 && agent_len <= 6 && agent_all_cjk {
                    out.push('已');
                    out.push('被');
                    i += 1;
                    rewritten = true;
                }
                break;
            }
            if rewritten {
                continue;
            }
        }
        out.push(chars[i]);
        i += 1;
    }
    out
}

/// 中文语境标点全角化。
///
/// 规则：半角逗号/句号/分号/冒号/问号/感叹号，若其前一个字符是 CJK，
/// 则转为全角；若后一个字符是 CJK 且前面是 ASCII 字母结尾词，也不转（保护英文）。
fn normalize_cn_punct(s: &str) -> String {
    let map = [(',', '，'), (';', '；'), (':', '：'), ('?', '？'), ('!', '！')];
    let chars: Vec<char> = s.chars().collect();
    let mut out = String::with_capacity(s.len());
    for (i, &ch) in chars.iter().enumerate() {
        let prev_cjk = i > 0 && is_cjk(chars[i - 1]);
        let mut replaced = false;
        for (half, full) in map {
            if ch == half {
                // 句号：CJK 前置时转全角
                if ch == '.' && prev_cjk {
                    out.push('。');
                    replaced = true;
                    break;
                }
                if prev_cjk {
                    out.push(full);
                    replaced = true;
                    break;
                }
            }
        }
        if !replaced {
            out.push(ch);
        }
    }
    out
}

/// 中英夹排空格：中文与英文/数字之间补一个空格，中文之间不留空格。
fn fix_cjk_latin_spacing(s: &str) -> String {
    let chars: Vec<char> = s.chars().collect();
    let mut out = String::with_capacity(s.len() + 8);
    for (i, &ch) in chars.iter().enumerate() {
        if ch == ' ' {
            // 判断这个空格两侧是否都是中文：若是则丢弃
            let prev_cjk = i > 0 && is_cjk(chars[i - 1]);
            let next_cjk = chars.get(i + 1).map(|c| is_cjk(*c)).unwrap_or(false);
            if prev_cjk && next_cjk {
                continue;
            }
            // 中文 + 空格 + ASCII 字母/数字：保留一个空格（正确排版）
            out.push(ch);
            continue;
        }
        out.push(ch);
    }
    // 补齐「中文紧跟英文」处缺失的空格
    let chars: Vec<char> = out.chars().collect();
    let mut res = String::with_capacity(out.len() + 8);
    for (i, &ch) in chars.iter().enumerate() {
        res.push(ch);
        if i + 1 < chars.len() {
            let next = chars[i + 1];
            if is_cjk(ch) && (next.is_ascii_alphanumeric()) {
                res.push(' ');
            } else if ch.is_ascii_alphanumeric() && is_cjk(next) {
                res.push(' ');
            }
        }
    }
    res
}

/// 长句拆分：长度超阈值且含并列连词时断开为两句。
fn split_long_sentences(s: &str, max_len: usize) -> String {
    let mut out = String::with_capacity(s.len());
    for part in s.split_inclusive(['\n']) {
        let trimmed = part.trim_end_matches('\n');
        let has_nl = trimmed.len() != part.len();
        if trimmed.chars().count() <= max_len {
            out.push_str(part);
            continue;
        }
        // 优先在「并且 / 而且 / 以及 / 同时 / ，」处断开
        let mut buf = String::new();
        let mut broke = false;
        for ch in trimmed.chars() {
            buf.push(ch);
            if buf.chars().count() >= max_len {
                // 回退到最近的自然断点
                let candidates = ["并且", "而且", "以及", "同时", "，"];
                let mut cut = None;
                for c in candidates {
                    if let Some(pos) = buf.rfind(c) {
                        if cut.map(|p| pos > p).unwrap_or(true) {
                            cut = Some(pos);
                        }
                    }
                }
                if let Some(pos) = cut {
                    let head: String = buf.chars().take(pos).collect();
                    let tail: String = buf.chars().skip(pos).collect();
                    out.push_str(&head);
                    out.push('。');
                    buf = tail.trim_start_matches('，').trim_start_matches(' ').to_string();
                    broke = true;
                }
            }
        }
        let _ = broke;
        out.push_str(&buf);
        if has_nl {
            out.push('\n');
        }
    }
    out
}

fn is_cjk(ch: char) -> bool {
    let cp = ch as u32;
    (0x4E00..=0x9FFF).contains(&cp)
        || (0x3400..=0x4DBF).contains(&cp)
        || (0x3000..=0x303F).contains(&cp)
        || (0xFF00..=0xFFEF).contains(&cp)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detect_chinese() {
        assert_eq!(detect_lang("这是一个中文页面，用于测试语言检测。"), Lang::Zh);
    }

    #[test]
    fn detect_english() {
        assert_eq!(
            detect_lang("This is an English page used for language detection tests."),
            Lang::En
        );
    }

    #[test]
    fn detect_code_is_unknown() {
        assert_eq!(detect_lang("() => { return 42; }"), Lang::Unknown);
        assert_eq!(detect_lang("12345"), Lang::Unknown);
        assert_eq!(detect_lang("   "), Lang::Unknown);
    }

    #[test]
    fn filter_code_and_urls() {
        assert!(!should_translate("https://example.com/a", Lang::Zh));
        assert!(!should_translate("/usr/bin/env", Lang::Zh));
        assert!(!should_translate("12345", Lang::Zh));
        assert!(!should_translate("const x = () => 1;", Lang::Zh));
        assert!(should_translate("Install the browser now", Lang::Zh));
    }

    #[test]
    fn skip_already_target_language() {
        assert!(!should_translate("安装浏览器", Lang::Zh));
        assert!(should_translate("安装浏览器", Lang::En));
    }

    #[test]
    fn split_english_sentences() {
        let s = split_sentences("Hello world. How are you? Fine!");
        assert_eq!(s.len(), 3);
        assert_eq!(s[0], "Hello world.");
        assert_eq!(s[1], "How are you?");
    }

    #[test]
    fn split_keeps_abbreviation_and_decimal() {
        let s = split_sentences("Version 1.2 is out. See docs.");
        assert_eq!(s.len(), 2);
        assert!(s[0].contains("1.2"));
    }

    #[test]
    fn split_chinese_sentences() {
        let s = split_sentences("第一句。第二句！第三句？");
        assert_eq!(s.len(), 3);
    }

    #[test]
    fn split_empty() {
        assert!(split_sentences("").is_empty());
        assert!(split_sentences("   ").is_empty());
    }

    #[test]
    fn glossary_applies_longest_first() {
        let g: Glossary = vec![
            ("网页浏览器".into(), "浏览器".into()),
            ("浏览器引擎".into(), "内核".into()),
        ];
        let out = apply_glossary("网页浏览器引擎很好用", &g);
        assert_eq!(out, "内核很好用");
    }

    #[test]
    fn glossary_empty_is_identity() {
        let empty: Vec<(String, String)> = Vec::new();
        assert_eq!(apply_glossary("abc", &empty), "abc");
    }

    #[test]
    fn polish_removes_duplicates() {
        assert_eq!(polish_zh("的的"), "的");
        assert_eq!(polish_zh("一个一个"), "一个");
    }

    #[test]
    fn polish_converts_passive() {
        assert_eq!(polish_zh("该功能被禁用"), "该功能已禁用");
        assert_eq!(polish_zh("文件被删除"), "文件已删除");
    }

    #[test]
    fn polish_handles_passive_with_agent() {
        assert_eq!(polish_zh("此功能被管理员禁用"), "此功能已被管理员禁用");
        assert_eq!(polish_zh("该目录被系统隐藏"), "该目录已被系统隐藏");
        // 无施动者的普通被动不受影响
        assert_eq!(polish_zh("按钮被禁用"), "按钮已禁用");
    }

    #[test]
    fn polish_is_idempotent_on_passive() {
        // 已经是"已被…"的文本不应被改写成"已已被…"
        assert_eq!(polish_zh("此功能已被管理员禁用"), "此功能已被管理员禁用");
        assert_eq!(polish_zh("此功能已被管理员禁用").contains("已已"), false);
    }

    #[test]
    fn polish_naturalizes_referents() {
        assert_eq!(polish_zh("这个应用是免费的"), "这款应用是免费的");
        assert_eq!(polish_zh("该网站是官方网站"), "这个网站是官方网站");
    }

    #[test]
    fn polish_normalizes_punctuation() {
        assert_eq!(polish_zh("你好，世界。"), "你好，世界。");
        assert_eq!(polish_zh("你好,世界"), "你好，世界");
    }

    #[test]
    fn polish_splits_long_sentence() {
        let long = "这是一个非常长的句子它包含很多信息并且描述了产品的诸多功能而且列举了使用场景最终给出建议";
        let out = polish_zh(long);
        assert!(out.contains('。'), "长句应被拆分: {out}");
    }

    #[test]
    fn polish_keeps_english_intact() {
        let out = polish_zh("Use Chrome, Edge or Firefox.");
        assert!(out.contains("Chrome"), "{out}");
        assert!(out.contains('.'), "英文句末句点应保留: {out}");
    }
}
