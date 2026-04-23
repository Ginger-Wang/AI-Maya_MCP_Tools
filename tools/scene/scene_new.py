# tools/scene/scene_new.py
from typing import Dict, Any


def scene_new(force: bool = True) -> Dict[str, Any]:
    """
    Create a new Maya scene.

    Args:
        force (bool): Force creation even if the current scene has unsaved changes.

    Returns:
        Dict[str, Any]: { "success": True }
    """
    import maya.cmds as cmds

    try:
        cmds.file(new=True, force=force)
        # New scenes may be marked dirty; reset modified flag
        cmds.file(modified=False)
        return {"success": True}

    except RuntimeError:
        if not force:
            raise RuntimeError(
                "Unable to create a new scene because of unsaved changes. "
                "Use force=True to force a new scene."
            )
        raise RuntimeError("Unable to create a new scene")
