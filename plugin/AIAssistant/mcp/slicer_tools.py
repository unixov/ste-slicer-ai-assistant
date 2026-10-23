import math

from UM.Math.Vector import Vector
from UM.Operations.TranslateOperation import TranslateOperation
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.Scene.Selection import Selection


class SlicerTools(object):
    def __init__(self, application, dispatch=None):
        self._application = application
        self._dispatch = dispatch or (lambda callback: callback())
        self._observed_backend = None
        self._backend_state = None
        self._backend_progress = None
        self._exporter = None

    def list_scene_objects(self, arguments):
        return self._dispatch(self._list_scene_objects)

    def _list_scene_objects(self):
        scene = self._application.getController().getScene()
        objects = []
        for node in DepthFirstIterator(scene.getRoot()):
            item = self._describe_mesh_node(node)
            if item is not None:
                objects.append(item)
        return {"objects": objects}

    def get_selection(self, arguments):
        return self._dispatch(self._get_selection)

    def _get_selection(self):
        objects = []
        for node in Selection.getAllSelectedObjects():
            item = self._describe_mesh_node(node)
            if item is not None:
                objects.append(item)
        return {"objects": objects}

    @staticmethod
    def _describe_mesh_node(node):
        mesh = node.getMeshData()
        if mesh is None:
            return None

        box = node.getBoundingBox()
        item = {
            "id": node.getId(),
            "name": node.getName(),
            "file": mesh.getFileName() or "",
        }
        if box is not None:
            item["bounds"] = {
                "width": box.width,
                "height": box.height,
                "depth": box.depth,
            }
        return item

    def move_object(self, arguments):
        arguments = arguments or {}
        object_id = arguments.get("object_id")
        position = arguments.get("position")
        if object_id is None or str(object_id).strip() == "":
            raise ValueError("object_id is required")
        if not isinstance(position, dict):
            raise ValueError("position must be an object")

        normalized_position = {}
        for key in ("x", "y", "z"):
            if key not in position:
                raise ValueError("position.%s is required" % key)
            value = position[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("position.%s must be a number" % key)
            value = float(value)
            if not math.isfinite(value):
                raise ValueError("position.%s must be finite" % key)
            normalized_position[key] = value

        return self._dispatch(
            lambda: self._move_object(object_id, normalized_position)
        )

    def _move_object(self, object_id, position):
        scene = self._application.getController().getScene()
        for node in DepthFirstIterator(scene.getRoot()):
            if str(node.getId()) != str(object_id):
                continue
            if node.getMeshData() is None:
                raise ValueError("Object is not a mesh: " + str(object_id))

            operation = TranslateOperation(
                node,
                Vector(position["x"], position["y"], position["z"]),
                set_position=True,
            )
            operation.push()
            return {
                "accepted": True,
                "object_id": node.getId(),
                "position": dict(position),
                "undoable": True,
                "coordinate_system": "world",
            }
        raise ValueError("Mesh object not found: " + str(object_id))

    def export_scene(self, arguments):
        arguments = arguments or {}
        file_name = arguments.get("file_name")
        file_format = arguments.get("file_format")
        if not isinstance(file_name, str) or not file_name.strip():
            raise ValueError("file_name is required")
        if not isinstance(file_format, str) or not file_format.strip():
            raise ValueError("file_format is required")
        return self._dispatch(
            lambda: self._export_scene(file_name, file_format)
        )

    def _export_scene(self, file_name, file_format):
        if self._exporter is None:
            from .exporter import SceneExporter
            self._exporter = SceneExporter(self._application)
        return self._exporter.export_scene(file_name, file_format)

    def get_export_status(self, arguments):
        return self._dispatch(self._get_export_status)

    def _get_export_status(self):
        if self._exporter is None:
            return {
                "state": "idle",
                "path": None,
                "format": None,
                "progress": None,
                "error": None,
            }
        return self._exporter.get_status()

    def start_slicing(self, arguments):
        return self._dispatch(self._start_slicing)

    def _start_slicing(self):
        get_backend_manager = getattr(self._application, "getBackendManager", None)
        if not callable(get_backend_manager):
            raise RuntimeError("Backend manager is unavailable.")
        manager = get_backend_manager()
        backend = manager.getCurrentBackend() if manager is not None else None
        if backend is None:
            raise RuntimeError("No active slicing backend.")
        force_slice = getattr(backend, "forceSlice", None)
        if not callable(force_slice):
            raise RuntimeError("Active backend does not support forceSlice().")

        self._observe_backend(backend)
        force_slice()
        get_plugin_id = getattr(backend, "getPluginId", None)
        return {
            "accepted": True,
            "backend": get_plugin_id() if callable(get_plugin_id) else None,
            "message": "Переслайсинг запущен штатным backend STE Slicer.",
            "asynchronous": True,
        }

    def get_backend_status(self, arguments):
        return self._dispatch(self._get_backend_status)

    def _get_backend_status(self):
        get_backend_manager = getattr(self._application, "getBackendManager", None)
        if not callable(get_backend_manager):
            return {"available": False, "message": "Backend manager is unavailable."}

        manager = get_backend_manager()
        backend = manager.getCurrentBackend() if manager is not None else None
        if backend is None:
            return {"available": False, "message": "No active slicing backend."}

        self._observe_backend(backend)
        get_plugin_id = getattr(backend, "getPluginId", None)
        backend_id = get_plugin_id() if callable(get_plugin_id) else None
        result = {
            "available": True,
            "backend": backend_id,
            "state": self._state_name(self._backend_state),
            "progress": self._backend_progress,
        }
        if self._backend_state is None:
            result["state_known"] = False
            result["message"] = "Backend state has not emitted a signal yet."
        else:
            result["state_known"] = True
        return result

    def _observe_backend(self, backend):
        if backend is self._observed_backend:
            return
        self._observed_backend = backend
        self._backend_state = None
        self._backend_progress = None
        state_signal = getattr(backend, "backendStateChange", None)
        if state_signal is not None and hasattr(state_signal, "connect"):
            state_signal.connect(self._on_backend_state_change)
        progress_signal = getattr(backend, "processingProgress", None)
        if progress_signal is not None and hasattr(progress_signal, "connect"):
            progress_signal.connect(self._on_backend_progress)

    def _on_backend_state_change(self, state):
        self._backend_state = state

    def _on_backend_progress(self, progress):
        try:
            self._backend_progress = float(progress)
        except (TypeError, ValueError):
            self._backend_progress = None

    @staticmethod
    def _state_name(state):
        if state is None:
            return None
        name = getattr(state, "name", None)
        if name:
            return name
        return {
            1: "NotStarted",
            2: "Processing",
            3: "Done",
            4: "Error",
            5: "Disabled",
        }.get(state, str(state))

    def get_settings(self, arguments):
        return self._dispatch(self._get_settings)

    def _get_settings(self):
        stack = self._application.getGlobalContainerStack()
        if stack is None:
            return {"machine": None, "settings": {}}

        keys = [
            "printing_mode",
            "layer_height",
            "infill_sparse_density",
            "wall_line_count",
            "support_enable",
            "material_print_temperature",
        ]
        values = {}
        for key in keys:
            try:
                values[key] = stack.getProperty(key, "value")
            except Exception:
                values[key] = None

        return {
            "machine": stack.getId(),
            "settings": values,
        }

    def arrange_scene(self, arguments):
        return self._dispatch(self._arrange_scene)

    def _arrange_scene(self):
        self._application.arrangeAll()
        return {"accepted": True, "message": "Авторасстановка запущена."}
