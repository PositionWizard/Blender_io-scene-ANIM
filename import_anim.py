# Things that need to be done to properly import anim files from Maya and other sources:
# 1. Perform general axis conversion on the object/armature
# 2. Remove the transform offset that's in parent-child bone relationship
#   (Blender has animation relative to the rest pose, Maya has it relative to the parent)
# 3. Apply Bone Scale to each bone by multiplying this scale by location values

if "bpy" in locals():
    import importlib
    if "parse_anim" in locals():
        importlib.reload(parse_anim)
    if "anim_utils" in locals():
        importlib.reload(anim_utils)

import bpy, io, time
from mathutils import Matrix, Vector, Euler

from typing import NamedTuple
from dataclasses import dataclass

from . import parse_anim, anim_utils

class ANIM_Node(NamedTuple):
    """Animation data information for ANIM node"""

    name: str
    property: str
    """Animated property like Location, Rotation, Scale or anything custom."""

    array_index: int 
    """F-Curve index of property affected by animation curve."""

    children: int
    """Number of children this node has."""

    id: int
    """Index of this node's animated properties."""

@dataclass
class ANIM_Keyframe:
    """Animation data for a single keyframe."""

    time: float
    value: float
    tan_in: str
    """"In" Tangent type.\n
    Types: auto, spline, linear, fixed, clamped."""

    tan_out: str
    """"Out" Tangent type.\n
    Types: auto, step, spline, linear, fixed, clamped."""

    islocked_tangent: bool
    """Does the keyframe have locked Tangents.\n
    In Blender, keyframe tangents are locked for every handle type other than "Free"."""

    islocked_weight: bool
    """Does the keyframe have locked Tangent Weight.\n
    Length of Tangent's handles is always free in Blender, meaning weights are never locked."""

    isbreakdown: bool
    """Is this a breakdown keyframe.\n
    Only available in Maya, this may result in different curve definition."""

    tan_in_angle: float
    """Angle in degrees that's written for "In" Tangent if it's 'fixed'."""

    tan_in_weight: float
    """Weight in range [0, 1] that's written for "In" Tangent if it's 'fixed'."""

    tan_out_angle: float
    """Angle in degrees that's written for "Out" Tangent if it's 'fixed'."""

    tan_out_weight: float
    """Weight in range [0, 1] that's written for "Out" Tangent if it's 'fixed'."""

class ANIM_FCurve(NamedTuple):
    """F-Curve data for animated property."""

    node: ANIM_Node
    """Animation data information for ANIM node."""

    settings: dict
    """F-Curve settings."""

    keys: list[ANIM_Keyframe]
    """List of keyframes for this F-Curve."""

class ANIM_FC_PropertyGroup(NamedTuple):
    name: str
    location: list[ANIM_FCurve]
    rotation_euler: list[ANIM_FCurve]
    rotation_quaternion: list[ANIM_FCurve]
    scale: list[ANIM_FCurve]
    custom: list[ANIM_FCurve]

HEADER_PROP_TYPES = {
    "animVersion": lambda x: tuple(map(int, x.split('.'))),
    "mayaVersion": lambda x: tuple(map(int, x.split('.'))),
    "startTime": lambda x: int(x),
    "endTime": lambda x: int(x)
}

def get_keys_elements(fline, file):
    """Returns a list of keyframes [Time, Value, In-Tangent Type, Out-Tangent Type, TangentLock, WeightLock, Breakdown].\n
    Optionally there can be two additional positions for 'fixed' In and Out Tangent - Angle and Weight respectively"""
    keys = []
    while parse_anim.cleanLine(fline) != "}":
        key_intan_angle = key_intan_weight = key_outtan_angle = key_outtan_weight = None
        anim_key = parse_anim.read_prop_keyframe(fline)

        # get in and out tangnets angle and weight values from correct list positions depending on whether or not given tangent is 'fixed'
        if anim_key[2] == 'fixed':
            key_intan_angle = anim_key[7]
            key_intan_weight = anim_key[8]

        if anim_key[3] == 'fixed':
            if anim_key[2] == 'fixed':
                outAngle_pos = 9
                outWeight_pos = 10
            else:
                outAngle_pos = 7
                outWeight_pos = 8

            key_outtan_angle = anim_key[outAngle_pos]
            key_outtan_weight = anim_key[outWeight_pos]
    
        # get this as a keyframe object through list slice operation of always present variables, then adding optional ones
        anim_key = ANIM_Keyframe(*anim_key[:7], key_intan_angle, key_intan_weight, key_outtan_angle, key_outtan_weight)
        keys.append(anim_key)

        fline = file.readline()

    return keys

