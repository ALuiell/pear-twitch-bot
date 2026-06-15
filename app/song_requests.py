import re
import time
import urllib.parse
from dataclasses import dataclass
import httpx

from PySide6.QtCore import QObject, Signal, Slot

from app.config import AppConfig
from app.twitch_irc import ChatMessage

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


class _TemplateValues(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@dataclass
class ViewerQueueEntry:
    entry_id: str
    user_login: str
    video_id: str
    label: str
    requested_at: float
    artist: str = ""
    title: str = ""


class SongRequestService(QObject):
    request_pear_add = Signal(str, str, str) # request_id, video_id, insert_position
    request_pear_search = Signal(str, str) # request_id, query
    request_pear_queue = Signal(str) # user_login
    request_pear_current = Signal(str) # user_login
    request_pear_resync = Signal()
    request_pear_skip = Signal(str) # user_login
    request_pear_remove = Signal(str, int) # user_login, index
    request_pear_remove_index = Signal(str, int) # request_id, pear_index
    request_pear_move_index = Signal(str, int, int) # request_id, pear_index, to_index

    send_chat_message = Signal(str)
    log_message = Signal(str, str)

    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.global_last_success: float = 0
        self.user_last_success: dict[str, float] = {}
        self.pending_searches: dict[str, tuple[str, str]] = {}
        self.viewer_queue: list[ViewerQueueEntry] = []
        self.last_queue_data: dict | None = None
        self.current_song_video_id: str | None = None
        self.pending_dispatch_request_id: str | None = None
        self.prepared_video_id: str | None = None
        self.resync_in_progress = False

    @Slot(object)
    def handle_chat_message(self, msg: ChatMessage):
        cfg = self.config.song_requests
        if not cfg.enabled:
            return

        text = msg.text.strip()
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        user_login = msg.login

        is_mod_or_vip = msg.is_mod or msg.is_vip or "broadcaster" in msg.badges

        if command == self._command(cfg.commands.queue):
            if cfg.enable_queue_cmd:
                self._send_viewer_queue(user_login)
            return
        if command == self._command(cfg.commands.current):
            if cfg.enable_current_cmd:
                self.request_pear_current.emit(user_login)
            return
        if command == self._command(cfg.commands.skip):
            if cfg.enable_skip_cmd and is_mod_or_vip:
                self.request_pear_skip.emit(user_login)
            return
        if command == self._command(cfg.commands.remove):
            if cfg.enable_remove_cmd and is_mod_or_vip:
                try:
                    self._remove_viewer_queue_entry(user_login, int(args.strip()))
                except ValueError:
                    self._respond("remove_usage", user=user_login, remove_command=self._display_command(cfg.commands.remove))
            return

        if command != self._command(cfg.commands.song) or not args:
            return

        if cfg.access_tier == "subs_only" and not (msg.is_subscriber or is_mod_or_vip):
            return
        if cfg.access_tier == "vip_mod" and not is_mod_or_vip:
            return
        if cfg.access_tier == "mods_only" and not msg.is_mod:
            return

        now = time.monotonic()
        if now - self.global_last_success < cfg.global_cooldown_seconds:
            self.log_message.emit("debug", f"Global cooldown blocked {user_login}")
            return

        last_user = self.user_last_success.get(user_login, 0)
        if now - last_user < cfg.user_cooldown_seconds:
            self._respond("cooldown", user=user_login)
            return

        try:
            video_id = self._extract_video_id(args)
        except ValueError as exc:
            if self._user_has_reached_limit(user_login):
                self._send_limit_message(user_login)
                return
            if self._looks_like_url(args):
                self._respond("invalid_source", user=user_login)
                self.log_message.emit("debug", f"Rejected invalid URL from {user_login}: {exc}")
                return
            request_id = f"search_{user_login}_{time.time()}"
            self.pending_searches[request_id] = (user_login, args)
            self.log_message.emit("info", f"Searching song: {args} by {user_login}")
            self.request_pear_search.emit(request_id, args)
            return

        artist, title = self._resolve_youtube_metadata(value=args, video_id=video_id)
        self._queue_viewer_track(user_login, video_id, args, artist=artist, title=title)

    def _queue_viewer_track(self, user_login: str, video_id: str, label: str, artist: str = "", title: str = ""):
        if self.config.song_requests.reject_duplicates and self._video_id_is_known(video_id):
            self._respond("duplicate", user=user_login)
            return

        if self._user_has_reached_limit(user_login):
            self._send_limit_message(user_login)
            return

        entry = ViewerQueueEntry(
            entry_id=f"viewer_{user_login}_{time.time()}",
            user_login=user_login,
            video_id=video_id,
            label=label.strip(),
            artist=artist.strip(),
            title=title.strip(),
            requested_at=time.time(),
        )
        self.viewer_queue.append(entry)
        self.global_last_success = time.monotonic()
        self.user_last_success[user_login] = time.monotonic()

        position = len(self.viewer_queue)
        track_display = self._format_track_display(entry, bracketed=True)
        if position == 1:
            self._respond("added_next", user=user_login, track=track_display, position=position)
        else:
            self._respond("added_position", user=user_login, track=track_display, position=position)

        self.log_message.emit("info", f"Queued viewer track {video_id} for {user_login}")
        self._dispatch_next_viewer_track()

    @Slot(str, dict)
    def handle_pear_success(self, request_id: str, result: dict):
        if request_id == self.pending_dispatch_request_id:
            self.pending_dispatch_request_id = None
            self.prepared_video_id = result.get("videoId") or self.prepared_video_id
            self.log_message.emit("debug", f"Dispatched viewer track {result.get('videoId', '')}")
            # Wait for Pear to publish fresh queue state before dispatching again.
            return

    @Slot(str, str)
    def handle_pear_failure(self, request_id: str, error: str):
        if request_id == self.pending_dispatch_request_id:
            self.pending_dispatch_request_id = None
            self.prepared_video_id = None
            self.log_message.emit("warning", f"Failed to dispatch viewer track: {error}")

    @Slot(str, object)
    def handle_search_completed(self, request_id: str, result: object):
        pending = self.pending_searches.pop(request_id, None)
        if not pending:
            return

        user_login, label = pending
        metadata = result if isinstance(result, dict) else {}
        video_id = str(metadata.get("videoId", "")).strip()
        if not video_id:
            self._respond("search_not_found", user=user_login)
            return

        artist = str(metadata.get("artist", "")).strip()
        title = str(metadata.get("title", "")).strip()
        self._queue_viewer_track(user_login, video_id, label, artist=artist, title=title)

    @Slot(str, object)
    def handle_queue_fetched(self, user_login: str, queue_data: object):
        if isinstance(queue_data, dict):
            self.last_queue_data = queue_data
        self._send_viewer_queue(user_login)

    @Slot(str, object)
    def handle_current_song_fetched(self, user_login: str, song: object):
        if song is None:
            self._respond("pear_unavailable", user=user_login)
            return

        if not isinstance(song, dict) or not song:
            self._respond("nothing_playing", user=user_login)
            return

        title = song.get("title", "")
        artist = song.get("artist", "")
        self._respond("current", user=user_login, artist=artist, title=title)

    @Slot()
    def command_resync_with_pear(self):
        self.pending_dispatch_request_id = None
        self.prepared_video_id = None
        self.last_queue_data = None
        self.current_song_video_id = None
        self.resync_in_progress = True
        self.log_message.emit("info", "Starting re-sync with Pear.")
        self.request_pear_resync.emit()

    @Slot(object)
    def observe_queue_updated(self, queue_data: object):
        self.last_queue_data = queue_data if isinstance(queue_data, dict) else None
        if self.prepared_video_id and self._find_video_index_in_pear_queue(self.prepared_video_id) is not None:
            self.prepared_video_id = None
        if self.resync_in_progress:
            return
        self._dispatch_next_viewer_track()

    @Slot(dict)
    def observe_current_song_updated(self, song: dict):
        self.current_song_video_id = song.get("videoId") if song else None

        self._reconcile_front_with_current_song()

        if self.resync_in_progress:
            self.resync_in_progress = False
            self.log_message.emit("info", "Re-synced local queue with Pear.")
            self._dispatch_next_viewer_track()
            return
        self._dispatch_next_viewer_track()

    @Slot(str, str)
    def handle_action_completed(self, user_login: str, action: str):
        if action == "skip":
            self._respond("skip_success", user=user_login)
        elif action.startswith("remove"):
            self._respond("remove_success", user=user_login)

    @Slot(str, str, str)
    def handle_action_failed(self, user_login: str, action: str, error: str):
        if action == "skip":
            self._respond("skip_failed", user=user_login, error=error)
        elif action == "remove":
            self._respond("remove_failed", user=user_login, error=error)

    @Slot(str)
    def handle_queue_operation_completed(self, request_id: str):
        if request_id == self.pending_dispatch_request_id:
            self.pending_dispatch_request_id = None
            # Keep the prepared marker until Pear sends fresh queue state.
            # Otherwise we can re-dispatch the same move/add against stale queue data.
            return
        self._dispatch_next_viewer_track()

    @Slot(str, str)
    def handle_queue_operation_failed(self, request_id: str, error: str):
        if request_id == self.pending_dispatch_request_id:
            self.pending_dispatch_request_id = None
            self.prepared_video_id = None
            self.log_message.emit("warning", f"Queue operation failed: {error}")

    @Slot()
    def clear_local_queue(self):
        self.viewer_queue.clear()
        self.pending_searches.clear()
        self.pending_dispatch_request_id = None
        self.prepared_video_id = None
        self.resync_in_progress = False
        self.last_queue_data = None
        self.current_song_video_id = None
        self.log_message.emit("info", "Viewer queue cleared from the dashboard.")

    def _dispatch_next_viewer_track(self):
        if not self.viewer_queue or self.pending_dispatch_request_id:
            return

        front = self.viewer_queue[0]
        if self.current_song_video_id and self.current_song_video_id == front.video_id:
            return
        if self.prepared_video_id == front.video_id:
            return

        current_index, next_video_id = self._get_current_index_and_next_video()
        if next_video_id == front.video_id:
            return

        existing_index = self._find_video_index_in_pear_queue(front.video_id)
        if existing_index is not None and current_index is not None:
            desired_index = current_index + 1
            if existing_index != desired_index:
                request_id = f"dispatch_move_{front.entry_id}"
                self.pending_dispatch_request_id = request_id
                self.prepared_video_id = front.video_id
                self.request_pear_move_index.emit(request_id, existing_index, desired_index)
            return

        insert_position = "INSERT_AFTER_CURRENT_VIDEO" if self.current_song_video_id else self.config.song_requests.insert_position
        request_id = f"dispatch_add_{front.entry_id}"
        self.pending_dispatch_request_id = request_id
        self.prepared_video_id = front.video_id
        self.request_pear_add.emit(request_id, front.video_id, insert_position)

    def _send_viewer_queue(self, user_login: str):
        if not self.viewer_queue:
            self._respond("queue_empty", user=user_login)
            return

        preview = []
        for index, entry in enumerate(self.viewer_queue[:3], start=1):
            label = self._format_queue_preview(entry)
            preview.append(f"{index}. {label}")
        self._respond("queue", user=user_login, queue=" | ".join(preview))

    def _remove_viewer_queue_entry(self, user_login: str, position: int):
        if position < 1 or position > len(self.viewer_queue):
            self._respond("remove_invalid_position", user=user_login, position=position)
            return

        entry = self.viewer_queue.pop(position - 1)
        self._respond("remove_item", user=user_login, position=position, track=self._format_track_display(entry))

        pear_index = self._find_video_index_in_pear_queue(entry.video_id)
        if pear_index is not None:
            self.request_pear_remove_index.emit(f"remove_local_{entry.entry_id}", pear_index)

        if position == 1:
            self.pending_dispatch_request_id = None
            if self.prepared_video_id == entry.video_id:
                self.prepared_video_id = None
            self._dispatch_next_viewer_track()

    def _user_has_reached_limit(self, user_login: str) -> bool:
        limit = self.config.song_requests.max_active_per_user
        if limit is None:
            return False
        return self._active_request_count(user_login) >= limit

    def _active_request_count(self, user_login: str) -> int:
        queue_count = sum(1 for entry in self.viewer_queue if entry.user_login == user_login)
        pending_search_count = sum(1 for pending_user, _ in self.pending_searches.values() if pending_user == user_login)
        return queue_count + pending_search_count

    def _send_limit_message(self, user_login: str):
        limit = self.config.song_requests.max_active_per_user
        if limit == 1:
            self._respond("limit_single", user=user_login, limit=limit)
        else:
            self._respond("limit_multiple", user=user_login, limit=limit or "")

    def _respond(self, template_name: str, **values):
        template = getattr(self.config.song_requests.responses, template_name)
        try:
            message = template.format_map(_TemplateValues(values)).strip()
        except (ValueError, AttributeError) as exc:
            self.log_message.emit("warning", f"Invalid response template '{template_name}': {exc}")
            message = str(template).strip()
        if message:
            self.send_chat_message.emit(message)

    def _command(self, value: str) -> str:
        return self._display_command(value).lower()

    def _display_command(self, value: str) -> str:
        command = value.strip().split(maxsplit=1)[0] if value.strip() else ""
        return command if not command or command.startswith("!") else f"!{command}"

    def _video_id_is_queued(self, video_id: str) -> bool:
        return any(entry.video_id == video_id for entry in self.viewer_queue)

    def _video_id_is_known(self, video_id: str) -> bool:
        if self._video_id_is_queued(video_id):
            return True
        if self.current_song_video_id == video_id:
            return True
        return self._find_video_index_in_pear_queue(video_id) is not None

    def _reconcile_front_with_current_song(self):
        if not self.viewer_queue or not self.current_song_video_id:
            return
        if self.viewer_queue[0].video_id != self.current_song_video_id:
            return

        started = self.viewer_queue.pop(0)
        if self.prepared_video_id == started.video_id:
            self.prepared_video_id = None
        self.log_message.emit("info", f"Viewer track started: {started.video_id} for {started.user_login}")

    def _format_track_display(self, entry: ViewerQueueEntry, bracketed: bool = False) -> str:
        if entry.artist and entry.title:
            display = f"{entry.artist} - {entry.title}"
        elif entry.title:
            display = entry.title
        else:
            display = entry.label
        return f"[{display}]" if bracketed else display

    def _format_queue_preview(self, entry: ViewerQueueEntry) -> str:
        label = f"{entry.user_login} - {self._format_track_display(entry)}"
        if len(label) > 42:
            label = label[:39] + "..."
        return label

    def _resolve_youtube_metadata(self, value: str, video_id: str) -> tuple[str, str]:
        if not self._looks_like_url(value):
            return "", ""

        lookup_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            response = httpx.get(
                "https://www.youtube.com/oembed",
                params={"url": lookup_url, "format": "json"},
                timeout=3,
            )
            response.raise_for_status()
            data = response.json()
            return (
                str(data.get("author_name", "")).strip(),
                str(data.get("title", "")).strip(),
            )
        except Exception as exc:
            self.log_message.emit("debug", f"Failed to resolve YouTube metadata for {video_id}: {exc}")
            return "", ""

    def _get_current_index_and_next_video(self) -> tuple[int | None, str | None]:
        items = self.last_queue_data.get("items", []) if isinstance(self.last_queue_data, dict) else []
        current_index = None
        for index, item in enumerate(items):
            renderer = self._extract_queue_renderer(item)
            if renderer.get("selected") is True:
                current_index = index
                break

        if current_index is None:
            return None, None

        next_index = current_index + 1
        if next_index >= len(items):
            return current_index, None

        next_renderer = self._extract_queue_renderer(items[next_index])
        return current_index, next_renderer.get("videoId")

    def _find_video_index_in_pear_queue(self, video_id: str) -> int | None:
        items = self.last_queue_data.get("items", []) if isinstance(self.last_queue_data, dict) else []
        for index, item in enumerate(items):
            renderer = self._extract_queue_renderer(item)
            if renderer.get("videoId") == video_id:
                return index
        return None

    def _looks_like_url(self, value: str) -> bool:
        parsed = urllib.parse.urlparse(value.strip())
        return bool(parsed.scheme and parsed.netloc)

    def _extract_queue_renderer(self, item: object) -> dict:
        if not isinstance(item, dict):
            return {}
        return (
            item.get("playlistPanelVideoRenderer")
            or item.get("playlistPanelVideoWrapperRenderer", {}).get("primaryRenderer", {}).get("playlistPanelVideoRenderer")
            or {}
        )

    def _extract_video_id(self, value: str) -> str:
        url = urllib.parse.urlparse(value.strip())
        host = url.hostname.lower() if url.hostname else ""

        if host not in ALLOWED_HOSTS:
            if VIDEO_ID_RE.fullmatch(value.strip()):
                return value.strip()
            raise ValueError("Only YouTube links are allowed")

        if host in {"youtu.be", "www.youtu.be"}:
            video_id = url.path.strip("/").split("/")[0]
        else:
            video_id = urllib.parse.parse_qs(url.query).get("v", [""])[0]

        if not VIDEO_ID_RE.fullmatch(video_id):
            raise ValueError("Invalid YouTube videoId")

        return video_id
