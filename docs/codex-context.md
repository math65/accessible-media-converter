# Contexte Agent

## Identite du projet

- Produit actuel : `Accessible Media Converter`
- Nature : application desktop Windows de transcodage media basee sur `wxPython` et `FFmpeg`
- Version repere actuelle : `1.7.1`
- Positionnement : accessibilite forte, usage clavier, conversion media reelle pour utilisateurs NVDA et grand public Windows
- Usage principal de ce fichier : memoire de reprise pour agents IA, lisible humainement, suffisante pour reprendre une maintenance release sans dependre du chat precedent

## Priorites et invariants

- La cible produit actuelle est **Windows uniquement**.
- L'ordre de priorite produit est : **accessibilite > simplicite > controle avance**.
- La compatibilite lecteurs d'ecran et les parcours clavier priment sur l'ajout de complexite.
- La simplicite d'usage passe avant l'exposition brute de reglages experts.
- Les options avancees restent permises, mais seulement apres clarte et accessibilite.
- La documentation locale embarquee doit rester **strictement orientee utilisateur**.
- Ne pas deriver ce fichier vers une documentation technique exhaustive ni dupliquer la `README`.
- Ce fichier doit decrire les workflows de reprise reelle : FFmpeg, build Windows, release GitHub, validations.

## Vue produit actuelle

L'application est une base v1.x deja fonctionnelle, pas un prototype. Elle couvre aujourd'hui :

- conversion audio vers audio
- conversion video vers video `MP4` / `MKV`
- extraction audio depuis video
- gestion explicite des pistes video, audio et sous-titres
- conversions par lot avec parallelisme configurable
- mise a jour applicative via GitHub
- contact support integre
- mode debug avec restauration de session
- packaging Windows avec PyInstaller et Inno Setup
- preference de langue utilisateur avec `auto`, `fr`, `en`
- documentation locale utilisateur FR et EN integree localement

## Etat du code et dette utile a connaitre

- Le centre d'orchestration UI est tres concentre dans `ui/main_window.py`.
- Il n'y a pas de tests automatises dans le depot.
- La fiabilite repose surtout sur la lecture du code, les builds et les tests manuels.
- L'i18n repose sur `gettext`, avec anglais source et preference utilisateur `auto | fr | en`.
- Le packaging Windows et la chaine de release sont deja presents et actifs.
- Le module updater applicatif est dans `core/updater.py`.
- Le script de build/release Windows est `scripts/build_release.ps1`.
- Le script de maintenance FFmpeg est `scripts/update_embedded_ffmpeg.ps1`.
- Les binaires `bin/ffmpeg.exe` et `bin/ffprobe.exe` restent suivis par Git malgre leur presence dans `.gitignore`.

## Etat reel au dernier controle

- Date du dernier controle complet : `2026-03-11`
- Commit de reference du dernier controle stable : `6a12c2a`
- Version applicative courante : `1.7.1`
- Release GitHub publique courante : `v1.7.1`
- URL release GitHub : `https://github.com/math65/accessible-media-converter/releases/tag/v1.7.1`
- Asset canonique publie : `AccessibleMediaConverter-Setup.exe`
- Asset versionne encore publie pour compatibilite updater avant `1.8.0` : `AccessibleMediaConverter-Setup-1.7.1.exe`
- FFmpeg embarque dans `bin/` au dernier controle : `2026-03-09-git-9b7439c31b-essentials_build`
- FFmpeg embarque dans le `dist/` regenere pour `1.7.1` au dernier controle : `2026-03-09-git-9b7439c31b-essentials_build`
- Le module updater applicatif a ete smoke-teste apres publication de `v1.7.1` : il resolvait bien `1.7.1`, l'asset canonique `AccessibleMediaConverter-Setup.exe`, la date de publication et les notes de release.
- Le dernier controle stable a eu lieu apres commit, build, push et publication de `v1.7.1`.
- Attention critique : ne jamais recopier "depot propre" dans ce fichier sans reexecuter `git status`.
- Attention critique : si ce fichier vient d'etre modifie dans le fil courant et n'est pas encore committe, le depot n'est plus propre.

## Pre-requis de build/release

Checklist minimale avant toute release ou rebuild complet :

- Windows
- `.venv` present et fonctionnel
- dependances Python installees dans `.venv` : `wxPython`, `PyInstaller`, `polib`
- `Inno Setup 6` installe, avec `ISCC.exe` trouvable via `PATH` ou emplacement standard
- `bin/ffmpeg.exe` present
- `bin/ffprobe.exe` present
- `docs/fr/index.html` present
- `docs/en/index.html` present
- `UniversalTranscoder.spec` present
- `installer/UniversalTranscoder.iss` present
- pour publier une release GitHub : `gh` installe et authentifie

Comportement reel de `scripts/build_release.ps1` :