def get_animData_elements(fline, file):
    """Returns dictionary of FCurve settings and keys list as (FCurve settings, Keyframes)"""
    props = dict()
    while parse_anim.cleanLine(fline) != '}':
        if parse_anim.cleanLine(fline) == 'keys {':
            fline = file.readline()                     # skip to next line
            fc_keys = get_keys_elements(fline, file)
        else:
            p, v = parse_anim.read_prop_single(fline)
            if p == 'weighted':
                v = bool(parse_anim.getInt(v))
            props[p] = v

        fline = file.readline()

    return props, fc_keys

def get_node_elements(fline):
    """Returns a tuple of (Name, Property, RNA_ID, Children, Index)"""
    props, isEmpty = parse_anim.read_prop_anim(fline)
    if isEmpty:
        return None
    
    attr = props[0] # the attribute like transform, visibility or custom property
    name = props[2] # object or bone
    children = props[-2]
    index = props[-1]

    # if it's any of the multi-channel attributes (XYZ), split the name by dot, get index by signature and translate names
    if any(True for k in anim_utils.B3D_ATTR_NAMES.keys() if k in attr):
        attr = attr.split(".")
        fc_attr = anim_utils.B3D_ATTR_NAMES[attr[0]]
        axis_ASCII = ord(attr[1][-1])
        rna_id = axis_ASCII-anim_utils.ASCII_X
    else:
        fc_attr = attr
        rna_id = 0

    return ANIM_Node(name, fc_attr, rna_id, children, index)

def get_header_elements(file):
    """Returns a dictionary of scene settings."""
    props = dict()
    ftell = 0
    for line in file:
        if line.startswith("anim "):
            file.seek(ftell)
            break
        
        ftell = file.tell()

        p, v = parse_anim.read_prop_single(line)
        try:
            # print(f"{type(HEADER_PROP_TYPES[p](v))}: {HEADER_PROP_TYPES[p](v)}")
            v = HEADER_PROP_TYPES[p](v)
        except KeyError:
            # print(f"{type(v)}: {v}")
            pass
        
        props[p] = v
        
    return props, file

def setupScene(op: bpy.types.Operator, ctx: bpy.context, timeUnit, linearUnit, angularUnit, startTime, endTime, use_fps, use_units, use_timerange, **kwargs):
    sc = ctx.scene
    
    framerate = anim_utils.B3D_TIME_UNITS[timeUnit]
    if use_fps: sc.render.fps = framerate
    elif sc.render.fps != framerate:
        op.report({'ERROR'}, ("Frame Rate not set! Set to %rfps for best results.") % framerate)
    if use_units:
        sc.unit_settings.length_unit = anim_utils.B3D_LINEAR_UNITS[linearUnit]
        sc.unit_settings.system_rotation = anim_utils.B3D_ANGULAR_UNITS[angularUnit]

    if use_timerange:
        sc.frame_start = startTime
        sc.frame_end = endTime

    return

# TODO
def add_custom_props(node, prop):
    if node.get(prop) is None:
        pass
    return

# TODO handle visibility animation as it's different paths for bones and objects
def prepare_custom_prop(node, prop):
    add_custom_props(node, prop)
    c_prop = '["'+prop+'"]'

    return c_prop

def get_fcDataPath(obj: bpy.types.Object,
                   node_name: str,
                   property: str,
                   pbone_names: list,
                   is_custom_prop: bool,
                   doObj: bool,
                   get_quaternion: bool):
    if obj.name != node_name and node_name in pbone_names:
        pbone = obj.pose.bones[node_name]
        pbone_path = pbone.path_from_id()
        fc_group = pbone.name

        if get_quaternion:
            prop = 'rotation_quaternion'
        else:
            prop = property

        fc_datapath = f'{pbone_path}.{prop}'

        # support for custom properties
        if is_custom_prop:
            c_prop = prepare_custom_prop(pbone, property)
            fc_datapath = pbone_path+c_prop

        return fc_datapath, fc_group

    elif doObj:
        if get_quaternion:
            fc_datapath = 'rotation_quaternion'
        else:
            fc_datapath = property
        fc_group = "Object Transforms"

        # support for custom properties
        if is_custom_prop:
            fc_datapath = prepare_custom_prop(obj, property)

        return fc_datapath, fc_group
    
    else:
        return None

