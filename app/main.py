import sys
from threading import Lock
from time import monotonic

import psutil
from PySide6.QtCore import QObject, QPoint, QRect, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QGraphicsDropShadowEffect,
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QSizeGrip, QSlider, QSpinBox,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from .audio import CaptureManager, LiveClipQueue
from .engine import ASRWorker, nvidia_gpus
from .settings import Settings
from .translation import OUTPUT_LANGUAGES
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
    def __init__(self):
        self.lock = Lock()
        self.text = ""
        self.time = 0

    def publish(self, text):
        with self.lock:
            self.text = text
            self.time = monotonic()

    def read(self, seconds):
        with self.lock:
            return self.text if monotonic() - self.time < seconds else ""


class Events(QObject):
    status = Signal(object, str)
    detail = Signal(object, str)


class AudioMeter(QWidget):
    def __init__(self):
        super().__init__()
        self.level = 0.0
        self.setFixedSize(80, 20)
        self.setAccessibleName("Livello audio")

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
    def __init__(self, settings):
        super().__init__()
        self.setWindowTitle("Finestra sottotitoli")
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
        handle = DragBar("   Sottotitoli · trascina per spostare")
        handle.setStyleSheet("background: #192431; color: white; border-radius: 7px; padding: 6px;")
        hide = QPushButton("Nascondi")
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
        self.caption.setAccessibleName("Sottotitoli in tempo reale")
        self.shadow = QGraphicsDropShadowEffect(self.caption)
        self.shadow.setColor(QColor("#000000"))
        self.shadow.setBlurRadius(8)
        self.shadow.setOffset(1, 2)
        self.caption.setGraphicsEffect(self.shadow)
        layout.addWidget(self.caption, 1)
        grip = QSizeGrip(self)
        grip.setStyleSheet("background: #192431;")
        layout.addWidget(grip, 0, Qt.AlignmentFlag.AlignRight)

    def apply_style(self, size, opacity):
        self.shadow.setEnabled(opacity < 35)
        self.caption.setStyleSheet(
            f"color: white; font-size: {size}px; font-weight: 700;"
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


class ControlWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.events = Events(self)
        self.events.status.connect(self.on_status)
        self.events.detail.connect(self.on_detail)
        self.worker = None
        self.previous_worker = None
        self.exiting = False
        self.captures = None
        self.caption = Caption()
        self.preview_until = 0
        self.floating = CaptionWindow(self.settings)
        self.setWindowTitle("SubtitleForEveryone")
        self.setMinimumWidth(600)
        self.setStyleSheet("""
            QWidget { background: #0c1520; color: #edf6ff; font-size: 14px; }
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
        tagline = QLabel("Sottotitoli in tempo reale per l’audio di Windows")
        tagline.setStyleSheet("color: #a9bed2;")
        titles.addWidget(tagline)
        heading.addLayout(titles, 1)
        layout.addLayout(heading)

        monitor = QFrame()
        monitor.setObjectName("monitor")
        monitor_layout = QVBoxLayout(monitor)
        monitor_layout.setContentsMargins(16, 12, 16, 14)
        monitor_title = QLabel("Monitor sottotitoli")
        monitor_title.setObjectName("monitorTitle")
        monitor_header = QHBoxLayout()
        monitor_header.addWidget(monitor_title, 1)
        self.audio_meter = AudioMeter()
        monitor_header.addWidget(self.audio_meter)
        monitor_layout.addLayout(monitor_header)
        self.monitor_text = QLabel()
        self.monitor_text.setTextFormat(Qt.TextFormat.PlainText)
        self.monitor_text.setWordWrap(True)
        self.monitor_text.setMinimumHeight(56)
        self.monitor_text.setStyleSheet("font-size: 20px; font-weight: 650;")
        monitor_layout.addWidget(self.monitor_text)
        layout.addWidget(monitor)

        form = QFormLayout()
        self.source = QComboBox()
        self.source.setEditable(True)
        self.source.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.source.lineEdit().setPlaceholderText("Nome del processo, ad esempio chrome.exe")
        self.refresh_sources()
        refresh = QPushButton("Aggiorna elenco")
        refresh.clicked.connect(self.refresh_sources)
        sources = QHBoxLayout()
        sources.addWidget(self.source, 1)
        sources.addWidget(refresh)
        audio_label = QLabel("&Sorgente audio")
        audio_label.setBuddy(self.source)
        form.addRow(audio_label, sources)
        self.model = QComboBox()
        for name in ("tiny", "base", "small", "medium", "large-v3"):
            self.model.addItem(name)
        self.model.setCurrentText(self.settings.get("asr_model", "tiny"))
        form.addRow("&Modello Whisper", self.model)
        self.subtitle_language = QComboBox()
        self.subtitle_language.addItem("Lingua del parlato (automatica)", "auto")
        for code, label in OUTPUT_LANGUAGES.items():
            self.subtitle_language.addItem(label, code)
        self.subtitle_language.setCurrentIndex(max(0, self.subtitle_language.findData(
            self.settings.get("subtitle_language", "auto"))))
        self.subtitle_language.currentIndexChanged.connect(
            lambda _: self.settings.set("subtitle_language", self.subtitle_language.currentData()))
        form.addRow("&Lingua dei sottotitoli", self.subtitle_language)
        self.backend = QComboBox()
        self.backend.addItem("CPU", "cpu")
        for index, name, _ in nvidia_gpus():
            self.backend.addItem(f"CUDA · {name}", f"cuda:{index}")
        for index, name in vulkan_gpus():
            self.backend.addItem(f"Vulkan · {name}", f"vulkan:{index}")
        self.backend.setCurrentIndex(max(0, self.backend.findData(self.settings.get("asr_device"))))
        form.addRow("&Elaborazione", self.backend)

        self.font = QSpinBox()
        self.font.setRange(16, 72)
        self.font.setSuffix(" px")
        self.font.setValue(self.settings.get("font_size", 31))
        self.font.valueChanged.connect(self.apply_style)
        form.addRow("&Dimensione testo", self.font)
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(self.settings.get("opacity", 65))
        self.opacity_value = QLabel()
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity, 1)
        opacity_row.addWidget(self.opacity_value)
        self.opacity.setAccessibleName("Opacità sfondo")
        self.opacity.valueChanged.connect(self.apply_style)
        form.addRow("Opacità sfondo", opacity_row)

        self.pin = QCheckBox("Sempre in primo piano")
        self.pin.setChecked(self.settings.get("pinned", True))
        self.pin.toggled.connect(self.set_pinned)
        form.addRow(self.pin)
        self.title_visible = QCheckBox("Mostra barra del titolo dei sottotitoli")
        self.title_visible.setChecked(self.settings.get("show_caption_title", False))
        self.title_visible.toggled.connect(self.floating.set_title_visible)
        form.addRow(self.title_visible)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.start_button = QPushButton("&Avvia")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.toggle)
        show = QPushButton("&Mostra finestra")
        show.clicked.connect(self.floating.show)
        preview = QPushButton("&Prova sottotitoli")
        preview.clicked.connect(self.show_preview)
        for button in (self.start_button, show, preview):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.status = QLabel("Scegli tutte le applicazioni o una singola applicazione.")
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

    def setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("SubtitleForEveryone")
        self.tray_menu = QMenu(self)
        self.tray_menu.addAction("Apri SubtitleForEveryone", self.restore_controls)
        self.tray_toggle = self.tray_menu.addAction("Avvia trascrizione", self.toggle)
        self.tray_menu.addAction("Mostra / nascondi sottotitoli", self.toggle_floating)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction("Esci", self.quit_from_tray)
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
        self.source.addItem("Tutto l’audio delle app", {"kind": "system"})
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
        size, opacity = self.font.value(), self.opacity.value()
        self.opacity_value.setText(f"{opacity}%")
        self.floating.apply_style(size, opacity)

    def set_pinned(self, pinned):
        self.floating.set_pinned(pinned)

    def show_preview(self):
        self.preview_until = monotonic() + 5
        self.refresh_caption()
        self.floating.show()

    def refresh_caption(self):
        text = "Questa è un’anteprima dei sottotitoli." if monotonic() < self.preview_until else self.caption.read(6)
        if self.floating.caption.text() != text:
            self.floating.caption.setText(text)
        preview = text or ("In attesa del parlato…" if self.worker else "Avvia la trascrizione per vedere qui i sottotitoli.")
        if self.monitor_text.text() != preview:
            self.monitor_text.setText(preview)
        self.audio_meter.set_level(self.captures.input_level() if self.worker else 0.0)

    def toggle(self):
        if self.worker:
            self.stop()
            return
        if self.previous_worker and self.previous_worker.is_alive():
            self.status.setText("Whisper sta terminando la sessione precedente. Attendi qualche secondo.")
            return
        self.previous_worker = None
        name = self.source.currentText().strip()
        index = self.source.findText(name)
        source = self.source.itemData(index) if index >= 0 else None
        if source is None:
            if not name or not name.lower().endswith(".exe") or any(c in name for c in "/\\:"):
                self.status.setText("Seleziona tutto l’audio o inserisci il nome di un processo .exe.")
                return
            source = {"kind": "process", "process": name}

        self.settings.set("audio_source", name)
        self.settings.set("sources", [dict(source, id="input", name=name, enabled=True)])
        self.settings.set("asr_model", self.model.currentText())
        self.settings.set("asr_device", self.backend.currentData())
        clips = LiveClipQueue(maxsize=4)
        self.caption = Caption()
        self.preview_until = 0
        session = object()
        self.session = session
        on_detail = lambda message: self.events.detail.emit(session, message)
        self.worker = ASRWorker(self.settings, clips, self.caption, on_detail, on_state=self.events.status.emit)
        self.captures = CaptureManager(self.settings, clips, on_detail)
        self.status.setText("Preparazione del modello… Al primo utilizzo può servire un download.")
        self.detail.clear()
        self.source.setEnabled(False)
        self.model.setEnabled(False)
        self.backend.setEnabled(False)
        if self.tray:
            self.tray_toggle.setText("Metti in pausa")
        self.start_button.setText("&Pausa")
        self.floating.show()
        self.worker.start()

    def on_status(self, worker, stage):
        if worker is not self.worker:
            return
        messages = {
            "loading": "Caricamento del modello…",
            "downloading": "Download del modello in corso. Puoi lasciare aperta l’app.",
            "repairing": "Ripristino dei file del modello…",
            "translation": "Preparazione della traduzione locale…",
            "retry": "Modello non disponibile. Nuovo tentativo tra pochi secondi.",
            "ready": f"In ascolto · {worker.active_device or 'CPU'} · Whisper {worker.active_model}",
        }
        self.status.setText(messages.get(stage, stage))
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
        if self.tray:
            self.tray_toggle.setText("Avvia trascrizione")
        self.start_button.setText("&Avvia")
        self.status.setText("In pausa.")
        self.detail.clear()

    def closeEvent(self, event):
        frame = self.floating.geometry()
        for key, value in {
            "caption_geometry": [frame.x(), frame.y(), frame.width(), frame.height()],
            "font_size": self.font.value(),
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
    if sys.platform == "win32":
        from ctypes import windll
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("SubtitleForEveryone.Desktop")
    app = QApplication(sys.argv)
    app.setApplicationName("SubtitleForEveryone")
    app.setWindowIcon(product_icon())
    window = ControlWindow()
    window.show()
    return app.exec()
