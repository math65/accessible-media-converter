"""
Automatic error reporting: verbose FFmpeg re-run and report payload construction.
"""
import os
import shutil
import subprocess
import tempfile

from core.app_info import APP_VERSION
from core.logger import read_log_tail
from core.support import collect_support_context, send_support_report

VERBOSE_RERUN_TIMEOUT = 30
# Extrait de stderr conservé dans le corps du rapport. On garde la TÊTE autant
# que la queue : l'en-tête `Input #0 ... from '<chemin>'` et le détail des flux
# sont en tête, et une source à sept flux les repoussait au-delà des 50
# dernières lignes — le chemin du fichier source disparaissait du rapport.
STDERR_HEAD_LINES = 30
STDERR_TAIL_LINES = 50


def rerun_ffmpeg_verbose(original_cmd, timeout=VERBOSE_RERUN_TIMEOUT):
    """Re-run the failed FFmpeg command with -loglevel verbose and capture stderr.

    Returns the captured stderr output as a string.
    """
    if not original_cmd:
        return "[No FFmpeg command available for diagnostic re-run]"

    cmd = list(original_cmd)
    cmd.insert(1, '-loglevel')
    cmd.insert(2, 'verbose')

    # Le diagnostic ne doit RIEN écrire chez l'utilisateur. La commande d'origine
    # porte `-y` et se termine par le chemin de sortie : relancée telle quelle,
    # elle réécrasait le fichier de l'utilisateur — y compris une sortie valide
    # produite depuis. On redirige vers un fichier temporaire, supprimé ensuite.
    temp_dir = None
    if len(cmd) > 1 and not str(cmd[-1]).startswith('-'):
        try:
            temp_dir = tempfile.mkdtemp(prefix='amc-diagnostic-')
            extension = os.path.splitext(str(cmd[-1]))[1] or '.tmp'
            cmd[-1] = os.path.join(temp_dir, 'diagnostic' + extension)
        except OSError:
            temp_dir = None

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            timeout=timeout,
            encoding='utf-8',
            errors='ignore',
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.stderr or ""
    except subprocess.TimeoutExpired as exc:
        captured = ""
        if exc.stderr:
            captured = exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode('utf-8', errors='ignore')
        return captured + f"\n[Diagnostic timed out after {timeout} seconds]"
    except Exception as exc:
        return f"[Diagnostic re-run failed: {exc}]"
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def summarize_ffmpeg_stderr(lines, head_lines=STDERR_HEAD_LINES, tail_lines=STDERR_TAIL_LINES):
    """Extrait lisible de la sortie FFmpeg : la tête ET la queue.

    La tête porte l'en-tête d'entrée (chemin source, liste des flux), la queue
    porte l'erreur. Ne garder que la queue faisait perdre le chemin du fichier
    en cause dès que la source avait beaucoup de flux.
    """
    if not lines:
        return ""
    if isinstance(lines, str):
        lines = lines.splitlines()
    lines = list(lines)
    if len(lines) <= head_lines + tail_lines:
        return "\n".join(lines)
    omitted = len(lines) - head_lines - tail_lines
    return "\n".join(
        lines[:head_lines]
        + [f"[... {omitted} lignes omises ...]"]
        + lines[-tail_lines:]
    )


def _drop_stderr_echo(error_message, ffmpeg_stderr):
    """Retire de l'erreur applicative la queue de stderr qu'elle recopie.

    `ConversionTask` lève ses exceptions en collant le tail de FFmpeg au message,
    si bien que le rapport affichait deux fois la même sortie : une fois sous
    « Application error message », une fois sous « FFmpeg error output ».
    """
    if not (error_message or "").strip() or not (ffmpeg_stderr or "").strip():
        return error_message
    known = {line.strip() for line in ffmpeg_stderr.splitlines() if line.strip()}
    kept = error_message.splitlines()
    while kept and (not kept[-1].strip() or kept[-1].strip() in known):
        kept.pop()
    return "\n".join(kept).strip() or error_message.strip()


def build_error_report_message(input_path, target_format, ffmpeg_stderr, user_comment="",
                               error_message=""):
    """Build the user-facing message body for the error report.

    error_message carries the failure as the app saw it. It is the only usable
    clue when the job never reached FFmpeg (missing cue image, no video track
    kept, truncated output…), where ffmpeg_stderr is empty.
    """
    filename = os.path.basename(input_path) if input_path else "unknown"
    lines = [
        f"Automatic error report — conversion failure",
        f"File: {filename}",
        f"Target format: {target_format}",
    ]
    error_message = _drop_stderr_echo(error_message or "", ffmpeg_stderr or "")
    if error_message and error_message.strip():
        lines.extend(["", "Application error message:", error_message.strip()])
    lines.extend([
        "",
        "FFmpeg error output:",
        ffmpeg_stderr or "(no output captured)",
    ])
    if user_comment and user_comment.strip():
        lines.extend(["", "User comment:", user_comment.strip()])
    return "\n".join(lines)


def send_error_report(
    email,
    input_path,
    target_format,
    ffmpeg_stderr,
    verbose_log,
    user_comment,
    support_context,
    error_message="",
):
    """Send the error report using the existing support report API.

    Raises SupportSendError on failure.
    """
    message = build_error_report_message(
        input_path, target_format, ffmpeg_stderr, user_comment, error_message
    )
    send_support_report(
        email_address=email,
        issue_type="conversion_problem",
        user_message=message,
        context=support_context,
        debug_log=build_debug_log_attachment(verbose_log),
    )


def build_debug_log_attachment(verbose_log=""):
    """Pièce jointe du rapport : re-passe verbeuse + journal de l'application.

    Le service n'accepte qu'un seul fichier ; on concatène. Le journal apporte
    ce que la re-passe ne peut pas donner : ce qui s'est passé AVANT l'échec —
    notamment les durées par piste relevées au chargement de chaque fichier.
    """
    parts = []
    if (verbose_log or "").strip():
        parts.append("=== Re-passe FFmpeg verbeuse ===\n" + verbose_log.strip())
    app_log = read_log_tail()
    if app_log.strip():
        parts.append("=== Journal de l'application ===\n" + app_log.strip())
    return "\n\n".join(parts)
