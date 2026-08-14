"""Vérifie que toute l'interface se construit — sans afficher une seule fenêtre.

Deux régressions surveillées :
  * un dialogue qui ne s'ouvre plus (API wxPython retirée lors d'une montée de version) ;
  * les avertissements de hiérarchie de wxWidgets 3.3 sur les `wxStaticBoxSizer`
    (« should be created as child of its wxStaticBox »). Ils signalent des
    contrôles qui ne sont pas rattachés à leur cadre : le lecteur d'écran perd
    alors le nom du groupe et l'ordre de tabulation peut sauter.

Le test tourne en sous-processus parce que wxWidgets écrit ces avertissements sur
la sortie d'erreur native, hors de portée d'une capture Python classique.
"""

import os
import subprocess
import sys
import unittest

from tests.helpers import REPO_ROOT

STATIC_BOX_WARNING = "should be created as child of its wxStaticBox"


def wx_available():
    try:
        import wx  # noqa: F401
    except Exception:
        return False
    return True


@unittest.skipUnless(wx_available(), "wxPython indisponible")
class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = subprocess.run(
            [sys.executable, "-m", "tests.ui_smoke_child"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    def test_every_dialog_builds(self):
        self.assertEqual(
            self.result.returncode, 0,
            f"le smoke test UI a échoué :\n{self.result.stdout}\n{self.result.stderr}",
        )
        self.assertIn("ECHECS: 0", self.result.stdout, self.result.stdout)

    def test_no_static_box_hierarchy_warning(self):
        offending = [
            line for line in self.result.stderr.splitlines() if STATIC_BOX_WARNING in line
        ]
        self.assertEqual(offending, [], "\n".join(offending))


if __name__ == "__main__":
    unittest.main()
