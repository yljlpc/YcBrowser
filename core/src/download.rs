//! 多连接分片下载引擎的**算法内核**（零第三方依赖）。
//!
//! 来源与移植说明：
//! 本模块移植自开源项目 SwiftDL（MIT，https://github.com/harshsinghsv/swiftdl）
//! 的 `crates/engine`，取其算法内核，去掉 reqwest/tokio/serde 等依赖：
//! - 原项目用 tokio 异步 + reqwest 发 HTTP；本项目的核心必须零依赖可编译
//!   （见 docs/03），因此**网络 I/O 留在 Python 前端**（标准库 urllib）。
//! - 可确定、可测试的算法部分——分片规划、动态再平衡、令牌桶限速、
//!   断点状态管理、文件探测与命名规则——移植到此处，供前端调用。
//!
//! 算法要点（与原项目一致）：
//! 1. **初始分片**：把文件均分成 N 段，每段一个连接。
//! 2. **动态再平衡**：某连接干完后，从"剩余最多"的段抢走后半段，
//!    保证末尾不会有连接闲着（这是多连接下载器速度的关键）。
//! 3. **令牌桶限速**：允许欠账（负余额即欠费），等待时间在锁外计算。
//! 4. **断点续传**：记录仍缺失的字节区间，崩溃/断网最多损失最后一秒进度。

use std::time::{Duration, Instant};

/// 低于此值的半段不再拆分：新连接的握手成本高于收益。
pub const MIN_SPLIT_HALF: u64 = 512 * 1024;
/// 单个分片的默认连接数上限（与 SwiftDL 一致，最多 32）。
pub const MAX_CONNECTIONS: usize = 32;
/// 默认最小连接数。
pub const MIN_CONNECTIONS: usize = 1;

/// 一个字节区间 `[pos, end)`。
///
/// `pos` 随写入前进；`end` 可以**后退**——当空闲连接抢走本段后半段时。
/// 二者同处一个状态单元，保证"写入"与"被抢"不会对同一字节产生分歧。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Segment {
    /// 本段起点（用于展示单连接进度）。
    pub start: u64,
    /// 当前写入位置。
    pub pos: u64,
    /// 本段拥有的结束位置。
    pub end: u64,
}

impl Segment {
    pub fn new(pos: u64, end: u64) -> Self {
        Self { start: pos, pos, end }
    }

    /// 剩余字节数。
    pub fn remaining(&self) -> u64 {
        self.end.saturating_sub(self.pos)
    }

    /// 抢走后半段：返回新段，若剩余太少则返回 None。
    ///
    /// 与 SwiftDL 的 `Segment::split` 等价：原段收缩到 `mid`，新段接手 `[mid, end)`。
    pub fn split(&mut self, min_half: u64) -> Option<Segment> {
        let remaining = self.remaining();
        if remaining < min_half.saturating_mul(2) {
            return None;
        }
        let mid = self.pos + remaining / 2;
        let old_end = self.end;
        self.end = mid;
        Some(Segment::new(mid, old_end))
    }

    /// 本次写入应占用的字节数（不修改状态）。
    pub fn take_len(&self, len: usize) -> usize {
        let n = (len as u64).min(self.remaining()) as usize;
        n
    }

    /// 提交写入进度，返回是否还有剩余。
    pub fn commit(&mut self, n: usize) -> bool {
        self.pos += n as u64;
        self.pos < self.end
    }
}

/// 把 `[0, size)` 均分成 `n` 段。
pub fn initial_segments(size: u64, n: usize) -> Vec<(u64, u64)> {
    let n = n.clamp(MIN_CONNECTIONS, MAX_CONNECTIONS) as u64;
    let n = n.min(size.max(1));
    if n == 0 {
        return Vec::new();
    }
    let chunk = size / n;
    (0..n)
        .map(|i| {
            let start = i * chunk;
            let end = if i + 1 == n { size } else { start + chunk };
            (start, end)
        })
        .collect()
}

