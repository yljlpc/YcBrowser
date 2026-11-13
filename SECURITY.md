# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.1.x   | ✅ |
| < 1.1   | ❌ |

Only the latest release line receives security fixes. Users are encouraged to
always run the latest published release from
[Releases](https://github.com/yljlpc/YcBrowser/releases).

## Reporting a Vulnerability

**Please do not open a public Issue for security problems.**

Use GitHub's private vulnerability reporting, which is enabled for this
repository:

> **Security** tab → **Report a vulnerability**

This opens a private advisory that only the maintainers can see. It lets us
discuss the issue, agree on a fix and prepare a release before anything
becomes public.

Please include, as far as you can:

- the affected version and the download source you used;
- your operating system and architecture;
- a description of the impact (what an attacker can achieve);
- minimal reproduction steps, logs or a crash dump;
- whether the issue is already public anywhere.

### What to expect

- Acknowledgement within **7 days**.
- An assessment and, where a fix is warranted, a planned release date within
  **30 days**.
- Credit in the release notes unless you prefer to stay anonymous.

### Scope

In scope: the browser application, the Rust native core, the download engine,
the translation client, and the build and packaging scripts in this repository.

Out of scope: issues in third-party components that are used unmodified
(Qt 6 / Chromium, PyQt6) — please report those to their respective
maintainers. We will help triage and coordinate if a third-party issue affects
YcBrowser.

### Code signing

Windows binaries are signed through the
[SignPath Foundation](https://signpath.org) free open-source program. If you
find a published binary that does not match the source in this repository, or a
signature that does not validate, treat it as a supply-chain incident and
report it through the channel above immediately. See
[CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md) for the signing policy.
