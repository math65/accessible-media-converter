"""Presets manager dialog — save / apply / replace / delete / import / export.

Opened from the main window's "Presets..." button (next to Settings/Quality).
A preset is a reusable bundle of the current tab's format + encoding settings +
output preferences + an optional shared-tag metadata template. Applying a preset
pours these back into the existing ``settings_store`` (the main window does that
on ID_OK); this dialog only owns the management UI and ``presets.json`` I/O.
"""

import wx

from core.formatting import build_format_label
from core.metadata_edit import (
    AUDIO_BATCH_FIELDS,
    MULTILINE_TAG_KEYS,
    VIDEO_SERIES_BATCH_FIELDS,
)
from core.presets import (
    PresetImportError,
    delete_preset,
    export_presets,
    find_preset,
    import_presets,
    load_presets,
    normalize_preset,
    save_presets,
    strip_export_fields,
    upsert_preset,
)
from core.speech import speak


# Shared-tag template fields per category (reuse the batch field sets, which
# already exclude per-file-unique tags like title/track). Image has no template.
_TEMPLATE_FIELDS = {
    "audio": AUDIO_BATCH_FIELDS,
    "video": VIDEO_SERIES_BATCH_FIELDS,
}


class PresetsDialog(wx.Dialog):
    def __init__(self, parent, category, current_format, current_settings, current_output):
        super().__init__(parent, title=_("Manage Presets"), size=(560, 440))
        self.SetName(_("Presets dialog"))

        self.category = category
        self.current_format = current_format
        self.current_settings = dict(current_settings or {})
        self.current_output = dict(current_output or {})

        # Full list across all categories (other categories are preserved on save);
        # only the current category is shown.
        self.presets = load_presets()
        self.result_preset = None  # set on Apply, read by the caller

        self._init_ui()
        self._refresh_list()
        self.Centre()
        wx.CallAfter(self.lst_presets.SetFocus)

    # ----- UI construction -------------------------------------------------

    def _init_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)

        body = wx.BoxSizer(wx.HORIZONTAL)

        list_col = wx.BoxSizer(wx.VERTICAL)
        lbl_list = wx.StaticText(panel, label=_("Presets"))
        self.lst_presets = wx.ListBox(panel, style=wx.LB_SINGLE)
        self.lst_presets.SetName(_("Presets list"))
        list_col.Add(lbl_list, 0, wx.BOTTOM, 4)
        list_col.Add(self.lst_presets, 1, wx.EXPAND)
        body.Add(list_col, 1, wx.EXPAND | wx.RIGHT, 10)

        btn_col = wx.BoxSizer(wx.VERTICAL)
        self.btn_save = wx.Button(panel, label=_("Save current settings as preset..."))
        self.btn_apply = wx.Button(panel, label=_("Apply"))
        self.btn_replace = wx.Button(panel, label=_("Replace with current settings"))
        self.btn_metadata = wx.Button(panel, label=_("Edit metadata..."))
        self.btn_rename = wx.Button(panel, label=_("Rename..."))
        self.btn_delete = wx.Button(panel, label=_("Delete"))
        self.btn_import = wx.Button(panel, label=_("Import..."))
        self.btn_export = wx.Button(panel, label=_("Export..."))

        buttons = [
            self.btn_save,
            self.btn_apply,
            self.btn_replace,
            self.btn_metadata,
            self.btn_rename,
            self.btn_delete,
            self.btn_import,
            self.btn_export,
        ]
        # No metadata template for image presets.
        if self.category not in _TEMPLATE_FIELDS:
            self.btn_metadata.Hide()
        for btn in buttons:
            if btn.IsShown():
                btn_col.Add(btn, 0, wx.EXPAND | wx.BOTTOM, 6)
        body.Add(btn_col, 0)

        outer.Add(body, 1, wx.EXPAND | wx.ALL, 12)

        close_sizer = wx.StdDialogButtonSizer()
        self.btn_close = wx.Button(panel, wx.ID_CANCEL, label=_("Close"))
        close_sizer.AddButton(self.btn_close)
        close_sizer.Realize()
        outer.Add(close_sizer, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        panel.SetSizer(outer)
        self.SetEscapeId(wx.ID_CANCEL)

        self.btn_save.Bind(wx.EVT_BUTTON, self.on_save_new)
        self.btn_apply.Bind(wx.EVT_BUTTON, self.on_apply)
        self.btn_replace.Bind(wx.EVT_BUTTON, self.on_replace)
        self.btn_metadata.Bind(wx.EVT_BUTTON, self.on_edit_metadata)
        self.btn_rename.Bind(wx.EVT_BUTTON, self.on_rename)
        self.btn_delete.Bind(wx.EVT_BUTTON, self.on_delete)
        self.btn_import.Bind(wx.EVT_BUTTON, self.on_import)
        self.btn_export.Bind(wx.EVT_BUTTON, self.on_export)
        self.lst_presets.Bind(wx.EVT_LISTBOX_DCLICK, self.on_apply)
        self.lst_presets.Bind(wx.EVT_LISTBOX, lambda evt: self._update_buttons())

    # ----- list helpers ----------------------------------------------------

    def _visible_presets(self):
        return [p for p in self.presets if p.get("category") == self.category]

    def _refresh_list(self, select_name=None):
        visible = self._visible_presets()
        labels = []
        for preset in visible:
            fmt = build_format_label(preset["format"], context=self.category)
            summary = preset.get("settings", {}).get("summary", "")
            labels.append(f"{preset['name']} — {fmt} ({summary})" if summary else f"{preset['name']} — {fmt}")
        self.lst_presets.Set(labels)
        if visible:
            index = 0
            if select_name:
                for i, preset in enumerate(visible):
                    if preset["name"].lower() == select_name.lower():
                        index = i
                        break
            self.lst_presets.SetSelection(index)
        self._update_buttons()

    def _selected_preset(self):
        index = self.lst_presets.GetSelection()
        if index == wx.NOT_FOUND:
            return None
        visible = self._visible_presets()
        if 0 <= index < len(visible):
            return visible[index]
        return None

    def _update_buttons(self):
        has_selection = self.lst_presets.GetSelection() != wx.NOT_FOUND
        for btn in (self.btn_apply, self.btn_replace, self.btn_rename, self.btn_delete, self.btn_export):
            btn.Enable(has_selection)
        if self.btn_metadata.IsShown():
            self.btn_metadata.Enable(has_selection)

    def _persist(self, select_name=None, spoken=None):
        save_presets(self.presets)
        self._refresh_list(select_name=select_name)
        if spoken:
            speak(spoken)

    def _build_current_preset(self, name, metadata=None):
        return normalize_preset({
            "name": name,
            "category": self.category,
            "format": self.current_format,
            "settings": self.current_settings,
            "output": self.current_output,
            "metadata": metadata or {},
        })

    # ----- actions ---------------------------------------------------------

    def on_save_new(self, event):
        with wx.TextEntryDialog(self, _("Preset name:"), _("Save Preset")) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            name = dlg.GetValue().strip()
        if not name:
            return

        existing = find_preset(self.presets, name)
        if existing is not None:
            if wx.MessageBox(
                _("A preset named \"{name}\" already exists. Replace it?").format(name=name),
                _("Replace Preset"),
                wx.YES_NO | wx.ICON_QUESTION,
                self,
            ) != wx.YES:
                return

        # Keep an existing preset's metadata template when overwriting by name.
        metadata = existing.get("metadata") if existing else None
        preset = self._build_current_preset(name, metadata)
        if preset is None:
            return
        self.presets = upsert_preset(self.presets, preset)
        self._persist(select_name=name, spoken=_("Preset \"{name}\" saved.").format(name=name))

    def on_apply(self, event):
        preset = self._selected_preset()
        if preset is None:
            return
        self.result_preset = preset
        speak(_("Preset \"{name}\" applied.").format(name=preset["name"]))
        self.EndModal(wx.ID_OK)

    def on_replace(self, event):
        preset = self._selected_preset()
        if preset is None:
            return
        if wx.MessageBox(
            _("Replace the settings of \"{name}\" with the current ones?").format(name=preset["name"]),
            _("Replace Preset"),
            wx.YES_NO | wx.ICON_QUESTION,
            self,
        ) != wx.YES:
            return
        updated = self._build_current_preset(preset["name"], preset.get("metadata"))
        if updated is None:
            return
        self.presets = upsert_preset(self.presets, updated)
        self._persist(select_name=preset["name"], spoken=_("Preset \"{name}\" updated.").format(name=preset["name"]))

    def on_edit_metadata(self, event):
        preset = self._selected_preset()
        if preset is None:
            return
        fields = _TEMPLATE_FIELDS.get(self.category)
        if not fields:
            return
        with _MetadataTemplateDialog(self, fields, preset.get("metadata", {})) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            preset["metadata"] = dlg.get_tags()
        self._persist(select_name=preset["name"], spoken=_("Metadata updated."))

    def on_rename(self, event):
        preset = self._selected_preset()
        if preset is None:
            return
        with wx.TextEntryDialog(self, _("New name:"), _("Rename Preset"), value=preset["name"]) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            new_name = dlg.GetValue().strip()
        if not new_name or new_name.lower() == preset["name"].lower():
            return
        if find_preset(self.presets, new_name) is not None:
            wx.MessageBox(
                _("A preset named \"{name}\" already exists.").format(name=new_name),
                _("Rename Preset"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return
        preset["name"] = new_name
        self._persist(select_name=new_name, spoken=_("Preset renamed."))

    def on_delete(self, event):
        preset = self._selected_preset()
        if preset is None:
            return
        if wx.MessageBox(
            _("Delete the preset \"{name}\"?").format(name=preset["name"]),
            _("Delete Preset"),
            wx.YES_NO | wx.ICON_QUESTION,
            self,
        ) != wx.YES:
            return
        self.presets = delete_preset(self.presets, preset["name"])
        self._persist(spoken=_("Preset deleted."))

    def on_import(self, event):
        with wx.FileDialog(
            self,
            _("Import Presets"),
            wildcard=_("Preset files (*.json)|*.json"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()

        try:
            imported = import_presets(path)
        except PresetImportError:
            wx.MessageBox(
                _("This file is not a valid presets file."),
                _("Import Presets"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        if not imported:
            wx.MessageBox(
                _("No valid preset found in this file."),
                _("Import Presets"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        added = self._merge_imported(imported)
        self._persist(spoken=_("{count} preset(s) imported.").format(count=added))

    def _merge_imported(self, imported):
        """Merge imported presets, prompting once whether to overwrite name clashes."""
        overwrite_all = None  # None until the user answers the first clash
        added = 0
        for preset in imported:
            clash = find_preset(self.presets, preset["name"])
            if clash is not None:
                if overwrite_all is None:
                    answer = wx.MessageBox(
                        _("Some presets already exist (e.g. \"{name}\"). Overwrite existing "
                          "presets? Choose No to keep both (imported ones are renamed).").format(name=preset["name"]),
                        _("Import Presets"),
                        wx.YES_NO | wx.ICON_QUESTION,
                        self,
                    )
                    overwrite_all = (answer == wx.YES)
                if not overwrite_all:
                    preset["name"] = self._unique_name(preset["name"])
            self.presets = upsert_preset(self.presets, preset)
            added += 1
        return added

    def _unique_name(self, name):
        candidate = name
        counter = 2
        while find_preset(self.presets, candidate) is not None:
            candidate = f"{name} ({counter})"
            counter += 1
        return candidate

    def on_export(self, event):
        selected = self._selected_preset()
        to_export = [selected] if selected is not None else self._visible_presets()
        if not to_export:
            return

        # Let the user drop portability-sensitive blocks (Sèb: the output path
        # rarely makes sense on another machine). Format + settings are always kept.
        has_metadata = self.category in _TEMPLATE_FIELDS
        with _ExportOptionsDialog(self, show_metadata=has_metadata) as opts:
            if opts.ShowModal() != wx.ID_OK:
                return
            include_output = opts.include_output()
            include_metadata = opts.include_metadata()
        to_export = strip_export_fields(
            to_export,
            include_output=include_output,
            include_metadata=include_metadata,
        )

        default_name = (selected["name"] if selected else self.category) + "_presets.json"
        with wx.FileDialog(
            self,
            _("Export Presets"),
            defaultFile=default_name,
            wildcard=_("Preset files (*.json)|*.json"),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        try:
            export_presets(path, to_export)
        except OSError:
            wx.MessageBox(
                _("Could not write the export file."),
                _("Export Presets"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        speak(_("{count} preset(s) exported.").format(count=len(to_export)))


class _ExportOptionsDialog(wx.Dialog):
    """Choose which portability-sensitive blocks to include in an export.

    Format + encoding settings are a preset's essence and always exported. The
    output destination and the metadata template are optional (a custom folder
    rarely transfers across machines), so each gets a checkbox, both ticked by
    default. The metadata checkbox is hidden for categories without a template.
    """

    def __init__(self, parent, show_metadata=True):
        super().__init__(parent, title=_("Export Options"))
        self.SetName(_("Export options dialog"))
        self._show_metadata = show_metadata

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            panel,
            label=_("Choose what to include in the export. The format and encoding "
                    "settings are always included."),
        )
        intro.Wrap(380)
        vbox.Add(intro, 0, wx.ALL, 12)

        self.chk_output = wx.CheckBox(panel, label=_("Include the output destination"))
        self.chk_output.SetValue(True)
        vbox.Add(self.chk_output, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.chk_metadata = wx.CheckBox(panel, label=_("Include the metadata"))
        self.chk_metadata.SetValue(True)
        if not show_metadata:
            self.chk_metadata.Hide()
        else:
            vbox.Add(self.chk_metadata, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(panel, wx.ID_OK, label=_("Export"))
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, label=_("Cancel"))
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 12)

        panel.SetSizerAndFit(vbox)
        self.Fit()
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Centre()
        wx.CallAfter(self.chk_output.SetFocus)

    def include_output(self):
        return self.chk_output.GetValue()

    def include_metadata(self):
        return bool(self._show_metadata and self.chk_metadata.GetValue())


class _MetadataTemplateDialog(wx.Dialog):
    """Edit a preset's shared-tag template (a subset of common metadata fields)."""

    def __init__(self, parent, fields, current_tags):
        super().__init__(parent, title=_("Preset Metadata"), size=(440, 420))
        self.SetName(_("Preset metadata dialog"))
        self.fields = fields
        current = current_tags if isinstance(current_tags, dict) else {}

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            panel,
            label=_("These tags are applied to every file when the preset is used. "
                    "Leave a field empty to leave it unchanged."),
        )
        intro.Wrap(400)
        vbox.Add(intro, 0, wx.ALL, 10)

        grid = wx.FlexGridSizer(rows=0, cols=2, vgap=8, hgap=10)
        grid.AddGrowableCol(1, 1)
        self.controls = {}
        for key, label in fields:
            text = _(label)
            lbl = wx.StaticText(panel, label=text)
            if key in MULTILINE_TAG_KEYS:
                ctrl = wx.TextCtrl(panel, value=str(current.get(key, "")), style=wx.TE_MULTILINE, size=(-1, 60))
            else:
                ctrl = wx.TextCtrl(panel, value=str(current.get(key, "")))
            ctrl.SetName(text)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            self.controls[key] = ctrl
        vbox.Add(grid, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(panel, wx.ID_OK, label=_("OK"))
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, label=_("Cancel"))
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(vbox)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Centre()

    def get_tags(self):
        tags = {}
        for key, ctrl in self.controls.items():
            value = ctrl.GetValue().strip()
            if value:
                tags[key] = value
        return tags
