import wx

class SettingsDialog(wx.Dialog):
    def __init__(self, parent, format_label, input_has_video, input_audio_codec, current_settings=None):
        super().__init__(parent, title=_("Conversion Settings"), size=(500, 500))
        
        self.format_label = format_label
        self.target_fmt = format_label.split(" ")[0].lower()
        self.input_audio_codec = input_audio_codec
        self.saved_settings = current_settings or {}
        
        # On définit les choix ici pour qu'ils soient traduisibles
        self.choices_cbr = [
            _("64k (Voice)"), 
            _("128k (Radio)"), 
            _("192k (Standard)"), 
            _("256k (High)"), 
            _("320k (Max)")
        ]
        
        self.choices_vbr = [
            _("Best Quality (V0)"), 
            _("High Quality (V2)"), 
            _("Medium Quality (V4)"),
            _("Standard Quality (V6)")
        ]
        
        self._init_ui()
        self._load_previous_settings()
        self.Centre()

    def _init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl_info = wx.StaticText(panel, label=_("Configure settings for: ") + self.format_label)
        lbl_info.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(lbl_info, 0, wx.ALL, 15)

        # --- Section Audio ---
        sb_audio = wx.StaticBoxSizer(wx.VERTICAL, panel, label=_("Audio Settings"))
        
        audio_only_formats = ['mp3', 'aac', 'm4a', 'flac', 'wav', 'ogg']
        if self.target_fmt not in audio_only_formats:
            self.rad_audio_convert = wx.RadioButton(panel, label=_("Convert Audio (Re-encode)"), style=wx.RB_GROUP)
            self.rad_audio_convert.SetValue(True)
            self.rad_audio_convert.Bind(wx.EVT_RADIOBUTTON, self.on_mode_change)
            
            self.rad_audio_copy = wx.RadioButton(panel, label=_("Copy Audio Stream (No quality loss)"))
            self.rad_audio_copy.Bind(wx.EVT_RADIOBUTTON, self.on_mode_change)
            
            if not self._check_audio_compatibility(): self.rad_audio_copy.Disable()
            
            sb_audio.Add(self.rad_audio_convert, 0, wx.ALL, 5)
            sb_audio.Add(self.rad_audio_copy, 0, wx.ALL, 5)
            sb_audio.AddSpacer(10)

        hbox_mode = wx.BoxSizer(wx.HORIZONTAL)
        self.rad_cbr = wx.RadioButton(panel, label=_("CBR (Constant Bitrate)"), style=wx.RB_GROUP)
        self.rad_vbr = wx.RadioButton(panel, label=_("VBR (Variable Quality)"))
        self.rad_cbr.SetValue(True)
        self.rad_cbr.Bind(wx.EVT_RADIOBUTTON, self.on_rate_mode_change)
        self.rad_vbr.Bind(wx.EVT_RADIOBUTTON, self.on_rate_mode_change)
        
        hbox_mode.Add(self.rad_cbr, 0, wx.RIGHT, 15)
        hbox_mode.Add(self.rad_vbr, 0)
        sb_audio.Add(hbox_mode, 0, wx.ALL, 5)

        hbox_val = wx.BoxSizer(wx.HORIZONTAL)
        self.lbl_val = wx.StaticText(panel, label=_("Bitrate:")) 
        self.combo_val = wx.Choice(panel, choices=self.choices_cbr)
        self.combo_val.SetSelection(2)
        
        hbox_val.Add(self.lbl_val, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        hbox_val.Add(self.combo_val, 1, wx.EXPAND)
        sb_audio.Add(hbox_val, 0, wx.EXPAND | wx.ALL, 10)
        
        vbox.Add(sb_audio, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # --- Section Vidéo ---
        if "Video" in self.format_label:
            sb_video = wx.StaticBoxSizer(wx.VERTICAL, panel, label=_("Video Settings"))
            self.rad_video_convert = wx.RadioButton(panel, label=_("Convert Video (H.264)"), style=wx.RB_GROUP)
            self.rad_video_copy = wx.RadioButton(panel, label=_("Copy Video Stream"))
            self.rad_video_convert.SetValue(True)
            
            sb_video.Add(self.rad_video_convert, 0, wx.ALL, 5)
            sb_video.Add(self.rad_video_copy, 0, wx.ALL, 5)
            
            lbl_q = wx.StaticText(panel, label=_("Quality (CRF): Balanced"))
            self.slider_q = wx.Slider(panel, value=23, minValue=18, maxValue=35)
            sb_video.Add(lbl_q, 0, wx.TOP, 5)
            sb_video.Add(self.slider_q, 0, wx.EXPAND | wx.ALL, 5)
            vbox.Add(sb_video, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # --- Boutons Action ---
        btns = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(panel, wx.ID_OK, label=_("OK"))
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, label=_("Cancel"))
        btns.AddButton(btn_ok)
        btns.AddButton(btn_cancel)
        btns.Realize()
        
        vbox.AddStretchSpacer()
        vbox.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 15)
        panel.SetSizer(vbox)

    def _load_previous_settings(self):
        s = self.saved_settings
        if not s: return
        
        if hasattr(self, 'rad_audio_copy'):
            if s.get('audio_mode') == 'copy':
                self.rad_audio_copy.SetValue(True)
                self.on_mode_change(None)

        if s.get('audio_mode') != 'copy':
            if s.get('rate_mode') == 'vbr':
                self.rad_vbr.SetValue(True)
                self.on_rate_mode_change(None)
                q_val = s.get('audio_qscale', 4)
                mapping = {0:0, 2:1, 4:2, 6:3}
                self.combo_val.SetSelection(mapping.get(q_val, 2))
            else:
                self.rad_cbr.SetValue(True)
                self.on_rate_mode_change(None)
                saved_bitrate = s.get('audio_bitrate', '192k')
                for i, choice in enumerate(self.choices_cbr):
                    if choice.startswith(saved_bitrate):
                        self.combo_val.SetSelection(i)
                        break

        if hasattr(self, 'rad_video_convert'):
            if s.get('video_mode') == 'copy': self.rad_video_copy.SetValue(True)
            else: self.slider_q.SetValue(s.get('video_crf', 23))

    def on_mode_change(self, event):
        is_copy = hasattr(self, 'rad_audio_copy') and self.rad_audio_copy.GetValue()
        self.rad_cbr.Enable(not is_copy)
        self.rad_vbr.Enable(not is_copy)
        self.combo_val.Enable(not is_copy)

    def on_rate_mode_change(self, event):
        if self.rad_cbr.GetValue():
            self.lbl_val.SetLabel(_("Bitrate:"))
            self.combo_val.Set(self.choices_cbr)
            self.combo_val.SetSelection(2)
        else:
            self.lbl_val.SetLabel(_("Quality:"))
            self.combo_val.Set(self.choices_vbr)
            self.combo_val.SetSelection(0)

    def _check_audio_compatibility(self):
        if not self.input_audio_codec: return False
        if self.target_fmt in ['aac', 'm4a']: return self.input_audio_codec == 'aac'
        if self.target_fmt == 'mp4': return self.input_audio_codec in ['aac', 'mp3', 'ac3']
        return self.target_fmt == 'mkv'

    def get_settings(self):
        settings = {'audio_mode': 'convert'}
        if hasattr(self, 'rad_audio_copy') and self.rad_audio_copy.GetValue():
            settings['audio_mode'] = 'copy'
            settings['summary'] = 'Copy'
        else:
            if self.rad_cbr.GetValue():
                bitrate = self.combo_val.GetStringSelection().split(" ")[0]
                settings.update({'rate_mode': 'cbr', 'audio_bitrate': bitrate, 'summary': f"CBR {bitrate}"})
            else:
                idx = self.combo_val.GetSelection()
                mapping = [0, 2, 4, 6]
                val = mapping[idx] if idx < len(mapping) else 4
                settings.update({'rate_mode': 'vbr', 'audio_qscale': val, 'summary': f"VBR V{val}"})
        if hasattr(self, 'rad_video_convert'):
            settings['video_mode'] = 'copy' if self.rad_video_copy.GetValue() else 'convert'
            settings['video_crf'] = self.slider_q.GetValue()
        return settings