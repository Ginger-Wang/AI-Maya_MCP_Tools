from typing import Dict, Any


TOOL_NAME = "skin_bind"
TOOL_FUNC = "bind_skin"
TOOL_DESCRIPTION = (
    "Bind joints to geometry using Maya skinCluster."
)


def bind_skin(
    geometry: str,
    joints,
    skin_method: int = 0,
    normalize_weights: int = 1,
    maximum_influences: int = 4,
    dropoff_rate: float = 4.0,
    remove_unused_influence: bool = True,
    to_selected_bones: bool = True,
) -> Dict[str, Any]:
    """
    Bind skin to geometry.

    Args:
        geometry (str):
            Geometry transform name.

        joints:
            Joint list or string:
            - "joint1 joint2 joint3"
            - "joint1,joint2,joint3"
            - ["joint1", "joint2", "joint3"]

        skin_method (int):
            0 = Classic Linear
            1 = Dual Quaternion
            2 = Weight Blended

        normalize_weights (int):
            Maya normalizeWeights flag.

        maximum_influences (int):
            Maximum influences per vertex.

        dropoff_rate (float):
            SkinCluster dropoff rate.

        remove_unused_influence (bool):
            Remove unused influences.

        to_selected_bones (bool):
            Preserve parameter for future extension.

    Returns:
        Dict[str, Any]
    """
    import maya.cmds as cmds

    if not geometry:
        raise RuntimeError("geometry is required")

    geo_found = cmds.ls(geometry, long=True) or []
    if not geo_found:
        raise RuntimeError(f"Geometry not found: {geometry}")

    geo = geo_found[0]

    raw = joints
    if raw is None:
        raise RuntimeError("joints is required")

    if isinstance(raw, str):
        raw = raw.replace(",", " ").split()

    if not isinstance(raw, (list, tuple)):
        raise RuntimeError(f"joints must be a string or list of joint names, got: {raw}")

    raw = [str(x).strip() for x in raw if str(x).strip()]
    if not raw:
        raise RuntimeError("joints is empty after parsing")

    found_joints = cmds.ls(raw, type="joint", long=True) or []
    if not found_joints:
        raise RuntimeError("No valid joints found")

    existing_short = {x.split("|")[-1] for x in found_joints}
    missing = [x for x in raw if x not in existing_short and x not in found_joints]

    # 如果已经有 skinCluster，先报错，避免重复绑定混乱
    history = cmds.listHistory(geo) or []
    existing_skin = cmds.ls(history, type="skinCluster") or []
    if existing_skin:
        raise RuntimeError(
            f"Geometry already has skinCluster: {existing_skin[0]}"
        )

    skin_cluster = cmds.skinCluster(
        found_joints,
        geo,
        toSelectedBones=to_selected_bones,
        skinMethod=skin_method,
        normalizeWeights=normalize_weights,
        maximumInfluences=maximum_influences,
        dropoffRate=dropoff_rate,
        removeUnusedInfluence=remove_unused_influence,
    )[0]

    cmds.refresh(force=True)

    return {
        "success": True,
        "geometry": geo,
        "skinCluster": skin_cluster,
        "influences": cmds.skinCluster(skin_cluster, q=True, inf=True) or [],
        "missing": missing,
    }
