# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Accessible Media Converter** — a Windows desktop transcoding app built with `wxPython` and embedded `FFmpeg`. Accessibility (NVDA, keyboard workflows) is the top design priority, ahead of advanced features or raw configurability. Current version: `1.20.0-rc1` (beta / pre-release; last stable `1.19.0`).

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

- **v1.20.0-rc1 — BETA (pre-release), branch `feature/segment-editor`, not yet on master.** Ships the
  **file cutter / segment editor** (memory [[project_feature_video_trim]]): a right-click **"Cut /
  Split…"** action on an audio/video file opens a dedicated `wx.Frame` editor (`ui/segment_editor.py`,
  menu bar). Model in `core/segments.py` (regions keep/discard, paving `[0,duration]`); export in
  `core/segment_export.py` (`SegmentExportTask` — one file: copy-concat vs reencode `filter_complex`) and
  via `BatchConversionManager._append_segment_jobs` (N separate files). Audio engine `core/audio_player.py`
  (single persistent PortAudio stream, one engine thread — churn caused native segfaults; sounddevice, no
  numpy, no COM); montage-mode playback (skip discarded, from current position), verify-cut (real export
  join), REAPER-style scrub, silence jump (`core/silence.py`), fine step, per-track preview, undo/redo,
  save/open `.amccut` project, format+quality dialog at export (editor stays open after export). New dep
  **sounddevice** (+cffi/pycparser) bundled in the spec (`sounddevice`+`_sounddevice_data` PortAudio DLL).
  Prefs `cutter_announce_transport`/`cutter_announce_position`. **`APP_VERSION="1.20.0-rc1"`** carries the
  rc suffix (updater rule, [[project_prerelease_optin]]); `APP_VERSION_WIN="1.20.0.0"`. Pipeline validated
  by an automated end-to-end pass (real exports: audio/video, copy+reencode, separate files); **NVDA
  real-use validation pending** (Mathieu). Publish as GitHub **prerelease** (`--prerelease`).

- **v1.19.0 — published 2026-06-29, tag `v1.19.0`, commit `d8aab05`.** Ships the **DownAccess ↔ AMC
  integration** (Downie→Permute pairing: DownAccess downloads, AMC converts). The DownAccess side was
  already shipped (it launches `AccessibleMediaConverter.exe "<path>"`); this release is the AMC-side
  follow-up from the handoff note `DOWNACCESS_INTEGRATION.md` (committed).
  - **Reliability fix**: `MainWindow.add_external_paths` (`ui/main_window.py`) no longer **drops**
    files received from outside (DownAccess, or the Explorer "Convert with…" verb) while a conversion
    is running. They are queued in `self._pending_external_paths` (with a status message) and drained
    by the new `_drain_pending_external_paths()`, called from both `_on_batch_complete` and
    `_on_merge_complete` after `is_converting` clears. The Explorer single-instance relay
    (`_on_external_watch_tick`) already routes through `add_external_paths`, so it's covered too.
  - **Reciprocity**: new Help menu entry "Download Media (DownAccess)…" opening `DOWNACCESS_RELEASES_URL`
    (`core/app_info.py`, `https://github.com/math65/downaccess/releases`), mirroring "View on GitHub…"
    (reuses `open_release_page`). i18n FR added. Embedded FFmpeg unchanged (`8.1.2`).
  - ⚠️ Published **without** real-world NVDA validation (to confirm a posteriori).

- **v1.18.0 — published 2026-06-27, tag `v1.18.0`, commit `47bf0ce`.** Bundles the three features
  below (opt-in pre-releases, batch track management, track disposition cleanup) plus an **embedded
  FFmpeg bump to `8.1.2`** (GyanD stable tag, via `/update-ffmpeg`). First release validated by
  Mathieu in real use (batch track management on the test fixtures). The `/release` skill was
  expanded this cycle to document stable-vs-beta version bumping (the `-rcN` suffix requirement).

