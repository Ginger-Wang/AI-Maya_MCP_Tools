from typing import Dict, Any, Optional


TOOL_NAME = "auto_humanoid_skeleton"
TOOL_FUNC = "auto_humanoid_skeleton"
TOOL_DESCRIPTION = (
    "Analyze a humanoid mesh using cross-section sampling, estimate body landmarks, "
    "apply body template adjustment, and optionally build a MetaHuman-style skeleton."
)


def auto_humanoid_skeleton(
    geometry: str,
    mode: str = "build",                     # analyze / build
    name_prefix: str = "char",

    body_template: str = "auto",            # auto / male / female / child / heroic / stylized
    template_strength: float = 0.65,        # 0.0 ~ 1.0

    create_guides: bool = True,
    create_joints: bool = True,
    include_fingers: bool = True,
    include_toes: bool = True,

    create_debug_sections: bool = False,
    debug_section_count: int = 48,

    preserve_feet_on_ground: bool = True,
    preserve_hand_reach: bool = False,

    joint_radius: float = 1.0,
    guide_scale: float = 1.0,
    parent_under_group: bool = True,
) -> Dict[str, Any]:
    """
    Analyze a humanoid mesh and estimate humanoid skeleton guide points.

    Improvements over v1:
        - uses vertical cross-section sampling
        - uses width / depth curves
        - detects neck / shoulder / pelvis from section change
        - tracks left/right body halves more robustly

    Best suited for:
        - standing humanoid
        - T-pose / A-pose
        - roughly symmetric character

    Coordinate assumption:
        X = left / right
        Y = up
        Z = forward / backward
    """
    import math
    import maya.cmds as cmds
    import maya.api.OpenMaya as om

    # --------------------------------------------------
    # Templates
    # --------------------------------------------------
    BODY_TEMPLATES = {
        "male": {
            "head_height_ratio": 0.130,
            "shoulder_width_ratio": 0.255,
            "hip_width_ratio": 0.180,
            "torso_length_ratio": 0.310,
            "arm_length_ratio": 0.365,
            "leg_length_ratio": 0.495,
            "neck_length_ratio": 0.055,
            "hand_length_ratio": 0.110,
            "foot_length_ratio": 0.150,
        },
        "female": {
            "head_height_ratio": 0.132,
            "shoulder_width_ratio": 0.235,
            "hip_width_ratio": 0.195,
            "torso_length_ratio": 0.300,
            "arm_length_ratio": 0.360,
            "leg_length_ratio": 0.510,
            "neck_length_ratio": 0.060,
            "hand_length_ratio": 0.108,
            "foot_length_ratio": 0.145,
        },
        "child": {
            "head_height_ratio": 0.165,
            "shoulder_width_ratio": 0.210,
            "hip_width_ratio": 0.170,
            "torso_length_ratio": 0.270,
            "arm_length_ratio": 0.315,
            "leg_length_ratio": 0.435,
            "neck_length_ratio": 0.050,
            "hand_length_ratio": 0.095,
            "foot_length_ratio": 0.125,
        },
        "heroic": {
            "head_height_ratio": 0.120,
            "shoulder_width_ratio": 0.290,
            "hip_width_ratio": 0.175,
            "torso_length_ratio": 0.330,
            "arm_length_ratio": 0.390,
            "leg_length_ratio": 0.520,
            "neck_length_ratio": 0.058,
            "hand_length_ratio": 0.115,
            "foot_length_ratio": 0.155,
        },
        "stylized": {
            "head_height_ratio": 0.145,
            "shoulder_width_ratio": 0.260,
            "hip_width_ratio": 0.190,
            "torso_length_ratio": 0.290,
            "arm_length_ratio": 0.345,
            "leg_length_ratio": 0.470,
            "neck_length_ratio": 0.052,
            "hand_length_ratio": 0.105,
            "foot_length_ratio": 0.140,
        },
    }

    # --------------------------------------------------
    # Utility
    # --------------------------------------------------
    def _resolve_mesh_shape(target: str):
        found = cmds.ls(target, long=True) or []
        if not found:
            raise RuntimeError(f"geometry not found: {target}")

        node = found[0]
        node_type = cmds.nodeType(node)

        if node_type == "mesh":
            return node

        shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
        meshes = [s for s in shapes if cmds.nodeType(s) == "mesh"]

        if not meshes:
            raise RuntimeError(f"No mesh shape found under: {target}")

        return meshes[0]

    def _get_mesh_points_world(mesh_shape: str):
        sel = om.MSelectionList()
        sel.add(mesh_shape)
        dag = sel.getDagPath(0)
        mesh_fn = om.MFnMesh(dag)
        pts = mesh_fn.getPoints(om.MSpace.kWorld)
        return [[p.x, p.y, p.z] for p in pts]

    def _bbox(points):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        zs = [p[2] for p in points]
        return {
            "min_x": min(xs), "max_x": max(xs),
            "min_y": min(ys), "max_y": max(ys),
            "min_z": min(zs), "max_z": max(zs),
        }

    def _center(points):
        if not points:
            return None
        n = float(len(points))
        return [
            sum(p[0] for p in points) / n,
            sum(p[1] for p in points) / n,
            sum(p[2] for p in points) / n,
        ]

    def _distance(a, b):
        return math.sqrt(
            (a[0] - b[0]) ** 2 +
            (a[1] - b[1]) ** 2 +
            (a[2] - b[2]) ** 2
        )

    def _normalize(v):
        l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
        if l < 1e-8:
            return [0.0, 0.0, 0.0]
        return [v[0] / l, v[1] / l, v[2] / l]

    def _lerp(a, b, t):
        return [
            a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t,
        ]

    def _clamp(v, vmin, vmax):
        return max(vmin, min(vmax, v))

    def _moving_average(values, radius=2):
        out = []
        count = len(values)
        for i in range(count):
            vals = values[max(0, i - radius): min(count, i + radius + 1)]
            out.append(sum(vals) / float(len(vals)))
        return out

    def _find_min_index(values, start_idx, end_idx):
        rng = values[start_idx:end_idx + 1]
        if not rng:
            return None
        local_i = min(range(len(rng)), key=lambda i: rng[i])
        return start_idx + local_i

    def _find_max_index(values, start_idx, end_idx):
        rng = values[start_idx:end_idx + 1]
        if not rng:
            return None
        local_i = max(range(len(rng)), key=lambda i: rng[i])
        return start_idx + local_i

    def _make_locator(name, pos):
        loc = cmds.spaceLocator(name=name)[0]
        cmds.xform(loc, ws=True, t=pos)
        try:
            cmds.setAttr(loc + ".localScaleX", guide_scale)
            cmds.setAttr(loc + ".localScaleY", guide_scale)
            cmds.setAttr(loc + ".localScaleZ", guide_scale)
        except Exception:
            pass
        return loc

    def _make_joint(name, pos):
        if cmds.objExists(name):
            raise RuntimeError(f"Joint already exists: {name}")
        j = cmds.createNode("joint", name=name)
        cmds.xform(j, ws=True, t=pos)
        try:
            cmds.setAttr(j + ".radius", max(0.001, 0.45 * joint_radius))
        except Exception:
            pass
        return j

    def _parent_safe(child, parent):
        if child and parent:
            cmds.parent(child, parent)

    def _mh(base_name: str) -> str:
        return f"{name_prefix}_{base_name}"

    def _mh_side(base_name: str, side: str) -> str:
        return f"{name_prefix}_{base_name}_{side}"

    # --------------------------------------------------
    # Section analysis
    # --------------------------------------------------
    def _build_cross_sections(points, bb, count=72):
        height = bb["max_y"] - bb["min_y"]
        width = bb["max_x"] - bb["min_x"]
        depth = bb["max_z"] - bb["min_z"]

        y_min = bb["min_y"]
        y_max = bb["max_y"]
        x_center = (bb["min_x"] + bb["max_x"]) * 0.5

        # section thickness relative to height
        half_band = max(height * 0.006, 0.0005)

        sections = []
        for i in range(count):
            t = i / float(count - 1)
            y = y_min + height * t

            band_points = [p for p in points if abs(p[1] - y) <= half_band]
            if not band_points:
                # widen band if necessary
                band_points = [p for p in points if abs(p[1] - y) <= half_band * 2.0]

            if not band_points:
                sections.append({
                    "index": i,
                    "ratio": t,
                    "y": y,
                    "count": 0,
                    "points": [],
                    "center": [x_center, y, (bb["min_z"] + bb["max_z"]) * 0.5],
                    "width": 0.0,
                    "depth": 0.0,
                    "left_points": [],
                    "right_points": [],
                    "left_center": None,
                    "right_center": None,
                    "left_extreme": None,
                    "right_extreme": None,
                    "front_extreme": None,
                    "back_extreme": None,
                })
                continue

            xs = [p[0] for p in band_points]
            zs = [p[2] for p in band_points]

            left_points = [p for p in band_points if p[0] >= x_center]
            right_points = [p for p in band_points if p[0] < x_center]

            sec = {
                "index": i,
                "ratio": t,
                "y": y,
                "count": len(band_points),
                "points": band_points,
                "center": _center(band_points),
                "width": max(xs) - min(xs),
                "depth": max(zs) - min(zs),
                "left_points": left_points,
                "right_points": right_points,
                "left_center": _center(left_points),
                "right_center": _center(right_points),
                "left_extreme": max(left_points, key=lambda p: p[0]) if left_points else None,
                "right_extreme": min(right_points, key=lambda p: p[0]) if right_points else None,
                "front_extreme": max(band_points, key=lambda p: p[2]),
                "back_extreme": min(band_points, key=lambda p: p[2]),
            }
            sections.append(sec)

        return sections

    def _detect_core_landmarks(sections, bb):
        height = bb["max_y"] - bb["min_y"]
        x_center = (bb["min_x"] + bb["max_x"]) * 0.5
        z_center = (bb["min_z"] + bb["max_z"]) * 0.5

        widths = [s["width"] for s in sections]
        depths = [s["depth"] for s in sections]
        widths_smooth = _moving_average(widths, radius=2)

        count = len(sections)

        def _idx(ratio):
            return int(_clamp(round((count - 1) * ratio), 0, count - 1))

        # search bands
        neck_i = _find_min_index(widths_smooth, _idx(0.84), _idx(0.94))
        shoulder_i = _find_max_index(widths_smooth, _idx(0.74), _idx(0.88))
        chest_i = _find_max_index(widths_smooth, _idx(0.66), _idx(0.82))
        pelvis_i = _find_max_index(widths_smooth, _idx(0.46), _idx(0.62))
        waist_i = _find_min_index(widths_smooth, _idx(0.54), _idx(0.74))
        hip_i = pelvis_i

        if neck_i is None:
            neck_i = _idx(0.89)
        if shoulder_i is None:
            shoulder_i = _idx(0.82)
        if chest_i is None:
            chest_i = _idx(0.75)
        if pelvis_i is None:
            pelvis_i = _idx(0.56)
        if waist_i is None:
            waist_i = _idx(0.64)
        if hip_i is None:
            hip_i = _idx(0.53)

        neck_sec = sections[neck_i]
        shoulder_sec = sections[shoulder_i]
        chest_sec = sections[chest_i]
        pelvis_sec = sections[pelvis_i]
        hip_sec = sections[hip_i]

        # head top
        head_top_sec = sections[_idx(0.99)]

        head_pos = [
            x_center,
            (neck_sec["y"] + head_top_sec["y"]) * 0.5,
            (neck_sec["center"][2] + head_top_sec["center"][2]) * 0.5 if neck_sec["center"] and head_top_sec["center"] else z_center,
        ]

        head_end_pos = [x_center, head_top_sec["y"], head_pos[2]]

        return {
            "neck_i": neck_i,
            "shoulder_i": shoulder_i,
            "chest_i": chest_i,
            "waist_i": waist_i,
            "pelvis_i": pelvis_i,
            "hip_i": hip_i,

            "neck_center": neck_sec["center"] or [x_center, neck_sec["y"], z_center],
            "shoulder_center": shoulder_sec["center"] or [x_center, shoulder_sec["y"], z_center],
            "chest_center": chest_sec["center"] or [x_center, chest_sec["y"], z_center],
            "pelvis_center": pelvis_sec["center"] or [x_center, pelvis_sec["y"], z_center],
            "hip_center": hip_sec["center"] or [x_center, hip_sec["y"], z_center],

            "head": head_pos,
            "head_end": head_end_pos,
        }

    def _estimate_arm_points(points, sections, side="l", x_center=0.0, shoulder_pos=None):
        # side filtering
        if side == "l":
            side_points = [p for p in points if p[0] >= x_center]
        else:
            side_points = [p for p in points if p[0] < x_center]

        if not side_points:
            return None

        # shoulder height band
        shoulder_y = shoulder_pos[1]

        # hand region candidates: farther from center, in upper-mid body
        hand_band = [
            p for p in side_points
            if shoulder_y - 0.34 * body_height <= p[1] <= shoulder_y - 0.02 * body_height
        ]

        if not hand_band:
            hand_band = side_points

        if side == "l":
            hand_extreme = max(hand_band, key=lambda p: p[0])
        else:
            hand_extreme = min(hand_band, key=lambda p: p[0])

        # elbow = shoulder -> hand interpolation, then bias by nearest section
        elbow_guess = _lerp(shoulder_pos, hand_extreme, 0.52)
        elbow_guess[1] = shoulder_y - body_height * 0.13

        hand_guess = _lerp(shoulder_pos, hand_extreme, 1.03)

        return {
            "upperarm": shoulder_pos[:],
            "lowerarm": elbow_guess,
            "hand": hand_guess,
        }

    def _estimate_leg_points(points, sections, side="l", x_center=0.0, pelvis_pos=None, root_y=0.0):
        if side == "l":
            side_points = [p for p in points if p[0] >= x_center]
        else:
            side_points = [p for p in points if p[0] < x_center]

        if not side_points:
            return None

        # section-based estimates
        def _sec_range(r0, r1):
            return [s for s in sections if r0 <= s["ratio"] <= r1]

        thigh_sections = _sec_range(0.46, 0.58)
        knee_sections = _sec_range(0.22, 0.34)
        ankle_sections = _sec_range(0.03, 0.09)
        foot_sections = _sec_range(0.00, 0.08)

        def _side_center_from_sections(sec_list):
            pts = []
            for s in sec_list:
                pts.extend(s["left_points"] if side == "l" else s["right_points"])
            return _center(pts)

        thigh_c = _side_center_from_sections(thigh_sections) or [pelvis_pos[0] + (body_width * 0.08 if side == "l" else -body_width * 0.08), pelvis_pos[1] - body_height * 0.03, pelvis_pos[2]]
        knee_c = _side_center_from_sections(knee_sections) or [thigh_c[0], root_y + body_height * 0.28, thigh_c[2] + body_depth * 0.03]
        ankle_c = _side_center_from_sections(ankle_sections) or [thigh_c[0], root_y + body_height * 0.06, thigh_c[2] + body_depth * 0.02]

        foot_pts = []
        for s in foot_sections:
            foot_pts.extend(s["left_points"] if side == "l" else s["right_points"])

        if foot_pts:
            front_foot = max(foot_pts, key=lambda p: p[2])
        else:
            front_foot = [ankle_c[0], root_y + body_height * 0.02, ankle_c[2] + body_depth * 0.18]

        foot_c = [ankle_c[0], max(root_y + body_height * 0.01, ankle_c[1] - body_height * 0.02), ankle_c[2]]
        ball_c = _lerp(foot_c, front_foot, 0.55)

        return {
            "thigh": [thigh_c[0], pelvis_pos[1] - body_height * 0.02, thigh_c[2]],
            "calf": [knee_c[0], knee_c[1], knee_c[2]],
            "foot": foot_c,
            "ball": ball_c,
            "toe_tip": front_foot,
        }

    def _extract_measurements(core_guides):
        height = abs(core_guides["head_end"][1] - core_guides["root"][1])
        if height < 1e-6:
            height = 1.0

        shoulder_width = abs(core_guides["upperarm_l"][0] - core_guides["upperarm_r"][0])
        hip_width = abs(core_guides["thigh_l"][0] - core_guides["thigh_r"][0])

        torso_length = _distance(core_guides["pelvis"], core_guides["spine_05"])
        neck_length = _distance(core_guides["spine_05"], core_guides["neck_01"])
        head_height = _distance(core_guides["neck_01"], core_guides["head_end"])

        arm_length = (
            _distance(core_guides["upperarm_l"], core_guides["lowerarm_l"]) +
            _distance(core_guides["lowerarm_l"], core_guides["hand_l"])
        )
        leg_length = (
            _distance(core_guides["thigh_l"], core_guides["calf_l"]) +
            _distance(core_guides["calf_l"], core_guides["foot_l"])
        )
        hand_length = _distance(core_guides["lowerarm_l"], core_guides["hand_l"]) * 0.55
        foot_length = _distance(core_guides["foot_l"], core_guides["ball_l"])

        return {
            "height": height,
            "head_height_ratio": head_height / height,
            "shoulder_width_ratio": shoulder_width / height,
            "hip_width_ratio": hip_width / height,
            "torso_length_ratio": torso_length / height,
            "neck_length_ratio": neck_length / height,
            "arm_length_ratio": arm_length / height,
            "leg_length_ratio": leg_length / height,
            "hand_length_ratio": hand_length / height,
            "foot_length_ratio": foot_length / height,
        }

    def _choose_body_template(measurements, requested_template):
        requested_template = (requested_template or "auto").strip().lower()

        if requested_template != "auto":
            if requested_template not in BODY_TEMPLATES:
                raise RuntimeError(
                    f"Unsupported body_template: {requested_template}. "
                    f"Supported: auto, {sorted(BODY_TEMPLATES.keys())}"
                )
            return requested_template

        weights = {
            "head_height_ratio": 2.0,
            "shoulder_width_ratio": 2.0,
            "hip_width_ratio": 1.5,
            "torso_length_ratio": 2.0,
            "leg_length_ratio": 2.0,
        }

        best_name = None
        best_score = None

        for template_name, template in BODY_TEMPLATES.items():
            score = 0.0
            for key, w in weights.items():
                score += abs(measurements[key] - template[key]) * w

            if best_score is None or score < best_score:
                best_score = score
                best_name = template_name

        return best_name

    def _apply_body_template_to_core_guides(core_guides, measurements, template_name):
        strength = _clamp(template_strength, 0.0, 1.0)
        if strength <= 0.0:
            return core_guides

        template = BODY_TEMPLATES[template_name]
        height = measurements["height"]

        target_shoulder_width = template["shoulder_width_ratio"] * height
        target_hip_width = template["hip_width_ratio"] * height
        target_torso_length = template["torso_length_ratio"] * height
        target_leg_length = template["leg_length_ratio"] * height
        target_arm_length = template["arm_length_ratio"] * height
        target_neck_length = template["neck_length_ratio"] * height
        target_head_height = template["head_height_ratio"] * height
        target_foot_length = template["foot_length_ratio"] * height

        # Shoulder width
        current_shoulder_width = abs(core_guides["upperarm_l"][0] - core_guides["upperarm_r"][0])
        blended_shoulder_width = current_shoulder_width + (target_shoulder_width - current_shoulder_width) * strength
        center_x = (core_guides["upperarm_l"][0] + core_guides["upperarm_r"][0]) * 0.5
        half_sw = blended_shoulder_width * 0.5
        shoulder_y = core_guides["spine_05"][1]

        core_guides["clavicle_l"][0] = center_x + half_sw * 0.35
        core_guides["upperarm_l"][0] = center_x + half_sw
        core_guides["clavicle_r"][0] = center_x - half_sw * 0.35
        core_guides["upperarm_r"][0] = center_x - half_sw

        core_guides["clavicle_l"][1] = shoulder_y
        core_guides["clavicle_r"][1] = shoulder_y
        core_guides["upperarm_l"][1] = shoulder_y - height * 0.01
        core_guides["upperarm_r"][1] = shoulder_y - height * 0.01

        # Hip width
        current_hip_width = abs(core_guides["thigh_l"][0] - core_guides["thigh_r"][0])
        blended_hip_width = current_hip_width + (target_hip_width - current_hip_width) * strength
        pelvis_x = core_guides["pelvis"][0]
        pelvis_y = core_guides["pelvis"][1]
        half_hw = blended_hip_width * 0.5

        core_guides["thigh_l"][0] = pelvis_x + half_hw
        core_guides["thigh_r"][0] = pelvis_x - half_hw

        # Torso
        current_torso_length = _distance(core_guides["pelvis"], core_guides["spine_05"])
        blended_torso_length = current_torso_length + (target_torso_length - current_torso_length) * strength

        spine_keys = ["spine_01", "spine_02", "spine_03", "spine_04", "spine_05"]
        for i, key in enumerate(spine_keys, start=1):
            t = i / len(spine_keys)
            core_guides[key][0] = pelvis_x
            core_guides[key][1] = pelvis_y + blended_torso_length * t
            core_guides[key][2] = core_guides["pelvis"][2]

        # Neck + head
        current_neck_length = _distance(core_guides["spine_05"], core_guides["neck_01"])
        blended_neck_length = current_neck_length + (target_neck_length - current_neck_length) * strength

        current_head_height = _distance(core_guides["neck_01"], core_guides["head_end"])
        blended_head_height = current_head_height + (target_head_height - current_head_height) * strength

        spine_top = core_guides["spine_05"]
        core_guides["neck_01"] = [spine_top[0], spine_top[1] + blended_neck_length, spine_top[2] + height * 0.01]
        core_guides["head"] = [spine_top[0], core_guides["neck_01"][1] + blended_head_height * 0.55, core_guides["neck_01"][2] + height * 0.02]
        core_guides["head_end"] = [core_guides["head"][0], core_guides["neck_01"][1] + blended_head_height, core_guides["head"][2]]

        # Arms
        for side in ("l", "r"):
            shoulder = core_guides[f"upperarm_{side}"]
            elbow = core_guides[f"lowerarm_{side}"]
            hand = core_guides[f"hand_{side}"]

            current_arm_length = _distance(shoulder, elbow) + _distance(elbow, hand)
            blended_arm_length = current_arm_length + (target_arm_length - current_arm_length) * strength

            direction = _normalize([
                hand[0] - shoulder[0],
                hand[1] - shoulder[1],
                hand[2] - shoulder[2],
            ])

            elbow_ratio = 0.52
            elbow[0] = shoulder[0] + direction[0] * blended_arm_length * elbow_ratio
            elbow[1] = shoulder[1] + direction[1] * blended_arm_length * elbow_ratio
            elbow[2] = shoulder[2] + direction[2] * blended_arm_length * elbow_ratio

            if not preserve_hand_reach:
                hand[0] = shoulder[0] + direction[0] * blended_arm_length
                hand[1] = shoulder[1] + direction[1] * blended_arm_length
                hand[2] = shoulder[2] + direction[2] * blended_arm_length

        # Legs
        for side in ("l", "r"):
            thigh = core_guides[f"thigh_{side}"]
            calf = core_guides[f"calf_{side}"]
            foot = core_guides[f"foot_{side}"]
            ball = core_guides[f"ball_{side}"]

            current_leg_length = _distance(thigh, calf) + _distance(calf, foot)
            blended_leg_length = current_leg_length + (target_leg_length - current_leg_length) * strength

            direction = _normalize([
                foot[0] - thigh[0],
                foot[1] - thigh[1],
                foot[2] - thigh[2],
            ])

            thigh_ratio = 0.52
            calf[0] = thigh[0] + direction[0] * blended_leg_length * thigh_ratio
            calf[1] = thigh[1] + direction[1] * blended_leg_length * thigh_ratio
            calf[2] = thigh[2] + direction[2] * blended_leg_length * thigh_ratio

            foot[0] = thigh[0] + direction[0] * blended_leg_length
            foot[1] = thigh[1] + direction[1] * blended_leg_length
            foot[2] = thigh[2] + direction[2] * blended_leg_length

            if preserve_feet_on_ground:
                foot[1] = min(foot[1], core_guides["root"][1] + height * 0.03)

            foot_dir = _normalize([
                ball[0] - foot[0],
                ball[1] - foot[1],
                ball[2] - foot[2],
            ])
            current_foot_length = _distance(foot, ball)
            blended_foot_length = current_foot_length + (target_foot_length - current_foot_length) * strength

            ball[0] = foot[0] + foot_dir[0] * blended_foot_length
            ball[1] = foot[1] + foot_dir[1] * blended_foot_length
            ball[2] = foot[2] + foot_dir[2] * blended_foot_length

        return core_guides

    def _add_finger_guides(guides, height, width, depth):
        def _one_side(side="l"):
            sign = 1.0 if side == "l" else -1.0
            hand = guides[f"hand_{side}"]

            spread = {
                "thumb":  -0.25,
                "index":   0.45,
                "middle":  0.20,
                "ring":   -0.05,
                "pinky":  -0.30,
            }

            lengths = {
                "thumb":  [0.30, 0.55, 0.78, 0.98],
                "index":  [0.28, 0.52, 0.76, 0.98],
                "middle": [0.30, 0.57, 0.83, 1.08],
                "ring":   [0.28, 0.50, 0.72, 0.92],
                "pinky":  [0.22, 0.38, 0.54, 0.70],
            }

            for finger_name, z_offset in spread.items():
                chain = lengths[finger_name]
                for idx, t in enumerate(chain):
                    x = hand[0] + sign * (width * 0.03 + width * 0.09 * t)
                    y = hand[1] - height * 0.002 * idx
                    z = hand[2] + depth * 0.10 * z_offset
                    if idx == 0:
                        guides[f"{finger_name}_metacarpal_{side}"] = [x, y, z]
                    else:
                        guides[f"{finger_name}_{idx:02d}_{side}"] = [x, y, z]

        _one_side("l")
        _one_side("r")

    def _add_toe_guides(guides, height, width, toe_tip_l, toe_tip_r):
        def _one_side(side="l", toe_tip=None):
            ball = guides[f"ball_{side}"]
            foot = guides[f"foot_{side}"]

            spread = {
                "bigtoe":   -0.30,
                "indextoe": -0.12,
                "middletoe": 0.00,
                "ringtoe":   0.12,
                "pinkytoe":  0.24,
            }

            for toe_name, offset in spread.items():
                x = ball[0] + (width * 0.018 * (1.0 if side == "l" else -1.0)) * (1.0 - offset)
                z1 = ball[2] + (toe_tip[2] - ball[2]) * 0.55
                z2 = toe_tip[2]
                y = max(guides["root"][1] + height * 0.005, foot[1] - height * 0.005)

                guides[f"{toe_name}_01_{side}"] = [x, y, z1]
                guides[f"{toe_name}_02_{side}"] = [x, y, z2]

        _one_side("l", toe_tip_l)
        _one_side("r", toe_tip_r)

    # --------------------------------------------------
    # Validate
    # --------------------------------------------------
    mode = (mode or "build").strip().lower()
    if mode not in {"analyze", "build"}:
        raise RuntimeError("mode must be 'analyze' or 'build'")

    if template_strength < 0.0 or template_strength > 1.0:
        raise RuntimeError("template_strength must be between 0.0 and 1.0")

    if debug_section_count < 8:
        raise RuntimeError("debug_section_count must be >= 8")

    if joint_radius <= 0:
        raise RuntimeError("joint_radius must be > 0")

    if guide_scale <= 0:
        raise RuntimeError("guide_scale must be > 0")

    # --------------------------------------------------
    # Mesh input
    # --------------------------------------------------
    mesh_shape = _resolve_mesh_shape(geometry)
    points = _get_mesh_points_world(mesh_shape)
    if not points:
        raise RuntimeError(f"Mesh has no points: {mesh_shape}")

    bb = _bbox(points)
    body_height = bb["max_y"] - bb["min_y"]
    body_width = bb["max_x"] - bb["min_x"]
    body_depth = bb["max_z"] - bb["min_z"]

    if body_height <= 0.0001:
        raise RuntimeError("Mesh height is too small")

    x_center = (bb["min_x"] + bb["max_x"]) * 0.5

    # --------------------------------------------------
    # Cross-sections
    # --------------------------------------------------
    sections = _build_cross_sections(points, bb, count=72)
    landmarks = _detect_core_landmarks(sections, bb)

    # --------------------------------------------------
    # Build initial guides from landmarks
    # --------------------------------------------------
    pelvis_center = landmarks["pelvis_center"]
    shoulder_center = landmarks["shoulder_center"]
    neck_center = landmarks["neck_center"]

    left_shoulder_pt = sections[landmarks["shoulder_i"]]["left_extreme"] or [x_center + body_width * 0.18, shoulder_center[1], shoulder_center[2]]
    right_shoulder_pt = sections[landmarks["shoulder_i"]]["right_extreme"] or [x_center - body_width * 0.18, shoulder_center[1], shoulder_center[2]]

    left_arm = _estimate_arm_points(points, sections, side="l", x_center=x_center, shoulder_pos=left_shoulder_pt)
    right_arm = _estimate_arm_points(points, sections, side="r", x_center=x_center, shoulder_pos=right_shoulder_pt)

    left_leg = _estimate_leg_points(points, sections, side="l", x_center=x_center, pelvis_pos=pelvis_center, root_y=bb["min_y"])
    right_leg = _estimate_leg_points(points, sections, side="r", x_center=x_center, pelvis_pos=pelvis_center, root_y=bb["min_y"])

    core_guides = {
        "root": [x_center, bb["min_y"], (bb["min_z"] + bb["max_z"]) * 0.5],
        "pelvis": [pelvis_center[0], pelvis_center[1], pelvis_center[2]],
        "spine_01": _lerp(pelvis_center, shoulder_center, 0.20),
        "spine_02": _lerp(pelvis_center, shoulder_center, 0.40),
        "spine_03": _lerp(pelvis_center, shoulder_center, 0.60),
        "spine_04": _lerp(pelvis_center, shoulder_center, 0.80),
        "spine_05": [shoulder_center[0], shoulder_center[1], shoulder_center[2]],
        "neck_01": landmarks["neck_center"],
        "head": landmarks["head"],
        "head_end": landmarks["head_end"],

        "clavicle_l": _lerp([x_center, shoulder_center[1], shoulder_center[2]], left_shoulder_pt, 0.35),
        "upperarm_l": left_arm["upperarm"],
        "lowerarm_l": left_arm["lowerarm"],
        "hand_l": left_arm["hand"],

        "clavicle_r": _lerp([x_center, shoulder_center[1], shoulder_center[2]], right_shoulder_pt, 0.35),
        "upperarm_r": right_arm["upperarm"],
        "lowerarm_r": right_arm["lowerarm"],
        "hand_r": right_arm["hand"],

        "thigh_l": left_leg["thigh"],
        "calf_l": left_leg["calf"],
        "foot_l": left_leg["foot"],
        "ball_l": left_leg["ball"],

        "thigh_r": right_leg["thigh"],
        "calf_r": right_leg["calf"],
        "foot_r": right_leg["foot"],
        "ball_r": right_leg["ball"],
    }

    # measurements + template
    measurements_before = _extract_measurements(core_guides)
    chosen_template = _choose_body_template(measurements_before, body_template)
    core_guides = _apply_body_template_to_core_guides(core_guides, measurements_before, chosen_template)
    measurements_after = _extract_measurements(core_guides)

    # full guides
    guides = dict(core_guides)

    if include_fingers:
        _add_finger_guides(guides, body_height, body_width, body_depth)

    if include_toes:
        _add_toe_guides(guides, body_height, body_width, left_leg["toe_tip"], right_leg["toe_tip"])

    # --------------------------------------------------
    # Debug output
    # --------------------------------------------------
    guide_nodes = []
    guide_group = None
    debug_section_nodes = []
    debug_group = None

    if create_guides:
        if parent_under_group:
            guide_group = cmds.group(empty=True, name=f"{name_prefix}_humanoid_guides_grp", world=True)

        for guide_name, pos in guides.items():
            loc_name = f"{name_prefix}_{guide_name}_guide"
            loc = _make_locator(loc_name, pos)
            guide_nodes.append(loc)
            if guide_group:
                _parent_safe(loc, guide_group)

    if create_debug_sections:
        if parent_under_group:
            debug_group = cmds.group(empty=True, name=f"{name_prefix}_section_debug_grp", world=True)

        # sample fewer debug locators to avoid clutter
        sampled = _build_cross_sections(points, bb, count=debug_section_count)
        for sec in sampled:
            name = f"{name_prefix}_sec_{sec['index']:02d}"
            loc = _make_locator(name, sec["center"])
            debug_section_nodes.append(loc)

            if debug_group:
                _parent_safe(loc, debug_group)

    # --------------------------------------------------
    # Build joints
    # --------------------------------------------------
    joint_nodes = []
    joint_group = None

    if mode == "build" and create_joints:
        if parent_under_group:
            joint_group = cmds.group(empty=True, name=f"{name_prefix}_metahuman_skeleton_grp", world=True)

        # center line
        root = _make_joint(_mh("root"), guides["root"])
        pelvis = _make_joint(_mh("pelvis"), guides["pelvis"])
        spine_01 = _make_joint(_mh("spine_01"), guides["spine_01"])
        spine_02 = _make_joint(_mh("spine_02"), guides["spine_02"])
        spine_03 = _make_joint(_mh("spine_03"), guides["spine_03"])
        spine_04 = _make_joint(_mh("spine_04"), guides["spine_04"])
        spine_05 = _make_joint(_mh("spine_05"), guides["spine_05"])
        neck_01 = _make_joint(_mh("neck_01"), guides["neck_01"])
        head = _make_joint(_mh("head"), guides["head"])
        head_end = _make_joint(_mh("head_end"), guides["head_end"])

        _parent_safe(pelvis, root)
        _parent_safe(spine_01, pelvis)
        _parent_safe(spine_02, spine_01)
        _parent_safe(spine_03, spine_02)
        _parent_safe(spine_04, spine_03)
        _parent_safe(spine_05, spine_04)
        _parent_safe(neck_01, spine_05)
        _parent_safe(head, neck_01)
        _parent_safe(head_end, head)

        joint_nodes.extend([root, pelvis, spine_01, spine_02, spine_03, spine_04, spine_05, neck_01, head, head_end])

        # arms
        for side in ("l", "r"):
            clav = _make_joint(_mh_side("clavicle", side), guides[f"clavicle_{side}"])
            up = _make_joint(_mh_side("upperarm", side), guides[f"upperarm_{side}"])
            low = _make_joint(_mh_side("lowerarm", side), guides[f"lowerarm_{side}"])
            hand = _make_joint(_mh_side("hand", side), guides[f"hand_{side}"])

            _parent_safe(clav, spine_05)
            _parent_safe(up, clav)
            _parent_safe(low, up)
            _parent_safe(hand, low)

            joint_nodes.extend([clav, up, low, hand])

            if include_fingers:
                for finger_name in ("thumb", "index", "middle", "ring", "pinky"):
                    meta_key = f"{finger_name}_metacarpal_{side}"
                    if meta_key not in guides:
                        continue

                    meta = _make_joint(_mh_side(f"{finger_name}_metacarpal", side), guides[meta_key])
                    _parent_safe(meta, hand)
                    joint_nodes.append(meta)

                    prev = meta
                    for idx in (1, 2, 3):
                        key = f"{finger_name}_{idx:02d}_{side}"
                        if key not in guides:
                            continue
                        j = _make_joint(_mh_side(f"{finger_name}_{idx:02d}", side), guides[key])
                        _parent_safe(j, prev)
                        joint_nodes.append(j)
                        prev = j

        # legs
        for side in ("l", "r"):
            thigh = _make_joint(_mh_side("thigh", side), guides[f"thigh_{side}"])
            calf = _make_joint(_mh_side("calf", side), guides[f"calf_{side}"])
            foot = _make_joint(_mh_side("foot", side), guides[f"foot_{side}"])
            ball = _make_joint(_mh_side("ball", side), guides[f"ball_{side}"])

            _parent_safe(thigh, pelvis)
            _parent_safe(calf, thigh)
            _parent_safe(foot, calf)
            _parent_safe(ball, foot)

            joint_nodes.extend([thigh, calf, foot, ball])

            if include_toes:
                for toe_name in ("bigtoe", "indextoe", "middletoe", "ringtoe", "pinkytoe"):
                    key1 = f"{toe_name}_01_{side}"
                    key2 = f"{toe_name}_02_{side}"
                    if key1 not in guides or key2 not in guides:
                        continue

                    toe1 = _make_joint(_mh_side(f"{toe_name}_01", side), guides[key1])
                    toe2 = _make_joint(_mh_side(f"{toe_name}_02", side), guides[key2])

                    _parent_safe(toe1, ball)
                    _parent_safe(toe2, toe1)

                    joint_nodes.extend([toe1, toe2])

        if joint_group:
            _parent_safe(root, joint_group)

    cmds.refresh(force=True)

    return {
        "success": True,
        "geometry": mesh_shape,
        "mode": mode,
        "body_template_requested": body_template,
        "body_template_used": chosen_template,
        "template_strength": template_strength,
        "bbox": bb,
        "dimensions": {
            "height": body_height,
            "width": body_width,
            "depth": body_depth,
        },
        "section_count": len(sections),
        "landmarks": {
            "neck_section_index": landmarks["neck_i"],
            "shoulder_section_index": landmarks["shoulder_i"],
            "chest_section_index": landmarks["chest_i"],
            "waist_section_index": landmarks["waist_i"],
            "pelvis_section_index": landmarks["pelvis_i"],
            "hip_section_index": landmarks["hip_i"],
        },
        "measurements_before": measurements_before,
        "measurements_after": measurements_after,
        "guide_count": len(guides),
        "guides": guides,
        "guide_group": guide_group,
        "guide_nodes": guide_nodes,
        "debug_group": debug_group,
        "debug_section_nodes": debug_section_nodes,
        "joint_group": joint_group,
        "joint_count": len(joint_nodes),
        "joints": joint_nodes,
        "notes": [
            "v2 uses vertical cross-section sampling instead of only bbox ratios.",
            "Finger and toe guides are still procedural recommendations based on final hand/foot guides.",
            "Best results on clean humanoid standing meshes with reasonable symmetry.",
            "This builds MetaHuman-style humanoid naming, not a full production rig.",
        ],
    }
