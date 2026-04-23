from typing import Dict, Any


TOOL_NAME = "reset_transform"
TOOL_FUNC = "reset_transform"
TOOL_DESCRIPTION = (
    "Reset translate / rotate / scale on Maya objects to default values."
)


def reset_transform(
    objects,
    translate: bool = True,
    rotate: bool = True,
    scale: bool = True,
) -> Dict[str, Any]:
    """
    Reset transform values on Maya objects.

    Args:
        objects:
            Object name, list of object names, or string like
            "a b c" / "a,b,c"

        translate (bool): Reset translate to 0
        rotate (bool): Reset rotate to 0
        scale (bool): Reset scale to 1

    Returns:
        Dict[str, Any]
    """
    import maya.cmds as cmds

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

    found = cmds.ls(raw, long=True) or []
    existing_short = {x.split("|")[-1] for x in found}
    missing = [x for x in raw if x not in existing_short and x not in found]

    processed = []
    for obj in found:
        if translate:
            cmds.setAttr(obj + ".translateX", 0)
            cmds.setAttr(obj + ".translateY", 0)
            cmds.setAttr(obj + ".translateZ", 0)

        if rotate:
            cmds.setAttr(obj + ".rotateX", 0)
            cmds.setAttr(obj + ".rotateY", 0)
            cmds.setAttr(obj + ".rotateZ", 0)

        if scale:
            cmds.setAttr(obj + ".scaleX", 1)
            cmds.setAttr(obj + ".scaleY", 1)
            cmds.setAttr(obj + ".scaleZ", 1)

        processed.append(obj)

    cmds.refresh(force=True)

    return {
        "success": True,
        "requested": raw,
        "processed": processed,
        "missing": missing,
    }
