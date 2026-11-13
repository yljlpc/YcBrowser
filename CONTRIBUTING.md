# Contributing to YcBrowser

Thanks for considering a contribution. This document explains how to build,
test and propose a change.

## Before you start

- **Search existing issues** — the bug may already be reported.
- **Open an issue first for larger changes** — a design discussion before a
  large patch saves everyone time.
- **Keep the license clean** — this project is MIT-licensed and distributed
  through [SignPath Foundation](https://signpath.org), which requires that
  **every** distributed component be open source. Do not add proprietary code,
  binaries or fonts (see *Fonts* below).

## Development setup

```bash
git clone https://github.com/yljlpc/YcBrowser.git
cd YcBrowser

# 1. Build the Rust native core
cd core && cargo build --release && cd ..

# 2. Install Python dependencies
python -m pip install -r requirements.txt

# 3. Run in development mode
./run.sh                 # Linux
python -m src.main       # Windows
```

### Prerequisites

- Rust 1.70+
- Python 3.10+
- Linux packaging: `fakeroot`, `dpkg-deb`
- Windows packaging: [NSIS](https://nsis.sourceforge.io/)

## Running the tests

```bash
cd core && cargo test              # Rust core unit tests
python tools/test_logic.py         # pure-logic tests (no Chromium needed)
python tools/test_download.py      # download engine, end to end
QT_QPA_PLATFORM=offscreen python tools/test_browser.py   # headless UI tests
```

Please add or update a test with every behavioural change. The CI workflow
(`.github/workflows/build-windows.yml`) runs all of the above on every push
and every tag.

## Submitting a pull request

1. Fork the repository and create a branch from `main`.
2. Make your change, keeping the commit history readable.
   One logical change per commit is much easier to review.
3. Make sure the tests pass locally and in CI.
4. Open a pull request against `main` and describe **what** changed and **why**.

### Commit messages

```
feat: add per-tab engine isolation for WebKit mode
fix: resume partial downloads after a dropped connection
docs: document the translation glossary format
```

### Code review

All changes — including changes to build scripts and CI configuration — are
reviewed before merging. Build and CI files are part of the reviewed source
because the signed artifacts must be traceable to reviewed source.

`main` is protected: direct pushes are not accepted, and at least one
approving review is required.

## Fonts

The Chinese font shipped with the project is **Noto Serif SC** under the
SIL Open Font License 1.1 (`fonts/OFL.txt`). If you would like to change the
bundled font, it must be an OFL-licensed (or similarly redistributable) font —
commercial fonts such as the Founder (方正) series cannot be redistributed in
the release package.

## Signing and releases

Releases are built by GitHub Actions from a `v*` tag and are signed by
[SignPath Foundation](https://signpath.org). Every release requires a manual
approval by the approver before the signature is applied. Please do **not**
upload build artifacts produced on your own machine to the Releases page —
that would break the build-to-source correspondence the signature attests to.

See [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md) for the full policy.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
