"""
geometry.py — извлечение геометрических характеристик из MeshData STE Slicer.

Не требует внешних зависимостей: использует только встроенный Python и
объекты UM.Mesh.MeshData, доступные в дистрибутиве STE Slicer.
"""

import math


def analyse_mesh(node):
    """
    Возвращает словарь с геометрическими характеристиками SceneNode.

    Параметры
    ---------
    node : UM.Scene.SceneNode
        Узел сцены с мешем.

    Возвращает
    ----------
    dict с ключами:
        vertex_count   : int   — число вершин
        face_count     : int   — число треугольников (приблизительно)
        bbox           : dict  — габариты {width, height, depth} мм
        center         : dict  — центр bbox {x, y, z} мм
        volume_bbox    : float — объём описывающего параллелепипеда, мм³
        aspect_ratios  : dict  — соотношения сторон {w_h, w_d, h_d}
        warnings       : list  — список потенциальных проблем печати
    """
    result = {
        "vertex_count": 0,
        "face_count": 0,
        "bbox": None,
        "center": None,
        "volume_bbox": None,
        "aspect_ratios": None,
        "warnings": [],
    }

    # --- mesh data ---
    mesh = node.getMeshData() if callable(getattr(node, "getMeshData", None)) else None
    if mesh is not None:
        try:
            verts = mesh.getVertices()
            if verts is not None:
                result["vertex_count"] = int(len(verts))
        except Exception:
            pass

        try:
            indices = mesh.getIndices()
            if indices is not None:
                result["face_count"] = int(len(indices))
            elif result["vertex_count"] > 0:
                # no index buffer — every 3 vertices form one face
                result["face_count"] = result["vertex_count"] // 3
        except Exception:
            result["face_count"] = result["vertex_count"] // 3

    # --- bounding box ---
    box = None
    try:
        get_bb = getattr(node, "getBoundingBox", None)
        if callable(get_bb):
            box = get_bb()
    except Exception:
        pass

    if box is not None:
        try:
            w = float(box.width)
            h = float(box.height)
            d = float(box.depth)
            result["bbox"] = {
                "width": round(w, 3),
                "height": round(h, 3),
                "depth": round(d, 3),
            }
            # center
            try:
                cx = float((box.left + box.right) / 2)
                cy = float((box.bottom + box.top) / 2)
                cz = float((box.back + box.front) / 2)
            except Exception:
                cx = cy = cz = 0.0
            result["center"] = {
                "x": round(cx, 3),
                "y": round(cy, 3),
                "z": round(cz, 3),
            }
            if w > 0 and h > 0 and d > 0:
                result["volume_bbox"] = round(w * h * d, 3)
                result["aspect_ratios"] = {
                    "w_h": round(w / h, 3) if h > 0 else None,
                    "w_d": round(w / d, 3) if d > 0 else None,
                    "h_d": round(h / d, 3) if d > 0 else None,
                }
        except Exception:
            pass

    # --- print warnings ---
    warnings = []
    if box is not None:
        try:
            w = float(box.width)
            h = float(box.height)
            d = float(box.depth)

            # Very tall / thin — likely needs support
            if h > 0 and w > 0 and d > 0:
                if h / max(w, d) > 3.0:
                    warnings.append(
                        "Высокая деталь (H/base > 3): вероятно нужны поддержки или разворот."
                    )
                # Flat / wide — may need brim
                if h < 3.0 and max(w, d) > 60.0:
                    warnings.append(
                        "Плоская широкая деталь: рекомендуется brim для адгезии."
                    )
                # Very small — check nozzle diameter
                if max(w, h, d) < 5.0:
                    warnings.append(
                        "Очень маленькая деталь: убедитесь, что диаметр сопла подходит."
                    )
                # Large footprint — check build plate
                if w > 200 or d > 200:
                    warnings.append(
                        "Большая деталь: проверьте, что помещается на столе принтера."
                    )
        except Exception:
            pass

    if result["vertex_count"] > 0 and result["face_count"] == 0:
        warnings.append("Нет индексного буфера — возможен не-манифолд меш.")

    result["warnings"] = warnings
    return result
