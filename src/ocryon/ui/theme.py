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
    min-height: 32px;
    padding: 6px 14px;
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
    selection-color: #ffffff;
    min-height: 32px;
    padding: 6px;
}
QListWidget::item {
    min-height: 28px;
    padding: 2px 4px;
}
QListWidget::item:selected {
    background: #174f80;
    color: #ffffff;
}
QPlainTextEdit {
    placeholder-text-color: #8fa2bc;
}
QComboBox {
    min-width: 88px;
}
QScrollArea {
    background: #080d15;
    border: none;
}
QProgressBar {
    background: #0b121d;
    border: 1px solid #2c4c73;
    border-radius: 7px;
    min-height: 20px;
    text-align: center;
}
QProgressBar::chunk {
    background: #145ea8;
    border-radius: 6px;
}
QToolTip {
    background: #111d2c;
    color: #f7fbff;
    border: 1px solid #4d86c5;
    padding: 5px;
}
QStatusBar {
    background: #070b12;
    color: #7f91aa;
}
"""
