"""Éditeur de segments accessible — « Cut / Split ».

Permet de découper un média temporel (audio ou vidéo) en régions à garder ou à
jeter, puis d'exporter soit **1 fichier reconcaténé** (les régions jetées, ex. les
pubs, disparaissent), soit **N fichiers séparés** (une sortie par région gardée).

Conçu pour un usage 100 % clavier + NVDA : il n'y a pas de scrub visuel. La
« timeline » est représentée par (a) la **position courante annoncée** et (b) la
**liste de segments navigable**. Chaque action de navigation ou de marquage parle
via :func:`core.speech.speak`, et chaque raccourci est doublé d'un bouton.

Raccourcis (quand le champ Position ou la liste a le focus) :
- Flèches ← / → : reculer / avancer du pas courant ;
- Origine / Fin : aller au début / à la fin ;
- Ctrl+← / Ctrl+→ : coupe précédente / suivante ;
- S : marquer le début d'une région ; E : marquer la fin (crée une région à jeter) ;
- X : couper à la position courante ; K : basculer garder / jeter du segment sélectionné ;
- Suppr : retirer une coupe (fusionne deux segments).

Phase 1 : navigation numérique uniquement (pas de lecture audio). La lecture et le
scrub arriveront en phase 2/3 via ``core/audio_player.py``.
"""

import os

import wx

from core.speech import speak
from core import segments as segmods
from core.audio_player import AudioPlayer


# Pas de déplacement proposés (libellé, millisecondes).
_STEP_CHOICES = [
    (lambda: _("10 ms"), 10),
    (lambda: _("100 ms"), 100),
    (lambda: _("1 second"), 1000),
    (lambda: _("10 seconds"), 10000),
    (lambda: _("1 minute"), 60000),
]
_DEFAULT_STEP_INDEX = 2  # 1 seconde

EXPORT_MODE_ONE_FILE = "one_file"
EXPORT_MODE_SEPARATE = "separate"


