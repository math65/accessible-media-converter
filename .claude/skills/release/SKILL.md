---
name: release
description: Cut a new release of Accessible Media Converter — refresh the embedded FFmpeg, bump version, build the installer, and publish the GitHub release. Use when the user wants to ship a new version.
disable-model-invocation: true
---

# Release workflow

Target version comes from `$ARGUMENTS` (e.g. `1.9.4`). If empty, ask the user for it before doing anything.

Run every step from the project root. Stop and report if any step fails — never publish a half-built release.

## Steps

1. **Clean tree.** Run `git status --porcelain`. If non-empty, stop and ask the user to commit or stash first.

2. **Refresh the embedded FFmpeg.** Every release should ship the current binaries, and
   `bin/` is the only place they live:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\update_embedded_ffmpeg.ps1
   ```
   The script is self-checking and safe to run directly: it compares the embedded build
   against the **full** GyanD release list (not `releases/latest`, which can lag),
   downloads the archive, verifies its SHA256, backs up the current binaries, swaps them
   in, and rolls back automatically if anything goes wrong.

   Read its **final line**, not just the exit code:

   - **`Embedded FFmpeg binaries updated successfully.`** → `bin/` changed. Two things follow.
     First run the test suite *before* building — it converts into every output format the
     app offers, which is exactly what catches a codec or option removed upstream:
     ```powershell
     .venv\Scripts\python.exe -m unittest discover -s tests -t .
     ```
     Then commit the binaries on their own, taking the exact build token from the first
     line of `& .\bin\ffmpeg.exe -version`:
     ```
     chore: update embedded FFmpeg to <version-token>
     ```
     (e.g. `chore: update embedded FFmpeg to 9.0.1`.) Mention the bump in the release notes
     written at step 4.
   - **`already matches` / `is newer than`** → nothing changed, `bin/` stays clean. Say so
     plainly and move on; don't invent follow-up work.
   - **An error** → the script has already restored the previous binaries. Confirm with
     `git status --short bin/` (it should be clean) and report the *actual* error. A
     download/API failure or a `hash mismatch` is usually transient — retry, and never
     bypass the hash check. `Binary not found` means `bin/ffmpeg.exe` or `bin/ffprobe.exe`
     is missing from the repo: investigate before forcing an install.

   Add `-CheckOnly` for a dry run that downloads nothing (~80 MB saved) — the GyanD release
   tag *is* the exact build version, so the comparison needs API metadata alone.

   Worth re-checking while you are here: the embedded libmp3lame is still **LAME 3.100**
   even though LAME 4.0 shipped upstream in July 2026. Nothing to do on our side — it
   depends on GyanD rebuilding against it.

3. **Bump version (must agree across files):**
   - `core/app_info.py`: set `APP_VERSION` and `APP_VERSION_WIN`.
   - `installer/UniversalTranscoder.iss` line 5: `#define AppVersion "..."`.

   Pick the form that matches what you are shipping:

   - **Stable `X.Y.Z`:** `APP_VERSION = "X.Y.Z"`, `APP_VERSION_WIN = "X.Y.Z.0"`,
     `.iss AppVersion "X.Y.Z"`.

   - **Pre-release / beta `X.Y.Z-rcN` (or `-betaN`):**
     - `APP_VERSION = "X.Y.Z-rcN"` — **the suffix is required.** The in-app updater's
       comparison is prerelease-aware (`X.Y.Z-rc1 < X.Y.Z`), so an installed rc must
       report its suffix; otherwise it is indistinguishable from the final `X.Y.Z` and
       the "stable supersedes my rc" auto-update will never fire. (See the
       `include_prereleases` preference / `core/updater.parse_version_key`.)
     - `APP_VERSION_WIN = "X.Y.Z.0"` — **must stay purely numeric** (Windows
       file-version fields reject `-rcN`). It does not encode the prerelease; that's fine.
     - `.iss AppVersion "X.Y.Z-rcN"` — keep the suffix so the installed/uninstall entry
       reads as a beta.
     - Publish it as a prerelease in step 7: `gh release create vX.Y.Z-rcN ... --prerelease`.
       A prerelease stays invisible to users who have **not** ticked
       "Also offer pre-release versions" in Preferences.

4. **Release notes (both languages required by the build):** create
   - `release-notes/vX.Y.Z.en.md`
   - `release-notes/vX.Y.Z.fr.md`

   Draft them from the commits since the last tag (`git log <last-tag>..HEAD --oneline`). Keep them user-facing and bilingual EN/FR. The build fails to combine notes if either file is missing.

5. **Build.** Run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
   ```
   This compiles `.po`→`.mo`, runs PyInstaller, runs Inno Setup, and writes `dist\release-notes.md`. Requires Inno Setup 6 installed.

   Expected outputs: `dist\AccessibleMediaConverter\AccessibleMediaConverter.exe` and `dist\AccessibleMediaConverter-Setup.exe`.

6. **Verify embedded FFmpeg** in the built app (not just `bin/`):
   ```powershell
   & ".\dist\AccessibleMediaConverter\_internal\bin\ffmpeg.exe" -version
   ```
   Confirm it matches what step 2 left in `bin/`. This is the check that catches a `dist/`
   built before the FFmpeg refresh.

7. **Commit, tag, publish.** Commit the version bump + release notes, push, then:
   ```powershell
   gh release create vX.Y.Z .\dist\AccessibleMediaConverter-Setup.exe --title "vX.Y.Z" --notes-file .\dist\release-notes.md
   ```
   The updater only accepts the exact asset name `AccessibleMediaConverter-Setup.exe` — attach that single file, nothing else.

## Gotchas

- Updating `bin/` does **not** rebuild `dist/`. The build script handles this, but never publish an installer built before an FFmpeg update — hence the ordering above (step 2 before step 5) and the verification at step 6.
- `bin/ffmpeg.exe` / `bin/ffprobe.exe` are git-tracked despite matching `.gitignore`; GitHub warns on push because of their size. That is expected, not a problem.
- `APP_VERSION` / `APP_VERSION_WIN` / `.iss AppVersion` must all agree, or the installer metadata mismatches the app.
- A beta/rc **must** carry its suffix in `APP_VERSION` (e.g. `1.18.0-rc1`) and `.iss AppVersion`, but **never** in `APP_VERSION_WIN` (numeric `X.Y.Z.0` only). Without the suffix in `APP_VERSION`, the prerelease-aware updater can't tell the rc from the final build, and testers stay stuck on the rc.
