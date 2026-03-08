import copy

import wx

from core.track_settings import (
    ADVANCED_DISPOSITIONS_BY_TYPE,
    BASE_DISPOSITIONS_BY_TYPE,
    normalize_track_settings,
)


LANGUAGE_MSGIDS = {
    "und": "Undetermined",
    "fre": "French",
    "eng": "English",
    "jpn": "Japanese",
    "spa": "Spanish",
    "ger": "German",
    "ita": "Italian",
    "por": "Portuguese",
    "rus": "Russian",
    "chi": "Chinese",
    "dut": "Dutch",
    "pol": "Polish",
    "kor": "Korean",
    "hin": "Hindi",
    "ara": "Arabic",
}

TRACK_LIST_NAMES = {
    "video": "Video tracks list",
    "audio": "Audio tracks list",
    "subtitle": "Subtitle tracks list",
}

DISPOSITION_LABELS = {
    "default": "Default",
    "forced": "Forced",
    "visual_impaired": "Audio Description",
    "hearing_impaired": "Hearing Impaired",
    "captions": "Captions",
    "descriptions": "Descriptions",
    "original": "Original",
    "comment": "Commentary",
    "dub": "Dub",
    "lyrics": "Lyrics",
    "karaoke": "Karaoke",
    "clean_effects": "Clean Effects",
    "non_diegetic": "Non-Diegetic",
}

DISPOSITION_ROW_LABELS = {
    "default": "Default",
    "forced": "Forced",
    "visual_impaired": "AD",
    "hearing_impaired": "HI",
    "captions": "Captions",
    "descriptions": "Descriptions",
    "original": "Original",
    "comment": "Commentary",
    "dub": "Dub",
    "lyrics": "Lyrics",
    "karaoke": "Karaoke",
    "clean_effects": "Clean Effects",
    "non_diegetic": "Non-Diegetic",
}


def _translate_language(language_code):
    msgid = LANGUAGE_MSGIDS.get(language_code or "und")
    if msgid:
        return _(msgid)
    return language_code or "und"


def _disposition_label(disposition_name):
    return _(DISPOSITION_LABELS.get(disposition_name, disposition_name.replace("_", " ").title()))


def _row_disposition_label(disposition_name):
    return _(DISPOSITION_ROW_LABELS.get(disposition_name, disposition_name.replace("_", " ").title()))


def _serialize_audio_track(track):
    return {
        "original_index": track.index,
        "codec_name": track.codec_name,
        "language": track.language if track.language else "und",
        "title": track.title if track.title else "",
        "default": track.is_default(),
        "forced": track.is_forced(),
    }


def _build_audio_track_label(track_data):
    parts = [track_data["codec_name"].upper(), _translate_language(track_data.get("language", "und"))]
    if track_data.get("title"):
        parts.append(f"\"{track_data['title']}\"")

    flags = []
    if track_data.get("default"):
        flags.append(_("Default"))
    if track_data.get("forced"):
        flags.append(_("Forced"))

    label = " - ".join([part for part in parts if part])
    if flags:
        label += f" ({', '.join(flags)})"
    return label


class EditableListCtrl(wx.ListCtrl):
    def __init__(self, parent):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self.EnableCheckBoxes(True)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_item_activated)

    def on_item_activated(self, event):
        index = event.GetIndex()
        self.CheckItem(index, not self.IsItemChecked(index))