/// 分片表：管理所有分片并负责"派活"。
///
/// 与 SwiftDL 的 `Shared::claim` 语义一致：
/// 1. 优先派发尚未被认领的整段；
/// 2. 整段派完后，从剩余最多的段抢走一半。
pub struct SegmentTable {
    segments: Vec<Segment>,
    /// 下一个待派发的分片下标。
    next: usize,
    min_half: u64,
}

impl SegmentTable {
    /// 由"仍缺失的区间"构造（用于断点续传）。
    pub fn from_ranges(ranges: Vec<(u64, u64)>) -> Self {
        Self {
            segments: ranges.into_iter().map(|(p, e)| Segment::new(p, e)).collect(),
            next: 0,
            min_half: MIN_SPLIT_HALF,
        }
    }

    /// 按总大小与连接数初始化。
    pub fn new(size: u64, connections: usize) -> Self {
        Self::from_ranges(initial_segments(size, connections))
    }

    pub fn len(&self) -> usize {
        self.segments.len()
    }

    pub fn is_empty(&self) -> bool {
        self.segments.is_empty()
    }

    /// 派发一个任务：返回该连接应下载的字节区间。
    pub fn claim(&mut self) -> Option<(u64, u64)> {
        // 1) 派发未认领的整段
        while self.next < self.segments.len() {
            let idx = self.next;
            self.next += 1;
            if self.segments[idx].remaining() > 0 {
                let s = &self.segments[idx];
                return Some((s.pos, s.end));
            }
        }
        // 2) 抢走剩余最多的段的后半段
        let victim = self
            .segments
            .iter()
            .enumerate()
            .max_by_key(|(_, s)| s.remaining())
            .map(|(i, _)| i)?;
        let stolen = {
            let s = &mut self.segments[victim];
            s.split(self.min_half)?
        };
        self.segments.push(stolen.clone());
        self.next = self.segments.len();
        Some((stolen.pos, stolen.end))
    }

    /// 提交某段的写入进度。
    ///
    /// `seg_start` 为该段的原始起点（claim 时给出）。
    pub fn commit(&mut self, seg_start: u64, pos: u64, end: u64) {
        for s in self.segments.iter_mut() {
            if s.start == seg_start {
                s.pos = pos;
                s.end = end;
                return;
            }
        }
    }

    /// 当前仍缺失的区间（用于保存断点状态）。
    pub fn remaining_ranges(&self) -> Vec<(u64, u64)> {
        self.segments
            .iter()
            .filter(|s| s.pos < s.end)
            .map(|s| (s.pos, s.end))
            .collect()
    }

    /// 剩余总字节。
    pub fn remaining_bytes(&self) -> u64 {
        self.segments.iter().map(|s| s.remaining()).sum()
    }

    /// 已下载字节（相对给定总大小）。
    pub fn downloaded(&self, total: u64) -> u64 {
        total.saturating_sub(self.remaining_bytes())
    }

    /// 每连接的 (起点, 当前位置, 终点)，按起点排序，供 UI 画连接图。
    pub fn spans(&self) -> Vec<(u64, u64, u64)> {
        let mut v: Vec<(u64, u64, u64)> = self
            .segments
            .iter()
            .map(|s| (s.start, s.pos, s.end))
            .collect();
        v.sort_by_key(|s| s.0);
        v
    }
}

/// 全局限速器：令牌桶，**允许欠账**（余额可为负）。
///
/// 调用者取走刚收到的字节数并"睡掉"欠账。
/// 这样热路径只持有一小段锁，且对任意并发连接数都成立。
///
/// 与 SwiftDL 的 `SpeedLimiter` 语义一致，但改为同步计算（返回需等待的时长），
/// 由调用方（Python 前端）自行 sleep。
pub struct SpeedLimiter {
    rate: u64,
    bucket: f64,
    last: Instant,
}

