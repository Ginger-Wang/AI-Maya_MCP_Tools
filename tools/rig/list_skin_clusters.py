from typing import Dict, Any


TOOL_NAME = "skin_list_clusters"
TOOL_FUNC = "list_skin_clusters"
TOOL_DESCRIPTION = "List all skinCluster nodes in the Maya scene."


def list_skin_clusters(long_name: bool = False) -> Dict[str, Any]:
    """
    List all skinCluster nodes in the current Maya scene.

    Args:
        long_name (bool): Return long names if available.

    Returns:
        Dict[str, Any]
    """
    import maya.cmds as cmds

    skins = cmds.ls(type="skinCluster", long=long_name) or []

    return {
        "success": True,
        "count": len(skins),
        "skinClusters": skins,
    }
