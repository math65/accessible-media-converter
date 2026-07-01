"""Éditeur de segments accessible — « Cut / Split ».

Fenêtre d'édition (``wx.Frame`` — nécessaire pour porter une **barre de menus**)
permettant de découper un média temporel (audio ou vidéo) en régions à garder ou à
jeter, puis d'exporter soit **1 fichier reconcaténé** (les régions jetées, ex. les
pubs, disparaissent), soit **N fichiers séparés** (une sortie par région gardée).

Conçu pour un usage 100 % clavier + NVDA :
- **toutes les actions sont dans la barre de menus** (découvrables, avec accélérateurs) ;
- la zone centrale est une **unique liste de segments** focusable (NVDA lit chaque
  ligne : n°, début, fin, durée, garder/jeter) — pas de champ de boutons à traverser ;
- la position courante est annoncée à la voix (``core.speech.speak``).

Raccourcis (la liste des segments a le focus) :
- Flèches ← / → : reculer / avancer du **pas** courant ; Origine / Fin : début / fin ;
- Ctrl+← / Ctrl+→ : coupe précédente / suivante ;
- **Espace** : Lecture / Stop (Stop revient au point de départ de la lecture) ;
- **Ctrl+Espace** : Pause / Reprise (la pause fige au playhead) ;
- **S / E** : marquer début / fin d'une région à jeter ; **X** : couper ici ;
- **K** : basculer garder / jeter du segment sélectionné ; **Suppr** : retirer une coupe.

L'éditeur **bloque la fenêtre principale** tant qu'il est ouvert (parent désactivé).
Le résultat est renvoyé à l'appelant par le callback ``on_export(meta, plan, mode)``.
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


class SegmentEditorFrame(wx.Frame):
    def __init__(self, parent, meta, on_export):
        title = _("Cut / Split — {name}").format(name=os.path.basename(meta.full_path))
        super().__init__(parent, title=title, size=(720, 520),
                         style=wx.DEFAULT_FRAME_STYLE)

        self.meta = meta
        self.on_export_cb = on_export
        self.duration_ms = int(round(float(getattr(meta, 'duration', 0) or 0) * 1000))
        self.plan = segmods.new_plan(self.duration_ms)
        self.position_ms = 0
        self.step_ms = _STEP_CHOICES[_DEFAULT_STEP_INDEX][1]
        self._region_start_ms = None
        self._scrub_enabled = False
        self._play_anchor_ms = 0      # point de départ de la lecture (Stop y revient)
        self._last_playhead_ms = 0    # dernière tête de lecture connue (Pause s'y pose)
        self.player = AudioPlayer()
        self._pending_export_mode = None  # mode demandé, appliqué à la fermeture

        self._build_menu()
        self._build_ui()
        self._refresh_segment_list(select_index=0)
        self._update_status()

        # L'éditeur bloque la fenêtre principale tant qu'il est ouvert.
        if parent is not None:
            parent.Disable()

        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.CentreOnParent()
        self.Show()
        wx.CallAfter(self.list_ctrl.SetFocus)

    # ------------------------------------------------------------------ menus
    def _build_menu(self):
        bar = wx.MenuBar()

        m_file = wx.Menu()
        self._append(m_file, _("Export as one file (remove discarded segments)") + "\tCtrl+E",
                     lambda e: self._request_export(EXPORT_MODE_ONE_FILE))
        self._append(m_file, _("Export as separate files (one per kept region)") + "\tCtrl+Shift+E",
                     lambda e: self._request_export(EXPORT_MODE_SEPARATE))
        m_file.AppendSeparator()
        self._append(m_file, _("Close") + "\tCtrl+W", lambda e: self.Close())
        bar.Append(m_file, _("&File"))

        m_play = wx.Menu()
        # Espace / Ctrl+Espace : gérés par on_char_hook (indiqués en libellé, sans
        # accélérateur, pour ne pas entrer en conflit avec la liste / le hook).
        self._append(m_play, _("Play / Stop") + "  (Space)", lambda e: self._toggle_play())
        self._append(m_play, _("Pause / Resume") + "  (Ctrl+Space)", lambda e: self._toggle_pause())
        self._append(m_play, _("Play current segment"), lambda e: self._play_current_segment())
        m_play.AppendSeparator()
        self.item_scrub = m_play.AppendCheckItem(wx.ID_ANY, _("Scrub on move (audio preview)"))
        self.Bind(wx.EVT_MENU, self.on_scrub_toggle, self.item_scrub)
        bar.Append(m_play, _("&Playback"))

        m_nav = wx.Menu()
        self._append(m_nav, _("Backward") + "  (Left)", lambda e: self._seek_to(self.position_ms - self.step_ms))
        self._append(m_nav, _("Forward") + "  (Right)", lambda e: self._seek_to(self.position_ms + self.step_ms))
        self._append(m_nav, _("Previous cut") + "  (Ctrl+Left)", lambda e: self._seek_to(self._prev_boundary()))
        self._append(m_nav, _("Next cut") + "  (Ctrl+Right)", lambda e: self._seek_to(self._next_boundary()))
        self._append(m_nav, _("Go to start") + "  (Home)", lambda e: self._seek_to(0))
        self._append(m_nav, _("Go to end") + "  (End)", lambda e: self._seek_to(self.duration_ms))
        self._append(m_nav, _("Go to position...") + "\tCtrl+G", lambda e: self._do_goto())
        m_nav.AppendSeparator()
        m_step = wx.Menu()
        self._step_items = []
        for index, (label, _ms) in enumerate(_STEP_CHOICES):
            item = m_step.AppendRadioItem(wx.ID_ANY, label())
            if index == _DEFAULT_STEP_INDEX:
                item.Check(True)
            self.Bind(wx.EVT_MENU, lambda e, i=index: self._set_step(i), item)
            self._step_items.append(item)
        m_nav.AppendSubMenu(m_step, _("Step"))
        bar.Append(m_nav, _("&Navigation"))

        m_edit = wx.Menu()
        self._append(m_edit, _("Mark region start") + "  (S)", lambda e: self._mark_start())
        self._append(m_edit, _("Mark region end") + "  (E)", lambda e: self._mark_end())
        self._append(m_edit, _("Cut here") + "  (X)", lambda e: self._cut_here())
        self._append(m_edit, _("Keep / Discard segment") + "  (K)", lambda e: self._toggle_selected_keep())
        self._append(m_edit, _("Remove cut") + "  (Del)", lambda e: self._remove_selected_boundary())
        bar.Append(m_edit, _("&Edit"))

        self.SetMenuBar(bar)

    def _append(self, menu, label, handler):
        item = menu.Append(wx.ID_ANY, label)
        self.Bind(wx.EVT_MENU, handler, item)
        return item

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        header = wx.StaticText(panel, label=_("Total duration: {duration}").format(
            duration=format_timecode(self.duration_ms)))
        sizer.Add(header, 0, wx.ALL, 8)

        self.lbl_position = wx.StaticText(panel, label="")
        self.lbl_position.SetName(_("Current position"))
        sizer.Add(self.lbl_position, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.list_ctrl = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.list_ctrl.SetName(_("Segments"))
        self.list_ctrl.InsertColumn(0, _("#"), width=44)
        self.list_ctrl.InsertColumn(1, _("Start"), width=150)
        self.list_ctrl.InsertColumn(2, _("End"), width=150)
        self.list_ctrl.InsertColumn(3, _("Duration"), width=130)
        self.list_ctrl.InsertColumn(4, _("State"), width=100)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda e: self._go_to_selected_segment())
        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(sizer)

        self.CreateStatusBar()
        self.SetStatusText("")

    # ------------------------------------------------------------------ helpers
    def _boundaries(self):
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
        self.list_ctrl.DeleteAllItems()
        for i, seg in enumerate(self.plan.segments):
            row = self.list_ctrl.InsertItem(i, str(i + 1))
            self.list_ctrl.SetItem(row, 1, format_timecode(seg.start_ms))
            self.list_ctrl.SetItem(row, 2, format_timecode(seg.end_ms))
            self.list_ctrl.SetItem(row, 3, format_timecode(seg.duration_ms))
            self.list_ctrl.SetItem(row, 4, _("Keep") if seg.keep else _("Discard"))
        if select_index is not None:
            self._select_row(select_index)

    def _update_status(self):
        self.lbl_position.SetLabel(_("Current position: {time}").format(
            time=format_timecode(self.position_ms)))
        step_label = _STEP_CHOICES[self._step_index()][0]()
        kept = len(segmods.kept_regions(self.plan))
        self.SetStatusText(_("Step: {step}   |   Kept regions: {kept}").format(
            step=step_label, kept=kept))

    def _step_index(self):
        for i, (_label, ms) in enumerate(_STEP_CHOICES):
            if ms == self.step_ms:
                return i
        return _DEFAULT_STEP_INDEX

    def _announce_position(self):
        seg_index = self._segment_index_at(self.position_ms)
        if self.plan.segments:
            seg = self.plan.segments[seg_index]
            state = _("keep") if seg.keep else _("discard")
            speak(_("{time} — segment {index} of {total}, {state}").format(
                time=format_timecode(self.position_ms), index=seg_index + 1,
                total=len(self.plan.segments), state=state))
        else:
            speak(format_timecode(self.position_ms))

    def _seek_to(self, pos_ms, speak_it=True):
        self.position_ms = max(0, min(int(pos_ms), self.duration_ms))
        self.lbl_position.SetLabel(_("Current position: {time}").format(
            time=format_timecode(self.position_ms)))
        if self._scrub_enabled:
            # Scrub façon REAPER : chaque pas joue un court aperçu (l'audio EST le
            # retour ; pas d'annonce vocale par-dessus).
            self.player.scrub(self.meta.full_path, self.position_ms)
        else:
            self._stop_if_playing()
            if speak_it:
                self._announce_position()

    # ------------------------------------------------------------------ lecture
    def _stop_if_playing(self):
        if self.player.is_playing():
            self.player.stop()

    def _play_from(self, start_ms, end_ms=None):
        start = int(start_ms) if start_ms < self.duration_ms else 0
        self._play_anchor_ms = start
        self._last_playhead_ms = start
        self.player.play(
            self.meta.full_path, start_ms=start,
            end_ms=end_ms if end_ms is not None else self.duration_ms,
            on_position=lambda ms: wx.CallAfter(self._on_playhead, ms),
            on_finished=lambda: wx.CallAfter(self._on_play_finished),
        )

    def _toggle_play(self):
        """Espace : Lecture / Stop. Stop revient à l'ancre (point de départ)."""
        if self.player.is_playing():
            self.player.stop()
            self.position_ms = self._play_anchor_ms
            self._sync_position_label()
            speak(_("Stopped, back at {time}").format(time=format_timecode(self.position_ms)))
        else:
            speak(_("Playing"))
            self._play_from(self.position_ms)

    def _toggle_pause(self):
        """Ctrl+Espace : Pause / Reprise. Pause fige au playhead (le curseur s'y pose)."""
        if self.player.is_playing():
            self.player.stop()
            self.position_ms = max(0, min(int(self._last_playhead_ms), self.duration_ms))
            self._sync_position_label()
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
        self._sync_position_label()
        speak(_("Playing segment {index}").format(index=index + 1))
        self._play_from(seg.start_ms, end_ms=seg.end_ms)

    def _sync_position_label(self):
        self.lbl_position.SetLabel(_("Current position: {time}").format(
            time=format_timecode(self.position_ms)))

    def _on_playhead(self, ms):
        # Affiche la tête de lecture EN LECTURE seulement ; le curseur d'édition
        # self.position_ms ne bouge pas, pour que Stop y revienne.
        self._last_playhead_ms = max(0, min(int(ms), self.duration_ms))
        if self.player.is_playing():
            self.lbl_position.SetLabel(_("Current position: {time}").format(
                time=format_timecode(self._last_playhead_ms)))

    def _on_play_finished(self):
        self._sync_position_label()

    def on_scrub_toggle(self, event):
        self._scrub_enabled = self.item_scrub.IsChecked()
        if not self._scrub_enabled:
            self._stop_if_playing()
        speak(_("Scrub on") if self._scrub_enabled else _("Scrub off"))

    # ------------------------------------------------------------------ actions
    def _set_step(self, index):
        self.step_ms = _STEP_CHOICES[index][1]
        if 0 <= index < len(self._step_items):
            self._step_items[index].Check(True)
        self._update_status()
        speak(_("Step: {step}").format(step=_STEP_CHOICES[index][0]()))

    def _do_goto(self):
        with wx.TextEntryDialog(self, _("Go to position (HH:MM:SS.mmm):"),
                                _("Go to position")) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            ms = parse_timecode(dlg.GetValue())
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
        self._update_status()
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
        self._update_status()
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
        self._update_status()
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
        self._update_status()
        speak(_("Cut removed; segments merged"))

    def _go_to_selected_segment(self):
        index = self._selected_index()
        if index < 0 or index >= len(self.plan.segments):
            speak(_("No segment selected"))
            return
        self._seek_to(self.plan.segments[index].start_ms)

    # ------------------------------------------------------------------ navigation bornes
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

    # ------------------------------------------------------------------ export / close
    def _request_export(self, mode):
        error = segmods.validate(self.plan)
        if error:
            speak(error)
            wx.MessageBox(error, _("Cannot export"), wx.ICON_WARNING, self)
            return
        # L'export réel (dialogues de sortie + conversion) est fait par l'appelant,
        # après la fermeture de l'éditeur (parent réactivé).
        self._pending_export_mode = mode
        self.Close()

    def on_close(self, event):
        self.player.stop()
        parent = self.GetParent()
        if parent is not None:
            parent.Enable()
            parent.Raise()
        mode = self._pending_export_mode
        meta, plan, cb = self.meta, self.plan, self.on_export_cb
        self.Destroy()
        if mode is not None and cb is not None:
            wx.CallAfter(cb, meta, plan, mode)

    # ------------------------------------------------------------------ clavier
    def on_char_hook(self, event):
        key = event.GetKeyCode()

        # Ctrl+Espace = Pause / Reprise (Ctrl+Espace n'est utilisé par aucun contrôle).
        if key == wx.WXK_SPACE and event.ControlDown():
            self._toggle_pause(); return
        # Espace = Lecture / Stop (on remplace le rôle natif de la liste).
        if key == wx.WXK_SPACE and not event.ControlDown():
            self._toggle_play(); return

        # Marquage / segments.
        if key in (ord('S'), ord('s')):
            self._mark_start(); return
        if key in (ord('E'), ord('e')) and not event.ControlDown():
            self._mark_end(); return
        if key in (ord('X'), ord('x')):
            self._cut_here(); return
        if key in (ord('K'), ord('k')):
            self._toggle_selected_keep(); return
        if key == wx.WXK_DELETE:
            self._remove_selected_boundary(); return

        # Navigation temporelle (Haut/Bas restent à la liste pour choisir un segment).
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
