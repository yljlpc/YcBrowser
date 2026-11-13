//! 与 Shell（PyQt6 前端）之间的行式 JSON-RPC 协议。
//!
//! 每一行是一个独立请求；进程存活期间保持 stdin/stdout 长连接，
//! 避免每次调用都 fork 进程。这与语言服务器（LSP）的 stdio 传输同构。

use crate::engine::{Backend, DocMode, EngineSpec};
use crate::download::{
    classify_file, drive_direct_url, filename_from_disposition, filename_from_url,
    initial_segments, sanitize_filename, SavedState, SegmentTable, MAX_CONNECTIONS,
    MIN_CONNECTIONS,
};
use crate::json::{parse, Json};
use crate::nav::{resolve, NavIntent, SearchEngine};
use crate::translate::{
    apply_glossary, detect_lang, polish_zh, should_translate, split_sentences, Lang,
};
use std::io::{BufRead, Write};

/// 处理单行请求，返回应答 JSON 字符串。
pub fn handle_line(line: &str) -> String {
    let req = match parse(line) {
        Ok(v) => v,
        Err(e) => return err(&format!("parse error: {e}")),
    };
    let cmd = match req.get("cmd").and_then(|v| v.as_str()) {
        Some(c) => c,
        None => return err("missing 'cmd'"),
    };
    match cmd {
        "ping" => ok_json(&[("pong", Json::Bool(true))]),
        "resolve_nav" => cmd_resolve_nav(&req),
        "engine_spec" => cmd_engine_spec(&req),
        "negotiate_docmode" => cmd_negotiate(&req),
        "translate_detect_lang" => cmd_detect_lang(&req),
        "translate_should" => cmd_translate_should(&req),
        "translate_split" => cmd_translate_split(&req),
        "translate_polish" => cmd_translate_polish(&req),
        "dl_plan" => cmd_dl_plan(&req),
        "dl_claim" => cmd_dl_claim(&req),
        "dl_commit" => cmd_dl_commit(&req),
        "dl_filename" => cmd_dl_filename(&req),
        "dl_resolve_dest" => cmd_dl_resolve_dest(&req),
        "dl_state" => cmd_dl_state(&req),
        other => err(&format!("unknown cmd: {other}")),
    }
}

/// 生成下载分片计划：给定总大小与连接数，返回初始区间列表。
fn cmd_dl_plan(req: &Json) -> String {
    let size = req.get("size").and_then(|v| v.as_int()).unwrap_or(0) as u64;
    let conns = req
        .get("connections")
        .and_then(|v| v.as_int())
        .unwrap_or(MIN_CONNECTIONS as i64)
        .clamp(MIN_CONNECTIONS as i64, MAX_CONNECTIONS as i64) as usize;
    let segs = initial_segments(size, conns);
    let arr = Json::Arr(
        segs.iter()
            .map(|(p, e)| Json::Arr(vec![Json::Int(*p as i64), Json::Int(*e as i64)]))
            .collect(),
    );
    ok_json(&[
        ("segments", arr),
        ("connections", Json::Int(conns as i64)),
        ("min_split_half", Json::Int(512 * 1024)),
    ])
}

/// 从分片表派发一个下载任务。
///
/// 前端把上一步返回的 segments 传回，核心据此派活；
/// 派完整段后，核心会从"剩余最多"的段抢走后半段（动态再平衡）。
fn cmd_dl_claim(req: &Json) -> String {
    let ranges = read_ranges(req.get("segments"));
    let mut table = SegmentTable::from_ranges(ranges);
    match table.claim() {
        Some((start, end)) => ok_json(&[
            ("start", Json::Int(start as i64)),
            ("end", Json::Int(end as i64)),
            ("segments", ranges_json(&table)),
        ]),
        None => ok_json(&[("start", Json::Int(-1)), ("end", Json::Int(-1)), ("segments", Json::Arr(vec![]))]),
    }
}

/// 提交写入进度，返回更新后的剩余区间与已下载字节。
fn cmd_dl_commit(req: &Json) -> String {
    let ranges = read_ranges(req.get("segments"));
    let total = req.get("total").and_then(|v| v.as_int()).unwrap_or(0) as u64;
    let start = req.get("start").and_then(|v| v.as_int()).unwrap_or(-1);
    let pos = req.get("pos").and_then(|v| v.as_int()).unwrap_or(0) as u64;
    let end = req.get("end").and_then(|v| v.as_int()).unwrap_or(0) as u64;
    let mut table = SegmentTable::from_ranges(ranges);
    if start >= 0 {
        table.commit(start as u64, pos, end);
    }
    ok_json(&[
        ("segments", ranges_json(&table)),
        ("remaining", Json::Int(table.remaining_bytes() as i64)),
        ("downloaded", Json::Int(table.downloaded(total) as i64)),
    ])
}

