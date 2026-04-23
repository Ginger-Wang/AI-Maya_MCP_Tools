from typing import Dict, Any


TOOL_NAME = "open_file"
TOOL_FUNC = "open_file"
TOOL_DESCRIPTION = "Open a Maya scene file. Use force=True to discard unsaved changes."


def open_file(path: str, force: bool = True) -> Dict[str, Any]:
    """
    Open a Maya scene file.

    Args:
        path (str): Full path to the Maya file (.ma / .mb)
        force (bool): Force open even if current scene has unsaved changes

    Returns:
        Dict[str, Any]: Scene state after open
    """
    import os
    import maya.cmds as cmds

    if not path:
        raise RuntimeError("path is required")

    if not os.path.exists(path):
        raise RuntimeError(f"File does not exist: {path}")

    try:
        cmds.file(path, open=True, force=force)

        return {
            "success": True,
            "opened": path,
            "currentFile": cmds.file(q=True, sn=True),
            "modified": cmds.file(q=True, modified=True),
            "assemblies": cmds.ls(assemblies=True),
        }

    except RuntimeError as e:
        if not force:
            raise RuntimeError(
                "Unable to open scene because of unsaved changes. "
                "Use force=True to force open."
            )
        raise RuntimeError("Unable to open scene: " + str(e))
