APP_STYLESHEET = """
QWidget {
    background: #0a0f18;
    color: #e8edf5;
    font-family: "Segoe UI";
    font-size: 13px;
}
QMainWindow {
    background: #070b12;
}
QFrame#topBar, QFrame#panel {
    background: #0f1724;
    border: 1px solid #1b2b42;
    border-radius: 12px;
}
QLabel#brand {
    font-size: 24px;
    font-weight: 800;
    color: #f7fbff;
}
QLabel#tagline {
    color: #7f91aa;
}
QPushButton {
    background: #16243a;
    border: 1px solid #2c4c73;
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background: #1b3150;
    border-color: #4d86c5;
}
QPushButton:focus, QComboBox:focus, QListWidget:focus, QPlainTextEdit:focus {
    border: 2px solid #67b7ff;
}
QPushButton:disabled, QComboBox:disabled {
    color: #75869c;
    background: #101925;
    border-color: #23354b;
}
QPushButton#primary {
    background: #145ea8;
    border-color: #2c88dc;
}
QPushButton#primary:hover {
    background: #1c70c2;
}
QListWidget, QPlainTextEdit, QComboBox {
    background: #0b121d;
    border: 1px solid #1c2c42;
    border-radius: 8px;
    selection-background-color: #174f80;
    padding: 6px;
}
QScrollArea {
    background: #080d15;
    border: none;
}
QStatusBar {
    background: #070b12;
    color: #7f91aa;
}
"""
