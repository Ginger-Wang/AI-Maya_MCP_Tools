from typing import Dict, Any, Optional


def set_transform(
    node: str,
    translate=None,
    rotate=None,
    scale=None,
    world_space: bool = True,
) -> Dict[str, Any]:
    """
    Tags: objects, modify, transform

    统一设置 Transform（translate / rotate / scale）
    - 支持 list / tuple / 字符串输入
    - commandPort / MCP / LLM 安全
    """

    import ast
    import maya.cmds as cmds

    if not node:
        raise RuntimeError("node is required")

    if not cmds.objExists(node):
        raise RuntimeError("Object does not exist: " + node)

    def _parse_vec3(raw, label):
        if raw is None:
            return None
        if isinstance(raw, str):
            text = raw.strip()

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
                    raise RuntimeError(
                        f"{label} must be numeric values, got: {raw}"
                    )

                if len(values) != 3:
                    raise RuntimeError(
                        f"{label} must have exactly 3 values (x y z), got: {values}"
                    )

                return values

        # list / tuple / 其它可迭代对象
        try:
            values = [float(v) for v in raw]
        except Exception:
            raise RuntimeError(
                f"{label} must be numeric values, got: {raw}"
            )

        if len(values) != 3:
            raise RuntimeError(
                f"{label} must have exactly 3 values (x y z), got: {values}"
            )

        return values

    # --------------------
    # Translate
    # --------------------
    if translate is not None:
        t = _parse_vec3(translate, "Translate")
        if t is not None:
            cmds.xform(node, t=t, ws=world_space)

    # --------------------
    # Rotate
    # --------------------
    if rotate is not None:
        r = _parse_vec3(rotate, "Rotate")
        if r is not None:
            cmds.xform(node, ro=r, ws=world_space)

    # --------------------
    # Scale（逐轴 setAttr，绝对稳定）
    # --------------------
    if scale is not None:
        s = _parse_vec3(scale, "Scale")
        if s is not None:
            cmds.setAttr(node + ".scaleX", s[0])
            cmds.setAttr(node + ".scaleY", s[1])
            cmds.setAttr(node + ".scaleZ", s[2])

    return {
        "success": True,
        "node": node,
        "translate": cmds.xform(node, q=True, t=True, ws=True),
        "rotate": cmds.xform(node, q=True, ro=True, ws=True),
        "scale": [
            cmds.getAttr(node + ".scaleX"),
            cmds.getAttr(node + ".scaleY"),
            cmds.getAttr(node + ".scaleZ"),
        ],
    }
