from typing import Dict, Any


TOOL_NAME = "skin_get_influences"
TOOL_FUNC = "get_skin_influences"
TOOL_DESCRIPTION = "Get influence joints of a skinned geometry or skinCluster."


def get_skin_influences(target: str) -> Dict[str, Any]:
    """
    Get influences from a geometry or a skinCluster node.

    Args:
        target (str):
            Geometry transform or skinCluster name.

    Returns:
        Dict[str, Any]
    """
    import maya.cmds as cmds

    if not target:
        raise RuntimeError("target is required")

    found = cmds.ls(target, long=True) or []
    if not found:
        raise RuntimeError(f"Target not found: {target}")

    node = found[0]

    skin_cluster = None

    if cmds.nodeType(node) == "skinCluster":
        skin_cluster = node
    else:
        history = cmds.listHistory(node) or []
        skins = cmds.ls(history, type="skinCluster") or []
        if skins:
            skin_cluster = skins[0]

    if not skin_cluster:
        raise RuntimeError(f"No skinCluster found for target: {target}")

    influences = cmds.skinCluster(skin_cluster, q=True, inf=True) or []

    return {
        "success": True,
        "target": node,
        "skinCluster": skin_cluster,
        "count": len(influences),
        "influences": influences,
    }
