from typing import Dict, Any, Optional


TOOL_NAME = "skin_copy_weights"
TOOL_FUNC = "copy_skin_weights"
TOOL_DESCRIPTION = (
    "Copy skin binding and weights from a source skinned mesh to a target mesh. "
    "Supports two modes: "
    "1) copy current skin+weights to another mesh "
    "2) rebind to another same-named skeleton and copy weights."
)


def copy_skin_weights(
    source_geometry: str,
    target_geometry: str = "",
    mode: str = "copy",
    replace_existing_skin: bool = True,
    target_joint_root: str = "",
    target_joints=None,
    surface_association: str = "closestPoint",
    influence_association: str = "closestJoint",
    normalize: bool = True,
    maximum_influences: int = 4,
    bind_method: int = 0,
) -> Dict[str, Any]:
    """
    Copy skin binding and weights.

    Modes
    -----
    1) mode = "copy"
       Copy source skin + weights to target geometry.
       Target may have no skin, or may already have wrong skin.

    2) mode = "replace_skeleton"
       Use another skeleton (same-named joints) on target geometry,
       then copy weights from source.

    Args
    ----
    source_geometry (str):
        Source mesh with correct skin and weights.

    target_geometry (str):
        Target mesh to receive skin/weights.
        If empty, defaults to source_geometry.
        For "replace_skeleton" mode, it can be the same mesh or another mesh.

    mode (str):
        "copy" or "replace_skeleton"

    replace_existing_skin (bool):
        If target already has skinCluster, unbind/remove it before rebinding.

    target_joint_root (str):
        Root joint of replacement skeleton (used in replace_skeleton mode).

    target_joints:
        Optional explicit joint list for replacement skeleton.
        Supports:
        - "j1 j2 j3"
        - "j1,j2,j3"
        - ["j1", "j2", "j3"]

    surface_association (str):
        closestPoint / closestComponent / rayCast

    influence_association (str):
        Used in normal copy mode.
        closestJoint / oneToOne / label / name

    normalize (bool):
        Force normalize target weights after copy.

    maximum_influences (int):
        Maximum influences when creating target skinCluster.

    bind_method (int):
        0 = Classic Linear
        1 = Dual Quaternion
        2 = Weight Blended

    Returns
    -------
    Dict[str, Any]
    """
    import maya.cmds as cmds

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------
    def _as_name_list(raw, label):
        if raw is None:
            return []

        if isinstance(raw, str):
            raw = raw.replace(",", " ").split()

        if not isinstance(raw, (list, tuple)):
            raise RuntimeError(f"{label} must be a string or list, got: {raw}")

        values = [str(x).strip() for x in raw if str(x).strip()]
        return values

    def _find_one(node_name: str, label: str) -> str:
        found = cmds.ls(node_name, long=True) or []
        if not found:
            raise RuntimeError(f"{label} not found: {node_name}")
        return found[0]

    def _get_skin_cluster(geo_or_skin: str) -> Optional[str]:
        found = cmds.ls(geo_or_skin, long=True) or []
        if not found:
            return None

        node = found[0]
        if cmds.nodeType(node) == "skinCluster":
            return node

        history = cmds.listHistory(node) or []
        skins = cmds.ls(history, type="skinCluster") or []
        return skins[0] if skins else None

    def _short_no_namespace(name: str) -> str:
        short_name = name.split("|")[-1]
        short_name = short_name.split(":")[-1]
        return short_name

    def _collect_joints_from_root(root_joint: str):
        root_found = cmds.ls(root_joint, type="joint", long=True) or []
        if not root_found:
            raise RuntimeError(f"target_joint_root not found or not a joint: {root_joint}")

        root = root_found[0]
        children = cmds.listRelatives(root, ad=True, type="joint", fullPath=True) or []
        all_joints = [root] + list(reversed(children))
        return all_joints

    def _unbind_existing_skin(target_geo: str):
        skin = _get_skin_cluster(target_geo)
        if skin:
            try:
                cmds.skinCluster(skin, e=True, unbind=True)
            except Exception:
                # 如果 edit/unbind 不行，再尝试 delete
                try:
                    cmds.delete(skin)
                except Exception:
                    pass

    def _duplicate_source_as_temp_with_history(src_geo: str):
        """
        用于 source_geometry == target_geometry 且要换骨骼时，
        先复制一份临时源，保留 skin history 作为 copy source。
        """
        dup = cmds.duplicate(src_geo, upstreamNodes=True, returnRootsOnly=True)[0]
        skin = _get_skin_cluster(dup)
        if not skin:
            raise RuntimeError(
                "Failed to build temporary duplicated source with skin history."
            )
        return dup, skin

    # --------------------------------------------------
    # Validate source / target
    # --------------------------------------------------
    if not source_geometry:
        raise RuntimeError("source_geometry is required")

    source_geo = _find_one(source_geometry, "source_geometry")

    if not target_geometry:
        target_geometry = source_geometry

    target_geo = _find_one(target_geometry, "target_geometry")

    source_skin = _get_skin_cluster(source_geo)
    if not source_skin:
        raise RuntimeError(f"Source geometry has no skinCluster: {source_geo}")

    source_influences = cmds.skinCluster(source_skin, q=True, inf=True) or []
    if not source_influences:
        raise RuntimeError(f"Source skinCluster has no influences: {source_skin}")

    source_geo_for_copy = source_geo
    source_skin_for_copy = source_skin

    # --------------------------------------------------
    # If target == source and we need to destroy target skin,
    # first build a temporary duplicate as weight source
    # --------------------------------------------------
    if replace_existing_skin and source_geo == target_geo:
        source_geo_for_copy, source_skin_for_copy = _duplicate_source_as_temp_with_history(source_geo)

    # --------------------------------------------------
    # Determine target influences
    # --------------------------------------------------
    target_influences = []

    if mode == "copy":
        # 直接用 source influences
        target_influences = list(source_influences)

    elif mode == "replace_skeleton":
        # 目标骨骼来自 target_joints 或 target_joint_root
        candidate_joints = _as_name_list(target_joints, "target_joints")

        if candidate_joints:
            candidate_joints = cmds.ls(candidate_joints, type="joint", long=True) or []
        elif target_joint_root:
            candidate_joints = _collect_joints_from_root(target_joint_root)
        else:
            raise RuntimeError(
                "replace_skeleton mode requires target_joint_root or target_joints"
            )

        if not candidate_joints:
            raise RuntimeError("No valid replacement joints found")

        # 建立短名映射
        candidate_map = {}
        for j in candidate_joints:
            key = _short_no_namespace(j)
            if key not in candidate_map:
                candidate_map[key] = j

        missing_influences = []
        mapped_influences = []

        for src_inf in source_influences:
            key = _short_no_namespace(src_inf)
            if key not in candidate_map:
                missing_influences.append(src_inf)
            else:
                mapped_influences.append(candidate_map[key])

        if missing_influences:
            raise RuntimeError(
                "Replacement skeleton is missing matching joints: "
                + ", ".join(missing_influences)
            )

        target_influences = mapped_influences

    else:
        raise RuntimeError(
            f"Unsupported mode: {mode}. Supported: copy / replace_skeleton"
        )

    if not target_influences:
        raise RuntimeError("No target influences resolved")

    # --------------------------------------------------
    # Remove target existing skin if requested
    # --------------------------------------------------
    if replace_existing_skin:
        _unbind_existing_skin(target_geo)

    # --------------------------------------------------
    # Create target skin
    # --------------------------------------------------
    target_skin = _get_skin_cluster(target_geo)
    if not target_skin:
        target_skin = cmds.skinCluster(
            target_influences,
            target_geo,
            toSelectedBones=True,
            skinMethod=bind_method,
            normalizeWeights=1,
            maximumInfluences=maximum_influences,
        )[0]

    # --------------------------------------------------
    # Copy weights
    # --------------------------------------------------
    if mode == "copy":
        # 正常复制：source/target influence 相同或高度接近
        cmds.copySkinWeights(
            ss=source_skin_for_copy,
            ds=target_skin,
            noMirror=True,
            surfaceAssociation=surface_association,
            influenceAssociation=[influence_association, "closestJoint", "oneToOne"],
        )
    else:
        # 换骨骼模式：target_influences 已按 source influence 顺序映射
        # 优先用 oneToOne，避免 namespace / DAG path 导致 name 匹配失败
        cmds.copySkinWeights(
            ss=source_skin_for_copy,
            ds=target_skin,
            noMirror=True,
            surfaceAssociation=surface_association,
            influenceAssociation=["oneToOne", "closestJoint"],
        )

    if normalize:
        cmds.skinCluster(target_skin, e=True, forceNormalizeWeights=True)

    cmds.refresh(force=True)

    # --------------------------------------------------
    # Clean temp
    # --------------------------------------------------
    temp_deleted = False
    if source_geo_for_copy != source_geo and cmds.objExists(source_geo_for_copy):
        try:
            cmds.delete(source_geo_for_copy)
            temp_deleted = True
        except Exception:
            pass

    return {
        "success": True,
        "mode": mode,
        "source_geometry": source_geo,
        "target_geometry": target_geo,
        "source_skin": source_skin_for_copy,
        "target_skin": target_skin,
        "source_influences": source_influences,
        "target_influences": cmds.skinCluster(target_skin, q=True, inf=True) or [],
        "temp_source_deleted": temp_deleted,
    }