- **Track disposition cleanup (v1.18.0).** The per-type disposition
  checkbox lists in `core/track_settings.py` were wrong (Sèb/Mathieu spotted audio showing BOTH
  "Audio Description" and "Descriptions"). Reworked via a web-research workflow against primary
  sources (FFmpeg `libavformat/avformat.h` disposition comments + Matroska RFC 9559). New per-type
  sets — **video**: `default` only (dropped `original`/`comment` — no consumer meaning on a video
  stream); **audio** base `default`,`visual_impaired` (audio description), advanced `dub`,`original`,
  `comment` (dropped `descriptions` = the bug, plus `lyrics`/`karaoke`/`clean_effects`/`non_diegetic`
  = no consumer use / no Matroska mapping; `hearing_impaired` also dropped from audio — rare/confusing
  "boosted-dialogue" mix, kept on subtitles only); **subtitle** base
  `default`,`forced`,`hearing_impaired`, advanced `original`,`comment`,`dub`,`captions`,`descriptions`.
  Key facts: `visual_impaired` = audio-description AUDIO flag; `descriptions` = textual video
  description, a TEXT/subtitle flag (never audio). Subtitle "advanced" flags are **preserved from
  source but hidden** (TrackPanel shows only base for subtitles), so niche flags survive a remux
  without cluttering the UI. Dispositions emit generically in `core/conversion.py`
  (`-disposition:<v|a|s>:<idx> a+b+c`), so removing a flag from the list drops it from the form AND
  the output. Legacy stored entries referencing removed flags normalize away gracefully. See
  [[reference_track_dispositions]] in auto-memory.

- **Batch track management (v1.18.0).** The two video-tab track
  context-menu actions now **follow the selection** (Sèb request: choosing/managing audio tracks
  was per-file only). Mirrors the existing "Edit Metadata (N files)…" pattern via
  `_resolve_metadata_target_indices`.
  - **`ui/main_window.py`**: `on_open_track_manager(index, target_indices=None)` and
    `on_choose_audio_extract_track(index, target_indices=None)` now propagate the reference file's
    result to every selected file; menu labels read "Manage Tracks (N files)…" / "Choose Audio
    Track (N files)…". `target_indices` is hoisted once in the menu builder (also reused for the
    presets entry). Both handlers keep their single-file behaviour when only one row is targeted.
  - **Matching rules** (heterogeneous selections) — both **by track position**, no language
    heuristics (Mathieu/Sèb decision: extraction keeps ONE track and the dialog already lists every
    track, so position both matches the mental model and tells two same-language tracks apart, e.g.
    FR original vs FR audio-description = different rows). **Manage Tracks** copies a deepcopy of the
    `track_settings` config to each file — each re-normalizes it against its own streams by
    `original_index` via `normalize_track_settings`. **Choose Audio Track** uses helper
    `_match_audio_track_for_extract`: applies the chosen track by its **ordinal among the audio
    tracks** (NOT raw `original_index`, which shifts with video/subtitle stream counts) — i.e. the
    Nth audio track of each file; files with fewer tracks are left untouched and counted in the
    status message. An earlier language+disposition matcher was scrapped as over-engineered.
  - **`ui/track_manager.py`**: `_serialize_audio_track` → public `serialize_audio_track` (reused by
    the batch matcher to serialize a matched track into the `audio_extract_track` dict; conversion
    already resolves that dict by `original_index` with a graceful fallback). i18n FR + EN/FR
    video-conversion docs ("Apply to several files at once").