/// 解析文件名：Content-Disposition > URL 末段 > 兜底名；并做净化与分类。
fn cmd_dl_filename(req: &Json) -> String {
    let url = req.get("url").and_then(|v| v.as_str()).unwrap_or("");
    let disposition = req.get("content_disposition").and_then(|v| v.as_str());
    let raw = disposition
        .and_then(filename_from_disposition)
        .or_else(|| filename_from_url(url))
        .unwrap_or_else(|| "download.bin".to_string());
    let clean = sanitize_filename(&raw);
    let name = if clean.is_empty() { "download.bin".to_string() } else { clean };
    ok_json(&[
        ("filename", Json::Str(name.clone())),
        ("category", Json::Str(classify_file(&name).to_string())),
        ("direct_url", Json::Str(drive_direct_url(url))),
    ])
}

/// 目标文件名去重：同名时追加 " (1)"、" (2)"。
///
/// `existing` 传入已占用文件名列表（由前端扫描目录得到）。
fn cmd_dl_resolve_dest(req: &Json) -> String {
    let dir = req.get("dir").and_then(|v| v.as_str()).unwrap_or("");
    let filename = req.get("filename").and_then(|v| v.as_str()).unwrap_or("download.bin");
    let existing: Vec<String> = match req.get("existing") {
        Some(Json::Arr(items)) => items.iter().filter_map(|v| v.as_str().map(String::from)).collect(),
        _ => Vec::new(),
    };
    let resolved = crate::download::resolve_dest(dir, filename, |c| existing.iter().any(|e| e == c));
    ok_json(&[("path", Json::Str(resolved))])
}

/// 断点状态：序列化 / 反序列化。
fn cmd_dl_state(req: &Json) -> String {
    let action = req.get("action").and_then(|v| v.as_str()).unwrap_or("save");
    match action {
        "load" => {
            let text = req.get("text").and_then(|v| v.as_str()).unwrap_or("");
            match SavedState::from_json(text) {
                Some(s) => {
                    let segs = Json::Arr(
                        s.segments
                            .iter()
                            .map(|(p, e)| Json::Arr(vec![Json::Int(*p as i64), Json::Int(*e as i64)]))
                            .collect(),
                    );
                    ok_json(&[
                        ("valid", Json::Bool(true)),
                        ("url", Json::Str(s.url)),
                        ("size", Json::Int(s.size as i64)),
                        ("etag", s.etag.map(Json::Str).unwrap_or(Json::Null)),
                        ("last_modified", s.last_modified.map(Json::Str).unwrap_or(Json::Null)),
                        ("segments", segs),
                    ])
                }
                None => ok_json(&[("valid", Json::Bool(false))]),
            }
        }
        _ => {
            let url = req.get("url").and_then(|v| v.as_str()).unwrap_or("");
            let size = req.get("size").and_then(|v| v.as_int()).unwrap_or(0) as u64;
            let etag = req.get("etag").and_then(|v| v.as_str()).map(String::from);
            let last_modified = req.get("last_modified").and_then(|v| v.as_str()).map(String::from);
            let ranges = read_ranges(req.get("segments"));
            let state = SavedState { url: url.to_string(), size, etag, last_modified, segments: ranges };
            ok_json(&[("json", Json::Str(state.to_json()))])
        }
    }
}

/// 读取 `[[p,e],...]` 形式的区间数组。
fn read_ranges(v: Option<&Json>) -> Vec<(u64, u64)> {
    let mut out = Vec::new();
    if let Some(Json::Arr(items)) = v {
        for item in items {
            if let Json::Arr(pair) = item {
                if pair.len() == 2 {
                    let p = pair[0].as_int().unwrap_or(0).max(0) as u64;
                    let e = pair[1].as_int().unwrap_or(0).max(0) as u64;
                    if e > p {
                        out.push((p, e));
                    }
                }
            }
        }
    }
    out
}

fn ranges_json(table: &SegmentTable) -> Json {
    Json::Arr(
        table
            .remaining_ranges()
            .iter()
            .map(|(p, e)| Json::Arr(vec![Json::Int(*p as i64), Json::Int(*e as i64)]))
            .collect(),
    )
}

/// 语言检测。
fn cmd_detect_lang(req: &Json) -> String {
    let text = req.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let lang = detect_lang(text);
    ok_json(&[("lang", Json::Str(lang.name().to_string()))])
}

