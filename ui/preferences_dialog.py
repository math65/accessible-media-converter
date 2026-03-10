import wx

from core.formatting import (
    DEFAULT_CONCURRENT_JOBS,
    DEFAULT_FFMPEG_THREADS,
    MAX_CONCURRENT_JOBS,
    MIN_CONCURRENT_JOBS,
    get_detected_cpu_threads,
    get_ffmpeg_thread_values,
)


class PreferencesDialog(wx.Dialog):
    def __init__(self, parent, current_settings):
        super().__init__(parent, title=_("Preferences"), size=(560, 460))
        self.SetName(_("Preferences dialog"))

        self.settings = current_settings
        self.mode = self.settings.get('output_mode', 'source')
        self.custom_path = self.settings.get('custom_output_path', '')
        self.existing_output_policy = self.settings.get('existing_output_policy', 'rename')
        self.open_output_folder_after_batch = bool(
            self.settings.get('open_output_folder_after_batch', False)
        )
        self.max_concurrent_jobs = self.settings.get('max_concurrent_jobs', DEFAULT_CONCURRENT_JOBS)
        self.ffmpeg_threads = self.settings.get('ffmpeg_threads', DEFAULT_FFMPEG_THREADS)
        self.continue_on_error = bool(self.settings.get('continue_on_error', True))
        self.detected_cpu_threads = get_detected_cpu_threads()
        self.ffmpeg_thread_values = (DEFAULT_FFMPEG_THREADS, *get_ffmpeg_thread_values())

        self._init_ui()
        self.Centre()

    def _init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        output_box = wx.StaticBox(panel, label=_("Output"))
        output_sizer = wx.StaticBoxSizer(output_box, wx.VERTICAL)

        self.rb_source = wx.RadioButton(panel, label=_("Same as source file"), style=wx.RB_GROUP)
        self.rb_source.SetName(_("Output in source folder"))
        output_sizer.Add(self.rb_source, 0, wx.ALL, 5)

        self.rb_custom = wx.RadioButton(panel, label=_("Specific folder:"))
        self.rb_custom.SetName(_("Output in specific folder"))
        output_sizer.Add(self.rb_custom, 0, wx.TOP | wx.LEFT, 5)

        hbox_custom = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_path = wx.TextCtrl(panel, value=self.custom_path, style=wx.TE_READONLY)
        self.btn_browse = wx.Button(panel, label=_("Browse..."))
        self.txt_path.SetName(_("Custom output folder path"))
        self.btn_browse.SetName(_("Browse output folder"))
        self.txt_path.SetToolTip(_("Selected destination folder path."))
        hbox_custom.Add(self.txt_path, 1, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 5)
        hbox_custom.Add(self.btn_browse, 0, wx.ALIGN_CENTER_VERTICAL)
        output_sizer.Add(hbox_custom, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 20)

        self.rb_ask = wx.RadioButton(panel, label=_("Ask every time (Batch)"))
        self.rb_ask.SetName(_("Ask output folder each time"))
        output_sizer.Add(self.rb_ask, 0, wx.ALL, 5)

        policy_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_policy = wx.StaticText(panel, label=_("Existing file policy"))
        self.choice_existing_output_policy = wx.Choice(
            panel,
            choices=[
                _("Rename automatically"),
                _("Overwrite existing file"),
                _("Skip existing file"),
            ],
        )
        self.choice_existing_output_policy.SetName(_("Existing file policy"))
        self.choice_existing_output_policy.SetToolTip(
            _("Choose what to do if an output file already exists.")
        )
        policy_row.Add(lbl_policy, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        policy_row.Add(self.choice_existing_output_policy, 1, wx.EXPAND)
        output_sizer.Add(policy_row, 0, wx.EXPAND | wx.ALL, 5)

        self.chk_open_output_folder = wx.CheckBox(panel, label=_("Open output folder when done"))
        self.chk_open_output_folder.SetName(_("Open output folder when done"))
        output_sizer.Add(self.chk_open_output_folder, 0, wx.ALL, 5)

        execution_box = wx.StaticBox(panel, label=_("Execution"))
        execution_sizer = wx.StaticBoxSizer(execution_box, wx.VERTICAL)

        jobs_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_jobs = wx.StaticText(panel, label=_("Max concurrent conversions"))
        self.choice_max_jobs = wx.Choice(
            panel,
            choices=[
                _("1 conversion"),
                _("2 conversions"),
                _("3 conversions"),
                _("4 conversions"),
            ],
        )
        current_max_jobs = max(MIN_CONCURRENT_JOBS, min(int(self.max_concurrent_jobs), MAX_CONCURRENT_JOBS))
        self.choice_max_jobs.SetSelection(current_max_jobs - MIN_CONCURRENT_JOBS)
        self.choice_max_jobs.SetName(_("Max concurrent conversions"))
        self.choice_max_jobs.SetToolTip(_("Set how many conversions can run at the same time."))
        jobs_row.Add(lbl_jobs, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        jobs_row.Add(self.choice_max_jobs, 0, wx.ALIGN_CENTER_VERTICAL)
        execution_sizer.Add(jobs_row, 0, wx.ALL, 5)

        threads_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_threads = wx.StaticText(panel, label=_("FFmpeg threads per conversion"))
        self.choice_ffmpeg_threads = wx.Choice(
            panel,
            choices=self._build_ffmpeg_thread_choice_labels(),
        )
        self.choice_ffmpeg_threads.SetName(_("FFmpeg threads per conversion"))
        self.choice_ffmpeg_threads.SetToolTip(_("Set how many FFmpeg threads each conversion can use."))
        self.choice_ffmpeg_threads.SetSelection(self._get_ffmpeg_threads_selection())
        threads_row.Add(lbl_threads, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        threads_row.Add(self.choice_ffmpeg_threads, 0, wx.ALIGN_CENTER_VERTICAL)
        execution_sizer.Add(threads_row, 0, wx.ALL, 5)

        self.chk_continue_on_error = wx.CheckBox(panel, label=_("Continue batch after an error"))
        self.chk_continue_on_error.SetName(_("Continue batch after an error"))
        execution_sizer.Add(self.chk_continue_on_error, 0, wx.ALL, 5)

        vbox.Add(output_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 15)
        vbox.Add(execution_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 15)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(panel, wx.ID_OK, label=_("OK"))
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, label=_("Cancel"))
        btn_ok.SetName(_("Save preferences"))
        btn_cancel.SetName(_("Cancel preferences"))
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 15)

        panel.SetSizer(vbox)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)

        self.Bind(wx.EVT_BUTTON, self.on_browse, self.btn_browse)
        self.Bind(wx.EVT_RADIOBUTTON, self.on_radio_change, self.rb_source)
        self.Bind(wx.EVT_RADIOBUTTON, self.on_radio_change, self.rb_custom)
        self.Bind(wx.EVT_RADIOBUTTON, self.on_radio_change, self.rb_ask)

        if self.mode == 'custom':
            self.rb_custom.SetValue(True)
        elif self.mode == 'ask':
            self.rb_ask.SetValue(True)
        else:
            self.rb_source.SetValue(True)

        self._init_existing_output_policy()
        self.chk_open_output_folder.SetValue(self.open_output_folder_after_batch)
        self.chk_continue_on_error.SetValue(self.continue_on_error)
        self._update_controls()

    def _init_existing_output_policy(self):
        policy_to_index = {
            'rename': 0,
            'overwrite': 1,
            'skip': 2,
        }
        self.choice_existing_output_policy.SetSelection(policy_to_index.get(self.existing_output_policy, 0))

    def _build_ffmpeg_thread_choice_labels(self):
        labels = [_("Automatic ({count} detected)").format(count=self.detected_cpu_threads)]
        for value in self.ffmpeg_thread_values[1:]:
            labels.append(_("{count} thread(s)").format(count=value))
        return labels

    def _get_ffmpeg_threads_selection(self):
        if isinstance(self.ffmpeg_threads, str) and self.ffmpeg_threads.lower() == DEFAULT_FFMPEG_THREADS:
            return 0

        try:
            parsed = int(self.ffmpeg_threads)
        except (TypeError, ValueError):
            return 0

        if parsed in self.ffmpeg_thread_values[1:]:
            return self.ffmpeg_thread_values.index(parsed)
        return 0

    def _update_controls(self):
        is_custom = self.rb_custom.GetValue()
        self.txt_path.Enable(is_custom)
        self.btn_browse.Enable(is_custom)

    def on_radio_change(self, event):
        self._update_controls()
        if self.rb_custom.GetValue():
            self.btn_browse.SetFocus()
            wx.CallAfter(self.btn_browse.SetFocus)

    def on_browse(self, event):
        with wx.DirDialog(self, _("Select Output Folder"), style=wx.DD_DEFAULT_STYLE) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.txt_path.SetValue(dlg.GetPath())

    def get_settings(self):
        if self.rb_source.GetValue():
            mode = 'source'
        elif self.rb_custom.GetValue():
            mode = 'custom'
        else:
            mode = 'ask'

        index_to_policy = {
            0: 'rename',
            1: 'overwrite',
            2: 'skip',
        }

        return {
            'output_mode': mode,
            'custom_output_path': self.txt_path.GetValue(),
            'existing_output_policy': index_to_policy.get(self.choice_existing_output_policy.GetSelection(), 'rename'),
            'open_output_folder_after_batch': self.chk_open_output_folder.GetValue(),
            'max_concurrent_jobs': self.choice_max_jobs.GetSelection() + MIN_CONCURRENT_JOBS,
            'ffmpeg_threads': self.ffmpeg_thread_values[self.choice_ffmpeg_threads.GetSelection()],
            'continue_on_error': self.chk_continue_on_error.GetValue(),
        }
