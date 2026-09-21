import os
import json
from PyQt5.QtCore import QObject, QTimer

class AutoSync(QObject):
    def __init__(self, config, config_path, parent=None):
        super().__init__(parent)
        self.config = config
        self.config_path = config_path
        self.english_path = os.path.join(os.path.expanduser("~"), "Desktop", "English.txt")
        self.target_path = config.get("sync_target_path", "")
        self.last_line = config.get("sync_last_line", "")
        self.last_mtime = self._get_mtime()
        self._asked_target = False   # 防止重复弹窗

        # 启动时：记录 English.txt 最后一行
        self._init_baseline()

        # 定时轮询
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check_update)
        self.timer.start(3000)

    # ---------- 初始化基线 ----------
    def _init_baseline(self):
        """启动时读取最后一行；若与配置记录不符，用当前内容覆盖"""
        lines = self._read_lines()
        if not lines:
            return
        current_last = lines[-1]
        if self.last_line != current_last:
            self.last_line = current_last
            self.config["sync_last_line"] = current_last
            self._save_config()

    # ---------- 工具方法 ----------
    def _get_mtime(self):
        if os.path.exists(self.english_path):
            return os.path.getmtime(self.english_path)
        return 0

    def _read_lines(self):
        if not os.path.exists(self.english_path):
            return []
        try:
            with open(self.english_path, "r", encoding="utf-8") as f:
                return [line.rstrip("\n").rstrip("\r") for line in f.readlines()]
        except Exception as e:
            print(f"读取 English.txt 失败: {e}")
            return []

    def _save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置失败: {e}")

    # ---------- 核心：检测更新并同步 ----------
    def _check_update(self):
        cur_mtime = self._get_mtime()
        if cur_mtime == self.last_mtime:
            return
        self.last_mtime = cur_mtime

        lines = self._read_lines()
        if not lines:
            return

        # 找到 last_line 最后一次出现的位置，之后的内容都是新的
        new_lines = []
        if self.last_line:
            try:
                idx = len(lines) - 1 - lines[::-1].index(self.last_line)
                new_lines = lines[idx + 1:]
            except ValueError:
                # 配置中的 last_line 已不在文件中（被用户清空或改写），把全部当作新内容
                new_lines = lines
        else:
            new_lines = lines

        if not new_lines:
            return

        # 确保目标路径存在
        if not self._ensure_target_path():
            return

        # 追加到目标文件
        self._append_to_target(new_lines)

        # 更新配置中的 last_line
        self.last_line = lines[-1]
        self.config["sync_last_line"] = self.last_line
        self._save_config()

    # ---------- 目标文件路径 ----------
    def _ensure_target_path(self):
        if self.target_path:
            return True
        if self._asked_target:
            return False
        self._asked_target = True

        from PyQt5.QtWidgets import QInputDialog
        path, ok = QInputDialog.getText(
            None,
            "设置同步目标文件",
            "首次启用自动同步，请输入目标 txt 文件的完整路径：\n"
            "（例如：D:/Sync/EnglishSync.txt）"
        )
        if ok and path.strip():
            self.target_path = path.strip()
            self.config["sync_target_path"] = self.target_path
            self._save_config()
            return True
        return False

    # ---------- 写入目标文件 ----------
    def _append_to_target(self, new_lines):
        try:
            dir_path = os.path.dirname(self.target_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
            with open(self.target_path, "a", encoding="utf-8") as f:
                for line in new_lines:
                    f.write(line + "\n")
            print(f"[AutoSync] 已同步 {len(new_lines)} 行到 {self.target_path}")
        except Exception as e:
            print(f"[AutoSync] 写入目标文件失败: {e}")

    # ---------- 停止 ----------
    def stop(self):
        if self.timer:
            self.timer.stop()