import wx

class SettingsDialog(wx.Dialog):
    def __init__(self, parent, format_label, has_video, input_audio_codec, current_settings):
        super().__init__(parent, title=_("Configure settings for: ") + format_label, size=(550, 650))
        
        self.has_video = has_video
        self.settings = current_settings
        self.format_label = format_label
        
        # --- DETECTIONS DE FORMAT ---
        lower_fmt = format_label.lower()
        self.is_lossless = any(x in lower_fmt for x in ['wav', 'flac', 'alac', 'lossless'])
        self.is_flac = 'flac' in lower_fmt
        self.is_mp3 = 'mp3' in lower_fmt
        self.is_aac = 'aac' in lower_fmt or 'm4a' in lower_fmt
        
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
            
            self.rb_vid_convert = wx.RadioButton(sb_vid_sizer.GetStaticBox(), label=_("Re-encode (Recommended)"), style=wx.RB_GROUP)
            self.rb_vid_copy = wx.RadioButton(sb_vid_sizer.GetStaticBox(), label=_("Copy Stream (Advanced)"))
            self.rb_vid_copy.SetToolTip(_("Keep original quality and speed up conversion.\nWarning: The output format must support the source codec."))
            
            sb_vid_sizer.Add(self.rb_vid_convert, 0, wx.ALL, 5)
            
            self.vid_params_sizer = wx.BoxSizer(wx.VERTICAL)
            row_crf = wx.BoxSizer(wx.HORIZONTAL)
            self.lbl_quality = wx.StaticText(sb_vid_sizer.GetStaticBox(), label=_("Quality (CRF):"), size=(220, -1))
            self.slider_crf = wx.Slider(sb_vid_sizer.GetStaticBox(), value=23, minValue=18, maxValue=35, size=(250, -1))
            self.slider_crf.Bind(wx.EVT_SLIDER, self.on_crf_change)
            
            row_crf.Add(self.lbl_quality, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
            row_crf.Add(self.slider_crf, 1, wx.EXPAND)
            
            self.vid_params_sizer.Add(row_crf, 0, wx.EXPAND | wx.LEFT, 20)
            sb_vid_sizer.Add(self.vid_params_sizer, 0, wx.EXPAND | wx.ALL, 5)
            sb_vid_sizer.Add(self.rb_vid_copy, 0, wx.ALL, 5)
            vbox.Add(sb_vid_sizer, 0, wx.EXPAND | wx.ALL, 10)
            
            self.Bind(wx.EVT_RADIOBUTTON, self.on_vid_mode_change, self.rb_vid_convert)
            self.Bind(wx.EVT_RADIOBUTTON, self.on_vid_mode_change, self.rb_vid_copy)

        # --- SECTION AUDIO ---
        sb_aud = wx.StaticBox(panel, label=_("Audio Settings"))
        sb_aud_sizer = wx.StaticBoxSizer(sb_aud, wx.VERTICAL)
        
        self.rb_aud_convert = wx.RadioButton(sb_aud_sizer.GetStaticBox(), label=_("Re-encode (Recommended)"), style=wx.RB_GROUP)
        self.rb_aud_copy = wx.RadioButton(sb_aud_sizer.GetStaticBox(), label=_("Copy Stream (Advanced)"))
        
        sb_aud_sizer.Add(self.rb_aud_convert, 0, wx.ALL, 5)
        
        # --- PARAMÈTRES AUDIO ---
        self.aud_params_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 1. SAMPLE RATE (TOUT LE MONDE)
        hbox_sr = wx.BoxSizer(wx.HORIZONTAL)
        lbl_sr = wx.StaticText(sb_aud_sizer.GetStaticBox(), label=_("Sample Rate:"))
        self.combo_sr = wx.Choice(sb_aud_sizer.GetStaticBox(), choices=[
            _("Original"), "44100 Hz", "48000 Hz", "88200 Hz", "96000 Hz"
        ])
        hbox_sr.Add(lbl_sr, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        hbox_sr.Add(self.combo_sr, 1, wx.EXPAND)
        self.aud_params_sizer.Add(hbox_sr, 0, wx.EXPAND | wx.LEFT | wx.BOTTOM, 15)

        # 2. LOGIQUE COMPLEXE : LOSSLESS vs LOSSY (CBR/VBR)
        
        if self.is_lossless:
            # --- CAS LOSSLESS ---
            hbox_depth = wx.BoxSizer(wx.HORIZONTAL)
            lbl_depth = wx.StaticText(sb_aud_sizer.GetStaticBox(), label=_("Bit Depth:"))
            self.combo_depth = wx.Choice(sb_aud_sizer.GetStaticBox(), choices=[
                _("Original"), _("16-bit (CD Quality)"), _("24-bit (Studio Quality)"), _("32-bit Float (Pro)")
            ])
            hbox_depth.Add(lbl_depth, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
            hbox_depth.Add(self.combo_depth, 1, wx.EXPAND)
            self.aud_params_sizer.Add(hbox_depth, 0, wx.EXPAND | wx.LEFT | wx.BOTTOM, 15)
            
            # Init useless vars
            self.combo_rate_mode = None
            self.combo_bitrate = None
            self.slider_vbr = None

        else:
            # --- CAS LOSSY (MP3 / AAC) ---
            
            # Choix CBR / VBR
            hbox_mode = wx.BoxSizer(wx.HORIZONTAL)
            lbl_mode = wx.StaticText(sb_aud_sizer.GetStaticBox(), label=_("Rate Mode:"))
            self.combo_rate_mode = wx.Choice(sb_aud_sizer.GetStaticBox(), choices=[
                _("Constant Bitrate (CBR)"), _("Variable Bitrate (VBR)")
            ])
            self.combo_rate_mode.Bind(wx.EVT_CHOICE, self.on_rate_mode_changed)
            hbox_mode.Add(lbl_mode, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
            hbox_mode.Add(self.combo_rate_mode, 1, wx.EXPAND)
            self.aud_params_sizer.Add(hbox_mode, 0, wx.EXPAND | wx.LEFT | wx.BOTTOM, 15)

            # Option A : CBR Bitrate
            self.hbox_cbr = wx.BoxSizer(wx.HORIZONTAL)
            lbl_br = wx.StaticText(sb_aud_sizer.GetStaticBox(), label=_("Bitrate:"))
            br_choices = ["32k", "40k", "48k", "64k", "80k", "96k", "112k", "128k", "160k", "192k", "224k", "256k", "320k"]
            self.combo_bitrate = wx.Choice(sb_aud_sizer.GetStaticBox(), choices=br_choices)
            self.hbox_cbr.Add(lbl_br, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
            self.hbox_cbr.Add(self.combo_bitrate, 1, wx.EXPAND)
            self.aud_params_sizer.Add(self.hbox_cbr, 0, wx.EXPAND | wx.LEFT | wx.BOTTOM, 15)

            # Option B : VBR Slider
            self.hbox_vbr = wx.BoxSizer(wx.HORIZONTAL)
            # Gestion Echelle MP3 (0-9) vs AAC (1-5)
            if self.is_mp3:
                # MP3: 0 = Best, 9 = Worst. Slider 0..9
                self.slider_vbr = wx.Slider(sb_aud_sizer.GetStaticBox(), value=0, minValue=0, maxValue=9, size=(250, -1))
            else:
                # AAC: 1 = Worst, 5 = Best. Slider 1..5
                self.slider_vbr = wx.Slider(sb_aud_sizer.GetStaticBox(), value=3, minValue=1, maxValue=5, size=(250, -1))
            
            self.lbl_vbr_val = wx.StaticText(sb_aud_sizer.GetStaticBox(), label=_("Quality (VBR):"), size=(250, -1))
            self.slider_vbr.Bind(wx.EVT_SLIDER, self.on_vbr_change)
            
            # Layout VBR
            vbr_col = wx.BoxSizer(wx.VERTICAL)
            vbr_col.Add(self.lbl_vbr_val, 0, wx.BOTTOM, 5)
            vbr_col.Add(self.slider_vbr, 0, wx.EXPAND)
            self.hbox_vbr.Add(vbr_col, 1, wx.EXPAND)
            self.aud_params_sizer.Add(self.hbox_vbr, 0, wx.EXPAND | wx.LEFT | wx.BOTTOM, 15)
            
            # Init useless vars
            self.combo_depth = None
            self.slider_comp = None

        # 3. SPECIAL FLAC COMPRESSION
        if self.is_flac:
            self.hbox_comp = wx.BoxSizer(wx.HORIZONTAL)
            lbl_comp = wx.StaticText(sb_aud_sizer.GetStaticBox(), label=_("Compression Level:"))
            self.slider_comp = wx.Slider(sb_aud_sizer.GetStaticBox(), value=5, minValue=0, maxValue=8, size=(200, -1))
            lbl_min = wx.StaticText(sb_aud_sizer.GetStaticBox(), label=_("Fast (0)"))
            lbl_max = wx.StaticText(sb_aud_sizer.GetStaticBox(), label=_("Max (8)"))
            
            self.hbox_comp.Add(lbl_comp, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
            self.hbox_comp.Add(lbl_min, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
            self.hbox_comp.Add(self.slider_comp, 1, wx.EXPAND)
            self.hbox_comp.Add(lbl_max, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
            
            self.aud_params_sizer.Add(self.hbox_comp, 0, wx.EXPAND | wx.LEFT, 15)
        
        sb_aud_sizer.Add(self.aud_params_sizer, 0, wx.EXPAND | wx.ALL, 5)
        sb_aud_sizer.Add(self.rb_aud_copy, 0, wx.ALL, 5)
        vbox.Add(sb_aud_sizer, 0, wx.EXPAND | wx.ALL, 10)

        self.Bind(wx.EVT_RADIOBUTTON, self.on_aud_mode_change, self.rb_aud_convert)
        self.Bind(wx.EVT_RADIOBUTTON, self.on_aud_mode_change, self.rb_aud_copy)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(panel, wx.ID_OK, label=_("OK"))
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, label=_("Cancel"))
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        panel.SetSizer(vbox)
        vbox.Fit(self)
        
        # --- LOADING VALUES ---
        # 1. Video
        if self.has_video:
            saved_crf = self.settings.get('video_crf', 23)
            self.slider_crf.SetValue(saved_crf)
            if self.video_mode == 'copy': self.rb_vid_copy.SetValue(True)
            else: self.rb_vid_convert.SetValue(True)
            self.on_crf_change(None)
            self.on_vid_mode_change(None) 

        # 2. Audio Common
        saved_sr = self.settings.get('audio_sample_rate', 'original')
        sr_map = {'original': 0, '44100': 1, '48000': 2, '88200': 3, '96000': 4}
        self.combo_sr.SetSelection(sr_map.get(str(saved_sr), 0))

        # 3. Audio Specific
        if self.is_lossless:
            saved_depth = self.settings.get('audio_bit_depth', 'original')
            depth_map = {'original': 0, '16': 1, '24': 2, '32': 3}
            self.combo_depth.SetSelection(depth_map.get(str(saved_depth), 0))
            if self.is_flac:
                self.slider_comp.SetValue(self.settings.get('flac_compression', 5))
        else:
            # CBR/VBR
            mode = self.settings.get('rate_mode', 'cbr')
            self.combo_rate_mode.SetSelection(1 if mode == 'vbr' else 0)
            
            # Bitrate
            saved_bitrate = self.settings.get('audio_bitrate', '192k')
            idx = self.combo_bitrate.FindString(saved_bitrate)
            if idx != wx.NOT_FOUND: self.combo_bitrate.SetSelection(idx)
            else: self.combo_bitrate.SetSelection(9) # 192k
            
            # VBR Quality
            saved_q = self.settings.get('audio_qscale', 0 if self.is_mp3 else 3)
            self.slider_vbr.SetValue(saved_q)
            self.on_vbr_change(None)
            self.on_rate_mode_changed(None)

        if self.audio_mode == 'copy': self.rb_aud_copy.SetValue(True)
        else: self.rb_aud_convert.SetValue(True)
        self.on_aud_mode_change(None)

    # --- LOGIQUE UI ---

    def on_crf_change(self, event):
        val = self.slider_crf.GetValue()
        prefix = _("Quality (CRF):")
        desc = ""
        if val < 20: desc = _("High Quality (V2)")
        elif val < 26: desc = _("Balanced")
        else: desc = _("Small Size")
        self.lbl_quality.SetLabel(f"{prefix} {val} ({desc})")

    def on_vbr_change(self, event):
        val = self.slider_vbr.GetValue()
        prefix = _("Quality (VBR):")
        desc = ""
        
        if self.is_mp3: # 0(best) to 9(worst)
            if val == 0: desc = _("Best Quality (V0)")
            elif val < 3: desc = "V1-V2 (High)"
            elif val < 7: desc = "V3-V6 (Mid)"
            else: desc = _("Smallest Size (V9)")
        else: # AAC: 1(low) to 5(best)
            if val == 5: desc = _("Audiophile (5)")
            elif val >= 3: desc = "High (3-4)"
            else: desc = _("Low Quality (1)")
            
        self.lbl_vbr_val.SetLabel(f"{prefix} {val} - {desc}")

    def on_rate_mode_changed(self, event):
        if not self.combo_rate_mode: return
        is_vbr = (self.combo_rate_mode.GetSelection() == 1)
        
        # Show/Hide Logic
        if is_vbr:
            self.hbox_cbr.ShowItems(False)
            self.hbox_vbr.ShowItems(True)
        else:
            self.hbox_cbr.ShowItems(True)
            self.hbox_vbr.ShowItems(False)
        self.Layout()

    def on_vid_mode_change(self, event):
        is_convert = self.rb_vid_convert.GetValue()
        self.slider_crf.Enable(is_convert)
        self.lbl_quality.Enable(is_convert)

    def on_aud_mode_change(self, event):
        is_convert = self.rb_aud_convert.GetValue()
        self.combo_sr.Enable(is_convert)
        
        if self.is_lossless:
            self.combo_depth.Enable(is_convert)
            if self.is_flac: self.slider_comp.Enable(is_convert)
        else:
            self.combo_rate_mode.Enable(is_convert)
            self.combo_bitrate.Enable(is_convert)
            self.slider_vbr.Enable(is_convert)
            self.lbl_vbr_val.Enable(is_convert)

    def get_settings(self):
        summary_parts = []
        
        # VIDEO
        if self.has_video:
            v_mode = 'copy' if self.rb_vid_copy.GetValue() else 'convert'
            if v_mode == 'copy': summary_parts.append("Video: Copy")
            else:
                crf = self.slider_crf.GetValue()
                summary_parts.append(f"H.264 CRF {crf}")
        else:
            v_mode = 'convert'

        # AUDIO
        a_mode = 'copy' if self.rb_aud_copy.GetValue() else 'convert'
        
        # Defaults
        sr_sel = self.combo_sr.GetSelection()
        sr_vals = ['original', '44100', '48000', '88200', '96000']
        sample_rate = sr_vals[sr_sel]
        
        bitrate = "192k"
        bit_depth = "original"
        rate_mode = "cbr"
        qscale = 0
        flac_comp = 5

        if self.is_lossless:
            depth_sel = self.combo_depth.GetSelection()
            depth_vals = ['original', '16', '24', '32']
            bit_depth = depth_vals[depth_sel]
            if self.is_flac: flac_comp = self.slider_comp.GetValue()
        else:
            rate_mode = "vbr" if self.combo_rate_mode.GetSelection() == 1 else "cbr"
            if rate_mode == "cbr":
                bitrate = self.combo_bitrate.GetStringSelection()
            else:
                qscale = self.slider_vbr.GetValue()

        if a_mode == 'copy':
            summary_parts.append("Audio: Copy")
        else:
            if self.is_lossless:
                depth_str = f"{bit_depth}-bit" if bit_depth != 'original' else "Original Depth"
                summary_parts.append(f"Lossless {depth_str}")
            else:
                codec_name = "AAC" if "aac" in self.format_label.lower() or "m4a" in self.format_label.lower() else "MP3"
                if rate_mode == 'cbr':
                    summary_parts.append(f"{codec_name} CBR {bitrate}")
                else:
                    if codec_name == "MP3": q_txt = f"V{qscale}"
                    else: q_txt = f"Q{qscale}"
                    summary_parts.append(f"{codec_name} VBR ({q_txt})")
            
            if sample_rate != 'original':
                summary_parts.append(f"{sample_rate}Hz")

        return {
            'video_mode': v_mode,
            'video_crf': self.slider_crf.GetValue() if self.has_video else 23,
            
            'audio_mode': a_mode,
            'audio_bitrate': bitrate,
            'rate_mode': rate_mode,
            'audio_qscale': qscale,
            'audio_sample_rate': sample_rate,
            'audio_bit_depth': bit_depth,
            'flac_compression': flac_comp,
            
            'summary': " / ".join(summary_parts)
        }