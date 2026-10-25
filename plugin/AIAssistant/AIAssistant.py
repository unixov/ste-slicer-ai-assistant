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
from UM.Logger import Logger
from steslicer.Stages.SteSlicerStage import SteSlicerStage

from .config.llm_client import LlmError, complete
from .mcp.registry import ToolRegistry
from .mcp.server import McpServer
from .mcp.slicer_tools import SlicerTools


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_BASE = """\
Ты — Aurora, дружелюбный ИИ-помощник для 3D/5D-печати в STE Slicer. \
Ты помогаешь как новичкам, так и опытным пользователям.

Язык: ТОЛЬКО русский. БЕЗ Markdown-символов (* # ` | и т.д.). \
Пиши как живой человек — просто, понятно, дружелюбно.

ПОЛНЫЙ АВТОМАТИЧЕСКИЙ АЛГОРИТМ — выполняй ВСЕ 5 шагов без остановок:
1. Вызови scene.list_objects — получи ID объекта.
2. Вызови scene.recommend_print_mode — получи режим (3D/5D), материал, вес.
3. Вызови scene.get_structural_analysis — получи зоны напряжений и recommended_settings.
4. Вызови settings.apply_print_profile с этими параметрами:
   - material и mode из шага 2
   - infill = infill_sparse_density из recommended_settings шага 3
   - wall_line_count из recommended_settings шага 3
   - layer_height из recommended_settings шага 3
5. Вызови backend.start_slicing — запусти слайсинг автоматически.
6. Дай финальный ответ: что нашёл, что настроил, что слайсинг запущен.

ПРАВИЛА (не нарушай):
- settings.apply, settings.apply_print_profile и backend.start_slicing выполняются БЕЗ подтверждения.
- Не вызывай один инструмент дважды за один диалог.
- Не останавливайся между шагами — выполняй всю цепочку за одно обращение к LLM.
- Если объектов нет — напиши "Загрузите модель, и я всё настрою и запущу автоматически."
- Всегда указывай конкретные числа: температуру, скорость, % заполнения.

СТИЛЬ ФИНАЛЬНОГО ОТВЕТА (после слайсинга):
- Начни: "Готово! Вот что я сделал:"
- Размеры и примерный вес детали.
- Режим печати (3D или 5D) и ЗАЧЕМ — одним предложением.
- Материал и температура.
- Заполнение % и число стенок — с пояснением "это значит...".
- Последняя строка: "Слайсинг запущен — можете нажать кнопку Печать."
"""


# ---------------------------------------------------------------------------
# Thread helpers
# ---------------------------------------------------------------------------

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

    def __init__(self, messages, tools=None, force_text=False, parent=None):
        super().__init__(parent)
        self._messages = messages
        self._tools = tools or []
        self._force_text = force_text

    @pyqtSlot()
    def run(self):
        try:
            content, tool_calls = complete(
                self._messages,
                tools=self._tools,
                force_text=self._force_text,
            )
            self.finished.emit(content, tool_calls)
        except LlmError as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit("Непредвиденная ошибка LLM: " + str(error))


# ---------------------------------------------------------------------------
# AssistantBridge
# ---------------------------------------------------------------------------

