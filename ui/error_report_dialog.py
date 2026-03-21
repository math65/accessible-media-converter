"""
Modeless dialog shown automatically when a conversion fails.
Asks the user if they want to send an error report.
"""
import logging
import os
import threading

import wx

from core.error_report import rerun_ffmpeg_verbose, send_error_report
from core.support import (
    collect_support_context,
    validate_support_email,
    SupportSendError,
)


class ErrorReportDialog(wx.Dialog):
    def __init__(self, parent, job_payload, settings_store):
        self._input_path = job_payload.get('input_path', '')
        self._target_format = job_payload.get('target_format', '')
        self._ffmpeg_command = job_payload.get('ffmpeg_command', [])
        self._ffmpeg_stderr = job_payload.get('ffmpeg_stderr', '')
        self._settings_store = settings_store
        self._parent_window = parent
        self._send_in_progress = False

        filename = os.path.basename(self._input_path) if self._input_path else _("Unknown file")
        title = _("Conversion Error")

        super().__init__(parent, title=title, size=(480, 300),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetName(title)

        self._init_ui(filename)
        self.Centre()
        self.Show()

    def _init_ui(self, filename):
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)

        question = wx.StaticText(
            panel,
            label=_(
                "The conversion of {filename} to {format} failed.\n"
                "Would you like to send an error report to support?"
            ).format(filename=filename, format=self._target_format.upper()),
        )
        question.Wrap(420)
        root.Add(question, 0, wx.EXPAND | wx.ALL, 16)

        form_grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        form_grid.AddGrowableCol(1, 1)

        lbl_email = wx.StaticText(panel, label=_("Your email"))
        self.txt_email = wx.TextCtrl(panel)
        self.txt_email.SetName(_("Your email"))
        self.txt_email.SetToolTip(_("Enter the email address that support should reply to."))
        saved_email = str(self._settings_store.get("support_user_email", "") or "")
        if saved_email:
            self.txt_email.SetValue(saved_email)

        lbl_comment = wx.StaticText(panel, label=_("Comment (optional)"))
        self.txt_comment = wx.TextCtrl(panel, style=wx.TE_MULTILINE)
        self.txt_comment.SetMinSize((-1, 50))
        self.txt_comment.SetName(_("Comment (optional)"))
        self.txt_comment.SetToolTip(_("Optionally describe what you were doing when the error occurred."))

        form_grid.Add(lbl_email, 0, wx.ALIGN_CENTER_VERTICAL)
        form_grid.Add(self.txt_email, 1, wx.EXPAND)
        form_grid.Add(lbl_comment, 0, wx.ALIGN_TOP | wx.TOP, 4)
        form_grid.Add(self.txt_comment, 1, wx.EXPAND)
        root.Add(form_grid, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.lbl_feedback = wx.StaticText(panel, label="")
        self.lbl_feedback.Wrap(420)
        self.lbl_feedback.Hide()
        root.Add(self.lbl_feedback, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        actions = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_yes = wx.Button(panel, label=_("Yes, send report"))
        self.btn_yes.SetName(_("Yes, send report"))
        self.btn_yes.SetToolTip(_("Run a diagnostic and send an error report to support."))
        self.btn_yes.SetDefault()
        self.btn_no = wx.Button(panel, wx.ID_CANCEL, label=_("No"))
        self.btn_no.SetName(_("No"))
        actions.AddStretchSpacer()
        actions.Add(self.btn_yes, 0, wx.RIGHT, 8)
        actions.Add(self.btn_no, 0)
        root.Add(actions, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        panel.SetSizer(root)

        self.btn_yes.Bind(wx.EVT_BUTTON, self._on_yes)
        self.btn_no.Bind(wx.EVT_BUTTON, self._on_no)
        self.Bind(wx.EVT_CLOSE, self._on_close_window)

        if saved_email:
            wx.CallAfter(self.txt_comment.SetFocus)
        else:
            wx.CallAfter(self.txt_email.SetFocus)

    def _set_feedback(self, message, is_error=False):
        self.lbl_feedback.SetLabel(message)
        self.lbl_feedback.SetForegroundColour(wx.RED if is_error else wx.Colour(0, 128, 0))
        self.lbl_feedback.Show()
        self.Layout()
        wx.CallAfter(self.lbl_feedback.SetFocus)

    def _set_send_state(self, sending):
        self._send_in_progress = sending
        self.txt_email.Enable(not sending)
        self.txt_comment.Enable(not sending)
        self.btn_yes.Enable(not sending)
        self.btn_no.Enable(not sending)
        self.Layout()

    def _on_yes(self, event):
        email = self.txt_email.GetValue().strip()
        if not validate_support_email(email):
            self._set_feedback(_("Please enter a valid email address."), is_error=True)
            self.txt_email.SetFocus()
            return

        self._settings_store["support_user_email"] = email
        self._set_send_state(True)
        self._set_feedback(_("Running diagnostic and sending report..."))

        user_comment = self.txt_comment.GetValue()
        threading.Thread(
            target=self._send_worker,
            args=(email, user_comment),
            daemon=True,
        ).start()

    def _send_worker(self, email, user_comment):
        try:
            verbose_log = rerun_ffmpeg_verbose(self._ffmpeg_command)
            support_context = collect_support_context(self._parent_window)
            send_error_report(
                email=email,
                input_path=self._input_path,
                target_format=self._target_format,
                ffmpeg_stderr=self._ffmpeg_stderr,
                verbose_log=verbose_log,
                user_comment=user_comment,
                support_context=support_context,
            )
        except SupportSendError as exc:
            wx.CallAfter(self._on_send_failure, exc.message)
            return
        except Exception as exc:
            logging.exception("Unable to send the error report.")
            wx.CallAfter(self._on_send_failure, str(exc))
            return

        wx.CallAfter(self._on_send_success)

    def _on_send_success(self):
        self._set_send_state(False)
        self._set_feedback(_("Your report has been sent successfully."))
        wx.CallLater(1500, self._close_if_alive)

    def _on_send_failure(self, message):
        self._set_send_state(False)
        self._set_feedback(
            message or _("Unable to send the error report right now."),
            is_error=True,
        )

    def _close_if_alive(self):
        if self and self.IsShown():
            self.Destroy()

    def _on_no(self, event):
        if not self._send_in_progress:
            self.Destroy()

    def _on_close_window(self, event):
        if self._send_in_progress:
            self._set_feedback(_("Please wait for the report to finish sending."), is_error=True)
            event.Veto()
            return
        self.Destroy()