- **Opt-in pre-releases (v1.18.0).** New Preferences checkbox
  `include_prereleases` (default **off**). When on, the update check considers GitHub
  **prereleases** (beta / rc) in addition to stable, so testers (Sèb) can opt into early builds
  from inside the app instead of installing them by hand.
  - **`core/updater.py`**: version comparison is now **prerelease-aware** (SemVer-style). New
    `parse_version_key()` returns `(release_tuple, stable_marker, prerelease_ids)` where a final
    release sorts **above** any prerelease of the same number (`1.17.0-rc2 < 1.17.0`), numeric
    prerelease ids compare numerically (`rc10 > rc2`). `is_release_newer()` uses it.
    `_extract_stable_releases` → `_extract_candidate_releases(payload, include_prereleases)` (drafts
    always excluded; prereleases excluded unless opted in). `parse_release_info` / `fetch_latest_release`
    gained `include_prereleases=False`; `parse_release_info` now picks the **highest version key** among
    candidates rather than trusting GitHub's publish order.
  - **CRITICAL process requirement** for the "stable arrives after a prerelease → offered as update"
    half: the **prerelease build must carry the suffix in `APP_VERSION`** (e.g. `APP_VERSION =
    "1.17.0-rc2"`), otherwise the installed rc reports `1.17.0` and the comparison can't tell it apart
    from the stable. `APP_VERSION_WIN` stays purely numeric (`1.17.0.0`) for the Windows file version.
    This also means a user can flip the toggle **off** after installing an rc and still get the matching
    stable (it's strictly newer), never a downgrade.
  - **Plumbing**: `core/formatting.py` default + normalization; `ui/preferences_dialog.py` checkbox;
    `ui/main_window.py` passes `include_prereleases` from `settings_store` to both `fetch_latest_release`
    call sites (`_update_check_worker`, the report-gate worker). i18n FR + EN/FR preferences docs.

- **v1.17.0 (encoding presets) — published 2026-06-26, tag `v1.17.0`.** First-class **encoding presets**
  (save / apply / replace / rename / delete / import / export), tester Sèb request. A preset is a snapshot
  poured back into the existing `settings_store` on apply — **no new conversion path**.
  - **`core/presets.py`** (new, no gettext): model + `presets.json` persistence in `%APPDATA%` (separate from
    `config.json`) + portable import/export. A preset = `{name, category, format, settings, output, metadata}`:
    output format, encoding settings, output destination (`output_mode`/`custom_output_path`/
    `preserve_folder_structure`), and a shared-tag **metadata template**. Reuses `normalize_format_settings`,
    the format-key tuples, `METADATA_TAG_KEYS`. `strip_export_fields(presets, include_output, include_metadata)`
    lets **export drop portability-sensitive blocks** (Sèb: the output path isn't relevant PC-to-PC; format +
    settings always kept).
  - **`ui/presets_dialog.py`** (new): `PresetsDialog` (list + manage buttons) + `_MetadataTemplateDialog`
    (reuses `AUDIO_BATCH_FIELDS` / `VIDEO_SERIES_BATCH_FIELDS`, no cover art; image has no metadata template) +
    `_ExportOptionsDialog` (checkboxes "include output" / "include metadata", both on by default, metadata box
    hidden for image).
  - **`ui/main_window.py`**: a **"Presets…"** button next to "Settings / Quality" **and** on the empty/start
    panel (reachable **with no file loaded**, e.g. to import — `_active_format_key()` falls back to
    `last_format_<tab>` when the format dropdown isn't populated yet), plus a **"Manage Presets…"** entry in the
    file-list **context menu** (every tab). Apply = `_apply_preset` pours format/settings/output back into
    `settings_store`; the metadata template goes onto loaded files via `_apply_preset_metadata`. **Scoping
    nuance (final Sèb point):** applied from the **context menu** the metadata template targets only the
    **selected files** (`target_indices` = `_resolve_metadata_target_indices`, mouse + keyboard); applied from
    the general **button** it targets **all loaded files**. Format/settings/output are global in both cases.
  - **Docs**: new `docs/{en,fr}/user/presets.html`, linked from both indexes. i18n FR complete.
  - **Pre-release history**: shipped as `v1.17.0-rc1` then `-rc2` (both `--prerelease`, invisible to the in-app
    updater) for Sèb to validate before this stable. Embedded FFmpeg unchanged (`2026-06-15-git-44d082edc8`).

- **v1.16.0 (preserve subfolder structure + 2 FFmpeg fixes) — published 2026-06-16, tag `v1.16.0`.**
  - **Feature (opt-in, off by default): preserve the original subfolder structure on output.** New
    Preferences checkbox `preserve_folder_structure`. When adding a folder that contains subfolders and
    converting to a **custom** output folder (modes `custom`/`ask`), the subfolder tree is recreated under
    the destination instead of flattening. No effect in `source` mode (already preserved) or on merge.
    Tester Sèb request. Plumbing: `core/probe.py` `MediaMetadata.relative_dir` (relpath vs the added root,
    "" for files added directly); `ui/main_window._collect_media_paths` now returns `(path, relative_dir)`
    tuples and `_process_added_files` sets it on meta; `build_output_path`/`build_cue_track_output_path`
    (`core/conversion.py`) take `relative_dir`, joined under the base dir only when a valid custom dir is in
    effect; `BatchConversionManager(preserve_structure=...)` (`core/batch_manager.py`) gates it via
    `_meta_relative_dir`, wired from `on_convert`. Subdirs auto-created by the existing `os.makedirs` in
    `ConversionTask.run`. i18n FR + EN/FR preferences docs.
  - **2 FFmpeg command bugs found by a full command audit and fixed** (commit `9c37209`; the audit verified
    all 40 command fragments against official docs — see [[reference_ffmpeg_command_audit]] in auto-memory):
    (1) **concat list apostrophe escaping** (`core/merge.py`) — the concat demuxer treats a single-quoted
    path as fully literal, so backslash-escaping did nothing; files like `O'Brien.mp3` broke the merge. Now
    uses the canonical `'\''` idiom. (2) **TIFF "uncompressed" emitted an invalid token** — FFmpeg's tiff
    encoder `-compression_algo` has no `none`; the uncompressed token is `raw`. Internal key changed `none`→
    `raw` in `core/conversion.py`, `core/formatting.py`, `ui/settings_dialog.py` (UI label "None" unchanged),
    with legacy `none`→`raw` migration in the normalizer.
  - **Embedded FFmpeg** bumped to `2026-06-15-git-44d082edc8`.

- **v1.15.0 (input format expansion) — published 2026-06-16, tag `v1.15.0`.** Broadened accepted **input**
  formats (tester Sèb request, started with `.mp2`, follow-up to the v1.14.0 MPEG-TS work).
  All additions verified decodable by the bundled FFmpeg before wiring.
  - **Audio**: `.mp2`, `.opus`, `.aiff`/`.aif`, `.ac3`, `.eac3`, `.dts`, `.mka`, `.amr`.
  - **Video**: `.mpg`/`.mpeg`, `.vob`, `.m4v`, `.3gp`/`.3g2`, `.flv`, `.ogv`.
  - **Image**: `.heic`/`.heif` (iPhone photos). HEIC is demuxed via the **mov family**
    (`mov,mp4,m4a,3gp,3g2,mj2`), carrying two HEVC image items (main + thumbnail); FFmpeg's
    default stream selection picks the full-res main image, so the existing
    `_build_image_command` path (`-i in … -an out`) converts it correctly with no special
    mapping. **Important**: image inputs are not routed by stream inspection like audio/video —
    they must also be added to `IMAGE_EXTENSIONS` in `core/probe.py._detect_image` (HEIC's
    container format name is not a `*_pipe`, so extension match is the reliable trigger).
  Audio/video additions are just one line each in `SUPPORTED_MEDIA_EXTENSIONS`
  (`ui/main_window.py`) — routing is automatic via the prober. Getting-started docs (EN/FR)
  updated. **MP2/AC3/DTS etc. output was deliberately not added** — no value for the app's
  audience (MP3/AAC/M4B beat them everywhere); only broadcast/legacy niches need them. If MP2
  output is ever needed, the bundled FFmpeg has the native `mp2` encoder (`-c:a mp2`, CBR);
  `libtwolame` is not in the build.
- **v1.15.0 (interactive announcements + startup modal sequencing).**
  Brings the announcement client to parity with Markdown Access / DownAccess; **no server
  change** (the backend already returned `link` and exposed `/api/announce/click`).
  **(1) Clickable links**: `core/announce.py` gains `CLICK_URL` + `click_announcement()`
  (fire-and-forget, mirrors `ack_announcement`). New `ui/announcement_dialog.py`
  (`AnnouncementDialog`) — accessible dialog (body in a read-only `wx.TextCtrl`, NVDA-read,
  focus on it; "Open link" button triggers `/click` then `webbrowser.open`; affirmative
  "Close"). `ui/main_window.py._on_announcement_received` now reads the nested
  `link: {label, url}` object: if `link.url` is present it shows `AnnouncementDialog` (with
  `on_link` → `click_announcement`), otherwise the existing `wx.MessageBox`. The `link` field
  was previously **ignored entirely**. Dedup (`mode: once` / `seen_announcements`), `install_id`
  and `ack` are unchanged. **(2) Modal sequencing**: the startup update check no longer races the
  announcement. `frame.schedule_startup_update_check()` was **removed from `main.py`** and is now
  chained in a `finally` inside `_on_announcement_received`, so the update check always fires —
  whether an announcement was shown, already seen, or absent — but **never before** the
  announcement modal closes (no two stacked modals). `schedule_startup_update_check()` itself
  (its `check_updates_on_startup` gate and `wx.CallLater(1200)`) is unchanged. i18n: "Announcement"
  / "Open link" added and translated to French.
- **v1.14.0 (MPEG-TS input)** — Accept the transport-stream family `.ts` / `.m2ts` / `.mts`
  as input (tester Sèb request). Added to `SUPPORTED_MEDIA_EXTENSIONS` (`ui/main_window.py`,
  the single source feeding the file dialog, drag-drop, paste, and the Explorer verb); audio/
  video routing is automatic via the prober's stream inspection, no per-extension code.
  Broadcast/TV captures often have missing PTS or non-monotonous DTS, so `-fflags +genpts` is
  injected **before** `-i` for TS-family inputs — in `ConversionTask` (single-file) and
  `MergeTask` (concat). The `-c copy` paths to MP4 need no manual bitstream filter: modern
  FFmpeg auto-inserts `aac_adtstoasc` / `h264_mp4toannexb` (autobsf). Shared helper
  `is_transport_stream` / `TRANSPORT_STREAM_EXTENSIONS` lives in `core/ffmpeg_helpers.py`.
  Docs updated (EN/FR getting-started). **Dependency management migrated to uv** this cycle
  (`pyproject.toml` + `uv.lock`, `.python-version` = 3.14; `requirements.txt` removed;
  `build_release.ps1` runs `uv sync --frozen`). Removed the stale `docs/codex-context.md`.
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
