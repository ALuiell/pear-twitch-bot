def get_stylesheet(checkmark_path: str = "") -> str:
    # Ensure backslashes are forward slashes for Qt CSS url() compliance
    checkmark_url = checkmark_path.replace("\\", "/")
    return f"""
    QWidget {{
        background: #090D16;
        color: #E2E8F0;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 14px;
    }}
    
    /* Sidebar styling */
    QFrame#Sidebar {{
        background: #0D1321;
        border-right: 1px solid #1E293B;
    }}
    
    QLabel#SidebarBrand {{
        color: #FFFFFF;
        font-size: 18px;
        font-weight: bold;
        padding: 10px 5px;
    }}
    
    QPushButton#SidebarBtn {{
        background: transparent;
        color: #94A3B8;
        border: none;
        border-radius: 8px;
        padding: 12px 16px;
        font-weight: bold;
        text-align: left;
    }}
    
    QPushButton#SidebarBtn:hover {{
        background: #1E293B;
        color: #E2E8F0;
    }}
    
    QPushButton#SidebarBtn[active="true"] {{
        background: #2563EB;
        color: #FFFFFF;
    }}
    
    QPushButton#SidebarBtn[active="true"]:hover {{
        background: #3B82F6;
    }}

    /* Card styling (replaces QGroupBox) */
    QFrame#Card {{
        background: #111827;
        border: 1px solid #1E293B;
        border-radius: 12px;
    }}
    
    QLabel#CardTitle {{
        color: #F8FAFC;
        font-size: 16px;
        font-weight: bold;
    }}

    /* Status dot & badge styling */
    QFrame#StatusBadge {{
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
    }}
    
    QLabel#StatusDot {{
        border-radius: 5px;
        background-color: #EF4444; /* Default red */
    }}
    
    QLabel#StatusDot[state="connected"] {{
        background-color: #10B981;
    }}
    
    QLabel#StatusDot[state="disconnected"] {{
        background-color: #EF4444;
    }}
    
    QLabel#StatusDot[state="warning"] {{
        background-color: #F59E0B;
    }}
    
    QLabel#StatusText {{
        color: #E2E8F0;
        font-weight: 500;
        background: transparent;
    }}

    /* Buttons styling */
    QPushButton {{
        background: #2563EB;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 16px;
        font-weight: bold;
    }}
    
    QPushButton:hover {{
        background: #3B82F6;
    }}
    
    QPushButton:disabled {{
        background: #1E293B;
        color: #64748B;
    }}
    
    QPushButton#TwitchConnectBtn {{
        background: #9146FF;
        font-size: 14px;
        padding: 10px 20px;
    }}
    
    QPushButton#TwitchConnectBtn:hover {{
        background: #A970FF;
    }}
    
    QPushButton#StartBotBtn {{
        background: #10B981;
        font-size: 14px;
        padding: 10px 20px;
    }}
    
    QPushButton#StartBotBtn:hover {{
        background: #34D399;
    }}
    
    QPushButton#StopBotBtn {{
        background: #EF4444;
        font-size: 14px;
        padding: 10px 20px;
    }}
    
    QPushButton#StopBotBtn:hover {{
        background: #F87171;
    }}
    
    QPushButton#PlayerBtn {{
        background: #1E293B;
        border: 1px solid #334155;
        font-size: 20px;
        border-radius: 20px; /* Round buttons */
        height: 40px;
        width: 40px;
        padding: 0;
    }}
    
    QPushButton#PlayerBtn:hover {{
        background: #334155;
        border-color: #475569;
    }}
    
    QPushButton#TextBtn {{
        background: #1E293B;
        border: 1px solid #334155;
        color: #E2E8F0;
        padding: 6px 12px;
        font-size: 12px;
        font-weight: bold;
    }}
    
    QPushButton#TextBtn:hover {{
        background: #334155;
    }}

    /* Current song display inside player */
    QFrame#SongDetailCard {{
        background: #090D16;
        border: 1px solid #1E293B;
        border-radius: 8px;
    }}
    
    QLabel#CurrentSongLabel {{
        font-size: 16px;
        color: #F8FAFC;
        font-weight: bold;
        background: transparent;
    }}
    
    /* Input Elements */
    QLineEdit, QSpinBox, QTextEdit {{
        background: #090D16;
        border: 1px solid #1E293B;
        border-radius: 6px;
        padding: 8px;
        color: #F8FAFC;
        selection-background-color: #3B82F6;
    }}
    
    QLineEdit:focus, QSpinBox:focus, QTextEdit:focus {{
        border: 1px solid #3B82F6;
    }}
    
    /* Checkbox indicator with checkmark */
    QCheckBox {{
        spacing: 8px;
        font-weight: bold;
    }}
    
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 2px solid #475569;
        background: #090D16;
    }}
    
    QCheckBox::indicator:hover {{
        border-color: #3B82F6;
    }}
    
    QCheckBox::indicator:checked {{
        background: #3B82F6;
        border-color: #2563EB;
        image: url({checkmark_url});
    }}

    /* Scrollbars */
    QScrollBar:vertical {{
        background: #090D16;
        width: 10px;
        margin: 2px;
        border-radius: 4px;
    }}
    
    QScrollBar::handle:vertical {{
        background: #475569;
        min-height: 20px;
        border-radius: 4px;
    }}
    
    QScrollBar::handle:vertical:hover {{
        background: #64748B;
    }}
    
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    
    /* Queue List styling */
    QListWidget#QueueList {{
        background: #090D16;
        border: 1px solid #1E293B;
        border-radius: 8px;
        padding: 4px;
        outline: none;
    }}
    
    QListWidget#QueueList::item {{
        color: #F8FAFC;
        padding: 8px 12px;
        border-radius: 4px;
        margin-bottom: 2px;
    }}
    
    QListWidget#QueueList::item:hover {{
        background: #1E293B;
    }}
    
    QListWidget#QueueList::item:selected {{
        background: #2563EB;
        color: #FFFFFF;
    }}
    """
