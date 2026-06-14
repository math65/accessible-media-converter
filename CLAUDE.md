# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Accessible Media Converter** — a Windows desktop transcoding app built with `wxPython` and embedded `FFmpeg`. Accessibility (NVDA, keyboard workflows) is the top design priority, ahead of advanced features or raw configurability. Current version: `1.13.0`.

## Running and building

Dependencies are managed with **uv** (`pyproject.toml` + `uv.lock`). The `dev`
dependency group holds the packaging tools (`pyinstaller`, `polib`); runtime deps
are `wxPython` and `accessible_output2`.

**Set up / refresh the environment:**
```powershell
uv sync          # creates .venv and installs runtime + dev deps from the lock
```
`uv sync` keeps the venv at `.venv`, so the `.venv\Scripts\python.exe` convention
below (and in `scripts/build_release.ps1`) still works unchanged. To bump a pinned
dep deliberately: `uv lock --upgrade-package wxPython` then re-test (NVDA).

**Run from source:**
```powershell
uv run main.py
# or, equivalently:
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
  - `cue.py` — cue sheet parsing (`CueSheet`/`CueTrack`, `parse_cue_text`/`load_cue_file`, `resolve_cue_audio`, `cuesheet_from_chapters`); drives album splitting (1 input → N tracks) consumed by `BatchConversionManager`.
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
- **`docs/`** — User-facing HTML docs (`docs/en/`, `docs/fr/`), bundled into the app by PyInstaller. AI agent handoff/context lives in this `CLAUDE.md` plus the auto-memory, not in a separate doc.

### Support / feedback backend

The support form (`core/support.py`) posts to `https://mathieumartin.ovh/api/feedback/report`,
the **generic multi-app endpoint** of the shared platform repo `app-backend`
(`C:\Users\mathi\dev\app-backend`) — a single **Go** binary (stdlib, no dependencies)
deployed to `/opt/app-backend-go/`, which handles all `/api/*` for every app.

- **Client contract (since v1.10.2)**: multipart `report` (JSON) + optional `log_file`,
  authenticated with `Authorization: Bearer <AMC_BEARER_SECRET>`. The JSON payload carries
  `{"app": "amc", "email", "summary", "subject_hint", "sections"}`. The technical context is
  built client-side as a French key/value section (`sections["Informations techniques"]`,
  hardcoded French in `_build_support_fr_section` — the email goes to the developer, so it
  must not follow the UI language). `summary` becomes the red "Message d'erreur" section the
  service auto-adds. Same shape as the DownAccess client (`dl/app/core/error_reporter.py`).
