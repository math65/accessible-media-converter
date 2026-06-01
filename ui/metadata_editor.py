import os

import wx

from core.metadata_edit import (
    METADATA_TAG_FIELDS,
    format_supports_cover,
    normalize_metadata_overrides,
    read_prefill_tags,
    source_supports_cover,
)


class MetadataEditorDialog(wx.Dialog):
    """Edit file-level tags and cover art for one or several media files.

    Returns, via get_result(), a tuple (overrides, target) where target is
    "convert" (apply during the next conversion) or "inplace" (re-tag the
    original file now without re-encoding).
    """

    def __init__(self, parent, metas, target_format):
        self.metas = list(metas)
        self.is_batch = len(self.metas) > 1
        self.target_format = target_format

        if self.is_batch:
            title = _("Edit metadata ({count} files)").format(count=len(self.metas))
        else:
            title = _("Edit metadata: {name}").format(name=self.metas[0].filename)

        super().__init__(parent, title=title, size=(560, 640))
        self.SetName(_("Edit metadata dialog"))

        self._convert_cover_possible = format_supports_cover(target_format)
        self._inplace_cover_possible = all(
            source_supports_cover(getattr(meta, "source_format_name", "")) for meta in self.metas
        )

        self.field_inputs = {}
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)

        self._build_intro()
        self._build_tag_fields()
        self._build_cover_section()
        self._build_target_section()
        self._build_buttons()

        self.SetSizer(self.main_sizer)
        self.Centre()
        self._bind_events()
        self._update_cover_controls_state()
        wx.CallAfter(self._set_initial_focus)

    def _build_intro(self):
        if self.is_batch:
            intro = wx.StaticText(
                self,
                label=_("Fields left empty are not changed on the selected files."),
            )
            intro.Wrap(520)
            self.main_sizer.Add(intro, 0, wx.ALL, 12)

    def _build_tag_fields(self):
        tag_box = wx.StaticBox(self, label=_("Tags"))
        tag_box.SetWindowStyle(tag_box.GetWindowStyle() & ~wx.TAB_TRAVERSAL)
        tag_sizer = wx.StaticBoxSizer(tag_box, wx.VERTICAL)

        grid = wx.FlexGridSizer(rows=0, cols=2, vgap=8, hgap=10)
        grid.AddGrowableCol(1, 1)

        prefill = {} if self.is_batch else read_prefill_tags(getattr(self.metas[0], "format_tags", {}))

        for field_key, label_msgid in METADATA_TAG_FIELDS:
            label = wx.StaticText(self, label=_(label_msgid) + ":")
            text_ctrl = wx.TextCtrl(self, value=prefill.get(field_key, ""))
            text_ctrl.SetName(_(label_msgid))
            grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(text_ctrl, 0, wx.EXPAND)
            self.field_inputs[field_key] = text_ctrl

        tag_sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 10)
        self.main_sizer.Add(tag_sizer, 0, wx.EXPAND | wx.ALL, 8)

    def _build_cover_section(self):
        cover_box = wx.StaticBox(self, label=_("Cover art"))
        cover_box.SetWindowStyle(cover_box.GetWindowStyle() & ~wx.TAB_TRAVERSAL)
        cover_sizer = wx.StaticBoxSizer(cover_box, wx.VERTICAL)

        if not self.is_batch:
            state = _("present") if getattr(self.metas[0], "has_cover_art", False) else _("none")
            self.lbl_cover_state = wx.StaticText(
                self, label=_("Embedded cover art: {state}").format(state=state)
            )
            cover_sizer.Add(self.lbl_cover_state, 0, wx.ALL, 6)

        self.rb_cover_keep = wx.RadioButton(self, label=_("Keep current cover"), style=wx.RB_GROUP)
        self.rb_cover_replace = wx.RadioButton(self, label=_("Replace with an image file..."))
        self.rb_cover_remove = wx.RadioButton(self, label=_("Remove cover"))
        self.rb_cover_keep.SetValue(True)
        for radio in (self.rb_cover_keep, self.rb_cover_replace, self.rb_cover_remove):
            radio.SetName(radio.GetLabel())
            cover_sizer.Add(radio, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)

        picker_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_picker = wx.StaticText(self, label=_("Image file:"))
        self.cover_picker = wx.FilePickerCtrl(
            self,
            message=_("Choose a cover image"),
            wildcard=_("Images") + " (*.jpg;*.jpeg;*.png)|*.jpg;*.jpeg;*.png",
            style=wx.FLP_USE_TEXTCTRL | wx.FLP_OPEN | wx.FLP_FILE_MUST_EXIST,
        )
        self.cover_picker.SetName(_("Cover image file"))
        picker_row.Add(lbl_picker, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        picker_row.Add(self.cover_picker, 1, wx.EXPAND)
        cover_sizer.Add(picker_row, 0, wx.EXPAND | wx.ALL, 6)

        self._cover_controls = (
            self.rb_cover_keep,
            self.rb_cover_replace,
            self.rb_cover_remove,
            self.cover_picker,
        )
        self.main_sizer.Add(cover_sizer, 0, wx.EXPAND | wx.ALL, 8)

    def _build_target_section(self):
        target_box = wx.StaticBox(self, label=_("Apply to"))
        target_box.SetWindowStyle(target_box.GetWindowStyle() & ~wx.TAB_TRAVERSAL)
        target_sizer = wx.StaticBoxSizer(target_box, wx.VERTICAL)

        self.rb_target_convert = wx.RadioButton(
            self, label=_("When converting (output file)"), style=wx.RB_GROUP
        )
        self.rb_target_inplace = wx.RadioButton(
            self, label=_("Re-tag the original file now (no re-encoding)")
        )
        self.rb_target_convert.SetValue(True)
        for radio in (self.rb_target_convert, self.rb_target_inplace):
            radio.SetName(radio.GetLabel())
            target_sizer.Add(radio, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)

        self.main_sizer.Add(target_sizer, 0, wx.EXPAND | wx.ALL, 8)

    def _build_buttons(self):
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK, label=_("OK"))
        btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_("Cancel"))
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        self.main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)

    def _bind_events(self):
        for radio in (self.rb_cover_keep, self.rb_cover_replace, self.rb_cover_remove):
            radio.Bind(wx.EVT_RADIOBUTTON, self.on_cover_choice_change)
        for radio in (self.rb_target_convert, self.rb_target_inplace):
            radio.Bind(wx.EVT_RADIOBUTTON, self.on_cover_choice_change)
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)

    def _cover_possible_for_current_target(self):
        if self.rb_target_inplace.GetValue():
            return self._inplace_cover_possible
        return self._convert_cover_possible

    def _set_initial_focus(self):
        first_field = self.field_inputs.get(METADATA_TAG_FIELDS[0][0])
        if first_field:
            first_field.SetFocus()

    def on_cover_choice_change(self, event):
        self._update_cover_controls_state()
        event.Skip()

    def _update_cover_controls_state(self):
        cover_possible = self._cover_possible_for_current_target()
        tip = _("Cover art is not available for this target/format.") if not cover_possible else ""
        for radio in (self.rb_cover_keep, self.rb_cover_replace, self.rb_cover_remove):
            radio.Enable(cover_possible)
            radio.SetToolTip(tip)
        replace_selected = cover_possible and self.rb_cover_replace.GetValue()
        self.cover_picker.Enable(replace_selected)

    def on_ok(self, event):
        if self._cover_possible_for_current_target() and self.rb_cover_replace.GetValue():
            path = self.cover_picker.GetPath()
            if not path or not os.path.isfile(path):
                wx.MessageBox(
                    _("Please choose a valid image file for the cover."),
                    _("Cover art"),
                    wx.ICON_WARNING,
                )
                return
        event.Skip()

    def get_result(self):
        tags = {}
        for field_key, _label_msgid in METADATA_TAG_FIELDS:
            value = self.field_inputs[field_key].GetValue().strip()
            if self.is_batch:
                if value:
                    tags[field_key] = value
            else:
                tags[field_key] = value

        cover = {"action": "keep"}
        if self._cover_possible_for_current_target():
            if self.rb_cover_replace.GetValue():
                cover = {"action": "replace", "path": self.cover_picker.GetPath()}
            elif self.rb_cover_remove.GetValue():
                cover = {"action": "remove"}

        overrides = normalize_metadata_overrides({"tags": tags, "cover": cover})
        target = "inplace" if self.rb_target_inplace.GetValue() else "convert"
        return overrides, target
