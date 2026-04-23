from typing import Dict, Any


TOOL_NAME = "freeze_transform"
TOOL_FUNC = "freeze_transform"
TOOL_DESCRIPTION = (
    "Freeze translate / rotate / scale on Maya objects using makeIdentity."
)


def freeze_transform(
    objects,
    translate: bool = True,
    rotate: bool = True,
    scale: bool = True,
    normal: bool = False,
) -> Dict[str, Any]:
    """
    Freeze transform on Maya objects.

    Args:
        objects:
            Object name, list of object names, or string like
            "a b c" / "a,b,c"

        translate (bool): Freeze translate
        rotate (bool): Freeze rotate
        scale (bool): Freeze scale
        normal (bool): Freeze normals flag for makeIdentity

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
        cmds.makeIdentity(
            obj,
            apply=True,
            t=translate,
            r=rotate,
            s=scale,
            n=normal,
            pn=True,
        )
        processed.append(obj)

    cmds.refresh(force=True)

    return {
        "success": True,
        "requested": raw,
        "processed": processed,
        "missing": missing,
    }
