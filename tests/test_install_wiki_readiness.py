from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = ROOT / "scripts" / "install-mission-control-plugin.ps1"
INSTALL_DOC = ROOT / "wiki-staging" / "Install-From-Codex.md"
HEADLESS_DOC = ROOT / "wiki-staging" / "Headless-Install-and-Autowire.md"
LIMITATIONS_DOC = ROOT / "wiki-staging" / "Known-Limitations-and-Non-Goals.md"


def test_install_wiki_matches_shipped_entrypoints() -> None:
    assert INSTALL_SCRIPT.exists()

    install_doc = INSTALL_DOC.read_text(encoding="utf-8")
    headless_doc = HEADLESS_DOC.read_text(encoding="utf-8")
    limitations_doc = LIMITATIONS_DOC.read_text(encoding="utf-8")
    install_script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "> Status: Current" in install_doc
    assert "> Status: Current" in headless_doc
    assert "ships headless install and health entrypoints" in install_doc
    assert "already ships install and health scripts" in headless_doc
    assert "some install/autowire surfaces remain planned or partial" not in limitations_doc
    assert "full readiness still depends on local Python, Codex, and runner availability" in limitations_doc

    assert ".\\scripts\\install-mission-control-plugin.ps1 -HeadlessOnly" not in headless_doc
    assert ".\\scripts\\install-mission-control-plugin.ps1 -Repair" not in headless_doc
    assert "python .\\scripts\\mission-control-manage.py install --dry-run" in headless_doc

    assert "HeadlessOnly" not in install_script
    assert "Repair" not in install_script
    assert "DryRun" in install_script
