import wx
import os
import threading
import json

from core import FileProber, ConversionTask
from ui.settings_dialog import SettingsDialog
from ui.preferences_dialog import PreferencesDialog

class FileListPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self.list_ctrl.InsertColumn(0, _("Filename"), width=300)
        self.list_ctrl.InsertColumn(1, _("Details (Codec/Bitrate)"), width=250)
        self.list_ctrl.InsertColumn(2, _("Status"), width=150)
        self.sizer.Add(self.list_ctrl, 1, wx.EXPAND)
        self.SetSizer(self.sizer)

class MainWindow(wx.Frame):
    def __init__(self):
        super().__init__(None, title=_("Universal Transcoder"), size=(900, 650))
        
        # --- ETAT INTERNE ---
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
        self.audio_formats_display = ["MP3 - Audio", "AAC - Audio"]
        self.audio_formats_keys = ["mp3", "aac"]
        self.video_formats_display = ["MP4 - Video (H.264)", "MKV - Video", "MP3 - Audio (Extract)", "AAC - Audio (Extract)"]
        self.video_formats_keys = ["mp4", "mkv", "mp3", "aac"]
        self.current_tab = "audio"
        self._init_menu_bar()
        self._init_ui()
        self._update_ui_state()
        self.Centre()
        
        # INTERCEPTION DE LA FERMETURE
        self.Bind(wx.EVT_CLOSE, self.on_close_window)

    def _load_config(self):
        defaults = {
            'mp3': {'audio_mode': 'convert', 'rate_mode': 'cbr', 'audio_bitrate': '192k', 'summary': 'CBR 192k'},
            'aac': {'audio_mode': 'convert', 'rate_mode': 'cbr', 'audio_bitrate': '192k', 'summary': 'CBR 192k'},
            'mp4': {'video_mode': 'convert', 'video_crf': 23, 'audio_mode': 'convert', 'rate_mode': 'cbr', 'audio_bitrate': '192k', 'summary': 'CBR 192k'},
            'mkv': {'video_mode': 'convert', 'video_crf': 23, 'audio_mode': 'convert', 'rate_mode': 'cbr', 'audio_bitrate': '192k', 'summary': 'CBR 192k'},
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
        item_add_dir = file_menu.Append(wx.ID_ANY, _("Add &Folder..."))
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
        self.empty_panel.SetName(self.empty_msg)
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
        self.panel_audio_list = FileListPanel(self.content_panel)
        self.panel_video_list = FileListPanel(self.content_panel)
        
        controls_box = wx.StaticBoxSizer(wx.VERTICAL, self.content_panel, label=_("Conversion Settings"))
        
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_fmt = wx.StaticText(self.content_panel, label=_("Convert to:"))
        self.combo_format = wx.Choice(self.content_panel)
        self.combo_format.Bind(wx.EVT_CHOICE, self.on_format_changed)
        self.btn_settings = wx.Button(self.content_panel, label=_("&Settings / Quality..."))
        self.btn_settings.Bind(wx.EVT_BUTTON, self.on_open_settings)
        row1.Add(lbl_fmt, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        row1.Add(self.combo_format, 1, wx.EXPAND | wx.RIGHT, 10)
        row1.Add(self.btn_settings, 0)
        controls_box.Add(row1, 0, wx.EXPAND | wx.ALL, 5)

        self.gauge = wx.Gauge(self.content_panel, range=100, size=(250, 20))
        controls_box.Add(self.gauge, 0, wx.EXPAND | wx.TOP, 10)
        self.gauge.Hide()
        
        # --- BOUTONS START / STOP ---
        self.btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.btn_convert = wx.Button(self.content_panel, label=_("&Start Conversion"))
        self.btn_convert.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.btn_convert.Bind(wx.EVT_BUTTON, self.on_convert)
        
        self.btn_stop = wx.Button(self.content_panel, label=_("Stop"))
        self.btn_stop.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.btn_stop.SetForegroundColour(wx.Colour(200, 0, 0)) # Rouge
        self.btn_stop.Bind(wx.EVT_BUTTON, self.on_stop)
        self.btn_stop.Hide() # Caché au début
        
        self.btn_sizer.Add(self.btn_convert, 1, wx.EXPAND)
        self.btn_sizer.Add(self.btn_stop, 1, wx.EXPAND) # Sera caché
        
        controls_box.Add(self.btn_sizer, 0, wx.EXPAND | wx.TOP, 10)
        
        self.content_sizer.Add(controls_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.content_panel.SetSizer(self.content_sizer)
        self.main_sizer.Add(self.empty_panel, 1, wx.EXPAND)
        self.main_sizer.Add(self.content_panel, 1, wx.EXPAND)
        self.panel.SetSizer(self.main_sizer)

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
            saved = self.settings_store.get(key, {})
            summary = saved.get('summary', '')
            if summary: choices.append(f"{label} [{summary}]")
            else: choices.append(label)
            if key == last_used: target_selection_index = i
        self.combo_format.Set(choices)
        if choices: self.combo_format.SetSelection(target_selection_index)

    def on_tab_changed(self, event):
        sel = self.notebook.GetSelection()
        if sel == 0: self.current_tab = 'audio'
        else: self.current_tab = 'video'
        self._update_formats_dropdown()
        event.Skip()

    def _update_ui_state(self):
        has_files = (len(self.audio_data) + len(self.video_data)) > 0
        # Désactiver l'édition si conversion en cours
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
        else:
            self.content_panel.Hide()
            self.empty_panel.Show()
            self.item_clear.Enable(False)
            self.item_remove.Enable(False)
            wx.CallAfter(self.empty_panel.SetFocus)
        self.panel.Layout()
        self.Refresh()

    def on_add_files(self, event):
        if self.is_converting: return # Sécurité
        with wx.FileDialog(self, _("Open Media"), wildcard="Media Files|*.*", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL: return
            self._process_added_files(dlg.GetPaths())

    def _process_added_files(self, paths):
        wx.BeginBusyCursor()
        for path in paths:
            meta = self.prober.analyze(path)
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
        wx.EndBusyCursor()
        self._update_ui_state()

    def on_clear_list(self, event):
        if self.is_converting: return
        self.audio_data = []
        self.video_data = []
        self.panel_audio_list.list_ctrl.DeleteAllItems()
        self.panel_video_list.list_ctrl.DeleteAllItems()
        self._update_ui_state()

    def on_remove_selected(self, event):
        if self.is_converting: return
        if self.current_tab == 'audio':
            lst = self.panel_audio_list.list_ctrl
            data = self.audio_data
        else:
            lst = self.panel_video_list.list_ctrl
            data = self.video_data
        selected_idx = lst.GetFirstSelected()
        if selected_idx != -1:
            lst.DeleteItem(selected_idx)
            del data[selected_idx]
            self._update_ui_state()

    def on_format_changed(self, event):
        idx = self.combo_format.GetSelection()
        if idx == wx.NOT_FOUND: return
        fmt_key = self.current_fmt_keys_active[idx]
        if self.current_tab == 'audio': self.settings_store['last_format_audio'] = fmt_key
        else: self.settings_store['last_format_video'] = fmt_key
        self._save_config()

    def on_open_settings(self, event):
        idx = self.combo_format.GetSelection()
        if idx == wx.NOT_FOUND: return
        fmt_key = self.current_fmt_keys_active[idx]
        if self.current_tab == 'audio': clean = self.audio_formats_display[idx]
        else:
            clean = self.video_formats_display[idx]
            if "Extract" in clean: clean = _(clean)
        input_ac = ""
        input_has_vid = (self.current_tab == 'video')
        if self.current_tab == 'audio' and self.audio_data: input_ac = self.audio_data[0].audio_codec
        elif self.current_tab == 'video' and self.video_data: input_ac = self.video_data[0].audio_codec
        current_saved = self.settings_store.get(fmt_key, {})
        dlg = SettingsDialog(self, clean, input_has_vid, input_ac, current_saved)
        if dlg.ShowModal() == wx.ID_OK:
            self.settings_store[fmt_key] = dlg.get_settings()
            self._save_config()
            self._update_formats_dropdown()
        dlg.Destroy()

    # --- NOUVEAU : GESTION START / STOP / CLOSE ---

    def on_stop(self, event):
        """Appelé quand on clique sur le bouton STOP"""
        self.btn_stop.Disable()
        self.btn_stop.SetLabel(_("Stopping..."))
        self.stop_requested = True # Le thread va lire ça

    def on_close_window(self, event):
        """Appelé quand on clique sur la croix de la fenêtre"""
        if self.is_converting:
            # Demande confirmation
            dlg = wx.MessageDialog(self, 
                                   _("A conversion is currently running.\nDo you really want to stop it and exit?"),
                                   _("Confirm Exit"), 
                                   wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
            
            if dlg.ShowModal() == wx.ID_YES:
                self.stop_requested = True
                self.Destroy() # Force la fermeture
            else:
                event.Veto() # On annule la fermeture
        else:
            event.Skip() # Fermeture normale

    def on_convert(self, event):
        if self.current_tab == 'audio':
            data = self.audio_data
            lst = self.panel_audio_list.list_ctrl
        else:
            data = self.video_data
            lst = self.panel_video_list.list_ctrl
        if not data: return
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

        # --- UI START STATE ---
        self.is_converting = True
        self.stop_requested = False
        
        self.btn_convert.Hide() # On cache Start
        self.btn_stop.Show()    # On montre Stop
        self.btn_stop.Enable(True)
        self.btn_stop.SetLabel(_("Stop"))
        
        self.gauge.SetValue(0)
        self.gauge.Show()
        self.content_panel.Layout() # Important pour redessiner les boutons
        
        # On désactive l'ajout de fichiers
        self._update_ui_state() 
        
        t = threading.Thread(target=self._worker_thread, args=(data, fmt_key, settings, lst, custom_out))
        t.daemon = True 
        t.start()

    def _worker_thread(self, data_list, fmt, settings, list_ctrl_obj, output_dir):
        errors_count = 0 
        
        for i, meta in enumerate(data_list):
            # Si on a demandé l'arrêt entre deux fichiers
            if self.stop_requested:
                break
                
            wx.CallAfter(list_ctrl_obj.SetItem, i, 2, _("Converting..."))
            def update_progress(pct):
                wx.CallAfter(self.gauge.SetValue, pct)
                wx.CallAfter(list_ctrl_obj.SetItem, i, 2, f"{_('Converting...')} {pct}%")

            # Callback pour vérifier l'arrêt PENDANT la conversion d'un fichier
            def check_stop():
                return self.stop_requested

            task = ConversionTask(meta.full_path, fmt, settings, duration=meta.duration, output_dir=output_dir)
            try:
                # On passe le callback de vérification
                task.run(progress_callback=update_progress, stop_check_callback=check_stop)
                wx.CallAfter(list_ctrl_obj.SetItem, i, 2, _("Done"))
            except Exception as e:
                # On vérifie si c'est un arrêt volontaire
                if str(e) == "Stopped by user":
                    wx.CallAfter(list_ctrl_obj.SetItem, i, 2, _("Stopped by user"))
                    break # On sort de la boucle for
                else:
                    errors_count += 1 
                    print(e)
                    wx.CallAfter(list_ctrl_obj.SetItem, i, 2, _("Error"))
        
        wx.CallAfter(self._on_batch_complete, errors_count)

    def _on_batch_complete(self, errors_count):
        self.is_converting = False
        self.stop_requested = False
        
        self.btn_stop.Hide()    # On cache Stop
        self.btn_convert.Show() # On remet Start
        self.gauge.Hide()
        self.content_panel.Layout()
        
        self._update_ui_state() # Réactive les menus
        
        if errors_count == 0:
            # On n'affiche le succès que si on n'a pas annulé manuellement
            # (si stop_requested était True, on a breaké la boucle, donc errors_count vaut 0 ou x)
            # Petite astuce : si le label du bouton stop est "Stopping...", c'est qu'on a annulé.
            if self.btn_stop.GetLabel() == _("Stopping..."):
                pass # Pas de popup succès si on a annulé
            else:
                wx.MessageBox(_("All tasks completed!"), _("Success"))
        else:
            msg = _("All tasks completed!") + f"\n\n{errors_count} " + _("Error")
            wx.MessageBox(msg, _("Done"), wx.ICON_WARNING)

    def on_exit(self, e): 
        self.Close()
    def on_about(self, e):
        wx.MessageBox(_("Universal Transcoder V1.0\nPowered by FFmpeg & wxPython"), _("About"))