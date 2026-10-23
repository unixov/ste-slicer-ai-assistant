import os
import shutil
import sys
import tempfile
import types
import unittest


class _Signal(object):
    def __init__(self):
        self.handlers = []

    def connect(self, handler):
        self.handlers.append(handler)

    def emit(self, *args):
        for handler in list(self.handlers):
            handler(*args)


class _OutputMode(object):
    TextMode = "text"
    BinaryMode = "binary"


class _FileWriter(object):
    OutputMode = _OutputMode


class _WriteFileJob(object):
    fail_start = False

    def __init__(self, writer, stream, data, mode):
        self.writer = writer
        self.stream = stream
        self.data = data
        self.mode = mode
        self.progress = _Signal()
        self.finished = _Signal()
        self._file_name = ""
        self._result = False
        self._error = None

    def setFileName(self, file_name):
        self._file_name = file_name

    def getFileName(self):
        return self._file_name

    def getStream(self):
        return self.stream

    def getResult(self):
        return self._result

    def getError(self):
        return self._error

    def start(self):
        if self.__class__.fail_start:
            raise RuntimeError("mock job start failure")
        self.progress.emit(self, 0.5)
        self._result = bool(self.writer.write(self.stream, self.data, self.mode))
        if not self._result:
            self._error = "mock writer failure"
        self.progress.emit(self, 1.0)
        self.finished.emit(self)


class _OutputDevice(object):
    def __init__(self, device_id):
        self.device_id = device_id
        self.writeStarted = _Signal()
        self.writeProgress = _Signal()
        self.writeFinished = _Signal()
        self.writeError = _Signal()
        self.writeSuccess = _Signal()


class _DeviceBusyError(Exception):
    pass


class _WriteRequestFailedError(Exception):
    pass


class _OutputDeviceError(object):
    DeviceBusyError = _DeviceBusyError
    WriteRequestFailedError = _WriteRequestFailedError


class _Writer(object):
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    def write(self, stream, nodes, mode):
        self.calls.append((stream, nodes, mode))
        if mode == _OutputMode.TextMode:
            stream.write("generated gcode")
        else:
            stream.write(b"generated 3mf")
        return self.result


class _FileHandler(object):
    def __init__(self):
        self.gcode_writer = _Writer()
        self.threemf_writer = _Writer()

    def getSupportedFileTypesWrite(self):
        return [
            {
                "id": "GCodeWriter",
                "extension": "gcode",
                "mime_type": "text/x-gcode",
                "mode": _OutputMode.TextMode,
            },
            {
                "id": "3MFWriter",
                "extension": "3mf",
                "mime_type": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
                "mode": _OutputMode.BinaryMode,
            },
        ]

    def getWriter(self, writer_id):
        return {
            "GCodeWriter": self.gcode_writer,
            "3MFWriter": self.threemf_writer,
        }.get(writer_id)

    def getWriterByMimeType(self, mime_type):
        if mime_type == "text/x-gcode":
            return self.gcode_writer
        return self.threemf_writer


class _Node(object):
    def getMeshData(self):
        return object()


class _Root(object):
    def __init__(self, nodes):
        self.nodes = nodes


class _Scene(object):
    def __init__(self, nodes):
        self.root = _Root(nodes)

    def getRoot(self):
        return self.root


class _Controller(object):
    def __init__(self, scene):
        self.scene = scene

    def getScene(self):
        return self.scene


class _Application(object):
    def __init__(self, scene, file_handler):
        self.controller = _Controller(scene)
        self.file_handler = file_handler

    def getController(self):
        return self.controller

    def getMeshFileHandler(self):
        return self.file_handler


