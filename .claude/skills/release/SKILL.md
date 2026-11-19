---
name: release
description: Cut a new release of Accessible Media Converter — optionally refresh the pinned FFmpeg, bump version, write release notes, then build and publish through the GitHub Actions workflow (dry run first, NVDA test, then publish). Use when the user wants to ship a new version.
disable-model-invocation: true
---

# Release workflow

Target version comes from `$ARGUMENTS` (e.g. `1.20.7`). If empty, ask the user for it before doing anything.

Run every step from the project root. Stop and report if any step fails — never publish a half-built release.

Building and publishing happen on **GitHub Actions** (`.github/workflows/release.yml`,
"Publier une version"): a clean Windows runner, locked dependencies, the pinned FFmpeg,
the full test suite as a hard gate. The local `build_release.ps1` path is kept as a
fallback (see the end).

## Steps

1. **Clean tree, on master.** Run `git status --porcelain` and `git branch --show-current`.
   If the tree is dirty, stop and ask the user to commit or stash first. The workflow only
   publishes from `master`.

2. **Decide on FFmpeg.** Which FFmpeg ships is fixed by `scripts/ffmpeg_release.json`
   (GyanD tag + archive SHA256), **not** by whatever is newest: CI installs exactly that
   with `-Pinned`. Check whether a newer GyanD build exists (downloads nothing):
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\update_embedded_ffmpeg.ps1 -CheckOnly
   ```
   - **`already matches` / `is newer than`** → nothing to do. Say so plainly and move on.
   - **An update is available** → read the tag it names. GyanD's newest is often a **git
     snapshot** (`2026-11-19-git-01ca75d350`) rather than a stable (`9.0.2`); the app has
     shipped stables since 8.1.2. Ask the user which one they want before changing it:
     - newest: `update_embedded_ffmpeg.ps1` (no argument);
     - a specific stable: `update_embedded_ffmpeg.ps1 -Tag 9.0.3`.

     Both install into `bin/` (SHA256 verified, automatic rollback on failure) **and rewrite
     `scripts/ffmpeg_release.json`**. Then run the test suite — it converts into every output
     format the app offers, which is exactly what catches a codec or option removed upstream:
     ```powershell
     .venv\Scripts\python.exe -m unittest discover -s tests -t .
     ```
     Commit `scripts/ffmpeg_release.json` with the release (step 5) and mention the bump, with
     the exact tag, in the release notes. `bin/*.exe` themselves are **not** git-tracked
     (over GitHub's 100 MB limit) — never `git add -f` them.
   - **An error** → the script has already restored the previous binaries and left the pin
     file alone. Report the *actual* error. A download/API failure or a `hash mismatch` is
     usually transient — retry, and never bypass the hash check.

   Worth re-checking while you are here: the embedded libmp3lame is still **LAME 3.100**
   even though LAME 4.0 shipped upstream in July 2026. Nothing to do on our side — it
   depends on GyanD rebuilding against it.

3. **Bump version (must agree across files — the workflow refuses otherwise):**
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
     - The workflow publishes any version with a `-` suffix as a **prerelease**
       (`--prerelease`), invisible to users who have **not** ticked
       "Also offer pre-release versions" in Preferences.

4. **Release notes (both languages required to publish):** create
   - `release-notes/vX.Y.Z.en.md`
   - `release-notes/vX.Y.Z.fr.md`

   Draft them from the commits since the last tag (`git log <last-tag>..HEAD --oneline`). Keep them user-facing and bilingual EN/FR. The workflow refuses to publish if either is missing or empty.

5. **Commit and push** the version bump, release notes (and `scripts/ffmpeg_release.json`
   if step 2 changed it) to `master`. Ask before pushing.

6. **Dry run.** Build without publishing:
   ```powershell
   gh workflow run release.yml --ref master -f version=X.Y.Z -f publier=false
   gh run watch (gh run list --workflow release.yml --limit 1 --json databaseId --jq '.[0].databaseId')
   ```
   The run checks the version against the code, installs the pinned FFmpeg, runs the
   **full test suite** (a single failure stops everything), builds with
   `scripts/build_release.ps1` (Inno Setup 6.7.1), and checks that
   `dist\AccessibleMediaConverter\_internal\bin\ffmpeg.exe`/`ffprobe.exe` are byte-identical
   to `bin\` and carry the pinned tag. A dry run only *warns* about a taken tag or missing
   notes; it fails on a version mismatch.

   Then download the installer for the user to test with NVDA:
   ```powershell
   gh run download <run-id> --name AccessibleMediaConverter-Setup-X.Y.Z --dir "$env:USERPROFILE\Downloads\AMC-X.Y.Z-essai"
   ```
   (`AccessibleMediaConverter-Setup.exe` + its `.sha256` + `release-notes.md`; kept 14 days).
   **Wait for the user's go** after their NVDA test before publishing.

7. **Publish.** Same command with the box ticked:
   ```powershell
   gh workflow run release.yml --ref master -f version=X.Y.Z -f publier=true
   ```
   On top of the dry-run steps it refuses unless the tag `vX.Y.Z` is free on origin (no
   release, draft included) and both release notes exist, then runs
   `gh release create vX.Y.Z dist/AccessibleMediaConverter-Setup.exe --title vX.Y.Z --notes-file dist/release-notes.md --target <built commit>`.
   The updater only accepts the exact asset name `AccessibleMediaConverter-Setup.exe` and
   verifies the SHA-256 digest GitHub computes for it — a single asset, nothing else.
   Report the release URL printed at the end of the run.

## Local fallback (no GitHub Actions)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_embedded_ffmpeg.ps1 -Pinned
.venv\Scripts\python.exe -m unittest discover -s tests -t .
.venv\Scripts\python.exe scripts\ci_release_check.py X.Y.Z --publish
powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
& ".\dist\AccessibleMediaConverter\_internal\bin\ffmpeg.exe" -version
gh release create vX.Y.Z .\dist\AccessibleMediaConverter-Setup.exe --title "vX.Y.Z" --notes-file .\dist\release-notes.md
```
Requires Inno Setup 6 installed (user scope is fine). Add `--prerelease` for an rc.

## Gotchas

- `gh workflow run` needs the workflow file on the default branch (`master`). A push to a
  `claude/**` branch that touches packaging files triggers a dry run on its own (version =
  `APP_VERSION`), which is how to test workflow changes before merging them.
- The workflow never commits: the version bump and notes must already be on master.
- Updating `bin/` does **not** rebuild `dist/`, and does not change what CI ships until
  `scripts/ffmpeg_release.json` is committed.
- `bin/ffmpeg.exe` / `bin/ffprobe.exe` are **not** git-tracked since v1.20.6 (each is over GitHub's 100 MB limit, which rejects the whole push). Never `git add -f` them. A fresh clone gets them from `scripts\update_embedded_ffmpeg.ps1 -Pinned`, and the build refuses to start without them.
- `APP_VERSION` / `APP_VERSION_WIN` / `.iss AppVersion` must all agree — `scripts/ci_release_check.py` enforces it.
- A beta/rc **must** carry its suffix in `APP_VERSION` (e.g. `1.18.0-rc1`) and `.iss AppVersion`, but **never** in `APP_VERSION_WIN` (numeric `X.Y.Z.0` only). Without the suffix in `APP_VERSION`, the prerelease-aware updater can't tell the rc from the final build, and testers stay stuck on the rc.
- Actions are pinned by commit SHA and Inno Setup by version (6.7.1): to bump one, change the SHA/version **and** its comment, then dry-run.
