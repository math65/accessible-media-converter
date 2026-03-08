import copy
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime


APP_DIR_NAME = "UniversalTranscoder"
DEBUG_DIR_NAME = "debug"
SESSION_STATE_FILENAME = "session-state.json"
DEBUG_LOG_FILENAME = "debug.log"
SESSION_STATE_SCHEMA_VERSION = 2

DEBUG_ENABLED_KEY = "debug_enabled"
DEBUG_RESTORE_PENDING_KEY = "debug_restore_pending"


def get_appdata_dir():
    appdata = os.getenv("APPDATA")
    if appdata:
        return appdata
    return os.path.expanduser("~")


def get_config_dir():
    return os.path.join(get_appdata_dir(), APP_DIR_NAME)


def ensure_config_dir():
    path = get_config_dir()
    os.makedirs(path, exist_ok=True)
    return path


def get_config_path():
    return os.path.join(get_config_dir(), "config.json")


def get_debug_dir():
    return os.path.join(get_config_dir(), DEBUG_DIR_NAME)


def ensure_debug_dir():
    path = get_debug_dir()
    os.makedirs(path, exist_ok=True)
    return path


def get_debug_log_path():
    return os.path.join(get_debug_dir(), DEBUG_LOG_FILENAME)


def get_session_state_path():
    return os.path.join(get_debug_dir(), SESSION_STATE_FILENAME)


def load_raw_config():
    config_path = get_config_path()
    if not os.path.exists(config_path):
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def save_raw_config(config_data):
    ensure_config_dir()
    with open(get_config_path(), "w", encoding="utf-8") as handle:
        json.dump(config_data, handle, indent=4)


def get_debug_flags(config_data=None):
    data = config_data if isinstance(config_data, dict) else load_raw_config()
    return {
        DEBUG_ENABLED_KEY: bool(data.get(DEBUG_ENABLED_KEY, False)),
        DEBUG_RESTORE_PENDING_KEY: bool(data.get(DEBUG_RESTORE_PENDING_KEY, False)),
    }


def update_debug_flags(config_data, enabled=None, restore_pending=None):
    updated = dict(config_data) if isinstance(config_data, dict) else {}
    if enabled is not None:
        updated[DEBUG_ENABLED_KEY] = bool(enabled)
    if restore_pending is not None:
        updated[DEBUG_RESTORE_PENDING_KEY] = bool(restore_pending)
    return updated


def build_session_snapshot(window):
    return {
        "schema_version": SESSION_STATE_SCHEMA_VERSION,
        "saved_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "current_tab": window.current_tab,
        "last_format_audio": window.settings_store.get("last_format_audio"),
        "last_format_video": window.settings_store.get("last_format_video"),
        "settings_store": copy.deepcopy(window.settings_store),
        "audio_files": _serialize_media_collection(window.audio_data),
        "video_files": _serialize_media_collection(window.video_data),
        "selected_indices_audio": _get_selected_indices(window.panel_audio_list.list_ctrl),
        "selected_indices_video": _get_selected_indices(window.panel_video_list.list_ctrl),
    }


def save_session_snapshot(window):
    ensure_debug_dir()
    snapshot = build_session_snapshot(window)
    with open(get_session_state_path(), "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=4)
    return snapshot


def load_session_snapshot():
    snapshot_path = get_session_state_path()
    if not os.path.exists(snapshot_path):
        return None

    try:
        with open(snapshot_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def clear_debug_artifacts():
    debug_dir = ensure_debug_dir()
    removed = []
    for entry in os.listdir(debug_dir):
        path = os.path.join(debug_dir, entry)
        if os.path.isdir(path):
            shutil.rmtree(path)
            removed.append(path)
        elif os.path.isfile(path):
            os.remove(path)
            removed.append(path)
    return removed


def open_debug_folder():
    debug_dir = ensure_debug_dir()
    subprocess.Popen(["explorer.exe", debug_dir])
    return debug_dir


def restart_application():
    args = _build_restart_command()
    kwargs = {"close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, **kwargs)
    return args


def _build_restart_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, *sys.argv[1:]]
    script_path = os.path.abspath(sys.argv[0])
    return [sys.executable, script_path, *sys.argv[1:]]


def _serialize_media_collection(media_collection):
    items = []
    for meta in media_collection:
        items.append(
            {
                "path": meta.full_path,
                "track_settings": copy.deepcopy(getattr(meta, "track_settings", None)),
                "audio_extract_track": copy.deepcopy(getattr(meta, "audio_extract_track", None)),
            }
        )
    return items


def _get_selected_indices(list_ctrl):
    selected = []
    index = list_ctrl.GetFirstSelected()
    while index != -1:
        selected.append(index)
        index = list_ctrl.GetNextSelected(index)
    return selected
