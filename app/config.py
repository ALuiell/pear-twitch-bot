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
class CommandNamesConfig:
    song: str = "!song"
    queue: str = "!queue"
    current: str = "!current"
    skip: str = "!skip"
    remove: str = "!remove"

@dataclass
class ResponseTemplatesConfig:
    remove_usage: str = "@{user}, usage: {remove_command} <number>"
    cooldown: str = "@{user}, please wait before requesting another song."
    limit_single: str = "@{user}, you already have a pending request."
    limit_multiple: str = "@{user}, you already reached the active request limit."
    invalid_source: str = "@{user}, only YouTube links or plain text search queries are allowed."
    duplicate: str = "@{user}, this track is already queued or playing."
    added_next: str = "@{user}, added {track} to the viewer queue. You're up next."
    added_position: str = "@{user}, added {track} to the viewer queue at position {position}."
    search_not_found: str = "@{user}, could not find any track for your search."
    pear_unavailable: str = "@{user}, Pear Desktop is currently unavailable."
    nothing_playing: str = "@{user}, nothing is currently playing."
    current: str = "@{user}, currently playing: {artist} - {title}"
    skip_success: str = "@{user}, track skipped!"
    remove_success: str = "@{user}, track removed from queue!"
    skip_failed: str = "@{user}, failed to skip the track: {error}"
    remove_failed: str = "@{user}, failed to remove the track: {error}"
    queue_empty: str = "@{user}, the viewer queue is currently empty."
    queue: str = "@{user}, viewer queue: {queue}"
    remove_invalid_position: str = "@{user}, there is no viewer queue item at position {position}."
    remove_item: str = "@{user}, removed viewer queue item {position}: {track}"

@dataclass
class SongRequestsConfig:
    enabled: bool = True
    commands: CommandNamesConfig = field(default_factory=CommandNamesConfig)
    responses: ResponseTemplatesConfig = field(default_factory=ResponseTemplatesConfig)
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
        song_data = dict(data.get("song_requests", {}))
        command_data = dict(song_data.pop("commands", {}))
        legacy_song_command = song_data.pop("command", None)
        if legacy_song_command and "song" not in command_data:
            command_data["song"] = legacy_song_command
        response_data = dict(song_data.pop("responses", {}))
        song_data["commands"] = CommandNamesConfig(**command_data)
        song_data["responses"] = ResponseTemplatesConfig(**response_data)
        return cls(
            version=data.get("version", 1),
            twitch=TwitchConfig(**data.get("twitch", {})),
            pear=PearConfig(**data.get("pear", {})),
            song_requests=SongRequestsConfig(**song_data),
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
