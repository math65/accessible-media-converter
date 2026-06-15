"""Dialogue d'annonce avec bouton lien optionnel.

Utilisé quand l'annonce backend porte un `link_url`. Accessible : corps dans un
wx.TextCtrl lecture seule (lu par NVDA), focus dessus, bouton « Ouvrir le lien »
qui ouvre l'URL et déclenche le suivi /api/announce/click via on_link.
"""
import webbrowser

import wx


class AnnouncementDialog(wx.Dialog):
    def __init__(self, parent, title, body, link_label="", link_url="", on_link=None):
        super().__init__(
            parent,
            title=title or _("Announcement"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
            size=(520, 360),
        )
        self._link_url = link_url
        self._on_link = on_link  # callable() — déclenche /click côté backend
        self._build_ui(body, link_label)
        self.Centre()

    def _build_ui(self, body, link_label):
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.txt_body = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY,
            value=body, name=self.GetTitle())
        self.txt_body.SetMinSize((-1, 200))
        sizer.Add(self.txt_body, 1, wx.EXPAND | wx.ALL, 12)

        btns = wx.BoxSizer(wx.HORIZONTAL)
        if self._link_url:
            label = link_label or _("Open link")
            self.btn_link = wx.Button(self, label=label, name=label)
            self.btn_link.Bind(wx.EVT_BUTTON, self._on_open_link)
            btns.Add(self.btn_link, 0, wx.RIGHT, 8)
        self.btn_close = wx.Button(self, wx.ID_OK, label=_("Close"), name=_("Close"))
        btns.AddStretchSpacer()
        btns.Add(self.btn_close, 0)
        sizer.Add(btns, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(sizer)
        self.SetAffirmativeId(self.btn_close.GetId())
        wx.CallAfter(self.txt_body.SetFocus)

    def _on_open_link(self, _evt):
        if self._on_link:
            try:
                self._on_link()
            except Exception:
                pass
        try:
            webbrowser.open(self._link_url)
        except Exception:
            pass
