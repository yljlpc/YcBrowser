//! 最小 JSON 值模型与序列化（零依赖实现）。
//!
//! 之所以手写而不是引 serde：本项目要求 core 在任何离线机器上 `cargo build`
//! 都能过，且二进制体积需 < 1MB；同时沙箱禁用 utime 会导致 cargo 解包 registry
//! 失败，零依赖是唯一稳妥的构建路径。见 docs/03-build-and-package.md。

#[derive(Debug, Clone, PartialEq)]
pub enum Json {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    Arr(Vec<Json>),
    Obj(Vec<(String, Json)>),
}

impl Json {
    pub fn obj() -> Json {
        Json::Obj(Vec::new())
    }

    /// 链式插入，保持插入顺序（便于人读的日志与 diff）。
    pub fn set(mut self, k: &str, v: Json) -> Json {
        if let Json::Obj(ref mut m) = self {
            if let Some(slot) = m.iter_mut().find(|(key, _)| key == k) {
                slot.1 = v;
            } else {
                m.push((k.to_string(), v));
            }
        }
        self
    }

    pub fn get(&self, k: &str) -> Option<&Json> {
        match self {
            Json::Obj(m) => m.iter().find(|(key, _)| key == k).map(|(_, v)| v),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Json::Str(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_int(&self) -> Option<i64> {
        match self {
            Json::Int(i) => Some(*i),
            Json::Float(f) => Some(*f as i64),
            _ => None,
        }
    }

    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Json::Bool(b) => Some(*b),
            _ => None,
        }
    }

    pub fn dump(&self) -> String {
        let mut out = String::with_capacity(128);
        self.write(&mut out, 0);
        out
    }

    fn write(&self, out: &mut String, depth: usize) {
        // 深度超过 64 直接截断，避免恶意输入构造的环/深链打爆栈。
        if depth > 64 {
            out.push_str("null");
            return;
        }
        match self {
            Json::Null => out.push_str("null"),
            Json::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
            Json::Int(i) => out.push_str(&i.to_string()),
            Json::Float(f) => {
                if f.is_finite() {
                    out.push_str(&format!("{f}"))
                } else {
                    out.push_str("null")
                }
            }
            Json::Str(s) => escape_into(s, out),
            Json::Arr(items) => {
                out.push('[');
                for (i, item) in items.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    item.write(out, depth + 1);
                }
                out.push(']');
            }
            Json::Obj(fields) => {
                out.push('{');
                for (i, (k, v)) in fields.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    escape_into(k, out);
                    out.push(':');
                    v.write(out, depth + 1);
                }
                out.push('}');
            }
        }
    }
}

fn escape_into(s: &str, out: &mut String) {
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
}

/// 从 `s` 的 `i` 位置开始解析一个 JSON 值。
pub fn parse(s: &str) -> Result<Json, String> {
    let bytes = s.as_bytes();
    let mut i = 0usize;
    let value = parse_at(bytes, &mut i, 0)?;
    skip_ws(bytes, &mut i);
    if i != bytes.len() {
        return Err(format!("trailing data at {i}"));
    }
    Ok(value)
}

fn skip_ws(b: &[u8], i: &mut usize) {
    while *i < b.len() && matches!(b[*i], b' ' | b'\n' | b'\r' | b'\t') {
        *i += 1;
    }
}

