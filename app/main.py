import sys
from collections import deque
from functools import partial
from pathlib import Path
from threading import Lock, Thread
from time import monotonic

import httpx
import psutil
from PySide6.QtCore import QLibraryInfo, QObject, QPoint, QProcess, QRect, QRectF, QTimer, QTranslator, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QFontComboBox, QFormLayout, QGraphicsDropShadowEffect,
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QScrollArea, QSizeGrip, QSlider, QSpinBox,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from .audio import CaptureManager, LiveClipQueue
from .engine import ASRWorker, nvidia_gpus
from .settings import ROOT, Settings
from .downloads import download_verified
from .i18n import LANGUAGES, resolve_language, text
from .profile import DEFAULT_PROFILE, PROFILES, recognition_profile
from . import startup, updates
from .vulkan import vulkan_gpus


def product_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 64, size / 64)
        gradient = QLinearGradient(6, 6, 58, 60)
        gradient.setColorAt(0, QColor("#5debd7"))
        gradient.setColorAt(1, QColor("#5587f5"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(1, 1, 62, 62), 16, 16)
        painter.setBrush(QColor("#092032"))
        painter.drawRoundedRect(QRectF(11, 14, 42, 31), 7, 7)
        painter.setPen(QPen(QColor("#092032"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(22, 43, 17, 49)
        painter.setPen(QPen(QColor("#effffd"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(19, 25, 45, 25)
        painter.drawLine(19, 34, 36, 34)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class Caption:
    def __init__(self, sequential=False):
        self.lock = Lock()
        self.text = ""
        self.time = 0
        self.until = 0
        self.pending = deque(maxlen=48) if sequential else None

    def publish(self, text):
        with self.lock:
            if self.pending is not None:
                if text:
                    self.pending.append(text)
            else:
                self.text = text
                self.time = monotonic()

    def read(self, seconds, fit=None):
        with self.lock:
            now = monotonic()
            if self.pending is not None and now >= self.until and self.pending:
                self.text = self.pending.popleft()
                if fit:
                    self.text, remainder = fit(self.text)
                    if remainder:
                        self.pending.appendleft(remainder)
                self.time = now
                self.until = now + max(1.0, min(6.0, len(self.text.split()) / 4))
            return self.text if now - self.time < seconds else ""


class Events(QObject):
    status = Signal(object, str)
    detail = Signal(object, str)
    update = Signal(str, object)
    installer = Signal(object)


class AudioMeter(QWidget):
    def __init__(self, tr):
        super().__init__()
        self.level = 0.0
        self.setFixedSize(80, 20)
        self.setAccessibleName(tr("meter"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for i, height in enumerate((5, 10, 16, 20, 16, 10, 5, 9)):
            painter.setBrush(QColor("#6ce4d4" if i < round(self.level * 8) else "#35536b"))
            painter.drawRoundedRect(QRectF(i * 10 + 2, (20 - height) / 2, 4, height), 2, 2)

    def set_level(self, level):
        if round(self.level * 8) != round(level * 8):
            self.level = level
            self.update()


class DragBar(QLabel):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.offset = event.globalPosition().toPoint() - self.window().pos()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, "offset"):
            self.window().move(event.globalPosition().toPoint() - self.offset)


class CaptionWindow(QWidget):
    def __init__(self, settings, tr):
        super().__init__()
        self.setWindowTitle(tr("caption_window"))
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(310, 105)
        self.resize(740, 170)
        geometry = settings.get("caption_geometry")
        if isinstance(geometry, list) and len(geometry) == 4:
            saved = QRect(*geometry)
            if any(screen.availableGeometry().intersected(saved).width() >= 100
                   and screen.availableGeometry().intersected(saved).height() >= 35
                   for screen in QApplication.screens()):
                self.setGeometry(saved)
        else:
            area = QApplication.primaryScreen().availableGeometry()
            self.move(QPoint(area.center().x() - self.width() // 2, area.bottom() - self.height() - 60))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.toolbar = QWidget()
        toolbar = QHBoxLayout(self.toolbar)
        toolbar.setContentsMargins(0, 0, 0, 0)
        handle = DragBar(tr("drag"))
        handle.setStyleSheet("background: #192431; color: white; border-radius: 7px; padding: 6px;")
        hide = QPushButton(tr("hide"))
        hide.clicked.connect(self.hide)
        mark = QLabel()
        mark.setPixmap(self.windowIcon().pixmap(24))
        toolbar.addWidget(mark)
        toolbar.addWidget(handle, 1)
        toolbar.addWidget(hide)
        layout.addWidget(self.toolbar)

        self.caption = DragBar()
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setMinimumWidth(0)
        self.caption.setMinimumHeight(0)
        self.caption.setAccessibleName(tr("caption_access"))
        self.shadow = QGraphicsDropShadowEffect(self.caption)
        self.shadow.setColor(QColor("#000000"))
        self.shadow.setBlurRadius(8)
        self.shadow.setOffset(1, 2)
        self.caption.setGraphicsEffect(self.shadow)
        layout.addWidget(self.caption, 1)
        grip = QSizeGrip(self)
        grip.setStyleSheet("background: #192431;")
        layout.addWidget(grip, 0, Qt.AlignmentFlag.AlignRight)

    def apply_style(self, font, color, opacity):
        self.caption.setFont(font)
        self.shadow.setEnabled(opacity < 35)
        self.caption.setStyleSheet(
            f"color: {color.name()};"
            f"background: rgba(10, 16, 25, {round(opacity * 255 / 100)});"
            "border-radius: 10px; padding: 8px;"
        )

    def set_pinned(self, pinned):
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned)
        if visible:
            self.show()

    def set_title_visible(self, visible):
        self.toolbar.setVisible(visible)

    def fit_caption(self, text):
        words = text.split()
        bounds = self.caption.rect().adjusted(8, 8, -8, -8)
        metrics = self.caption.fontMetrics()
        for count in range(len(words), 1, -1):
            page = " ".join(words[:count])
            if metrics.boundingRect(bounds, Qt.TextFlag.TextWordWrap, page).height() <= bounds.height():
                return page, " ".join(words[count:])
        return words[0], " ".join(words[1:])


class ControlWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.language = resolve_language(self.settings.get("ui_language", "auto"))
        self.t = partial(text, self.language)
        self.events = Events(self)
        self.events.status.connect(self.on_status)
        self.events.detail.connect(self.on_detail)
        self.events.update.connect(self.on_update_result)
        self.events.installer.connect(self.on_installer_ready)
        self.update_in_progress = False
        self.update_message = ""
        self.preferences = None
        self.relaunch = None
        self.install_update = None
        self.worker = None
        self.previous_worker = None
        self.exiting = False
        self.captures = None
        self.caption = Caption()
        self.preview_until = 0
        self.floating = CaptionWindow(self.settings, self.t)
        self.setWindowTitle("SubtitleForEveryone")
        self.setMinimumWidth(600)
        control_font = self.font()
        control_font.setPixelSize(14)
        self.setFont(control_font)
        self.setStyleSheet("""
            QWidget { background: #0c1520; color: #edf6ff; }
            QLabel { background: transparent; }
            QFrame#monitor { background: #132438; border: 1px solid #2d4860; border-radius: 15px; }
            QLabel#monitorTitle { color: #8dc9d4; font-weight: 700; }
            QPushButton, QComboBox, QSpinBox {
                background: #1b3044; color: #f0f7ff; border: 1px solid #3a536c;
                border-radius: 8px; padding: 8px;
            }
            QPushButton:hover { background: #284662; }
            QPushButton#primary { background: #6ce4d4; color: #0b1e2b; font-weight: 700; }
            QPushButton#primary:hover { background: #a0f3e9; }
            QPushButton:focus, QComboBox:focus, QSpinBox:focus { border: 2px solid #8fe1fc; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        heading = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(self.windowIcon().pixmap(52))
        heading.addWidget(mark)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("SubtitleForEveryone")
        title.setStyleSheet("font-size: 25px; font-weight: 700;")
        titles.addWidget(title)
        tagline = QLabel(self.t("tagline"))
        tagline.setStyleSheet("color: #a9bed2;")
        titles.addWidget(tagline)
        heading.addLayout(titles, 1)
        preferences = QPushButton(self.t("settings"))
        preferences.clicked.connect(self.show_preferences)
        heading.addWidget(preferences)
        layout.addLayout(heading)

        monitor = QFrame()
        monitor.setObjectName("monitor")
        monitor_layout = QVBoxLayout(monitor)
        monitor_layout.setContentsMargins(16, 12, 16, 14)
        monitor_title = QLabel(self.t("monitor"))
        monitor_title.setObjectName("monitorTitle")
        monitor_header = QHBoxLayout()
        monitor_header.addWidget(monitor_title, 1)
        self.audio_meter = AudioMeter(self.t)
        monitor_header.addWidget(self.audio_meter)
        monitor_layout.addLayout(monitor_header)
        self.monitor_text = QLabel()
        self.monitor_text.setTextFormat(Qt.TextFormat.PlainText)
        self.monitor_text.setWordWrap(True)
        self.monitor_text.setMinimumHeight(56)
        monitor_layout.addWidget(self.monitor_text)
        layout.addWidget(monitor)

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(0, 0, 0, 0)
        self.source = QComboBox()
        self.source.setEditable(True)
        self.source.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.source.lineEdit().setPlaceholderText(self.t("process_hint"))
        self.refresh_sources()
        refresh = QPushButton(self.t("refresh"))
        refresh.clicked.connect(self.refresh_sources)
        sources = QHBoxLayout()
        sources.addWidget(self.source, 1)
        sources.addWidget(refresh)
        audio_label = QLabel(self.t("source"))
        audio_label.setBuddy(self.source)
        form.addRow(audio_label, sources)
        self.model = QComboBox()
        for name in ("tiny", "base", "small", "medium", "large-v3"):
            self.model.addItem(name)
        self.model.setCurrentText(self.settings.get("asr_model", "tiny"))
        form.addRow(self.t("model"), self.model)
        self.subtitle_language = QComboBox()
        self.subtitle_language.addItem(self.t("original"), "auto")
        for code, label in LANGUAGES.items():
            self.subtitle_language.addItem(label, code)
        self.subtitle_language.setCurrentIndex(max(0, self.subtitle_language.findData(
            self.settings.get("subtitle_language", "auto"))))
        self.subtitle_language.currentIndexChanged.connect(
            lambda _: self.settings.set("subtitle_language", self.subtitle_language.currentData()))
        form.addRow(self.t("subtitle_language"), self.subtitle_language)
        self.backend = QComboBox()
        self.backend.addItem("CPU", "cpu")
        for index, name, _ in nvidia_gpus():
            self.backend.addItem(f"CUDA · {name}", f"cuda:{index}")
        for index, name in vulkan_gpus():
            self.backend.addItem(f"Vulkan · {name}", f"vulkan:{index}")
        self.backend.setCurrentIndex(max(0, self.backend.findData(self.settings.get("asr_device"))))
        form.addRow(self.t("compute"), self.backend)
        self.profile_slider = QSlider(Qt.Orientation.Horizontal)
        self.profile_slider.setRange(0, len(PROFILES) - 1)
        self.profile_slider.setValue(self.settings.get("recognition_profile", DEFAULT_PROFILE))
        self.profile_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.profile_slider.setTickInterval(1)
        self.profile_slider.setAccessibleName(self.t("balance"))
        self.profile_slider.valueChanged.connect(lambda value: self.settings.set("recognition_profile", value))
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel(self.t("speed")))
        profile_row.addWidget(self.profile_slider, 1)
        profile_row.addWidget(QLabel(self.t("quality")))
        form.addRow(profile_row)

        self.font_picker = QFontComboBox()
        self.font_picker.setCurrentFont(QFont(self.settings.get("caption_font", QApplication.font().family())))
        self.font_picker.currentFontChanged.connect(self.change_font)
        self.text_color = QColor(self.settings.get("caption_color", "#ffffff"))
        if not self.text_color.isValid():
            self.text_color = QColor("#ffffff")
        self.color_button = QPushButton()
        self.color_button.setAccessibleName(self.t("text_color"))
        self.color_button.clicked.connect(self.choose_text_color)
        text_style = QHBoxLayout()
        text_style.addWidget(self.font_picker, 1)
        text_style.addWidget(self.color_button)
        font_label = QLabel(self.t("font_color"))
        font_label.setBuddy(self.font_picker)
        form.addRow(font_label, text_style)

        self.font_size = QSpinBox()
        self.font_size.setRange(16, 72)
        self.font_size.setSuffix(" px")
        self.font_size.setValue(self.settings.get("font_size", 31))
        self.font_size.valueChanged.connect(self.apply_style)
        form.addRow(self.t("text_size"), self.font_size)
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(self.settings.get("opacity", 65))
        self.opacity_value = QLabel()
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity, 1)
        opacity_row.addWidget(self.opacity_value)
        self.opacity.setAccessibleName(self.t("opacity"))
        self.opacity.valueChanged.connect(self.apply_style)
        form.addRow(self.t("opacity"), opacity_row)

        self.pin = QCheckBox(self.t("pinned"))
        self.pin.setChecked(self.settings.get("pinned", True))
        self.pin.toggled.connect(self.set_pinned)
        form.addRow(self.pin)
        self.title_visible = QCheckBox(self.t("show_title"))
        self.title_visible.setChecked(self.settings.get("show_caption_title", False))
        self.title_visible.toggled.connect(self.floating.set_title_visible)
        form.addRow(self.title_visible)
        controls = QScrollArea()
        controls.setFrameShape(QFrame.Shape.NoFrame)
        controls.setWidgetResizable(True)
        controls.setWidget(form_widget)
        controls.setMinimumHeight(min(form_widget.sizeHint().height() + 2,
                                      max(200, self.screen().availableGeometry().height() - 340)))
        layout.addWidget(controls, 1)

        actions = QHBoxLayout()
        self.start_button = QPushButton(self.t("start"))
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.toggle)
        show = QPushButton(self.t("show"))
        show.clicked.connect(self.floating.show)
        preview = QPushButton(self.t("preview"))
        preview.clicked.connect(self.show_preview)
        for button in (self.start_button, show, preview):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.status = QLabel(self.t("choose_source"))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.apply_style()
        self.floating.set_pinned(self.pin.isChecked())
        self.floating.set_title_visible(self.title_visible.isChecked())
        self.setup_tray()
        self.refresh_caption()

        self.timer = QTimer(self, interval=100)
        self.timer.timeout.connect(self.refresh_caption)
        self.timer.start()
        if self.settings.get("check_updates_on_startup", True):
            QTimer.singleShot(250, self.check_updates)

    def show_preferences(self):
        if self.preferences is None:
            self.preferences = QDialog(self)
            self.preferences.setWindowTitle(self.t("settings"))
            form = QFormLayout(self.preferences)
            language = QComboBox()
            language.addItem(self.t("system_language"), "auto")
            for code, name in LANGUAGES.items():
                language.addItem(name, code)
            language.setCurrentIndex(max(0, language.findData(self.settings.get("ui_language", "auto"))))
            language.activated.connect(lambda _: self.change_language(language.currentData()))
            form.addRow(self.t("ui_language"), language)
            logon = QCheckBox(self.t("auto_start"))
            logon.setChecked(startup.enabled())
            logon.toggled.connect(lambda checked: self.change_logon(logon, checked))
            form.addRow(logon)
            auto_update = QCheckBox(self.t("update_start"))
            auto_update.setChecked(self.settings.get("check_updates_on_startup", True))
            auto_update.toggled.connect(lambda value: self.settings.set("check_updates_on_startup", value))
            form.addRow(auto_update)
            self.update_button = QPushButton(self.t("update_check"))
            self.update_button.setEnabled(not self.update_in_progress)
            self.update_button.clicked.connect(self.check_updates)
            form.addRow(self.update_button)
            self.update_status = QLabel(self.update_message)
            self.update_status.setWordWrap(True)
            form.addRow(self.update_status)
            form.addRow(QLabel(self.t("version", version=updates.installed_version())))
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            buttons.rejected.connect(self.preferences.reject)
            form.addRow(buttons)
        self.preferences.exec()

    def change_language(self, language):
        if language == self.settings.get("ui_language", "auto"):
            return
        self.settings.set("ui_language", language)
        self.relaunch = ["--resume-transcription"] if self.worker else []
        self.preferences.accept()
        self.quit_from_tray()

    def change_logon(self, checkbox, value):
        try:
            startup.set_enabled(value)
        except OSError as error:
            checkbox.blockSignals(True)
            checkbox.setChecked(not value)
            checkbox.blockSignals(False)
            QMessageBox.warning(self.preferences, self.t("settings"), self.t("auto_start_error") + "\n" + str(error))

    def set_update_status(self, key):
        self.update_message = self.t(key)
        if self.preferences is not None:
            self.update_status.setText(self.update_message)
            self.update_button.setEnabled(not self.update_in_progress)

    def check_updates(self):
        if self.update_in_progress:
            return
        self.update_in_progress = True
        self.set_update_status("update_wait")

        def fetch():
            try:
                with httpx.Client(timeout=6) as client:
                    result = updates.latest_update(client)
            except (httpx.HTTPError, ValueError, OSError):
                result = "failed", None
            self.events.update.emit(*result)

        Thread(target=fetch, daemon=True).start()

    def on_update_result(self, result, release):
        self.update_in_progress = False
        self.set_update_status("update_" + result)
        if result == "available":
            installable = bool(getattr(sys, "frozen", False) and release.url)
            answer = QMessageBox.question(self.preferences if self.preferences and self.preferences.isVisible() else self,
                                          self.t("update_check"),
                                          self.t("update_install" if installable else "update_found", version=release.tag))
            if answer == QMessageBox.StandardButton.Yes:
                if installable:
                    self.download_update(release)
                else:
                    QDesktopServices.openUrl(QUrl(release.page))

    def download_update(self, release):
        self.update_in_progress = True
        self.set_update_status("update_download")

        def fetch():
            try:
                with httpx.Client(timeout=30) as client:
                    path = download_verified(client, release.url, ROOT / "updates" / release.name,
                                             release.size, release.digest)
            except (httpx.HTTPError, ValueError, OSError):
                path = None
            self.events.installer.emit(path)

        Thread(target=fetch, daemon=True).start()

    def on_installer_ready(self, path):
        self.update_in_progress = False
        if path is None:
            self.set_update_status("update_failed")
            QMessageBox.warning(self, self.t("update_check"), self.t("update_failed"))
            return
        self.install_update = str(path)
        self.quit_from_tray()

    def setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("SubtitleForEveryone")
        self.tray_menu = QMenu(self)
        self.tray_menu.addAction(self.t("open"), self.restore_controls)
        self.tray_toggle = self.tray_menu.addAction(self.t("start_tray"), self.toggle)
        self.tray_menu.addAction(self.t("toggle_captions"), self.toggle_floating)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.t("quit"), self.quit_from_tray)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore_controls()

    def restore_controls(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_floating(self):
        self.floating.setVisible(not self.floating.isVisible())

    def quit_from_tray(self):
        self.exiting = True
        self.close()
        QApplication.quit()

    def refresh_sources(self):
        previous = self.source.currentText() or self.settings.get("audio_source", "")
        self.source.clear()
        self.source.addItem(self.t("all_apps"), {"kind": "system"})
        processes = {process.info["name"] for process in psutil.process_iter(["name"])
                     if process.info["name"]}
        for name in sorted(processes, key=str.casefold):
            if name.lower().endswith(".exe"):
                self.source.addItem(name)
        if previous:
            index = self.source.findText(previous)
            if index >= 0:
                self.source.setCurrentIndex(index)
            elif previous.lower().endswith(".exe"):
                self.source.setEditText(previous)

    def apply_style(self):
        size, opacity = self.font_size.value(), self.opacity.value()
        font = self.font_picker.currentFont()
        font.setPixelSize(size)
        font.setWeight(QFont.Weight.Bold)
        color = self.text_color.name()
        swatch = QPixmap(16, 16)
        swatch.fill(self.text_color)
        self.color_button.setIcon(QIcon(swatch))
        self.color_button.setText(color.upper())
        self.opacity_value.setText(f"{opacity}%")
        self.floating.apply_style(font, self.text_color, opacity)
        font.setPixelSize(20)
        self.monitor_text.setFont(font)
        self.monitor_text.setStyleSheet(f"color: {color};")

    def change_font(self, font):
        self.settings.set("caption_font", font.family())
        self.apply_style()

    def choose_text_color(self):
        color = QColorDialog.getColor(self.text_color, self, self.t("text_color"))
        if color.isValid():
            self.text_color = color
            self.settings.set("caption_color", color.name())
            self.apply_style()

    def set_pinned(self, pinned):
        self.floating.set_pinned(pinned)

    def show_preview(self):
        self.preview_until = monotonic() + 5
        self.refresh_caption()
        self.floating.show()

    def refresh_caption(self):
        caption_text = self.t("preview_caption") if monotonic() < self.preview_until else self.caption.read(6, self.floating.fit_caption)
        if self.floating.caption.text() != caption_text:
            self.floating.caption.setText(caption_text)
        preview = caption_text or (self.t("waiting") if self.worker else self.t("monitor_idle"))
        if self.monitor_text.text() != preview:
            self.monitor_text.setText(preview)
        self.audio_meter.set_level(self.captures.input_level() if self.worker else 0.0)

    def toggle(self):
        if self.worker:
            self.stop()
            return
        if self.previous_worker and self.previous_worker.is_alive():
            self.status.setText(self.t("stopping"))
            return
        self.previous_worker = None
        name = self.source.currentText().strip()
        index = self.source.findText(name)
        source = self.source.itemData(index) if index >= 0 else None
        if source is None:
            if not name or not name.lower().endswith(".exe") or any(c in name for c in "/\\:"):
                self.status.setText(self.t("invalid_source"))
                return
            source = {"kind": "process", "process": name}

        self.settings.set("audio_source", source.get("process", ""))
        self.settings.set("sources", [dict(source, id="input", name=name, enabled=True)])
        self.settings.set("asr_model", self.model.currentText())
        self.settings.set("asr_device", self.backend.currentData())
        profile = recognition_profile(self.settings)
        clips = LiveClipQueue(maxsize=profile.queue_size)
        self.caption = Caption(sequential=profile.max_caption_age is None)
        self.preview_until = 0
        session = object()
        self.session = session
        on_detail = lambda message: self.events.detail.emit(session, message)
        self.worker = ASRWorker(self.settings, clips, self.caption, on_detail,
                                on_state=self.events.status.emit, tr=self.t)
        self.captures = CaptureManager(self.settings, clips, on_detail, tr=self.t)
        self.status.setText(self.t("preparing"))
        self.detail.clear()
        self.source.setEnabled(False)
        self.model.setEnabled(False)
        self.backend.setEnabled(False)
        self.profile_slider.setEnabled(False)
        if self.tray:
            self.tray_toggle.setText(self.t("pause_tray"))
        self.start_button.setText(self.t("pause"))
        self.floating.show()
        self.worker.start()

    def on_status(self, worker, stage):
        if worker is not self.worker:
            return
        self.status.setText(self.t(stage, device=worker.active_device or "CPU", model=worker.active_model))
        if stage == "ready" and not self.captures.workers:
            self.captures.start()

    def on_detail(self, session, message):
        if self.worker and self.session is session:
            self.detail.setText(message)

    def stop(self):
        if self.worker:
            worker, self.worker = self.worker, None
            self.previous_worker = worker
            worker.stop()
            self.captures.stop()
        self.caption = Caption()
        self.preview_until = 0
        self.refresh_caption()
        self.source.setEnabled(True)
        self.model.setEnabled(True)
        self.backend.setEnabled(True)
        self.profile_slider.setEnabled(True)
        if self.tray:
            self.tray_toggle.setText(self.t("start_tray"))
        self.start_button.setText(self.t("start"))
        self.status.setText(self.t("paused"))
        self.detail.clear()

    def closeEvent(self, event):
        frame = self.floating.geometry()
        for key, value in {
            "caption_geometry": [frame.x(), frame.y(), frame.width(), frame.height()],
            "font_size": self.font_size.value(),
            "opacity": self.opacity.value(),
            "pinned": self.pin.isChecked(),
            "show_caption_title": self.title_visible.isChecked(),
            "asr_device": self.backend.currentData(),
            "asr_model": self.model.currentText(),
        }.items():
            self.settings.set(key, value)
        if self.tray and not self.exiting:
            self.hide()
            event.ignore()
            return
        self.stop()
        if self.tray:
            self.tray.hide()
        self.floating.close()
        event.accept()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from .self_test import run
        return run(Path(sys.argv[2]))
    if sys.platform == "win32":
        from ctypes import windll
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("SubtitleForEveryone.Desktop")
    app = QApplication(sys.argv)
    app.setApplicationName("SubtitleForEveryone")
    app.setWindowIcon(product_icon())
    window = ControlWindow()
    translator = QTranslator(app)
    translations = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(f"qtbase_{window.language}", translations):
        app.installTranslator(translator)
    window.show()
    if "--resume-transcription" in sys.argv:
        QTimer.singleShot(0, window.toggle)
    status = app.exec()
    if window.install_update:
        QProcess.startDetached(window.install_update, [], str(ROOT / "updates"))
    elif window.relaunch is not None:
        args = window.relaunch
        if not getattr(sys, "frozen", False):
            args = [str(Path(__file__).resolve().parents[1] / "launch.py"), *args]
        QProcess.startDetached(sys.executable, args)
    return status