/// 是否需要翻译（滤代码/URL/已是目标语言）。
fn cmd_translate_should(req: &Json) -> String {
    let text = req.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let target = match req.get("target").and_then(|v| v.as_str()) {
        Some("en") => Lang::En,
        _ => Lang::Zh,
    };
    ok_json(&[("should", Json::Bool(should_translate(text, target)))])
}

/// 分句（供前端批量送译）。
fn cmd_translate_split(req: &Json) -> String {
    let text = req.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let parts = split_sentences(text);
    let arr = Json::Arr(parts.into_iter().map(Json::Str).collect());
    ok_json(&[("sentences", arr)])
}

/// 中文润色：术语统一 + 直译腔修正。
///
/// 术语表以「原词,译词」逗号分隔传入，避免引入嵌套 JSON 解析复杂度。
fn cmd_translate_polish(req: &Json) -> String {
    let text = req.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let glossary_spec = req.get("glossary").and_then(|v| v.as_str()).unwrap_or("");
    let mut glossary: Vec<(String, String)> = Vec::new();
    for item in glossary_spec.split('\n') {
        let item = item.trim();
        if item.is_empty() {
            continue;
        }
        if let Some((from, to)) = item.split_once(',') {
            let from = from.trim();
            let to = to.trim();
            if !from.is_empty() && !to.is_empty() {
                glossary.push((from.to_string(), to.to_string()));
            }
        }
    }
    let unified = apply_glossary(text, &glossary);
    let polished = polish_zh(&unified);
    ok_json(&[
        ("text", Json::Str(polished.clone())),
        ("changed", Json::Bool(polished != text)),
    ])
}

fn cmd_resolve_nav(req: &Json) -> String {
    let input = req.get("input").and_then(|v| v.as_str()).unwrap_or("");
    let engine = match req.get("engine").and_then(|v| v.as_str()) {
        Some(s) => SearchEngine::parse(s),
        None => SearchEngine::Bing,
    };
    let intent = resolve(input, engine);
    let (kind, url) = match &intent {
        NavIntent::Url(u) => ("url", u.clone()),
        NavIntent::Search(u) => ("search", u.clone()),
        NavIntent::Internal(p) => ("internal", p.clone()),
    };
    ok_json(&[
        ("kind", Json::Str(kind.to_string())),
        ("url", Json::Str(url)),
    ])
}

fn cmd_engine_spec(req: &Json) -> String {
    let backend = req
        .get("backend")
        .and_then(|v| v.as_str())
        .and_then(Backend::parse)
        .unwrap_or(Backend::Blink);
    let mut spec = EngineSpec::for_backend(backend);
    if let Some(dm) = req.get("doc_mode").and_then(|v| v.as_str()).and_then(DocMode::from_cmd) {
        spec.doc_mode = dm;
    }
    ok_json(&[
        ("backend", Json::Str(spec.backend.name().to_string())),
        ("doc_mode", Json::Str(spec.doc_mode.label().to_string())),
        ("ua", Json::Str(spec.effective_ua())),
        ("cloak_ua", Json::Bool(spec.cloak_ua)),
        ("legacy_shims", Json::Bool(spec.legacy_shims)),
    ])
}

fn cmd_negotiate(req: &Json) -> String {
    let token = req.get("x_ua_compatible").and_then(|v| v.as_str()).unwrap_or("");
    let dm = if let Some(t) = DocMode::from_ua_compatible(token) {
        t
    } else {
        req.get("current")
            .and_then(|v| v.as_str())
            .and_then(DocMode::from_cmd)
            .unwrap_or(DocMode::Ie11)
    };
    ok_json(&[("doc_mode", Json::Str(dm.label().to_string()))])
}

/// 主循环：逐行读取 stdin，写应答到 stdout。
pub fn run() {
    let stdin = std::io::stdin();
    let mut stdout = std::io::stdout();
    let mut reader = stdin.lock();
    let mut buf = String::new();
    loop {
        buf.clear();
        match reader.read_line(&mut buf) {
            Ok(0) => break, // EOF
            Ok(_) => {
                let line = buf.trim();
                if line.is_empty() {
                    continue;
                }
                let resp = handle_line(line);
                let _ = writeln!(stdout, "{resp}");
                let _ = stdout.flush();
            }
            Err(_) => break,
        }
    }
}

fn ok_json(pairs: &[(&str, Json)]) -> String {
    let mut obj = Json::obj().set("ok", Json::Bool(true));
    let mut res = Json::obj();
    for (k, v) in pairs {
        res = res.set(k, v.clone());
    }
    obj = obj.set("result", res);
    obj.dump()
}

fn err(msg: &str) -> String {
    Json::obj()
        .set("ok", Json::Bool(false))
        .set("error", Json::Str(msg.to_string()))
        .dump()
}