impl SpeedLimiter {
    /// `bytes_per_sec` 为 0 表示不限速。
    pub fn new(bytes_per_sec: u64) -> Self {
        Self { rate: bytes_per_sec, bucket: 0.0, last: Instant::now() }
    }

    pub fn set_rate(&mut self, bytes_per_sec: u64) {
        self.rate = bytes_per_sec;
    }

    pub fn rate(&self) -> u64 {
        self.rate
    }

    /// 记账消费 `bytes`，返回需要等待的时长（零表示无需等待）。
    pub fn take(&mut self, bytes: usize) -> Duration {
        if self.rate == 0 {
            return Duration::ZERO;
        }
        let now = Instant::now();
        let refill = now.duration_since(self.last).as_secs_f64() * self.rate as f64;
        // 最多允许一秒的突发量。
        self.bucket = (self.bucket + refill).min(self.rate as f64) - bytes as f64;
        self.last = now;
        if self.bucket < 0.0 {
            Duration::from_secs_f64((-self.bucket) / self.rate as f64)
        } else {
            Duration::ZERO
        }
    }
}

/// 远程文件探测结果。
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct RemoteFile {
    /// 跟随重定向后的地址，分片请求直接打这里。
    pub url: String,
    /// 总大小；未知时为 None。
    pub size: Option<u64>,
    /// 服务器支持 Range 请求（可分片、可续传）。
    pub resumable: bool,
    /// 建议的文件名。
    pub filename: String,
    pub etag: Option<String>,
    pub last_modified: Option<String>,
}

/// 从 `Content-Disposition` 解析文件名。
///
/// 同时支持 `filename*=UTF-8''na%20me.zip`（RFC 6266/5987）与
/// `filename="name.zip"`，优先使用编码形式。
pub fn filename_from_disposition(value: &str) -> Option<String> {
    let params: Vec<&str> = value.split(';').map(str::trim).collect();
    for p in &params {
        let lower = p.to_ascii_lowercase();
        if lower.starts_with("filename*=") {
            let raw = &p["filename*=".len()..];
            let encoded = raw.splitn(3, '\'').nth(2).unwrap_or(raw);
            return Some(percent_decode(encoded.trim_matches('"')));
        }
    }
    for p in &params {
        let lower = p.to_ascii_lowercase();
        if lower.starts_with("filename=") {
            return Some(p["filename=".len()..].trim_matches('"').to_string());
        }
    }
    None
}

/// 从 URL 路径末段推导文件名。
///
/// 只看路径部分（去掉查询串与片段），且末段不能是主机名，
/// 否则 `https://example.com/` 会被误判成文件 "example.com"。
pub fn filename_from_url(url: &str) -> Option<String> {
    let path = url.split('?').next().unwrap_or(url);
    let path = path.split('#').next().unwrap_or(path);
    // 去掉 scheme://host 前缀
    let after_host = match path.find("://") {
        Some(i) => {
            let rest = &path[i + 3..];
            match rest.find('/') {
                Some(j) => &rest[j..],
                None => return None, // 没有路径部分
            }
        }
        None => path,
    };
    let last = after_host.rsplit('/').find(|s| !s.is_empty())?;
    if last.is_empty() {
        return None;
    }
    Some(percent_decode(last))
}

/// 去掉 Windows 禁止的字符与路径部分。
pub fn sanitize_filename(name: &str) -> String {
    let base = name.rsplit(['/', '\\']).next().unwrap_or(name);
    base.chars()
        .map(|c| if "<>:\"|?*".contains(c) || c.is_control() { '_' } else { c })
        .collect::<String>()
        .trim()
        .trim_end_matches('.')
        .to_string()
}

