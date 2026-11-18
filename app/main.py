import sys
from threading import Lock
from time import monotonic

import psutil
from PySide6.QtCore import QObject, QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QGraphicsDropShadowEffect,
    QHBoxLayout, QLabel, QPushButton, QSizeGrip, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from .audio import CaptureManager, LiveClipQueue, microphone_devices
from .engine import ASRWorker
from .settings import Settings


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
        toolbar = QHBoxLayout()
        handle = DragBar("   Sottotitoli · trascina per spostare")
        handle.setStyleSheet("background: #192431; color: white; border-radius: 7px; padding: 6px;")
        hide = QPushButton("Nascondi")
        hide.clicked.connect(self.hide)
        toolbar.addWidget(handle, 1)
        toolbar.addWidget(hide)
        layout.addLayout(toolbar)

        self.caption = QLabel()
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


class ControlWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.events = Events(self)
        self.events.status.connect(self.on_status)
        self.events.detail.connect(self.on_detail)
        self.worker = None
        self.previous_worker = None
        self.captures = None
        self.caption = Caption()
        self.preview_until = 0
        self.floating = CaptionWindow(self.settings)
        self.setWindowTitle("SubtitileForEveryone")
        self.setMinimumWidth(485)
        self.setStyleSheet("""
            QWidget { background: #111923; color: #edf4fb; font-size: 14px; }
            QLabel { background: transparent; }
            QPushButton, QComboBox, QSpinBox {
                background: #203244; color: #f0f7ff; border: 1px solid #455d75;
                border-radius: 6px; padding: 7px;
            }
            QPushButton:focus, QComboBox:focus, QSpinBox:focus { border: 2px solid #8fe1fc; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        title = QLabel("SubtitileForEveryone")
        title.setStyleSheet("font-size: 25px; font-weight: 700;")
        layout.addWidget(title)

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
        form.addRow("&Sorgente audio", sources)
        self.model = QComboBox()
        for name in ("tiny", "base", "small", "medium"):
            self.model.addItem(name)
        self.model.setCurrentText(self.settings.get("asr_model", "tiny"))
        form.addRow("&Modello Whisper", self.model)

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
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.start_button = QPushButton("&Avvia")
        self.start_button.clicked.connect(self.toggle)
        show = QPushButton("&Mostra finestra")
        show.clicked.connect(self.floating.show)
        preview = QPushButton("&Prova sottotitoli")
        preview.clicked.connect(self.show_preview)
        for button in (self.start_button, show, preview):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.status = QLabel("Scegli un microfono o il processo dell’app che riproduce l’audio.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.apply_style()
        self.floating.set_pinned(self.pin.isChecked())

        self.timer = QTimer(self, interval=100)
        self.timer.timeout.connect(self.refresh_caption)
        self.timer.start()

    def refresh_sources(self):
        previous = self.source.currentText() or self.settings.get("source_text", "")
        self.source.clear()
        self.source.addItem("Microfono predefinito", {"kind": "mic", "device": None})
        for index, name in microphone_devices():
            self.source.addItem(f"Microfono · {name}", {"kind": "mic", "device": index})
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
                self.status.setText("Seleziona un microfono o inserisci il nome di un processo .exe.")
                return
            source = {"kind": "process", "process": name}

        self.settings.set("source_text", name)
        self.settings.set("sources", [dict(source, id="input", name=name, enabled=True)])
        self.settings.set("asr_model", self.model.currentText())
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
            "retry": "Modello non disponibile. Nuovo tentativo tra pochi secondi.",
            "ready": "In ascolto. Se hai scelto un’app, avvia la riproduzione audio.",
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
        self.start_button.setText("&Avvia")
        self.status.setText("In pausa.")
        self.detail.clear()

    def closeEvent(self, event):
        self.stop()
        frame = self.floating.geometry()
        for key, value in {
            "caption_geometry": [frame.x(), frame.y(), frame.width(), frame.height()],
            "font_size": self.font.value(),
            "opacity": self.opacity.value(),
            "pinned": self.pin.isChecked(),
        }.items():
            self.settings.set(key, value)
        self.floating.close()
        event.accept()


def main():
    if sys.platform == "win32":
        from ctypes import windll
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("SubtitileForEveryone.Desktop")
    app = QApplication(sys.argv)
    app.setApplicationName("SubtitileForEveryone")
    window = ControlWindow()
    window.show()
    return app.exec()
