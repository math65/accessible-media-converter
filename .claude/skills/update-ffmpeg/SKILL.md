---
name: update-ffmpeg
description: Update the embedded FFmpeg/ffprobe binaries in bin/ to the latest GyanD build. Use when the user wants to refresh the bundled FFmpeg.
disable-model-invocation: true
---

# Update embedded FFmpeg

Refreshes the git-tracked `bin/ffmpeg.exe` and `bin/ffprobe.exe` to the latest
GyanD `essentials_build`. The PowerShell script does the heavy lifting — your job
is to run it, read the outcome correctly, and guide what comes next.

## Run it

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_embedded_ffmpeg.ps1
```

The script is self-checking and safe to run directly: it compares the embedded
version against the GitHub release list (full list from `GyanD/codexffmpeg`, not
`releases/latest`, which can lag), downloads the archive, verifies its SHA256
digest, backs up the current binaries, swaps them in, and rolls back automatically
if anything goes wrong. If the embedded build is already current, it exits without
touching any file.

To check *without* installing — just see whether a newer build exists — add
`-CheckOnly`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_embedded_ffmpeg.ps1 -CheckOnly
```

This is cheap: the GyanD release **tag** is the exact build version, so the script
reads it from the GitHub API and compares it to the embedded binary without
downloading anything (~80 MB saved). Use it freely for a dry run. When you actually
want to install, run the plain command above — no need to run `-CheckOnly` first.

## Read the outcome

Match the script's final lines, not just its exit code:

- **`Embedded FFmpeg binaries updated successfully.`** → an update happened. Go to
  *After a successful update*.
- **`already matches` / `is newer than`** → nothing changed; the embedded build is
  already up to date. Report that plainly and stop — there is nothing to commit and
  no release to cut. Don't invent follow-up work.
- **The script threw an error** → go to *If it fails*.

Then confirm what actually landed on disk:

```powershell
& .\bin\ffmpeg.exe -version | Select-Object -First 1
git status --short bin/
```

After a real update, `bin/ffmpeg.exe` and `bin/ffprobe.exe` show as modified. After
a no-op, `git status` is clean.

## After a successful update

`bin/` now carries the new FFmpeg, but `dist/` does **not** — the shipped app only
picks it up on a full rebuild. So two things remain, and they're the user's call:

1. **Commit.** The project convention (see git history) is:
   ```
   chore: update embedded FFmpeg to <version-token>
   ```
   where `<version-token>` is the exact build string, e.g.
   `2026-05-28-git-7b46c6a2a3`. Take it from the `ffmpeg -version` first line.
2. **Publish.** Mention that `/release` rebuilds `dist/` and bundles this FFmpeg bump
   into the installer.

Ask whether to commit the `bin/` change now or go straight to `/release` (which will
include the bump). Don't push or publish unless asked.

## If it fails

The script is defensive: on a copy or verification failure it restores the previous
binaries from backup, so `bin/` is never left half-updated. Report the *actual*
error and what it means, rather than a generic failure:

- **GitHub API / download error** → usually transient (network, rate limit).
  Suggest a retry.
- **`hash mismatch`** → the downloaded archive was corrupted or tampered with. The
  script refuses it on purpose; don't bypass — just retry.
- **`Binary not found`** → `bin/ffmpeg.exe` or `bin/ffprobe.exe` is missing from the
  repo, so there's no current version to compare against. Investigate before forcing
  an install.

After any failure, confirm the working tree is intact with `git status --short bin/`
— it should be clean if the update didn't complete.

## Important

- `bin/ffmpeg.exe` / `bin/ffprobe.exe` are git-tracked despite matching `.gitignore`;
  GitHub warns on push because of their size. This is expected, not a problem.
