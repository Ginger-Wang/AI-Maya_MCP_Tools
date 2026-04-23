from typing import Dict, Any, Optional


TOOL_NAME = "select_objects"
TOOL_FUNC = "select_objects"
TOOL_DESCRIPTION = "Select objects in the Maya scene. Supports string or list input."


def select_objects(
    objects,
    replace: bool = True,
) -> Dict[str, Any]:
    """
    Select objects in the current Maya scene.

    Args:
        objects: Object name, list of object names, or string like "a b c" / "a,b,c"
        replace (bool): Replace current selection if True

    Returns:
        Dict[str, Any]: Requested / selected / missing
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

    # 去掉空值
    raw = [str(x).strip() for x in raw if str(x).strip()]

    if not raw:
        raise RuntimeError("objects is empty after parsing")

    # --------------------------------------------------
    # 查找真实存在的对象（用 ls(long=True) 更稳）
    # --------------------------------------------------
    found = cmds.ls(raw, long=True) or []

    # 建立“短名/原始输入”维度的 missing 列表
    existing_short = {x.split("|")[-1] for x in found}
    missing = [x for x in raw if x not in existing_short and x not in found]

    # --------------------------------------------------
    # 执行选择
    # --------------------------------------------------
    cmds.select(clear=True)

    if found:
        cmds.select(found, replace=replace)

    cmds.refresh(force=True)

    return {
        "success": True,
        "requested": raw,
        "selected": cmds.ls(sl=True, long=True) or [],
        "missing": missing,
    }
