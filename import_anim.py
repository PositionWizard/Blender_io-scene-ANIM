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

# def isFirstNode(name, do, prevName, i):
#     if name != prevName and i>0:
#         return False, name
    
#     return do, name

# TODO handle visibility animation as it's different paths for bones and objects
def prepare_custom_prop(node, prop):
    add_custom_props(node, prop)
    c_prop = '["'+prop+'"]'

    return c_prop

def get_fcDataPath(obj: bpy.types.Object,
                   anim_fc: ANIM_FCurve,
                   pbone_names: list,
                   is_custom_prop: bool,
                   doObj: bool):
    if obj.name != anim_fc.node.name and anim_fc.node.name in pbone_names:
        pbone = obj.pose.bones[anim_fc.node.name]
        pbone_path = pbone.path_from_id()
        fc_datapath = f'{pbone_path}.{anim_fc.node.property}'
        fc_group = pbone.name

        # support for custom properties
        if is_custom_prop:
            c_prop = prepare_custom_prop(pbone, anim_fc.node.property)
            fc_datapath += c_prop

        return fc_datapath, fc_group

    elif doObj:
        fc_datapath = anim_fc.node.property
        fc_group = "Object Transforms"

        # support for custom properties
        if is_custom_prop:
            fc_datapath = prepare_custom_prop(obj, anim_fc.node.property)

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
        mod.mode_before = anim_utils.B3D_CYCLES_TYPE[fc_postInf]

    return fc
    
def write_keyframes(fc: bpy.types.FCurve, anim_fc: ANIM_FCurve, anim_offset, linearUnit, angularUnit, **settings):
    linearUnit = anim_utils.B3D_LINEAR_UNITS[linearUnit]
    angularUnit = anim_utils.B3D_ANGULAR_UNITS[angularUnit]

    fc_unit = anim_utils.B3D_UNIT_TYPE[anim_fc.settings["output"]]
    unit_convert = {'LENGTH': anim_utils.units_convertor(linearUnit, 'METERS'),
                    'ROTATION': anim_utils.units_convertor(angularUnit, 'RADIANS')}
                    
    for anim_key in anim_fc.keys:
        # Convert linear and angular units based on global file settings.
        # Additional check for 'scale' property is there because some other doofus made a tool exporting those as 'linear' instead of 'unitless'
        # and we don't want to convert those based on units system.
        if fc_unit in unit_convert.keys() and anim_fc.node.property != 'scale':
            anim_key.value = unit_convert[fc_unit](anim_key.value)

        ktype = 'KEYFRAME'
        if anim_key.isbreakdown:
            ktype = 'BREAKDOWN'
        kp = fc.keyframe_points.insert(frame=anim_offset+anim_key.time, value=anim_key.value, keyframe_type=ktype)
        # if anim_fc.node.name == 'Root':
        #     print(f"{anim_fc.node.property}_{anim_fc.node.array_index} of value: {anim_key.value}, at frame: {anim_key.time}")

def write_animation(op: bpy.types.Operator,
                    ctx: bpy.context,
                    obj: bpy.types.Object,
                    filename: str,
                    anim_fcurves: list[ANIM_FCurve],
                    settings,
                    use_custom_props,
                    use_selected_bones,
                    anim_offset,
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

    prevNode = ""
    for i, anim_fc in enumerate(anim_fcurves):
        if doObj and anim_fc.node.name != prevNode and i>0:
            doObj = False
        prevNode = anim_fc.node.name

        # skip custom properties based on user flag
        is_custom_prop = anim_fc.node.property not in anim_utils.ANIM_ATTR_NAMES.keys()
        if not use_custom_props and is_custom_prop:
            continue

        fc_funcRes = get_fcDataPath(obj, anim_fc, pbone_names, is_custom_prop, doObj)

        if fc_funcRes == None:
            continue

        fc_datapath, fc_group = fc_funcRes

        # handle an error in case it tries to insert an already existing fcurve   
        try:    
            fc = action.fcurves.new(fc_datapath, index=anim_fc.node.array_index, action_group=fc_group)
        except RuntimeError as e:
            # operator.report({'INFO'}, ("Couldn't add curve for %r (%s)") % (fc_datapath, e))
            fc = action.fcurves.find(data_path=fc_datapath, index=anim_fc.node.array_index)

        fc = setup_fcurve(fc, anim_fc)
        write_keyframes(fc, anim_fc, anim_offset, **settings)

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

    anim_fcurves = []
    node = None
    for fl in fbody:
        if fl.startswith("anim "):
            # print(f"{i}: reading 'anim' line...")
            fc_keys = None
            node = get_node_elements(fl)
        
        if fl.startswith("animData {"):
            # print(f"{i}: reading 'animData' block...")
            fl = ioStream.readline()                                        # skip to next line
            fc_settings, fc_keys = get_animData_elements(fl, ioStream)

            # print(f"{i}: SAVING to datablock...")
            anim_fcurves.append(ANIM_FCurve(node, fc_settings, fc_keys))

    
    # Close the file to free up memory, since it's no longer needed
    ioStream.close()

    filename = bpy.path.basename(filepath).split(".")[0]
    write_animation(operator, context, obj, filename, anim_fcurves, settings, **kwargs)
            
    operator.report({'INFO'}, "Import finished in %.4f sec." % (time.process_time() - start_time))
    return result
