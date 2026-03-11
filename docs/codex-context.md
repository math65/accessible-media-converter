# Contexte Agent

## Identite du projet

- Produit actuel : `Accessible Media Converter`
- Nature : application desktop Windows de transcodage media basee sur `wxPython` et `FFmpeg`
- Version repere : `1.7.0`
- Positionnement : accessibilite forte, usage clavier, conversion media reelle pour utilisateurs NVDA et grand public Windows
- Usage principal de ce fichier : memoire de reprise pour agents IA, tout en restant lisible humainement

## Priorites et invariants

- La cible produit actuelle est **Windows uniquement**.
- L'ordre de priorite produit est : **accessibilite > simplicite > controle avance**.
- La compatibilite lecteurs d'ecran et les parcours clavier priment sur l'ajout de complexite.
- La simplicite d'usage passe avant l'exposition brute de reglages experts.
- Les options avancees restent permises, mais seulement apres clarte et accessibilite.
- La documentation locale embarquee doit rester **strictement orientee utilisateur**.
- Ne pas deriver ce fichier vers une documentation technique detaillee ni dupliquer la `README`.

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
- La release publique actuelle est `v1.7.0`.
- Le depot doit etre verifie avec `git status` avant toute reprise ou release ; ne pas supposer l'etat de `origin/master`.

## Chantier actif

Le chantier actif a la date de cette mise a jour est **termine pour la release 1.7.0**. Il n'y a pas de feature en cours a reprendre automatiquement sans nouvelle consigne utilisateur.

Direction validee :

- integration de la documentation locale via le menu Aide
- packaging de `docs/` dans la build Windows
- pages FR et EN utilisateur presentes dans le depot
- ajout d'une preference de langue utilisateur avec `auto`, `fr`, `en`
- documentation locale FR et EN, avec fallback vers `en` puis `fr`
- **pas de contenu technique** dans la documentation locale embarquee
- alignement doc / produit avec suppression de la promesse UI de drag and drop non implemente
- publication de `v1.7.0` sur GitHub avec notes de release et setup Windows

Etat local connu au moment de cette mise a jour :

- depot local propre apres commit et push
- arret utilisateur d'un batch : demande de suppression des fichiers partiellement generes sur les sorties interrompues
- noyau i18n extensible pour futures langues via `gettext`
- script de maintenance `scripts/manage_i18n.py` et catalogue source `locales/base.pot`
- module `core/documentation.py` pour la doc locale par langue
- verification de release ajustee dans `scripts/build_release.ps1`
- release `v1.7.0` publiee avec deux assets setup :
- `AccessibleMediaConverter-Setup.exe` = nom canonique actuel
- `AccessibleMediaConverter-Setup-1.7.0.exe` = compatibilite temporaire pour l'updater des versions precedentes
- intention produit connue : en `1.8.0`, retirer l'ancien asset versionne si la compatibilite legacy n'est plus necessaire

## Convention de handoff

- Fichier canonique de reprise : `docs/codex-context.md`
- Format attendu : Markdown simple, court, lisible par humain et agent
- Mise a jour : manuelle, a chaque etape importante ou changement de direction produit
- Ne pas creer plusieurs fichiers concurrents pour le meme role de contexte

## Procedure de reprise

Si un fil plante ou si une nouvelle conversation reprend le travail :

1. Relire ce fichier en premier.
2. Verifier `git status`.
3. Identifier les fichiers modifies et non commites.
4. Reprendre depuis l'etat disque reel plutot que supposer la memoire du chat precedent.
5. Relire en priorite les fichiers du chantier actif.
6. Mettre a jour ce fichier des qu'une decision importante change.

## Derniere mise a jour

- Date : `2026-03-11`
- Sujet actif : etat stable apres publication de `v1.7.0`
- Prochaine etape attendue : attendre la prochaine consigne produit ; pour `1.8.0`, reevaluer la suppression du setup versionne et du fallback associe dans l'updater
