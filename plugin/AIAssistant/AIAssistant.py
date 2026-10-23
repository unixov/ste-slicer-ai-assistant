import json
import os
import threading

from PyQt5.QtCore import (
    QObject,
    QThread,
    Qt,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)

from UM.Application import Application
from steslicer.Stages.SteSlicerStage import SteSlicerStage

from .config.llm_client import LlmError, complete
from .mcp.registry import ToolRegistry
from .mcp.server import McpServer
from .mcp.slicer_tools import SlicerTools


class _MainThreadRequest(object):
    def __init__(self, callback):
        self.callback = callback
        self.event = threading.Event()
        self.lock = threading.Lock()
        self.started = False
        self.cancelled = False
        self.result = None
        self.error = None


class LlmWorker(QObject):
    finished = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(self, messages, tools=None, parent=None):
        super().__init__(parent)
        self._messages = messages
        self._tools = tools or []

    @pyqtSlot()
    def run(self):
        try:
            content, tool_calls = complete(self._messages, tools=self._tools)
            self.finished.emit(content, tool_calls)
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
    _main_thread_request = pyqtSignal(object)

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
        self._mcp_server = None
        self._slicer_tools = None
        self._main_thread_request.connect(
            self._handle_main_thread_request,
            Qt.QueuedConnection,
        )
        self._pending_tool_request = False
        self._tool_rounds = 0

    def _dispatch_slicer_callback(self, callback):
        if QThread.currentThread() == self.thread():
            return callback()

        request = _MainThreadRequest(callback)
        self._main_thread_request.emit(request)
        if not request.event.wait(30):
            with request.lock:
                if not request.event.is_set():
                    if not request.started:
                        request.cancelled = True
                        raise RuntimeError(
                            "Тайм-аут: операция отменена до запуска."
                        )
                    raise RuntimeError(
                        "Тайм-аут: операция уже выполняется; результат неизвестен. "
                        "Не повторяйте её автоматически."
                    )
        if request.error is not None:
            raise request.error
        return request.result

    @pyqtSlot(object)
    def _handle_main_thread_request(self, request):
        with request.lock:
            if request.cancelled:
                request.event.set()
                return
            request.started = True
        try:
            request.result = request.callback()
        except Exception as error:
            request.error = error
        finally:
            request.event.set()

    def configure_mcp(self, application):
        self._slicer_tools = SlicerTools(
            application,
            dispatch=self._dispatch_slicer_callback,
        )
        registry = ToolRegistry()
        registry.register(
            "scene.list_objects",
            "List mesh objects currently loaded in STE Slicer.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            self._slicer_tools.list_scene_objects,
        )
        registry.register(
            "settings.get",
            "Read selected print settings and the active machine.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            self._slicer_tools.get_settings,
        )
        registry.register(
            "scene.get_selection",
            "List mesh objects currently selected in STE Slicer.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            self._slicer_tools.get_selection,
        )
        registry.register(
            "scene.arrange_all",
            "Arrange models on the active build plate.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            self._slicer_tools.arrange_scene,
            requires_confirmation=True,
        )
        self._mcp_server = McpServer(registry)

    def _openai_tools(self):
        if self._mcp_server is None:
            return []
        tools = []
        for item in self._mcp_server.list_tools():
            tools.append({
                "type": "function",
                "function": {
                    "name": item["name"],
                    "description": item["description"],
                    "parameters": item["inputSchema"],
                },
            })
        return tools

    def _scene_context(self):
        if self._mcp_server is None:
            return "Состояние слайсера пока недоступно."
        objects = self._mcp_server.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "scene.list_objects"}}
        )
        settings = self._mcp_server.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "settings.get"}}
        )
        selection = self._mcp_server.handle(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "scene.get_selection"}}
        )
        return "Текущее состояние STE Slicer:\n" + json.dumps(
            {
                "objects": objects,
                "selection": selection,
                "settings": settings,
            },
            ensure_ascii=False,
        )

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
        self._history[0]["content"] = (
            "Ты ассистент по настройке печати в STE Slicer. "
            "Пока не утверждай, что изменил сцену или выполнил расчёт прочности.\n\n"
            + self._scene_context()
        )
        self.messageReceived.emit(text)
        self.requestStarted.emit()
        self._set_status("Запрос к LLM...")
        self._tool_rounds = 0
        self._start_llm_request()

    def _start_llm_request(self):
        self._thread = QThread(self)
        self._worker = LlmWorker(list(self._history), self._openai_tools())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._cleanup_request)
        self._thread.start()

    @pyqtSlot(str, object)
    def _on_finished(self, reply, tool_calls):
        if tool_calls:
            if self._tool_rounds >= 4:
                self._set_status("Слишком много последовательных действий")
                self.requestFailed.emit(
                    "Остановлено: превышен лимит последовательных вызовов инструментов."
                )
                self._thread.quit()
                return
            self._tool_rounds += 1
            assistant_message = {"role": "assistant", "content": reply or None, "tool_calls": tool_calls}
            self._history.append(assistant_message)
            self._execute_tool_calls(tool_calls)
            self._pending_tool_request = True
            self._thread.quit()
            return

        self._history.append({"role": "assistant", "content": reply or ""})
        self._thread.quit()
        self._set_status("Готов к работе")
        self.replyReady.emit(reply or "")

    def _execute_tool_calls(self, tool_calls):
        for call in tool_calls:
            function = call.get("function", {})
            name = function.get("name", "")
            raw_arguments = function.get("arguments", "{}")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except (TypeError, ValueError):
                arguments = {}
            result = self._mcp_server.handle({
                "jsonrpc": "2.0",
                "id": call.get("id"),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            })
            self._history.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": json.dumps(result, ensure_ascii=False),
            })

    @pyqtSlot(str)
    def _on_failed(self, error):
        self._set_status("Ошибка запроса")
        self.requestFailed.emit(error)
        if self._thread is not None:
            self._thread.quit()

    @pyqtSlot()
    def _cleanup_request(self):
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        if self._pending_tool_request:
            self._pending_tool_request = False
            self._start_llm_request()


class AssistantStage(SteSlicerStage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = AssistantBridge(self)
        self._qml_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "ui",
            "AssistantSidebar.qml",
        )
        self._bridge.configure_mcp(Application.getInstance())
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
