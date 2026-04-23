from typing import Dict, Any


TOOL_NAME = "list_objects"
TOOL_FUNC = "list_objects"
TOOL_DESCRIPTION = (
    "List Maya scene objects by category. "
    "Supports joints, meshes, curves, cameras, lights, deformers, locators, transforms, or all."
)


def list_objects(
    category: str = "all",
    long_name: bool = False,
    include_shapes: bool = False,
    include_default_cameras: bool = True,
) -> Dict[str, Any]:
    """
    List scene objects grouped by category.

    Args:
        category (str):
            Supported:
            - all
            - joints
            - meshes
            - curves
            - cameras
            - lights
            - deformers
            - locators
            - transforms

        long_name (bool):
            Return full DAG path if True.

        include_shapes (bool):
            If True, also include shape nodes for shape-based categories
            such as meshes / curves / cameras / lights / locators.

        include_default_cameras (bool):
            If False, filter out persp / top / front / side camera transforms.

    Returns:
        Dict[str, Any]
    """
    import maya.cmds as cmds

    category = (category or "all").strip().lower()

    valid_categories = {
        "all",
        "joints",
        "meshes",
        "curves",
        "cameras",
        "lights",
        "deformers",
        "locators",
        "transforms",
    }

    if category not in valid_categories:
        raise RuntimeError(
            f"Unsupported category: {category}. "
            f"Supported: {sorted(valid_categories)}"
        )

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------
    def _dedupe(items):
        seen = set()
        result = []
        for x in items:
            if x not in seen:
                seen.add(x)
                result.append(x)
        return result

    def _ls_type_safe(node_type: str):
        try:
            return cmds.ls(type=node_type, long=long_name) or []
        except Exception:
            # 某些插件节点类型不存在时，直接忽略
            return []

    def _ls_types_safe(node_types):
        items = []
        for t in node_types:
            items.extend(_ls_type_safe(t))
        return _dedupe(items)

    def _parents_of_shapes(shapes):
        parents = []
        for shape in shapes:
            rel = cmds.listRelatives(shape, parent=True, fullPath=long_name) or []
            if rel:
                parents.extend(rel)
        return _dedupe(parents)

    def _shape_category(shape_types):
        shapes = _ls_types_safe(shape_types)
        transforms = _parents_of_shapes(shapes)

        data = {
            "count": len(transforms),
            "objects": transforms,
        }

        if include_shapes:
            data["shape_count"] = len(shapes)
            data["shapes"] = shapes

        return data

    # --------------------------------------------------
    # Category collectors
    # --------------------------------------------------

    def _collect_joints():
        joints = _ls_type_safe("joint")
        return {
            "count": len(joints),
            "objects": joints,
        }

    def _collect_meshes():
        # mesh 是 shape，通常更有用的是返回 transform
        return _shape_category(["mesh"])

    def _collect_curves():
        return _shape_category(["nurbsCurve"])

    def _collect_cameras():
        data = _shape_category(["camera"])

        if not include_default_cameras:
            default_cam_names = {"persp", "top", "front", "side"}
            filtered = []
            for obj in data["objects"]:
                short_name = obj.split("|")[-1]
                if short_name not in default_cam_names:
                    filtered.append(obj)
            data["objects"] = filtered
            data["count"] = len(filtered)

            if include_shapes and "shapes" in data:
                filtered_shapes = []
                for shape in data["shapes"]:
                    parents = cmds.listRelatives(shape, parent=True, fullPath=long_name) or []
                    if not parents:
                        continue
                    short_name = parents[0].split("|")[-1]
                    if short_name not in default_cam_names:
                        filtered_shapes.append(shape)
                data["shapes"] = filtered_shapes
                data["shape_count"] = len(filtered_shapes)

        return data

    def _collect_lights():
        # Maya 内置常见灯光 + 一些常见 Arnold 灯光类型（不存在时会自动忽略）
        light_types = [
            "ambientLight",
            "directionalLight",
            "pointLight",
            "spotLight",
            "areaLight",
            "volumeLight",
            "aiAreaLight",
            "aiSkyDomeLight",
            "aiPhotometricLight",
            "aiMeshLight",
        ]
        return _shape_category(light_types)

    def _collect_locators():
        return _shape_category(["locator"])

    def _collect_transforms():
        transforms = _ls_type_safe("transform")
        return {
            "count": len(transforms),
            "objects": transforms,
        }

    def _collect_deformers():
        # 常用变形器列表
        deformer_types = [
            "skinCluster",
            "blendShape",
            "cluster",
            "lattice",
            "wire",
            "wrap",
            "sculpt",
            "nonLinear",
            "deltaMush",
            "tweak",
            "ffd",
            "proximityWrap",
            "shrinkWrap",
        ]

        deformers = _ls_types_safe(deformer_types)

        # 尝试补 geometryFilter 基类（某些 Maya 版本可能有效）
        try:
            geometry_filters = cmds.ls(type="geometryFilter") or []
            deformers.extend(geometry_filters)
        except Exception:
            pass

        deformers = _dedupe(deformers)

        return {
            "count": len(deformers),
            "objects": deformers,
        }

    collectors = {
        "joints": _collect_joints,
        "meshes": _collect_meshes,
        "curves": _collect_curves,
        "cameras": _collect_cameras,
        "lights": _collect_lights,
        "locators": _collect_locators,
        "transforms": _collect_transforms,
        "deformers": _collect_deformers,
    }

    # --------------------------------------------------
    # Build result
    # --------------------------------------------------
    if category == "all":
        categories = {}
        total_count = 0

        for key, fn in collectors.items():
            data = fn()
            categories[key] = data
            total_count += data.get("count", 0)

        return {
            "success": True,
            "category": "all",
            "total_categories": len(categories),
            "total_count": total_count,
            "categories": categories,
        }

    data = collectorscategory

    return {
        "success": True,
        "category": category,
        "count": data.get("count", 0),
        "result": data,
    }