def get_posebone_names(ctx: bpy.context, obj: bpy.types.Object, use_selected_bones: bool):
    posebones = obj.pose.bones
    if use_selected_bones:
        org_mode = obj.mode
        bpy.ops.object.mode_set(mode='POSE')
        sel_bones = ctx.selected_pose_bones_from_active_object
        bpy.ops.object.mode_set(mode=org_mode)

        if sel_bones: posebones = sel_bones

    pbone_names = [pb.name for pb in posebones]

    return pbone_names

def setup_fcurve(fc: bpy.types.FCurve, anim_fc: ANIM_FCurve):
    # setup extrapolation and cycling
    fc_postInf = anim_fc.settings["postInfinity"]
    fc_preInf = anim_fc.settings["preInfinity"]
    extr_types = ['constant', 'linear']
    if fc_postInf in extr_types:
        fc.extrapolation = fc_postInf.upper()

    if fc_postInf not in extr_types or fc_preInf not in extr_types:
        fc.extrapolation = 'CONSTANT'
        mod = fc.modifiers.new('CYCLES')
        mod.mode_before = anim_utils.B3D_CYCLES_TYPE[fc_preInf]
        mod.mode_after = anim_utils.B3D_CYCLES_TYPE[fc_postInf]

    return fc

def pack_anim_fcurves(animFC: ANIM_FCurve, nodeNames: list, anim_nodes: list):
    array_id = 1+anim_utils.FCURVE_PATHS_NAME_TO_ID.get(animFC.node.property, 4)     # map property name to an ID to group those properties together
    node_id = nodeNames.index(animFC.node.name)                                    # get node ID to put fcurves in a group for this node
    if not anim_nodes[node_id]:                                                    # if slot for a node group is empty, fill it with empty lists, one for each property group
        # animFC_group = [[] for i in range(5)]
        anim_nodes[node_id] = ANIM_FC_PropertyGroup(animFC.node.name, [], [], [], [], [])
    
    anim_nodes[node_id][array_id].append(animFC)                                   # add animation curve to a correct property group, under a node group

    return anim_nodes

def get_frames(fcurves: list[ANIM_FCurve], frames=set()):
    for anim_fc in fcurves:
        fri = [kp.time for kp in anim_fc.keys]
        frames.update(fri)

    return frames

def animkey_make_simple(t: float, val: float):
    return ANIM_Keyframe(t, val, 'auto', 'auto', 1, 0, 0, None, None, None, None)

def complete_animFCgroup(anim_fcgroup: list[ANIM_FCurve], first_frame: float):
    # TODO quaternion handling?
    fc_identity = [0,0,0]
    fc_group_new = [None]*3

    # get a list of fcurve indices for a given property
    fc_ids = [afc.node.array_index for afc in anim_fcgroup]

    # create missing curves for the property and insert basic keyframes
    for k, val in enumerate(fc_identity):
        if k not in fc_ids:
            p0 = anim_fcgroup[0]
            afc = ANIM_FCurve(ANIM_Node(p0.node.name, p0.node.property, k, p0.node.children, -1), p0.settings, [animkey_make_simple(first_frame, val)])
            fc_group_new[k] = afc
            
        try:
            pos_id = anim_fcgroup[k].node.array_index
            fc_group_new[pos_id] = anim_fcgroup[k]
        except IndexError: continue

    fc_group_new = list[ANIM_FCurve](fc_group_new)

    return fc_group_new

def transpose_frameArray_to_propArray(anim_fcgroup: list[ANIM_FCurve], frame_array: list[list[ANIM_Keyframe]]):
    # pack new 'baked' keyframes back into a proper structure and finally into a new list of property's curves
    anim_fcgroup_new = list[ANIM_FCurve]()
    for afc in anim_fcgroup:
        keys_new = [keys_array[afc.node.array_index] for keys_array in frame_array]
        afc_node_new = ANIM_FCurve(afc.node, afc.settings, keys_new)
        anim_fcgroup_new.append(afc_node_new)

    return anim_fcgroup_new

