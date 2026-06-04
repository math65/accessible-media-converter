# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Accessible Media Converter** — a Windows desktop transcoding app built with `wxPython` and embedded `FFmpeg`. Accessibility (NVDA, keyboard workflows) is the top design priority, ahead of advanced features or raw configurability. Current version: `1.9.4`.

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

**Check embedded FFmpeg version** (dry run — compares the GitHub release tag, no download):
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
  - `ffmpeg_helpers.py` — shared FFmpeg helpers (binary path resolution, thread parsing, audio codec/sample-rate args) used by `ConversionTask`, `MergeTask`, and `FileProber`.
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

### Support / feedback backend

The support form (`core/support.py`) posts to `https://mathieumartin.ovh/api/support-report`.
**Since 2026-06-04 this endpoint is served by a separate shared platform repo,
`app-backend` (`C:\Users\mathi\dev\app-backend`, deployed to `/var/www/app-backend/`),
which handles all `/api/*` for every app via one front controller.**

- The route and the JSON payload are **unchanged** — `app-backend` reproduces the
  old `/api/support-report` contract exactly (honeypot auth, plain-text email,
  curated `technical_context` formatting) through a legacy adapter, so the
  shipped client keeps working with **no migration required**.
- `server/support-report/` in *this* repo is now **dormant**: kept for history
  and rollback, but no longer deployed. Don't edit it for live changes — work in
  the `app-backend` repo instead.
- Server facts: **PHP-FPM 8.4** (not 8.2), **`mbstring` is absent** (avoid `mb_*`
  in any backend PHP). SMTP password env `APPCLAVIER_SMTP_PASS`.
- Future: migrate the client to the generic `/api/feedback/report` endpoint
  (payload carries `"app": "amc"`); that path will need an `AMC_BEARER_SECRET`
  env var on the server (not created yet — the legacy honeypot route needs none).

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
- The FFmpeg update script reads the full release list from `GyanD/codexffmpeg` instead of `releases/latest`, because `latest` may not be the most recent build. It decides whether an update is needed by comparing the GyanD release **tag** (which is the exact build token) against the embedded `ffmpeg -version` string, so `-CheckOnly` answers from API metadata alone and downloads nothing.
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

- **2026-06-04 (backend)** — The `/api/support-report` endpoint moved to a new
  shared platform repo, `app-backend` (serves `/api/*` for all apps). The route
  and payload are unchanged (legacy adapter), so no client change is needed. This
  repo's `server/support-report/` is now dormant. See "Support / feedback backend"
  under Architecture.
- **v1.10.1** — Update installer now relaunches the app after a silent update. `installer/UniversalTranscoder.iss` gained a `[Run]` entry `Filename: {app}\exe; Flags: nowait runasoriginaluser; Check: WizardSilent` (only on silent installs, launched as the original non-elevated user). The relaunch is performed by the **new version's** installer, so updating *to* v1.10.1+ brings the app back automatically.
- **v1.10.0** — Metadata editing: right-click an audio/video file (or several) → "Edit Metadata…" opens `ui/metadata_editor.py` to edit all standard tags (title/artist/album/album_artist/composer/date/track/disc/genre/comment) and the cover art (replace from JPEG/PNG, remove, keep). A target selector chooses **"apply during conversion"** (stored on `meta.metadata_overrides`, applied by `ConversionTask`) or **"re-tag the original now"** (in-place `-c copy` via `core/metadata_retag.py`, temp file + atomic replace, original untouched on failure). Batch editing applies filled fields to all selected files. Pure logic in `core/metadata_edit.py`. Cover embedding during conversion is limited to audio outputs (mp3/aac/alac/flac); in-place cover follows the source container. `core/probe.py` now extracts `format_tags`/`has_cover_art`/`source_format_name`.
- **v1.9.5 (post-v1.9.4)** — Update installer now runs **silently with a progress bar** instead of the interactive wizard: `launch_installer_after_exit()` passes `/SILENT /SUPPRESSMSGBOXES /NORESTART` (works with already-published installers too). `installer/UniversalTranscoder.iss` gained `CloseApplications=yes` / `RestartApplications=no` to make silent installs robust against locked files. The download/confirm flow in `UpdateDialog` is unchanged. Fixed "output path equals input file" collision: converting a file to its own format in the source folder (e.g. `song.m4a`→M4A/AAC, `track.mp3`→MP3, `photo.png`→PNG) no longer gets silently skipped (skip policy) or fails with FFmpeg "Output is also Input" (overwrite policy). `BatchConversionManager._reserve_output_path()` now always writes a safe suffixed copy (`name (1).ext`) when the candidate output is the source file itself, for all formats and all policies. New global preference "Preserve original metadata" (opt-in, off by default): adds `-map_metadata 0 -map_chapters 0` to audio/video conversions and merges, and preserves embedded cover art for audio outputs (mp3/aac/alac/flac) by copying the `attached_pic` stream (`-c:v copy` instead of `-vn`) when the source is not a real video. Shared via `apply_metadata_preservation()` in `core/ffmpeg_helpers.py`. Embedded FFmpeg bumped to `2026-05-28-git-7b46c6a2a3`. `update_embedded_ffmpeg.ps1` now compares the GitHub release tag directly (download-free `-CheckOnly`), and the `/update-ffmpeg` skill gained post-update, already-up-to-date, and error-handling guidance.
- **v1.9.4** — Clear error for a missing input file instead of a cryptic FFmpeg failure. Added `/release` and `/update-ffmpeg` skills.
- **v1.9.3** — Embedded FFmpeg update; 'View on GitHub' entry in the Help menu.
- **v1.9.2** — Bugfix pass (merge paths, conversion timeout, audio copy, bare except, duplicate messages) and shared FFmpeg helper extraction into `core/ffmpeg_helpers.py`.
- **v1.9.1** — Image conversion support (JPEG, PNG, WebP, TIFF, BMP) with dedicated UI tab, format-specific settings dialog, resize with aspect ratio preservation, and French translations. Auto error report dialog. Logger crash fix for exe without console.
- **v1.8.0** — Removed legacy updater fallback. Bilingual release notes. Fixed i18n in support dialog. Accessibility improvements (StaticBox tab order, keyboard navigation, estimated time remaining).
