# Intégration DownAccess ↔ Access Media Converter

> Note de passation pour une session Claude Code travaillant sur **AMC**.
> Lire `CLAUDE.md` d'abord (architecture, règles a11y, i18n, build).

## Le contexte

DownAccess (`C:\Users\mathi\dev\dl`) **télécharge** des médias ; Access Media
Converter (ce dépôt) les **convertit**. Le couple reproduit **Downie → Permute** :
depuis un téléchargement terminé, l'utilisateur l'ouvre dans AMC pour une conversion
avancée.

**Côté DownAccess, c'est déjà fait et livré** (commit `62bfb0d`). Il :
- lance `AccessibleMediaConverter.exe "<chemin>"` pour passer un fichier à AMC ;
- localise l'exe via le registre de désinstallation Inno (AppId
  `{7E285383-842B-4F3B-8455-DF3F9F74F4F7}_is1`, valeur `InstallLocation`), sinon
  `%ProgramFiles%\Accessible Media Converter\`, sinon un réglage manuel ;
- expose deux surfaces : des entrées de format « Ouvrir avec Access Media Converter
  — vidéo / — audio seul » (qui téléchargent l'**original sans réencodage** puis
  appellent AMC), et un menu contextuel « Ouvrir dans Access Media Converter » sur un
  téléchargement terminé.

## Ce qu'AMC fait DÉJÀ bien (ne rien refaire)

Le plus dur est déjà en place côté AMC — c'est pour ça que DownAccess n'a eu qu'à
lancer l'exe :

- **Argument CLI** : `main.py:45` lit `sys.argv[1:]` et ne garde que les chemins
  existants. Passés à la fenêtre via `wx.CallAfter(frame.add_external_paths, …)`
  (`main.py:68-69`).
- **Instance unique + relais** : `main.py:51-56` (wx.SingleInstanceChecker
  `"AccessibleMediaConverter"`). Une 2ᵉ instance dépose ses chemins dans
  `core/single_instance.py` (`push_paths` → `pending_open.txt`) et sort ;
  l'instance maître draine toutes les 700 ms (`ui/main_window.py:804-820`,
  `drain_paths`) et remonte au premier plan.
- **Ajout en file** : `MainWindow.add_external_paths()` (`ui/main_window.py:785`)
  réutilise `_collect_media_paths` + `_process_added_files`.

Le contrat est donc stable : **`AccessibleMediaConverter.exe "<fichier>"`**.

## À FAIRE côté AMC

### 1. (Bug fiabilité) Ne plus perdre un fichier reçu pendant une conversion

`ui/main_window.py:789` :

```python
def add_external_paths(self, input_paths):
    if self.is_converting:
        return            # <-- le(s) fichier(s) transmis sont silencieusement perdus
```

Si AMC est en train de convertir quand DownAccess lui envoie un fichier (ou quand
l'utilisateur fait « Convertir avec… » depuis l'explorateur), le `return` jette les
chemins. Le tic du relais (`_on_external_watch_tick`, `:816`) appelle aussi
`add_external_paths` → même perte.

**Correctif attendu** : au lieu de jeter, **mettre en attente** et traiter quand la
conversion se termine (p. ex. accumuler dans une liste `self._pending_external_paths`
drainée à la fin de la conversion), ou ajouter les fichiers à la liste média (l'ajout
n'a pas besoin que la conversion soit finie ; seul le *lancement* d'une nouvelle
conversion doit attendre). Donner un retour visuel/statut (« N fichier(s) ajouté(s),
ils seront prêts à la fin de la conversion en cours »), conformément aux règles UX.

### 2. (Réciprocité) Faire la pub de DownAccess depuis AMC

Symétrique de la passerelle existante : depuis AMC, proposer/mentionner DownAccess
pour télécharger depuis le web (menu Aide ou bouton dédié). Page :
`https://github.com/math65/downaccess/releases`. Respecter les règles a11y (libellé
texte, dialogue natif) et i18n (`_()` + catalogues EN).

## Références

| Élément | Fichier | Ligne |
|---|---|---|
| Parsing argv + instance unique | `main.py` | 45, 51-69 |
| Réception externe (API) | `ui/main_window.py` | 785 |
| **Garde `is_converting` à corriger** | `ui/main_window.py` | **789** |
| Watcher du relais (700 ms) | `ui/main_window.py` | 804-820 |
| Relais fichier (push/drain) | `core/single_instance.py` | 24, 39 |
| Constantes (exe, AppId, GitHub) | `core/app_info.py` | 1-26 |

Côté DownAccess (pour info, ne pas modifier ici) : `app/core/amc_integration.py`,
menu contextuel + handoff dans `app/ui/main_window.py`, entrées de format dans
`app/ui/add_url_dialog.py`.