/// 百分号解码（仅处理 %XX，不依赖外部 crate）。
pub fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let hex = &s[i + 1..i + 3];
            if let Ok(v) = u8::from_str_radix(hex, 16) {
                out.push(v);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// 解析 `Content-Range: bytes 0-0/12345`，返回 (总大小, 支持范围)。
///
/// 状态码 206 且能解析出总大小 → 服务器支持 Range。
pub fn parse_content_range(value: &str) -> Option<(u64, bool)> {
    let v = value.trim();
    let rest = v.strip_prefix("bytes ").unwrap_or(v);
    let (_, total) = rest.split_once('/')?;
    let total = total.trim();
    if total == "*" {
        return Some((0, true));
    }
    let total: u64 = total.parse().ok()?;
    Some((total, true))
}

/// 从 `Content-Range` 判断是否支持分片（206 + 有总长度）。
pub fn supports_range(status: u16, content_range: Option<&str>, content_length: Option<u64>) -> (Option<u64>, bool) {
    if status == 206 {
        if let Some(cr) = content_range {
            if let Some((total, _)) = parse_content_range(cr) {
                if total > 0 {
                    return (Some(total), true);
                }
            }
        }
        // 206 但总长未知：可分片但不知道总大小
        return (content_length, true);
    }
    // 200：服务器忽略了 Range，只能单流下载
    (content_length, false)
}

/// 目标路径去重：同名时追加 " (1)"、" (2)"，绝不覆盖已有文件。
///
/// `exists` 由调用方注入（核心不碰文件系统，便于测试）。
/// 比对按**文件名**进行——调用方通常给的是目录内的文件名清单，
/// 而返回的是带目录的完整路径。
pub fn resolve_dest<F>(dir: &str, filename: &str, mut exists: F) -> String
where
    F: FnMut(&str) -> bool,
{
    let dir = dir.trim_end_matches('/');
    let path = format!("{dir}/{filename}");
    if !exists(filename) {
        return path;
    }
    let (stem, ext) = match filename.rfind('.') {
        Some(i) if i > 0 => (&filename[..i], &filename[i..]),
        _ => (filename, ""),
    };
    for i in 1..10_000 {
        let name = format!("{stem} ({i}){ext}");
        if !exists(&name) {
            return format!("{dir}/{name}");
        }
    }
    path
}

/// Google Drive 分享链接 → 直接文件地址。
///
/// Drive 的普通分享链接返回的是"病毒扫描中"网页，而非文件本身。
pub fn drive_direct_url(url: &str) -> String {
    if !url.contains("drive.google.com") {
        return url.to_string();
    }
    let id = url
        .split('?')
        .filter(|part| part.contains('='))
        .find_map(|part| part.split('&').find_map(|kv| kv.strip_prefix("id=")))
        .map(|v| v.to_string())
        .or_else(|| {
            // /file/d/<id>/view
            let path = url.split('?').next().unwrap_or(url);
            let segs: Vec<&str> = path.split('/').collect();
            segs.windows(3)
                .find(|w| w[0] == "file" && w[1] == "d")
                .map(|w| w[2].to_string())
        });
    match id {
        Some(id)
            if !id.is_empty()
                && id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_') =>
        {
            format!("https://drive.usercontent.google.com/download?id={id}&export=download&confirm=t")
        }
        _ => url.to_string(),
    }
}

/// 按扩展名归类下载文件（SwiftDL 的分类目录策略）。
pub fn classify_file(filename: &str) -> &'static str {
    let lower = filename.to_ascii_lowercase();
    let ext = lower.rsplit('.').next().unwrap_or("");
    match ext {
        "mp4" | "mkv" | "avi" | "mov" | "webm" | "flv" | "wmv" | "m4v" | "mpg" | "mpeg" | "rmvb" => "视频",
        "mp3" | "flac" | "wav" | "aac" | "ogg" | "m4a" | "wma" | "ape" => "音乐",
        "exe" | "msi" | "deb" | "rpm" | "apk" | "dmg" | "pkg" | "appimage" | "run" | "sh" => "程序",
        "zip" | "rar" | "7z" | "tar" | "gz" | "bz2" | "xz" | "zst" | "iso" => "压缩包",
        "pdf" | "doc" | "docx" | "xls" | "xlsx" | "ppt" | "pptx" | "txt" | "md" | "epub" => "文档",
        _ => "其他",
    }
}

