# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases up to and including `0.1.18` predate this file; see the
[Git history](https://github.com/neka-nat/freecad-mcp/commits/main) and
[GitHub releases](https://github.com/neka-nat/freecad-mcp/releases) for them.

## [Unreleased]

### Added
- Development tooling: `ruff`, `mypy`, and `pytest` configured via a `dev`
  dependency group, plus a GitHub Actions CI workflow that lints, type-checks,
  and tests on pull requests.
- Test suite for the MCP-side operation layer, response helpers, and the
  addon's IP allow-list validation.
- `CLAUDE.md` with architecture and development guidance.
- "Security considerations" section in the README documenting the remote-mode
  threat model (arbitrary code execution, no auth/encryption).
- Packaging metadata in `pyproject.toml` (description, project URLs, keywords,
  classifiers).

### Changed
- Refactored `operations/core.py` to remove the repeated try/except and
  screenshot-on-success boilerplate via a `_guard` decorator and a
  `_with_screenshot` helper (no behavior change).

### Fixed
- `execute_code_async` no longer tells the model to poll the removed
  `SessionState.Label` pattern; the runtime hint now matches the tool
  docstring.
- Corrected type annotations flagged by `mypy` (implicit-`Optional` default on
  `create_object`, and text-only tool return types that were narrower than the
  values actually returned).
