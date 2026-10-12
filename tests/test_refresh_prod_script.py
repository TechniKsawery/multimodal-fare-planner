"""Statyczne testy bezpieczenstwa scripts/refresh_prod.ps1 (skrypt nie jest uruchamiany)."""
import re
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parent.parent / "scripts" / "refresh_prod.ps1").read_text(encoding="utf-8")
# komentarze i teksty wypisywane (Write-Host "...") nie sa wykonywanym kodem
CODE = re.sub(r"<#.*?#>", "", SCRIPT, flags=re.S)
CODE = re.sub(r'Write-Host\s+"[^"\n]*"', "", "\n".join(l for l in CODE.splitlines() if not l.lstrip().startswith("#")))


def test_no_destructive_docker_commands():
    assert not re.search(r"volume\W+(rm|prune)|system\W+prune|image\W+prune", CODE)


def test_seed_option_exists_and_mounts_prod_readonly():
    assert "[switch]$SeedFromProd" in SCRIPT
    assert '"${prodVolume}:/src:ro"' in SCRIPT


def test_prod_volume_never_mounted_writable():
    for m in re.finditer(r'"\$\{prodVolume\}:[^"]*"', SCRIPT):
        assert m.group(0).endswith(':ro"')


def test_seed_copy_happens_before_import():
    assert SCRIPT.index("cp -a /src/. /dst/") < SCRIPT.index('"import", "-d"')


def test_seed_pulls_alpine_before_copy_with_clear_error():
    assert '@("pull", "alpine:3")' in SCRIPT
    assert SCRIPT.index('@("pull", "alpine:3")') < SCRIPT.index("cp -a /src/. /dst/")
    assert "docker pull alpine:3" in SCRIPT  # komunikat dla czlowieka


def test_run_ignores_native_stderr_when_exit_code_zero():
    body = SCRIPT[SCRIPT.index("function Run {"):SCRIPT.index("function TryRun")]
    assert '$ErrorActionPreference = "Continue"' in body
    assert "$code -ne 0" in body


def test_switchonly_validates_and_skips_import():
    assert "[switch]$SwitchOnly" in SCRIPT and "[string]$Volume" in SCRIPT
    # walidacja nazwy, istnienia i ze to nie obecny prod
    assert "^mw_motis_refresh_" in SCRIPT
    assert "-eq $prodVolume" in SCRIPT
    # import i pobranie siedza w gałęzi else (omijane przez -SwitchOnly)
    assert SCRIPT.index("if ($SwitchOnly) {\n        Step \"1-2") < SCRIPT.index("else {\n    Step \"1.")
    assert SCRIPT.index("else {\n    Step \"1.") < SCRIPT.index('"import", "-d"') < SCRIPT.index('Step "3.')


def test_switchonly_blocks_when_inputs_newer_than_volume():
    assert "CreatedAt" in SCRIPT
    assert "LastWriteTimeUtc -gt $created" in SCRIPT
    assert "ZABLOKOWANE" in SCRIPT


def test_switchonly_rejects_conflicting_flags():
    assert "-SwitchOnly i -NoSwitch" in SCRIPT
