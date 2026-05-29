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

2. **Bump version (two files, must match):**
   - `core/app_info.py`: set `APP_VERSION = "X.Y.Z"` and `APP_VERSION_WIN = "X.Y.Z.0"`.
   - `installer/UniversalTranscoder.iss` line 5: `#define AppVersion "X.Y.Z"`.

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
