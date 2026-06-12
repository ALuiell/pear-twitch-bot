import json
import logging
import os
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_FILE = Path("config.json")
EXAMPLE_CONFIG_FILE = Path("config.example.json")

@dataclass
class TwitchConfig:
    client_id: str = ""
    username: str = ""
    user_id: str = ""
    target_channel: str = ""
    auto_start_bot: bool = False

@dataclass
class PearConfig:
    base_url: str = "http://127.0.0.1:26538"
    request_timeout_seconds: int = 8
    auth_client_id: str = "twitch-pear-song-requests"

@dataclass
class SongRequestsConfig:
    enabled: bool = True
    command: str = "!song"
    access_tier: str = "everyone"
    global_cooldown_seconds: int = 5
    user_cooldown_seconds: int = 300
    insert_position: str = "INSERT_AT_END"
    reject_duplicates: bool = True
    max_active_per_user: int | None = 1
    enable_queue_cmd: bool = True
    enable_current_cmd: bool = True
    enable_skip_cmd: bool = True
    enable_remove_cmd: bool = True

@dataclass
class UiConfig:
    start_minimized: bool = False
    minimize_to_tray: bool = True
    log_limit: int = 500

@dataclass
class AppConfig:
    version: int = 1
    twitch: TwitchConfig = field(default_factory=TwitchConfig)
    pear: PearConfig = field(default_factory=PearConfig)
    song_requests: SongRequestsConfig = field(default_factory=SongRequestsConfig)
    ui: UiConfig = field(default_factory=UiConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        return cls(
            version=data.get("version", 1),
            twitch=TwitchConfig(**data.get("twitch", {})),
            pear=PearConfig(**data.get("pear", {})),
            song_requests=SongRequestsConfig(**data.get("song_requests", {})),
            ui=UiConfig(**data.get("ui", {}))
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def load_config() -> AppConfig:
    """Loads config.json. If it doesn't exist, copies config.example.json or creates defaults."""
    if not CONFIG_FILE.exists():
        logger.info(f"{CONFIG_FILE} not found. Creating from defaults.")
        if EXAMPLE_CONFIG_FILE.exists():
            try:
                with open(EXAMPLE_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                config = AppConfig.from_dict(data)
                save_config(config)
                return config
            except Exception as e:
                logger.error(f"Failed to load {EXAMPLE_CONFIG_FILE}: {e}")
        
        # Fallback to defaults
        config = AppConfig()
        save_config(config)
        return config

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AppConfig.from_dict(data)
    except Exception as e:
        logger.error(f"Failed to load {CONFIG_FILE}: {e}")
        return AppConfig()

def save_config(config: AppConfig) -> None:
    """Saves config.json atomically to prevent corruption."""
    data = config.to_dict()
    try:
        fd, temp_path = tempfile.mkstemp(dir=CONFIG_FILE.parent, text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, CONFIG_FILE)
        logger.debug("Configuration saved successfully.")
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")
        if 'temp_path' in locals() and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
