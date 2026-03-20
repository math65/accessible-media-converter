# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Accessible Media Converter** — a Windows desktop transcoding app built with `wxPython` and embedded `FFmpeg`. Accessibility (NVDA, keyboard workflows) is the top design priority, ahead of advanced features or raw configurability. Current version: `1.7.1`.

## Running and building

**Run from source:**
```powershell
python main.py
```

**Full release build** (compiles translations, PyInstaller, Inno Setup):
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
```

Expected outputs: `dist\AccessibleMediaConverter\AccessibleMediaConverter.exe` and `dist\AccessibleMediaConverter-Setup.exe`

**Check embedded FFmpeg version:**
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_embedded_ffmpeg.ps1 -CheckOnly
```

**Update embedded FFmpeg:**
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_embedded_ffmpeg.ps1
```

**Translation management:**
```powershell
python .\scripts\manage_i18n.py extract
python .\scripts\manage_i18n.py update --lang fr
python .\scripts\manage_i18n.py init --lang es
```

There is no automated test suite. Validation is manual (smoke test the built exe, run updater smoke check).

## Architecture

### Layers

- **`main.py`** — Entry point: loads config, installs gettext translation, cleans update artifacts, launches wxPython `MainLoop`.
- **`core/`** — All business logic: conversion, probing, batch management, formatting presets, track settings, i18n, auto-updater, support contact, debug/session state. Public API exported via `core/__init__.py`: `ConversionTask`, `FileProber`, `MediaMetadata`.
- **`ui/`** — wxPython UI. `ui/main_window.py` is the central orchestrator (large file by design). It handles file input, probing, dialog management, batch initiation, progress, and session restore. Separate dialog files for settings, preferences, track manager, support, and update.
- **`scripts/`** — PowerShell release tooling and Python i18n tooling.
- **`locales/`** — Gettext catalogs. English is the source language; French (`locales/fr/`) is the only shipped translation.
- **`docs/`** — User-facing HTML docs (`docs/en/`, `docs/fr/`). `docs/codex-context.md` is the canonical AI agent handoff document (French, updated manually at each milestone).

### Key data flow

1. User adds files → `FileProber` (wraps `ffprobe`) extracts `MediaMetadata`.
2. User selects format/settings → `formatting.py` provides codec presets and validation.
3. User starts conversion → `BatchConversionManager` (`core/batch_manager.py`) spawns parallel `ConversionTask` threads.
4. Each `ConversionTask` builds and executes an FFmpeg command line via `core/conversion.py`.
5. Config and session state persisted to `%APPDATA%\AccessibleMediaConverter`.

### Version and release metadata

- Application version is defined in `core/app_info.py`.
- Installer version is in `installer/UniversalTranscoder.iss` (`AppVersion` default).
- Both must be kept in sync on version bumps.

## Critical gotchas

- `bin/ffmpeg.exe` and `bin/ffprobe.exe` are git-tracked despite appearing in `.gitignore`. GitHub will warn on push due to their size.
- Updating `bin/` does **not** update `dist/`. Always rebuild after an FFmpeg update before publishing.
- The updater in `core/updater.py` only accepts the exact asset `AccessibleMediaConverter-Setup.exe`. The legacy fallback to versioned asset names was removed in v1.8.0.
- The FFmpeg update script reads the full release list from `GyanD/codexffmpeg` instead of `releases/latest`, because `latest` may not be the most recent build.

## Release workflow

1. Verify `git status` is clean.
2. Bump version in `core/app_info.py` and `installer/UniversalTranscoder.iss`.
3. Create `release-notes/vX.Y.Z.md`.
4. Run `scripts/build_release.ps1`.
5. Verify embedded FFmpeg version in `dist\AccessibleMediaConverter\_internal\bin\ffmpeg.exe`.
6. Commit, push, publish GitHub release with the single installer asset.

```powershell
gh release create vX.Y.Z .\dist\AccessibleMediaConverter-Setup.exe --title "vX.Y.Z" --notes-file .\release-notes\vX.Y.Z.md
```

## Upcoming: v1.8.0

- Remove legacy updater fallback to versioned asset name (single `AccessibleMediaConverter-Setup.exe` only)
- Bilingual release notes in a single GitHub release body with per-language extraction
- Fix i18n in support dialog

See `docs/plans/v1.8-updater-release-notes.md` for the detailed plan.
