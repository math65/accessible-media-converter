---
name: update-ffmpeg
description: Update the embedded FFmpeg/ffprobe binaries in bin/ to the latest GyanD build. Use when the user wants to refresh the bundled FFmpeg.
disable-model-invocation: true
---

# Update embedded FFmpeg

Updates the git-tracked `bin/ffmpeg.exe` and `bin/ffprobe.exe`.

1. **Check current vs. available** (optional but recommended):
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\update_embedded_ffmpeg.ps1 -CheckOnly
   ```
   The script reads the full release list from `GyanD/codexffmpeg` (not `releases/latest`, which may lag).

2. **Update:**
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\update_embedded_ffmpeg.ps1
   ```

3. **Report** the new version (`& .\bin\ffmpeg.exe -version`) to the user.

## Important

- `bin/ffmpeg.exe` / `bin/ffprobe.exe` are git-tracked despite being in `.gitignore`; GitHub warns on push due to size. This is expected.
- Updating `bin/` does **not** update `dist/`. A full release rebuild (`/release`) is required before publishing so the shipped app carries the new FFmpeg.
