import logging
import os
import re
import time
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QLineEdit, QCheckBox, 
    QTextEdit, QSpinBox, QStackedWidget,
    QFormLayout, QFrame, QSizePolicy, QApplication,
    QListWidget, QListWidgetItem, QComboBox, QScrollArea
)
from PySide6.QtCore import Slot, Qt, QObject, Signal

from app.config import AppConfig, save_config
from app.twitch_controller import TwitchController
from app.pear_client import PearWorker
from app.song_requests import SongRequestService
from app.ui.styles import get_stylesheet

class LogEmitter(QObject):
    log_signal = Signal(str, str)

class QtLogHandler(logging.Handler):
    def __init__(self, emitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record):
        level = record.levelname.lower()
        self.emitter.log_signal.emit(level, record.getMessage())

class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, twitch_ctrl: TwitchController, pear_worker: PearWorker, song_srv: SongRequestService):
        super().__init__()
        self.config = config
        self.twitch_ctrl = twitch_ctrl
        self.pear_worker = pear_worker
        self.song_srv = song_srv
        
        self.setWindowTitle("PearSongBot")
        self.resize(800, 550)
        
        # Load stylesheet with checkmark SVG
        current_dir = os.path.dirname(os.path.abspath(__file__))
        checkmark_path = os.path.join(current_dir, "checkmark.svg")
        self.setStyleSheet(get_stylesheet(checkmark_path))
        
        self._setup_ui()
        self._connect_signals()
        self._recent_logs: dict[tuple[str, str], tuple[float, int]] = {}
        self._settings_dirty = False
        self._syncing_ui = False
        self.btn_pear_pause.hide()
        
        # Route standard python logs to the UI text box
        self.log_emitter = LogEmitter()
        self.log_emitter.log_signal.connect(self.append_log)
        self.qt_log_handler = QtLogHandler(self.log_emitter)
        logging.getLogger().addHandler(self.qt_log_handler)
        
        self._sync_ui_with_config()
        self._force_dark_titlebar()
        
    def _force_dark_titlebar(self):
        import sys
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                value = ctypes.c_int(1)
                # DWMWA_USE_IMMERSIVE_DARK_MODE
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass
                
    def _create_card(self, title: str):
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)
        
        title_lbl = QLabel(title)
        title_lbl.setObjectName("CardTitle")
        card_layout.addWidget(title_lbl)
        
        return card, card_layout

    def _create_status_badge(self, title: str):
        badge = QFrame()
        badge.setObjectName("StatusBadge")
        badge_layout = QHBoxLayout(badge)
        badge_layout.setContentsMargins(12, 8, 12, 8)
        badge_layout.setSpacing(8)
        
        dot = QLabel()
        dot.setObjectName("StatusDot")
        dot.setFixedSize(10, 10)
        dot.setProperty("state", "disconnected")
        
        text = QLabel(f"{title}: Disconnected")
        text.setObjectName("StatusText")
        
        badge_layout.addWidget(dot)
        badge_layout.addWidget(text)
        badge_layout.addStretch()
        
        return badge, dot, text

    def _update_status(self, dot_widget, text_widget, title, state, display_text):
        dot_widget.setProperty("state", state)
        text_widget.setText(f"{title}: {display_text}")
        dot_widget.style().unpolish(dot_widget)
        dot_widget.style().polish(dot_widget)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ------------------
        # Left Sidebar Panel
        # ------------------
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 24, 16, 24)
        sidebar_layout.setSpacing(12)
        
        lbl_brand = QLabel("🍐 Pear Requests")
        lbl_brand.setObjectName("SidebarBrand")
        lbl_brand.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(lbl_brand)
        
        # Navigation Buttons
        self.btn_nav_dash = QPushButton("Dashboard")
        self.btn_nav_dash.setObjectName("SidebarBtn")
        self.btn_nav_dash.clicked.connect(lambda: self._on_nav_clicked(0))
        
        self.btn_nav_settings = QPushButton("Settings")
        self.btn_nav_settings.setObjectName("SidebarBtn")
        self.btn_nav_settings.clicked.connect(lambda: self._on_nav_clicked(1))
        
        self.btn_nav_logs = QPushButton("Logs")
        self.btn_nav_logs.setObjectName("SidebarBtn")
        self.btn_nav_logs.clicked.connect(lambda: self._on_nav_clicked(2))
        
        self.nav_buttons = [self.btn_nav_dash, self.btn_nav_settings, self.btn_nav_logs]
        for btn in self.nav_buttons:
            sidebar_layout.addWidget(btn)
            
        sidebar_layout.addStretch()
        main_layout.addWidget(sidebar)
        
        # ------------------
        # Right Stack Widget
        # ------------------
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(20, 20, 20, 20)
        
        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)
        main_layout.addWidget(content_container)
        
        # ------------------
        # Tab 1: Dashboard Page
        # ------------------
        dash_widget = QWidget()
        dash_layout = QVBoxLayout(dash_widget)
        dash_layout.setSpacing(20)
        dash_layout.setContentsMargins(0, 0, 0, 0)
        dash_layout.setAlignment(Qt.AlignTop)
        
        # Connection Panel Card
        conn_card, conn_card_layout = self._create_card("Status & Connection")
        
        # Status rows
        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        auth_badge, self.auth_dot, self.lbl_auth_status = self._create_status_badge("Auth")
        irc_badge, self.irc_dot, self.lbl_irc_status = self._create_status_badge("Bot")
        status_row.addWidget(auth_badge)
        status_row.addWidget(irc_badge)
        conn_card_layout.addLayout(status_row)
        
        # Connection Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.btn_auth = QPushButton("Connect Twitch")
        self.btn_auth.setObjectName("TwitchConnectBtn")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setVisible(False)
        
        self.btn_start_bot = QPushButton("Start Bot")
        self.btn_start_bot.setObjectName("StartBotBtn")
        self.btn_stop_bot = QPushButton("Stop Bot")
        self.btn_stop_bot.setObjectName("StopBotBtn")
        self.btn_stop_bot.setVisible(False)
        
        btn_row.addWidget(self.btn_auth)
        btn_row.addWidget(self.btn_disconnect)
        btn_row.addWidget(self.btn_start_bot)
        btn_row.addWidget(self.btn_stop_bot)
        conn_card_layout.addLayout(btn_row)
        
        dash_layout.addWidget(conn_card)
        
        # Player Panel Card
        player_card, player_card_layout = self._create_card("Pear Desktop Player")
        
        # Pear status badge
        pear_status_row = QHBoxLayout()
        pear_status_badge, self.pear_dot, self.lbl_pear_status = self._create_status_badge("Pear Desktop")
        pear_status_row.addWidget(pear_status_badge)
        player_card_layout.addLayout(pear_status_row)
        
        # Current song detail card
        song_detail = QFrame()
        song_detail.setObjectName("SongDetailCard")
        song_detail_layout = QVBoxLayout(song_detail)
        song_detail_layout.setContentsMargins(15, 12, 15, 12)
        song_detail_layout.setSpacing(4)
        
        lbl_now_playing_title = QLabel("NOW PLAYING")
        lbl_now_playing_title.setStyleSheet("color: #64748B; font-size: 11px; font-weight: bold;")
        
        self.lbl_current_song = QLabel("None")
        self.lbl_current_song.setObjectName("CurrentSongLabel")
        self.lbl_current_song.setWordWrap(True)
        
        song_detail_layout.addWidget(lbl_now_playing_title)
        song_detail_layout.addWidget(self.lbl_current_song)
        player_card_layout.addWidget(song_detail)
        
        # Player control button row
        p_btn_row = QHBoxLayout()
        p_btn_row.setAlignment(Qt.AlignCenter)
        p_btn_row.setSpacing(15)
        
        self.btn_pear_play = QPushButton("▶")
        self.btn_pear_play.setObjectName("PlayerBtn")
        self.btn_pear_pause = QPushButton("⏸")
        self.btn_pear_pause.setObjectName("PlayerBtn")
        self.btn_pear_next = QPushButton("⏭")
        self.btn_pear_next.setObjectName("PlayerBtn")
        self.btn_pear_clear = QPushButton("🗑")
        self.btn_pear_clear.setObjectName("PlayerBtn")
        self.btn_pear_clear.setToolTip("Clear Queue")
        
        for btn in (self.btn_pear_play, self.btn_pear_pause, self.btn_pear_next, self.btn_pear_clear):
            p_btn_row.addWidget(btn)
            
        player_card_layout.addLayout(p_btn_row)

        pear_actions_row = QHBoxLayout()
        pear_actions_row.addStretch()
        self.btn_pear_resync = QPushButton("Re-sync with Pear")
        self.btn_pear_resync.setObjectName("TextBtn")
        pear_actions_row.addWidget(self.btn_pear_resync)
        player_card_layout.addLayout(pear_actions_row)
        
        queue_lbl = QLabel("UPCOMING IN QUEUE")
        queue_lbl.setStyleSheet("color: #64748B; font-size: 11px; font-weight: bold; margin-top: 10px;")
        player_card_layout.addWidget(queue_lbl)
        
        self.list_queue = QListWidget()
        self.list_queue.setObjectName("QueueList")
        player_card_layout.addWidget(self.list_queue)
        
        dash_layout.addWidget(player_card)
        
        self.stacked_widget.addWidget(dash_widget)
        
        # ------------------
        # Tab 2: Settings Page
        # ------------------
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.NoFrame)
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setAlignment(Qt.AlignTop)
        
        req_card, req_card_layout = self._create_card("Song Requests Configuration")
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setSpacing(15)
        form_layout.setContentsMargins(0, 8, 0, 8)
        
        self.chk_enabled = QCheckBox("Enable song request commands")
        self.chk_enabled.toggled.connect(self._mark_settings_dirty)
        
        self.chk_queue = QCheckBox("Enable queue command")
        self.chk_queue.toggled.connect(self._mark_settings_dirty)
        
        self.chk_current = QCheckBox("Enable current command")
        self.chk_current.toggled.connect(self._mark_settings_dirty)
        
        self.chk_skip = QCheckBox("Enable skip command")
        self.chk_skip.toggled.connect(self._mark_settings_dirty)
        
        self.chk_remove = QCheckBox("Enable remove command")
        self.chk_remove.toggled.connect(self._mark_settings_dirty)
        
        self.txt_channel = QLineEdit()
        self.txt_channel.setPlaceholderText("e.g. your_twitch_name")
        self.txt_channel.textChanged.connect(self._mark_settings_dirty)
        
        self.spin_global = QSpinBox()
        self.spin_global.setRange(0, 3600)
        self.spin_global.setSuffix(" seconds")
        self.spin_global.valueChanged.connect(self._mark_settings_dirty)
        
        self.spin_user = QSpinBox()
        self.spin_user.setRange(0, 86400)
        self.spin_user.setSuffix(" seconds")
        self.spin_user.valueChanged.connect(self._mark_settings_dirty)

        self.txt_max_active = QLineEdit()
        self.txt_max_active.setPlaceholderText("empty = unlimited")
        self.txt_max_active.textChanged.connect(self._mark_settings_dirty)
        
        self.cmb_access_tier = QComboBox()
        self.cmb_access_tier.addItems(["Everyone", "Subscribers, VIPs & Mods", "VIPs & Mods Only", "Moderators Only"])
        self.cmb_access_tier.currentTextChanged.connect(self._mark_settings_dirty)
        
        form_layout.addRow("", self.chk_enabled)
        form_layout.addRow("", self.chk_queue)
        form_layout.addRow("", self.chk_current)
        form_layout.addRow("", self.chk_skip)
        form_layout.addRow("", self.chk_remove)
        form_layout.addRow("Target Channel:", self.txt_channel)
        form_layout.addRow("Global Cooldown:", self.spin_global)
        form_layout.addRow("User Cooldown:", self.spin_user)
        form_layout.addRow("Max Active Per User:", self.txt_max_active)
        form_layout.addRow("Access Tier:", self.cmb_access_tier)

        command_fields = [
            ("Song Command:", "song"), ("Queue Command:", "queue"),
            ("Current Command:", "current"), ("Skip Command:", "skip"),
            ("Remove Command:", "remove"),
        ]
        self.command_inputs = {}
        for label, name in command_fields:
            field = QLineEdit()
            field.setPlaceholderText(f"!{name}")
            field.textChanged.connect(self._mark_settings_dirty)
            self.command_inputs[name] = field
            form_layout.addRow(label, field)
        
        req_card_layout.addLayout(form_layout)
        settings_actions = QHBoxLayout()
        settings_actions.addStretch()
        self.btn_save_settings = QPushButton("Save Settings")
        self.btn_save_settings.setObjectName("StartBotBtn")
        self.btn_save_settings.clicked.connect(self._save_settings)
        self.btn_save_settings.setEnabled(False)
        settings_actions.addWidget(self.btn_save_settings)
        req_card_layout.addLayout(settings_actions)
        settings_layout.addWidget(req_card)

        response_card, response_layout = self._create_card("Chat Response Templates")
        help_label = QLabel("Available placeholders are shown in each field. Unknown placeholders are left unchanged.")
        help_label.setWordWrap(True)
        response_layout.addWidget(help_label)
        response_form = QFormLayout()
        response_form.setLabelAlignment(Qt.AlignRight)
        response_form.setSpacing(10)
        response_fields = [
            ("Remove Usage", "remove_usage", "{user}, {remove_command}"),
            ("Cooldown", "cooldown", "{user}"), ("Single Limit", "limit_single", "{user}, {limit}"),
            ("Request Limit", "limit_multiple", "{user}, {limit}"), ("Invalid Source", "invalid_source", "{user}"),
            ("Duplicate", "duplicate", "{user}"), ("Added Next", "added_next", "{user}, {track}, {position}"),
            ("Added Position", "added_position", "{user}, {track}, {position}"),
            ("Search Not Found", "search_not_found", "{user}"), ("Pear Unavailable", "pear_unavailable", "{user}"),
            ("Nothing Playing", "nothing_playing", "{user}"), ("Current Song", "current", "{user}, {artist}, {title}"),
            ("Skip Success", "skip_success", "{user}"), ("Remove Success", "remove_success", "{user}"),
            ("Skip Failed", "skip_failed", "{user}, {error}"), ("Remove Failed", "remove_failed", "{user}, {error}"),
            ("Empty Queue", "queue_empty", "{user}"), ("Queue", "queue", "{user}, {queue}"),
            ("Invalid Position", "remove_invalid_position", "{user}, {position}"),
            ("Removed Item", "remove_item", "{user}, {position}, {track}"),
        ]
        self.response_inputs = {}
        for label, name, placeholders in response_fields:
            field = QLineEdit()
            field.setPlaceholderText(placeholders)
            field.textChanged.connect(self._mark_settings_dirty)
            self.response_inputs[name] = field
            response_form.addRow(f"{label}:", field)
        response_layout.addLayout(response_form)
        settings_layout.addWidget(response_card)
        settings_scroll.setWidget(settings_widget)
        self.stacked_widget.addWidget(settings_scroll)
        
        # ------------------
        # Tab 3: Logs Page
        # ------------------
        logs_widget = QWidget()
        logs_layout = QVBoxLayout(logs_widget)
        logs_layout.setContentsMargins(0, 0, 0, 0)
        logs_layout.setSpacing(12)
        
        # Header Row for Logs Action Buttons
        log_header = QHBoxLayout()
        lbl_log_title = QLabel("System Log Messages")
        lbl_log_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #F8FAFC;")
        
        btn_copy = QPushButton("Copy Logs")
        btn_copy.setObjectName("TextBtn")
        btn_copy.clicked.connect(self._copy_logs)
        
        btn_clear = QPushButton("Clear Logs")
        btn_clear.setObjectName("TextBtn")
        btn_clear.clicked.connect(self._clear_logs)
        
        log_header.addWidget(lbl_log_title)
        log_header.addStretch()
        log_header.addWidget(btn_copy)
        log_header.addWidget(btn_clear)
        logs_layout.addLayout(log_header)
        
        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setFontFamily("Consolas")
        self.txt_logs.setStyleSheet("font-family: 'Consolas', 'Fira Code', monospace; font-size: 13px;")
        logs_layout.addWidget(self.txt_logs)
        
        self.stacked_widget.addWidget(logs_widget)
        
        # Default view (Dashboard)
        self._on_nav_clicked(0)

    def _on_nav_clicked(self, index: int):
        self.stacked_widget.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            active_val = True if i == index else False
            btn.setProperty("active", active_val)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _copy_logs(self):
        QApplication.clipboard().setText(self.txt_logs.toPlainText())
        logging.info("Logs copied to clipboard.")

    def _clear_logs(self):
        self.txt_logs.clear()

    def _sync_ui_with_config(self):
        self._syncing_ui = True
        cfg = self.config.song_requests
        self.chk_enabled.setChecked(cfg.enabled)
        self.chk_queue.setChecked(cfg.enable_queue_cmd)
        self.chk_current.setChecked(cfg.enable_current_cmd)
        self.chk_skip.setChecked(cfg.enable_skip_cmd)
        self.chk_remove.setChecked(cfg.enable_remove_cmd)
        self.txt_channel.setText(self.config.twitch.target_channel)
        self.spin_global.setValue(cfg.global_cooldown_seconds)
        self.spin_user.setValue(cfg.user_cooldown_seconds)
        self.txt_max_active.setText("" if cfg.max_active_per_user is None else str(cfg.max_active_per_user))
        for name, field in self.command_inputs.items():
            field.setText(getattr(cfg.commands, name))
        for name, field in self.response_inputs.items():
            field.setText(getattr(cfg.responses, name))
        
        # Sync access tier
        tier = cfg.access_tier
        if tier == "subs_only":
            self.cmb_access_tier.setCurrentText("Subscribers, VIPs & Mods")
        elif tier == "vip_mod":
            self.cmb_access_tier.setCurrentText("VIPs & Mods Only")
        elif tier == "mods_only":
            self.cmb_access_tier.setCurrentText("Moderators Only")
        else:
            self.cmb_access_tier.setCurrentText("Everyone")

        self._syncing_ui = False
        self._set_settings_dirty(False)
        
        if self.config.twitch.username:
            self._update_status(self.auth_dot, self.lbl_auth_status, "Auth", "connected", self.config.twitch.username)
            self.btn_auth.setVisible(False)
            self.btn_disconnect.setVisible(True)

    def _connect_signals(self):
        # Buttons
        self.btn_auth.clicked.connect(self.twitch_ctrl.start_oauth)
        self.btn_disconnect.clicked.connect(self.twitch_ctrl.disconnect_account)
        self.btn_start_bot.clicked.connect(self.twitch_ctrl.start_bot)
        self.btn_stop_bot.clicked.connect(self.twitch_ctrl.stop_bot)
        
        self.btn_pear_play.clicked.connect(self.pear_worker.command_toggle_play)
        self.btn_pear_next.clicked.connect(self.pear_worker.command_next)
        self.btn_pear_clear.clicked.connect(self.pear_worker.command_clear_queue)
        self.btn_pear_resync.clicked.connect(self.song_srv.command_resync_with_pear)

        # Twitch Controller
        self.twitch_ctrl.auth_state_changed.connect(self._on_auth_state_changed)
        self.twitch_ctrl.irc_state_changed.connect(self._on_irc_state_changed)
        self.twitch_ctrl.log_message.connect(self.append_log)
        
        # Song Request Service
        self.song_srv.log_message.connect(self.append_log)
        
        # Pear Worker
        self.pear_worker.state_changed.connect(self._on_pear_state_changed)
        self.pear_worker.current_song_updated.connect(self._on_current_song_updated)
        self.pear_worker.queue_updated.connect(self._on_queue_updated)
        self.pear_worker.clear_queue_completed.connect(self._on_clear_queue_completed)
        self.pear_worker.clear_queue_failed.connect(self._on_clear_queue_failed)

    @Slot(bool, str)
    def _on_auth_state_changed(self, is_auth: bool, username: str):
        if is_auth:
            self._update_status(self.auth_dot, self.lbl_auth_status, "Auth", "connected", username)
            self.btn_auth.setVisible(False)
            self.btn_disconnect.setVisible(True)
        else:
            self._update_status(self.auth_dot, self.lbl_auth_status, "Auth", "disconnected", "Disconnected")
            self.btn_auth.setVisible(True)
            self.btn_disconnect.setVisible(False)

    @Slot(str)
    def _on_irc_state_changed(self, state: str):
        if state == "connected":
            self._update_status(self.irc_dot, self.lbl_irc_status, "Bot", "connected", "Connected")
            self.btn_start_bot.setVisible(False)
            self.btn_stop_bot.setVisible(True)
        elif state == "connecting" or state == "reconnecting":
            self._update_status(self.irc_dot, self.lbl_irc_status, "Bot", "warning", f"{state.capitalize()}...")
            self.btn_start_bot.setVisible(False)
            self.btn_stop_bot.setVisible(True)
        else:
            self._update_status(self.irc_dot, self.lbl_irc_status, "Bot", "disconnected", "Stopped")
            self.btn_start_bot.setVisible(True)
            self.btn_stop_bot.setVisible(False)

    @Slot(str)
    def _on_pear_state_changed(self, state: str):
        if state == "connected":
            self._update_status(self.pear_dot, self.lbl_pear_status, "Pear Desktop", "connected", "Connected")
        else:
            self._update_status(self.pear_dot, self.lbl_pear_status, "Pear Desktop", "disconnected", state.capitalize())

    @Slot(object)
    def _on_current_song_updated(self, song: dict | None):
        self._update_toggle_button_label(song)
        if song and "title" in song:
            author = song.get("author") or song.get("artist")
            if author:
                self.lbl_current_song.setText(f"{author} - {song['title']}")
            else:
                self.lbl_current_song.setText(song['title'])
        else:
            self.lbl_current_song.setText("None")

    def _update_toggle_button_label(self, song: dict | None):
        if not isinstance(song, dict) or not song:
            self.btn_pear_play.setText("▶")
            return

        if song.get("isPaused") is True:
            self.btn_pear_play.setText("▶")
        elif song.get("isPaused") is False:
            self.btn_pear_play.setText("⏸")
        else:
            self.btn_pear_play.setText("▶")

    @Slot()
    def _on_clear_queue_completed(self):
        self.song_srv.clear_local_queue()
        self.append_log("info", "Pear queue cleared.")

    @Slot(str)
    def _on_clear_queue_failed(self, error: str):
        self.append_log("warning", f"Failed to clear Pear queue: {error}")

    @Slot(object)
    def _on_queue_updated(self, queue_data: dict):
        self.list_queue.clear()
        if not queue_data or not isinstance(queue_data, dict):
            return
            
        items = queue_data.get("items", [])
        for item in items:
            renderer = item.get("playlistPanelVideoRenderer", {})
            if not renderer:
                continue
                
            title_runs = renderer.get("title", {}).get("runs", [])
            title = "".join(r.get("text", "") for r in title_runs) if title_runs else "Unknown Title"
            
            byline_runs = renderer.get("shortBylineText", {}).get("runs", [])
            artist = "".join(r.get("text", "") for r in byline_runs)
            
            if artist:
                display_text = f"{artist} - {title}"
            else:
                display_text = title
                
            list_item = QListWidgetItem(display_text)
            self.list_queue.addItem(list_item)

    @Slot(str, str)
    def append_log(self, level: str, message: str):
        formatted = self._format_log_for_user(level, message)
        if formatted is None:
            return

        level, message = formatted
        if self._should_suppress_log(level, message):
            return

        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        color = "#94A3B8"
        if level == "error": color = "#EF4444"
        elif level == "warning": color = "#F59E0B"
        elif level == "info": color = "#3B82F6"
        
        self.txt_logs.append(f'<span style="color: #64748B;">[{ts}]</span> <span style="color: {color}; font-weight: bold;">[{level.upper()}]</span> {message}')

    def _format_log_for_user(self, level: str, message: str) -> tuple[str, str] | None:
        if level == "debug":
            return None

        lowered = message.lower()
        if "health check failed" in lowered:
            return None
        if "configuration saved successfully" in lowered:
            return None
        if "token securely written" in lowered or "token removed from credential manager" in lowered:
            return None
        if "failed to read token from credential manager" in lowered:
            return None

        replacements = [
            (r"^Queued viewer track [A-Za-z0-9_-]{11} for (\w+)$", "Viewer queue: added a track from @\\1."),
            (r"^Dispatched viewer track [A-Za-z0-9_-]{11}$", "Viewer queue: prepared the next viewer track in Pear."),
            (r"^Viewer track started: [A-Za-z0-9_-]{11} for (\w+)$", "Now playing: started a viewer request from @\\1."),
            (r"^Failed to dispatch viewer track: .+$", "Viewer queue: failed to prepare the next track in Pear."),
            (r"^Queue operation failed: .+$", "Viewer queue: failed to reorder or remove a track in Pear."),
            (r"^Searching song: (.+) by (\w+)$", "Search: looking for '\\1' for @\\2."),
            (r"^Starting browser for Twitch OAuth\.\.\.$", "Twitch: opening the browser for login."),
            (r"^Successfully authenticated as (\w+)$", "Twitch: connected as @\\1."),
            (r"^Twitch account disconnected\.$", "Twitch: account disconnected."),
            (r"^Connection error: .+$", "Twitch IRC: connection failed, retrying automatically."),
            (r"^Reconnecting in 5 seconds\.\.\.$", "Twitch IRC: reconnect scheduled in 5 seconds."),
            (r"^Cannot start bot: No Twitch token found\.$", "Twitch bot: can't start because no Twitch login token is available."),
            (r"^Cannot start bot: Twitch token storage is unavailable in this build\.$", "Twitch bot: this EXE cannot access saved Twitch credentials. Rebuild the app and log in again."),
            (r"^Cannot start bot: Twitch token could not be read from Windows Credential Manager\.$", "Twitch bot: saved Twitch credentials could not be read from Windows Credential Manager."),
            (r"^Cannot start bot: Twitch token is unavailable on this platform\.$", "Twitch bot: saved Twitch credentials are unavailable on this platform."),
            (r"^Cannot start bot: Target channel is empty\.$", "Twitch bot: can't start because the target channel is empty."),
            (r"^Bot is already running\.$", "Twitch bot: already running."),
            (r"^OAuth Failed: (.+)$", "Twitch login failed: \\1"),
            (r"^Failed to authenticate with Pear API: .+$", "Pear API: failed to authorize with the API server."),
            (r"^Failed to import win32cred for Twitch token storage: .+$", "Twitch login: the EXE is missing Windows credential support."),
            (r"^No Twitch token entry found in Windows Credential Manager\.$", "Twitch login: no saved Twitch credentials were found on this PC session."),
            (r"^Twitch token entry was found in Credential Manager but it is empty\.$", "Twitch login: saved Twitch credentials were empty."),
            (r"^Failed to read Twitch token from Credential Manager: .+$", "Twitch login: saved Twitch credentials could not be read."),
            (r"^Pear auth endpoint did not return an access token\.$", "Pear API: authorization did not return an access token."),
            (r"^Failed to get queue: .+$", "Pear API: failed to read the queue."),
            (r"^Failed to get current song: .+$", "Pear API: failed to read the current song."),
            (r"^HTTP Error adding song to Pear: .+$", "Pear API: failed to add a track to the queue."),
            (r"^Failed to send next command: .+$", "Pear API: failed to skip to the next track."),
            (r"^Failed to send pause command: .+$", "Pear API: failed to pause playback."),
            (r"^Failed to send play command: .+$", "Pear API: failed to resume playback."),
            (r"^Failed to send play/pause toggle command: .+$", "Pear API: failed to toggle playback."),
            (r"^Failed to clear queue: .+$", "Pear API: failed to clear the queue."),
            (r"^Failed to remove song: .+$", "Pear API: failed to remove a track."),
            (r"^Failed to move song: .+$", "Pear API: failed to reorder a track."),
            (r"^Failed to search song: .+$", "Pear API: search request failed."),
            (r"^Viewer queue cleared from the dashboard\.$", "Viewer queue: local queue cleared."),
            (r"^Starting re-sync with Pear\.$", "Pear sync: requesting a fresh queue and current track state."),
            (r"^Re-synced local queue with Pear\.$", "Pear sync: local queue state refreshed."),
            (r"^Rejected invalid URL from (\w+): .+$", "Request rejected: invalid non-YouTube link from @\\1."),
            (r"^Starting Twitch Pear Song Requests\.\.\.$", "Application started."),
        ]

        for pattern, replacement in replacements:
            if re.match(pattern, message):
                return level, re.sub(pattern, replacement, message)

        return level, message

    def _should_suppress_log(self, level: str, message: str) -> bool:
        now = time.monotonic()
        key = (level, message)
        previous = self._recent_logs.get(key)
        if previous and now - previous[0] < 8:
            self._recent_logs[key] = (now, previous[1] + 1)
            return True

        self._recent_logs[key] = (now, 1)
        stale_keys = [k for k, (ts, _) in self._recent_logs.items() if now - ts > 60]
        for stale_key in stale_keys:
            del self._recent_logs[stale_key]
        return False

    @Slot()
    def _mark_settings_dirty(self):
        if self._syncing_ui:
            return
        self._set_settings_dirty(True)

    def _set_settings_dirty(self, is_dirty: bool):
        self._settings_dirty = is_dirty
        if hasattr(self, "btn_save_settings"):
            self.btn_save_settings.setEnabled(is_dirty)
            self.btn_save_settings.setText("Save Settings*" if is_dirty else "Save Settings")

    @Slot()
    def _save_settings(self):
        self.config.twitch.target_channel = self.txt_channel.text().strip()
        
        cfg = self.config.song_requests
        cfg.enabled = self.chk_enabled.isChecked()
        cfg.enable_queue_cmd = self.chk_queue.isChecked()
        cfg.enable_current_cmd = self.chk_current.isChecked()
        cfg.enable_skip_cmd = self.chk_skip.isChecked()
        cfg.enable_remove_cmd = self.chk_remove.isChecked()
        cfg.global_cooldown_seconds = self.spin_global.value()
        cfg.user_cooldown_seconds = self.spin_user.value()
        for name, field in self.command_inputs.items():
            value = field.text().strip()
            if value and not value.startswith("!"):
                value = f"!{value}"
            setattr(cfg.commands, name, value)
            field.setText(value)
        for name, field in self.response_inputs.items():
            setattr(cfg.responses, name, field.text())
        raw_limit = self.txt_max_active.text().strip()
        if not raw_limit:
            cfg.max_active_per_user = None
        else:
            try:
                parsed_limit = int(raw_limit)
            except ValueError:
                parsed_limit = 1
            cfg.max_active_per_user = None if parsed_limit <= 0 else parsed_limit
            
        # Save access tier
        selected_tier = self.cmb_access_tier.currentText()
        if selected_tier == "Subscribers, VIPs & Mods":
            cfg.access_tier = "subs_only"
        elif selected_tier == "VIPs & Mods Only":
            cfg.access_tier = "vip_mod"
        elif selected_tier == "Moderators Only":
            cfg.access_tier = "mods_only"
        else:
            cfg.access_tier = "everyone"
            
        save_config(self.config)
        self._set_settings_dirty(False)
        self.append_log("info", "Settings saved.")

    def closeEvent(self, event):
        self.twitch_ctrl.stop_bot()
        self.pear_worker.stop()
        super().closeEvent(event)
