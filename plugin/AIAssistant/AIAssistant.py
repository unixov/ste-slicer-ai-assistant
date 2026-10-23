import os

from PyQt5.QtCore import QObject, QThread, pyqtProperty, pyqtSignal, pyqtSlot

from UM.Application import Application
from steslicer.Stages.SteSlicerStage import SteSlicerStage

from .config.llm_client import LlmError, complete


class LlmWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, messages, parent=None):
        super().__init__(parent)
        self._messages = messages

    @pyqtSlot()
    def run(self):
        try:
            self.finished.emit(complete(self._messages))
        except LlmError as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit("Непредвиденная ошибка LLM: " + str(error))


class AssistantBridge(QObject):
    messageReceived = pyqtSignal(str)
    replyReady = pyqtSignal(str)
    requestStarted = pyqtSignal()
    requestFailed = pyqtSignal(str)
    statusChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status = "Готов к работе"
        self._history = [
            {
                "role": "system",
                "content": (
                    "Ты ассистент по настройке печати в STE Slicer. "
                    "Пока только отвечай текстом и не утверждай, что изменил сцену."
                ),
            }
        ]
        self._thread = None
        self._worker = None

    @pyqtProperty(str, notify=statusChanged)
    def status(self):
        return self._status

    def _set_status(self, value):
        self._status = value
        self.statusChanged.emit()

    @pyqtSlot(str)
    def sendMessage(self, text):
        text = (text or "").strip()
        if not text or self._thread is not None:
            return

        self._history.append({"role": "user", "content": text})
        self.messageReceived.emit(text)
        self.requestStarted.emit()
        self._set_status("Запрос к LLM...")

        self._thread = QThread(self)
        self._worker = LlmWorker(list(self._history))
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_request)
        self._thread.start()

    @pyqtSlot(str)
    def _on_finished(self, reply):
        self._history.append({"role": "assistant", "content": reply})
        self._set_status("Готов к работе")
        self.replyReady.emit(reply)

    @pyqtSlot(str)
    def _on_failed(self, error):
        self._set_status("Ошибка запроса")
        self.requestFailed.emit(error)

    @pyqtSlot()
    def _cleanup_request(self):
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None


class AssistantStage(SteSlicerStage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = AssistantBridge(self)
        self._qml_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "ui",
            "AssistantSidebar.qml",
        )
        Application.getInstance().engineCreatedSignal.connect(self._engineCreated)

    def _engineCreated(self):
        application = Application.getInstance()
        engine = getattr(application, "qmlEngine", None)
        if callable(engine):
            qml_engine = engine()
            if qml_engine is not None:
                qml_engine.rootContext().setContextProperty(
                    "aiAssistantBridge", self._bridge
                )

        self.addDisplayComponent("sidebar", self._qml_path)