- verifie la presence de `.venv\Scripts\python.exe`
- verifie la presence de `UniversalTranscoder.spec`
- verifie la presence de `installer\UniversalTranscoder.iss`
- verifie la presence de `docs\fr\index.html` et `docs\en\index.html`
- verifie la presence de `bin\ffmpeg.exe` et `bin\ffprobe.exe`
- verifie que `PyInstaller` et `polib` sont importables
- compile les `.po` en `.mo`
- supprime `build/` et `dist/`
- regenere `build/windows_version_info.txt`
- lance `PyInstaller`
- embarque `bin\ffmpeg.exe` et `bin\ffprobe.exe` via `UniversalTranscoder.spec`
- construit l'installateur Inno Setup

## Maintenance FFmpeg

Script source :

- `scripts/update_embedded_ffmpeg.ps1`

Comportement reel du script :

- lit la version actuelle de `bin/ffmpeg.exe` et `bin/ffprobe.exe`
- n'utilise plus l'endpoint GitHub `releases/latest`
- lit la liste des releases publiees de `GyanD/codexffmpeg`
- selectionne la release la plus recente contenant un asset `ffmpeg-.*-essentials_build.zip`
- compare les binaires embarques avec la release distante
- supporte `-CheckOnly`
- telecharge et extrait seulement si une mise a jour est necessaire
- remplace `bin/ffmpeg.exe` et `bin/ffprobe.exe` seulement si necessaire
- conserve une sauvegarde locale temporaire et restaure en cas d'echec pendant le remplacement

Invariant critique :

- mettre a jour `bin/` ne met **pas** a jour `dist/`
- apres chaque update FFmpeg, il faut relancer un build complet si on veut republier l'application avec ces nouveaux binaires

Commandes de verification minimales apres update FFmpeg :

```powershell
.\bin\ffmpeg.exe -version | Select-Object -First 1
.\bin\ffprobe.exe -version | Select-Object -First 1
```

Commande de controle sans modification :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_embedded_ffmpeg.ps1 -CheckOnly
```

Commande de mise a jour effective :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_embedded_ffmpeg.ps1
```

## Workflow build Windows

Script central :

- `scripts/build_release.ps1`