class TrackPanel(wx.Panel):
    def __init__(self, parent, track_entries, track_type):
        super().__init__(parent)
        self.track_type = track_type
        self.base_dispositions = BASE_DISPOSITIONS_BY_TYPE[track_type]
        self.advanced_dispositions = ADVANCED_DISPOSITIONS_BY_TYPE[track_type]
        if track_type == "subtitle":
            self.visible_dispositions = self.base_dispositions
        else:
            self.visible_dispositions = self.base_dispositions + self.advanced_dispositions
        self.tracks_data = self._prepare_track_entries(track_entries)
        self.current_selection = -1
        self.languages_choices = sorted(
            [(_(msgid), code) for code, msgid in LANGUAGE_MSGIDS.items()],
            key=lambda item: item[0],
        )
        self.base_checkboxes = {}
        self.advanced_checkboxes = {}

        self.main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.list_ctrl = EditableListCtrl(self)
        self.list_ctrl.SetName(_(TRACK_LIST_NAMES[track_type]))
        self.list_ctrl.SetToolTip(_("Use Space to keep or remove a track. Use Ctrl+Up and Ctrl+Down to reorder."))
        self.list_ctrl.InsertColumn(0, _("#"), width=40)
        self.list_ctrl.InsertColumn(1, _("Codec"), width=90)
        self.list_ctrl.InsertColumn(2, _("Lang"), width=100)
        self.list_ctrl.InsertColumn(3, _("Title"), width=200)
        self.list_ctrl.InsertColumn(4, _("Flags"), width=260)
        self.main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 5)

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

        self.detail_box = wx.StaticBox(self, label=_("Track Settings"))
        self.detail_sizer = wx.StaticBoxSizer(self.detail_box, wx.VERTICAL)

        grid = wx.FlexGridSizer(rows=2, cols=2, vgap=10, hgap=10)
        grid.AddGrowableCol(1, 1)

        lbl_lang = wx.StaticText(self, label=_("Language:"))
        self.combo_lang = wx.Choice(self, choices=[item[0] for item in self.languages_choices])
        self.combo_lang.SetName(_("Language"))
        self.combo_lang.SetToolTip(_("Track language"))
        grid.Add(lbl_lang, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.combo_lang, 1, wx.EXPAND)

        lbl_title = wx.StaticText(self, label=_("Track Title:"))
        self.txt_title = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.txt_title.SetName(_("Track title"))
        grid.Add(lbl_title, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.txt_title, 1, wx.EXPAND)

        self.detail_sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 10)

        self.detail_sizer.Add(wx.StaticText(self, label=_("Attributes:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.base_flags_sizer = wx.WrapSizer(wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS)
        for disposition_name in self.visible_dispositions:
            checkbox = self._create_disposition_checkbox(disposition_name)
            self.base_flags_sizer.Add(checkbox, 0, wx.RIGHT | wx.BOTTOM, 12)
            if disposition_name in self.base_dispositions:
                self.base_checkboxes[disposition_name] = checkbox
            else:
                self.advanced_checkboxes[disposition_name] = checkbox
        self.detail_sizer.Add(self.base_flags_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.main_sizer.Add(self.detail_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(self.main_sizer)

        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_item_deselected)
        self.list_ctrl.Bind(wx.EVT_KEY_DOWN, self.on_key_down)
        self.combo_lang.Bind(wx.EVT_CHOICE, self.on_edit_change)
        self.txt_title.Bind(wx.EVT_TEXT, self.on_edit_change)

        self._fill_list()
        self._enable_details(False)

    def _prepare_track_entries(self, track_entries):
        prepared = []
        for position, entry in enumerate(track_entries, start=1):
            normalized_entry = copy.deepcopy(entry)
            normalized_entry.setdefault("ui_id", str(position))
            normalized_entry.setdefault("codec_name", "unknown")
            normalized_entry.setdefault("language", "und")
            normalized_entry.setdefault("title", "")
            normalized_entry.setdefault("keep", True)
            normalized_entry.setdefault("dispositions", {})
            for disposition_name in self.base_dispositions + self.advanced_dispositions:
                normalized_entry["dispositions"].setdefault(disposition_name, False)
            prepared.append(normalized_entry)
        return prepared

    def _create_disposition_checkbox(self, disposition_name, parent=None):
        checkbox = wx.CheckBox(parent or self, label=_disposition_label(disposition_name))
        checkbox.disposition_name = disposition_name
        checkbox.SetName(checkbox.GetLabel())
        checkbox.Bind(wx.EVT_CHECKBOX, self.on_disposition_change)
        return checkbox

    def _fill_list(self):
        self.list_ctrl.DeleteAllItems()
        for index, track in enumerate(self.tracks_data):
            row = self.list_ctrl.InsertItem(index, track["ui_id"])
            self.list_ctrl.SetItem(row, 1, track["codec_name"].upper())
            self.list_ctrl.CheckItem(row, bool(track.get("keep", True)))
            self._update_row_display(row)

    def _update_row_display(self, index):
        if index < 0 or index >= len(self.tracks_data):
            return

        track = self.tracks_data[index]
        self.list_ctrl.SetItem(index, 2, _translate_language(track.get("language", "und")))
        self.list_ctrl.SetItem(index, 3, track.get("title", ""))

        flags = [
            _row_disposition_label(disposition_name)
            for disposition_name, enabled in track.get("dispositions", {}).items()
            if enabled and disposition_name in self.visible_dispositions
        ]
        self.list_ctrl.SetItem(index, 4, ", ".join(flags))

    def _sync_keep_from_ui(self):
        for index, track in enumerate(self.tracks_data):
            track["keep"] = self.list_ctrl.IsItemChecked(index)

    def _load_details_to_ui(self):
        if self.current_selection == -1:
            return

        track = self.tracks_data[self.current_selection]
        selected_language = track.get("language", "und")
        selection_index = 0
        for index, (_, code) in enumerate(self.languages_choices):
            if code == selected_language:
                selection_index = index
                break

        self.combo_lang.SetSelection(selection_index)
        self.txt_title.SetValue(track.get("title", ""))

        dispositions = track.get("dispositions", {})
        for disposition_name, checkbox in self.base_checkboxes.items():
            checkbox.SetValue(bool(dispositions.get(disposition_name, False)))
        for disposition_name, checkbox in self.advanced_checkboxes.items():
            checkbox.SetValue(bool(dispositions.get(disposition_name, False)))

    def _enable_details(self, enable):
        self.combo_lang.Enable(enable)
        self.txt_title.Enable(enable)
        self.btn_up.Enable(enable)
        self.btn_down.Enable(enable)

        for checkbox in self.base_checkboxes.values():
            checkbox.Enable(enable)
        for checkbox in self.advanced_checkboxes.values():
            checkbox.Enable(enable)

        if not enable:
            self.combo_lang.SetSelection(wx.NOT_FOUND)
            self.txt_title.ChangeValue("")
            for checkbox in self.base_checkboxes.values():
                checkbox.SetValue(False)
            for checkbox in self.advanced_checkboxes.values():
                checkbox.SetValue(False)

    def on_item_selected(self, event):
        self.current_selection = event.GetIndex()
        self._load_details_to_ui()
        self._enable_details(True)

    def on_item_deselected(self, event):
        if self.list_ctrl.GetFirstSelected() == -1:
            self.current_selection = -1
            self._enable_details(False)

    def on_key_down(self, event):
        key = event.GetKeyCode()
        if event.ControlDown():
            if key == wx.WXK_UP:
                self.move_item(-1)
                return
            if key == wx.WXK_DOWN:
                self.move_item(1)
                return

        if key == wx.WXK_SPACE and self.current_selection != -1:
            new_state = not self.list_ctrl.IsItemChecked(self.current_selection)
            self.list_ctrl.CheckItem(self.current_selection, new_state)
            self.tracks_data[self.current_selection]["keep"] = new_state
            return

        event.Skip()

    def on_edit_change(self, event):
        if self.current_selection == -1:
            event.Skip()
            return

        track = self.tracks_data[self.current_selection]
        selection_index = self.combo_lang.GetSelection()
        if selection_index != wx.NOT_FOUND:
            track["language"] = self.languages_choices[selection_index][1]
        track["title"] = self.txt_title.GetValue()
        self._update_row_display(self.current_selection)
        event.Skip()

    def on_disposition_change(self, event):
        if self.current_selection == -1:
            event.Skip()
            return

        checkbox = event.GetEventObject()
        disposition_name = getattr(checkbox, "disposition_name", None)
        if not disposition_name:
            event.Skip()
            return

        track = self.tracks_data[self.current_selection]
        track["dispositions"][disposition_name] = checkbox.GetValue()

        if disposition_name == "default" and checkbox.GetValue():
            for index, other_track in enumerate(self.tracks_data):
                if index == self.current_selection:
                    continue
                if other_track["dispositions"].get("default", False):
                    other_track["dispositions"]["default"] = False
                    self._update_row_display(index)

        self._update_row_display(self.current_selection)
        event.Skip()

    def move_item(self, direction):
        if self.current_selection == -1:
            return

        new_index = self.current_selection + direction
        if new_index < 0 or new_index >= len(self.tracks_data):
            return

        self._sync_keep_from_ui()
        self.tracks_data[self.current_selection], self.tracks_data[new_index] = (
            self.tracks_data[new_index],
            self.tracks_data[self.current_selection],
        )
        self._fill_list()
        self.list_ctrl.SetItemState(new_index, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
        self.list_ctrl.EnsureVisible(new_index)
        self.current_selection = new_index
        self._load_details_to_ui()

    def has_any_kept_tracks(self):
        self._sync_keep_from_ui()
        return any(track.get("keep", False) for track in self.tracks_data)

    def get_tracks_config(self):
        self._sync_keep_from_ui()
        return copy.deepcopy(self.tracks_data)


class TrackManagerDialog(wx.Dialog):
    def __init__(self, parent, file_meta):
        super().__init__(parent, title=_("Track Manager") + f" - {file_meta.filename}", size=(860, 700))
        self.SetName(_("Track manager dialog"))
        self.track_settings = normalize_track_settings(getattr(file_meta, "track_settings", None), file_meta)

        self.notebook = wx.Notebook(self)
        self.notebook.SetName(_("Track categories"))

        self.video_panel = TrackPanel(self.notebook, self.track_settings["video_tracks"], "video")
        self.audio_panel = TrackPanel(self.notebook, self.track_settings["audio_tracks"], "audio")
        self.sub_panel = TrackPanel(self.notebook, self.track_settings["subtitle_tracks"], "subtitle")

        self.notebook.AddPage(self.video_panel, _("Video Tracks"))
        self.notebook.AddPage(self.audio_panel, _("Audio Tracks"))
        self.notebook.AddPage(self.sub_panel, _("Subtitles"))

        lbl_hint = wx.StaticText(self, label=_("Shortcuts: Ctrl+Up/Down to reorder, Space to toggle."))
        lbl_hint.SetForegroundColour(wx.Colour(100, 100, 100))
        lbl_hint.SetName(_("Keyboard shortcuts hint"))

        btn_sizer = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(self, wx.ID_OK, label=_("Apply"))
        self.btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_("Cancel"))
        self.btn_ok.SetName(_("Apply track settings"))
        self.btn_cancel.SetName(_("Cancel track settings"))
        self.btn_ok.Bind(wx.EVT_BUTTON, self.on_apply)
        btn_sizer.AddButton(self.btn_ok)
        btn_sizer.AddButton(self.btn_cancel)
        btn_sizer.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(lbl_hint, 0, wx.ALIGN_LEFT | wx.LEFT | wx.BOTTOM, 10)
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizer(sizer)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Centre()

    def on_apply(self, event):
        if not self.video_panel.has_any_kept_tracks():
            wx.MessageBox(_("At least one video track must be kept."), _("Warning"), wx.ICON_WARNING)
            return

        self.EndModal(wx.ID_OK)

    def get_configuration(self):
        return {
            "video_tracks": self.video_panel.get_tracks_config(),
            "audio_tracks": self.audio_panel.get_tracks_config(),
            "subtitle_tracks": self.sub_panel.get_tracks_config(),
        }


class AudioExtractTrackDialog(wx.Dialog):
    def __init__(self, parent, file_meta, current_selection=None):
        super().__init__(parent, title=_("Choose Audio Track...") + f" - {file_meta.filename}", size=(640, 420))
        self.SetName(_("Audio extract track dialog"))

        self.tracks = [_serialize_audio_track(track) for track in file_meta.audio_tracks]

        self.lbl_intro = wx.StaticText(
            self,
            label=_("Select the audio track to extract. Only one track can be kept."),
        )

        self.list_box = wx.ListBox(
            self,
            choices=[_build_audio_track_label(track) for track in self.tracks],
            style=wx.LB_SINGLE,
        )
        self.list_box.SetName(_("Audio extraction tracks list"))
        self.list_box.SetToolTip(_("Select the single audio track to extract."))

        initial_index = self._resolve_initial_selection(current_selection)
        if initial_index != wx.NOT_FOUND:
            self.list_box.SetSelection(initial_index)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK, label=_("Apply"))
        btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_("Cancel"))
        btn_ok.SetName(_("Apply audio extraction track"))
        btn_cancel.SetName(_("Cancel audio extraction track"))
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.lbl_intro, 0, wx.EXPAND | wx.ALL, 10)
        sizer.Add(self.list_box, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizer(sizer)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Centre()

    def _resolve_initial_selection(self, current_selection):
        selected_index = None
        if isinstance(current_selection, dict):
            selected_index = current_selection.get("original_index")

        if selected_index is not None:
            for index, track in enumerate(self.tracks):
                if track["original_index"] == selected_index:
                    return index

        for index, track in enumerate(self.tracks):
            if track.get("default"):
                return index

        if self.tracks:
            return 0

        return wx.NOT_FOUND

    def get_selected_track(self):
        selection = self.list_box.GetSelection()
        if selection == wx.NOT_FOUND:
            return None
        return dict(self.tracks[selection])
