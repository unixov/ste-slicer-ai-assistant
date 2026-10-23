from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator


class SlicerTools(object):
    def __init__(self, application, dispatch=None):
        self._application = application
        self._dispatch = dispatch or (lambda callback: callback())

    def list_scene_objects(self, arguments):
        return self._dispatch(self._list_scene_objects)

    def _list_scene_objects(self):
        scene = self._application.getController().getScene()
        objects = []
        for node in DepthFirstIterator(scene.getRoot()):
            mesh = node.getMeshData()
            if mesh is None:
                continue
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
            objects.append(item)
        return {"objects": objects}

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