def format_timecode(ms):
    """Millisecondes → 'HH:MM:SS.mmm' (lisible et sans ambiguïté pour NVDA)."""
    ms = max(0, int(round(ms)))
    hours, rem = divmod(ms, 3600000)
    minutes, rem = divmod(rem, 60000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def parse_timecode(text):
    """Parse 'HH:MM:SS.mmm', 'MM:SS(.mmm)', 'SS(.mmm)' ou un nombre de secondes en
    millisecondes. Retourne None si non interprétable."""
    text = (text or "").strip().replace(',', '.')
    if not text:
        return None
    try:
        if ':' in text:
            parts = text.split(':')
            if len(parts) > 3:
                return None
            parts = [float(p) for p in parts]
            seconds = 0.0
            for part in parts:
                seconds = seconds * 60 + part
            return int(round(seconds * 1000))
        return int(round(float(text) * 1000))
    except (ValueError, TypeError):
        return None


class SegmentEditorDialog(wx.Dialog):
    def __init__(self, parent, meta):
        title = _("Cut / Split — {name}").format(name=os.path.basename(meta.full_path))
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self.meta = meta
        self.duration_ms = int(round(float(getattr(meta, 'duration', 0) or 0) * 1000))
        self.plan = segmods.new_plan(self.duration_ms)
        self.position_ms = 0
        self.step_ms = _STEP_CHOICES[_DEFAULT_STEP_INDEX][1]
        self._region_start_ms = None
        self._scrub_enabled = False
        self._play_anchor_ms = 0      # point de départ de la lecture (Stop y revient)
        self._last_playhead_ms = 0    # dernière tête de lecture connue (Pause s'y pose)
        self.player = AudioPlayer()
        # Résultats lus par l'appelant après ShowModal() == wx.ID_OK.
        self.export_mode = EXPORT_MODE_ONE_FILE

        self._build_ui()
        self._refresh_segment_list()
        self._update_position_display(speak_it=False)

        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.SetSize((640, 620))
        self.CentreOnParent()
        wx.CallAfter(self.txt_position.SetFocus)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)

        info = wx.StaticText(panel, label=_("Total duration: {duration}").format(
            duration=format_timecode(self.duration_ms)))
        outer.Add(info, 0, wx.ALL, 10)

        # --- Transport / position -------------------------------------------------
        nav_box = wx.StaticBox(panel, label=_("Navigation"))
        nav_box.SetWindowStyle(nav_box.GetWindowStyle() & ~wx.TAB_TRAVERSAL)
        nav_sizer = wx.StaticBoxSizer(nav_box, wx.VERTICAL)

        grid = wx.FlexGridSizer(rows=0, cols=2, vgap=8, hgap=10)
        grid.AddGrowableCol(1, 1)

        lbl_pos = wx.StaticText(panel, label=_("Current position:"))
        self.txt_position = wx.TextCtrl(panel, style=wx.TE_READONLY)
        self.txt_position.SetName(_("Current position"))
        self.txt_position.SetToolTip(_(
            "Arrow keys move by the step; Home/End go to start/end; "
            "Ctrl+Left/Right jump to cut points."))
        grid.Add(lbl_pos, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.txt_position, 1, wx.EXPAND)

        lbl_step = wx.StaticText(panel, label=_("Step:"))
        self.choice_step = wx.Choice(panel, choices=[label() for label, _ms in _STEP_CHOICES])
        self.choice_step.SetSelection(_DEFAULT_STEP_INDEX)
        self.choice_step.SetName(_("Step"))
        self.choice_step.Bind(wx.EVT_CHOICE, self.on_step_change)
        grid.Add(lbl_step, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.choice_step, 0, wx.EXPAND)

        lbl_goto = wx.StaticText(panel, label=_("Go to position (HH:MM:SS.mmm):"))
        self.txt_goto = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.txt_goto.SetName(_("Go to position"))
        self.txt_goto.Bind(wx.EVT_TEXT_ENTER, lambda e: self._do_goto())
        grid.Add(lbl_goto, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.txt_goto, 1, wx.EXPAND)

        nav_sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 8)

        nav_btns = wx.BoxSizer(wx.HORIZONTAL)
        btn_goto = wx.Button(panel, label=_("Go"))
        btn_goto.Bind(wx.EVT_BUTTON, lambda e: self._do_goto())
        self.btn_play = wx.Button(panel, label=_("Play / Stop (Space)"))
        self.btn_play.SetToolTip(_(
            "Space plays, then Stop returns to where playback started. "
            "Ctrl+Space pauses at the current point and resumes from there."))
        self.btn_play.Bind(wx.EVT_BUTTON, lambda e: self._toggle_play())
        btn_play_seg = wx.Button(panel, label=_("Play current segment"))
        btn_play_seg.Bind(wx.EVT_BUTTON, lambda e: self._play_current_segment())
        for btn in (btn_goto, self.btn_play, btn_play_seg):
            nav_btns.Add(btn, 0, wx.RIGHT, 8)
        nav_sizer.Add(nav_btns, 0, wx.LEFT | wx.BOTTOM, 8)

        self.chk_scrub = wx.CheckBox(panel, label=_("Scrub on move (audio preview)"))
        self.chk_scrub.SetName(_("Scrub on move"))
        self.chk_scrub.SetToolTip(_(
            "When enabled, each move plays a short audio preview at the new position."))
        self.chk_scrub.Bind(wx.EVT_CHECKBOX, self.on_scrub_toggle)
        nav_sizer.Add(self.chk_scrub, 0, wx.LEFT | wx.BOTTOM, 8)
        outer.Add(nav_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # --- Marquage -------------------------------------------------------------
        mark_box = wx.StaticBox(panel, label=_("Marking"))
        mark_box.SetWindowStyle(mark_box.GetWindowStyle() & ~wx.TAB_TRAVERSAL)
        mark_sizer = wx.StaticBoxSizer(mark_box, wx.HORIZONTAL)
        btn_mark_start = wx.Button(panel, label=_("Mark region start (S)"))
        btn_mark_start.Bind(wx.EVT_BUTTON, lambda e: self._mark_start())
        btn_mark_end = wx.Button(panel, label=_("Mark region end (E)"))
        btn_mark_end.Bind(wx.EVT_BUTTON, lambda e: self._mark_end())
        btn_cut = wx.Button(panel, label=_("Cut here (X)"))
        btn_cut.Bind(wx.EVT_BUTTON, lambda e: self._cut_here())
        for btn in (btn_mark_start, btn_mark_end, btn_cut):
            mark_sizer.Add(btn, 0, wx.RIGHT, 8)
        outer.Add(mark_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # --- Liste des segments ---------------------------------------------------
        list_box = wx.StaticBox(panel, label=_("Segments"))
        list_box.SetWindowStyle(list_box.GetWindowStyle() & ~wx.TAB_TRAVERSAL)
        list_sizer = wx.StaticBoxSizer(list_box, wx.VERTICAL)

        self.list_ctrl = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.list_ctrl.SetName(_("Segments"))
        self.list_ctrl.EnableCheckBoxes(True)
        self.list_ctrl.InsertColumn(0, _("#"), width=40)
        self.list_ctrl.InsertColumn(1, _("Start"), width=130)
        self.list_ctrl.InsertColumn(2, _("End"), width=130)
        self.list_ctrl.InsertColumn(3, _("Duration"), width=110)
        self.list_ctrl.InsertColumn(4, _("State"), width=90)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_CHECKED, self.on_item_checked)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self.on_item_checked)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_item_activated)
        list_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 8)

        seg_btns = wx.BoxSizer(wx.HORIZONTAL)
        btn_toggle = wx.Button(panel, label=_("Keep / Discard (K)"))
        btn_toggle.Bind(wx.EVT_BUTTON, lambda e: self._toggle_selected_keep())
        btn_remove = wx.Button(panel, label=_("Remove cut (Del)"))
        btn_remove.Bind(wx.EVT_BUTTON, lambda e: self._remove_selected_boundary())
        btn_goseg = wx.Button(panel, label=_("Go to segment start"))
        btn_goseg.Bind(wx.EVT_BUTTON, lambda e: self._go_to_selected_segment())
        for btn in (btn_toggle, btn_remove, btn_goseg):
            seg_btns.Add(btn, 0, wx.RIGHT, 8)
        list_sizer.Add(seg_btns, 0, wx.LEFT | wx.BOTTOM, 8)
        outer.Add(list_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # --- Mode d'export --------------------------------------------------------
        self.radio_mode = wx.RadioBox(
            panel, label=_("Export mode"),
            choices=[
                _("One file (remove discarded segments)"),
                _("Separate files (one per kept region)"),
            ],
            majorDimension=1, style=wx.RA_SPECIFY_COLS,
        )
        self.radio_mode.SetName(_("Export mode"))
        self.radio_mode.Bind(wx.EVT_RADIOBOX, self.on_mode_change)
        outer.Add(self.radio_mode, 0, wx.EXPAND | wx.ALL, 10)

        note = wx.StaticText(panel, label=_(
            "Export uses the output format and quality currently selected in the main window."))
        outer.Add(note, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # --- Boutons OK / Annuler -------------------------------------------------
        btns = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK, _("Export"))
        self.btn_ok.Bind(wx.EVT_BUTTON, self.on_export)
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, _("Cancel"))
        btns.AddButton(self.btn_ok)
        btns.AddButton(btn_cancel)
        btns.Realize()
        outer.Add(btns, 0, wx.EXPAND | wx.ALL, 10)

        panel.SetSizer(outer)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)

    # ------------------------------------------------------------------ helpers
    def _boundaries(self):
        """Positions de toutes les coupes (bornes internes), triées, avec 0 et fin."""
        marks = {0, self.duration_ms}
        for seg in self.plan.segments:
            marks.add(seg.start_ms)
            marks.add(seg.end_ms)
        return sorted(marks)

    def _selected_index(self):
        return self.list_ctrl.GetFirstSelected()

    def _select_row(self, index):
        if 0 <= index < self.list_ctrl.GetItemCount():
            self.list_ctrl.SetItemState(
                index, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
            self.list_ctrl.EnsureVisible(index)

    def _segment_index_at(self, pos_ms):
        for i, seg in enumerate(self.plan.segments):
            if seg.start_ms <= pos_ms < seg.end_ms:
                return i
        return max(0, len(self.plan.segments) - 1)

    def _refresh_segment_list(self, select_index=None):
        self._suppress_check_event = True
        self.list_ctrl.DeleteAllItems()
        for i, seg in enumerate(self.plan.segments):
            row = self.list_ctrl.InsertItem(i, str(i + 1))
            self.list_ctrl.SetItem(row, 1, format_timecode(seg.start_ms))
            self.list_ctrl.SetItem(row, 2, format_timecode(seg.end_ms))
            self.list_ctrl.SetItem(row, 3, format_timecode(seg.duration_ms))
            self.list_ctrl.SetItem(row, 4, _("Keep") if seg.keep else _("Discard"))
            self.list_ctrl.CheckItem(row, seg.keep)
        self._suppress_check_event = False
        if select_index is not None:
            self._select_row(select_index)

    def _update_position_display(self, speak_it=True):
        self.txt_position.ChangeValue(format_timecode(self.position_ms))
        if speak_it:
            seg_index = self._segment_index_at(self.position_ms)
            seg = self.plan.segments[seg_index] if self.plan.segments else None
            state = ""
            if seg is not None:
                state = _("keep") if seg.keep else _("discard")
                speak(_("{time} — segment {index} of {total}, {state}").format(
                    time=format_timecode(self.position_ms),
                    index=seg_index + 1, total=len(self.plan.segments), state=state))
            else:
                speak(format_timecode(self.position_ms))

    def _seek_to(self, pos_ms, speak_it=True):
        self.position_ms = max(0, min(int(pos_ms), self.duration_ms))
        if self._scrub_enabled:
            # Scrub façon REAPER : chaque pas joue un court aperçu à la nouvelle
            # position (l'audio EST le retour ; pas d'annonce vocale par-dessus).
            self.txt_position.ChangeValue(format_timecode(self.position_ms))
            self.player.scrub(self.meta.full_path, self.position_ms)
        else:
            # Sans scrub, se déplacer met la lecture continue en pause.
            self._stop_if_playing()
            self._update_position_display(speak_it=speak_it)

    # ------------------------------------------------------------------ lecture
    def _stop_if_playing(self):
        if self.player.is_playing():
            self.player.stop()

    def _play_from(self, start_ms, end_ms=None):
        """Démarre la lecture ; ``start_ms`` devient l'**ancre** (point où Stop
        ramènera le curseur). Le curseur d'édition ne bouge pas pendant l'écoute."""
        start = int(start_ms) if start_ms < self.duration_ms else 0
        self._play_anchor_ms = start
        self._last_playhead_ms = start
        self.player.play(
            self.meta.full_path, start_ms=start, end_ms=end_ms if end_ms is not None else self.duration_ms,
            on_position=lambda ms: wx.CallAfter(self._on_playhead, ms),
            on_finished=lambda: wx.CallAfter(self._on_play_finished),
        )

    def _toggle_play(self):
        """Espace : Lecture / Stop. Stop revient à l'ancre (point de départ)."""
        if self.player.is_playing():
            self.player.stop()
            self.position_ms = self._play_anchor_ms
            self.txt_position.ChangeValue(format_timecode(self.position_ms))
            speak(_("Stopped, back at {time}").format(time=format_timecode(self.position_ms)))
        else:
            speak(_("Playing"))
            self._play_from(self.position_ms)

    def _toggle_pause(self):
        """Ctrl+Espace : Pause / Reprise. Pause fige au playhead (le curseur s'y
        pose) ; une reprise repart de là."""
        if self.player.is_playing():
            self.player.stop()
            self.position_ms = max(0, min(int(self._last_playhead_ms), self.duration_ms))
            self.txt_position.ChangeValue(format_timecode(self.position_ms))
            speak(_("Paused at {time}").format(time=format_timecode(self.position_ms)))
        else:
            speak(_("Playing"))
            self._play_from(self.position_ms)

    def _play_current_segment(self):
        index = self._selected_index()
        if index < 0:
            index = self._segment_index_at(self.position_ms)
        if index < 0 or index >= len(self.plan.segments):
            speak(_("No segment selected"))
            return
        seg = self.plan.segments[index]
        self._stop_if_playing()
        self.position_ms = seg.start_ms
        self.txt_position.ChangeValue(format_timecode(self.position_ms))
        speak(_("Playing segment {index}").format(index=index + 1))
        self._play_from(seg.start_ms, end_ms=seg.end_ms)

    def _on_playhead(self, ms):
        # Affiche la tête de lecture EN LECTURE seulement (visuel, silencieux) : le
        # curseur d'édition self.position_ms ne bouge pas, pour que Stop y revienne.
        self._last_playhead_ms = max(0, min(int(ms), self.duration_ms))
        if self.player.is_playing():
            self.txt_position.ChangeValue(format_timecode(self._last_playhead_ms))

    def _on_play_finished(self):
        # Fin naturelle de l'écoute : on ré-affiche le curseur d'édition.
        self.txt_position.ChangeValue(format_timecode(self.position_ms))

    def on_scrub_toggle(self, event):
        self._scrub_enabled = self.chk_scrub.GetValue()
        if not self._scrub_enabled:
            self._stop_if_playing()
        speak(_("Scrub on") if self._scrub_enabled else _("Scrub off"))

    def stop_playback(self):
        """À appeler par l'appelant après ShowModal (avant Destroy)."""
        self.player.stop()

    def on_close(self, event):
        self.player.stop()
        event.Skip()

    # ------------------------------------------------------------------ actions
    def _do_goto(self):
        ms = parse_timecode(self.txt_goto.GetValue())
        if ms is None:
            speak(_("Invalid time"))
            wx.MessageBox(_("Please enter a valid time (HH:MM:SS.mmm)."),
                          _("Invalid time"), wx.ICON_WARNING, self)
            return
        self._seek_to(ms)

    def _cut_here(self):
        idx = segmods.split_at(self.plan, self.position_ms)
        if idx < 0:
            speak(_("No cut added here"))
            return
        self._refresh_segment_list(select_index=idx)
        speak(_("Cut added at {time}").format(time=format_timecode(self.position_ms)))

    def _mark_start(self):
        self._region_start_ms = self.position_ms
        speak(_("Region start marked at {time}").format(time=format_timecode(self.position_ms)))

    def _mark_end(self):
        if self._region_start_ms is None:
            speak(_("Mark a region start first"))
            return
        start = self._region_start_ms
        end = self.position_ms
        if end == start:
            speak(_("Region start and end are identical"))
            return
        segmods.mark_region(self.plan, start, end, keep=False)
        self._region_start_ms = None
        lo, hi = (start, end) if start < end else (end, start)
        target = self._segment_index_at(lo + 1)
        self._refresh_segment_list(select_index=target)
        speak(_("Discard region created from {start} to {end}").format(
            start=format_timecode(lo), end=format_timecode(hi)))

    def _toggle_selected_keep(self):
        index = self._selected_index()
        if index < 0:
            speak(_("No segment selected"))
            return
        segmods.toggle_keep(self.plan, index)
        keep = self.plan.segments[index].keep
        self._refresh_segment_list(select_index=index)
        speak(_("Segment {index}: {state}").format(
            index=index + 1, state=_("keep") if keep else _("discard")))

    def _remove_selected_boundary(self):
        index = self._selected_index()
        if index < 0:
            speak(_("No segment selected"))
            return
        if index >= len(self.plan.segments) - 1:
            speak(_("The last segment has no following cut to remove"))
            return
        segmods.remove_boundary(self.plan, index)
        self._refresh_segment_list(select_index=index)
        speak(_("Cut removed; segments merged"))

    def _go_to_selected_segment(self):
        index = self._selected_index()
        if index < 0 or index >= len(self.plan.segments):
            speak(_("No segment selected"))
            return
        self._seek_to(self.plan.segments[index].start_ms)

    # ------------------------------------------------------------------ events
    def on_step_change(self, event):
        idx = self.choice_step.GetSelection()
        if idx != wx.NOT_FOUND:
            self.step_ms = _STEP_CHOICES[idx][1]

    def on_mode_change(self, event):
        self.export_mode = EXPORT_MODE_ONE_FILE if self.radio_mode.GetSelection() == 0 else EXPORT_MODE_SEPARATE

    def on_item_checked(self, event):
        if getattr(self, '_suppress_check_event', False):
            return
        index = event.GetIndex()
        if 0 <= index < len(self.plan.segments):
            keep = self.list_ctrl.IsItemChecked(index)
            segmods.set_keep(self.plan, index, keep)
            self.list_ctrl.SetItem(index, 4, _("Keep") if keep else _("Discard"))

    def on_item_activated(self, event):
        self._go_to_selected_segment()

    def on_char_hook(self, event):
        key = event.GetKeyCode()
        focus = wx.Window.FindFocus()

        # Champ d'édition « Aller à » : ne rien intercepter (Entrée gérée à part).
        if focus is self.txt_goto:
            event.Skip()
            return

        transport = focus is self.txt_position

        # Marquage / segments : partout sauf dans le menu « Pas » et le mode d'export
        # (où les lettres servent à la sélection rapide) et le champ « Aller à »
        # (déjà écarté). Fonctionne donc aussi quand le focus est sur un bouton.
        if focus not in (self.choice_step, self.radio_mode):
            if key in (ord('S'), ord('s')):
                self._mark_start(); return
            if key in (ord('E'), ord('e')):
                self._mark_end(); return
            if key in (ord('X'), ord('x')):
                self._cut_here(); return
            if key in (ord('K'), ord('k')):
                self._toggle_selected_keep(); return
            if key == wx.WXK_DELETE:
                self._remove_selected_boundary(); return

        # Ctrl+Espace = Pause / Reprise, partout sauf dans les contrôles qui se
        # servent des lettres/flèches (menu « Pas », mode d'export ; « Aller à »
        # déjà écarté). Ctrl+Espace n'est utilisé nativement par aucun contrôle.
        if key == wx.WXK_SPACE and event.ControlDown() and focus not in (self.choice_step, self.radio_mode):
            self._toggle_pause(); return

        # Espace = Lecture / Stop, depuis le champ Position (ailleurs, Espace doit
        # activer le bouton ou la case à cocher qui a le focus).
        if transport and key == wx.WXK_SPACE and not event.ControlDown():
            self._toggle_play(); return

        # Navigation temporelle : active PARTOUT sauf dans les contrôles qui se
        # servent nativement des flèches (liste des segments, menu « Pas », mode
        # d'export) — et le champ « Aller à », déjà écarté plus haut. Ainsi les
        # flèches avancent/reculent même quand le focus est sur un bouton.
        if focus not in (self.choice_step, self.radio_mode, self.list_ctrl):
            if key == wx.WXK_LEFT:
                self._seek_to(self._prev_boundary() if event.ControlDown()
                              else self.position_ms - self.step_ms)
                return
            if key == wx.WXK_RIGHT:
                self._seek_to(self._next_boundary() if event.ControlDown()
                              else self.position_ms + self.step_ms)
                return
            if key == wx.WXK_HOME:
                self._seek_to(0); return
            if key == wx.WXK_END:
                self._seek_to(self.duration_ms); return

        event.Skip()

    def _prev_boundary(self):
        prev = 0
        for mark in self._boundaries():
            if mark < self.position_ms:
                prev = mark
            else:
                break
        return prev

    def _next_boundary(self):
        for mark in self._boundaries():
            if mark > self.position_ms:
                return mark
        return self.duration_ms

    def on_export(self, event):
        error = segmods.validate(self.plan)
        if error:
            speak(error)
            wx.MessageBox(error, _("Cannot export"), wx.ICON_WARNING, self)
            return  # ne pas fermer : laisser corriger
        self.export_mode = EXPORT_MODE_ONE_FILE if self.radio_mode.GetSelection() == 0 else EXPORT_MODE_SEPARATE
        self.player.stop()
        self.EndModal(wx.ID_OK)
