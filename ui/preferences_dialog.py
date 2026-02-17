import wx

class PreferencesDialog(wx.Dialog):
    def __init__(self, parent, current_settings):
        super().__init__(parent, title=_("Preferences"), size=(500, 300))
        self.SetName(_("Preferences dialog"))
        
        self.settings = current_settings
        self.mode = self.settings.get('output_mode', 'source') # source, custom, ask
        self.custom_path = self.settings.get('custom_output_path', '')

        self._init_ui()
        self.Centre()

    def _init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Section Destination
        sb = wx.StaticBox(panel, label=_("Output Destination"))
        sb_sizer = wx.StaticBoxSizer(sb, wx.VERTICAL)
        
        # Option 1 : Source (Modifié : on a retiré "(Default)")
        self.rb_source = wx.RadioButton(panel, label=_("Same as source file"), style=wx.RB_GROUP)
        self.rb_source.SetName(_("Output in source folder"))
        sb_sizer.Add(self.rb_source, 0, wx.ALL, 5)
        
        # Option 2 : Dossier Spécifique
        self.rb_custom = wx.RadioButton(panel, label=_("Specific folder:"))
        self.rb_custom.SetName(_("Output in specific folder"))
        sb_sizer.Add(self.rb_custom, 0, wx.TOP | wx.LEFT, 5)
        
        # Ligne pour le chemin + bouton parcourir
        hbox_custom = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_path = wx.TextCtrl(panel, value=self.custom_path)
        self.btn_browse = wx.Button(panel, label=_("Browse..."))
        self.txt_path.SetName(_("Custom output folder path"))
        self.btn_browse.SetName(_("Browse output folder"))
        self.txt_path.SetToolTip(_("Type or paste the destination folder path."))
        
        hbox_custom.Add(self.txt_path, 1, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 5)
        hbox_custom.Add(self.btn_browse, 0, wx.ALIGN_CENTER_VERTICAL)
        sb_sizer.Add(hbox_custom, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 20)
        
        # Option 3 : Demander à chaque fois
        self.rb_ask = wx.RadioButton(panel, label=_("Ask every time (Batch)"))
        self.rb_ask.SetName(_("Ask output folder each time"))
        sb_sizer.Add(self.rb_ask, 0, wx.ALL, 5)
        
        vbox.Add(sb_sizer, 0, wx.EXPAND | wx.ALL, 15)
        
        # Boutons OK/Annuler (Modifié : on force les labels traduits)
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(panel, wx.ID_OK, label=_("OK")) 
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, label=_("Cancel"))
        btn_ok.SetName(_("Save preferences"))
        btn_cancel.SetName(_("Cancel preferences"))
        
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        
        vbox.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 15)
        
        panel.SetSizer(vbox)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        
        # Events
        self.Bind(wx.EVT_BUTTON, self.on_browse, self.btn_browse)
        self.Bind(wx.EVT_RADIOBUTTON, self.on_radio_change, self.rb_source)
        self.Bind(wx.EVT_RADIOBUTTON, self.on_radio_change, self.rb_custom)
        self.Bind(wx.EVT_RADIOBUTTON, self.on_radio_change, self.rb_ask)
        
        # Initial State
        if self.mode == 'custom':
            self.rb_custom.SetValue(True)
        elif self.mode == 'ask':
            self.rb_ask.SetValue(True)
        else:
            self.rb_source.SetValue(True)
            
        self._update_controls()

    def _update_controls(self):
        is_custom = self.rb_custom.GetValue()
        self.txt_path.Enable(is_custom)
        self.btn_browse.Enable(is_custom)

    def on_radio_change(self, event):
        self._update_controls()
        if self.rb_custom.GetValue():
            self.txt_path.SetFocus()
            wx.CallAfter(self.txt_path.SetFocus)

    def on_browse(self, event):
        with wx.DirDialog(self, _("Select Output Folder"), style=wx.DD_DEFAULT_STYLE) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.txt_path.SetValue(dlg.GetPath())

    def get_settings(self):
        if self.rb_source.GetValue(): mode = 'source'
        elif self.rb_custom.GetValue(): mode = 'custom'
        else: mode = 'ask'
        
        return {
            'output_mode': mode,
            'custom_output_path': self.txt_path.GetValue()
        }
