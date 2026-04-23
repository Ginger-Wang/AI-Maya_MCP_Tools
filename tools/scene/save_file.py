from typing import Dict, Any


TOOL_NAME = "save_file"
TOOL_FUNC = "save_file"
TOOL_DESCRIPTION = "Save the current Maya scene. If path is provided, save as that file."


def save_file(path: str = "") -> Dict[str, Any]:
    """
    Save the current Maya scene.

    Args:
        path (str): Optional. If given, performs Save As.

    Returns:
        Dict[str, Any]: Save result and file state
    """
    import os
    import maya.cmds as cmds

    before = {
        "currentFile": cmds.file(q=True, sn=True),
        "modified": cmds.file(q=True, modified=True),
    }

    # --------------------------------------------------
    # Save As
    # --------------------------------------------------
    if path:
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            raise RuntimeError(f"Directory does not exist: {directory}")

        ext = os.path.splitext(path)[1].lower()
        if ext == ".ma":
            file_type = "mayaAscii"
        elif ext == ".mb":
            file_type = "mayaBinary"
        else:
            raise RuntimeError(
                "Unsupported file extension. Use .ma or .mb"
            )

        try:
            cmds.file(rename=path)
            cmds.file(save=True, type=file_type)
        except RuntimeError as e:
            raise RuntimeError("Unable to save scene as file: " + str(e))

    # --------------------------------------------------
    # Save current file
    # --------------------------------------------------
    else:
        current = cmds.file(q=True, sn=True)
        if not current:
            raise RuntimeError(
                "Current scene has no filename. Please provide path for Save As."
            )

        try:
            cmds.file(save=True)
        except RuntimeError as e:
            raise RuntimeError("Unable to save current scene: " + str(e))

    after_file = cmds.file(q=True, sn=True)

    return {
        "success": True,
        "before": before,
        "after": {
            "currentFile": after_file,
            "modified": cmds.file(q=True, modified=True),
            "existsOnDisk": os.path.exists(after_file) if after_file else False,
        },
    }
