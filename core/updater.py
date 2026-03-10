import json
import os
import subprocess
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib import error, request

from core.app_info import (
    APP_EXE_NAME,
    APP_GITHUB_RELEASES_API_LATEST,
    APP_GITHUB_RELEASES_PAGE,
    APP_INSTALLER_BASENAME,
    APP_VERSION,
)


UPDATES_DIRNAME = "updates"
UPDATER_STATE_FILENAME = "updater-state.json"
HTTP_TIMEOUT_SECONDS = 10
DOWNLOAD_CHUNK_SIZE = 1024 * 256


class UpdaterError(Exception):
    pass


class UpdateCheckError(UpdaterError):
    pass


class UpdateDownloadError(UpdaterError):
    pass


@dataclass(frozen=True)
class ReleaseInfo:
    tag_name: str
    version: str
    published_at: str
    html_url: str
    body: str
    asset_name: str
    asset_url: str


def get_local_appdata_dir():
    localappdata = os.getenv("LOCALAPPDATA")
    if localappdata:
        return Path(localappdata)
    return Path.home() / "AppData" / "Local"


def get_update_root_dir():
    return get_local_appdata_dir() / APP_EXE_NAME


def get_updates_dir():
    return get_update_root_dir() / UPDATES_DIRNAME


def ensure_updates_dir():
    updates_dir = get_updates_dir()
    updates_dir.mkdir(parents=True, exist_ok=True)
    return updates_dir


def get_updater_state_path():
    return get_update_root_dir() / UPDATER_STATE_FILENAME


def normalize_version(value):
    normalized = str(value or "").strip()
    if normalized.lower().startswith("v"):
        normalized = normalized[1:]
    return normalized


def parse_version_tuple(value):
    normalized = normalize_version(value)
    if not normalized:
        return tuple()

    parts = []
    for token in normalized.split("."):
        digits = []
        for char in token:
            if char.isdigit():
                digits.append(char)
            else:
                break
        if not digits:
            parts.append(0)
            continue
        parts.append(int("".join(digits)))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_release_newer(remote_version, current_version=APP_VERSION):
    return parse_version_tuple(remote_version) > parse_version_tuple(current_version)


def fetch_latest_release(timeout=HTTP_TIMEOUT_SECONDS):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{APP_EXE_NAME}/{APP_VERSION}",
    }
    api_request = request.Request(APP_GITHUB_RELEASES_API_LATEST, headers=headers)

    try:
        with request.urlopen(api_request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise UpdateCheckError(
            _("GitHub update check failed with HTTP status {code}.").format(code=exc.code)
        ) from exc
    except error.URLError as exc:
        raise UpdateCheckError(_("Unable to contact GitHub to check for updates.")) from exc
    except TimeoutError as exc:
        raise UpdateCheckError(_("The update check timed out.")) from exc
    except json.JSONDecodeError as exc:
        raise UpdateCheckError(_("GitHub returned an invalid update response.")) from exc

    return parse_release_info(payload)


def parse_release_info(payload):
    if not isinstance(payload, dict):
        raise UpdateCheckError(_("GitHub returned an invalid update response."))

    tag_name = str(payload.get("tag_name") or "").strip()
    version = normalize_version(tag_name)
    html_url = str(payload.get("html_url") or APP_GITHUB_RELEASES_PAGE).strip() or APP_GITHUB_RELEASES_PAGE
    body = normalize_release_notes(payload.get("body"))
    published_at = str(payload.get("published_at") or "").strip()
    asset_name, asset_url = find_setup_asset(payload.get("assets"))

    if not version:
        raise UpdateCheckError(_("The GitHub release does not define a valid version tag."))

    return ReleaseInfo(
        tag_name=tag_name,
        version=version,
        published_at=published_at,
        html_url=html_url,
        body=body,
        asset_name=asset_name,
        asset_url=asset_url,
    )


def normalize_release_notes(value):
    normalized = str(value or "").replace("\r\n", "\n").strip()
    if normalized:
        return normalized
    return _("No release notes provided.")


def format_release_date(value):
    if not value:
        return _("Unknown")

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


def find_setup_asset(assets):
    if not isinstance(assets, list):
        raise UpdateCheckError(_("No installer asset was found in the GitHub release."))

    prefix = f"{APP_INSTALLER_BASENAME}-"
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "").strip()
        if not name.startswith(prefix) or not name.lower().endswith(".exe"):
            continue

        download_url = str(asset.get("browser_download_url") or "").strip()
        if download_url:
            return name, download_url

    raise UpdateCheckError(_("No installer asset was found in the GitHub release."))


