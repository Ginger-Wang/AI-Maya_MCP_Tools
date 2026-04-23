from typing import Dict, Any


TOOL_NAME = "delete_objects"
TOOL_FUNC = "delete_objects"
TOOL_DESCRIPTION = "Delete objects in the Maya scene. Supports string or list input. Destructive operation."


def delete_objects(objects) -> Dict[str, Any]:
    """
    Delete objects in the current Maya scene.

    Args:
        objects: Object name, list of object names, or string like "a b c" / "a,b,c"

    Returns:
        Dict[str, Any]: Requested / deleted / missing
    """
    import maya.cmds as cmds

    # --------------------------------------------------
    # 解析输入
    # --------------------------------------------------
    raw = objects

    if raw is None:
        raise RuntimeError("objects is required")

    if isinstance(raw, str):
        raw = raw.replace(",", " ").split()

    if not isinstance(raw, (list, tuple)):
        raise RuntimeError(
            f"objects must be a string or list of object names, got: {raw}"
        )

    raw = [str(x).strip() for x in raw if str(x).strip()]

    if not raw:
        raise RuntimeError("objects is empty after parsing")

    # --------------------------------------------------
    # 查找真实存在的对象
    # 用 long=True 避免层级路径 / 同名 transform 问题
    # --------------------------------------------------
    found = cmds.ls(raw, long=True) or []

    existing_short = {x.split("|")[-1] for x in found}
    missing = [x for x in raw if x not in existing_short and x not in found]

    # --------------------------------------------------
    # 删除
    # --------------------------------------------------
    if found:
        cmds.delete(found)
        cmds.refresh(force=True)

    return {
        "success": True,
        "requested": raw,
        "deleted": found,
        "missing": missing,
    }
