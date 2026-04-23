from typing import Dict, Any


TOOL_NAME = "skin_normalize_weights"
TOOL_FUNC = "normalize_skin_weights"
TOOL_DESCRIPTION = "Normalize weights on a skinCluster or skinned geometry."


def normalize_skin_weights(target: str) -> Dict[str, Any]:
    """
    Normalize skin weights on a skinCluster or skinned geometry.

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

    cmds.skinCluster(skin_cluster, e=True, forceNormalizeWeights=True)
    cmds.refresh(force=True)

    return {
        "success": True,
        "target": node,
        "skinCluster": skin_cluster,
        "normalized": True,
    }
