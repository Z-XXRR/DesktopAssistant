import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
import json


class EnglishWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        with open("config.json", "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.setup_ui()
        self.english_path = self.get_file_path("English.txt")
        self.load_english()
        self.last_mtime = self.get_file_mtime()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_update)
        self.timer.start(3000)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.word_list = QListWidget()
        self.word_list.setFont(QFont("Microsoft YaHei", 10))
        style = """
            QListWidget {
                background: transparent;
                border: 2px solid rgba(200,200,200,150);
                border-radius: 10px;
                padding: 10px;
                color: __TEXT_COLOR__;
            }
            QListWidget::item { color: __TEXT_COLOR__; padding: 5px; border-bottom: 1px solid rgba(200,200,200,100); }
            QListWidget::item:selected { background: rgba(100,150,255,100); }
            QScrollBar:vertical { width: 8px; background: rgba(200,200,200,100); border-radius: 4px; }
            QScrollBar::handle:vertical { background: rgba(150,150,150,150); border-radius: 4px; min-height: 20px; }
        """
        self.word_list.setStyleSheet(style.replace("__TEXT_COLOR__", self.config["color_words"]))
        self.word_list.itemClicked.connect(self.on_word_clicked)
        layout.addWidget(self.word_list)

    def get_file_path(self, filename):
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        return os.path.join(desktop, filename)

    def get_file_mtime(self):
        if os.path.exists(self.english_path):
            return os.path.getmtime(self.english_path)
        return 0

    def check_update(self):
        cur = self.get_file_mtime()
        if cur != self.last_mtime:
            self.last_mtime = cur
            self.load_english()

    def load_english(self):
        self.word_list.clear()
        if not os.path.exists(self.english_path):
            self.word_list.addItem("【英语文件不存在】\n请在桌面创建“English.txt”")
            return
        try:
            with open(self.english_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            self.word_list.addItem(f"读取出错：{e}")
            return
        for line in lines:
            line = line.strip()
            if not line:
                continue
            count = 1
            word = ""
            while True:
                parts = line.split(' ',1)
                word+= parts[0]+" "
                if len(parts) > 1 and parts[1] and parts[1][0].isascii() and parts[1][0].isalpha():
                    #count += 1
                    #continue
                    #word+= parts[0]+" "
                    line = parts[1]
                else:
                    #words+=parts[0]
                    if len(parts) > 1:
                        meaning = parts[1]
                    else:
                        meaning = ""
                    break

            #parts = line.split(' ', count)
            #word = parts[0]
            #meaning = parts[1] if len(parts) > 1 else ""

            item = QListWidgetItem(word)
            item.setData(Qt.UserRole, {'word': word, 'meaning': meaning, 'show_meaning': False})
            self.word_list.addItem(item)

    def on_word_clicked(self, item):
        data = item.data(Qt.UserRole)
        if not data:
            return
        data['show_meaning'] = not data.get('show_meaning', False)
        if data['show_meaning']:
            text = f"{data['word']}  {data['meaning']}" if data['meaning'] else data['word']
        else:
            text = data['word']
        item.setText(text)
        item.setData(Qt.UserRole, data)