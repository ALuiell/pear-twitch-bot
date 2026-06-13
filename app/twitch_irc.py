import logging
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from typing import Any
from PySide6.QtCore import QObject, Signal, Slot

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ChatMessage:
    message_id: str
    user_id: str
    login: str
    display_name: str
    channel: str
    text: str
    badges: frozenset[str]
    is_mod: bool
    is_subscriber: bool
    is_vip: bool

class TwitchIrcWorker(QObject):
    state_changed = Signal(str)      # connected, disconnected, reconnecting
    chat_message = Signal(object)    # ChatMessage
    log_message = Signal(str, str)   # level, text
    fatal_error = Signal(str)

    def __init__(self, username: str, channel: str, token: str):
        super().__init__()
        self.username = username.lower()
        self.channel = channel.lower()
        self.token = token
        self._is_running = False
        self._socket: socket.socket | None = None
        self._send_queue: list[str] = []
        self._lock = threading.Lock()

    @Slot()
    def start_connection(self):
        self._is_running = True
        self._connect_and_loop()

    def _connect_and_loop(self):
        while self._is_running:
            self.state_changed.emit("connecting")
            try:
                context = ssl.create_default_context()
                raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                raw_socket.settimeout(10.0)
                self._socket = context.wrap_socket(raw_socket, server_hostname="irc.chat.twitch.tv")
                self._socket.connect(("irc.chat.twitch.tv", 6697))
                self._socket.settimeout(1.0) # non-blocking reads loop

                self._send(f"PASS oauth:{self.token}")
                self._send(f"NICK {self.username}")
                self._send("CAP REQ :twitch.tv/tags twitch.tv/commands")
                self._send(f"JOIN #{self.channel}")

                self.state_changed.emit("connected")
                self._read_loop()

            except Exception as e:
                logger.error(f"IRC connection error: {e}")
                self.log_message.emit("error", f"Connection error: {e}")
            finally:
                self._close_socket()

            if self._is_running:
                self.state_changed.emit("reconnecting")
                self.log_message.emit("info", "Reconnecting in 5 seconds...")
                time.sleep(5)

    def _read_loop(self):
        buffer = ""
        while self._is_running and self._socket:
            # Flush send queue
            with self._lock:
                to_send = list(self._send_queue)
                self._send_queue.clear()
            for msg in to_send:
                self._send(msg)

            try:
                data = self._socket.recv(4096)
                if not data:
                    break # Connection closed
                buffer += data.decode("utf-8", errors="replace")
                
                while "\r\n" in buffer:
                    line, buffer = buffer.split("\r\n", 1)
                    self._handle_line(line)
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error reading from socket: {e}")
                break

    def _handle_line(self, line: str):
        if line.startswith("PING"):
            self._send(line.replace("PING", "PONG", 1))
            return

        # Simple parsing for PRIVMSG
        if " PRIVMSG " in line:
            try:
                self._parse_privmsg(line)
            except Exception as e:
                logger.error(f"Failed to parse PRIVMSG: {e}")

    def _parse_privmsg(self, line: str):
        # Format: @tags :prefix PRIVMSG #channel :text
        tags_str = ""
        prefix_str = ""
        
        if line.startswith("@"):
            parts = line.split(" :", 1)
            tags_str = parts[0][1:]
            line = ":" + parts[1]
            
        parts = line.split(" ", 3)
        prefix_str = parts[0][1:] # remove :
        command = parts[1]
        channel = parts[2][1:] # remove #
        text = parts[3][1:] if len(parts) > 3 and parts[3].startswith(":") else ""

        login = prefix_str.split("!")[0]
        
        # Parse tags
        tags = {}
        for tag in tags_str.split(";"):
            if "=" in tag:
                k, v = tag.split("=", 1)
                tags[k] = v
                
        badges_str = tags.get("badges", "")
        badges = frozenset([b.split("/")[0] for b in badges_str.split(",") if b])
        
        msg = ChatMessage(
            message_id=tags.get("id", ""),
            user_id=tags.get("user-id", ""),
            login=login,
            display_name=tags.get("display-name", login),
            channel=channel,
            text=text.strip(),
            badges=badges,
            is_mod="moderator" in badges or tags.get("mod") == "1" or "broadcaster" in badges,
            is_subscriber="subscriber" in badges or "founder" in badges,
            is_vip="vip" in badges
        )
        self.chat_message.emit(msg)

    def _send(self, message: str):
        if not self._socket: return
        try:
            self._socket.sendall((message + "\r\n").encode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    @Slot(str)
    def send_privmsg(self, text: str):
        # Remove newlines
        text = text.replace("\r", " ").replace("\n", " ")
        msg = f"PRIVMSG #{self.channel} :{text}"
        with self._lock:
            self._send_queue.append(msg)

    @Slot()
    def stop(self):
        self._is_running = False
        self._close_socket()

    def _close_socket(self):
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception: pass
            try:
                self._socket.close()
            except Exception: pass
            self._socket = None
        self.state_changed.emit("disconnected")
