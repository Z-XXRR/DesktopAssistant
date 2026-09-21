import sys
import os
from PyQt5.QtWidgets import QDialog, QCheckBox, QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox
from PyQt5.QtCore import Qt
import json
import winreg  # 原代码漏了这一行，会 NameError

AUTOSTART_NAME = "TodoDesktop"

def _project_dir():
    return os.path.dirname(os.path.abspath(__file__))

def _startup_dir():
    """当前用户的「启动」文件夹路径（不需要管理员权限）"""
    return os.path.join(
        os.environ.get("APPDATA", ""),
        r"Microsoft\Windows\Start Menu\Programs\Startup"
    )

def _is_real_python_exe(path):
    """判断是否真实可执行的 Python 解释器（排除 WindowsApps 的执行别名）"""
    if not path:
        return False
    if not os.path.isfile(path):
        return False
    # WindowsApps 下的 python.exe 是 0 字节 reparse point，WshShell.Run 调用会 80070002
    low = path.lower().replace("/", "\\")
    # 注意：这里必须是普通字符串，\\windowsapps\\ 会折叠成单反斜杠 \windowsapps\
    if "\\windowsapps\\" in low:
        return False
    return True

def _build_run_command():
    """构造开机时运行的命令。
    返回 (target_exe, args_list, working_directory)
    - 打包模式：直接运行 exe
    - 开发模式：找真实存在的 pythonw.exe / pyw.exe，避免弹黑色控制台
    """
    workdir = _project_dir()
    if getattr(sys, "frozen", False):
        return sys.executable, [], workdir

    main_py = os.path.join(workdir, "main.py")

    # 候选无窗口解释器：按优先级降序排列
    candidates = []
    # 1) sys.executable 同目录下的 pythonw.exe（标准 Python.org 安装）
    exe_dir = os.path.dirname(sys.executable)
    candidates.append(os.path.join(exe_dir, "pythonw.exe"))
    # 2) Python Launcher 的 pyw.exe（最稳，专门为无窗口启动设计）
    local_app = os.environ.get("LocalAppData", "")
    if local_app:
        candidates.append(os.path.join(local_app, r"Programs\Python\Launcher\pyw.exe"))
    # 3) sys.executable 本身（如果它不是 WindowsApps 别名）
    if _is_real_python_exe(sys.executable):
        candidates.append(sys.executable)
    # 4) py.exe launcher（会有黑框，作为最后兜底）
    if local_app:
        candidates.append(os.path.join(local_app, r"Programs\Python\Launcher\py.exe"))

    for c in candidates:
        if _is_real_python_exe(c):
            return c, [main_py], workdir

    raise RuntimeError(
        "找不到真实存在的 Python 解释器。\n"
        "当前 sys.executable = " + sys.executable + "\n"
        "候选路径都不是真实文件。请用 python.org 的安装包安装 Python，"
        "或改用打包后的 exe 模式。"
    )



class SettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.config = config
        self.autostart_notice = None  # 延迟到对话框关闭后再提示，避免嵌套模态框
        self.setWindowTitle("设置")
        self.setFixedSize(300, 280)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # 开机自启
        self.cb_autostart = QCheckBox("开机自动启动")
        self.cb_autostart.setChecked(self.config.get("auto_start", False))
        layout.addWidget(self.cb_autostart)

        # 功能开关
        self.cb_todo = QCheckBox("启用待办提示")
        self.cb_todo.setChecked(self.config.get("enable_todo", True))
        layout.addWidget(self.cb_todo)

        self.cb_english = QCheckBox("启用英语单词")
        self.cb_english.setChecked(self.config.get("enable_english", True))
        layout.addWidget(self.cb_english)

        self.cb_sync = QCheckBox("自动同步 English.txt 到目标文件")
        self.cb_sync.setChecked(self.config.get("enable_sync", False))
        layout.addWidget(self.cb_sync)
        # 保存/取消
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def save(self):
        # 更新配置
        self.config["auto_start"] = self.cb_autostart.isChecked()
        self.config["enable_todo"] = self.cb_todo.isChecked()
        self.config["enable_english"] = self.cb_english.isChecked()
        self.config["enable_sync"] = self.cb_sync.isChecked()

        # 保存到文件
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

        # 设置开机启动
        try:
            self.set_auto_start(self.config["auto_start"])
        except Exception as e:
            QMessageBox.critical(self, "开机自启设置失败", str(e))

        self.accept()

    # ------------------------------------------------------------------
    # 开机自启：启动文件夹 + .vbs 脚本（不需要管理员权限、不闪黑框、中文路径稳）
    # ------------------------------------------------------------------
    def set_auto_start(self, enabled):
        startup = _startup_dir()
        if not os.path.isdir(startup):
            raise RuntimeError("找不到启动文件夹：" + startup)

        vbs_path = os.path.join(startup, f"{AUTOSTART_NAME}.vbs")

        if enabled:
            target_exe, args, workdir = _build_run_command()
            vbs = SettingsDialog._make_vbs(target_exe, args, workdir)
            # UTF-16 LE + BOM 是 VBScript 最稳的编码，中文路径不会乱码
            with open(vbs_path, "wb") as f:
                f.write(b"\xFF\xFE")  # UTF-16 LE BOM
                f.write(vbs.encode("utf-16-le"))

            # 同时清理旧版本可能写入的注册表项，避免重复启动
            self._remove_registry_entry()

            # 延迟到本对话框关闭后再提示（见 show_settings），避免嵌套模态对话框
            if not getattr(sys, "frozen", False):
                self.autostart_notice = (
                    "已写入启动文件夹。\n"
                    "说明：开发模式下会使用 pythonw.exe 静默启动 main.py。\n"
                    "若重启后未启动，请先手动运行 main.py 确认脚本本身能正常运行。"
                )
        else:
            # 移除启动文件夹中的 vbs
            if os.path.exists(vbs_path):
                try:
                    os.remove(vbs_path)
                except OSError:
                    pass
            # 同时清理旧注册表项
            self._remove_registry_entry()

    @staticmethod
    def _make_vbs(target_exe, args, workdir):
        """生成用于 WshShell.Run 的 VBS 源码。

        注意：VBScript 字符串字面量中，要表示一个 ASCII 双引号，必须
        写成两个连续的 ""。因此整个命令里所有内部双引号在进入字面量
        前都要加倍一次，外面再用一对 "" 包住整个字符串。
        """
        def vbs_escape(s):
            # 防止路径里罕见地含有 " 字符，破坏字面量结构
            return s.replace('"', '""')

        # 1) 运行时实际执行的命令字符串（含 ASCII 引号，用来分隔空格/中文路径）：
        #      "target_exe" "arg1" "arg2" ...
        runtime_parts = [f'"{vbs_escape(target_exe)}"']
        runtime_parts += [f'"{vbs_escape(a)}"' for a in args]
        runtime_cmd = " ".join(runtime_parts)

        # 2) 把 runtime_cmd 表达成一个 VBS 字符串字面量：
        #    外面包一层 "..."，内部每个 " 都写成 ""
        vbs_cmd_literal = '"' + runtime_cmd.replace('"', '""') + '"'

        esc_workdir = vbs_escape(workdir)

        lines = [
            "Option Explicit",
            "Dim WshShell",
            'Set WshShell = CreateObject("WScript.Shell")',
            f'WshShell.CurrentDirectory = "{esc_workdir}"',
            f"WshShell.Run {vbs_cmd_literal}, 0, False",
            "Set WshShell = Nothing",
            "",    # 文件末尾留个空行，VBS 更稳
        ]
        return "\r\n".join(lines)

    @staticmethod
    def _remove_registry_entry():
        """清理老版本可能写入的注册表 Run 项，避免重复启动。"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except OSError:
            pass
