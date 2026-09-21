import os
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QApplication, QMessageBox, QSplitter
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QPen, QColor
from todo_widget import TodoWidget
from english_widget import EnglishWidget

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

SPLITTER_HANDLE = 6   # 待办框与英语框之间分割条的粗细
MIN_BOX_HEIGHT = 60   # 单个框可被拖到的最小高度
SAVE_DELAY = 500      # 尺寸变化后延迟写盘的毫秒数


class ResizeGrip(QWidget):
    """角落上的缩放手柄，自绘样式（QSizeGrip 画得极淡，透明窗口上看不见）。

    corner="bottom_right"：拖右下角，改窗口长宽，左上角不动；
    corner="top_left"    ：拖左上角，右、下边固定，窗口位置和长宽一起变。
    """

    def __init__(self, parent, corner):
        super().__init__(parent)
        self.mirrored = corner == "top_left"
        self.setFixedSize(18, 18)
        self.setCursor(Qt.SizeBDiagCursor if self.mirrored else Qt.SizeFDiagCursor)
        self.setToolTip("拖动调整左上角" if self.mirrored else "拖动调整窗口大小")
        self._origin = None     # 按下时的鼠标位置
        self._geometry = None   # 按下时的窗口几何

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 160))
        painter.drawEllipse(0, 0, w, h)
        painter.setPen(QPen(QColor(90, 90, 90, 220), 1.5))
        for i in range(3):
            off = i * 4 + 4
            if self.mirrored:
                painter.drawLine(off, 2, 2, off)
            else:
                painter.drawLine(w - off, h - 2, w - 2, h - off)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._origin = event.globalPos()
            self._geometry = self.window().geometry()

    def mouseMoveEvent(self, event):
        if self._origin is None:
            return
        win = self.window()
        delta = event.globalPos() - self._origin
        if self.mirrored:
            w = max(win.minimumWidth(), self._geometry.width() - delta.x())
            h = max(win.minimumHeight(), self._geometry.height() - delta.y())
            # 右下角固定，左上角跟着鼠标移动
            win.setGeometry(self._geometry.right() + 1 - w,
                            self._geometry.bottom() + 1 - h, w, h)
        else:
            w = max(win.minimumWidth(), self._geometry.width() + delta.x())
            h = max(win.minimumHeight(), self._geometry.height() + delta.y())
            win.resize(w, h)

    def mouseReleaseEvent(self, event):
        self._origin = None
        self._geometry = None


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(200, 100)  # 可自由缩放，只保留最小尺寸

        # 加载配置
        self.config = self.load_config()
        self.auto_sync = None
        # 布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(0)   # 无缝衔接

        # 存储子组件引用
        self.todo_widget = None
        self.english_widget = None

        # 待办框与英语框放在分割器里，框之间的分割条可拖动，单独调整各自高度
        self.splitter = QSplitter(Qt.Vertical, self)
        self.splitter.setHandleWidth(SPLITTER_HANDLE)
        self.splitter.setStyleSheet("""
            QSplitter::handle { background: rgba(180,180,180,120); border-radius: 2px; }
            QSplitter::handle:hover { background: rgba(120,150,255,180); }
        """)
        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        self.layout.addWidget(self.splitter)

        self._stretch_sizes = []      # 当前分割比例，用于窗口整体缩放时按用户比例分配
        self._syncing_stretch = False # 同步比例时忽略 splitterMoved，避免反复触发

        # 拖动缩放时延迟写盘，避免每一帧都写 config.json
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self.save_geometry)

        # 右上角按钮（悬浮，不加入布局）
        self.setting_btn = QPushButton("⚙", self)
        self.setting_btn.setFixedSize(36, 36)
        self.setting_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,180);
                border: 1px solid rgba(200,200,200,150);
                border-radius: 18px;
                font-size: 16px;
                color: #333;
            }
            QPushButton:hover { background: rgba(230,230,230,200); }
        """)
        self.setting_btn.clicked.connect(self.show_settings)
        self.close_btn = QPushButton("✕", self)
        self.close_btn.setFixedSize(36, 36)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,180);
                border: 1px solid rgba(200,200,200,150);
                border-radius: 18px;
                font-size: 16px;
                color: #333;
            }
            QPushButton:hover { background: rgba(255,120,120,180); }
        """)
        self.close_btn.clicked.connect(self.close_app)

        # 两个角落的缩放把手：无边框窗口靠它们拖动调整大小
        self.size_grip = ResizeGrip(self, "bottom_right")   # 右下：改长宽
        self.top_left_grip = ResizeGrip(self, "top_left")   # 左上：改长宽并移动窗口

        # 根据配置创建子组件（内部会按配置设置窗口长宽，并将按钮/把手置顶）
        self.rebuild_widgets()
        self.move_to_top_right()

    def load_config(self):
        default = {
            "auto_start": False, "enable_todo": True, "enable_english": True,
            # 尺寸设置：窗口宽度、待办框高度、英语框高度
            "window_width": 600, "todo_height": 800, "english_height": 400,
        }
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return default
        return default

    def save_config(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)
    


    def _update_auto_sync(self):
        """根据配置启用/停用自动同步"""
        enabled = self.config.get("enable_sync", False)
        if enabled:
            if self.auto_sync is None:
                try:
                    from auto_sync import AutoSync
                    self.auto_sync = AutoSync(self.config, CONFIG_PATH, self)
                except Exception as e:
                    print(f"[MainWindow] 启动自动同步失败: {e}")
                    self.auto_sync = None
        
        else:
            if self.auto_sync is not None:
                self.auto_sync.stop()
                self.auto_sync = None
    

    def rebuild_widgets(self):
        """根据当前配置重建子组件"""
        # ---------- 1. 清除旧组件 ----------
        for w in (self.todo_widget, self.english_widget):
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.todo_widget = None
        self.english_widget = None

        # ---------- 2. 按配置的尺寸恢复窗口，并添加启用的组件 ----------
        width = self.config.get("window_width", 600)
        todo_h = self.config.get("todo_height", 800)
        english_h = self.config.get("english_height", 400)
        heights = []   # 已启用组件的高度，同时作为分割比例

        # 添加待办（不固定高度，可被分割条拖动调整）
        if self.config.get("enable_todo", True):
            self.todo_widget = TodoWidget(self)
            self.todo_widget.setMinimumHeight(MIN_BOX_HEIGHT)
            self.splitter.addWidget(self.todo_widget)
            heights.append(todo_h)

        # 添加英语单词
        if self.config.get("enable_english", True):
            self.english_widget = EnglishWidget(self)
            self.english_widget.setMinimumHeight(MIN_BOX_HEIGHT)
            self.splitter.addWidget(self.english_widget)
            heights.append(english_h)

        # ---------- 3. 调整窗口尺寸（上下各10像素边距） ----------
        # 若两个功能都关闭，至少保留最小高度，避免窗口不可见
        if not heights:
            heights = [100]
        handle = SPLITTER_HANDLE if len(heights) > 1 else 0

        # 最小尺寸：每个框至少 MIN_BOX_HEIGHT，拖动把手时窗口不能再被压小
        self.setMinimumSize(200, MIN_BOX_HEIGHT * len(heights) + handle + 20)

        # 窗口不能超出屏幕，否则右下角的缩放手柄会掉到屏幕外，根本够不到
        screen = QApplication.primaryScreen().availableGeometry()
        width = min(width, screen.width())
        limit = screen.height() - handle - 20
        if sum(heights) > limit:
            ratio = limit / float(sum(heights))
            heights = [max(MIN_BOX_HEIGHT, int(h * ratio)) for h in heights]

        self.resize(width, sum(heights) + handle + 20)

        # 用配置高度恢复分割比例；等窗口真正布局完成后再设置，否则会被忽略
        sizes = list(heights)
        self._stretch_sizes = sizes
        self._syncing_stretch = True
        for i, h in enumerate(sizes):
            self.splitter.setStretchFactor(i, max(1, h))
        self._syncing_stretch = False
        QTimer.singleShot(0, lambda: self.splitter.setSizes(sizes))

        # ---------- 4. 悬浮按钮与缩放把手置顶 ----------
        # 子组件创建在后，层级高于按钮，会把鼠标事件全部吃掉，
        # 必须重新定位并 raise，否则设置/关闭按钮点击无效。
        self.reposition_corner_buttons()
        self.setting_btn.raise_()
        self.close_btn.raise_()
        self.size_grip.raise_()
        self.top_left_grip.raise_()

        # ---------- 5. 更新自动同步状态 ----------
        self._update_auto_sync()


    def reposition_corner_buttons(self):
        m = 14
        x = self.width() - m
        self.close_btn.move(x - self.close_btn.width(), m)
        self.setting_btn.move(x - self.close_btn.width() - 8 - self.setting_btn.width(), m)
        # 缩放把手分别固定在右下角和左上角
        self.size_grip.move(
            self.width() - m - self.size_grip.width(),
            self.height() - m - self.size_grip.height(),
        )
        self.top_left_grip.move(m, m)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reposition_corner_buttons()
        # 子组件几何在本次事件之后才更新，延迟读取真实尺寸再写盘
        self._save_timer.start(SAVE_DELAY)

    def _on_splitter_moved(self, pos, index):
        """拖动两个框之间的分割条后，延迟写盘"""
        if not self._syncing_stretch:
            self._save_timer.start(SAVE_DELAY)

    def save_geometry(self):
        """把用户调出来的窗口长宽、两个框的高度存入 config.json"""
        changed = False
        if self.config.get("window_width") != self.width():
            self.config["window_width"] = self.width()
            changed = True

        for key, widget in (("todo_height", self.todo_widget),
                            ("english_height", self.english_widget)):
            if widget is not None and self.config.get(key) != widget.height():
                self.config[key] = widget.height()
                changed = True

        # 记录当前分割比例：之后整体缩放窗口时，两个框按用户的比例分配
        sizes = self.splitter.sizes()
        if sizes and sizes != self._stretch_sizes:
            self._stretch_sizes = sizes
            self._syncing_stretch = True
            for i, h in enumerate(sizes):
                self.splitter.setStretchFactor(i, max(1, h))
            self._syncing_stretch = False

        if changed:
            self.save_config()

    def show_settings(self):
        try:
            from settings import SettingsDialog
            dlg = SettingsDialog(self, self.config)
            if dlg.exec_():
                # 用户保存后，重新加载配置并重建
                self.config = self.load_config()
                self.rebuild_widgets()
                # 同时更新开机启动（由settings处理）
                notice = getattr(dlg, "autostart_notice", None)
                if notice:
                    QMessageBox.information(self, "已开启自启", notice)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开设置失败：{e}")
        finally:
            # 主窗口是 Qt.Tool + WindowStaysOnBottomHint，模态子对话框关闭后
            # 可能被窗口管理器隐藏且不再重显，这里强制恢复显示，避免看起来像“程序退出”。
            self.show()
            self.raise_()
            self.activateWindow()

    def close_app(self):
        reply = QMessageBox.question(self, "退出确认", "确定退出？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.close()

    def move_to_top_right(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.width() - self.width(), 0)