import wx
import os
import threading
import json

from core import FileProber, ConversionTask
from ui.settings_dialog import SettingsDialog
from ui.preferences_dialog import PreferencesDialog
from ui.track_manager import TrackManagerDialog 

class FileListPanel(wx.Panel):
    def __init__(self, parent, list_name):
        super().__init__(parent)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        # CORRECTION A03 : Suppression de wx.LC_SINGLE_SEL pour permettre la sélection multiple
        self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.list_ctrl.InsertColumn(0, _("Filename"), width=300)
        self.list_ctrl.InsertColumn(1, _("Details (Codec/Bitrate)"), width=250)
        self.list_ctrl.InsertColumn(2, _("Status"), width=150)
        self.list_ctrl.SetName(list_name)
        self.list_ctrl.SetToolTip(_("Use arrows to browse files. Press Delete to remove selected entries."))
        self.sizer.Add(self.list_ctrl, 1, wx.EXPAND)
        self.SetSizer(self.sizer)

class MainWindow(wx.Frame):
    def __init__(self):
        super().__init__(None, title=_("Universal Transcoder"), size=(950, 650))
        
        self.is_converting = False
        self.stop_requested = False
        
        self.prober = FileProber()
        self.audio_data = [] 
        self.video_data = [] 
        
        app_data = os.getenv('APPDATA')
        config_dir = os.path.join(app_data, "UniversalTranscoder")
        if not os.path.exists(config_dir): os.makedirs(config_dir)
        self.config_path = os.path.join(config_dir, "config.json")
        self.settings_store = self._load_config()
        
        self.audio_formats_display = [
            "MP3 - Audio", 
            "AAC - Audio (M4A)", 
            "WAV - Audio (Lossless)", 
            "FLAC - Audio (Lossless)",
            "ALAC - Audio (Apple Lossless)",
            "OGG - Audio (Vorbis)",
            "WMA - Audio (Legacy)"
        ]
        self.audio_formats_keys = ["mp3", "aac", "wav", "flac", "alac", "ogg", "wma"]
        
        self.video_formats_display = ["MP4 - Video (H.264)", "MKV - Video", "MP3 - Audio (Extract)", "AAC - Audio (Extract)"]
        self.video_formats_keys = ["mp4", "mkv", "mp3", "aac"]
        
        self.current_tab = "audio"
        self._init_menu_bar()
        self._init_ui()
        self._init_accessibility()
        self.CreateStatusBar(1)
        self._set_status(_("Ready. Add files to begin."))
        self._update_ui_state()
        self.Centre()
        
        self.Bind(wx.EVT_CLOSE, self.on_close_window)

    def _load_config(self):
        defaults = {
            'mp3': {'audio_mode': 'convert', 'rate_mode': 'cbr', 'audio_bitrate': '192k', 'audio_qscale': 0, 'audio_sample_rate': 'original', 'audio_channels': '2', 'summary': 'CBR 192k / Stereo'},
            'aac': {'audio_mode': 'convert', 'rate_mode': 'cbr', 'audio_bitrate': '192k', 'audio_qscale': 3, 'audio_sample_rate': 'original', 'audio_channels': '2', 'summary': 'CBR 192k / Stereo'},
            'ogg': {'audio_mode': 'convert', 'audio_qscale': 6, 'audio_sample_rate': 'original', 'audio_channels': '2', 'summary': 'VBR Q6 / Stereo'},
            'wma': {'audio_mode': 'convert', 'audio_bitrate': '128k', 'audio_sample_rate': 'original', 'audio_channels': '2', 'summary': 'CBR 128k / Stereo'},
            'wav': {'audio_mode': 'convert', 'audio_sample_rate': 'original', 'audio_bit_depth': 'original', 'audio_channels': 'original', 'summary': 'Lossless'},
            'flac': {'audio_mode': 'convert', 'audio_sample_rate': 'original', 'audio_bit_depth': 'original', 'flac_compression': 5, 'audio_channels': 'original', 'summary': 'Lossless'},
            'alac': {'audio_mode': 'convert', 'audio_sample_rate': 'original', 'audio_bit_depth': 'original', 'audio_channels': 'original', 'summary': 'Lossless'},
            'mp4': {'video_mode': 'convert', 'video_crf': 23, 'audio_mode': 'convert', 'rate_mode': 'cbr', 'audio_bitrate': '192k', 'audio_sample_rate': 'original', 'audio_channels': '2', 'summary': 'CBR 192k'},
            'mkv': {'video_mode': 'convert', 'video_crf': 23, 'audio_mode': 'convert', 'rate_mode': 'cbr', 'audio_bitrate': '192k', 'audio_sample_rate': 'original', 'audio_channels': '2', 'summary': 'CBR 192k'},
            'last_format_audio': 'mp3',
            'last_format_video': 'mp4',
            'output_mode': 'source',
            'custom_output_path': ''
        }
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
                    return defaults
            except: return defaults
        return defaults

    def _save_config(self):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.settings_store, f, indent=4)
        except: pass

    def _init_menu_bar(self):
        menubar = wx.MenuBar()
        file_menu = wx.Menu()
        item_add = file_menu.Append(wx.ID_OPEN, _("&Add Files...") + "\tCtrl+O")
        # CORRECTION A02 : On garde la référence pour le bind
        item_add_folder = file_menu.Append(wx.ID_ANY, _("Add &Folder..."))
        file_menu.AppendSeparator()
        item_exit = file_menu.Append(wx.ID_EXIT, _("E&xit") + "\tAlt+F4")
        
        edit_menu = wx.Menu()
        self.item_clear = edit_menu.Append(wx.ID_ANY, _("&Clear List") + "\tAlt+C")
        self.item_remove = edit_menu.Append(wx.ID_ANY, _("Remove &Selected") + "\tDel")
        edit_menu.AppendSeparator()
        item_prefs = edit_menu.Append(wx.ID_PREFERENCES, _("Preferences"))
        
        help_menu = wx.Menu()
        item_about = help_menu.Append(wx.ID_ABOUT, _("&About"))

        self.Bind(wx.EVT_MENU, self.on_add_files, item_add)
        # CORRECTION A02 : Le Bind manquant !
        self.Bind(wx.EVT_MENU, self.on_add_folder, item_add_folder)
        self.Bind(wx.EVT_MENU, self.on_exit, item_exit)
        self.Bind(wx.EVT_MENU, self.on_clear_list, self.item_clear)
        self.Bind(wx.EVT_MENU, self.on_remove_selected, self.item_remove)
        self.Bind(wx.EVT_MENU, self.on_preferences, item_prefs)
        self.Bind(wx.EVT_MENU, self.on_about, item_about)

        menubar.Append(file_menu, _("&File"))
        menubar.Append(edit_menu, _("&Edit"))
        menubar.Append(help_menu, _("&Help"))
        self.SetMenuBar(menubar)

    def _init_ui(self):
        self.panel = wx.Panel(self)
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.empty_panel = wx.Panel(self.panel)
        self.empty_msg = _("No files selected.\n\nPress Ctrl+O to add files\nor Drag & Drop them here.")
        empty_sizer = wx.BoxSizer(wx.VERTICAL)
        self.lbl_empty = wx.StaticText(self.empty_panel, label=self.empty_msg)
        self.lbl_empty.SetFont(wx.Font(14, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        empty_sizer.AddStretchSpacer()
        empty_sizer.Add(self.lbl_empty, 0, wx.ALIGN_CENTER | wx.ALL, 20)
        empty_sizer.AddStretchSpacer()
        self.empty_panel.SetSizer(empty_sizer)
        
        self.content_panel = wx.Panel(self.panel)
        self.content_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.notebook = wx.Notebook(self.content_panel)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_changed)
        
        self.panel_audio_list = FileListPanel(self.content_panel, _("Audio files list"))
        self.panel_video_list = FileListPanel(self.content_panel, _("Video files list"))
        
        self.panel_audio_list.list_ctrl.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        self.panel_video_list.list_ctrl.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        
        controls_box = wx.StaticBoxSizer(wx.VERTICAL, self.content_panel, label=_("Conversion Settings"))
        
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.lbl_fmt = wx.StaticText(self.content_panel, label=_("Convert to:"))
        self.combo_format = wx.Choice(self.content_panel)
        self.combo_format.Bind(wx.EVT_CHOICE, self.on_format_changed)
        self.btn_settings = wx.Button(self.content_panel, label=_("&Settings / Quality..."))
        self.btn_settings.Bind(wx.EVT_BUTTON, self.on_open_settings)
        row1.Add(self.lbl_fmt, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        row1.Add(self.combo_format, 1, wx.EXPAND | wx.RIGHT, 10)
        row1.Add(self.btn_settings, 0)
        controls_box.Add(row1, 0, wx.EXPAND | wx.ALL, 5)

        self.gauge = wx.Gauge(self.content_panel, range=100, size=(250, 20))
        controls_box.Add(self.gauge, 0, wx.EXPAND | wx.TOP, 10)
        self.gauge.Hide()

        self.lbl_progress = wx.StaticText(self.content_panel, label="")
        controls_box.Add(self.lbl_progress, 0, wx.EXPAND | wx.TOP, 5)
        self.lbl_progress.Hide()
        
        self.btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_convert = wx.Button(self.content_panel, label=_("&Start Conversion"))
        self.btn_convert.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.btn_convert.Bind(wx.EVT_BUTTON, self.on_convert)
        self.btn_stop = wx.Button(self.content_panel, label=_("Stop"))
        self.btn_stop.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.btn_stop.SetForegroundColour(wx.Colour(200, 0, 0))
        self.btn_stop.Bind(wx.EVT_BUTTON, self.on_stop)
        self.btn_stop.Hide()
        self.btn_sizer.Add(self.btn_convert, 1, wx.EXPAND)
        self.btn_sizer.Add(self.btn_stop, 1, wx.EXPAND)
        
        controls_box.Add(self.btn_sizer, 0, wx.EXPAND | wx.TOP, 10)
        
        self.content_sizer.Add(controls_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.content_panel.SetSizer(self.content_sizer)
        self.main_sizer.Add(self.empty_panel, 1, wx.EXPAND)
        self.main_sizer.Add(self.content_panel, 1, wx.EXPAND)
        self.panel.SetSizer(self.main_sizer)

    def _init_accessibility(self):
        self.panel.SetName(_("Main panel"))
        self.notebook.SetName(_("File categories"))
        self.empty_panel.SetName(_("Empty file list panel"))
        self.lbl_empty.SetName(_("No files selected information"))

        self.lbl_fmt.SetName(_("Convert to"))
        self.combo_format.SetName(_("Convert to"))
        self.combo_format.SetToolTip(_("Select the target output format."))
        self.btn_settings.SetName(_("Settings and quality"))
        self.btn_settings.SetToolTip(_("Open format-specific settings."))

        self.gauge.SetName(_("Conversion progress percentage"))
        self.gauge.SetToolTip(_("Shows conversion progress from 0 to 100 percent."))
        self.lbl_progress.SetName(_("Conversion progress details"))

        self.btn_convert.SetName(_("Start conversion"))
        self.btn_stop.SetName(_("Stop conversion"))

    def _update_combo_format_accessible_name(self):
        # Keep a stable control name; selected value is announced separately by the combo itself.
        self.combo_format.SetName(_("Convert to"))

    def _set_status(self, message):
        if self.GetStatusBar():
            self.SetStatusText(message)

    # --- CORRECTION A02 : AJOUT DE LA FONCTION ---
    def on_add_folder(self, event):
        if self.is_converting: return
        with wx.DirDialog(self, _("Select a folder to add"), style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL: return
            folder_path = dlg.GetPath()
            
            files_to_add = []
            valid_exts = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm']
            
            wx.BeginBusyCursor()
            for root, dirs, files in os.walk(folder_path):
                for f in files:
                    if os.path.splitext(f)[1].lower() in valid_exts:
                        files_to_add.append(os.path.join(root, f))
            
            if files_to_add:
                self._process_added_files(files_to_add)
                self._set_status(f"{len(files_to_add)} " + _("file(s) added from folder."))
            else:
                wx.MessageBox(_("No compatible media files found in this folder."), _("Info"))
                self._set_status(_("No compatible media files found in this folder."))
            
            wx.EndBusyCursor()

    def on_context_menu(self, event):
        if self.is_converting: return
        
        if self.current_tab == 'audio':
            lst = self.panel_audio_list.list_ctrl
        else:
            lst = self.panel_video_list.list_ctrl
            
        index = lst.GetFirstSelected()
        if index == -1: return

        idx_fmt = self.combo_format.GetSelection()
        if idx_fmt == wx.NOT_FOUND: return
        fmt_key = self.current_fmt_keys_active[idx_fmt]
        
        menu = wx.Menu()
        item_tracks = menu.Append(wx.ID_ANY, _("Manage Tracks..."))
        
        if fmt_key not in ['mkv', 'mp4', 'mov']:
            item_tracks.Enable(False)
            item_tracks.SetItemLabel(_("Manage Tracks...") + " (MKV/MP4 only)")
        
        self.Bind(wx.EVT_MENU, lambda e: self.on_open_track_manager(index), item_tracks)
        
        self.PopupMenu(menu)
        menu.Destroy()

    def on_open_track_manager(self, index):
        if self.current_tab == 'audio':
            meta = self.audio_data[index]
        else:
            meta = self.video_data[index]
            
        dlg = TrackManagerDialog(self, meta)
        if dlg.ShowModal() == wx.ID_OK:
            config = dlg.get_configuration()
            meta.track_settings = config 
            
            if self.current_tab == 'audio':
                self.panel_audio_list.list_ctrl.SetItem(index, 2, _("Ready") + " (+Tracks)")
            else:
                self.panel_video_list.list_ctrl.SetItem(index, 2, _("Ready") + " (+Tracks)")
                
        dlg.Destroy()

    def on_preferences(self, event):
        dlg = PreferencesDialog(self, self.settings_store)
        if dlg.ShowModal() == wx.ID_OK:
            new_prefs = dlg.get_settings()
            self.settings_store.update(new_prefs)
            self._save_config()
        dlg.Destroy()

    def _update_layout_strategy(self):
        count_audio = len(self.audio_data)
        count_video = len(self.video_data)
        self.notebook.Hide()
        self.panel_audio_list.Hide()
        self.panel_video_list.Hide()
        self.content_sizer.Detach(self.notebook)
        self.content_sizer.Detach(self.panel_audio_list)
        self.content_sizer.Detach(self.panel_video_list)
        while self.notebook.GetPageCount() > 0: self.notebook.RemovePage(0)
        if count_audio > 0 and count_video > 0:
            self.panel_audio_list.Reparent(self.notebook)
            self.panel_video_list.Reparent(self.notebook)
            self.notebook.AddPage(self.panel_audio_list, _("Audio") + f" ({count_audio})")
            self.notebook.AddPage(self.panel_video_list, _("Video") + f" ({count_video})")
            self.notebook.Show()
            self.panel_audio_list.Show()
            self.panel_video_list.Show()
            self.content_sizer.Insert(0, self.notebook, 1, wx.EXPAND | wx.ALL, 5)
            if self.current_tab == 'video': self.notebook.SetSelection(1)
            else: self.notebook.SetSelection(0)
        elif count_audio > 0:
            self.current_tab = 'audio'
            self.panel_audio_list.Reparent(self.content_panel)
            self.panel_audio_list.Show()
            self.content_sizer.Insert(0, self.panel_audio_list, 1, wx.EXPAND | wx.ALL, 10)
        elif count_video > 0:
            self.current_tab = 'video'
            self.panel_video_list.Reparent(self.content_panel)
            self.panel_video_list.Show()
            self.content_sizer.Insert(0, self.panel_video_list, 1, wx.EXPAND | wx.ALL, 10)
        self.content_panel.Layout()
        self._update_formats_dropdown()

    def _update_formats_dropdown(self):
        if self.current_tab == 'audio':
            keys = self.audio_formats_keys
            displays = self.audio_formats_display
            last_used = self.settings_store.get('last_format_audio', 'mp3')
        else:
            keys = self.video_formats_keys
            displays = self.video_formats_display
            last_used = self.settings_store.get('last_format_video', 'mp4')
        self.current_fmt_keys_active = keys 
        choices = []
        target_selection_index = 0
        for i, key in enumerate(keys):
            label = displays[i]
            if "Extract" in label:
                if "MP3" in label: label = _("MP3 - Audio (Extract)")
                if "AAC" in label: label = _("AAC - Audio (Extract)")
            elif "WAV" in label: label = _("WAV - Audio (Lossless)")
            elif "FLAC" in label: label = _("FLAC - Audio (Lossless)")
            elif "ALAC" in label: label = _("ALAC - Audio (Apple Lossless)")
            elif "AAC" in label: label = _("AAC - Audio (M4A)")
            elif "OGG" in label: label = _("OGG - Audio (Vorbis)")
            elif "WMA" in label: label = _("WMA - Audio (Legacy)")
                
            saved = self.settings_store.get(key, {})
            summary = saved.get('summary', '')
            if summary: choices.append(f"{label} [{summary}]")
            else: choices.append(label)
            if key == last_used: target_selection_index = i
        self.combo_format.Set(choices)
        if choices:
            self.combo_format.SetSelection(target_selection_index)
        self._update_combo_format_accessible_name()

    def on_tab_changed(self, event):
        sel = self.notebook.GetSelection()
        if sel == 0: self.current_tab = 'audio'
        else: self.current_tab = 'video'
        self._update_formats_dropdown()
        if self.current_tab == 'audio':
            self._set_status(_("Audio tab selected."))
        else:
            self._set_status(_("Video tab selected."))
        event.Skip()

    def _update_ui_state(self):
        has_files = (len(self.audio_data) + len(self.video_data)) > 0
        if self.is_converting:
            self.item_clear.Enable(False)
            self.item_remove.Enable(False)
            return

        if has_files:
            self.empty_panel.Hide()
            self._update_layout_strategy()
            self.content_panel.Show()
            self.item_clear.Enable(True)
            self.item_remove.Enable(True)
            self._set_status(
                f"{len(self.audio_data)} " + _("audio file(s), ") +
                f"{len(self.video_data)} " + _("video file(s) loaded.")
            )
        else:
            self.content_panel.Hide()
            self.empty_panel.Show()
            self.item_clear.Enable(False)
            self.item_remove.Enable(False)
            wx.CallAfter(self.empty_panel.SetFocus)
            self._set_status(_("No files loaded."))
        self.panel.Layout()
        self.Refresh()

    def on_add_files(self, event):
        if self.is_converting: return
        with wx.FileDialog(self, _("Open Media"), wildcard="Media Files|*.*", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL: return
            self._process_added_files(dlg.GetPaths())

    def _process_added_files(self, paths):
        wx.BeginBusyCursor()
        added_count = 0
        for path in paths:
            meta = self.prober.analyze(path)
            meta.track_settings = None 
            
            if meta.has_video:
                self.video_data.append(meta)
                target_list = self.panel_video_list.list_ctrl
            else:
                self.audio_data.append(meta)
                target_list = self.panel_audio_list.list_ctrl
            index = target_list.GetItemCount()
            target_list.InsertItem(index, meta.filename)
            target_list.SetItem(index, 1, meta.get_summary())
            target_list.SetItem(index, 2, _("Ready"))
            added_count += 1
        wx.EndBusyCursor()
        self._update_ui_state()
        if added_count:
            self._set_status(f"{added_count} " + _("file(s) added."))

    def on_clear_list(self, event):
        if self.is_converting: return
        self.audio_data = []
        self.video_data = []
        self.panel_audio_list.list_ctrl.DeleteAllItems()
        self.panel_video_list.list_ctrl.DeleteAllItems()
        self._update_ui_state()
        self._set_status(_("List cleared."))

    # CORRECTION A03 : Support de la sélection multiple
    def on_remove_selected(self, event):
        if self.is_converting: return
        if self.current_tab == 'audio':
            lst = self.panel_audio_list.list_ctrl
            data = self.audio_data
        else:
            lst = self.panel_video_list.list_ctrl
            data = self.video_data
            
        # GetNextSelected loop
        selected_indices = []
        idx = lst.GetFirstSelected()
        while idx != -1:
            selected_indices.append(idx)
            idx = lst.GetNextSelected(idx)
            
        # Delete in reverse order to keep indices valid
        removed = 0
        for idx in reversed(selected_indices):
            lst.DeleteItem(idx)
            del data[idx]
            removed += 1
            
        self._update_ui_state()
        if removed:
            self._set_status(f"{removed} " + _("file(s) removed."))

    def on_format_changed(self, event):
        idx = self.combo_format.GetSelection()
        if idx == wx.NOT_FOUND: return
        fmt_key = self.current_fmt_keys_active[idx]
        if self.current_tab == 'audio': self.settings_store['last_format_audio'] = fmt_key
        else: self.settings_store['last_format_video'] = fmt_key
        self._save_config()
        self._update_combo_format_accessible_name()
        self._set_status(_("Output format selected: ") + self.combo_format.GetString(idx))

    def on_open_settings(self, event):
        idx = self.combo_format.GetSelection()
        if idx == wx.NOT_FOUND: return
        fmt_key = self.current_fmt_keys_active[idx]
        
        # Format key est passé à la boite de dialogue pour corrections (WMA...)
        
        if self.current_tab == 'audio': clean = self.audio_formats_display[idx]
        else:
            clean = self.video_formats_display[idx]
            if "Extract" in clean: clean = _(clean)
        
        if "WAV" in clean: clean = _("WAV - Audio (Lossless)")
        elif "FLAC" in clean: clean = _("FLAC - Audio (Lossless)")
        elif "ALAC" in clean: clean = _("ALAC - Audio (Apple Lossless)")
        elif "AAC" in clean: clean = _("AAC - Audio (M4A)")
        elif "OGG" in clean: clean = _("OGG - Audio (Vorbis)")
        elif "WMA" in clean: clean = _("WMA - Audio (Legacy)")
            
        input_ac = ""
        input_has_vid = (self.current_tab == 'video')
        if self.current_tab == 'audio' and self.audio_data: input_ac = self.audio_data[0].audio_codec
        elif self.current_tab == 'video' and self.video_data: input_ac = self.video_data[0].audio_codec
        current_saved = self.settings_store.get(fmt_key, {})
        
        # Passage du fmt_key pour la logique interne
        dlg = SettingsDialog(self, clean, input_has_vid, input_ac, current_saved, fmt_key)
        if dlg.ShowModal() == wx.ID_OK:
            self.settings_store[fmt_key] = dlg.get_settings()
            self._save_config()
            self._update_formats_dropdown()
            self._set_status(_("Settings updated for format: ") + clean)
        dlg.Destroy()

    def on_stop(self, event):
        self.btn_stop.Disable()
        self.btn_stop.SetLabel(_("Stopping..."))
        self.stop_requested = True
        self._set_status(_("Stop requested."))

    def on_close_window(self, event):
        if self.is_converting:
            dlg = wx.MessageDialog(self, 
                                   _("A conversion is currently running.\nDo you really want to stop it and exit?"),
                                   _("Confirm Exit"), 
                                   wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
            
            if dlg.ShowModal() == wx.ID_YES:
                self.stop_requested = True
                self.Destroy()
            else:
                event.Veto()
        else:
            event.Skip()

    def on_convert(self, event):
        if self.current_tab == 'audio':
            data = self.audio_data
            lst = self.panel_audio_list.list_ctrl
        else:
            data = self.video_data
            lst = self.panel_video_list.list_ctrl
        if not data:
            self._set_status(_("No files to convert."))
            return
        idx = self.combo_format.GetSelection()
        if idx == wx.NOT_FOUND: return
        fmt_key = self.current_fmt_keys_active[idx]
        settings = self.settings_store.get(fmt_key, {})
        
        output_mode = self.settings_store.get('output_mode', 'source')
        custom_out = None
        if output_mode == 'source': custom_out = None
        elif output_mode == 'custom':
            custom_out = self.settings_store.get('custom_output_path', '')
            if not custom_out or not os.path.exists(custom_out):
                wx.MessageBox(_("Custom folder not found. Using source folder."), _("Warning"), wx.ICON_WARNING)
                custom_out = None
        elif output_mode == 'ask':
            with wx.DirDialog(self, _("Select Output Folder"), style=wx.DD_DEFAULT_STYLE) as dlg:
                if dlg.ShowModal() == wx.ID_OK: custom_out = dlg.GetPath()
                else: return 

        self.is_converting = True
        self.stop_requested = False
        
        self.btn_convert.Hide()
        self.btn_stop.Show()
        self.btn_stop.Enable(True)
        self.btn_stop.SetLabel(_("Stop"))
        
        self.gauge.SetValue(0)
        self.gauge.Show()
        self.lbl_progress.SetLabel(_("Preparing conversion..."))
        self.lbl_progress.Show()
        self.content_panel.Layout()
        self._set_status(_("Conversion started."))
        
        self._update_ui_state() 
        
        t = threading.Thread(target=self._worker_thread, args=(data, fmt_key, settings, lst, custom_out))
        t.daemon = True 
        t.start()

    def _worker_thread(self, data_list, fmt, settings, list_ctrl_obj, output_dir):
        errors_count = 0 
        
        for i, meta in enumerate(data_list):
            if self.stop_requested: break
                
            wx.CallAfter(list_ctrl_obj.SetItem, i, 2, _("Converting..."))
            def update_progress(pct):
                progress_txt = f"{_('Converting...')} {pct}%"
                wx.CallAfter(self.gauge.SetValue, pct)
                wx.CallAfter(self.lbl_progress.SetLabel, progress_txt)
                wx.CallAfter(list_ctrl_obj.SetItem, i, 2, progress_txt)
                wx.CallAfter(self._set_status, progress_txt)

            def check_stop(): return self.stop_requested

            task = ConversionTask(meta, fmt, settings, output_dir=output_dir)
            try:
                task.run(progress_callback=update_progress, stop_check_callback=check_stop)
                wx.CallAfter(list_ctrl_obj.SetItem, i, 2, _("Done"))
                wx.CallAfter(self._set_status, _("File converted successfully."))
            except Exception as e:
                if str(e) == "Stopped by user":
                    wx.CallAfter(list_ctrl_obj.SetItem, i, 2, _("Stopped by user"))
                    wx.CallAfter(self._set_status, _("Conversion stopped by user."))
                    break
                else:
                    errors_count += 1 
                    print(e)
                    wx.CallAfter(list_ctrl_obj.SetItem, i, 2, _("Error"))
                    wx.CallAfter(self._set_status, _("An error occurred during conversion."))
        
        wx.CallAfter(self._on_batch_complete, errors_count)

    def _on_batch_complete(self, errors_count):
        self.is_converting = False
        self.stop_requested = False
        
        self.btn_stop.Hide()
        self.btn_convert.Show()
        self.gauge.Hide()
        self.lbl_progress.Hide()
        self.content_panel.Layout()
        
        self._update_ui_state()
        
        if self.btn_stop.GetLabel() != _("Stopping..."):
            if errors_count == 0:
                wx.MessageBox(_("All tasks completed!"), _("Success"))
                self._set_status(_("All tasks completed successfully."))
            else:
                msg = _("All tasks completed!") + f"\n\n{errors_count} " + _("Error")
                wx.MessageBox(msg, _("Done"), wx.ICON_WARNING)
                self._set_status(f"{errors_count} " + _("error(s) during conversion."))

    def on_exit(self, e): self.Close()
    def on_about(self, e): wx.MessageBox(_("Universal Transcoder V1.0\nPowered by FFmpeg & wxPython"), _("About"))
