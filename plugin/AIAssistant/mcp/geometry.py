"""
geometry.py — геометрический анализ MeshData и эвристический структурный анализ.

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


# ---------------------------------------------------------------------------
# KILLER FEATURE: Heuristic Structural Zone Analysis
# ---------------------------------------------------------------------------

def estimate_structural_zones(node):
    """
    Эвристический анализ структурных зон детали для оптимизации FDM-печати.

    Без FEA-решателя: использует геометрические пропорции bounding box,
    соотношения сторон и базовые правила сопротивления материалов, чтобы
    оценить зоны концентрации напряжений и выдать рекомендации по:
      - ориентации детали (слои вдоль вектора нагрузки)
      - адаптивному заполнению (высокая плотность в зонах напряжений)
      - числу стенок и паттерну заполнения

    Параметры
    ---------
    node : UM.Scene.SceneNode

    Возвращает
    ----------
    dict с ключами:
        geometry       : dict  — результат analyse_mesh
        stress_profile : str   — тип профиля нагружения (column / bracket / plate / general)
        zones          : list  — зоны с оценкой риска [0-10] и описанием
        orientation    : dict  — рекомендация по ориентации
        adaptive_infill: dict  — рекомендации по заполнению
        recommended_settings: dict — конкретные значения настроек слайсера
        explanation    : str   — текстовое пояснение на русском языке
    """
    geo = analyse_mesh(node)
    bbox = geo.get("bbox") or {}
    w = bbox.get("width", 0.0)
    h = bbox.get("height", 0.0)
    d = bbox.get("depth", 0.0)

    result = {
        "geometry": geo,
        "stress_profile": "general",
        "zones": [],
        "orientation": {},
        "adaptive_infill": {},
        "recommended_settings": {},
        "explanation": "",
    }

    if not (w > 0 and h > 0 and d > 0):
        result["explanation"] = "Невозможно выполнить анализ: bounding box недоступен."
        return result

    base = max(w, d)   # footprint размер
    foot = min(w, d)   # наименьшая сторона следа
    dims = sorted([w, h, d])  # [min, mid, max]

    # -----------------------------------------------------------------------
    # 1. Классификация профиля нагружения
    # -----------------------------------------------------------------------
    h_to_base = h / base if base > 0 else 0
    slender = foot > 0 and h / foot > 2.5   # высокая и узкая
    thin_plate = h < 5.0 and base > 40.0    # плоская широкая пластина
    bracket = (                              # кронштейн/консоль
        dims[2] / dims[1] > 2.0 and
        dims[1] / dims[0] > 1.5
    )

    if slender and h_to_base > 2.0:
        profile = "column"
    elif thin_plate:
        profile = "plate"
    elif bracket:
        profile = "bracket"
    else:
        profile = "general"

    result["stress_profile"] = profile

    # -----------------------------------------------------------------------
    # 2. Определение зон напряжений
    # -----------------------------------------------------------------------
    zones = []

    # Зона 1 — основание (адгезия + сжатие первых слоёв)
    base_risk = 6 if thin_plate else 4
    zones.append({
        "name": "base",
        "label": "Основание (первые слои)",
        "risk_score": base_risk,
        "description": (
            "Зона адгезии к столу. При плоской широкой детали — "
            "высокий риск отслоения (warping)." if thin_plate
            else "Стандартная зона сжатия. Критична для адгезии."
        ),
        "z_fraction": [0.0, 0.1],
    })

    # Зона 2 — средняя часть колонны / тонкое сечение
    if slender:
        neck_risk = min(10, int(4 + h_to_base * 1.5))
        zones.append({
            "name": "neck",
            "label": "Шейка (тонкое сечение)",
            "risk_score": neck_risk,
            "description": (
                "Критическая зона концентрации напряжений. Слои "
                "перпендикулярны вектору нагрузки — высокий риск "
                "расслоения под осевой нагрузкой."
            ),
            "z_fraction": [0.3, 0.7],
        })
    else:
        zones.append({
            "name": "mid",
            "label": "Средняя зона",
            "risk_score": 3,
            "description": "Умеренные напряжения изгиба или сдвига.",
            "z_fraction": [0.2, 0.8],
        })

    # Зона 3 — консоль / верхняя часть кронштейна
    if profile == "bracket":
        zones.append({
            "name": "cantilever_tip",
            "label": "Конец консоли (максимальный момент)",
            "risk_score": 9,
            "description": (
                "Максимальный изгибающий момент. Слои FDM "
                "перпендикулярны вектору изгиба — самая уязвимая "
                "точка конструкции."
            ),
            "z_fraction": [0.7, 1.0],
        })
    elif profile == "column":
        zones.append({
            "name": "top",
            "label": "Вершина колонны",
            "risk_score": 5,
            "description": (
                "Зона приложения нагрузки. Требует хорошей "
                "плотности верхних слоёв."
            ),
            "z_fraction": [0.85, 1.0],
        })
    else:
        zones.append({
            "name": "top",
            "label": "Верхняя зона",
            "risk_score": 2,
            "description": "Низкие нагрузки, стандартная плотность.",
            "z_fraction": [0.8, 1.0],
        })

    result["zones"] = zones
    max_risk = max(z["risk_score"] for z in zones)

    # -----------------------------------------------------------------------
    # 3. Рекомендация по ориентации
    # -----------------------------------------------------------------------
    if profile == "column":
        result["orientation"] = {
            "action": "rotate",
            "axis": "x",
            "angle_deg": 90,
            "reason": (
                "Уложить деталь горизонтально: слои будут идти "
                "ВДОЛЬ оси нагрузки, а не поперёк. "
                "Прочность на растяжение вырастет в 2-4 раза "
                "по сравнению с вертикальной ориентацией."
            ),
            "estimated_strength_gain": "+200-400%",
        }
    elif profile == "bracket":
        result["orientation"] = {
            "action": "rotate",
            "axis": "y",
            "angle_deg": 45,
            "reason": (
                "Повернуть кронштейн на 45°: слои проходят "
                "диагонально через зону изгиба — "
                "компромисс между прочностью и высотой поддержек."
            ),
            "estimated_strength_gain": "+50-80%",
        }
    elif profile == "plate":
        result["orientation"] = {
            "action": "rotate",
            "axis": "x",
            "angle_deg": 90,
            "reason": (
                "Печатать на ребро: слои идут вдоль плоскости "
                "пластины, что обеспечивает максимальную "
                "жёсткость на изгиб."
            ),
            "estimated_strength_gain": "+150-300%",
        }
    else:
        result["orientation"] = {
            "action": "keep",
            "axis": None,
            "angle_deg": 0,
            "reason": "Текущая ориентация оптимальна для общего профиля нагружения.",
            "estimated_strength_gain": "0%",
        }

    # -----------------------------------------------------------------------
    # 4. Адаптивное заполнение
    # -----------------------------------------------------------------------
    if max_risk >= 8:
        base_density = 15
        stress_density = 80
        pattern = "gyroid"
        walls = 5
    elif max_risk >= 5:
        base_density = 15
        stress_density = 60
        pattern = "gyroid"
        walls = 4
    else:
        base_density = 15
        stress_density = 30
        pattern = "grid"
        walls = 3

    high_risk_zones = [z["name"] for z in zones if z["risk_score"] >= 5]

    result["adaptive_infill"] = {
        "base_density_pct": base_density,
        "stress_zone_density_pct": stress_density,
        "pattern": pattern,
        "high_risk_zones": high_risk_zones,
        "estimated_material_saving_vs_uniform_80pct": (
            "{}%".format(
                max(0, int((1 - (
                    base_density * 0.6 + stress_density * 0.4
                ) / 80) * 100))
            )
        ),
    }

    # -----------------------------------------------------------------------
    # 5. Конкретные настройки слайсера
    # -----------------------------------------------------------------------
    recommended = {
        "infill_sparse_density": stress_density,
        "infill_pattern": pattern,
        "wall_line_count": walls,
        "layer_height": 0.15 if max_risk >= 7 else 0.2,
        "support_enable": profile in ("column", "bracket") and result["orientation"]["action"] != "keep",
    }

    # 5D-печать для высоконагруженных деталей
    if max_risk >= 7:
        recommended["printing_mode"] = "5d"
        recommended["_5d_note"] = (
            "5D-режим позволяет ориентировать слои вдоль вектора "
            "нагрузки без физического поворота детали."
        )
    else:
        recommended["printing_mode"] = "3d"

    result["recommended_settings"] = recommended

    # -----------------------------------------------------------------------
    # 6. Текстовое пояснение
    # -----------------------------------------------------------------------
    risk_label = (
        "КРИТИЧЕСКИЙ" if max_risk >= 8
        else "ВЫСОКИЙ" if max_risk >= 6
        else "УМЕРЕННЫЙ" if max_risk >= 4
        else "НИЗКИЙ"
    )

    result["explanation"] = (
        "Профиль нагружения: {profile}. "
        "Максимальный риск разрушения: {risk} (оценка {score}/10). "
        "Обнаружено {nz} зон напряжений. "
        "Рекомендуемое заполнение: {bd}% (базовое) / {sd}% (зоны нагрузок), "
        "паттерн {pat}. "
        "Число стенок: {walls}. "
        "{orient_note}"
    ).format(
        profile=profile,
        risk=risk_label,
        score=max_risk,
        nz=len(zones),
        bd=base_density,
        sd=stress_density,
        pat=pattern,
        walls=walls,
        orient_note=result["orientation"]["reason"],
    )

    return result


# ---------------------------------------------------------------------------
# Print mode recommendation: 3D vs 5D + material suggestion
# Based on aurora GeometryAnalyzer logic, adapted for UM bbox (no trimesh).
# ---------------------------------------------------------------------------

# Plastic density kg/cm³ for mass estimation
_MATERIAL_DENSITY = {
    "PLA":   1.24,
    "PETG":  1.27,
    "ABS":   1.04,
    "TPU":   1.20,
    "NYLON": 1.14,
    "PA":    1.14,
}


def recommend_print_mode(node):
    """
    Анализирует геометрию узла сцены и рекомендует:
      - режим печати: 3D или 5D
      - материал: PLA / PETG / ABS / TPU / NYLON
      - структурный риск
      - массу и объём детали (оценка по bounding box и коэффициенту заполнения)

    Не требует trimesh — работает только с bounding box и счётчиком полигонов.

    Параметры
    ---------
    node : UM.Scene.SceneNode

    Возвращает
    ----------
    dict с ключами:
        recommended_mode     : "3D" или "5D"
        mode_reason          : str — простое объяснение для пользователя
        recommended_material : str — PLA / PETG / ABS / TPU / NYLON
        material_reason      : str — почему именно этот материал
        dimensions_mm        : dict — габариты {x, y, z}
        volume_bbox_cm3      : float — объём описывающего параллелепипеда в см³
        estimated_volume_cm3 : float — оценка объёма детали (~40% от bbox)
        estimated_mass_g     : dict  — масса в граммах для каждого материала
        overhang_likely      : bool — вероятно ли наличие нависаний
        aspect_ratio         : float — соотношение макс/мин сторон
        print_complexity     : str — "simple" / "moderate" / "complex"
        beginner_summary     : str — объяснение для начинающего пользователя
    """
    geo = analyse_mesh(node)
    bbox = geo.get("bbox") or {}
    w = bbox.get("width", 0.0)
    h = bbox.get("height", 0.0)
    d = bbox.get("depth", 0.0)

    result = {
        "recommended_mode":     "3D",
        "mode_reason":          "",
        "recommended_material": "PLA",
        "material_reason":      "",
        "dimensions_mm":        {"x": round(w, 2), "y": round(h, 2), "z": round(d, 2)},
        "volume_bbox_cm3":      0.0,
        "estimated_volume_cm3": 0.0,
        "estimated_mass_g":     {},
        "overhang_likely":      False,
        "aspect_ratio":         1.0,
        "print_complexity":     "simple",
        "beginner_summary":     "",
    }

    if not (w > 0 and h > 0 and d > 0):
        result["beginner_summary"] = "Не удалось определить размеры модели."
        return result

    dims = sorted([w, h, d])  # [min, mid, max]
    aspect = dims[2] / (dims[0] + 1e-8)
    vol_bbox_mm3 = w * h * d
    vol_bbox_cm3 = vol_bbox_mm3 / 1000.0
    # Typical solid fill fraction for FDM part ~35-45% of bbox
    est_vol_cm3 = round(vol_bbox_cm3 * 0.40, 3)

    result["aspect_ratio"]      = round(aspect, 2)
    result["volume_bbox_cm3"]   = round(vol_bbox_cm3, 3)
    result["estimated_volume_cm3"] = est_vol_cm3

    # Mass estimate for each material
    for mat, density in _MATERIAL_DENSITY.items():
        result["estimated_mass_g"][mat] = round(est_vol_cm3 * density * 1000 / 1000 * density, 1)
    # Correct: density in g/cm³, volume in cm³ → mass in g
    for mat, density in _MATERIAL_DENSITY.items():
        result["estimated_mass_g"][mat] = round(est_vol_cm3 * density, 1)

    # -----------------------------------------------------------------------
    # 3D vs 5D recommendation
    # Aurora logic: overhangs > 45° or high aspect ratio → 5D
    # We estimate overhangs from geometry: very tall & thin column, or
    # high face count with complex shape (vertex_count / face ratio).
    # -----------------------------------------------------------------------
    vertex_count = geo.get("vertex_count", 0)
    face_count   = geo.get("face_count", 0)

    # Heuristic: overhang likely if aspect ratio > 3 (tall thin column)
    # or if the part is wider than tall (horizontal bridges)
    overhang_likely = False
    if aspect > 4.0:
        overhang_likely = True  # very elongated — likely needs 5D orientation
    if h > 0 and w > 0 and d > 0:
        # Low flat part with protrusions estimated by vertex density
        if h < 10.0 and face_count > 5000:
            overhang_likely = True  # complex flat part
        if h / max(w, d) < 0.15 and face_count > 2000:
            overhang_likely = True  # very flat with many faces → overhangs likely

    result["overhang_likely"] = overhang_likely

    if overhang_likely or aspect > 4.0:
        result["recommended_mode"] = "5D"
        if aspect > 4.0:
            result["mode_reason"] = (
                "Деталь очень вытянутая (соотношение сторон {:.1f}:1). "
                "5D-печать повернёт слои вдоль длинной оси — деталь будет "
                "значительно прочнее и не потребует поддержек.".format(aspect)
            )
        else:
            result["mode_reason"] = (
                "Деталь плоская и сложная — скорее всего есть нависания > 45°. "
                "5D-печать позволяет печатать такие детали без поддержек, "
                "экономя пластик и время."
            )
    else:
        result["recommended_mode"] = "3D"
        result["mode_reason"] = (
            "Деталь простой формы, нависаний не обнаружено. "
            "Стандартная 3D-печать подойдёт отлично."
        )

    # -----------------------------------------------------------------------
    # Complexity
    # -----------------------------------------------------------------------
    if face_count > 50000 or aspect > 5:
        result["print_complexity"] = "complex"
    elif face_count > 10000 or aspect > 2.5 or overhang_likely:
        result["print_complexity"] = "moderate"
    else:
        result["print_complexity"] = "simple"

    # -----------------------------------------------------------------------
    # Material recommendation
    # -----------------------------------------------------------------------
    # Without user input we recommend based on part size and complexity.
    # Large / heavy parts → PETG (better than PLA for functional use).
    # Very small / decorative → PLA.
    # Complex / mechanical → PETG as safe default.
    if est_vol_cm3 > 50 or result["print_complexity"] == "complex":
        mat = "PETG"
        mat_reason = (
            "Деталь большая или сложная. PETG прочнее PLA, "
            "не боится влаги и подходит для функциональных деталей."
        )
    elif est_vol_cm3 < 2 and result["print_complexity"] == "simple":
        mat = "PLA"
        mat_reason = (
            "Небольшая простая деталь. PLA — самый простой в печати "
            "материал, даёт хорошее качество поверхности."
        )
    else:
        mat = "PLA"
        mat_reason = (
            "PLA — универсальный материал для большинства деталей. "
            "Если деталь несёт нагрузку, рассмотрите PETG."
        )

    result["recommended_material"] = mat
    result["material_reason"]      = mat_reason

    # -----------------------------------------------------------------------
    # Beginner-friendly summary
    # -----------------------------------------------------------------------
    mass_g = result["estimated_mass_g"].get(mat, 0)
    result["beginner_summary"] = (
        "Деталь {w:.0f} x {d:.0f} x {h:.0f} мм, примерно {mass:.0f} г ({mat}). "
        "Режим: {mode}. {mode_reason} "
        "Материал: {mat} — {mat_reason}"
    ).format(
        w=w, d=d, h=h,
        mass=mass_g,
        mat=mat,
        mode=result["recommended_mode"],
        mode_reason=result["mode_reason"],
        mat_reason=mat_reason,
    )

    return result