def get_neighbor_keys(anim_fc: ANIM_FCurve, frame: float):
    """Returns a tuple of (previous, next) ANIM_Keyframes closest to a given frame."""
    last_key = None
    for key in anim_fc.keys:
        if key.time > frame:
            return last_key, key
        last_key = key

    return last_key, None

def animkey_create_fill(last_key: ANIM_Keyframe, next_key: ANIM_Keyframe, frame: float):
    """Create a new key, with linearly interpolated value between last and next closest keys."""

    if not last_key:
        return next_key

    if not next_key:
        return last_key

    if last_key and next_key:
        # get a normalized frame position (percentage in [0.0-1.0]) between previous and next frames
        frame_pct = (next_key.time-frame)/(next_key.time-last_key.time)
        computed_value = anim_utils.lerp(last_key.value, next_key.value, frame_pct)
        return animkey_make_simple(frame, computed_value)

    return animkey_make_simple(frame, 0)

def anim_create_quaternion_fcgroup(anim_fcnode: ANIM_Node, frame: float, settings=dict()) -> list[ANIM_FCurve]:
    quaternions = []
    for i in range(0, 4):                    
        node_quat = ANIM_Node(anim_fcnode.name, 'rotation_quaternion', i, anim_fcnode.children, -1) 
        anim_fcurve = ANIM_FCurve(node_quat, settings, [])
        quaternions.append(anim_fcurve)

    return quaternions

def transposeConvert_propArray_to_frameArray(anim_fcgroup: list[ANIM_FCurve], frames, linearUnit, angularUnit, **settings):
    """Transpose a list of fcurves which contain keyframes, into a list of frames containting keyframe groups for each fcurve."""
    
    animkeys_channel_list, values_channel_list = [], []

    # loop through each channel (fcurve) of a property and gather ANIM_Keyframes and values into lists for each frame
    for k, fr in enumerate(frames):
        values_channel_list.append([])
        animkeys_channel_list.append([])
        for afc in anim_fcgroup:
            # default_keyValue = round(transform_map[afc.node.property][afc.node.array_index], 6)
            afc_key = next((key for key in afc.keys if key.time == fr), None)
            afc_value = 0

            # estimate a new value from existing neighboring keys if there is no keyframe on a current frame of given property channel but other channel has it
            if not afc_key:
                print("Property on following frame is missing! Filling...")
                print(f"{afc.node.name}_{afc.node.property}[{afc.node.array_index}], frame: {fr}")

                last_key, next_key = get_neighbor_keys(afc, fr)
                afc_key = animkey_create_fill(last_key, next_key, fr)
            
            fc_unit, unit_converter = anim_utils.anim_unit_converter(afc.settings["output"], linearUnit, angularUnit)
            if fc_unit in unit_converter.keys() and afc.node.property != 'scale':
                afc_value = unit_converter[fc_unit](afc_key.value)

            values_channel_list[k].append(afc_value)
            animkeys_channel_list[k].append(afc_key)

    return values_channel_list, animkeys_channel_list

def offset_transforms(node_matrix_parent: Matrix, eulRef: Euler, rot_mode: str, prop: str, keys_array: list[float], animkeys_array: list[ANIM_Keyframe], apply_scaling: bool, global_scale: float) -> tuple[list[ANIM_Keyframe], Euler]:
    '''Offset transforms for multiple channels at once per transform type.\n
    Returns a tuple of:
    - ANIM_Keyframe list
    - an offset Euler, to be used as reference for converting and proper filtering of next keyframe'''

    key_values_Space = [None]*3
    node_loc, node_rot, node_scale = node_matrix_parent.decompose()

    transform_map = {
        'location': key_values_Space[0],
        'rotation_euler': key_values_Space[1],
        'scale': node_scale
    }

    # Transform rotation and translation curves to a new space
    if prop == 'rotation_euler':
        rotMat = anim_utils.offset_rotation(keys_array, prop, node_rot)

        # TODO add option to retain original bone rotation        
        # Source rotation values are always in Euler XYZ because anim format doesn't support different rotation orders.
        # Filter euler values (anti-gimbal lock) by a compatibile euler from previous, converted rotation keyframes.
        # If target item rotation mode is quaternion (eulRef==None), then don't convert to eulers.
        key_values_Space[1] = rotMat.to_euler(rot_mode, eulRef)

        transform_map[prop] = key_values_Space[1]

    elif prop == 'location':
        key_transValues = Vector(keys_array).to_3d()
        # scale curves according to Bone Scale but only for bones
        if apply_scaling:
            key_transValues *= global_scale
        newMat = node_matrix_parent @ Matrix.Translation(key_transValues)
        transform_map[prop] = key_values_Space[0] = newMat.translation

    for i, key in enumerate(animkeys_array):
        key.value = transform_map[prop][i]

    return animkeys_array, transform_map['rotation_euler']