Commande operatoire :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
```

Ce script :

- compile les traductions
- nettoie `build/` et `dist/`
- regenere la ressource Windows de version
- lance `PyInstaller` avec `UniversalTranscoder.spec`
- construit `dist\AccessibleMediaConverter\AccessibleMediaConverter.exe`
- construit `dist\AccessibleMediaConverter-Setup.exe`

Points critiques :

- `UniversalTranscoder.spec` embarque explicitement `bin\ffmpeg.exe` et `bin\ffprobe.exe`
- si `bin/` change et que le build n'est pas relance, le `dist/` peut rester obsolete
- ne pas supposer que le `dist/` present sur disque correspond a `bin/` sans verification explicite

Sorties attendues apres succes :

- `dist\AccessibleMediaConverter\AccessibleMediaConverter.exe`
- `dist\AccessibleMediaConverter\_internal\bin\ffmpeg.exe`
- `dist\AccessibleMediaConverter\_internal\bin\ffprobe.exe`
- `dist\AccessibleMediaConverter-Setup.exe`

## Workflow release GitHub

Procedure de maintenance release type `1.7.1` :

1. Verifier `git status`.
2. Confirmer la version de `bin/ffmpeg.exe` et `bin/ffprobe.exe`.
3. Bump version dans `core/app_info.py`.
4. Garder coherent `installer/UniversalTranscoder.iss` sur la valeur par defaut `AppVersion`.
5. Creer le fichier de notes dans `release-notes/`.
6. Executer `scripts/build_release.ps1`.
7. Verifier que `dist\AccessibleMediaConverter\_internal\bin\ffmpeg.exe` embarque bien la version voulue.
8. Verifier que `dist\AccessibleMediaConverter-Setup.exe` existe.
9. Tant que `1.8.0` n'a pas supprime la compatibilite legacy, dupliquer l'installateur canonique en `AccessibleMediaConverter-Setup-<version>.exe`.
10. Commit.
11. Push.
12. Publier la release GitHub.

Commandes operatoires de reference :

Duplication de l'asset versionne avant `1.8.0` :

```powershell
Copy-Item .\dist\AccessibleMediaConverter-Setup.exe .\dist\AccessibleMediaConverter-Setup-X.Y.Z.exe -Force
```

Publication GitHub :

```powershell
gh release create vX.Y.Z .\dist\AccessibleMediaConverter-Setup.exe .\dist\AccessibleMediaConverter-Setup-X.Y.Z.exe --title "vX.Y.Z" --notes-file .\release-notes\vX.Y.Z.md
```

Comportement attendu avant `1.8.0` :

- publier les deux assets setup
- l'updater actuel choisit d'abord `AccessibleMediaConverter-Setup.exe`
- l'updater garde encore un fallback vers `AccessibleMediaConverter-Setup-<version>.exe`
- cette compatibilite legacy est volontaire en `1.7.1` et n'a pas encore ete retiree dans `core/updater.py`

## Verification post-build / post-release

Validation obligatoire apres build local :

- `dist\AccessibleMediaConverter\AccessibleMediaConverter.exe` existe
- `dist\AccessibleMediaConverter-Setup.exe` existe
- `dist\AccessibleMediaConverter\_internal\bin\ffmpeg.exe` correspond a `bin\ffmpeg.exe`
- `dist\AccessibleMediaConverter\_internal\bin\ffprobe.exe` correspond a `bin\ffprobe.exe`
- l'application peut se lancer au moins en smoke check

Commandes minimales de verification post-build :

```powershell
.\dist\AccessibleMediaConverter\_internal\bin\ffmpeg.exe -version | Select-Object -First 1
.\dist\AccessibleMediaConverter\_internal\bin\ffprobe.exe -version | Select-Object -First 1
.\dist\AccessibleMediaConverter\AccessibleMediaConverter.exe
```

Validation obligatoire apres release GitHub :

- `gh release view vX.Y.Z` retourne la release attendue
- la release n'est ni `draft` ni `prerelease`
- les assets attendus sont presents
- l'asset canonique est bien `AccessibleMediaConverter-Setup.exe`
- les notes de release sont presentes
- le module updater applicatif resout la nouvelle release

Commande de verification GitHub :

```powershell
gh release view vX.Y.Z --json tagName,name,isDraft,isPrerelease,publishedAt,assets,url
```

Smoke check updater deja valide en `1.7.1` :

```powershell
@'
from core.updater import fetch_latest_release
r = fetch_latest_release()
print(r.version)
print(r.asset_name)
print(r.published_at)
print(r.html_url)
print(r.body)
'@ | .\.venv\Scripts\python.exe -
```

Verifier a minima :

- `version`
- `asset_name`
- `published_at`
- `html_url`
- contenu des notes

## Pieges confirmes

- `.gitignore` liste `bin/ffmpeg.exe` et `bin/ffprobe.exe`, mais ces fichiers restent trackes
- GitHub avertit sur leur taille au push
- le push passe encore, mais ce n'est pas une strategie long terme
- le `dist/` peut etre obsolete meme si `bin/` est a jour
- `releases/latest` de `GyanD/codexffmpeg` ne renvoie pas forcement la build FFmpeg la plus recente
- le script FFmpeg doit donc lire la liste des releases publiees
- le contexte ne doit pas annoncer "depot propre" sans verification terminale immediate
- le contexte ne doit pas deriver en manuel complet du code, mais il doit couvrir les workflows de reprise necessaires

## Chantier actif et prochaine version

- Le chantier `1.7.1` est termine.
- Il n'y a pas de feature en cours a reprendre automatiquement sans nouvelle consigne utilisateur.
- La prochaine etape produit deja cadree est `v1.8.0`, documentee dans `docs/plans/v1.8-updater-release-notes.md`.

Points figes pour `1.8.0` :

- suppression du fallback updater vers `AccessibleMediaConverter-Setup-<version>.exe`
- asset unique `AccessibleMediaConverter-Setup.exe`
- release notes GitHub bilingues dans un seul `body`
- extraction des notes par langue
- correction i18n de la fenetre support

Rappel important :

- `1.7.1` a volontairement garde la compatibilite des assets versionnes
- cette compatibilite n'a pas encore ete retiree de `core/updater.py`

## Convention de handoff

- Fichier canonique de reprise : `docs/codex-context.md`
- Format attendu : Markdown simple, lisible par humain et agent
- Mise a jour : manuelle, a chaque etape importante ou changement de direction produit
- Ne pas creer plusieurs fichiers concurrents pour le meme role de contexte
- Toujours preferer l'etat disque reel aux souvenirs du chat precedent

## Procedure de reprise

Si un fil plante ou si une nouvelle conversation reprend le travail :

1. Relire ce fichier en premier.
2. Verifier `git status`.
3. Identifier les fichiers modifies et non commites.
4. Reprendre depuis l'etat disque reel plutot que supposer la memoire du chat precedent.
5. Si le sujet touche a FFmpeg, verifier a la fois `bin/` et `dist/`.
6. Si le sujet touche a une release Windows, relire `scripts/build_release.ps1`, `scripts/update_embedded_ffmpeg.ps1` et `core/updater.py`.
7. Si `docs/plans/` contient un plan valide pour la prochaine version, le relire avant de reprendre.
8. Refaire les validations post-build ou post-release au lieu de supposer qu'elles ont deja ete faites.
9. Mettre a jour ce fichier des qu'une decision importante change.

## Derniere mise a jour

- Date : `2026-03-11`
- Sujet actif : etat stable apres publication de `v1.7.1`, avec plan `v1.8.0` toujours fige pour updater + release notes
- Prochaine etape attendue : attendre la prochaine consigne produit ; pour `1.8.0`, appliquer le plan updater / release notes, retirer le fallback asset versionne et corriger l'i18n de la fenetre support