def _install_uranium_mocks():
    file_writer_module = types.ModuleType("UM.FileHandler.FileWriter")
    file_writer_module.FileWriter = _FileWriter
    write_job_module = types.ModuleType("UM.FileHandler.WriteFileJob")
    write_job_module.WriteFileJob = _WriteFileJob
    output_device_module = types.ModuleType("UM.OutputDevice.OutputDevice")
    output_device_module.OutputDevice = _OutputDevice
    output_package = types.ModuleType("UM.OutputDevice")
    output_package.OutputDeviceError = _OutputDeviceError
    iterator_module = types.ModuleType("UM.Scene.Iterator.DepthFirstIterator")
    iterator_module.DepthFirstIterator = lambda root: iter(root.nodes)

    modules = {
        "UM": types.ModuleType("UM"),
        "UM.FileHandler": types.ModuleType("UM.FileHandler"),
        "UM.FileHandler.FileWriter": file_writer_module,
        "UM.FileHandler.WriteFileJob": write_job_module,
        "UM.OutputDevice": output_package,
        "UM.OutputDevice.OutputDevice": output_device_module,
        "UM.Scene": types.ModuleType("UM.Scene"),
        "UM.Scene.Iterator": types.ModuleType("UM.Scene.Iterator"),
        "UM.Scene.Iterator.DepthFirstIterator": iterator_module,
    }
    for name, module in modules.items():
        sys.modules[name] = module


_install_uranium_mocks()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin", "AIAssistant"))

from mcp.exporter import AssistantFileOutputDevice, SceneExporter


class ExporterTests(unittest.TestCase):
    def setUp(self):
        _WriteFileJob.fail_start = False
        self.directory = tempfile.mkdtemp(prefix="ste-ai-export-")
        self.file_handler = _FileHandler()
        self.application = _Application(
            _Scene([_Node()]),
            self.file_handler,
        )

    def tearDown(self):
        shutil.rmtree(self.directory)

    def test_gcode_export_uses_registered_writer_and_adds_extension(self):
        exporter = SceneExporter(self.application)
        result = exporter.export_scene(
            os.path.join(self.directory, "part"),
            "gcode",
        )

        output_path = os.path.join(self.directory, "part.gcode")
        self.assertTrue(result["accepted"])
        self.assertEqual(result["state"], "done")
        self.assertTrue(os.path.isfile(output_path))
        with open(output_path, "r") as stream:
            self.assertEqual(stream.read(), "generated gcode")
        self.assertEqual(len(self.file_handler.gcode_writer.calls), 1)
        self.assertEqual(len(self.file_handler.threemf_writer.calls), 0)

    def test_3mf_export_uses_binary_writer(self):
        exporter = SceneExporter(self.application)
        exporter.export_scene(
            os.path.join(self.directory, "part.3mf"),
            "3mf",
        )

        output_path = os.path.join(self.directory, "part.3mf")
        with open(output_path, "rb") as stream:
            self.assertEqual(stream.read(), b"generated 3mf")
        self.assertEqual(len(self.file_handler.threemf_writer.calls), 1)

    def test_existing_file_is_not_overwritten(self):
        output_path = os.path.join(self.directory, "existing.gcode")
        with open(output_path, "w") as stream:
            stream.write("keep me")

        exporter = SceneExporter(self.application)
        with self.assertRaises(ValueError):
            exporter.export_scene(output_path, "gcode")

        with open(output_path, "r") as stream:
            self.assertEqual(stream.read(), "keep me")
        self.assertEqual(len(self.file_handler.gcode_writer.calls), 0)

    def test_start_failure_removes_partial_file(self):
        _WriteFileJob.fail_start = True
        exporter = SceneExporter(self.application)

        with self.assertRaises(RuntimeError):
            exporter.export_scene(
                os.path.join(self.directory, "failed.gcode"),
                "gcode",
            )

        self.assertFalse(os.path.exists(os.path.join(self.directory, "failed.gcode")))

    def test_scene_without_mesh_is_rejected(self):
        application = _Application(_Scene([]), self.file_handler)
        exporter = SceneExporter(application)

        with self.assertRaises(ValueError):
            exporter.export_scene(
                os.path.join(self.directory, "empty.gcode"),
                "gcode",
            )


if __name__ == "__main__":
    unittest.main()
