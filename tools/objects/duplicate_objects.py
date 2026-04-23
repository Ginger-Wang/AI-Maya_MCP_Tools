from typing import Dict, Any


TOOL_NAME = "duplicate_objects"
TOOL_FUNC = "duplicate_objects"
TOOL_DESCRIPTION = (
    "Duplicate objects in the Maya scene. "
    "Supports string or list input. Returns duplicated objects."
)


def duplicate_objects(
    objects,
    rename_children: bool = True,
) -> Dict[str, Any]:
    """
    Duplicate objects in the current Maya scene.

    Args:
        objects:
            Object name, list of object names, or string like
            "a b c" / "a,b,c"

        rename_children (bool):
            Passed to cmds.duplicate(renameChildren=...)

    Returns:
        Dict[str, Any]:
            Requested / found / duplicated / missing
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

    duplicated = []
    if found:
        duplicated = cmds.duplicate(found, renameChildren=rename_children) or []
        cmds.refresh(force=True)

    return {
        "success": True,
        "requested": raw,
        "found": found,
        "duplicated": duplicated,
        "missing": missing,
    }
