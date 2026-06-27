---
name: release
description: Cut a new release of Accessible Media Converter — bump version, build the installer, and publish the GitHub release. Use when the user wants to ship a new version.
disable-model-invocation: true
---

# Release workflow

Target version comes from `$ARGUMENTS` (e.g. `1.9.4`). If empty, ask the user for it before doing anything.

Run every step from the project root. Stop and report if any step fails — never publish a half-built release.

## Steps

1. **Clean tree.** Run `git status --porcelain`. If non-empty, stop and ask the user to commit or stash first.

2. **Bump version (must agree across files):**
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
     - Publish it as a prerelease in step 6: `gh release create vX.Y.Z-rcN ... --prerelease`.
       A prerelease stays invisible to users who have **not** ticked
       "Also offer pre-release versions" in Preferences.

3. **Release notes (both languages required by the build):** create
   - `release-notes/vX.Y.Z.en.md`
   - `release-notes/vX.Y.Z.fr.md`

   Draft them from the commits since the last tag (`git log <last-tag>..HEAD --oneline`). Keep them user-facing and bilingual EN/FR. The build fails to combine notes if either file is missing.

4. **Build.** Run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
   ```
   This compiles `.po`→`.mo`, runs PyInstaller, runs Inno Setup, and writes `dist\release-notes.md`. Requires Inno Setup 6 installed.

   Expected outputs: `dist\AccessibleMediaConverter\AccessibleMediaConverter.exe` and `dist\AccessibleMediaConverter-Setup.exe`.

5. **Verify embedded FFmpeg** in the built app (not just `bin/`):
   ```powershell
   & ".\dist\AccessibleMediaConverter\_internal\bin\ffmpeg.exe" -version
   ```
   Confirm it's the version you intend to ship.

6. **Commit, tag, publish.** Commit the version bump + release notes, push, then:
   ```powershell
   gh release create vX.Y.Z .\dist\AccessibleMediaConverter-Setup.exe --title "vX.Y.Z" --notes-file .\dist\release-notes.md
   ```
   The updater only accepts the exact asset name `AccessibleMediaConverter-Setup.exe` — attach that single file, nothing else.

## Gotchas

- Updating `bin/` does **not** rebuild `dist/`. The build script handles this, but never publish an installer built before an FFmpeg update.
- `APP_VERSION` / `APP_VERSION_WIN` / `.iss AppVersion` must all agree, or the installer metadata mismatches the app.
- A beta/rc **must** carry its suffix in `APP_VERSION` (e.g. `1.18.0-rc1`) and `.iss AppVersion`, but **never** in `APP_VERSION_WIN` (numeric `X.Y.Z.0` only). Without the suffix in `APP_VERSION`, the prerelease-aware updater can't tell the rc from the final build, and testers stay stuck on the rc.
