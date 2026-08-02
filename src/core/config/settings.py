"""Configuration loader for the devops framework.

Centralized path resolution for the entire project.
All CWD-relative paths are consolidated here, resolved from PROJECT_ROOT.
No module should use os.getcwd() or bare relative paths.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# -- Project root detection ---------------------------------------------------
# This file lives at PROJECT_ROOT/src/core/config/settings.py
HERE = Path(__file__).resolve().parent  # src/core/config/
PROJECT_ROOT = HERE.parent.parent.parent  # project root

# -- Application paths (centralized — no CWD-relative paths elsewhere) --------
DB_PATH = Path(os.environ.get("DB_PATH") or PROJECT_ROOT / "jobs.db")
DATA_DIR = PROJECT_ROOT / "data"
CV_DIR = DATA_DIR / "cv"
TARGETS_PATH = PROJECT_ROOT / "config" / "targets.json"
VAULT_FILE = PROJECT_ROOT / ".secrets.yml"


@dataclass
class ScraperConfig:
    """Runtime configuration for scrapers."""

    headless: bool = True
    timeout_ms: int = 30_000
    scroll_pause_ms: int = 1500


@dataclass
class TelegramConfig:
    """Telegram delivery configuration."""

    bot_token: str = ""
    chat_id: str = ""


@dataclass
class AppConfig:
    """Top-level application config."""

    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    db_path: str = str(DB_PATH)


def load_vault_secret(vault_file: Path | str = VAULT_FILE, key: str = "") -> str:
    """Read a secret from an ansible-vault encrypted YAML file.

    Requires ANSIBLE_VAULT_PASSWORD or vault_password.txt to be set.
    """
    vault_path = Path(vault_file)
    if not vault_path.exists():
        raise FileNotFoundError(f"Vault file not found: {vault_path}")

    try:
        result = subprocess.run(
            ["ansible-vault", "view", "--vault-password-file", "vault_password.txt", str(vault_path)],  # noqa: E501
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ansible-vault failed: {result.stderr}")

        import yaml
        data = yaml.safe_load(result.stdout)

        if key:
            return str(data.get(key, ""))
        return json.dumps(data)

    except FileNotFoundError:
        raise RuntimeError("ansible-vault not installed. Install with: pip install ansible-vault")  # noqa: B904


def load_config(config_path: Path | str | None = None) -> AppConfig:
    """Load config from a JSON file, falling back to defaults."""
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            data = json.load(f)
        return AppConfig(
            scraper=ScraperConfig(**data.get("scraper", {})),
            telegram=TelegramConfig(**data.get("telegram", {})),
            db_path=data.get("db_path", str(DB_PATH)),
        )
    return AppConfig()