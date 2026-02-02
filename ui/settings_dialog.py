import wx

class SettingsDialog(wx.Dialog):
    def __init__(self, parent, format_label, has_video, input_audio_codec, current_settings):
        super().__init__(parent, title=_("Configure settings for: ") + format_label, size=(550, 520))
        
        self.has_video = has_video
        self.settings = current_settings
        
        # Valeurs actuelles
        self.audio_mode = self.settings.get('audio_mode', 'convert')
        self.video_mode = self.settings.get('video_mode', 'convert')
        
        self._init_ui()
        self.Centre()

    def _init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # --- SECTION VIDÉO ---
        if self.has_video:
            sb_vid = wx.StaticBox(panel, label=_("Video Settings"))
            sb_vid_sizer = wx.StaticBoxSizer(sb_vid, wx.VERTICAL)
            
            # Choix Mode Vidéo
            self.rb_vid_convert = wx.RadioButton(sb_vid_sizer.GetStaticBox(), label=_("Re-encode (Recommended)"), style=wx.RB_GROUP)
            self.rb_vid_copy = wx.RadioButton(sb_vid_sizer.GetStaticBox(), label=_("Copy Stream (Advanced)"))
            self.rb_vid_copy.SetToolTip(_("Keep original quality and speed up conversion.\nWarning: The output format must support the source codec."))
            
            sb_vid_sizer.Add(self.rb_vid_convert, 0, wx.ALL, 5)
            
            # --- Sous-section conversion vidéo ---
            self.vid_params_sizer = wx.BoxSizer(wx.VERTICAL)
            
            # Slider CRF
            row_crf = wx.BoxSizer(wx.HORIZONTAL)
            
            # CORRECTION : On met juste le préfixe ici
            self.lbl_quality = wx.StaticText(sb_vid_sizer.GetStaticBox(), label=_("Quality (CRF):"), size=(220, -1))
            
            self.slider_crf = wx.Slider(sb_vid_sizer.GetStaticBox(), value=23, minValue=18, maxValue=35, size=(250, -1))
            self.slider_crf.Bind(wx.EVT_SLIDER, self.on_crf_change)
            
            row_crf.Add(self.lbl_quality, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
            row_crf.Add(self.slider_crf, 1, wx.EXPAND)
            
            self.vid_params_sizer.Add(row_crf, 0, wx.EXPAND | wx.LEFT, 20)
            sb_vid_sizer.Add(self.vid_params_sizer, 0, wx.EXPAND | wx.ALL, 5)
            
            sb_vid_sizer.Add(self.rb_vid_copy, 0, wx.ALL, 5)
            vbox.Add(sb_vid_sizer, 0, wx.EXPAND | wx.ALL, 10)
            
            # Events Vidéo
            self.Bind(wx.EVT_RADIOBUTTON, self.on_vid_mode_change, self.rb_vid_convert)
            self.Bind(wx.EVT_RADIOBUTTON, self.on_vid_mode_change, self.rb_vid_copy)

        # --- SECTION AUDIO ---
        sb_aud = wx.StaticBox(panel, label=_("Audio Settings"))
        sb_aud_sizer = wx.StaticBoxSizer(sb_aud, wx.VERTICAL)
        
        # Choix Mode Audio
        self.rb_aud_convert = wx.RadioButton(sb_aud_sizer.GetStaticBox(), label=_("Re-encode (Recommended)"), style=wx.RB_GROUP)
        self.rb_aud_copy = wx.RadioButton(sb_aud_sizer.GetStaticBox(), label=_("Copy Stream (Advanced)"))
        
        sb_aud_sizer.Add(self.rb_aud_convert, 0, wx.ALL, 5)
        
        # --- Sous-section conversion audio ---
        self.aud_params_sizer = wx.BoxSizer(wx.VERTICAL)
        
        hbox_bitrate = wx.BoxSizer(wx.HORIZONTAL)
        lbl_bitrate = wx.StaticText(sb_aud_sizer.GetStaticBox(), label=_("Bitrate:"))
        self.combo_bitrate = wx.Choice(sb_aud_sizer.GetStaticBox(), choices=["64k", "128k", "192k", "256k", "320k"])
        
        hbox_bitrate.Add(lbl_bitrate, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        hbox_bitrate.Add(self.combo_bitrate, 1, wx.EXPAND)
        
        self.aud_params_sizer.Add(hbox_bitrate, 0, wx.EXPAND | wx.LEFT, 20)
        sb_aud_sizer.Add(self.aud_params_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        sb_aud_sizer.Add(self.rb_aud_copy, 0, wx.ALL, 5)
        vbox.Add(sb_aud_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Events Audio
        self.Bind(wx.EVT_RADIOBUTTON, self.on_aud_mode_change, self.rb_aud_convert)
        self.Bind(wx.EVT_RADIOBUTTON, self.on_aud_mode_change, self.rb_aud_copy)

        # Boutons OK/Cancel
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(panel, wx.ID_OK, label=_("OK"))
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, label=_("Cancel"))
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        panel.SetSizer(vbox)
        vbox.Fit(self)
        
        # --- CHARGEMENT DES VALEURS INITIALES ---
        
        # 1. Vidéo
        if self.has_video:
            saved_crf = self.settings.get('video_crf', 23)
            self.slider_crf.SetValue(saved_crf)
            
            if self.video_mode == 'copy':
                self.rb_vid_copy.SetValue(True)
            else:
                self.rb_vid_convert.SetValue(True)
                
            # IMPORTANT : On appelle la fonction pour mettre à jour le texte immédiatement
            self.on_crf_change(None)
            self.on_vid_mode_change(None) 

        # 2. Audio
        saved_bitrate = self.settings.get('audio_bitrate', '192k')
        idx = self.combo_bitrate.FindString(saved_bitrate)
        if idx != wx.NOT_FOUND: self.combo_bitrate.SetSelection(idx)
        else: self.combo_bitrate.SetSelection(2) 
        
        if self.audio_mode == 'copy':
            self.rb_aud_copy.SetValue(True)
        else:
            self.rb_aud_convert.SetValue(True)
        self.on_aud_mode_change(None)

    # --- LOGIQUE UI ---

    def on_crf_change(self, event):
        val = self.slider_crf.GetValue()
        
        # On reconstruit la phrase complète dynamiquement
        prefix = _("Quality (CRF):")
        
        desc = ""
        if val < 20: desc = _("High Quality (V2)")
        elif val < 26: desc = _("Balanced")
        else: desc = _("Small Size")
        
        self.lbl_quality.SetLabel(f"{prefix} {val} ({desc})")

    def on_vid_mode_change(self, event):
        is_convert = self.rb_vid_convert.GetValue()
        self.slider_crf.Enable(is_convert)
        self.lbl_quality.Enable(is_convert)

    def on_aud_mode_change(self, event):
        is_convert = self.rb_aud_convert.GetValue()
        self.combo_bitrate.Enable(is_convert)

    def get_settings(self):
        summary_parts = []
        
        # VIDEO
        if self.has_video:
            v_mode = 'copy' if self.rb_vid_copy.GetValue() else 'convert'
            if v_mode == 'copy':
                summary_parts.append("Video: Copy")
            else:
                crf = self.slider_crf.GetValue()
                summary_parts.append(f"H.264 CRF {crf}")
        else:
            v_mode = 'convert'

        # AUDIO
        a_mode = 'copy' if self.rb_aud_copy.GetValue() else 'convert'
        bitrate = self.combo_bitrate.GetStringSelection()
        
        if a_mode == 'copy':
            summary_parts.append("Audio: Copy")
        else:
            summary_parts.append(f"AAC {bitrate}")

        return {
            'video_mode': v_mode,
            'video_crf': self.slider_crf.GetValue() if self.has_video else 23,
            
            'audio_mode': a_mode,
            'rate_mode': 'cbr',
            'audio_bitrate': bitrate,
            
            'summary': " / ".join(summary_parts)
        }