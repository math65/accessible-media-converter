import os
import platform
import sys
import webbrowser
from urllib.parse import quote

from core.app_info import APP_NAME, APP_VERSION, SUPPORT_EMAIL
from core.debug_session import get_debug_dir
from core.formatting import build_format_label
from core.i18n import get_current_language_code, get_current_language_source


def collect_support_context(window):
    debug_dir = get_debug_dir()
    selected_format = _get_selected_format_label(window)
    language_code = get_current_language_code()
    language_source = get_current_language_source()
    if language_source and language_source != "fallback":
        language_value = f"{language_code} ({language_source})"
    else:
        language_value = language_code

    return {
        "app_version": APP_VERSION,
        "execution_mode": _("Packaged") if getattr(sys, "frozen", False) else _("Source"),
        "operating_system": f"{platform.system()} {platform.release()}".strip(),
        "python_version": sys.version.split(" (")[0],
        "language": language_value,
        "current_tab": _("Video") if getattr(window, "current_tab", "audio") == "video" else _("Audio"),
        "selected_output_format": selected_format or _("Not selected"),
        "debug_mode": _("Enabled") if bool(window.settings_store.get("debug_enabled", False)) else _("Disabled"),
        "debug_data_present": _("Yes") if _has_debug_artifacts(debug_dir) else _("No"),
        "debug_folder": debug_dir,
    }


def build_support_subject():
    return _("{app_name} support request").format(app_name=APP_NAME)


def build_support_technical_block(context):
    lines = [
        _("App version: {value}").format(value=context["app_version"]),
        _("Execution mode: {value}").format(value=context["execution_mode"]),
        _("Operating system: {value}").format(value=context["operating_system"]),
        _("Python version: {value}").format(value=context["python_version"]),
        _("Language: {value}").format(value=context["language"]),
        _("Current tab: {value}").format(value=context["current_tab"]),
        _("Selected output format: {value}").format(value=context["selected_output_format"]),
        _("Debug mode: {value}").format(value=context["debug_mode"]),
        _("Debug data present: {value}").format(value=context["debug_data_present"]),
        _("Debug folder: {value}").format(value=context["debug_folder"]),
    ]
    return "\n".join(lines)


def build_support_message(user_message, context):
    message = (user_message or "").strip()
    if not message:
        message = _("Please describe your issue here.")

    return "\n".join(
        [
            _("Your message:"),
            message,
            "",
            _("Technical information:"),
            build_support_technical_block(context),
        ]
    )


def build_mailto_url(email_address, subject, body):
    normalized_body = body.replace("\r\n", "\n").replace("\n", "\r\n")
    return f"mailto:{quote(email_address)}?subject={quote(subject)}&body={quote(normalized_body)}"


def open_support_mail_client(email_address, subject, body):
    mailto_url = build_mailto_url(email_address, subject, body)

    if os.name == "nt":
        try:
            os.startfile(mailto_url)
            return mailto_url
        except OSError:
            pass

    if webbrowser.open(mailto_url, new=0):
        return mailto_url

    raise RuntimeError("Unable to open the default mail client.")


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
    if not os.path.isdir(debug_dir):
        return False

    with os.scandir(debug_dir) as entries:
        for entry in entries:
            if entry.is_file() or entry.is_dir():
                return True
    return False
