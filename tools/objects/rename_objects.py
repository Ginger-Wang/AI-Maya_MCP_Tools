from typing import Dict, Any, Optional


TOOL_NAME = "rename_objects"
TOOL_FUNC = "rename_objects"
TOOL_DESCRIPTION = (
    "Rename one or more Maya objects. "
    "Single rename uses old_name + new_name. "
    "Batch rename uses objects + base_name."
)


def rename_objects(
    old_name: str = "",
    new_name: str = "",
    objects=None,
    base_name: str = "",
    padding: int = 2,
) -> Dict[str, Any]:
    """
    Rename Maya objects.

    Usage:
    1) Single rename:
        old_name=\"pCube1\", new_name=\"myCube\"

    2) Batch rename:
        objects=[\"a\", \"b\", \"c\"], base_name=\"ctrl\"

    Args:
        old_name (str): Old name for single rename
        new_name (str): New name for single rename
        objects: List / string input for batch rename
        base_name (str): Base name for batch rename
        padding (int): Number padding for batch rename

    Returns:
        Dict[str, Any]
    """
    import maya.cmds as cmds

    # --------------------------------------------------
    # 单个重命名
    # --------------------------------------------------
    if old_name and new_name:
        found = cmds.ls(old_name, long=True) or []
        if not found:
            raise RuntimeError(f"Object not found: {old_name}")

        target = found[0]
        renamed = cmds.rename(target, new_name)
        cmds.refresh(force=True)

        return {
            "success": True,
            "mode": "single",
            "old_name": old_name,
            "new_name": renamed,
        }

    # --------------------------------------------------
    # 批量重命名
    # --------------------------------------------------
    raw = objects

    if raw is None:
        raise RuntimeError(
            "Either provide old_name + new_name, or objects + base_name"
        )

    if isinstance(raw, str):
        raw = raw.replace(",", " ").split()

    if not isinstance(raw, (list, tuple)):
        raise RuntimeError(
            f"objects must be a string or list of object names, got: {raw}"
        )

    raw = [str(x).strip() for x in raw if str(x).strip()]
    if not raw:
        raise RuntimeError("objects is empty after parsing")

    if not base_name:
        raise RuntimeError("base_name is required for batch rename")

    found = cmds.ls(raw, long=True) or []
    existing_short = {x.split("|")[-1] for x in found}
    missing = [x for x in raw if x not in existing_short and x not in found]

    renamed = []
    for idx, obj in enumerate(found, start=1):
        new_obj_name = f"{base_name}_{idx:0{padding}d}"
        final_name = cmds.rename(obj, new_obj_name)
        renamed.append({
            "old": obj,
            "new": final_name,
        })

    cmds.refresh(force=True)

    return {
        "success": True,
        "mode": "batch",
        "requested": raw,
        "renamed": renamed,
        "missing": missing,
    }
