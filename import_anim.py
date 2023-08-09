if "bpy" in locals():
    import importlib
    if "parse_anim" in locals():
        importlib.reload(parse_anim)
    if "anim_utils" in locals():
        importlib.reload(anim_utils)

import bpy, io, time

from . import parse_anim, anim_utils

HEADER_PROP_TYPES = {
    "animVersion": lambda x: tuple(map(int, x.split('.'))),
    "mayaVersion": lambda x: tuple(map(int, x.split('.'))),
    "startTime": lambda x: int(x),
    "endTime": lambda x: int(x)
}

def get_keys_elements(fline, file):
    """Returns a list of [Time, Value, In-Tangent Type, Out-Tangent Type, WeightLock, TangentLock, Breakdown].\n
    Optionally there can be two additional positions for 'fixed' In and Out Tangent - Angle and Weight respectively"""
    keys = []
    while parse_anim.cleanLine(fline) != "}":
        keys.append(parse_anim.read_prop_keyframe(fline))
        fline = file.readline()

    return keys

def get_animData_elements(fline, file):
    """Returns dictionary of FCurve settings and keys as [FCurve settings, Keyframes]"""
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
    """Returns a list of [Object/Bone, Property, RNA_ID, Children, Index]"""
    props, isEmpty = parse_anim.read_prop_anim(fline)
    if isEmpty:
        return None
    
    attr = props[0] # the attribute like transform, visibility or custom property
    node = props[2] # object or bone
    children = props[-2]
    index = props[-1]

    # if it's any of the multi-channel attributes (XYZ), split the name by dot and get index by signature
    if any(True for k in anim_utils.B3D_ATTR_NAMES.keys() if k in attr):
        attr = attr.split(".")
        fc_attr = anim_utils.B3D_ATTR_NAMES[attr[0]]
        axis_ASCII = ord(attr[1][-1])
        rna_id = axis_ASCII-anim_utils.ASCII_X
    else:
        fc_attr = attr
        rna_id = 0

    return [node, fc_attr, rna_id, children, index]

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

def setupScene(timeUnit, linearUnit, angularUnit, startTime, endTime, **kwargs):
    sc = bpy.context.scene

    sc.render.fps = anim_utils.B3D_TIME_UNITS[timeUnit]
    sc.unit_settings.length_unit = anim_utils.B3D_LINEAR_UNITS[linearUnit]
    sc.unit_settings.system_rotation = anim_utils.B3D_ANGULAR_UNITS[angularUnit]
    sc.frame_start = startTime
    sc.frame_end = endTime

    return

def load(operator, context, filepath="", **kwargs):
    result = {'FINISHED'}

    obj = bpy.context.active_object
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
    setupScene(**settings)

    anim_datablock = []
    node = None
    for i, fl in enumerate(fbody):

        if fl.startswith("anim "):
            # print(f"{i}: reading 'anim' line...")
            fc_keys = None
            node = get_node_elements(fl)

        if fl.startswith("animData {"):
            # print(f"{i}: reading 'animData' block...")
            fl = ioStream.readline()                                        # skip to next line
            fc_settings, fc_keys = get_animData_elements(fl, ioStream)

        if node and fc_keys:
            # print(f"{i}: SAVING to datablock...")
            anim_datablock.append([node, fc_settings, fc_keys])
            
    operator.report({'INFO'}, "Import finished in %.4f sec." % (time.process_time() - start_time))
    return result
