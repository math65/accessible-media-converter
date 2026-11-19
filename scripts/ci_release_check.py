"""Controle prealable d'une publication, lance par .github/workflows/release.yml.

    python scripts/ci_release_check.py VERSION [--publish]

Toujours (essai a blanc compris) : la version demandee doit etre celle que le code
porte deja -- APP_VERSION et APP_VERSION_WIN dans core/app_info.py, AppVersion dans
installer/UniversalTranscoder.iss -- et l'installeur doit garder le nom exact que
l'updater accepte. Sinon on construirait un installeur dont le nom d'artefact ment.

Avec --publish : le tag vVERSION doit etre libre (ni tag ni release, brouillon
compris) et les notes release-notes/vVERSION.en.md et .fr.md presentes et non
vides. Sans --publish, ces deux points ne sont que des avertissements.

Ne lit que du texte (aucun import de core/) : rien de l'application n'est execute.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_INFO = ROOT / "core" / "app_info.py"
ISS = ROOT / "installer" / "UniversalTranscoder.iss"
NOTES_DIR = ROOT / "release-notes"
EXPECTED_INSTALLER = "AccessibleMediaConverter-Setup.exe"
VERSION_RE = re.compile(r"^(\d+\.\d+\.\d+)(?:-(?:rc|beta)\d+)?$")


def read_assignment(text: str, name: str) -> str | None:
    match = re.search(rf'^{name}\s*=\s*(?:f)?"([^"]*)"', text, re.MULTILINE)
    return match.group(1) if match else None


def remote_tag_exists(tag: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"],
        capture_output=True, text=True, check=True, cwd=ROOT,
    )
    return bool(result.stdout.strip())


def release_exists(tag: str) -> bool:
    # gh release list montre aussi les brouillons au jeton du depot.
    result = subprocess.run(
        ["gh", "release", "list", "--limit", "1000", "--json", "tagName"],
        capture_output=True, text=True, check=True, cwd=ROOT,
    )
    return any(item.get("tagName") == tag for item in json.loads(result.stdout or "[]"))


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    publish = "--publish" in argv
    if len(args) != 1:
        print(__doc__)
        return 2

    version = args[0]
    match = VERSION_RE.match(version)
    if not match:
        print(f"::error::Version invalide : '{version}' (attendu : 1.20.7 ou 1.21.0-rc1)")
        return 1
    numeric = match.group(1)

    errors: list[str] = []
    warnings: list[str] = []

    app_info = APP_INFO.read_text(encoding="utf-8")
    app_version = read_assignment(app_info, "APP_VERSION")
    app_version_win = read_assignment(app_info, "APP_VERSION_WIN")
    installer_base = read_assignment(app_info, "APP_INSTALLER_BASENAME")
    if app_version != version:
        errors.append(f"core/app_info.py : APP_VERSION = {app_version!r}, attendu {version!r}.")
    if app_version_win != f"{numeric}.0":
        errors.append(
            f"core/app_info.py : APP_VERSION_WIN = {app_version_win!r}, attendu {numeric + '.0'!r} "
            "(purement numerique, meme pour une rc)."
        )
    if f"{installer_base}.exe" != EXPECTED_INSTALLER:
        errors.append(
            f"core/app_info.py : l'installeur s'appellerait {installer_base}.exe ; "
            f"l'updater n'accepte que {EXPECTED_INSTALLER}."
        )

    iss_match = re.search(r'^\s*#define\s+AppVersion\s+"([^"]*)"', ISS.read_text(encoding="utf-8-sig"), re.MULTILINE)
    iss_version = iss_match.group(1) if iss_match else None
    if iss_version != version:
        errors.append(f"installer/UniversalTranscoder.iss : AppVersion = {iss_version!r}, attendu {version!r}.")

    publish_problems: list[str] = []
    tag = f"v{version}"
    if remote_tag_exists(tag):
        publish_problems.append(f"le tag {tag} existe deja sur origin.")
    if release_exists(tag):
        publish_problems.append(f"une release {tag} existe deja (brouillon compris).")
    for lang in ("en", "fr"):
        notes = NOTES_DIR / f"{tag}.{lang}.md"
        if not notes.is_file() or not notes.read_text(encoding="utf-8-sig").strip():
            publish_problems.append(f"notes de version manquantes ou vides : release-notes/{notes.name}.")
    (errors if publish else warnings).extend(publish_problems)

    for message in warnings:
        print(f"::warning::{message}")
    for message in errors:
        print(f"::error::{message}")
    if errors:
        return 1
    print(f"Controle prealable OK pour {tag} (publication : {'oui' if publish else 'non, essai a blanc'}).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
