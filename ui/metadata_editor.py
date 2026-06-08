import os

import wx
from wx.lib.scrolledpanel import ScrolledPanel

from core.episode_parse import parse_episode_from_filename, parse_track_from_filename
from core.metadata_edit import (
    AUDIO_BATCH_FIELDS,
    AUDIO_METADATA_FIELDS,
    CONTENT_TYPE_SERIES,
    MULTILINE_TAG_KEYS,
    NUMERIC_TAG_KEYS,
    VIDEO_CONTENT_TYPES,
    VIDEO_SERIES_BATCH_FIELDS,
    detect_content_type,
    fields_for_content_type,
    format_supports_cover,
    normalize_metadata_overrides,
    read_prefill_tags,
    source_supports_cover,
)


def _is_integer(text):
    try:
        int(text)
        return True
    except ValueError:
        return False


class MetadataEditorDialog(wx.Dialog):
    """Edit file-level tags and cover art for one or several media files.

    Returns, via get_result(), a tuple (overrides, target) where target is
    "convert" (apply during the next conversion) or "inplace" (re-tag the
    original file now without re-encoding). The tag area scrolls so it copes
    with the longer audio field set (and the multi-line Lyrics box) on small
    screens, while OK/Cancel stay pinned and reachable.
    """

    def __init__(self, parent, metas, target_format):
        self.metas = list(metas)
        self.is_batch = len(self.metas) > 1
        self.target_format = target_format

        if self.is_batch:
            title = _("Edit metadata ({count} files)").format(count=len(self.metas))
        else:
            title = _("Edit metadata: {name}").format(name=self.metas[0].filename)

        super().__init__(
            parent, title=title, size=(580, 680),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetName(_("Edit metadata dialog"))

        self._convert_cover_possible = format_supports_cover(target_format)
        self._inplace_cover_possible = all(
            source_supports_cover(getattr(meta, "source_format_name", "")) for meta in self.metas
        )

        # Video files get a content-type selector (film / series / other) that
        # swaps the field set; audio keeps the music tags. A batch enables
        # per-file number auto-detection (episode for series, track for audio).
        self.is_video = any(getattr(meta, "has_video", False) for meta in self.metas)
        self.content_type = detect_content_type(self.metas[0]) if self.is_video else None
        self.autodetect_numbers = True

        # Typed values are preserved across field-set switches; seed from the
        # single-file prefill (batch starts blank so empty fields stay untouched).
        self._values = {} if self.is_batch else dict(read_prefill_tags(getattr(self.metas[0], "format_tags", {})))
        if not self.is_batch:
            self._prefill_from_filename()

        self.active_fields = self._resolve_fields()
        self.field_inputs = {}

        # Scrollable content (everything except the buttons) + pinned buttons.
        self.scroll = ScrolledPanel(self)
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)

        self._build_intro()
        if self.is_video:
            self._build_content_type_selector()
        if self.is_batch:
            self._build_autodetect_checkbox()
        self._build_tag_fields()
        self._build_cover_section()
        self._build_target_section()
        self.scroll.SetSizer(self.main_sizer)
        self.scroll.SetupScrolling(scroll_x=False, scroll_y=True)

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(self.scroll, 1, wx.EXPAND)
        self._build_buttons(dialog_sizer)
        self.SetSizer(dialog_sizer)

        self.Centre()
        self._bind_events()
        self._update_cover_controls_state()
        wx.CallAfter(self._set_initial_focus)

    def _build_intro(self):
        if self.is_batch:
            intro = wx.StaticText(
                self.scroll,
                label=_("Fields left empty are not changed on the selected files."),
            )
            intro.Wrap(520)
            self.main_sizer.Add(intro, 0, wx.ALL, 12)

    def _prefill_from_filename(self):
        source = getattr(self.metas[0], "full_path", "") or getattr(self.metas[0], "filename", "")
        if self.is_video:
            parsed = parse_episode_from_filename(source)
            if not parsed:
                return
            if not self._values.get("season_number"):
                self._values["season_number"] = str(parsed["season"])
            if not self._values.get("episode_id"):
                self._values["episode_id"] = str(parsed["episode"])
            if parsed.get("show") and not self._values.get("show"):
                self._values["show"] = parsed["show"]
        else:
            parsed = parse_track_from_filename(source)
            if not parsed:
                return
            if not self._values.get("track"):
                self._values["track"] = str(parsed["track"])
            if parsed.get("disc") and not self._values.get("disc"):
                self._values["disc"] = str(parsed["disc"])

    def _resolve_fields(self):
        if not self.is_video:
            if self.is_batch and self.autodetect_numbers:
                # Track/disc come from each file name, so only shared fields show.
                return AUDIO_BATCH_FIELDS
            return AUDIO_METADATA_FIELDS
        if self.is_batch and self.content_type == CONTENT_TYPE_SERIES and self.autodetect_numbers:
            return VIDEO_SERIES_BATCH_FIELDS
        return fields_for_content_type(self.content_type)

    def _build_content_type_selector(self):
        row = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(self.scroll, label=_("Content type:"))
        self.choice_content_type = wx.Choice(
            self.scroll,
            choices=[_(content_label) for _ctype, content_label, _fields in VIDEO_CONTENT_TYPES],
        )
        self.choice_content_type.SetName(_("Content type"))
        type_ids = [ctype for ctype, _label, _fields in VIDEO_CONTENT_TYPES]
        if self.content_type in type_ids:
            self.choice_content_type.SetSelection(type_ids.index(self.content_type))
        self.choice_content_type.Bind(wx.EVT_CHOICE, self.on_content_type_change)
        row.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        row.Add(self.choice_content_type, 0, wx.ALIGN_CENTER_VERTICAL)
        self.main_sizer.Add(row, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)

    def _build_autodetect_checkbox(self):
        # Audio batch -> track; video series batch -> season/episode.
        label = (
            _("Detect season and episode from each file name")
            if self.is_video
            else _("Detect track number from each file name")
        )
        self.cb_autodetect = wx.CheckBox(self.scroll, label=label)
        self.cb_autodetect.SetName(label)
        self.cb_autodetect.SetValue(self.autodetect_numbers)
        self.cb_autodetect.Bind(wx.EVT_CHECKBOX, self.on_autodetect_toggle)
        self.main_sizer.Add(self.cb_autodetect, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        self._update_autodetect_visibility()

    def _update_autodetect_visibility(self):
        if not hasattr(self, "cb_autodetect"):
            return
        # Audio batch always; video batch only for series (film/other have no
        # per-file numbers to detect).
        visible = self.is_batch and (not self.is_video or self.content_type == CONTENT_TYPE_SERIES)
        self.cb_autodetect.Show(visible)

    def on_autodetect_toggle(self, event):
        self.autodetect_numbers = self.cb_autodetect.GetValue()
        self._populate_tag_fields(self._resolve_fields())
        self.Layout()
        event.Skip()

    def autodetect_kind(self):
        """'episode' | 'track' | None — what to read from each file name."""
        if not (self.is_batch and self.autodetect_numbers):
            return None
        if not self.is_video:
            return "track"
        if self.content_type == CONTENT_TYPE_SERIES:
            return "episode"
        return None

    def _build_tag_fields(self):
        tag_box = wx.StaticBox(self.scroll, label=_("Tags"))
        tag_box.SetWindowStyle(tag_box.GetWindowStyle() & ~wx.TAB_TRAVERSAL)
        tag_sizer = wx.StaticBoxSizer(tag_box, wx.VERTICAL)

        # The grid is rebuilt when the field set changes, so it lives in its own
        # container sizer that we can clear and repopulate.
        self.tags_container = wx.BoxSizer(wx.VERTICAL)
        tag_sizer.Add(self.tags_container, 0, wx.EXPAND | wx.ALL, 10)
        self.main_sizer.Add(tag_sizer, 0, wx.EXPAND | wx.ALL, 8)

        self._populate_tag_fields(self.active_fields)

    def _populate_tag_fields(self, fields):
        # Keep anything already typed before swapping the field set, so shared
        # fields survive a content-type / auto-detect change.
        for field_key, ctrl in self.field_inputs.items():
            self._values[field_key] = ctrl.GetValue()

        self.tags_container.Clear(delete_windows=True)
        self.field_inputs = {}

        grid = wx.FlexGridSizer(rows=0, cols=2, vgap=8, hgap=10)
        grid.AddGrowableCol(1, 1)
        for field_key, label_msgid in fields:
            label = wx.StaticText(self.scroll, label=_(label_msgid) + ":")
            if field_key in MULTILINE_TAG_KEYS:
                text_ctrl = wx.TextCtrl(
                    self.scroll, value=self._values.get(field_key, ""),
                    style=wx.TE_MULTILINE, size=(-1, 70),
                )
                grid.Add(label, 0, wx.ALIGN_TOP | wx.TOP, 4)
            else:
                text_ctrl = wx.TextCtrl(self.scroll, value=self._values.get(field_key, ""))
                grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
            text_ctrl.SetName(_(label_msgid))
            grid.Add(text_ctrl, 0, wx.EXPAND)
            self.field_inputs[field_key] = text_ctrl

        self.tags_container.Add(grid, 0, wx.EXPAND)
        self.active_fields = tuple(fields)
        self.main_sizer.Layout()
        self.scroll.Layout()
        self.scroll.SetupScrolling(scroll_x=False, scroll_y=True, scrollToTop=False)

    def on_content_type_change(self, event):
        selection = self.choice_content_type.GetSelection()
        if selection != wx.NOT_FOUND:
            self.content_type = VIDEO_CONTENT_TYPES[selection][0]
            self._update_autodetect_visibility()
            self._populate_tag_fields(self._resolve_fields())
            self.Layout()
        event.Skip()

    def _build_cover_section(self):
        cover_box = wx.StaticBox(self.scroll, label=_("Cover art"))
        cover_box.SetWindowStyle(cover_box.GetWindowStyle() & ~wx.TAB_TRAVERSAL)
        cover_sizer = wx.StaticBoxSizer(cover_box, wx.VERTICAL)

        if not self.is_batch:
            state = _("present") if getattr(self.metas[0], "has_cover_art", False) else _("none")
            self.lbl_cover_state = wx.StaticText(
                self.scroll, label=_("Embedded cover art: {state}").format(state=state)
            )
            cover_sizer.Add(self.lbl_cover_state, 0, wx.ALL, 6)

        self.rb_cover_keep = wx.RadioButton(self.scroll, label=_("Keep current cover"), style=wx.RB_GROUP)
        self.rb_cover_replace = wx.RadioButton(self.scroll, label=_("Replace with an image file..."))
        self.rb_cover_remove = wx.RadioButton(self.scroll, label=_("Remove cover"))
        self.rb_cover_keep.SetValue(True)
        for radio in (self.rb_cover_keep, self.rb_cover_replace, self.rb_cover_remove):
            radio.SetName(radio.GetLabel())
            cover_sizer.Add(radio, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)

        picker_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_picker = wx.StaticText(self.scroll, label=_("Image file:"))
        self.cover_picker = wx.FilePickerCtrl(
            self.scroll,
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
        target_box = wx.StaticBox(self.scroll, label=_("Apply to"))
        target_box.SetWindowStyle(target_box.GetWindowStyle() & ~wx.TAB_TRAVERSAL)
        target_sizer = wx.StaticBoxSizer(target_box, wx.VERTICAL)

        self.rb_target_convert = wx.RadioButton(
            self.scroll, label=_("When converting (output file)"), style=wx.RB_GROUP
        )
        self.rb_target_inplace = wx.RadioButton(
            self.scroll, label=_("Re-tag the original file now (no re-encoding)")
        )
        self.rb_target_convert.SetValue(True)
        for radio in (self.rb_target_convert, self.rb_target_inplace):
            radio.SetName(radio.GetLabel())
            target_sizer.Add(radio, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)

        self.main_sizer.Add(target_sizer, 0, wx.EXPAND | wx.ALL, 8)

    def _build_buttons(self, dialog_sizer):
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK, label=_("OK"))
        btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_("Cancel"))
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        dialog_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
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
        if self.active_fields:
            first_field = self.field_inputs.get(self.active_fields[0][0])
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
        # Numeric-only fields (e.g. Season): MP4 stores them as integer atoms and
        # silently turns non-numbers into 0, so reject non-numeric input here.
        for field_key, label_msgid in self.active_fields:
            if field_key in NUMERIC_TAG_KEYS:
                value = self.field_inputs[field_key].GetValue().strip()
                if value and not _is_integer(value):
                    wx.MessageBox(
                        _("{field} must be a whole number.").format(field=_(label_msgid)),
                        _("Invalid value"),
                        wx.ICON_WARNING,
                    )
                    self.field_inputs[field_key].SetFocus()
                    return

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
        for field_key, _label_msgid in self.active_fields:
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