def write_keyframes(fc: bpy.types.FCurve, anim_fc: ANIM_FCurve, anim_offset, apply_unit_linear, axis_transform, linearUnit, angularUnit, **settings):
    # linearUnit = anim_utils.B3D_LINEAR_UNITS[linearUnit]
    # angularUnit = anim_utils.B3D_ANGULAR_UNITS[angularUnit]

    # fc_unit = anim_utils.B3D_UNIT_TYPE[anim_fc.settings["output"]]
    # unit_convert = {'LENGTH': anim_utils.units_convertor(linearUnit, 'METERS'),
    #                 'ROTATION': anim_utils.units_convertor(angularUnit, 'RADIANS')}
    
    fc_unit, unit_converter = anim_utils.anim_unit_converter(anim_fc.settings["output"], linearUnit, angularUnit)

    for i, anim_key in enumerate(anim_fc.keys):
        # Convert linear and angular units based on global file settings.
        # Additional check for 'scale' property is there because some other doofus made a tool exporting those as 'linear' instead of 'unitless'
        # and we don't want to convert those based on units system.
        if not axis_transform and fc_unit in unit_converter.keys() and anim_fc.node.property != 'scale':
            if not (not apply_unit_linear and fc_unit == 'LENGTH'):
                anim_key.value = unit_converter[fc_unit](anim_key.value)

        ktype = 'KEYFRAME'
        if anim_key.isbreakdown:
            ktype = 'BREAKDOWN'
        kp = fc.keyframe_points.insert(frame=anim_offset+anim_key.time, value=anim_key.value, keyframe_type=ktype)

        # check current next keyframe's (if exists) for their connected tangents and set proper interpolation types
        try:
            if anim_key.tan_out == anim_fc.keys[i+1].tan_in and anim_key.tan_out in ('step', 'linear'):
                kp.interpolation = anim_utils.B3D_INTERP_TYPE[anim_key.tan_out]
                continue
        except IndexError:
            pass

        kp.interpolation = 'BEZIER'
        kp.handle_left_type = anim_utils.B3D_TANGENT_TYPE[anim_key.tan_in]
        kp.handle_right_type = anim_utils.B3D_TANGENT_TYPE[anim_key.tan_out]
        # TODO add proper keyframe handle definition which probably needs to be recalculated for new axes

        # if anim_fc.node.name == 'Root':
        #     print(f"{anim_fc.node.property}_{anim_fc.node.array_index} of value: {anim_key.value}, at frame: {anim_key.time}")

    fc.update()