/// 断点状态：记录仍缺失的字节区间。
///
/// 序列化用手写 JSON（与项目 json.rs 风格一致，避免引入 serde）。
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct SavedState {
    pub url: String,
    pub size: u64,
    pub etag: Option<String>,
    pub last_modified: Option<String>,
    /// 仍缺失的 `[pos, end)` 区间。
    pub segments: Vec<(u64, u64)>,
}

impl SavedState {
    /// 是否描述同一个远程文件版本（URL/大小/校验器一致）。
    pub fn matches(
        &self,
        url: &str,
        size: u64,
        etag: &Option<String>,
        last_modified: &Option<String>,
    ) -> bool {
        self.url == url
            && self.size == size
            && (self.etag.is_none() || etag.is_none() || &self.etag == etag)
            && (self.last_modified.is_none()
                || last_modified.is_none()
                || &self.last_modified == last_modified)
    }

    /// 序列化为 JSON 文本（供前端写入 `.omnidl` 断点文件）。
    pub fn to_json(&self) -> String {
        let segs: Vec<String> = self
            .segments
            .iter()
            .map(|(p, e)| format!("[{p},{e}]"))
            .collect();
        format!(
            "{{\"url\":{},\"size\":{},\"etag\":{},\"last_modified\":{},\"segments\":[{}]}}",
            json_str(&self.url),
            self.size,
            self.etag.as_deref().map(json_str).unwrap_or_else(|| "null".into()),
            self.last_modified.as_deref().map(json_str).unwrap_or_else(|| "null".into()),
            segs.join(",")
        )
    }

    /// 从 JSON 文本解析（容错：解析失败返回 None）。
    pub fn from_json(text: &str) -> Option<SavedState> {
        let url = json_field_str(text, "url")?;
        let size = json_field_num(text, "size").unwrap_or(0.0) as u64;
        let etag = json_field_str(text, "etag");
        let last_modified = json_field_str(text, "last_modified");
        let mut segments = Vec::new();
        if let Some(arr) = json_field_array(text, "segments") {
            // arr 形如 "[40,100],[0,40]"：去掉首尾方括号后按 "],[" 切分。
            let inner = arr.trim_matches(|c| c == '[' || c == ']');
            for piece in inner.split("],[") {
                let nums: Vec<&str> = piece
                    .split(',')
                    .map(|s| s.trim())
                    .filter(|s| !s.is_empty())
                    .collect();
                if nums.len() == 2 {
                    if let (Ok(p), Ok(e)) = (nums[0].parse::<u64>(), nums[1].parse::<u64>()) {
                        segments.push((p, e));
                    }
                }
            }
        }
        Some(SavedState { url, size, etag, last_modified, segments })
    }
}

