from typing import Dict, Any, Optional


TOOL_NAME = "create_primitive"
TOOL_FUNC = "create_primitive"
TOOL_DESCRIPTION = (
    "Create a basic Maya primitive. "
    "Supported types: cube, sphere, cylinder, plane, cone, torus. "
    "Supports transform parameters and common size parameters."
)


def create_primitive(
    primitive_type: str = "cube",
    name: str = "",
    size: float = 1.0,
    radius: float = 1.0,
    height: float = 2.0,
    width: float = 1.0,
    depth: float = 1.0,
    translate: Optional[Any] = None,
    rotate: Optional[Any] = None,
    scale: Optional[Any] = None,
    world_space: bool = True,
) -> Dict[str, Any]:
    """
    Create a basic Maya primitive and optionally apply transform.

    Args:
        primitive_type (str):
            cube / sphere / cylinder / plane / cone / torus

        name (str):
            Optional object name. If empty, Maya default naming is used.

        size (float):
            Generic size used by cube / plane fallback.

        radius (float):
            Used by sphere / cylinder / cone / torus.

        height (float):
            Used by cylinder / cone.

        width (float):
            Used by plane.

        depth (float):
            Used by plane / cube custom dimensions if needed later.

        translate:
            [x, y, z] or "x y z" or "x,y,z" or "[x, y, z]"

        rotate:
            [x, y, z] or "x y z" or "x,y,z" or "[x, y, z]"

        scale:
            [x, y, z] or "x y z" or "x,y,z" or "[x, y, z]"

        world_space (bool):
            Apply translate / rotate in world space.

    Returns:
        Dict[str, Any]:
            Creation result and final transform state.
    """
    import ast
    import maya.cmds as cmds

    primitive_type = (primitive_type or "cube").strip().lower()

    def _parse_vec3(raw, label):
        if raw is None:
            return None

        if isinstance(raw, str):
            text = raw.strip()

            # 先尝试解析 "[1,2,3]" / "(1,2,3)"
            if (
                (text.startswith("[") and text.endswith("]")) or
                (text.startswith("(") and text.endswith(")"))
            ):
                try:
                    raw = ast.literal_eval(text)
                except Exception:
                    pass

            if isinstance(raw, str):
                text = raw.strip()
                text = text.strip("")
                text = text.replace(",", " ")
                parts = [p for p in text.split() if p]

                try:
                    values = [float(v) for v in parts]
                except Exception:
                    raise RuntimeError(f"{label} must be numeric values, got: {raw}")

                if len(values) != 3:
                    raise RuntimeError(f"{label} must have exactly 3 values (x y z), got: {values}")

                return values

        try:
            values = [float(v) for v in raw]
        except Exception:
            raise RuntimeError(f"{label} must be numeric values, got: {raw}")

        if len(values) != 3:
            raise RuntimeError(f"{label} must have exactly 3 values (x y z), got: {values}")

        return values

    def _apply_transform(node_name: str):
        t = _parse_vec3(translate, "Translate")
        if t is not None:
            cmds.xform(node_name, t=t, ws=world_space)

        r = _parse_vec3(rotate, "Rotate")
        if r is not None:
            cmds.xform(node_name, ro=r, ws=world_space)

        s = _parse_vec3(scale, "Scale")
        if s is not None:
            # 不用 xform(s=...)，直接 setAttr 最稳
            cmds.setAttr(node_name + ".scaleX", s[0])
            cmds.setAttr(node_name + ".scaleY", s[1])
            cmds.setAttr(node_name + ".scaleZ", s[2])

    create_kwargs = {}
    if name:
        create_kwargs["name"] = name

    created = None
    history = None

    # --------------------------------------------------
    # 根据 primitive_type 创建基础几何体
    # --------------------------------------------------
    if primitive_type == "cube":
        # cube 用 size 作为统一边长
        created, history = cmds.polyCube(
            w=size,
            h=size,
            d=size,
            **create_kwargs
        )

    elif primitive_type == "sphere":
        created, history = cmds.polySphere(
            r=radius,
            **create_kwargs
        )

    elif primitive_type == "cylinder":
        created, history = cmds.polyCylinder(
            r=radius,
            h=height,
            **create_kwargs
        )

    elif primitive_type == "plane":
        # plane 优先用 width / depth；如果没传，就退回 size
        plane_w = width if width is not None else size
        plane_h = depth if depth is not None else size
        created, history = cmds.polyPlane(
            w=plane_w,
            h=plane_h,
            **create_kwargs
        )

    elif primitive_type == "cone":
        created, history = cmds.polyCone(
            r=radius,
            h=height,
            **create_kwargs
        )

    elif primitive_type == "torus":
        # Maya torus: radius + sectionRadius
        # 这里简单约定 section radius = radius * 0.25
        created, history = cmds.polyTorus(
            r=radius,
            sr=max(radius * 0.25, 0.001),
            **create_kwargs
        )

    else:
        raise RuntimeError(
            f"Unsupported primitive_type: {primitive_type}. "
            f"Supported: cube, sphere, cylinder, plane, cone, torus"
        )

    if not created or not cmds.objExists(created):
        raise RuntimeError(f"Failed to create primitive: {primitive_type}")

    # 应用 transform
    _apply_transform(created)

    # 返回真实状态
    return {
        "success": True,
        "primitive_type": primitive_type,
        "object": created,
        "history": history,
        "nodeType": cmds.nodeType(created),
        "translate": cmds.xform(created, q=True, t=True, ws=True),
        "rotate": cmds.xform(created, q=True, ro=True, ws=True),
        "scale": [
            cmds.getAttr(created + ".scaleX"),
            cmds.getAttr(created + ".scaleY"),
            cmds.getAttr(created + ".scaleZ"),
        ],
    }
