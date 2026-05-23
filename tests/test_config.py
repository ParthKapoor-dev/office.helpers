from __future__ import annotations

import tools.pdf_numbering.config as config
from tools.pdf_numbering.config import (
    DEFAULTS,
    load_config,
    save_config,
    settings_from_config,
)


def test_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path / "cfg")
    assert load_config() == DEFAULTS


def test_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path / "cfg")
    save_config(
        {
            "folder": "C:/Users/x/Desktop/pdfs",
            "position": "top-right",
            "font_size": 14,
            "margin_pt": 10,
            "make_backup": False,
            "watch_enabled": True,
        }
    )
    cfg = load_config()
    assert cfg["folder"] == "C:/Users/x/Desktop/pdfs"
    assert cfg["position"] == "top-right"
    assert cfg["watch_enabled"] is True
    assert cfg["make_backup"] is False


def test_corrupt_config_falls_back(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    (cfg_dir / "config.json").write_text("not json {", encoding="utf-8")
    monkeypatch.setattr(config, "config_dir", lambda: cfg_dir)
    assert load_config() == DEFAULTS


def test_settings_from_config():
    settings = settings_from_config(
        {"position": "bottom-left", "font_size": 12, "margin_pt": 20, "make_backup": False}
    )
    assert settings.position == "bottom-left"
    assert settings.font_size == 12.0
    assert settings.margin_pt == 20.0
    assert settings.make_backup is False
