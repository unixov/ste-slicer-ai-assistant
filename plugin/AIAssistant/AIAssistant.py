import os

from PyQt5.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from UM.Application import Application
from steslicer.Stages.SteSlicerStage import SteSlicerStage


class AssistantBridge(QObject):
    messageReceived = pyqtSignal(str)
    replyReady = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status = "Готов к работе"

    @pyqtProperty(str, notify=messageReceived)
    def status(self):
        return self._status

    @pyqtSlot(str)
    def sendMessage(self, text):
        text = (text or "").strip()
        if not text:
            return
        self._status = "Сообщение получено"
        self.messageReceived.emit(text)
        self.replyReady.emit(
            "Запрос принят. Подключение LLM и инструменты STE Slicer будут добавлены следующим этапом."
        )


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
