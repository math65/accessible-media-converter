import json
import os
import platform
import re
import sys
from urllib import error, request

from core.app_info import (
    APP_EXE_NAME,
    APP_NAME,
    APP_VERSION,
    SUPPORT_REPORT_API_URL,
)
from core.debug_session import get_debug_dir
from core.formatting import build_format_label
from core.i18n import get_current_language_code


SUPPORT_HTTP_TIMEOUT_SECONDS = 15
SUPPORT_ISSUE_TYPE_ITEMS = (
    ("conversion_problem", "Conversion problem"),
    ("application_crash", "Application crash"),
    ("update_problem", "Update problem"),
    ("accessibility_issue", "Accessibility issue"),
    ("installation_problem", "Installation problem"),
    ("feature_request", "Feature request"),
    ("other", "Other"),
)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SupportSendError(Exception):
    def __init__(self, error_code, message):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def get_support_issue_type_items():
    return tuple(SUPPORT_ISSUE_TYPE_ITEMS)


def get_support_issue_type_codes():
    return tuple(code for code, _ in SUPPORT_ISSUE_TYPE_ITEMS)


def build_support_issue_label(issue_type):
    labels = {code: _(msgid) for code, msgid in SUPPORT_ISSUE_TYPE_ITEMS}
    return labels.get(issue_type, _("Other"))


def collect_support_context(window):
    debug_dir = get_debug_dir()
    try:
        max_concurrent_jobs = int(window.settings_store.get("max_concurrent_jobs", 2))
    except (TypeError, ValueError):
        max_concurrent_jobs = 2

    return {
        "app_version": APP_VERSION,
        "execution_mode": "packaged" if getattr(sys, "frozen", False) else "source",
        "operating_system": f"{platform.system()} {platform.release()}".strip(),
        "language": get_current_language_code(),
        "current_tab": getattr(window, "current_tab", "audio"),
        "selected_output_format": _get_selected_format_label(window),
        "debug_mode_enabled": bool(window.settings_store.get("debug_enabled", False)),
        "debug_data_present": _has_debug_artifacts(debug_dir),
        "loaded_audio_files_count": len(getattr(window, "audio_data", []) or []),
        "loaded_video_files_count": len(getattr(window, "video_data", []) or []),
        "auto_update_check_enabled": bool(
            window.settings_store.get("check_updates_on_startup", True)
        ),
        "existing_output_policy": str(
            window.settings_store.get("existing_output_policy", "rename")
        ),
        "max_concurrent_jobs": max_concurrent_jobs,
        "ffmpeg_threads": window.settings_store.get("ffmpeg_threads", "auto"),
    }


def validate_support_email(email_address):
    return bool(EMAIL_PATTERN.match(str(email_address or "").strip()))


def validate_support_form(email_address, issue_type, user_message):
    if not validate_support_email(email_address):
        return _("Please enter a valid email address.")
    if issue_type not in get_support_issue_type_codes():
        return _("Please choose an issue type.")
    if not str(user_message or "").strip():
        return _("Please describe your issue before sending the report.")
    return ""


def build_support_subject(issue_type, context=None):
    context = context or {}
    version = str(context.get("app_version") or APP_VERSION)
    issue_label = build_support_issue_label(issue_type)
    return _("{app_name} - {issue} - v{version}").format(
        app_name=APP_NAME,
        issue=issue_label,
        version=version,
    )


def build_support_technical_block(context):
    lines = [
        _("App version: {value}").format(value=context.get("app_version", APP_VERSION)),
        _("Execution mode: {value}").format(
            value=_format_execution_mode(context.get("execution_mode", "source"))
        ),
        _("Operating system: {value}").format(
            value=context.get("operating_system", _("Unknown"))
        ),
        _("Language: {value}").format(value=context.get("language", _("Unknown"))),
        _("Current tab: {value}").format(
            value=_format_tab(context.get("current_tab", "audio"))
        ),
        _("Selected output format: {value}").format(
            value=context.get("selected_output_format") or _("Not selected")
        ),
        _("Debug mode: {value}").format(
            value=_format_bool(context.get("debug_mode_enabled", False))
        ),
        _("Debug data present: {value}").format(
            value=_format_bool(context.get("debug_data_present", False))
        ),
        _("Loaded audio files: {value}").format(
            value=context.get("loaded_audio_files_count", 0)
        ),
        _("Loaded video files: {value}").format(
            value=context.get("loaded_video_files_count", 0)
        ),
        _("Automatic update checks: {value}").format(
            value=_format_bool(context.get("auto_update_check_enabled", False))
        ),
        _("Existing output policy: {value}").format(
            value=_format_existing_output_policy(
                context.get("existing_output_policy", "rename")
            )
        ),
        _("Max concurrent conversions: {value}").format(
            value=context.get("max_concurrent_jobs", 0)
        ),
        _("FFmpeg threads: {value}").format(
            value=_format_ffmpeg_threads(context.get("ffmpeg_threads", "auto"))
        ),
    ]
    return "\n".join(lines)


