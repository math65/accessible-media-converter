# Accessible Media Converter

Accessible Media Converter is a Windows desktop transcoding tool built with `wxPython` and powered by `FFmpeg`.

The project is designed with accessibility and keyboard-driven workflows in mind, while still offering enough control for real-world media conversion tasks such as audio extraction, multi-track video handling, stream copy, loudness normalization, and batch processing.

## Highlights

- Accessible desktop UI for Windows
- Audio-to-audio and video-to-audio conversion
- Video-to-video conversion for `MP4` and `MKV`
- Explicit track selection for video, audio, and subtitles
- Audio extraction track selection for multi-audio video files
- Batch conversion with configurable parallel jobs
- Optional streaming normalization at `-16 LUFS`
- Debug mode with session snapshot and user-facing debug folder
- Built-in support contact flow
- PHP support-report backend for direct email delivery
- Installer-based Windows release pipeline

## Supported formats

Input support depends on `FFmpeg` / `ffprobe`, but the application currently targets common formats such as:

- Audio: `MP3`, `WAV`, `FLAC`, `AAC`, `OGG`, `WMA`, `M4A`
- Video: `MP4`, `MKV`, `AVI`, `MOV`, `WMV`, `WEBM`

Current output formats:

- Audio: `MP3`, `AAC`, `WAV`, `FLAC`, `ALAC`, `OGG`, `WMA`
- Video: `MP4`, `MKV`

## Main features

- Format-specific settings with persisted summaries
- Audio mode: re-encode or stream copy
- Video mode: H.264 re-encode or stream copy
- Video CRF presets
- Streaming loudness normalization toggle
- Per-file track management for video outputs
- Per-file audio extraction choice for video-to-audio outputs
- Clipboard import with `Ctrl+V`
- Select all with `Ctrl+A`
- Preferences shortcut with `Ctrl+,`
- Parallel conversions with output conflict handling

## Requirements

- Windows 10 or Windows 11
- Python `3.14` recommended for source development
- `FFmpeg` and `ffprobe` binaries available in `bin/`

Python dependency declared in the repository:

- `wxPython>=4.2.1`

Additional tools used for development and packaging:

- `polib`
- `PyInstaller`
- `Inno Setup 6`

## Run from source

1. Create and activate a virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
pip install pyinstaller polib
```

3. Place `ffmpeg.exe` and `ffprobe.exe` in the `bin/` folder.
4. Launch the application:

```powershell
python main.py
```

## Build a release

The repository includes a Windows release script that:

- compiles translations
- builds the PyInstaller app folder
- generates Windows version metadata
- builds the Inno Setup installer

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
```

Expected outputs:

- `dist\AccessibleMediaConverter\AccessibleMediaConverter.exe`
- `dist\AccessibleMediaConverter-Setup-<version>.exe`

## Project layout

- [`main.py`](main.py): application entry point
- [`core/`](core): probing, conversion, formatting, debug, support, batch logic
- [`ui/`](ui): main window and dialogs
- [`server/`](server): PHP support-report backend
- [`installer/`](installer): Inno Setup installer
- [`scripts/`](scripts): release build tooling

## Configuration and debug data

The installed application stores user data outside the application folder:

- configuration: `%APPDATA%\AccessibleMediaConverter`
- debug data: `%APPDATA%\AccessibleMediaConverter\debug`

This means upgrades do not wipe user preferences or debug artifacts by default.

## Accessibility focus

This project is built with accessibility as a core goal, not as an afterthought. Current efforts include:

- keyboard-friendly workflows
- NVDA-oriented control naming and navigation improvements
- explicit menu shortcuts
- simplified support and debug flows for end users

## Support

Support contact address:

- `contact@mathieumartin.ovh`

## Status

Current public version in the repository metadata:

- `1.5.1`
