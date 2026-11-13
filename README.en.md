# YcBrowser

[简体中文](README.md) | English

A multi-engine **desktop web browser** built on a **Rust native core** with a
**PyQt6 / Qt 6 WebEngine** shell, featuring live page translation and a
multi-connection download engine.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightblue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Rust](https://img.shields.io/badge/rust-1.70%2B-orange.svg)

---

## Features

### Multi-engine compatibility

| Engine | Notes |
|---|---|
| **Blink** | Default. QtWebEngine 6.10 (Chromium content + V8). |
| **WebKit** | Runs with a WebKit user-agent string. |
| **Trident** | IE compatibility mode: negotiates document mode via `X-UA-Compatible` (including real-world patterns such as `IE=EmulateIE7`), spoofs the IE user agent, and injects legacy DOM shims (`document.all`, `attachEvent`). |

Every tab owns an independent `QWebEngineProfile`, so **engine and user agent
can be isolated per tab**.

### Live translation (English → Chinese)

- Extracts visible page text (skipping scripts, code and input fields) →
  translates sentence by sentence → applies **unified terminology and
  colloquial rewriting** → writes the result back into the DOM.
- One-click "restore original page".
- Backends: **MyMemory** (free, default) / **Google** / **LibreTranslate** /
  custom endpoint (custom endpoints accept `{text}`, `{source}`, `{target}`
  placeholders, or a raw JSON POST body).
- Target language and a custom glossary are configurable in Settings.

> Language processing (detection, sentence splitting, terminology unification,
> Chinese polishing) is implemented in the Rust core, so it is **deterministic
> and unit-testable**.

### High-speed download engine

The algorithm core is ported from [SwiftDL](https://github.com/harshsinghsv/swiftdl) (MIT):

- **Multi-connection chunking** — up to 32 parallel connections per file
  (configurable, default 8).
- **Dynamic rebalancing** — when a connection finishes, it immediately takes
  over the largest remaining segment, avoiding idle time at the tail.
- **No merge step** — the file is pre-divided by total length and each
  connection writes directly at its own offset.
- **Automatic fallback** — falls back to a single thread when the server does
  not support `Range`.
- **Resumable** — a `.omnidl` sidecar records missing byte ranges; after a crash
  or network loss at most about one second of progress is lost.
- **Organized archiving** — files are sorted into *video / music / program /
  archive / document* subfolders by extension.
- **Media sniffing** — "Download page media…" lists playable video and audio
  URLs found on the page.

### Interface

- Multi-tab, separate address bar, history, bookmarks, find-in-page, download
  manager, developer tools.
- **Resolution-aware scaling** — the scale factor is computed from
  `primary screen resolution / 1920x1080` and `devicePixelRatio`, then clamped
  to 0.8–2.2. It updates toolbar icons, label text and per-tab web zoom live.
  Can be disabled or set manually in Settings.
- Incognito windows, printing and PDF export, per-tab context menu.
- Chinese fonts are bundled, so the UI renders consistently everywhere.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│ PyQt6 / Qt 6 front-end (src/)                        │
│  main.py       entry point (registers fonts/theme/core)│
│  window.py     main window: toolbar, address bar,     │
│                engine switch, tabs                    │
│  tab.py        tab: QWebEngineView + private profile  │
│  translate.py  translation client (MyMemory/Google/..)│
│  downloader.py multi-connection download engine       │
│  core_client.py IPC client for the Rust core          │
│                (line-delimited JSON-RPC)              │
└───────────────┬──────────────────────────────────────┘
                │ stdin/stdout (one JSON object per line)
┌───────────────┴──────────────────────────────────────┐
│ Rust native core (core/, zero third-party deps)       │
│  engine.rs    engine dispatch: Blink/WebKit/Trident   │
│  nav.rs       address bar normalisation               │
│  translate.rs language detection, splitting, glossary │
│  download.rs  chunk planning, rebalancing, throttle   │
│  ipc.rs       JSON-RPC service loop                   │
└──────────────────────────────────────────────────────┘
```

---

## Installation

### Windows

Download `YcBrowser-<version>-setup.exe` from
[Releases](https://github.com/yljlpc/YcBrowser/releases), or run `OmniBrowser.exe`
from the portable folder.

> **Fully self-contained.** The installer bundles the complete Qt 6 runtime
> (platform plugins, WebEngine renderer process and resources, ICU data, V8
> snapshots), a Python runtime, the VC++ runtime, Chinese fonts and the Rust
> native core. The target machine needs **no preinstalled software or
> environment**, and nothing is written outside the install directory and the
> user's own data directory.

> **Code signing.** Windows binaries are built and published through GitHub
> Actions. Code signing for this project is handled by the **SignPath
> Foundation** free open-source program, which verifies that a binary was
> built from this public repository and vouches for it. The certificate is
> issued to *SignPath Foundation*, so that is the publisher name users see.
> See [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md) and
> [PRIVACY.md](PRIVACY.md).

### Linux

Download the `.deb` packages from
[Releases](https://github.com/yljlpc/YcBrowser/releases):

```bash
sudo apt install ./omnibrowser_<version>_amd64.deb
```

Two variants are provided:

- **openKylin** — ships the PyQt6 bindings, works fully offline.
- **deepin** — depends on the system `python3-pyqt6`, adapts to its ABI.

---

## Building from source

### Prerequisites

- Rust 1.70+ (builds the native core)
- Python 3.10+
- Linux packaging needs `fakeroot` and `dpkg-deb`; Windows packaging needs
  [NSIS](https://nsis.sourceforge.io/)

### Build the Rust core

```bash
cd core
cargo build --release
# artifact: core/target/release/omnibrowser-core(.exe)
```

### Run (development mode)

```bash
./run.sh                 # Linux, foreground
# Windows:
python -m src.main
```

### Package

```bash
# Linux (openKylin + deepin packages)
bash package/build_debs.sh

# Windows (portable folder + NSIS installer)
python installer/build_windows.py

# Win11-specific installer (DPI awareness, taskbar pinning)
python build_windows_win11.py
```

### Verify the produced bundle

```bash
# Static self-check: Qt path resolution / runtime hook / platform plugin /
# required WebEngine file manifest / dependency closure / bundled resources /
# signature status
python tools/verify_bundle.py dist/OmniBrowser

# Standalone PE dependency audit
python tools/audit_dependencies.py dist/OmniBrowser
```

---

## Tests

```bash
# Rust core unit tests
cd core && cargo test

# Pure-logic validation (does not launch Chromium)
python tools/test_logic.py

# End-to-end download engine test (local HTTP server + real chunked download)
python tools/test_download.py

# Headless per-feature test with real Blink rendering
QT_QPA_PLATFORM=offscreen python tools/test_browser.py
```

---

## Known limitations

1. Pages rendered with `setHtml` show an internal Qt-encoded URL in the
   address bar. This is Qt behaviour and does not affect navigation.
2. Without a GPU, Chromium falls back to software rendering, which limits
   performance on complex pages.
3. Trident mode is *emulation*: legacy sites load with IE semantics, but
   Windows-only capabilities such as ActiveX cannot be provided (a placeholder
   shim is injected so scripts do not crash).
4. Adaptive streaming (HLS `.m3u8` / DASH `.mpd`) requires segment muxing.
   This project does not bundle a muxer and asks the user to use an external
   tool.
5. Translation quality depends on the chosen backend. Terminology unification
   and colloquial rewriting noticeably reduce machine-translation tone, but
   cannot fully replace human editing.

---

## Contributing

- [CONTRIBUTING.md](CONTRIBUTING.md) — how to build, test and submit a pull
  request.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — code of conduct.
- [SECURITY.md](SECURITY.md) — how to report a security issue privately.
- [requirements.txt](requirements.txt) — Python dependencies.

> The `main` branch is protected: changes land through pull requests and need
> at least one approving review. Build scripts and CI configuration are
> reviewed source as well — this directly implements the SignPath Foundation
> requirement that a binary must be traceable to reviewed source.

## Third-party components

- **[SwiftDL](https://github.com/harshsinghsv/swiftdl)** (MIT) — the download
  engine algorithm core was ported from this project.
- **Qt 6 / PyQt6 / QtWebEngine** — LGPL v3 / GPL v3.
- **Noto Serif SC** — bundled Chinese font, SIL Open Font License 1.1
  (`fonts/OFL.txt`).

The complete third-party component and licence notice is in
[LICENSE](LICENSE).

## Code signing and privacy

- [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md) — signing policy, signing
  coverage and team roles.
- [PRIVACY.md](PRIVACY.md) — privacy policy (local data, data flow of the
  translation feature, how engine tiers affect requests).
- [docs/04-windows-code-signing.md](docs/04-windows-code-signing.md) — how the
  signing mechanism works and how certificates are obtained.

## License

[MIT](LICENSE)