def write_animation(op: bpy.types.Operator,
                    ctx: bpy.context,
                    obj: bpy.types.Object,
                    filename: str,
                    anim_nodes: list[ANIM_FC_PropertyGroup],
                    settings,
                    apply_unit_linear,
                    axis_transform,
                    bake_space_transform,
                    use_custom_props,
                    use_selected_bones,
                    anim_offset,
                    global_matrix: Matrix,
                    global_scale,
                    **kwargs):
    animData = obj.animation_data
    if not animData:
        animData = obj.animation_data_create()

    action = bpy.data.actions.new(filename)
    animData.action = action

    pbone_names = []
    doObj = True
    if obj.type == 'ARMATURE':
        if use_selected_bones:
            doObj = False
        pbone_names = get_posebone_names(ctx, obj, use_selected_bones)

    for i, node in enumerate(anim_nodes):
        # treat as object only the first node if applicable and get parent-space matrix
        if doObj and i>0:
            doObj = False

        if node.name in pbone_names:
            doObj = False
            bone = obj.data.bones[node.name]
            node_matrix_parent_inv = anim_utils.bone_calculate_parentSpace(bone).inverted()
            if i==0 and bake_space_transform:
                node_matrix_parent_inv = global_matrix @ node_matrix_parent_inv
        elif doObj:
            node_matrix_parent_inv = global_matrix
        else:
            continue

        created_quaternions = list[ANIM_FCurve]()
        use_converted_quaternions = False

        for j, anim_fcgroup in enumerate(node[1:]):
            if not anim_fcgroup:
                continue

            # skip custom properties based on user flag
            is_custom_prop = j==4
            if not use_custom_props and is_custom_prop:
                continue

            print("--------------------------------")
            # sort the fcurves according to array_index
            anim_fcgroup = sorted(anim_fcgroup, key=lambda afc: afc.node.array_index)

            # get frames where keyframes exist for any of the animation curves in a given property array (entire location/rotation/scale)
            frames = set()
            frames = get_frames(anim_fcgroup, frames)
            print(f"j: [{j}], frames: {frames}")

            # 'j' indices represent following node properties:
            # 0 - location
            # 1 - rotation_euler
            # 2 - rotation_quaternion
            # 3 - scale
            # 4 - custom
            # do only for location and euler rotation
            anim_framegroup_keys = list[list[ANIM_Keyframe]]()
            use_converted_quaternions = False
            if j<2 and axis_transform:
                # for incomplete euler rotation or location
                if len(anim_fcgroup) < 3:
                    anim_fcgroup = complete_animFCgroup(anim_fcgroup, list(frames)[0])
                    
                if doObj: rot_mode = obj.rotation_mode
                else: rot_mode = obj.pose.bones[node.name].rotation_mode
                # anim_framgroup_vals, anim_framegroup_keys = transposeConvert_propArray_to_frameArray(anim_fcgroup, frames, node_matrix_parent_inv.inverted(), **settings)
                anim_framgroup_vals, anim_framegroup_keys = transposeConvert_propArray_to_frameArray(anim_fcgroup, frames, **settings)

                n = anim_fcgroup[0].node
                # for a, b, f in zip(anim_framgroup_vals, anim_framegroup_keys, frames):
                #     for k, (x, y) in enumerate(zip(a, b)):
                #         print(f"{n.name}_{n.property}[{k}] | frame: ({f}) {y.time} vals value: {x}, keys value: {y.value}")

                # get rotation values as reference to properly filter next euler values
                afc_prop = anim_fcgroup[0].node.property

                if j == 1:
                    # source rotation is always euler so if target item expects quaternions then fall back to 'XYZ' euler for now
                    # create a temp group of quaternion fcurves, to fill it later with keys
                    if rot_mode == 'QUATERNION':
                        rot_mode = 'XYZ'
                        created_quaternions = anim_create_quaternion_fcgroup(anim_fcgroup[0].node, list(frames)[0], anim_fcgroup[0].settings)
                        use_converted_quaternions = True
                    rotRef_mat = anim_utils.offset_rotation(anim_framgroup_vals[0], afc_prop, node_matrix_parent_inv.decompose()[1])
                    eulRef = rotRef_mat.to_euler(rot_mode)
                else:
                    eulRef = None
                    rot_mode = None
                    
                # have to loop through all the frames again to do the offset calculations, unfortunately...
                # this is to avoid wrong offsets due to key modifications right after gathering them (it's offseting keys from already offset ones at previous frame, basically)
                for k, fr in enumerate(frames):
                    # Do calculations for entire frames
                    # this updates 'anim_framegroup_keys' list with transformed values
                    # cache a resulted Euler rotation for filtering the next keyframe value properly
                    eulRef = offset_transforms(node_matrix_parent_inv, eulRef, rot_mode, afc_prop, anim_framgroup_vals[k], anim_framegroup_keys[k], not doObj, global_scale)[1]

                    # if quaternion rotation is the target property and anim curve data is filled from current euler anim data in the file, then fill quaternion curves with converted keys
                    if use_converted_quaternions:
                        quat = eulRef.to_quaternion()
                        for l, animfc in enumerate(created_quaternions):
                            animfc.keys.append(animkey_make_simple(fr, quat[l]))

                    for m, (x, y) in enumerate(zip(anim_framgroup_vals[k], anim_framegroup_keys[k])):
                        print(f"{n.name}_{n.property}[{m}] | frame: ({fr}) {y.time} value: {x}, new value: {y.value}")

                # anim_fcgroup = transpose_frameArray_to_propArray(anim_fcgroup, anim_framegroup_newkeys)
            
            # replace the eulers group with created quaternions since we want to use converted values
            if use_converted_quaternions:
                anim_fcgroup = created_quaternions

            for anim_fc in anim_fcgroup:
                if anim_framegroup_keys and not use_converted_quaternions:
                    keys_new = [keys_array[anim_fc.node.array_index] for keys_array in anim_framegroup_keys]
                    anim_fc = ANIM_FCurve(anim_fc.node, anim_fc.settings, keys_new)

                fc_funcRes = get_fcDataPath(obj, anim_fc.node.name, anim_fc.node.property, pbone_names, is_custom_prop, doObj, use_converted_quaternions)

                if fc_funcRes == None:
                    continue

                fc_datapath, fc_group = fc_funcRes
                print(f"{anim_fc.node.name}, {anim_fc.node.property} [{anim_fc.node.array_index}]")

                # handle an error in case it tries to insert an already existing fcurve   
                try:    
                    fc = action.fcurves.new(fc_datapath, index=anim_fc.node.array_index, action_group=fc_group)
                except RuntimeError as e:
                    # operator.report({'INFO'}, ("Couldn't add curve for %r (%s)") % (fc_datapath, e))
                    fc = action.fcurves.find(data_path=fc_datapath, index=anim_fc.node.array_index)

                fc = setup_fcurve(fc, anim_fc)
                write_keyframes(fc, anim_fc, anim_offset, apply_unit_linear, axis_transform, **settings)

    return