def build_support_report(email_address, issue_type, user_message, context):
    message = str(user_message or "").strip() or _("Please describe your issue here.")
    return "\n".join(
        [
            _("Issue type: {value}").format(value=build_support_issue_label(issue_type)),
            _("User email: {value}").format(value=str(email_address or "").strip()),
            "",
            _("Your message:"),
            message,
            "",
            _("Technical information:"),
            build_support_technical_block(context),
        ]
    )


def send_support_report(email_address, issue_type, user_message, context, timeout=SUPPORT_HTTP_TIMEOUT_SECONDS):
    payload = {
        "email": str(email_address or "").strip(),
        "issue_type": issue_type,
        "message": str(user_message or "").strip(),
        "technical_context": dict(context or {}),
        "honeypot": "",
    }
    body = json.dumps(payload).encode("utf-8")
    api_request = request.Request(
        SUPPORT_REPORT_API_URL,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": f"{APP_EXE_NAME}/{APP_VERSION}",
        },
    )

    try:
        with request.urlopen(api_request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise _build_support_send_error(exc) from exc
    except error.URLError as exc:
        raise SupportSendError(
            "server_error",
            _("Unable to contact the support server right now."),
        ) from exc
    except TimeoutError as exc:
        raise SupportSendError(
            "server_error",
            _("The support request timed out."),
        ) from exc
    except json.JSONDecodeError as exc:
        raise SupportSendError(
            "server_error",
            _("The support server returned an invalid response."),
        ) from exc

    if not isinstance(response_payload, dict):
        raise SupportSendError(
            "server_error",
            _("The support server returned an invalid response."),
        )

    if response_payload.get("ok"):
        return response_payload

    raise SupportSendError(
        str(response_payload.get("error_code") or "server_error"),
        _map_support_error_message(
            str(response_payload.get("error_code") or "server_error"),
            str(response_payload.get("message") or ""),
        ),
    )


def _build_support_send_error(exc):
    message = _("Unable to send the support report right now.")
    error_code = "server_error"

    try:
        response_payload = json.loads(exc.read().decode("utf-8"))
    except Exception:
        response_payload = {}

    if isinstance(response_payload, dict):
        error_code = str(response_payload.get("error_code") or error_code)
        message = _map_support_error_message(
            error_code,
            str(response_payload.get("message") or ""),
        )
    elif getattr(exc, "code", 0) == 429:
        error_code = "rate_limited"
        message = _map_support_error_message(error_code, "")

    return SupportSendError(error_code, message)


def _map_support_error_message(error_code, fallback_message):
    mapping = {
        "validation_error": _("Please review the support form fields and try again."),
        "rate_limited": _("Too many reports have been sent recently. Please try again later."),
        "server_error": _("Unable to send the support report right now."),
    }
    return mapping.get(error_code) or fallback_message or mapping["server_error"]


def _format_execution_mode(value):
    return _("Packaged") if value == "packaged" else _("Source")


def _format_tab(value):
    return _("Video") if value == "video" else _("Audio")


def _format_bool(value):
    return _("Yes") if bool(value) else _("No")


def _format_existing_output_policy(value):
    labels = {
        "rename": _("Rename automatically"),
        "overwrite": _("Overwrite existing file"),
        "skip": _("Skip existing file"),
    }
    return labels.get(value, value)


def _format_ffmpeg_threads(value):
    if isinstance(value, str) and value.lower() == "auto":
        return _("Automatic")
    return str(value)


def _get_selected_format_label(window):
    combo = getattr(window, "combo_format", None)
    format_keys = getattr(window, "current_fmt_keys_active", None)
    current_tab = getattr(window, "current_tab", "audio")
    if combo is None or not format_keys:
        return ""

    selection = combo.GetSelection()
    if selection < 0 or selection >= len(format_keys):
        return ""

    return build_format_label(format_keys[selection], context=current_tab)


def _has_debug_artifacts(debug_dir):
    try:
        with os.scandir(debug_dir) as entries:
            for entry in entries:
                if entry.is_file() or entry.is_dir():
                    return True
    except OSError:
        return False
    return False