class AssistantBridge(QObject):
    messageReceived = pyqtSignal(str)
    replyReady = pyqtSignal()
    requestStarted = pyqtSignal()
    requestFailed = pyqtSignal()
    statusChanged = pyqtSignal()
    requestStateChanged = pyqtSignal()
    confirmationChanged = pyqtSignal()
    lastReplyChanged = pyqtSignal()
    lastErrorChanged = pyqtSignal()
    modelLoadedSignal = pyqtSignal()
    structuralAnalysisReady = pyqtSignal()
    settingsApplied = pyqtSignal()
    printModeReady = pyqtSignal()
    _main_thread_request = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status = "Готов к работе"
        self._last_reply = ""
        self._last_error = ""
        self._known_mesh_ids = set()
        self._pending_auto_analysis = False
        self._history = [{"role": "system", "content": _SYSTEM_PROMPT_BASE}]
        self._thread = None
        self._worker = None
        self._mcp_server = None
        self._slicer_tools = None
        self._main_thread_request.connect(
            self._handle_main_thread_request,
            Qt.QueuedConnection,
        )
        self._pending_tool_request = False
        self._pending_tool_calls = []
        self._pending_confirmation_call = None
        self._confirmation_pending = False
        self._confirmation_tool = ""
        self._confirmation_arguments = ""
        self._tool_rounds = 0
        # Structural analysis result cache (for QML access)
        self._last_structural_result = {}
        # Applied settings cache (for QML display)
        self._last_applied_settings = []
        # Print mode recommendation cache (for QML display)
        self._last_print_mode_result = {}

    # ------------------------------------------------------------------ #
    # Main-thread dispatcher                                               #
    # ------------------------------------------------------------------ #

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
                        "Тайм-аут: операция уже выполняется; результат неизвестен."
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

    # ------------------------------------------------------------------ #
    # MCP / tool registration                                              #
    # ------------------------------------------------------------------ #

    def configure_mcp(self, application):
        self._slicer_tools = SlicerTools(
            application,
            dispatch=self._dispatch_slicer_callback,
        )
        registry = ToolRegistry()

        # ---- read-only scene tools ----
        registry.register(
            "scene.list_objects",
            "List mesh objects currently loaded in STE Slicer with geometry info.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            self._slicer_tools.list_scene_objects,
        )
        registry.register(
            "scene.analyse_object",
            "Analyse the geometry of a specific mesh object: vertex/face count, "
            "bounding box, aspect ratios and print warnings.",
            {
                "type": "object",
                "properties": {
                    "object_id": {"type": ["string", "number"]},
                },
                "required": ["object_id"],
                "additionalProperties": False,
            },
            self._slicer_tools.analyse_object,
        )
        registry.register(
            "scene.get_selection",
            "List mesh objects currently selected in STE Slicer.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            self._slicer_tools.get_selection,
        )

        # ---- KILLER FEATURE: structural analysis ----
        registry.register(
            "scene.get_structural_analysis",
            (
                "Perform heuristic structural zone analysis on a mesh object. "
                "Returns load profile (column/bracket/plate/general), stress zones with "
                "risk scores 0-10, optimal print orientation recommendation, "
                "adaptive infill densities for high/low stress zones, and concrete "
                "slicer settings (infill %, pattern, wall count, layer height, print mode). "
                "Use this FIRST whenever the user mentions load, strength, stress or durability."
            ),
            {
                "type": "object",
                "properties": {
                    "object_id": {"type": ["string", "number"]},
                },
                "required": ["object_id"],
                "additionalProperties": False,
            },
            self._slicer_tools.get_structural_analysis,
        )

        # ---- mutating scene tools ----
        registry.register(
            "scene.arrange_all",
            "Arrange models on the active build plate.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            self._slicer_tools.arrange_scene,
            requires_confirmation=True,
        )
        registry.register(
            "scene.move_object",
            "Move one mesh object to an absolute world position in millimeters.",
            {
                "type": "object",
                "properties": {
                    "object_id": {"type": ["string", "number"]},
                    "position": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "z": {"type": "number"},
                        },
                        "required": ["x", "y", "z"],
                        "additionalProperties": False,
                    },
                },
                "required": ["object_id", "position"],
                "additionalProperties": False,
            },
            self._slicer_tools.move_object,
            requires_confirmation=True,
        )
        registry.register(
            "scene.rotate_object",
            (
                "Rotate a mesh object around a world axis by the given angle in degrees. "
                "Use this to apply the orientation recommended by scene.get_structural_analysis."
            ),
            {
                "type": "object",
                "properties": {
                    "object_id": {"type": ["string", "number"]},
                    "axis": {"type": "string", "enum": ["x", "y", "z"]},
                    "angle_deg": {"type": "number"},
                },
                "required": ["object_id", "axis", "angle_deg"],
                "additionalProperties": False,
            },
            self._slicer_tools.rotate_object,
        )

        # ---- print mode recommendation ----
        registry.register(
            "scene.recommend_print_mode",
            (
                "Analyse a mesh object's geometry and automatically recommend: "
                "print mode (3D or 5D), best material (PLA/PETG/ABS/TPU/NYLON), "
                "estimated volume and mass in grams, complexity level, and a "
                "beginner-friendly explanation in Russian. "
                "Call this FIRST for every loaded model before applying settings."
            ),
            {
                "type": "object",
                "properties": {
                    "object_id": {"type": ["string", "number"]},
                },
                "required": ["object_id"],
                "additionalProperties": False,
            },
            self._slicer_tools.get_print_mode_recommendation,
        )

        # ---- settings tools ----
        registry.register(
            "settings.get",
            "Read selected print settings and the active machine.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            self._slicer_tools.get_settings,
        )
        registry.register(
            "settings.apply",
            (
                "Apply a set of print settings to the active machine stack. "
                "Pass a dict of {setting_key: value}. "
                "Supported keys: printing_mode, layer_height, infill_sparse_density, "
                "infill_pattern, wall_line_count, support_enable, support_type, "
                "material_print_temperature, print_speed, retraction_enable, "
                "retraction_amount, adhesion_type. "
                "Use recommended_settings from scene.get_structural_analysis directly."
            ),
            {
                "type": "object",
                "properties": {
                    "settings": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
                "required": ["settings"],
                "additionalProperties": False,
            },
            self._slicer_tools.apply_settings,
        )
        registry.register(
            "settings.apply_print_profile",
            (
                "Apply a complete print profile in one call: material, temperature, "
                "speed, layer height, infill %, supports on/off, print mode (3D or 5D). "
                "Use the recommended_mode from scene.recommend_print_mode and "
                "infill/wall/layer values from scene.get_structural_analysis. "
                "No confirmation needed — applies immediately."
            ),
            {
                "type": "object",
                "properties": {
                    "material":     {"type": "string",  "description": "PLA | PETG | ABS | TPU | NYLON"},
                    "layer_height": {"type": "number",  "description": "Layer height mm (e.g. 0.2)"},
                    "print_speed":  {"type": "integer", "description": "Print speed mm/s"},
                    "temperature":  {"type": "integer", "description": "Nozzle temperature °C"},
                    "infill":       {"type": "integer", "description": "Infill density 0-100 %"},
                    "supports":     {"type": "boolean", "description": "Enable support structures"},
                    "mode":         {"type": "string",  "enum": ["3D", "5D"], "description": "Print mode"},
                },
                "required": ["material"],
                "additionalProperties": False,
            },
            self._slicer_tools.apply_print_profile,
        )

        # ---- backend tools ----
        registry.register(
            "backend.get_status",
            "Read the active slicing backend and its last observed state.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            self._slicer_tools.get_backend_status,
        )
        registry.register(
            "backend.start_slicing",
            "Start asynchronous re-slicing with the active STE Slicer backend.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            self._slicer_tools.start_slicing,
        )

        # ---- export tools ----
        registry.register(
            "export.scene",
            "Export the current mesh scene to a new .gcode or .3mf file at an explicit path.",
            {
                "type": "object",
                "properties": {
                    "file_name": {"type": "string"},
                    "file_format": {"type": "string", "enum": ["gcode", "3mf"]},
                },
                "required": ["file_name", "file_format"],
                "additionalProperties": False,
            },
            self._slicer_tools.export_scene,
            requires_confirmation=True,
        )
        registry.register(
            "export.get_status",
            "Read the asynchronous status of the latest scene export.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            self._slicer_tools.get_export_status,
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

    def _extract_tool_result(self, mcp_response):
        try:
            text = mcp_response["result"]["content"][0]["text"]
            return json.loads(text)
        except Exception:
            return mcp_response

    def _scene_context(self):
        if self._mcp_server is None:
            return "Состояние слайсера пока недоступно."
        try:
            objects = self._extract_tool_result(self._mcp_server.handle(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "scene.list_objects"}}
            ))
            settings = self._extract_tool_result(self._mcp_server.handle(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "settings.get"}}
            ))
            backend = self._extract_tool_result(self._mcp_server.handle(
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "backend.get_status"}}
            ))
            return "Текущее состояние STE Slicer:\n" + json.dumps(
                {"objects": objects, "settings": settings, "backend": backend},
                ensure_ascii=False,
                indent=2,
            )
        except Exception as exc:
            Logger.log("w", "AI Assistant: _scene_context failed: %s", exc)
            return "Состояние слайсера временно недоступно."

    # ------------------------------------------------------------------ #
    # Qt properties                                                        #
    # ------------------------------------------------------------------ #

    @pyqtProperty(str, notify=statusChanged)
    def status(self):
        return self._status

    @pyqtProperty(str, notify=lastReplyChanged)
    def lastReply(self):
        return self._last_reply

    @pyqtProperty(str, notify=lastErrorChanged)
    def lastError(self):
        return self._last_error

    @pyqtProperty(bool, notify=requestStateChanged)
    def busy(self):
        return self._thread is not None or self._confirmation_pending

    @pyqtProperty(bool, notify=confirmationChanged)
    def confirmationPending(self):
        return self._confirmation_pending

    @pyqtProperty(str, notify=confirmationChanged)
    def confirmationTool(self):
        return self._confirmation_tool

    @pyqtProperty(str, notify=confirmationChanged)
    def confirmationArguments(self):
        return self._confirmation_arguments

    @pyqtProperty(str, notify=structuralAnalysisReady)
    def lastStructuralResult(self):
        """JSON-строка последнего структурного анализа для QML."""
        return json.dumps(self._last_structural_result, ensure_ascii=False)

    @pyqtProperty(str, notify=settingsApplied)
    def lastAppliedSettings(self):
        """JSON-строка списка применённых настроек для QML."""
        return json.dumps(self._last_applied_settings, ensure_ascii=False)

    @pyqtProperty(str, notify=printModeReady)
    def lastPrintModeResult(self):
        """JSON-строка последней рекомендации режима печати для QML."""
        return json.dumps(self._last_print_mode_result, ensure_ascii=False)

    def _set_status(self, value):
        self._status = value
        self.statusChanged.emit()

    # ------------------------------------------------------------------ #
    # Message flow                                                         #
    # ------------------------------------------------------------------ #

    @pyqtSlot()
    def triggerFullSetup(self):
        """
        One-click full setup: analyse → apply settings → start slicing.
        Called from the big "Настроить и начать" button in QML.
        """
        if self.busy:
            return
        prompt = (
            "Выполни полную автоматическую настройку и запусти слайсинг: "
            "определи режим печати (3D или 5D), подбери материал, "
            "выполни структурный анализ, примени все настройки и запусти слайсинг. "
            "Объясни что сделал простыми словами."
        )
        self.sendMessage(prompt)

    @pyqtSlot(str)
    def sendMessage(self, text):
        text = (text or "").strip()
        if not text:
            return
        if self.busy:
            Logger.log("d", "AI Assistant: sendMessage skipped (busy): %s", text[:60])
            return

        self._history.append({"role": "user", "content": text})
        # Refresh system prompt with current scene state each time
        self._history[0]["content"] = (
            _SYSTEM_PROMPT_BASE + "\n\n" + self._scene_context()
        )
        self.messageReceived.emit(text)
        self.requestStarted.emit()
        self._set_status("Запрос к LLM...")
        self._tool_rounds = 0
        self._start_llm_request()

    def _start_llm_request(self):
        force_text = self._tool_rounds >= 6
        self._thread = QThread(self)
        self._worker = LlmWorker(
            list(self._history),
            self._openai_tools(),
            force_text=force_text,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._cleanup_request)
        self._thread.start()
        self.requestStateChanged.emit()

    @pyqtSlot(str, object)
    def _on_finished(self, reply, tool_calls):
        Logger.log(
            "d",
            "AI Assistant: LLM response received (content_length=%s, tool_calls=%s)",
            len(reply or ""),
            len(tool_calls or []),
        )
        if tool_calls:
            if self._tool_rounds >= 8:
                self._set_status("Слишком много последовательных действий")
                self._last_error = "Остановлено: превышен лимит вызовов инструментов."
                self.lastErrorChanged.emit()
                self.requestFailed.emit()
                self._thread.quit()
                return
            self._tool_rounds += 1
            assistant_message = {
                "role": "assistant",
                "content": reply or None,
                "tool_calls": tool_calls,
            }
            self._history.append(assistant_message)
            self._pending_tool_calls = list(tool_calls)
            if self._execute_pending_tool_calls():
                self._pending_tool_request = True
            self._thread.quit()
            return

        display_reply = (reply or "").strip()
        if not display_reply:
            display_reply = (
                "LLM завершила запрос без текстового ответа. "
                "Проверь модель и формат ответа провайдера."
            )
        self._history.append({"role": "assistant", "content": display_reply})
        self._thread.quit()
        self._set_status("Готов к работе")
        self._last_reply = display_reply
        self.lastReplyChanged.emit()
        self.replyReady.emit()

    # ------------------------------------------------------------------ #
    # Tool call helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_tool_arguments(call):
        function = call.get("function", {})
        raw_arguments = function.get("arguments", "{}")
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        except (TypeError, ValueError):
            arguments = {}
        return arguments if isinstance(arguments, dict) else {}

    def _call_tool(self, call, confirmed=False):
        function = call.get("function", {})
        name = function.get("name", "")
        arguments = self._parse_tool_arguments(call)
        response = self._mcp_server.handle({
            "jsonrpc": "2.0",
            "id": call.get("id"),
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
                "confirmed": confirmed,
            },
        })
        # Cache print mode recommendation for QML
        if name == "scene.recommend_print_mode" and not self._requires_confirmation(response):
            try:
                self._last_print_mode_result = self._extract_tool_result(response)
                self.printModeReady.emit()
            except Exception:
                pass
        # Cache structural analysis result for QML
        if name == "scene.get_structural_analysis" and not self._requires_confirmation(response):
            try:
                self._last_structural_result = self._extract_tool_result(response)
                self.structuralAnalysisReady.emit()
            except Exception:
                pass
        # Cache applied settings (both settings.apply and settings.apply_print_profile)
        if name in ("settings.apply", "settings.apply_print_profile") and not self._requires_confirmation(response):
            try:
                res = self._extract_tool_result(response)
                applied = res.get("applied", [])
                if applied:
                    self._last_applied_settings = applied
                    self.settingsApplied.emit()
                    Logger.log(
                        "i",
                        "AI Assistant: settings applied count=%d",
                        len(applied),
                    )
            except Exception:
                pass
        return response

    @staticmethod
    def _requires_confirmation(response):
        try:
            text = response["result"]["content"][0]["text"]
            return bool(json.loads(text).get("requires_confirmation"))
        except (KeyError, IndexError, TypeError, ValueError):
            return False

    def _append_tool_result(self, call, response):
        self._history.append({
            "role": "tool",
            "tool_call_id": call.get("id", ""),
            "content": json.dumps(response, ensure_ascii=False),
        })

    def _show_confirmation(self, call):
        function = call.get("function", {})
        self._pending_confirmation_call = call
        self._confirmation_tool = function.get("name", "")
        self._confirmation_arguments = json.dumps(
            self._parse_tool_arguments(call),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        self._confirmation_pending = True
        self._set_status("Ожидание подтверждения")
        self.confirmationChanged.emit()
        self.requestStateChanged.emit()

    def _execute_pending_tool_calls(self):
        while self._pending_tool_calls:
            call = self._pending_tool_calls.pop(0)
            response = self._call_tool(call)
            if self._requires_confirmation(response):
                self._show_confirmation(call)
                return False
            self._append_tool_result(call, response)
        return True

    def _finish_confirmation(self):
        self._pending_confirmation_call = None
        self._confirmation_pending = False
        self._confirmation_tool = ""
        self._confirmation_arguments = ""
        self.confirmationChanged.emit()
        self.requestStateChanged.emit()

    @pyqtSlot()
    def confirmAction(self):
        call = self._pending_confirmation_call
        if call is None:
            return
        response = self._call_tool(call, confirmed=True)
        self._append_tool_result(call, response)
        self._finish_confirmation()
        self._continue_after_confirmation()

    def _continue_after_confirmation(self):
        if not self._execute_pending_tool_calls():
            return
        if self._thread is None:
            self._pending_tool_request = False
            self._start_llm_request()
        else:
            self._pending_tool_request = True

    @pyqtSlot()
    def cancelAction(self):
        call = self._pending_confirmation_call
        if call is None:
            return
        self._append_tool_result(
            call,
            {
                "jsonrpc": "2.0",
                "id": call.get("id"),
                "result": {
                    "content": [{
                        "type": "text",
                        "text": json.dumps(
                            {"cancelled": True,
                             "message": "Операция отменена пользователем."},
                            ensure_ascii=False,
                        ),
                    }],
                },
            },
        )
        self._finish_confirmation()
        self._continue_after_confirmation()

    @pyqtSlot(str)
    def _on_failed(self, error):
        safe_error = str(error).strip() or "неизвестная ошибка"
        self._set_status("Ошибка запроса: " + safe_error)
        Logger.log("e", "AI Assistant: LLM request failed: %s", safe_error)
        self._last_error = safe_error
        self.lastErrorChanged.emit()
        self.requestFailed.emit()
        if self._thread is not None:
            self._thread.quit()

    @pyqtSlot()
    def _cleanup_request(self):
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self.requestStateChanged.emit()
        if self._pending_tool_request:
            self._pending_tool_request = False
            self._start_llm_request()

    # ------------------------------------------------------------------ #
    # Auto-analysis on model load                                          #
    # ------------------------------------------------------------------ #

    @pyqtSlot(object)
    def onSceneChanged(self, node=None):
        if node is not None:
            has_mesh = (
                callable(getattr(node, "getMeshData", None))
                and node.getMeshData() is not None
            )
            if not has_mesh:
                return

        if self._mcp_server is None:
            return

        try:
            result = self._mcp_server.handle({
                "jsonrpc": "2.0",
                "id": 0,
                "method": "tools/call",
                "params": {"name": "scene.list_objects"},
            })
            objects = self._extract_tool_result(result).get("objects", [])

            current_ids = set(str(o.get("id", "")) for o in objects if o.get("id"))
            new_ids = current_ids - self._known_mesh_ids
            self._known_mesh_ids = current_ids

            if not new_ids:
                return

            new_objects = [o for o in objects if str(o.get("id", "")) in new_ids]
            Logger.log("d", "AI Assistant: new mesh object(s) detected: %s", new_ids)

            self.modelLoadedSignal.emit()

            if self.busy:
                Logger.log("d", "AI Assistant: busy, skipping auto-analysis")
                return

            desc = json.dumps(new_objects, ensure_ascii=False, indent=2)
            prompt = (
                "Пользователь загрузил новые объекты в STE Slicer:\n" + desc + "\n\n"
                "Выполни структурный анализ (scene.get_structural_analysis) для первого объекта. "
                "Затем кратко объясни профиль нагружения, назови зоны риска и предложи "
                "конкретные настройки для оптимальной прочности при минимальном расходе пластика."
            )
            self.sendMessage(prompt)

        except Exception as exc:
            Logger.log("w", "AI Assistant: onSceneChanged error: %s", exc)


# ---------------------------------------------------------------------------
# AssistantStage
# ---------------------------------------------------------------------------

class AssistantStage(SteSlicerStage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = AssistantBridge(self)
        self._qml_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "ui",
            "AssistantSidebar.qml",
        )
        app = Application.getInstance()
        self._bridge.configure_mcp(app)
        app.engineCreatedSignal.connect(self._engineCreated)
        try:
            scene = app.getController().getScene()
            scene.sceneChanged.connect(self._bridge.onSceneChanged)
            Logger.log("d", "AI Assistant: connected sceneChanged for auto-analysis")
        except Exception as exc:
            Logger.log("w", "AI Assistant: could not connect sceneChanged: %s", exc)

    def _engineCreated(self):
        application = Application.getInstance()
        qml_engine = getattr(application, "_qml_engine", None)
        if qml_engine is None:
            engine_getter = getattr(application, "qmlEngine", None)
            if callable(engine_getter):
                qml_engine = engine_getter()

        if qml_engine is None:
            Logger.log(
                "e",
                "AI Assistant: QML engine is unavailable; bridge was not registered.",
            )
        else:
            try:
                qml_engine.rootContext().setContextProperty(
                    "aiAssistantBridge", self._bridge
                )
                Logger.log(
                    "i",
                    "AI Assistant: bridge registered, loading sidebar from %s",
                    self._qml_path,
                )
            except Exception as error:
                Logger.log(
                    "e",
                    "AI Assistant: failed to register QML bridge: %s",
                    error,
                )

        self.addDisplayComponent("sidebar", self._qml_path)
