import importlib.util
import pytest


def test_cli_module_exists():
    assert importlib.util.find_spec("slotharbor.cli") is not None


def test_cli_init_and_health(tmp_path,capsys):
    from slotharbor.cli import main
    assert main(["--database",str(tmp_path/"app.sqlite"),"init"]) == 0
    assert "initialized" in capsys.readouterr().out


def test_cli_create_and_demo(tmp_path,monkeypatch,capsys):
    from slotharbor.cli import main
    db=str(tmp_path/"app.sqlite")
    monkeypatch.setattr("slotharbor.cli.getpass.getpass",lambda prompt:"test-only-cli-password")
    assert main(["--database",db,"create-user","--username","owner","--role","admin"]) == 0
    assert main(["--database",db,"demo","--actor","owner"]) == 0
    assert main(["--database",db,"demo","--actor","owner"]) == 2
    assert main(["--database",db,"reset-password","--username","owner"]) == 0
    assert main(["--database",db,"backup",str(tmp_path/"copy.sqlite")]) == 0
