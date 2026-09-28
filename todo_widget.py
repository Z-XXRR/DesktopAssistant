import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont
import json



class TodoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        with open("config.json", "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.setup_ui()
        self.todo_path = self.get_file_path(self.config["todo_list"])
        self.load_todo()
        self.last_mtime = self.get_file_mtime()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_update)
        self.timer.start(3000)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Microsoft YaHei", 10))
        style = """
            QTextEdit {
                background: transparent;
                border: 2px solid rgba(200,200,200,150);
                border-radius: 10px;
                padding: 10px;
                color: __TEXT_COLOR__;
            }
            QScrollBar:vertical { width: 8px; background: rgba(200,200,200,100); border-radius: 4px; }
            QScrollBar::handle:vertical { background: rgba(150,150,150,150); border-radius: 4px; min-height: 20px; }
        """
        self.text_edit.setStyleSheet(style.replace("__TEXT_COLOR__", self.config["color_setting"]))
        layout.addWidget(self.text_edit)

    def get_file_path(self, filename):
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        return os.path.join(desktop, filename)

    def get_file_mtime(self):
        if os.path.exists(self.todo_path):
            return os.path.getmtime(self.todo_path)
        return 0

    def check_update(self):
        cur = self.get_file_mtime()
        if cur != self.last_mtime:
            self.last_mtime = cur
            self.load_todo()

    def load_todo(self):
        if os.path.exists(self.todo_path):
            try:
                with open(self.todo_path, "r", encoding="utf-8") as f:
                    self.text_edit.setText(f.read())
            except Exception as e:
                self.text_edit.setText(f"读取出错：{e}")
        else:
            self.text_edit.setText("【代办文件不存在】\n请在桌面创建“代办.txt”")