fn json_str(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for ch in s.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// 取出 `"key":"value"` 形式的字符串字段。
fn json_field_str(text: &str, key: &str) -> Option<String> {
    let pat = format!("\"{key}\":");
    let idx = text.find(&pat)? + pat.len();
    let rest = text[idx..].trim_start();
    if !rest.starts_with('"') {
        return None;
    }
    let rest = &rest[1..];
    let mut out = String::new();
    let mut chars = rest.chars();
    while let Some(c) = chars.next() {
        match c {
            '"' => return Some(out),
            '\\' => match chars.next() {
                Some('n') => out.push('\n'),
                Some('r') => out.push('\r'),
                Some('t') => out.push('\t'),
                Some('"') => out.push('"'),
                Some('\\') => out.push('\\'),
                Some('u') => {
                    let hex: String = chars.by_ref().take(4).collect();
                    if let Ok(v) = u32::from_str_radix(&hex, 16) {
                        out.push(char::from_u32(v).unwrap_or('\u{fffd}'));
                    }
                }
                Some(other) => out.push(other),
                None => break,
            },
            c => out.push(c),
        }
    }
    None
}

/// 取出 `"key":123` 形式的数字字段。
fn json_field_num(text: &str, key: &str) -> Option<f64> {
    let pat = format!("\"{key}\":");
    let idx = text.find(&pat)? + pat.len();
    let rest = text[idx..].trim_start();
    let num: String = rest.chars().take_while(|c| c.is_ascii_digit() || *c == '.' || *c == '-').collect();
    num.parse::<f64>().ok()
}

/// 取出 `"key":[...]` 形式的数组字段**内部内容**（不含最外层方括号）。
fn json_field_array(text: &str, key: &str) -> Option<String> {
    let pat = format!("\"{key}\":");
    let idx = text.find(&pat)? + pat.len();
    let rest = text[idx..].trim_start();
    if !rest.starts_with('[') {
        return None;
    }
    let bytes = rest.as_bytes();
    let mut depth = 0i32;
    for (i, b) in bytes.iter().enumerate() {
        match b {
            b'[' => depth += 1,
            b']' => {
                depth -= 1;
                if depth == 0 {
                    return Some(rest[1..i].to_string());
                }
            }
            _ => {}
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn initial_split_covers_file() {
        let segs = initial_segments(1003, 4);
        assert_eq!(segs.first().unwrap().0, 0);
        assert_eq!(segs.last().unwrap().1, 1003);
        for w in segs.windows(2) {
            assert_eq!(w[0].1, w[1].0);
        }
        assert_eq!(initial_segments(3, 8).len(), 3);
    }

    #[test]
    fn connections_capped_at_32() {
        assert_eq!(initial_segments(1000, 100).len(), 32);
        assert_eq!(initial_segments(1000, 0).len(), 1);
    }

    #[test]
    fn split_halves_remaining() {
        let mut s = Segment::new(100, 300);
        let tail = s.split(10).unwrap();
        assert_eq!((s.pos, s.end), (100, 200));
        assert_eq!((tail.pos, tail.end), (200, 300));
        let mut small = Segment::new(0, 15);
        assert!(small.split(10).is_none());
    }

    #[test]
    fn table_claims_then_steals() {
        // 用大文件测试再平衡：小文件不拆分是既定策略（握手成本高于收益）。
        let size = 10 * 1024 * 1024u64;
        let mut t = SegmentTable::new(size, 2);
        let a = t.claim().unwrap();
        let b = t.claim().unwrap();
        assert_eq!(a, (0, size / 2));
        assert_eq!(b, (size / 2, size));
        // 全部派完后应从剩余最多的段抢一半
        let c = t.claim().expect("大文件应可再平衡");
        assert!(c.0 < c.1);
        let total: u64 = t.remaining_ranges().iter().map(|(p, e)| e - p).sum();
        assert!(total > 0 && total <= size);
    }

    #[test]
    fn small_segments_are_not_split() {
        // 低于 2*MIN_SPLIT_HALF 的剩余量不再拆分（与 SwiftDL 一致）。
        let mut t = SegmentTable::new(1000, 2);
        assert!(t.claim().is_some());
        assert!(t.claim().is_some());
        assert!(t.claim().is_none(), "小文件不应再平衡");
    }

    #[test]
    fn table_remaining_and_downloaded() {
        let mut t = SegmentTable::new(1000, 4);
        let _ = t.claim();
        t.commit(0, 250, 250);
        assert_eq!(t.downloaded(1000), 250);
        assert_eq!(t.remaining_bytes(), 750);
    }

    #[test]
    fn limiter_limits_rate() {
        let mut l = SpeedLimiter::new(1000);
        let w = l.take(2000);
        assert!(w > Duration::ZERO, "超量应产生等待");
        let mut un = SpeedLimiter::new(0);
        assert_eq!(un.take(999999), Duration::ZERO);
    }

    #[test]
    fn parses_disposition() {
        assert_eq!(
            filename_from_disposition(r#"attachment; filename="a b.zip""#).as_deref(),
            Some("a b.zip")
        );
        assert_eq!(
            filename_from_disposition(
                "attachment; filename=x.bin; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf"
            )
            .as_deref(),
            Some("résumé.pdf")
        );
        assert_eq!(filename_from_disposition("inline"), None);
    }

    #[test]
    fn sanitizes_filenames() {
        assert_eq!(sanitize_filename("../evil/na:me?.txt"), "na_me_.txt");
        assert_eq!(sanitize_filename("trailing..."), "trailing");
    }

    #[test]
    fn filename_from_url_ignores_query() {
        assert_eq!(filename_from_url("https://x/a/b/file.zip?x=1").as_deref(), Some("file.zip"));
        assert_eq!(filename_from_url("https://x/").as_deref(), None);
    }

    #[test]
    fn content_range_parsing() {
        assert_eq!(parse_content_range("bytes 0-0/12345"), Some((12345, true)));
        assert_eq!(parse_content_range("bytes */500"), Some((500, true)));
        assert_eq!(parse_content_range("garbage"), None);
    }

    #[test]
    fn range_support_detection() {
        let (size, resumable) = supports_range(206, Some("bytes 0-0/1000"), None);
        assert_eq!(size, Some(1000));
        assert!(resumable);
        let (size, resumable) = supports_range(200, None, Some(1000));
        assert_eq!(size, Some(1000));
        assert!(!resumable, "200 表示服务器忽略 Range，不能分片");
    }

    #[test]
    fn resolve_dest_avoids_overwrite() {
        let mut taken = vec!["a.zip".to_string()];
        let p = resolve_dest("/d", "a.zip", |x| taken.iter().any(|t| t == x));
        assert_eq!(p, "/d/a (1).zip");
        taken.push("a (1).zip".into());
        let p2 = resolve_dest("/d", "a.zip", |x| taken.iter().any(|t| t == x));
        assert_eq!(p2, "/d/a (2).zip");
        let p3 = resolve_dest("/d", "b.zip", |_| false);
        assert_eq!(p3, "/d/b.zip");
    }

    #[test]
    fn drive_links_go_to_the_file() {
        let want = "https://drive.usercontent.google.com/download?id=AbC_1-x&export=download&confirm=t";
        assert_eq!(drive_direct_url("https://drive.google.com/uc?id=AbC_1-x&export=download"), want);
        assert_eq!(drive_direct_url("https://drive.google.com/file/d/AbC_1-x/view?usp=sharing"), want);
        assert_eq!(drive_direct_url("https://example.com/uc?id=AbC_1-x"), "https://example.com/uc?id=AbC_1-x");
    }

    #[test]
    fn classifies_by_extension() {
        assert_eq!(classify_file("a.mp4"), "视频");
        assert_eq!(classify_file("a.MP3"), "音乐");
        assert_eq!(classify_file("a.deb"), "程序");
        assert_eq!(classify_file("a.zip"), "压缩包");
        assert_eq!(classify_file("a.pdf"), "文档");
        assert_eq!(classify_file("a.xyz"), "其他");
    }

    #[test]
    fn saved_state_roundtrip() {
        let s = SavedState {
            url: "https://x/f?token=old".into(),
            size: 100,
            etag: Some("e".into()),
            last_modified: None,
            segments: vec![(40, 100), (0, 40)],
        };
        let text = s.to_json();
        let back = SavedState::from_json(&text).unwrap();
        assert_eq!(back, s);
        assert!(back.matches("https://x/f?token=old", 100, &Some("e".into()), &None));
        assert!(!back.matches("https://x/f?token=new", 100, &Some("e".into()), &None));
        assert!(!back.matches("https://x/f?token=old", 101, &Some("e".into()), &None));
    }

    #[test]
    fn percent_decode_basic() {
        assert_eq!(percent_decode("a%20b"), "a b");
        assert_eq!(percent_decode("%E4%B8%AD"), "中");
        assert_eq!(percent_decode("100%"), "100%");
    }
}
