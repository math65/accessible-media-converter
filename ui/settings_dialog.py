import wx

from core.formatting import DEFAULT_FORMAT_SETTINGS, build_format_summary


VIDEO_CRF_PRESET_OPTIONS = (
    (16, "Very High Quality"),
    (18, "High Quality"),
    (20, "Quality"),
    (22, "Balanced Quality"),
    (23, "Balanced - Recommended"),
    (24, "Compact"),
    (26, "More Compact"),
    (28, "Small File"),
    (30, "Very Compact"),
)


class SettingsDialog(wx.Dialog):
    def __init__(self, parent, title_format, has_video, input_ac, current_settings, format_key):
        super().__init__(parent, title=_("Configure settings for: ") + title_format, size=(500, 600))
        self.current_settings = current_settings
        self.format_key = format_key 
        
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # --- AUDIO ---
        audio_box = wx.StaticBox(self, label=_("Audio Settings"))
        audio_sizer = wx.StaticBoxSizer(audio_box, wx.VERTICAL)
        
        # Audio Mode
        row_mode = wx.BoxSizer(wx.HORIZONTAL)
        self.rb_convert = wx.RadioButton(self, label=_("Re-encode (Recommended)"), style=wx.RB_GROUP)
        self.rb_copy = wx.RadioButton(self, label=_("Copy Stream (Advanced)"))
        row_mode.Add(self.rb_convert, 0, wx.RIGHT, 15)
        row_mode.Add(self.rb_copy, 0)
        audio_sizer.Add(row_mode, 0, wx.ALL, 5)
        
        self.lbl_copy_warn = wx.StaticText(self, label=_("Keep original quality and speed up conversion.\nWarning: The output format must support the source codec."))
        self.lbl_copy_warn.SetForegroundColour(wx.Colour(100, 100, 100))
        audio_sizer.Add(self.lbl_copy_warn, 0, wx.ALL | wx.EXPAND, 5)
        
        # Audio Details Panel
        self.panel_audio_opts = wx.Panel(self)
        
        grid_audio = wx.FlexGridSizer(rows=0, cols=2, vgap=10, hgap=10)
        grid_audio.AddGrowableCol(1, 1)
        
        # 1. Sample Rate
        self.sr_display_choices = [_("Original"), "44.1 kHz", "48 kHz", "96 kHz", "22.05 kHz"]
        self.lbl_sr = wx.StaticText(self.panel_audio_opts, label=_("Sample Rate:"))
        self.combo_sr = wx.Choice(
            self.panel_audio_opts,
            choices=self.sr_display_choices
        )
        grid_audio.Add(self.lbl_sr, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_audio.Add(self.combo_sr, 0, wx.EXPAND)
        
        # 2. Channels
        self.ch_display_choices = [_("Stereo (Downmix)"), _("Mono"), _("Original Channels")]
        self.lbl_ch = wx.StaticText(self.panel_audio_opts, label=_("Channels:"))
        self.combo_ch = wx.Choice(
            self.panel_audio_opts,
            choices=self.ch_display_choices
        )
        grid_audio.Add(self.lbl_ch, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_audio.Add(self.combo_ch, 0, wx.EXPAND)
        
        # 3. Rate Mode (CBR/VBR)
        self.lbl_rate_mode = wx.StaticText(self.panel_audio_opts, label=_("Rate Mode:"))
        self.rate_mode_display_choices = [_("Constant Bitrate (CBR)"), _("Variable Bitrate (VBR)")]
        self.combo_rate_mode = wx.Choice(self.panel_audio_opts, choices=self.rate_mode_display_choices)
        self.combo_rate_mode.Bind(wx.EVT_CHOICE, self.on_rate_mode_change)
        
        if self.format_key == 'wma':
            self.lbl_rate_mode.Hide()
            self.combo_rate_mode.Hide()
        else:
            grid_audio.Add(self.lbl_rate_mode, 0, wx.ALIGN_CENTER_VERTICAL)
            grid_audio.Add(self.combo_rate_mode, 0, wx.EXPAND)
        
        # 4. Bitrate (CBR)
        self.lbl_bitrate = wx.StaticText(self.panel_audio_opts, label=_("Bitrate:"))
        self.bitrate_display_choices = ['320k', '256k', '192k', '160k', '128k', '96k', '64k']
        self.combo_bitrate = wx.Choice(self.panel_audio_opts, choices=self.bitrate_display_choices)
        grid_audio.Add(self.lbl_bitrate, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_audio.Add(self.combo_bitrate, 0, wx.EXPAND)
        
        # 5. Quality (VBR/OGG)
        self.lbl_quality = wx.StaticText(self.panel_audio_opts, label=_("Quality (VBR):"))
        self.combo_quality = wx.Choice(self.panel_audio_opts, choices=[]) 
        
        grid_audio.Add(self.lbl_quality, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_audio.Add(self.combo_quality, 0, wx.EXPAND)
        
        # 6. Specific (FLAC/WAV Depth & Compression)
        self.lbl_depth = wx.StaticText(self.panel_audio_opts, label=_("Bit Depth:"))
        self.combo_depth = wx.Choice(self.panel_audio_opts, choices=[_("Original"), _("16-bit (CD Quality)"), _("24-bit (Studio Quality)"), _("32-bit Float (Pro)")])
        grid_audio.Add(self.lbl_depth, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_audio.Add(self.combo_depth, 0, wx.EXPAND)
        
        # Compression Level (FLAC)
        self.lbl_comp = wx.StaticText(self.panel_audio_opts, label=_("Compression Level:"))
        
        comp_choices = []
        for i in range(13): # 0 à 12
            txt = str(i)
            if i == 0: txt += " (" + _("Fast") + ")"
            if i == 5: txt += " (" + _("Standard") + ")"
            if i == 8: txt += " (" + _("Max") + ")"
            # CORRECTION TRADUCTION ICI
            if i == 12: txt += " (" + _("Ultra Slow") + ")"
            comp_choices.append(txt)
            
        self.combo_comp = wx.Choice(self.panel_audio_opts, choices=comp_choices)
        
        grid_audio.Add(self.lbl_comp, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_audio.Add(self.combo_comp, 0, wx.EXPAND)

        self.chk_normalize_streaming = wx.CheckBox(
            self.panel_audio_opts,
            label=_("Normalize for streaming (-16 LUFS)"),
        )

        audio_opts_sizer = wx.BoxSizer(wx.VERTICAL)
        audio_opts_sizer.Add(grid_audio, 0, wx.EXPAND)
        audio_opts_sizer.Add(self.chk_normalize_streaming, 0, wx.TOP, 12)
        self.panel_audio_opts.SetSizer(audio_opts_sizer)
        audio_sizer.Add(self.panel_audio_opts, 1, wx.EXPAND | wx.ALL, 10)
        self.main_sizer.Add(audio_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # --- VIDEO ---
        if has_video and format_key in ['mp4', 'mkv', 'mov']:
            video_box = wx.StaticBox(self, label=_("Video Settings"))
            video_sizer = wx.StaticBoxSizer(video_box, wx.VERTICAL)
            
            row_vmode = wx.BoxSizer(wx.HORIZONTAL)
            self.rb_v_convert = wx.RadioButton(self, label=_("Re-encode (Recommended)"), style=wx.RB_GROUP)
            self.rb_v_copy = wx.RadioButton(self, label=_("Copy Stream (Advanced)"))
            row_vmode.Add(self.rb_v_convert, 0, wx.RIGHT, 15)
            row_vmode.Add(self.rb_v_copy, 0)
            video_sizer.Add(row_vmode, 0, wx.ALL, 5)
            
            self.panel_video_opts = wx.Panel(self)
            grid_vid = wx.FlexGridSizer(rows=1, cols=2, vgap=10, hgap=10)
            grid_vid.AddGrowableCol(1, 1)
            
            self.lbl_crf = wx.StaticText(self.panel_video_opts, label=_("Quality (CRF):"))
            grid_vid.Add(self.lbl_crf, 0, wx.ALIGN_CENTER_VERTICAL)

            self.combo_crf = wx.Choice(self.panel_video_opts, choices=[])
            grid_vid.Add(self.combo_crf, 1, wx.EXPAND)
            
            self.panel_video_opts.SetSizer(grid_vid)
            video_sizer.Add(self.panel_video_opts, 1, wx.EXPAND | wx.ALL, 10)
            self.main_sizer.Add(video_sizer, 0, wx.EXPAND | wx.ALL, 5)
            
            self.rb_v_convert.Bind(wx.EVT_RADIOBUTTON, self.on_vmode_change)
            self.rb_v_copy.Bind(wx.EVT_RADIOBUTTON, self.on_vmode_change)
        
        # --- BOUTONS ---
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK, label=_("OK"))
        btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_("Cancel"))
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        self.main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(self.main_sizer)
        self.Centre()
        
        # Bindings
        self.rb_convert.Bind(wx.EVT_RADIOBUTTON, self.on_mode_change)
        self.rb_copy.Bind(wx.EVT_RADIOBUTTON, self.on_mode_change)
        self.combo_sr.Bind(wx.EVT_CHOICE, self.on_audio_option_change)
        self.combo_ch.Bind(wx.EVT_CHOICE, self.on_audio_option_change)
        self.combo_bitrate.Bind(wx.EVT_CHOICE, self.on_audio_option_change)
        self.combo_quality.Bind(wx.EVT_CHOICE, self.on_audio_option_change)
        self.combo_depth.Bind(wx.EVT_CHOICE, self.on_audio_option_change)
        self.combo_comp.Bind(wx.EVT_CHOICE, self.on_audio_option_change)
        self.chk_normalize_streaming.Bind(wx.EVT_CHECKBOX, self.on_audio_option_change)
        if hasattr(self, 'combo_crf'):
            self.combo_crf.Bind(wx.EVT_CHOICE, self.on_video_option_change)
        
        self._load_from_settings()
        self._update_visibility()
        self._set_accessibility_metadata()

    def _load_from_settings(self):
        s = self.current_settings
        
        if s.get('audio_mode') == 'copy': self.rb_copy.SetValue(True)
        else: self.rb_convert.SetValue(True)
        
        sr_map = {'original': 0, '44100': 1, '48000': 2, '96000': 3, '22050': 4}
        self.combo_sr.SetSelection(sr_map.get(str(s.get('audio_sample_rate', 'original')), 0))
        
        ch_map = {'2': 0, '1': 1, 'original': 2}
        self.combo_ch.SetSelection(ch_map.get(str(s.get('audio_channels', '2')), 0))
        
        if self.format_key == 'wma':
            self.lbl_rate_mode.Hide()
            self.combo_rate_mode.Hide()
        else:
            self.combo_rate_mode.SetSelection(1 if s.get('rate_mode') == 'vbr' else 0)
        
        br_map = {'320k': 0, '256k': 1, '192k': 2, '160k': 3, '128k': 4, '96k': 5, '64k': 6}
        self.combo_bitrate.SetSelection(br_map.get(s.get('audio_bitrate', '192k'), 2))
        
        q = int(s.get('audio_qscale', 0))
        self._populate_quality_combo() 
        
        if self.format_key == 'mp3':
            if q >= 0 and q <= 9: self.combo_quality.SetSelection(q)
        elif self.format_key == 'aac':
            idx = q - 1
            if idx >= 0 and idx < 5: self.combo_quality.SetSelection(idx)
        elif self.format_key == 'ogg':
            if q >= 0 and q <= 10: self.combo_quality.SetSelection(q)
        
        d_map = {'original': 0, '16': 1, '24': 2, '32': 3}
        self.combo_depth.SetSelection(d_map.get(str(s.get('audio_bit_depth', 'original')), 0))

        c = int(s.get('flac_compression', 5))
        if c > 12: c = 12
        self.combo_comp.SetSelection(c)

        self.chk_normalize_streaming.SetValue(bool(s.get('audio_normalize_streaming', False)))

        if hasattr(self, 'rb_v_convert'):
            if s.get('video_mode') == 'copy': self.rb_v_copy.SetValue(True)
            else: self.rb_v_convert.SetValue(True)
            self._populate_crf_combo(s.get('video_crf', DEFAULT_FORMAT_SETTINGS['mp4']['video_crf']))

    def _populate_quality_combo(self):
        self.combo_quality.Clear()
        choices = []
        if self.format_key == 'mp3':
            for i in range(10):
                desc = f"V{i}"
                if i == 0: desc += " (" + _("Best Quality") + ")"
                elif i == 2: desc += " (" + _("High Quality") + ")"
                elif i == 4: desc += " (" + _("Medium") + ")"
                elif i == 9: desc += " (" + _("Smallest Size") + ")"
                choices.append(desc)
        elif self.format_key == 'aac':
            for i in range(1, 6):
                desc = f"Q{i}"
                if i == 1: desc += " (" + _("Low") + ")"
                elif i == 3: desc += " (" + _("Standard") + ")"
                elif i == 5: desc += " (" + _("High") + ")"
                choices.append(desc)
        elif self.format_key == 'ogg':
            for i in range(11):
                desc = f"Q{i}"
                if i == 6: desc += " (" + _("Audiophile") + ")"
                choices.append(desc)
        self.combo_quality.Set(choices)

    def on_mode_change(self, e):
        self._update_visibility()
        if self.rb_convert.GetValue():
            self._focus_primary_audio_control()
            wx.CallAfter(self._focus_primary_audio_control)

    def on_vmode_change(self, e):
        self._update_visibility()

    def on_rate_mode_change(self, e):
        self._update_visibility(preserve_focus=self.combo_rate_mode)

    def on_audio_option_change(self, e):
        self._update_dynamic_accessible_names()
        e.Skip()

    def on_video_option_change(self, e):
        self._update_dynamic_accessible_names()
        e.Skip()

    def _update_visibility(self, preserve_focus=None):
        is_convert = self.rb_convert.GetValue()
        self.panel_audio_opts.Enable(is_convert)
        self.chk_normalize_streaming.Enable(is_convert)
        self.lbl_copy_warn.Show(not is_convert)
        
        if is_convert:
            self.lbl_rate_mode.Hide()
            self.combo_rate_mode.Hide()
            self.lbl_bitrate.Hide()
            self.combo_bitrate.Hide()
            self.lbl_quality.Hide()
            self.combo_quality.Hide()
            self.lbl_depth.Hide()
            self.combo_depth.Hide()
            self.lbl_comp.Hide()
            self.combo_comp.Hide()
            
            fmt = self.format_key
            is_vbr = (self.combo_rate_mode.GetSelection() == 1)
            
            if fmt == 'wma': is_vbr = False
            
            if fmt in ['mp3', 'aac']:
                self.lbl_rate_mode.Show()
                self.combo_rate_mode.Show()
                if is_vbr:
                    self.lbl_quality.Show()
                    self.combo_quality.Show()
                    self.lbl_quality.SetLabel(_("Quality (VBR):"))
                else:
                    self.lbl_bitrate.Show()
                    self.combo_bitrate.Show()
            
            elif fmt == 'ogg':
                self.lbl_quality.Show()
                self.combo_quality.Show()
                self.lbl_quality.SetLabel(_("Quality (OGG):"))
                
            elif fmt == 'wma':
                self.lbl_bitrate.Show()
                self.combo_bitrate.Show()
                
            elif fmt in ['wav', 'flac', 'alac']:
                self.lbl_depth.Show()
                self.combo_depth.Show()
                if fmt == 'flac':
                    self.lbl_comp.Show()
                    self.combo_comp.Show()

        if hasattr(self, 'panel_video_opts'):
            is_v_convert = self.rb_v_convert.GetValue()
            self.panel_video_opts.Enable(is_v_convert)

        self._update_dynamic_accessible_names()
        self.panel_audio_opts.Layout()
        self.main_sizer.Layout()
        if preserve_focus and preserve_focus.IsShown() and preserve_focus.IsEnabled():
            current_focus = wx.Window.FindFocus()
            if current_focus is not preserve_focus:
                wx.CallAfter(preserve_focus.SetFocus)

    def _set_accessibility_metadata(self):
        self.SetName(_("Format settings dialog"))
        self.panel_audio_opts.SetName(_("Audio settings panel"))
        self.panel_audio_opts.SetToolTip(_("Use Tab to navigate audio options."))

        self.rb_convert.SetName(_("Audio mode re-encode"))
        self.rb_copy.SetName(_("Audio mode copy stream"))
        self.rb_convert.SetToolTip(_("Re-encode audio with detailed settings."))
        self.rb_copy.SetToolTip(_("Copy source audio without re-encoding."))

        self.combo_sr.SetName(_("Sample Rate"))
        self.combo_ch.SetName(_("Channels"))
        self.combo_rate_mode.SetName(_("Rate Mode"))
        self.combo_bitrate.SetName(_("Bitrate"))
        self.combo_quality.SetName(_("Quality"))
        self.combo_depth.SetName(_("Bit Depth"))
        self.combo_comp.SetName(_("Compression"))
        self.chk_normalize_streaming.SetName(_("Normalize for streaming"))

        self.combo_sr.SetToolTip(_("Target sample rate."))
        self.combo_ch.SetToolTip(_("Target channel layout."))
        self.combo_rate_mode.SetToolTip(_("Choose CBR or VBR mode."))
        self.combo_bitrate.SetToolTip(_("Bitrate used in CBR mode."))
        self.combo_quality.SetToolTip(_("Quality scale used in VBR mode."))
        self.combo_depth.SetToolTip(_("Bit depth for lossless formats."))
        self.combo_comp.SetToolTip(_("Compression level for FLAC."))
        self.chk_normalize_streaming.SetToolTip(_("Apply streaming loudness normalization at -16 LUFS."))

        self.lbl_copy_warn.SetName(_("Copy mode warning"))

        if hasattr(self, 'panel_video_opts'):
            self.panel_video_opts.SetName(_("Video settings panel"))
            self.rb_v_convert.SetName(_("Video mode re-encode"))
            self.rb_v_copy.SetName(_("Video mode copy stream"))
            self.combo_crf.SetName(_("Video quality CRF"))
            self.combo_crf.SetToolTip(_("Lower CRF means better quality and bigger file."))
            self.lbl_crf.SetName(_("Video quality CRF"))

        self._update_dynamic_accessible_names()

    def _update_dynamic_accessible_names(self):
        # Keep stable, explicit names so NVDA always announces the same label for each field.
        self.combo_sr.SetName(_("Sample Rate"))
        self.combo_ch.SetName(_("Channels"))
        self.combo_rate_mode.SetName(_("Rate Mode"))
        self.combo_bitrate.SetName(_("Bitrate"))
        self.combo_quality.SetName(_("Quality"))
        self.combo_depth.SetName(_("Bit Depth"))
        self.combo_comp.SetName(_("Compression"))
        self.chk_normalize_streaming.SetName(_("Normalize for streaming"))
        if hasattr(self, 'combo_crf'):
            self.combo_crf.SetName(_("Video quality CRF"))

    def _focus_primary_audio_control(self):
        for ctrl in [self.combo_sr, self.combo_ch, self.combo_rate_mode, self.combo_bitrate, self.combo_quality, self.combo_depth, self.combo_comp, self.chk_normalize_streaming]:
            if ctrl.IsShown() and ctrl.IsEnabled():
                ctrl.SetFocus()
                return

    def _coerce_video_crf_value(self, value):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return DEFAULT_FORMAT_SETTINGS['mp4']['video_crf']

        if 0 <= parsed <= 51:
            return parsed
        return DEFAULT_FORMAT_SETTINGS['mp4']['video_crf']

    def _build_crf_choice_label(self, value, label_msgid=None, custom=False):
        if custom:
            label = _("Custom")
        else:
            label = _(label_msgid or "Balanced - Recommended")
        return _("CRF {value} ({label})").format(value=value, label=label)

    def _populate_crf_combo(self, current_value):
        value = self._coerce_video_crf_value(current_value)
        preset_values = {preset_value for preset_value, _ in VIDEO_CRF_PRESET_OPTIONS}
        custom_value = value if value not in preset_values else None

        self.video_crf_values = []
        choices = []
        custom_inserted = False

        for preset_value, label_msgid in VIDEO_CRF_PRESET_OPTIONS:
            if custom_value is not None and not custom_inserted and custom_value < preset_value:
                self.video_crf_values.append(custom_value)
                choices.append(self._build_crf_choice_label(custom_value, custom=True))
                custom_inserted = True

            self.video_crf_values.append(preset_value)
            choices.append(self._build_crf_choice_label(preset_value, label_msgid=label_msgid))

        if custom_value is not None and not custom_inserted:
            self.video_crf_values.append(custom_value)
            choices.append(self._build_crf_choice_label(custom_value, custom=True))

        self.combo_crf.Set(choices)
        selected_value = value if value in self.video_crf_values else DEFAULT_FORMAT_SETTINGS['mp4']['video_crf']
        self.combo_crf.SetSelection(self.video_crf_values.index(selected_value))

    def get_settings(self):
        s = {}
        s['audio_mode'] = 'copy' if self.rb_copy.GetValue() else 'convert'
        sr_vals = ['original', '44100', '48000', '96000', '22050']
        s['audio_sample_rate'] = sr_vals[self.combo_sr.GetSelection()]
        ch_vals = ['2', '1', 'original']
        s['audio_channels'] = ch_vals[self.combo_ch.GetSelection()]
        
        if self.format_key == 'wma': s['rate_mode'] = 'cbr'
        else: s['rate_mode'] = 'vbr' if self.combo_rate_mode.GetSelection() == 1 else 'cbr'
        
        br_vals = ['320k', '256k', '192k', '160k', '128k', '96k', '64k']
        s['audio_bitrate'] = br_vals[self.combo_bitrate.GetSelection()]
        
        qual_idx = self.combo_quality.GetSelection()
        if qual_idx == wx.NOT_FOUND:
            qual_idx = int(
                self.current_settings.get(
                    'audio_qscale',
                    DEFAULT_FORMAT_SETTINGS.get(self.format_key, DEFAULT_FORMAT_SETTINGS['mp3']).get('audio_qscale', 0)
                )
            )
        if self.format_key == 'aac': s['audio_qscale'] = qual_idx + 1
        else: s['audio_qscale'] = qual_idx
        
        d_vals = ['original', '16', '24', '32']
        s['audio_bit_depth'] = d_vals[self.combo_depth.GetSelection()]
        
        s['flac_compression'] = self.combo_comp.GetSelection()
        s['audio_normalize_streaming'] = self.chk_normalize_streaming.GetValue()

        if hasattr(self, 'rb_v_convert'):
            s['video_mode'] = 'copy' if self.rb_v_copy.GetValue() else 'convert'
            selected_index = self.combo_crf.GetSelection()
            if selected_index == wx.NOT_FOUND:
                s['video_crf'] = self._coerce_video_crf_value(
                    self.current_settings.get('video_crf', DEFAULT_FORMAT_SETTINGS['mp4']['video_crf'])
                )
            else:
                s['video_crf'] = self.video_crf_values[selected_index]

        s['summary'] = build_format_summary(self.format_key, s)
        return s
