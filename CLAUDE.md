# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Accessible Media Converter** — a Windows desktop transcoding app built with `wxPython` and embedded `FFmpeg`. Accessibility (NVDA, keyboard workflows) is the top design priority, ahead of advanced features or raw configurability. Current version: `1.9.1`.

## Running and building

**Run from source:**
```powershell
.venv\Scripts\python.exe main.py
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
.venv\Scripts\python.exe .\scripts\manage_i18n.py extract
.venv\Scripts\python.exe .\scripts\manage_i18n.py update --lang fr
.venv\Scripts\python.exe .\scripts\manage_i18n.py init --lang es
```

In development, `core/i18n.py` loads `.po` files directly via `polib` — no need to compile `.mo` files while iterating on translations.

There is no automated test suite. Validation is manual (smoke test the built exe, run updater smoke check).

## Architecture

### Layers

- **`main.py`** — Entry point: loads config, installs gettext translation, cleans update artifacts, launches wxPython `MainLoop`.
- **`core/`** — All business logic. Key modules:
  - `conversion.py` — `ConversionTask`: builds and runs FFmpeg commands (audio/video/image paths).
  - `probe.py` — `FileProber` / `MediaMetadata` / `MediaTrack`: wraps `ffprobe` to extract stream info.
  - `batch_manager.py` — `BatchConversionManager`: spawns parallel `ConversionTask` threads.
  - `merge.py` — `MergeTask`: concatenates multiple files into one output via FFmpeg concat demuxer.
  - `formatting.py` — codec presets, format/codec constants, and settings validation.
  - `track_settings.py` — per-file track selection overrides (which audio/video/subtitle streams to keep or map).
  - `i18n.py` — gettext installation, language resolution, `.po`→`.mo` fallback.
  - `debug_session.py` — config and session persistence to `%APPDATA%\AccessibleMediaConverter`.
  - `error_report.py` — re-runs failed FFmpeg commands with `-loglevel verbose` for diagnostic reports.
  - `updater.py`, `support.py`, `documentation.py`, `app_info.py`, `logger.py` — auto-updater, support email, local HTML docs, version info, logging setup.
  - Public API exported via `core/__init__.py`: `ConversionTask`, `FileProber`, `MediaMetadata`.
- **`ui/`** — wxPython UI. `ui/main_window.py` is the central orchestrator (large file by design). It handles file input, probing, dialog management, batch initiation, progress, and session restore. Separate dialog files for settings, preferences, track manager, support, and update.
- **`scripts/`** — PowerShell release tooling and Python i18n tooling.
- **`locales/`** — Gettext catalogs. English is the source language; French (`locales/fr/`) is the only shipped translation.
- **`docs/`** — User-facing HTML docs (`docs/en/`, `docs/fr/`). `docs/codex-context.md` is the canonical AI agent handoff document (French, updated manually at each milestone).

### Key data flow

1. User adds files → `FileProber` (wraps `ffprobe`) extracts `MediaMetadata`. Images are detected via extension, ffprobe format name, or heuristic and routed to a dedicated image tab.
2. User selects format/settings → `formatting.py` provides codec presets and validation for audio, video, and image formats.
3. User starts conversion → `BatchConversionManager` (`core/batch_manager.py`) spawns parallel `ConversionTask` threads.
4. Each `ConversionTask` builds and executes an FFmpeg command line via `core/conversion.py`. Image conversion uses a dedicated code path (`_build_image_command` / `_run_image_conversion`).
5. Config and session state persisted to `%APPDATA%\AccessibleMediaConverter`.

### Version and release metadata

- Application version is defined in `core/app_info.py`.
- Installer version is in `installer/UniversalTranscoder.iss` (`AppVersion` default).
- Both must be kept in sync on version bumps.

### i18n in `core/` modules

`core/` modules are imported before `main.py` calls `install_language()`, so they cannot call `_()` directly at import time. They use a lazy helper instead:

```python
def _translate(msgid):
    translator = builtins.__dict__.get('_')
    if callable(translator):
        return translator(msgid)
    return msgid
```

Call `_translate()` / `_translatef()` inside functions, never at module level.

## Critical gotchas

- `bin/ffmpeg.exe` and `bin/ffprobe.exe` are git-tracked despite appearing in `.gitignore`. GitHub will warn on push due to their size.
- Updating `bin/` does **not** update `dist/`. Always rebuild after an FFmpeg update before publishing.
- The updater in `core/updater.py` only accepts the exact asset `AccessibleMediaConverter-Setup.exe`. The legacy fallback to versioned asset names was removed in v1.8.0.
- The FFmpeg update script reads the full release list from `GyanD/codexffmpeg` instead of `releases/latest`, because `latest` may not be the most recent build.
- Python 3.14+ detects `_` variable shadowing in function scope. Never use `_` as a throwaway variable in functions that call `_()` for gettext — use explicit names like `label` or index access like `item[0]`.

## Release workflow

1. Verify `git status` is clean.
2. Bump version in `core/app_info.py` and `installer/UniversalTranscoder.iss`.
3. Create `release-notes/vX.Y.Z.en.md` and `release-notes/vX.Y.Z.fr.md`.
4. Run `scripts/build_release.ps1` — generates `dist\release-notes.md` automatically.
5. Verify embedded FFmpeg version in `dist\AccessibleMediaConverter\_internal\bin\ffmpeg.exe`.
6. Commit, push, publish GitHub release with the single installer asset.

```powershell
gh release create vX.Y.Z .\dist\AccessibleMediaConverter-Setup.exe --title "vX.Y.Z" --notes-file .\dist\release-notes.md
```

## Recent changes

- **v1.9.1** — Image conversion support (JPEG, PNG, WebP, TIFF, BMP) with dedicated UI tab, format-specific settings dialog, resize with aspect ratio preservation, and French translations. Auto error report dialog. Logger crash fix for exe without console.
- **v1.8.0** — Removed legacy updater fallback. Bilingual release notes. Fixed i18n in support dialog. Accessibility improvements (StaticBox tab order, keyboard navigation, estimated time remaining).