def load(operator: bpy.types.Operator,
         context: bpy.context,
         filepath="",
         **kwargs):
    result = {'FINISHED'}

    obj = context.active_object
    if not obj:
        operator.report({'ERROR'}, ("No active object to import animation for."))
        return {'CANCELLED'}

    operator.report({'INFO'}, "Importing ANIM...%r" % filepath)
    start_time = time.process_time()

    try:
        with open(filepath, "r", encoding="ascii") as f:
            ioStream = io.StringIO(f.read())

    except FileNotFoundError as e:
        operator.report({'ERROR'}, ("Couldn't open file %r (%s)") % (filepath, e))
        return {'CANCELLED'}
    
    settings, fbody = get_header_elements(ioStream)
    setupScene(operator, context, **settings, **kwargs)

    anim_nodes = []
    nodeNames = []
    node = None
    for fl in fbody:
        if fl.startswith("anim "):
            # print(f"{i}: reading 'anim' line...")
            fc_keys = None
            node = get_node_elements(fl)
            if node and node.name not in nodeNames:
                nodeNames.append(node.name)
                anim_nodes.append([])
        
        if fl.startswith("animData {"):
            # print(f"{i}: reading 'animData' block...")
            fl = ioStream.readline()                                        # skip to next line
            fc_settings, fc_keys = get_animData_elements(fl, ioStream)

            # print(f"{i}: SAVING to datablock...")
            animFC = ANIM_FCurve(node, fc_settings, fc_keys)
            anim_nodes = pack_anim_fcurves(animFC, nodeNames, anim_nodes)
            
    anim_nodes = list[ANIM_FC_PropertyGroup](anim_nodes)
    # for node in anim_nodes:
    #     print("----------------------------------------------")
    #     print(f"Group: {node[0][0].node.name}")
    #     for fcgroup in node:
    #         if fcgroup:
    #             print("--------------------------------")
    #             for fc in fcgroup:
    #                 print(f"{fc.node.name}, {fc.node.property} [{fc.node.array_index}]")
    
    # Close the file to free up memory, since it's no longer needed
    ioStream.close()

    filename = bpy.path.basename(filepath).split(".")[0]
    # Clone and convert the armature to different axis upon export
    write_animation(operator, context, obj, filename, anim_nodes, settings, **kwargs)
            
    operator.report({'INFO'}, "Import finished in %.4f sec." % (time.process_time() - start_time))
    return result
