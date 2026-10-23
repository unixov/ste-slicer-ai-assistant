import os
import sys
import types
import unittest


class _Vector(object):
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z


class _TranslateOperation(object):
    instances = []

    def __init__(self, node, translation, set_position=False):
        self.node = node
        self.translation = translation
        self.set_position = set_position
        self.pushed = False
        self.__class__.instances.append(self)

    def push(self):
        self.pushed = True


class _Node(object):
    def __init__(self, object_id, mesh=True):
        self.object_id = object_id
        self.mesh = object() if mesh else None

    def getId(self):
        return self.object_id

    def getMeshData(self):
        return self.mesh


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
    def __init__(self, scene):
        self.controller = _Controller(scene)

    def getController(self):
        return self.controller


def _install_uranium_mocks():
    vector_module = types.ModuleType("UM.Math.Vector")
    vector_module.Vector = _Vector
    iterator_module = types.ModuleType("UM.Scene.Iterator.DepthFirstIterator")
    iterator_module.DepthFirstIterator = lambda root: iter(root.nodes)
    selection_module = types.ModuleType("UM.Scene.Selection")
    selection_module.Selection = types.SimpleNamespace(getAllSelectedObjects=lambda: [])
    operation_module = types.ModuleType("UM.Operations.TranslateOperation")
    operation_module.TranslateOperation = _TranslateOperation

    modules = {
        "UM": types.ModuleType("UM"),
        "UM.Math": types.ModuleType("UM.Math"),
        "UM.Math.Vector": vector_module,
        "UM.Scene": types.ModuleType("UM.Scene"),
        "UM.Scene.Iterator": types.ModuleType("UM.Scene.Iterator"),
        "UM.Scene.Iterator.DepthFirstIterator": iterator_module,
        "UM.Scene.Selection": selection_module,
        "UM.Operations": types.ModuleType("UM.Operations"),
        "UM.Operations.TranslateOperation": operation_module,
    }
    for name, module in modules.items():
        sys.modules[name] = module


_install_uranium_mocks()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin", "AIAssistant"))

from mcp.slicer_tools import SlicerTools


class SlicerToolsTests(unittest.TestCase):
    def setUp(self):
        _TranslateOperation.instances = []
        self.node = _Node("part-1")
        self.application = _Application(_Scene([self.node]))
        self.tools = SlicerTools(self.application)

    def test_move_object_uses_absolute_world_undoable_operation(self):
        result = self.tools.move_object(
            {
                "object_id": "part-1",
                "position": {"x": 10, "y": -2.5, "z": 0},
            }
        )

        self.assertTrue(result["accepted"])
        self.assertTrue(result["undoable"])
        self.assertEqual(result["coordinate_system"], "world")
        self.assertEqual(result["position"], {"x": 10.0, "y": -2.5, "z": 0.0})
        self.assertEqual(len(_TranslateOperation.instances), 1)
        operation = _TranslateOperation.instances[0]
        self.assertTrue(operation.pushed)
        self.assertTrue(operation.set_position)
        self.assertEqual(operation.translation.x, 10.0)
        self.assertEqual(operation.translation.y, -2.5)
        self.assertEqual(operation.translation.z, 0.0)

    def test_move_object_rejects_non_finite_coordinates(self):
        with self.assertRaises(ValueError):
            self.tools.move_object(
                {
                    "object_id": "part-1",
                    "position": {"x": float("nan"), "y": 0, "z": 0},
                }
            )
        self.assertEqual(_TranslateOperation.instances, [])

    def test_move_object_rejects_missing_mesh(self):
        tools = SlicerTools(_Application(_Scene([_Node("group-1", mesh=False)])))
        with self.assertRaises(ValueError):
            tools.move_object(
                {
                    "object_id": "group-1",
                    "position": {"x": 0, "y": 0, "z": 0},
                }
            )
        self.assertEqual(_TranslateOperation.instances, [])


if __name__ == "__main__":
    unittest.main()