- **Legacy route still live**: the old `/api/support-report` (honeypot auth, plain-text
  email, server-side formatting via `internal/legacy/amc_support.go`) is **kept alive** on
  the server for AMC installs older than v1.10.2. Never remove it while old clients exist
  (RÈGLE D'OR). `server/support-report/` in *this* repo stays **dormant** (history/rollback).
- Server facts: a single static **Go** binary behind Caddy
  (`reverse_proxy 127.0.0.1:8787`), run by **systemd** (`app-backend`, ~10 MB RAM,
  user `www-data`). Secrets in `/etc/app-backend/env` (root:600, injected by
  systemd): SMTP password `APPCLAVIER_SMTP_PASS`, and **`AMC_BEARER_SECRET`** (the
  per-app Bearer for the generic route — must be present in the env file). The old PHP
  backend (`/var/www/app-backend`, PHP-FPM) is **dormant**, kept for rollback.

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

- **v1.13.0 (cue sheets — album splitting)** — First **1 input → N outputs** path. A `.cue`
  (or a FLAC with an embedded cue, opt-in) carries `meta.cue_sheet` (a `core/cue.py` `CueSheet`);
  `BatchConversionManager._prepare_jobs` expands it into one job per track via `_append_cue_jobs`,
  each a `ConversionTask` **clip** (`clip=(start_ms,end_ms)`, `extra_tags`, `input_path_override`):
  `-ss` before `-i`, `-t` after, explicit per-track tags (no source-metadata copy). Output goes to an
  **album subfolder** `<dir>/<album>/NN - Title.ext` (`build_cue_track_output_path` + `sanitize_filename`).
  **Parser** `core/cue.py`: `parse_cue_text`/`load_cue_file` (MM:SS:FF→ms, encodings utf-8-sig/cp1252),
  `finalize_tracks`, `resolve_cue_audio`, `cuesheet_from_chapters`. **probe** branches on `.cue`
  (`_analyze_cue`: parse, resolve image, probe its duration) and adds `-show_chapters` to detect an
  **embedded** cue (`CUESHEET` tag text or ffprobe chapters → `meta.has_embedded_cue`). **UI**: cue row
  shows "Album — N tracks (CUE)" / "To split"; excluded from merge; context menu "Preview Tracks…",
  "Split by Embedded Cue Sheet" / "Convert as a Single File". Fixed a race on the shared album subfolder
  (`os.makedirs(exist_ok=True)` in `ConversionTask.run`). Tags from cue: title/artist(performer)/album/
  album_artist/track/date/genre.
- **v1.13.0 (4 Sèb feedback items)** — Done as 4 independent commits.
  **(A) Enter validates dialogs**: `SetAffirmativeId`/`SetEscapeId` added to `ui/settings_dialog.py`,
  `support_dialog.py`, `update_dialog.py`, `error_report_dialog.py` (the others already had it).
  Multi-line `wx.TextCtrl` keep Enter as newline natively — no trap. Removed dead `TE_PROCESS_ENTER`
  from `track_manager` `txt_title`; tooltip on `btn_merge` clarifying it uses the selected format
  (the "merge only MP3?" question was a misunderstanding — `on_merge` already follows `combo_format`).
  **(B) Reorder files**: `_move_media_item` swaps the focused row with its neighbour (focus/selection
  follow), via a new `_set_list_row` helper reused by `_append_media_metadata`. **Alt+Up/Down** handled
  in `on_char_hook` (frame-level EVT_CHAR_HOOK, when a file list has focus) + "Move Up"/"Move Down"
  context-menu entries. The list order drives merge order. NVDA gets an **explicit spoken
  announcement** ("<file> moved, N of M") via the new `core/speech.speak` helper backed by
  **accessible_output2** (added to `requirements.txt`; the spec bundles it via `collect_all` for
  `accessible_output2`/`platform_utils`/`libloader` — screen-reader DLLs). **(C) Single instance**: `main.py` creates a
  `wx.SingleInstanceChecker`; secondary instances (Explorer multi-select runs the `%1` verb once per
  file → N windows) relay their paths through `core/single_instance.py` (relay file in `%APPDATA%`,
  drained by a `wx.Timer` in `MainWindow.start_external_paths_watcher`) then exit. Master window adds
  the paths and raises itself. Relay file (not a socket) → no Windows firewall prompt. **(D) Per-file
  output settings**: `meta.output_override = {"format", "settings"}` on `MediaMetadata` (modelled on
  `track_settings`/`metadata_overrides`). Context menu (audio/video) "Output Settings…" picks a format
  among the tab's valid formats then reuses `SettingsDialog`, applied to the multi-selection; "Reset
  Output Settings" clears it. Shown in the Status column (`Output: MP3 320k`). Consumed by
  `BatchConversionManager._prepare_jobs` via `_resolve_job_format_settings` (override format/settings
  per job; threads/preserve-metadata inherited from global). Merge ignores overrides (single format).
- **v1.12.0 (ABR MP3 + Explorer context menu)** — Follow-up to tester Sèb's feedback.
  **ABR mode** (target average bitrate) added to MP3 alongside CBR/VBR: `apply_audio_codec_args`
  (`core/ffmpeg_helpers.py`) emits `-abr 1 -b:a <bitrate>` for `rate_mode == "abr"`; libmp3lame
  exposes **no** VBR min/max bound, ABR is the honest equivalent. In `ui/settings_dialog.py` the
  rate-mode selector moved from **index-based** (0=CBR/1=VBR) to **value-based** mapping that depends
  on the codec (`_rate_mode_values`, `_populate_rate_mode_combo`/`_current_rate_mode`/
  `_set_rate_mode_selection`): MP3 → CBR/ABR/VBR, AAC → CBR/VBR only (native AAC encoder has no
  `-abr`). ABR reuses the bitrate selector (target average). Summary `ABR {bitrate}` in
  `core/_build_audio_mode_summary`. Joint stereo: already on by default, nothing to do. **Explorer
  context menu** "Convert with Accessible Media Converter": `main.py` reads `sys.argv` and routes the
  paths through the new public method `MainWindow.add_external_paths` (mirrors `on_paste_files`,
  reuses `_collect_media_paths`/`_process_added_files`); `installer/UniversalTranscoder.iss` adds
  `[Registry]` HKCR keys (`*\shell` + `Directory\shell`, `Flags: uninsdeletekey`) and a
  `[CustomMessages] ConvertWithApp` EN/FR. Single-instance out of scope (multi-select opens multiple
  windows). Also ships the truncated-m4a fix (`de40507`, never published).
- **v1.11.0 (M4B audiobooks)** — New **M4B output format with chapters**.
  `"m4b"` added to `AUDIO_OUTPUT_FORMAT_KEYS` (`core/formatting.py`); it is a MP4/AAC
  container forced with `-f ipod` and defaults to **stereo 128k** (audiobooks may contain
  music — fully adjustable, mono/64k possible). **Merging** several audio files into an M4B
  generates **one chapter per file**: `core/merge.py` builds an FFMETADATA file
  (`;FFMETADATA1` + `[CHAPTER]` blocks, `TIMEBASE=1/1000`, START/END in ms cumulated from
  `meta.duration`), passed as a 2nd input with `-map 0:a -map_chapters 1`. **Converting** a
  single already-chaptered file to M4B preserves its chapters (`-map_chapters 0`). Chapter
  titles follow a new **Preferences** dropdown `m4b_chapter_naming` (3 modes:
  `title_or_number` default → file's `title` tag else localized "Chapter N" via gettext;
  `title_or_filename`; `numbered`). M4B routes through the AAC controls in the settings
  dialog (`_get_active_audio_codec_key` maps `m4b`→`aac`) and is accepted as input (`.m4b`).
- **v1.11.0 (video/audio metadata)** — Metadata editor adapts to a **video Content type**
  selector (Film / TV series / Other) showing relevant fields (synopsis; series/season/episode),
  with **filename auto-detection** of season/episode (SxxExx) for video and track number for
  audio (`core/episode_parse.py`), new audio fields (Grouping, Copyright, multi-line Lyrics),
  and accessibility fixes (Ctrl+A and the keyboard context menu now honour the multi-selection).
- **v1.11.0 (updater integrity)** — `core/updater.py` now verifies the downloaded installer
  before launching it: completeness check (bytes vs `Content-Length`) plus a SHA-256 match
  against the GitHub asset `digest` field (`parse_expected_sha256`; `find_setup_asset` returns
  `(name, url, digest)`). A mismatch raises `UpdateDownloadError` and the installer is not run.
- **v1.11.0 (user docs)** — User documentation (`docs/en/`, `docs/fr/`) brought up to date with
  the app: new M4B/chapters, metadata editor (audio + video Content type + auto-detection),
  preferences, and update integrity. New page `docs/{en,fr}/user/image-conversion.html` (the
  image feature was undocumented). EN pages now use a **local** stylesheet (`docs/en/assets/`)
  instead of pulling FR's, FR/EN parity fixed (e.g. the missing "Application language" bullet),
  and keyboard equivalents (Menu key / Shift+F10) added for every context-menu action.
  Published as **v1.11.0** (2026-06-08), tag `v1.11.0`, single asset
  `AccessibleMediaConverter-Setup.exe`.
- **v1.10.2 (report gate)** — Reporting a problem now requires an up-to-date app and a valid email.
  Before opening the support form (Help → Contact Support) **or** the automatic conversion-error
  dialog, `ui/main_window.py` runs a fresh GitHub update check (`_check_update_then` /
  `_finish_report_gate`, reusing `fetch_latest_release`/`is_release_newer`/`UpdateDialog`). If a newer
  version exists it **hard-blocks** with an "Update now / Cancel" prompt and the report does not open
  (the bug may already be fixed); when up to date — or the check fails offline — the report opens.
  Short-circuited during a conversion (an update can't install anyway). The email field is now
  labelled "(required)" in both dialogs (sending without a valid email was already rejected). Embedded
  FFmpeg bumped to `2026-06-04-git-c27a3b12e3`.
- **v1.10.2 (announcements)** — Startup announcement client (mirrors DownAccess). `core/announce.py`
  polls the shared backend `POST /api/announce/check` (Bearer, reuses `_APP_ID`/`_BEARER` from
  `core/support.py`) at launch; an active announcement is shown via `wx.MessageBox` (icon from
  `style`), then confirmed with `/api/announce/ack`. A per-install `install_id` (uuid, generated on
  first launch) and a `seen_announcements` list (for `mode: once` dedup) live in `settings_store`
  (`core/formatting.py` defaults + normalization). Wired in `ui/main_window.py`
  (`check_announcement_at_startup` / `_on_announcement_received`) and called from `main.py` after the
  update check. The check is silent: any network error is ignored. Announcements are created in the
  web admin (`/api/admin`) targeting `amc` (or `*`). The check now sends the **UI language**
  (`lang` = `i18n.get_current_language_code()`, `fr`/`en`): the backend returns the localized
  title/body (announcements are bilingual; English falls back to French when no English overlay).
- **v1.10.2** — Support form migrated from the legacy `/api/support-report` (honeypot)
  to the generic `/api/feedback/report` endpoint (Bearer auth, multipart `report` JSON +
  `log_file`), matching the DownAccess client. `core/support.py` now builds the technical
  block as a hardcoded-French key/value section and sends it with `Authorization: Bearer
  <AMC_BEARER_SECRET>`; `SUPPORT_REPORT_API_URL` was removed from `core/app_info.py`. The
  legacy route stays live server-side for older installs (no removal). Requires
  `AMC_BEARER_SECRET` in the server env (`/etc/app-backend/env`). See "Support / feedback
  backend".
- **2026-06-04 (backend)** — The `/api/support-report` endpoint moved to a new
  shared platform repo, `app-backend` (serves `/api/*` for all apps), which was
  then rewritten from PHP to **Go** (single static binary behind Caddy, ~10 MB RAM).
  The route and payload are unchanged (legacy adapter), so no client change is
  needed. This repo's `server/support-report/` is now dormant. See "Support /
  feedback backend" under Architecture.
- **v1.10.1** — Update installer now relaunches the app after a silent update. `installer/UniversalTranscoder.iss` gained a `[Run]` entry `Filename: {app}\exe; Flags: nowait runasoriginaluser; Check: WizardSilent` (only on silent installs, launched as the original non-elevated user). The relaunch is performed by the **new version's** installer, so updating *to* v1.10.1+ brings the app back automatically.
- **v1.10.0** — Metadata editing: right-click an audio/video file (or several) → "Edit Metadata…" opens `ui/metadata_editor.py` to edit all standard tags (title/artist/album/album_artist/composer/date/track/disc/genre/comment) and the cover art (replace from JPEG/PNG, remove, keep). A target selector chooses **"apply during conversion"** (stored on `meta.metadata_overrides`, applied by `ConversionTask`) or **"re-tag the original now"** (in-place `-c copy` via `core/metadata_retag.py`, temp file + atomic replace, original untouched on failure). Batch editing applies filled fields to all selected files. Pure logic in `core/metadata_edit.py`. Cover embedding during conversion is limited to audio outputs (mp3/aac/alac/flac); in-place cover follows the source container. `core/probe.py` now extracts `format_tags`/`has_cover_art`/`source_format_name`.
- **v1.9.5 (post-v1.9.4)** — Update installer now runs **silently with a progress bar** instead of the interactive wizard: `launch_installer_after_exit()` passes `/SILENT /SUPPRESSMSGBOXES /NORESTART` (works with already-published installers too). `installer/UniversalTranscoder.iss` gained `CloseApplications=yes` / `RestartApplications=no` to make silent installs robust against locked files. The download/confirm flow in `UpdateDialog` is unchanged. Fixed "output path equals input file" collision: converting a file to its own format in the source folder (e.g. `song.m4a`→M4A/AAC, `track.mp3`→MP3, `photo.png`→PNG) no longer gets silently skipped (skip policy) or fails with FFmpeg "Output is also Input" (overwrite policy). `BatchConversionManager._reserve_output_path()` now always writes a safe suffixed copy (`name (1).ext`) when the candidate output is the source file itself, for all formats and all policies. New global preference "Preserve original metadata" (opt-in, off by default): adds `-map_metadata 0 -map_chapters 0` to audio/video conversions and merges, and preserves embedded cover art for audio outputs (mp3/aac/alac/flac) by copying the `attached_pic` stream (`-c:v copy` instead of `-vn`) when the source is not a real video. Shared via `apply_metadata_preservation()` in `core/ffmpeg_helpers.py`. Embedded FFmpeg bumped to `2026-05-28-git-7b46c6a2a3`. `update_embedded_ffmpeg.ps1` now compares the GitHub release tag directly (download-free `-CheckOnly`), and the `/update-ffmpeg` skill gained post-update, already-up-to-date, and error-handling guidance.
- **v1.9.4** — Clear error for a missing input file instead of a cryptic FFmpeg failure. Added `/release` and `/update-ffmpeg` skills.
- **v1.9.3** — Embedded FFmpeg update; 'View on GitHub' entry in the Help menu.
- **v1.9.2** — Bugfix pass (merge paths, conversion timeout, audio copy, bare except, duplicate messages) and shared FFmpeg helper extraction into `core/ffmpeg_helpers.py`.
- **v1.9.1** — Image conversion support (JPEG, PNG, WebP, TIFF, BMP) with dedicated UI tab, format-specific settings dialog, resize with aspect ratio preservation, and French translations. Auto error report dialog. Logger crash fix for exe without console.
- **v1.8.0** — Removed legacy updater fallback. Bilingual release notes. Fixed i18n in support dialog. Accessibility improvements (StaticBox tab order, keyboard navigation, estimated time remaining).
