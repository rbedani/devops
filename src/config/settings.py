"""Configuration loader for the devops framework."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from dataclasses import dataclass, field


CONFIG_DIR = Path(__file__).parent
PROJECT_ROOT = CONFIG_DIR.parent.parent
VAULT_FILE = PROJECT_ROOT / ".secrets.yml"


@dataclass
class ScraperConfig:
    """Runtime configuration for scrapers."""

    headless: bool = True
    timeout_ms: int = 30_000
    max_results: int = 25
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
    db_path: str = "jobs.db"


def load_vault_secret(vault_file: Path | str = VAULT_FILE, key: str = "") -> str:
    """Read a secret from an ansible-vault encrypted YAML file.

    Requires ANSIBLE_VAULT_PASSWORD or vault_password.txt to be set.
    """
    vault_path = Path(vault_file)
    if not vault_path.exists():
        raise FileNotFoundError(f"Vault file not found: {vault_path}")

    try:
        result = subprocess.run(
            ["ansible-vault", "view", "--vault-password-file", "vault_password.txt", str(vault_path)],
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
        raise RuntimeError("ansible-vault not installed. Install with: pip install ansible-vault")


def load_config(config_path: Path | str | None = None) -> AppConfig:
    """Load config from a JSON file, falling back to defaults."""
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            data = json.load(f)
        return AppConfig(
            scraper=ScraperConfig(**data.get("scraper", {})),
            telegram=TelegramConfig(**data.get("telegram", {})),
            db_path=data.get("db_path", "jobs.db"),
        )
    return AppConfig()
