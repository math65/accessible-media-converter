import wx

class EditableListCtrl(wx.ListCtrl):
    """ListCtrl avec Checkboxes natives"""
    def __init__(self, parent):
        wx.ListCtrl.__init__(self, parent, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self.EnableCheckBoxes(True) 
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated)

    def OnItemActivated(self, event):
        idx = event.GetIndex()
        self.CheckItem(idx, not self.IsItemChecked(idx))

class TrackPanel(wx.Panel):
    """Panneau Master-Detail pour un type de pistes (Audio ou Subs)"""
    def __init__(self, parent, tracks, track_type):
        super().__init__(parent)
        self.track_type = track_type 
        self.tracks_data = [] 
        self.current_selection = -1

        # --- INITIALISATION DES LANGUES ---
        self.LANGUAGES_MAP = {
            "und": _("Undetermined"),
            "fre": _("French"),
            "eng": _("English"),
            "jpn": _("Japanese"),
            "spa": _("Spanish"),
            "ger": _("German"),
            "ita": _("Italian"),
            "por": _("Portuguese"),
            "rus": _("Russian"),
            "chi": _("Chinese"),
            "dut": _("Dutch"),
            "pol": _("Polish"),
            "kor": _("Korean"),
            "hin": _("Hindi"),
            "ara": _("Arabic"),
        }
        self.languages_choices = sorted([(v, k) for k, v in self.LANGUAGES_MAP.items()], key=lambda x: x[0])

        for i, t in enumerate(tracks):
            d = {
                'ui_id': str(i + 1), # ID Fixe (1, 2, 3...) basé sur l'ordre d'origine
                'original_index': t.index,
                'codec_name': t.codec_name,
                'language': t.language if t.language else 'und',
                'title': t.title if t.title else "",
                'keep': True,
                'default': t.is_default(),
                'forced': t.is_forced(),
                'hearing_impaired': t.disposition.get('hearing_impaired', 0) == 1,
                'visual_impaired': t.disposition.get('visual_impaired', 0) == 1,
                'comment': t.disposition.get('comment', 0) == 1
            }
            self.tracks_data.append(d)

        # --- UI LAYOUT ---
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # --- ZONE HAUTE : LA LISTE ---
        self.list_ctrl = EditableListCtrl(self)
        if self.track_type == 'audio':
            self.list_ctrl.SetName(_("Audio tracks list"))
        else:
            self.list_ctrl.SetName(_("Subtitle tracks list"))
        self.list_ctrl.SetToolTip(_("Use Space to keep or remove a track. Use Ctrl+Up and Ctrl+Down to reorder."))
        
        # Colonne ID Fixe
        self.list_ctrl.InsertColumn(0, _("#"), width=30)
        self.list_ctrl.InsertColumn(1, _("Codec"), width=60)
        self.list_ctrl.InsertColumn(2, _("Lang"), width=100)
        self.list_ctrl.InsertColumn(3, _("Title"), width=180)
        self.list_ctrl.InsertColumn(4, _("Flags"), width=150)
        
        self.main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 5)

        # --- ZONE MILIEU : BOUTONS ---
        btn_box = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_up = wx.Button(self, label=_("Move Up") + " (Ctrl+Up)")
        self.btn_down = wx.Button(self, label=_("Move Down") + " (Ctrl+Down)")
        self.btn_up.SetName(_("Move selected track up"))
        self.btn_down.SetName(_("Move selected track down"))
        self.btn_up.Bind(wx.EVT_BUTTON, lambda e: self.move_item(-1))
        self.btn_down.Bind(wx.EVT_BUTTON, lambda e: self.move_item(1))
        
        btn_box.Add(self.btn_up, 0, wx.RIGHT, 5)
        btn_box.Add(self.btn_down, 0)
        self.main_sizer.Add(btn_box, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

        # --- ZONE BASSE : DETAILS ---
        self.detail_box = wx.StaticBox(self, label=_("Track Settings"))
        self.detail_sizer = wx.StaticBoxSizer(self.detail_box, wx.VERTICAL)
        
        grid = wx.FlexGridSizer(rows=3, cols=2, vgap=10, hgap=10)
        grid.AddGrowableCol(1, 1)
        
        # 1. LANGUE
        lbl_lang = wx.StaticText(self, label=_("Language:"))
        self.combo_lang = wx.Choice(self, choices=[x[0] for x in self.languages_choices])
        self.combo_lang.SetName(_("Language"))
        self.combo_lang.SetToolTip(_("Track language"))
        grid.Add(lbl_lang, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.combo_lang, 1, wx.EXPAND)
        
        # 2. TITRE
        lbl_title = wx.StaticText(self, label=_("Track Title:"))
        self.txt_title = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.txt_title.SetName(_("Track title"))
        grid.Add(lbl_title, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.txt_title, 1, wx.EXPAND)
        
        # 3. ATTRIBUTS
        lbl_flags = wx.StaticText(self, label=_("Attributes:"))
        self.flags_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.chk_default = wx.CheckBox(self, label=_("Default"))
        self.chk_forced = wx.CheckBox(self, label=_("Forced"))
        self.chk_default.SetName(_("Set selected track as default"))
        self.chk_forced.SetName(_("Set selected track as forced"))
        self.flags_sizer.Add(self.chk_default, 0, wx.RIGHT, 15)
        self.flags_sizer.Add(self.chk_forced, 0, wx.RIGHT, 15)
        
        self.chk_special = None
        if self.track_type == 'audio':
            self.chk_special = wx.CheckBox(self, label=_("Audio Description"))
        else:
            self.chk_special = wx.CheckBox(self, label=_("Hearing Impaired"))
        self.chk_special.SetName(self.chk_special.GetLabel())
            
        self.flags_sizer.Add(self.chk_special, 0)
        
        grid.Add(lbl_flags, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.flags_sizer, 1, wx.EXPAND)
        
        self.detail_sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 10)
        self.main_sizer.Add(self.detail_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(self.main_sizer)

        # --- BINDINGS ---
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_item_deselected)
        self.list_ctrl.Bind(wx.EVT_KEY_DOWN, self.on_key_down)
        
        self.combo_lang.Bind(wx.EVT_CHOICE, self.on_edit_change)
        self.txt_title.Bind(wx.EVT_TEXT, self.on_edit_change)
        
        self.chk_default.Bind(wx.EVT_CHECKBOX, self.on_flag_change)
        self.chk_forced.Bind(wx.EVT_CHECKBOX, self.on_edit_change)
        self.chk_special.Bind(wx.EVT_CHECKBOX, self.on_edit_change)

        self._fill_list()
        self._enable_details(False)

    def _fill_list(self):
        self.list_ctrl.DeleteAllItems()
        for i, track in enumerate(self.tracks_data):
            # On affiche l'ID FIXE (ui_id) stocké dans les données
            idx = self.list_ctrl.InsertItem(i, track['ui_id']) 
            
            self.list_ctrl.SetItem(idx, 1, track['codec_name'].upper())
            self.list_ctrl.CheckItem(idx, track['keep'])
            self._update_row_display(idx)
            self.list_ctrl.SetItemData(idx, i)

    def _sync_keep_from_ui(self):
        if self.list_ctrl.GetItemCount() != len(self.tracks_data):
            return
        for i, track in enumerate(self.tracks_data):
            track['keep'] = self.list_ctrl.IsItemChecked(i)

    def _update_row_display(self, index):
        if index < 0 or index >= len(self.tracks_data): return
        track = self.tracks_data[index]
        
        # IMPORTANT : On NE met PLUS à jour la colonne 0 ici.
        # Elle garde la valeur définie à l'insertion (l'ID d'origine).
        
        lang_name = self.LANGUAGES_MAP.get(track['language'], track['language'])
        self.list_ctrl.SetItem(index, 2, lang_name)
        self.list_ctrl.SetItem(index, 3, track['title'])
        
        flags = []
        if track['default']: flags.append(_("Default"))
        if track['forced']: flags.append(_("Forced"))
        if track['hearing_impaired']: flags.append(_("HI"))
        if track['visual_impaired']: flags.append(_("AD"))
        
        self.list_ctrl.SetItem(index, 4, ", ".join(flags))

    def on_item_selected(self, event):
        self.current_selection = event.GetIndex()
        self._load_details_to_ui()
        self._enable_details(True)

    def on_item_deselected(self, event):
        self.current_selection = -1
        self._enable_details(False)

    def _enable_details(self, enable):
        self.combo_lang.Enable(enable)
        self.txt_title.Enable(enable)
        self.chk_default.Enable(enable)
        self.chk_forced.Enable(enable)
        if self.chk_special: self.chk_special.Enable(enable)
        
        if not enable:
            self.combo_lang.SetSelection(wx.NOT_FOUND)
            self.txt_title.Clear()
            self.chk_default.SetValue(False)
            self.chk_forced.SetValue(False)
            if self.chk_special: self.chk_special.SetValue(False)

    def _load_details_to_ui(self):
        if self.current_selection == -1: return
        track = self.tracks_data[self.current_selection]
        
        lang_code = track['language']
        sel_idx = 0
        for i, (name, code) in enumerate(self.languages_choices):
            if code == lang_code:
                sel_idx = i
                break
        self.combo_lang.SetSelection(sel_idx)
        self.txt_title.SetValue(track['title'])
        self.chk_default.SetValue(track['default'])
        self.chk_forced.SetValue(track['forced'])
        
        if self.track_type == 'audio':
            self.chk_special.SetValue(track['visual_impaired'])
        else:
            self.chk_special.SetValue(track['hearing_impaired'])

    def on_edit_change(self, event):
        if self.current_selection == -1: return
        track = self.tracks_data[self.current_selection]
        
        sel_idx = self.combo_lang.GetSelection()
        if sel_idx != wx.NOT_FOUND:
            track['language'] = self.languages_choices[sel_idx][1]
            
        track['title'] = self.txt_title.GetValue()
        track['forced'] = self.chk_forced.GetValue()
        
        if self.track_type == 'audio':
            track['visual_impaired'] = self.chk_special.GetValue()
        else:
            track['hearing_impaired'] = self.chk_special.GetValue()
            
        self._update_row_display(self.current_selection)

    def on_flag_change(self, event):
        if self.current_selection == -1: return
        
        is_default = self.chk_default.GetValue()
        track = self.tracks_data[self.current_selection]
        track['default'] = is_default
        
        if is_default:
            for i, t in enumerate(self.tracks_data):
                if i != self.current_selection:
                    t['default'] = False
                    self._update_row_display(i)
        
        self._update_row_display(self.current_selection)

    def on_key_down(self, event):
        key = event.GetKeyCode()
        if event.ControlDown():
            if key == wx.WXK_UP:
                self.move_item(-1)
                return
            elif key == wx.WXK_DOWN:
                self.move_item(1)
                return
        
        if key == wx.WXK_SPACE:
            if self.current_selection != -1:
                curr = self.list_ctrl.IsItemChecked(self.current_selection)
                new_state = not curr
                self.list_ctrl.CheckItem(self.current_selection, new_state)
                self.tracks_data[self.current_selection]['keep'] = new_state
                return

        event.Skip()

    def move_item(self, direction):
        idx = self.current_selection
        if idx == -1: return
        
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.tracks_data): return

        # Préserve l'état "Keep" de toutes les lignes avant réordonnancement.
        self._sync_keep_from_ui()
        
        self.tracks_data[idx], self.tracks_data[new_idx] = self.tracks_data[new_idx], self.tracks_data[idx]

        # On regénère tout pour que l'ID suive bien sa position de donnée.
        self._fill_list()

        # On resélectionne
        self.list_ctrl.SetItemState(new_idx, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
        self.list_ctrl.EnsureVisible(new_idx)
        self.current_selection = new_idx
        self._load_details_to_ui()

    def get_tracks_config(self):
        final_list = []
        for i, track in enumerate(self.tracks_data):
            if self.list_ctrl.IsItemChecked(i):
                track['keep'] = True
                final_list.append(track)
            else:
                track['keep'] = False
        return final_list

class TrackManagerDialog(wx.Dialog):
    def __init__(self, parent, file_meta):
        super().__init__(parent, title=_("Track Manager") + f" - {file_meta.filename}", size=(800, 600))
        self.SetName(_("Track manager dialog"))
        
        self.notebook = wx.Notebook(self)
        self.notebook.SetName(_("Track categories"))
        
        self.audio_panel = TrackPanel(self.notebook, file_meta.audio_tracks, 'audio')
        self.notebook.AddPage(self.audio_panel, _("Audio Tracks"))
        
        self.sub_panel = TrackPanel(self.notebook, file_meta.subtitle_tracks, 'subtitle')
        self.notebook.AddPage(self.sub_panel, _("Subtitles"))
        
        lbl_hint = wx.StaticText(self, label=_("Shortcuts: Ctrl+Up/Down to reorder, Space to toggle."))
        lbl_hint.SetForegroundColour(wx.Colour(100, 100, 100))
        lbl_hint.SetName(_("Keyboard shortcuts hint"))
        
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK, label=_("Apply"))
        btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_("Cancel"))
        btn_ok.SetName(_("Apply track settings"))
        btn_cancel.SetName(_("Cancel track settings"))
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(lbl_hint, 0, wx.ALIGN_LEFT | wx.LEFT | wx.BOTTOM, 10)
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(sizer)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Centre()

    def get_configuration(self):
        return {
            'audio_tracks': self.audio_panel.get_tracks_config(),
            'subtitle_tracks': self.sub_panel.get_tracks_config()
        }