def download_release_installer(release_info, progress_callback=None, timeout=HTTP_TIMEOUT_SECONDS):
    if not isinstance(release_info, ReleaseInfo):
        raise UpdateDownloadError(_("Invalid update information."))

    updates_dir = ensure_updates_dir()
    final_path = updates_dir / release_info.asset_name
    partial_path = updates_dir / f"{release_info.asset_name}.part"

    if partial_path.exists():
        partial_path.unlink(missing_ok=True)

    headers = {"User-Agent": f"{APP_EXE_NAME}/{APP_VERSION}"}
    asset_request = request.Request(release_info.asset_url, headers=headers)

    try:
        with request.urlopen(asset_request, timeout=timeout) as response:
            total_size = int(response.headers.get("Content-Length", "0") or "0")
            downloaded = 0
            with open(partial_path, "wb") as handle:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback is not None:
                        progress_callback(downloaded, total_size)

        if final_path.exists():
            final_path.unlink()
        partial_path.replace(final_path)
        return final_path
    except error.HTTPError as exc:
        raise UpdateDownloadError(
            _("The installer download failed with HTTP status {code}.").format(code=exc.code)
        ) from exc
    except error.URLError as exc:
        raise UpdateDownloadError(_("Unable to download the installer from GitHub.")) from exc
    except TimeoutError as exc:
        raise UpdateDownloadError(_("The installer download timed out.")) from exc
    except OSError as exc:
        raise UpdateDownloadError(_("Unable to save the downloaded installer.")) from exc
    finally:
        if partial_path.exists():
            partial_path.unlink(missing_ok=True)


def load_updater_state():
    state_path = get_updater_state_path()
    if not state_path.exists():
        return {}

    try:
        with open(state_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def save_updater_state(installer_path, version, cleanup_pending=True):
    state_path = get_updater_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "downloaded_installer_path": str(Path(installer_path)),
        "downloaded_version": normalize_version(version),
        "cleanup_pending": bool(cleanup_pending),
    }
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4)
    return payload


def clear_updater_state():
    state_path = get_updater_state_path()
    if state_path.exists():
        state_path.unlink(missing_ok=True)


def cleanup_update_artifacts():
    updates_dir = get_updates_dir()
    state = load_updater_state()
    removed_paths = []
    keep_pending = False
    pending_installer = str(state.get("downloaded_installer_path") or "").strip()
    cleanup_pending = bool(state.get("cleanup_pending", False))

    if cleanup_pending and pending_installer:
        pending_path = Path(pending_installer)
        if pending_path.exists():
            try:
                pending_path.unlink()
                removed_paths.append(str(pending_path))
            except OSError:
                keep_pending = True
        else:
            removed_paths.append(str(pending_path))

    if updates_dir.exists():
        pattern = f"{APP_INSTALLER_BASENAME}-*.exe"
        for stale_path in updates_dir.glob(pattern):
            normalized_pending = os.path.normcase(pending_installer) if pending_installer else ""
            if normalized_pending and os.path.normcase(str(stale_path)) == normalized_pending:
                continue
            try:
                stale_path.unlink()
                removed_paths.append(str(stale_path))
            except OSError:
                continue

        for partial_path in updates_dir.glob("*.part"):
            try:
                partial_path.unlink()
                removed_paths.append(str(partial_path))
            except OSError:
                continue

    if keep_pending:
        save_updater_state(pending_installer, state.get("downloaded_version", ""), cleanup_pending=True)
    else:
        clear_updater_state()

    return removed_paths


def open_release_page(url):
    target = str(url or APP_GITHUB_RELEASES_PAGE).strip() or APP_GITHUB_RELEASES_PAGE
    if os.name == "nt":
        try:
            os.startfile(target)
            return target
        except OSError:
            pass

    if webbrowser.open(target, new=0):
        return target

    raise RuntimeError("Unable to open the release page.")


def launch_installer_after_exit(installer_path):
    resolved_path = str(Path(installer_path).resolve())
    if os.name != "nt":
        subprocess.Popen([resolved_path], close_fds=True)
        return resolved_path

    escaped_path = resolved_path.replace("'", "''")
    command = f"Start-Sleep -Milliseconds 800; Start-Process -FilePath '{escaped_path}'"
    kwargs = {"close_fds": True}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-Command",
            command,
        ],
        **kwargs,
    )
    return resolved_path