fn parse_at(b: &[u8], i: &mut usize, depth: usize) -> Result<Json, String> {
    if depth > 64 {
        return Err("nesting too deep".into());
    }
    skip_ws(b, i);
    if *i >= b.len() {
        return Err("unexpected end".into());
    }
    match b[*i] {
        b'n' => {
            expect(b, i, b"null")?;
            Ok(Json::Null)
        }
        b't' => {
            expect(b, i, b"true")?;
            Ok(Json::Bool(true))
        }
        b'f' => {
            expect(b, i, b"false")?;
            Ok(Json::Bool(false))
        }
        b'"' => Ok(Json::Str(parse_str(b, i)?)),
        b'[' => {
            *i += 1;
            let mut items = Vec::new();
            skip_ws(b, i);
            if *i < b.len() && b[*i] == b']' {
                *i += 1;
                return Ok(Json::Arr(items));
            }
            loop {
                items.push(parse_at(b, i, depth + 1)?);
                skip_ws(b, i);
                match b.get(*i) {
                    Some(b',') => {
                        *i += 1;
                    }
                    Some(b']') => {
                        *i += 1;
                        return Ok(Json::Arr(items));
                    }
                    _ => return Err(format!("bad array at {i}")),
                }
            }
        }
        b'{' => {
            *i += 1;
            let mut fields = Vec::new();
            skip_ws(b, i);
            if *i < b.len() && b[*i] == b'}' {
                *i += 1;
                return Ok(Json::Obj(fields));
            }
            loop {
                skip_ws(b, i);
                let k = parse_str(b, i)?;
                skip_ws(b, i);
                if b.get(*i) != Some(&b':') {
                    return Err(format!("expected ':' at {i}"));
                }
                *i += 1;
                let value = parse_at(b, i, depth + 1)?;
                fields.push((k, value));
                skip_ws(b, i);
                match b.get(*i) {
                    Some(b',') => {
                        *i += 1;
                    }
                    Some(b'}') => {
                        *i += 1;
                        return Ok(Json::Obj(fields));
                    }
                    _ => return Err(format!("bad object at {i}")),
                }
            }
        }
        b'-' | b'0'..=b'9' => parse_num(b, i),
        c => Err(format!("unexpected byte {c} at {i}")),
    }
}

fn expect(b: &[u8], i: &mut usize, lit: &[u8]) -> Result<(), String> {
    if b.len() >= *i + lit.len() && &b[*i..*i + lit.len()] == lit {
        *i += lit.len();
        Ok(())
    } else {
        Err(format!("expected literal at {i}"))
    }
}

fn parse_num(b: &[u8], i: &mut usize) -> Result<Json, String> {
    let start = *i;
    if b.get(*i) == Some(&b'-') {
        *i += 1;
    }
    let mut is_float = false;
    while *i < b.len() {
        match b[*i] {
            b'0'..=b'9' => *i += 1,
            b'.' | b'e' | b'E' | b'+' | b'-' => {
                is_float = true;
                *i += 1;
            }
            _ => break,
        }
    }
    let text = std::str::from_utf8(&b[start..*i]).map_err(|e| e.to_string())?;
    if is_float {
        text.parse::<f64>()
            .map(Json::Float)
            .map_err(|e| format!("bad float {text}: {e}"))
    } else {
        text.parse::<i64>()
            .map(Json::Int)
            .map_err(|e| format!("bad int {text}: {e}"))
    }
}

fn parse_str(b: &[u8], i: &mut usize) -> Result<String, String> {
    if b.get(*i) != Some(&b'"') {
        return Err(format!("expected string at {i}"));
    }
    *i += 1;
    let mut out = String::new();
    while *i < b.len() {
        match b[*i] {
            b'"' => {
                *i += 1;
                return Ok(out);
            }
            b'\\' => {
                *i += 1;
                let esc = *b.get(*i).ok_or("bad escape")?;
                match esc {
                    b'"' => out.push('"'),
                    b'\\' => out.push('\\'),
                    b'/' => out.push('/'),
                    b'b' => out.push('\u{8}'),
                    b'f' => out.push('\u{c}'),
                    b'n' => out.push('\n'),
                    b'r' => out.push('\r'),
                    b't' => out.push('\t'),
                    b'u' => {
                        let hex = b
                            .get(*i + 1..*i + 5)
                            .ok_or("short \\u")?;
                        let cp = u32::from_str_radix(
                            std::str::from_utf8(hex).map_err(|e| e.to_string())?,
                            16,
                        )
                        .map_err(|e| format!("bad \\u: {e}"))?;
                        *i += 4;
                        out.push(char::from_u32(cp).unwrap_or('\u{fffd}'));
                    }
                    c => return Err(format!("bad escape {c}")),
                }
                *i += 1;
            }
            _ => {
                let start = *i;
                while *i < b.len() && b[*i] != b'"' && b[*i] != b'\\' {
                    *i += 1;
                }
                out.push_str(std::str::from_utf8(&b[start..*i]).map_err(|e| e.to_string())?);
            }
        }
    }
    Err("unterminated string".into())
}
