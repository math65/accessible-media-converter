import logging

import wx

from core.app_info import SUPPORT_EMAIL
from core.debug_session import open_debug_folder
from core.support import (
    build_support_message,
    build_support_subject,
    build_support_technical_block,
    collect_support_context,
    open_support_mail_client,
)


class SupportContactDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title=_("Contact Support"), size=(640, 360))
        self.SetName(_("Contact Support"))

        self.parent_window = parent
        self.contact_email = SUPPORT_EMAIL
        self.subject = build_support_subject()
        self.support_context = collect_support_context(parent)

        self._init_ui()
        self._refresh_message_preview()
        self.Centre()

    def _init_ui(self):
        panel = wx.Panel(self)
        self.root = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            panel,
            label=_(
                "Describe your issue below. Your mail client will open with the message already prepared."
            ),
        )
        intro.Wrap(560)
        self.root.Add(intro, 0, wx.EXPAND | wx.ALL, 12)

        hint = wx.StaticText(
            panel,
            label=_("You will only need to review the email and send it."),
        )
        hint.Wrap(560)
        self.root.Add(hint, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        message_box = wx.StaticBoxSizer(wx.VERTICAL, panel, _("Your message"))
        self.txt_user_message = wx.TextCtrl(panel, style=wx.TE_MULTILINE)
        self.txt_user_message.SetMinSize((-1, 130))
        self.txt_user_message.SetName(_("Your message"))
        self.txt_user_message.SetToolTip(_("Describe the problem you encountered."))
        message_box.Add(self.txt_user_message, 1, wx.EXPAND | wx.ALL, 8)
        self.root.Add(message_box, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.lbl_feedback = wx.StaticText(panel, label="")
        self.lbl_feedback.Wrap(560)
        self.lbl_feedback.Hide()
        self.root.Add(self.lbl_feedback, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.fallback_panel = wx.Panel(panel)
        fallback_root = wx.BoxSizer(wx.VERTICAL)

        fallback_intro = wx.StaticText(
            self.fallback_panel,
            label=_(
                "If the mail client did not open, copy the information below and send it manually."
            ),
        )
        fallback_intro.Wrap(560)
        fallback_root.Add(fallback_intro, 0, wx.EXPAND | wx.ALL, 8)

        details_box = wx.StaticBoxSizer(wx.VERTICAL, self.fallback_panel, _("Mail details"))
        details_grid = wx.FlexGridSizer(cols=3, vgap=8, hgap=8)
        details_grid.AddGrowableCol(1, 1)

        lbl_address = wx.StaticText(self.fallback_panel, label=_("Contact address"))
        self.txt_address = wx.TextCtrl(self.fallback_panel, value=self.contact_email, style=wx.TE_READONLY)
        self.txt_address.SetName(_("Contact address"))
        self.txt_address.SetToolTip(_("Support email address to copy."))
        self.btn_copy_address = wx.Button(self.fallback_panel, label=_("Copy address"))
        self.btn_copy_address.SetName(_("Copy address"))

        lbl_subject = wx.StaticText(self.fallback_panel, label=_("Subject"))
        self.txt_subject = wx.TextCtrl(self.fallback_panel, value=self.subject, style=wx.TE_READONLY)
        self.txt_subject.SetName(_("Subject"))
        self.txt_subject.SetToolTip(_("Support email subject to copy."))
        self.btn_copy_subject = wx.Button(self.fallback_panel, label=_("Copy subject"))
        self.btn_copy_subject.SetName(_("Copy subject"))

        details_grid.Add(lbl_address, 0, wx.ALIGN_CENTER_VERTICAL)
        details_grid.Add(self.txt_address, 1, wx.EXPAND)
        details_grid.Add(self.btn_copy_address, 0)
        details_grid.Add(lbl_subject, 0, wx.ALIGN_CENTER_VERTICAL)
        details_grid.Add(self.txt_subject, 1, wx.EXPAND)
        details_grid.Add(self.btn_copy_subject, 0)
        details_box.Add(details_grid, 0, wx.EXPAND | wx.ALL, 8)
        fallback_root.Add(details_box, 0, wx.EXPAND | wx.BOTTOM, 12)

        self.txt_technical_info = wx.TextCtrl(
            self.fallback_panel,
            value=build_support_technical_block(self.support_context),
            style=wx.TE_MULTILINE | wx.TE_READONLY,
        )
        self.txt_technical_info.SetMinSize((-1, 160))
        self.txt_technical_info.SetName(_("Technical information"))
        self.txt_technical_info.SetToolTip(_("Technical information included in the support message."))
        technical_box = wx.StaticBoxSizer(wx.VERTICAL, self.fallback_panel, _("Technical information"))
        technical_box.Add(self.txt_technical_info, 1, wx.EXPAND | wx.ALL, 8)
        fallback_root.Add(technical_box, 1, wx.EXPAND | wx.BOTTOM, 12)

        self.txt_message_preview = wx.TextCtrl(
            self.fallback_panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
        )
        self.txt_message_preview.SetMinSize((-1, 170))
        self.txt_message_preview.SetName(_("Message preview"))
        self.txt_message_preview.SetToolTip(
            _("Full support message that can be copied manually if needed.")
        )
        preview_box = wx.StaticBoxSizer(wx.VERTICAL, self.fallback_panel, _("Message preview"))
        preview_box.Add(self.txt_message_preview, 1, wx.EXPAND | wx.ALL, 8)
        fallback_root.Add(preview_box, 1, wx.EXPAND | wx.BOTTOM, 12)

        preview_actions = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_copy_message = wx.Button(self.fallback_panel, label=_("Copy full message"))
        self.btn_copy_message.SetName(_("Copy full message"))
        preview_actions.Add(self.btn_copy_message, 0)
        preview_actions.AddStretchSpacer()
        self.btn_open_debug = wx.Button(self.fallback_panel, label=_("Open Debug Folder"))
        self.btn_open_debug.SetName(_("Open Debug Folder"))
        self.btn_open_debug.SetToolTip(_("Open the debug folder in File Explorer."))
        preview_actions.Add(self.btn_open_debug, 0)
        fallback_root.Add(preview_actions, 0, wx.EXPAND)

        self.fallback_panel.SetSizer(fallback_root)
        self.fallback_panel.Hide()
        self.root.Add(self.fallback_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        actions = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_open_mail = wx.Button(panel, label=_("Open Mail Client"))
        self.btn_open_mail.SetName(_("Open Mail Client"))
        self.btn_open_mail.SetToolTip(
            _("Open the default mail client with the prepared message.")
        )
        self.btn_open_mail.SetDefault()
        self.btn_close = wx.Button(panel, wx.ID_CLOSE, label=_("Close"))
        self.btn_close.SetName(_("Close"))

        actions.AddStretchSpacer()
        actions.Add(self.btn_open_mail, 0, wx.RIGHT, 8)
        actions.Add(self.btn_close, 0)
        self.root.Add(actions, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        panel.SetSizer(self.root)
        self.SetEscapeId(self.btn_close.GetId())

        self.Bind(wx.EVT_TEXT, self.on_message_changed, self.txt_user_message)
        self.Bind(wx.EVT_BUTTON, self.on_copy_address, self.btn_copy_address)
        self.Bind(wx.EVT_BUTTON, self.on_copy_subject, self.btn_copy_subject)
        self.Bind(wx.EVT_BUTTON, self.on_copy_message, self.btn_copy_message)
        self.Bind(wx.EVT_BUTTON, self.on_open_debug_folder, self.btn_open_debug)
        self.Bind(wx.EVT_BUTTON, self.on_open_mail_client, self.btn_open_mail)
        self.Bind(wx.EVT_BUTTON, self.on_close, self.btn_close)

        self.txt_user_message.SetFocus()

    def _refresh_message_preview(self):
        self.txt_message_preview.SetValue(
            build_support_message(self.txt_user_message.GetValue(), self.support_context)
        )

    def _set_feedback(self, message, is_error=False):
        self.lbl_feedback.SetLabel(message)
        self.lbl_feedback.SetForegroundColour(
            wx.Colour(180, 0, 0) if is_error else wx.Colour(0, 120, 0)
        )
        self.lbl_feedback.Show()
        self.Layout()

    def _show_fallback_details(self):
        self.fallback_panel.Show()
        self.SetMinSize((760, 720))
        self.SetSize((760, 720))
        self.Layout()
        self.FitInside()

    def _copy_text(self, text, success_message):
        if not wx.TheClipboard.Open():
            self._set_feedback(_("Unable to copy to the clipboard."), is_error=True)
            return

        try:
            text_data = wx.TextDataObject()
            text_data.SetText(text)
            wx.TheClipboard.SetData(text_data)
        finally:
            wx.TheClipboard.Close()

        self._set_feedback(success_message)

    def on_message_changed(self, event):
        self._refresh_message_preview()
        event.Skip()

    def on_copy_address(self, event):
        self._copy_text(self.contact_email, _("Support email address copied to clipboard."))

    def on_copy_subject(self, event):
        self._copy_text(self.subject, _("Support email subject copied to clipboard."))

    def on_copy_message(self, event):
        self._copy_text(
            self.txt_message_preview.GetValue(),
            _("Support message copied to clipboard."),
        )

    def on_open_debug_folder(self, event):
        try:
            open_debug_folder()
            self._set_feedback(_("Debug folder opened."))
        except Exception:
            logging.exception("Unable to open the debug folder from support dialog.")
            self._set_feedback(_("Unable to open the debug folder."), is_error=True)

    def on_open_mail_client(self, event):
        try:
            open_support_mail_client(
                self.contact_email,
                self.subject,
                self.txt_message_preview.GetValue(),
            )
            self.EndModal(wx.ID_OK)
        except Exception:
            logging.exception("Unable to open the default mail client.")
            self._show_fallback_details()
            self._set_feedback(
                _("Unable to open the default mail client. Copy the address, subject, and message below."),
                is_error=True,
            )

    def on_close(self, event):
        self.EndModal(wx.ID_CLOSE)
