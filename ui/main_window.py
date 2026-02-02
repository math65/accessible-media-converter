import wx
import os
import threading
import json

from core import FileProber, ConversionTask
from ui.settings_dialog import SettingsDialog

class MainWindow(wx.Frame):
    def __init__(self):
        super().__init__(None, title=_("Universal Transcoder"), size=(800, 600))
        
        self.prober = FileProber()
        self.files_data = []
        
        # --- CONFIGURATION ---
        app_data = os.getenv('APPDATA')
        config_dir = os.path.join(app_data, "UniversalTranscoder")
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
            
        self.config_path = os.path.join(config_dir, "config.json")
        self.settings_store = self._load_config()
        
        self._init_menu_bar()
        self._init_ui()
        self._update_ui_state()
        self.Centre()

    def _load_config(self):
        defaults = {
            'mp3': {'audio_mode': 'convert', 'rate_mode': 'cbr', 'audio_bitrate': '192k', 'summary': 'CBR 192k'},
            'aac': {'audio_mode': 'convert', 'rate_mode': 'cbr', 'audio_bitrate': '192k', 'summary': 'CBR 192k'},
            'mp4': {'video_mode': 'convert', 'video_crf': 23, 'audio_mode': 'convert', 'rate_mode': 'cbr', 'audio_bitrate': '192k', 'summary': 'CBR 192k'},
            'mkv': {'video_mode': 'convert', 'video_crf': 23, 'audio_mode': 'convert', 'rate_mode': 'cbr', 'audio_bitrate': '192k', 'summary': 'CBR 192k'}
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
        item_add_dir = file_menu.Append(wx.ID_ANY, _("Add &Folder..."))
        file_menu.AppendSeparator()
        item_exit = file_menu.Append(wx.ID_EXIT, _("E&xit") + "\tAlt+F4")
        
        edit_menu = wx.Menu()
        self.item_clear = edit_menu.Append(wx.ID_ANY, _("&Clear List") + "\tAlt+C")
        self.item_remove = edit_menu.Append(wx.ID_ANY, _("Remove &Selected") + "\tDel")
        
        help_menu = wx.Menu()
        item_about = help_menu.Append(wx.ID_ABOUT, _("&About"))

        self.Bind(wx.EVT_MENU, self.on_add_files, item_add)
        self.Bind(wx.EVT_MENU, self.on_exit, item_exit)
        self.Bind(wx.EVT_MENU, self.on_clear_list, self.item_clear)
        self.Bind(wx.EVT_MENU, self.on_remove_selected, self.item_remove)
        self.Bind(wx.EVT_MENU, self.on_about, item_about)

        menubar.Append(file_menu, _("&File"))
        menubar.Append(edit_menu, _("&Edit"))
        menubar.Append(help_menu, _("&Help"))
        self.SetMenuBar(menubar)

    def _init_ui(self):
        self.panel = wx.Panel(self)
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)

        # 1. PANNEAU ÉTAT VIDE (Focus NVDA amélioré)
        self.empty_panel = wx.Panel(self.panel)
        self.empty_msg = _("No files selected.\n\nPress Ctrl+O to add files\nor Drag & Drop them here.")
        # Pour que NVDA lise le message dès qu'on force le focus sur le panel
        self.empty_panel.SetName(self.empty_msg)

        empty_sizer = wx.BoxSizer(wx.VERTICAL)
        self.lbl_empty = wx.StaticText(self.empty_panel, label=self.empty_msg)
        self.lbl_empty.SetFont(wx.Font(14, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        
        empty_sizer.AddStretchSpacer()
        empty_sizer.Add(self.lbl_empty, 0, wx.ALIGN_CENTER | wx.ALL, 20)
        empty_sizer.AddStretchSpacer()
        self.empty_panel.SetSizer(empty_sizer)

        # 2. PANNEAU CONTENU
        self.content_panel = wx.Panel(self.panel)
        content_sizer = wx.BoxSizer(wx.VERTICAL)

        self.list_ctrl = wx.ListCtrl(self.content_panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self.list_ctrl.InsertColumn(0, _("Filename"), width=300)
        self.list_ctrl.InsertColumn(1, _("Details (Codec/Bitrate)"), width=250)
        self.list_ctrl.InsertColumn(2, _("Status"), width=150)
        
        content_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 10)

        controls_box = wx.StaticBoxSizer(wx.VERTICAL, self.content_panel, label=_("Conversion Settings"))
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_fmt = wx.StaticText(self.content_panel, label=_("Convert to:"))
        
        self.base_formats = ["MP3 - Audio", "AAC - Audio", "MP4 - Video (H.264)", "MKV - Video"]
        self.fmt_keys = ["mp3", "aac", "mp4", "mkv"]
        
        self.combo_format = wx.Choice(self.content_panel, choices=self.base_formats)
        self.combo_format.SetSelection(0)
        self.combo_format.Bind(wx.EVT_CHOICE, self.on_format_changed)
        
        self.btn_settings = wx.Button(self.content_panel, label=_("&Settings / Quality..."))
        self.btn_settings.Bind(wx.EVT_BUTTON, self.on_open_settings)
        
        row1.Add(lbl_fmt, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        row1.Add(self.combo_format, 1, wx.EXPAND | wx.RIGHT, 10)
        row1.Add(self.btn_settings, 0)
        controls_box.Add(row1, 0, wx.EXPAND | wx.ALL, 5)

        self.btn_convert = wx.Button(self.content_panel, label=_("&Start Conversion"))
        self.btn_convert.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.btn_convert.Bind(wx.EVT_BUTTON, self.on_convert)
        
        controls_box.Add(self.btn_convert, 0, wx.EXPAND | wx.TOP, 10)
        content_sizer.Add(controls_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.content_panel.SetSizer(content_sizer)

        self.main_sizer.Add(self.empty_panel, 1, wx.EXPAND)
        self.main_sizer.Add(self.content_panel, 1, wx.EXPAND)
        self.panel.SetSizer(self.main_sizer)
        
        self.on_format_changed(None)

    def _update_ui_state(self):
        has_files = len(self.files_data) > 0
        if has_files:
            self.empty_panel.Hide()
            self.content_panel.Show()
            self.item_clear.Enable(True)
            self.item_remove.Enable(True)
            self.panel.Layout()
            # On force le focus sur la liste pour NVDA
            wx.CallAfter(self.list_ctrl.SetFocus)
            if self.list_ctrl.GetItemCount() > 0:
                wx.CallAfter(self.list_ctrl.Select, 0)
        else:
            self.content_panel.Hide()
            self.empty_panel.Show()
            self.item_clear.Enable(False)
            self.item_remove.Enable(False)
            self.panel.Layout()
            # On force le focus sur le panneau vide pour que NVDA lise les instructions
            wx.CallAfter(self.empty_panel.SetFocus)
        self.Refresh()

    def on_add_files(self, event):
        with wx.FileDialog(self, _("Open Media"), wildcard="Media Files|*.mp4;*.mkv;*.avi;*.mp3;*.wav;*.flac;*.mov|All Files|*.*",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL: return
            self._process_added_files(dlg.GetPaths())

    def _process_added_files(self, paths):
        wx.BeginBusyCursor()
        for path in paths:
            meta = self.prober.analyze(path)
            self.files_data.append(meta)
            index = self.list_ctrl.GetItemCount()
            self.list_ctrl.InsertItem(index, meta.filename)
            self.list_ctrl.SetItem(index, 1, meta.get_summary())
            self.list_ctrl.SetItem(index, 2, _("Ready"))
        wx.EndBusyCursor()
        self._update_ui_state()

    def on_clear_list(self, event):
        self.files_data = []
        self.list_ctrl.DeleteAllItems()
        self._update_ui_state()

    def on_remove_selected(self, event):
        selected_idx = self.list_ctrl.GetFirstSelected()
        if selected_idx != -1:
            self.list_ctrl.DeleteItem(selected_idx)
            del self.files_data[selected_idx]
            self._update_ui_state()

    def on_format_changed(self, event):
        idx = self.combo_format.GetSelection()
        fmt_key = self.fmt_keys[idx]
        saved = self.settings_store.get(fmt_key, {})
        summary = saved.get('summary', '')
        clean_label = self.base_formats[idx]
        if summary:
            new_label = f"{clean_label} [{summary}]"
            self.combo_format.SetString(idx, new_label)
        else:
            self.combo_format.SetString(idx, clean_label)
        self.combo_format.SetSelection(idx)

    def on_open_settings(self, event):
        idx = self.combo_format.GetSelection()
        fmt_key = self.fmt_keys[idx]
        clean_label = self.base_formats[idx]
        input_audio_codec = ""
        input_has_video = False
        if self.files_data:
            input_audio_codec = self.files_data[0].audio_codec
            input_has_video = self.files_data[0].has_video
        current_saved = self.settings_store.get(fmt_key, {})
        dlg = SettingsDialog(self, clean_label, input_has_video, input_audio_codec, current_saved)
        if dlg.ShowModal() == wx.ID_OK:
            self.settings_store[fmt_key] = dlg.get_settings()
            self._save_config()
            self.on_format_changed(None)
        dlg.Destroy()

    def on_convert(self, event):
        if not self.files_data: return
        idx = self.combo_format.GetSelection()
        fmt_key = self.fmt_keys[idx]
        settings = self.settings_store.get(fmt_key, {})
        self.btn_convert.Disable()
        t = threading.Thread(target=self._worker_thread, args=(fmt_key, settings))
        t.daemon = True 
        t.start()

    def _worker_thread(self, fmt, settings):
        for i, meta in enumerate(self.files_data):
            wx.CallAfter(self.list_ctrl.SetItem, i, 2, _("Converting..."))
            task = ConversionTask(meta.full_path, fmt, settings)
            try:
                task.run()
                wx.CallAfter(self.list_ctrl.SetItem, i, 2, _("Done"))
            except Exception as e:
                wx.CallAfter(self.list_ctrl.SetItem, i, 2, _("Error"))
        wx.CallAfter(self._on_batch_complete)

    def _on_batch_complete(self):
        self.btn_convert.Enable()
        wx.MessageBox(_("All tasks completed!"), _("Success"))

    def on_exit(self, e): self.Close()
    def on_about(self, e):
        wx.MessageBox(_("Universal Transcoder V1.0\nPowered by FFmpeg & wxPython"), _("About"))