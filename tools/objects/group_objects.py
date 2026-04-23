from typing import Dict, Any


TOOL_NAME = "group_objects"
TOOL_FUNC = "group_objects"
TOOL_DESCRIPTION = (
    "Group Maya objects. "
    "If objects are provided, group them. "
    "If not, create an empty group."
)


def group_objects(
    objects=None,
    group_name: str = "group1",
    world: bool = True,
) -> Dict[str, Any]:
    """
    Group Maya objects.

    Args:
        objects:
            Object name, list of object names, or string like
            "a b c" / "a,b,c".
            If None, creates an empty group.

        group_name (str):
            Name of the new group.

        world (bool):
            Whether to create group under world.

    Returns:
        Dict[str, Any]
    """
    import maya.cmds as cmds

    # --------------------------------------------------
    # 创建空组
    # --------------------------------------------------
    if objects is None or objects == "":
        grp = cmds.group(empty=True, name=group_name, world=world)
        cmds.refresh(force=True)
        return {
            "success": True,
            "mode": "empty_group",
            "group": grp,
        }

    raw = objects

    if isinstance(raw, str):
        raw = raw.replace(",", " ").split()

    if not isinstance(raw, (list, tuple)):
        raise RuntimeError(
            f"objects must be a string or list of object names, got: {raw}"
        )

    raw = [str(x).strip() for x in raw if str(x).strip()]
    if not raw:
        raise RuntimeError("objects is empty after parsing")

    found = cmds.ls(raw, long=True) or []
    existing_short = {x.split("|")[-1] for x in found}
    missing = [x for x in raw if x not in existing_short and x not in found]

    if not found:
        raise RuntimeError("No valid objects found to group")

    grp = cmds.group(found, name=group_name, world=world)
    cmds.refresh(force=True)

    return {
        "success": True,
        "mode": "group_objects",
        "requested": raw,
        "group": grp,
        "children": cmds.listRelatives(grp, children=True, fullPath=True) or [],
        "missing": missing,
    }
