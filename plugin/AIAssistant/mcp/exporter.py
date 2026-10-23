import os

from UM.FileHandler.FileWriter import FileWriter
from UM.FileHandler.WriteFileJob import WriteFileJob
from UM.OutputDevice.OutputDevice import OutputDevice
from UM.OutputDevice import OutputDeviceError


class AssistantFileOutputDevice(OutputDevice):
    """Headless local output device using STE Slicer's writer pipeline.

    Unlike the stock LocalFileOutputDevice, this adapter does not open a
    QFileDialog. The assistant supplies a validated path after the user has
    confirmed the pending MCP action in the sidebar.
    """

    _FORMAT_EXTENSIONS = {
        "gcode": "gcode",
        "3mf": "3mf",
    }

    def __init__(self, application):
        super().__init__("ai_assistant_file")
        self._application = application
        self._writing = False
        self._job = None
        self._stream = None
        self._path = None
        self._format = None
        self._status = {
            "state": "idle",
            "path": None,
            "format": None,
            "progress": None,
            "error": None,
        }

    def getStatus(self):
        return dict(self._status)

    def requestWrite(self, nodes, file_name=None, file_format=None,
                     file_handler=None, **kwargs):
        if self._writing:
            raise OutputDeviceError.DeviceBusyError()

        path, normalized_format = self._validate_request(
            file_name,
            file_format,
        )
        if os.path.exists(path):
            raise ValueError("Refusing to overwrite existing file: " + path)

        handler = file_handler or self._application.getMeshFileHandler()
        file_type = self._find_file_type(handler, normalized_format)
        writer = handler.getWriter(file_type["id"])
        if writer is None:
            writer = handler.getWriterByMimeType(file_type["mime_type"])
        if writer is None:
            raise OutputDeviceError.WriteRequestFailedError(
                "Writer is unavailable for ." + file_type["extension"]
            )

        mode = file_type["mode"]
        if mode == FileWriter.OutputMode.TextMode:
            stream = open(path, "xt", encoding="utf-8")
        elif mode == FileWriter.OutputMode.BinaryMode:
            stream = open(path, "xb")
        else:
            raise OutputDeviceError.WriteRequestFailedError(
                "Unsupported output mode for " + normalized_format
            )

        try:
            job = WriteFileJob(writer, stream, nodes, mode)
            job.setFileName(path)
            job.progress.connect(self._on_job_progress)
            job.finished.connect(self._on_job_finished)
            self._stream = stream
            self._job = job
            self._path = path
            self._format = normalized_format
            self._writing = True
            self._status = {
                "state": "writing",
                "path": path,
                "format": normalized_format,
                "progress": 0.0,
                "error": None,
            }
            self.writeStarted.emit(self)
            job.start()
        except Exception:
            try:
                stream.close()
            except Exception:
                pass
            try:
                os.remove(path)
            except OSError:
                pass
            self._writing = False
            self._job = None
            self._stream = None
            self._status = {
                "state": "error",
                "path": path,
                "format": normalized_format,
                "progress": None,
                "error": "Export job could not be started.",
            }
            raise

    def _validate_request(self, file_name, file_format):
        if not isinstance(file_name, str) or not file_name.strip():
            raise ValueError("file_name is required")
        if not isinstance(file_format, str):
            raise ValueError("file_format is required")

        normalized_format = file_format.strip().lower().lstrip(".")
        if normalized_format not in self._FORMAT_EXTENSIONS:
            raise ValueError("file_format must be one of: gcode, 3mf")

        path = os.path.abspath(os.path.expanduser(file_name.strip()))
        if os.path.isdir(path):
            raise ValueError("file_name must point to a file")
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            raise ValueError("Parent directory does not exist: " + parent)

        expected_extension = "." + self._FORMAT_EXTENSIONS[normalized_format]
        root, extension = os.path.splitext(path)
        if not extension:
            path = root + expected_extension
        elif extension.lower() != expected_extension:
            raise ValueError(
                "file_name extension must be " + expected_extension
            )
        return path, normalized_format

    @staticmethod
    def _find_file_type(file_handler, normalized_format):
        expected_extension = normalized_format.lower()
        for item in file_handler.getSupportedFileTypesWrite():
            if str(item.get("extension", "")).lower() == expected_extension:
                return item
        raise OutputDeviceError.WriteRequestFailedError(
            "STE Slicer has no writer for ." + expected_extension
        )

    def _on_job_progress(self, job, progress):
        try:
            value = float(progress)
        except (TypeError, ValueError):
            value = None
        self._status["progress"] = value
        self.writeProgress.emit(self, progress)

    def _on_job_finished(self, job):
        self._writing = False
        result = bool(job.getResult())
        error = job.getError()
        try:
            self._stream.close()
        except (AttributeError, OSError, PermissionError) as close_error:
            result = False
            error = close_error

        self._status["state"] = "done" if result else "error"
        self._status["progress"] = 1.0 if result else self._status["progress"]
        self._status["error"] = None if result else str(error)
        self.writeFinished.emit(self)
        if result:
            self.writeSuccess.emit(self)
        else:
            self.writeError.emit(self)
        self._job = None
        self._stream = None


class SceneExporter(object):
    """Exports the current scene through the application's mesh writers."""

    def __init__(self, application):
        self._application = application
        self._device = AssistantFileOutputDevice(application)

    def export_scene(self, file_name, file_format):
        from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator

        scene = self._application.getController().getScene()
        nodes = []
        for node in DepthFirstIterator(scene.getRoot()):
            if node.getMeshData() is not None:
                nodes.append(node)
        if not nodes:
            raise ValueError("The scene contains no mesh objects")

        self._device.requestWrite(
            nodes,
            file_name=file_name,
            file_format=file_format,
        )
        result = self._device.getStatus()
        result.update({
            "accepted": True,
            "asynchronous": True,
            "message": "Экспорт запущен штатным writer pipeline STE Slicer.",
        })
        return result

    def get_status(self):
        return self._device.getStatus()
