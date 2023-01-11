import bpy, io, math
from pathlib import Path
from mathutils import Matrix, Euler, Vector



# class AnimEXT_OT_AnimExport(bpy.types.Operator):
#     bl_idname = "maya_anim.export"
#     bl_label = "Export ANIM"
#     bl_description = "Export animation curves using Autodesk Maya file format"
#     bl_options = {'UNDO'}

#     filepath: StringProperty(subtype="FILE_PATH")
#     filter_glob: StringProperty(
#         default = "*.anim",
#         options = {'HIDDEN'},
#         maxlen= 255
#     )
#     filename: StringProperty(
#         default="untitled.anim"
#     )

#     def execute(self, context):
#         #print(self.filepath)
#         with open(Path(self.filepath).joinpath(self.filepath, self.filename), 'wb') as temp_file:
#             temp_file.chow
#             temp_file.write(buff)
#         return {'FINISHED'}

#     def invoke(self, context, event):
#         wm = bpy.context.window_manager
#         wm.fileselect_add(self)
#         return {'RUNNING_MODAL'}

# ANIM_TIME_UNITS = {
#     # in fps
#     "game": 15,
#     "film": 24,
#     "pal": 25,
#     "ntsc": 30,
#     "show": 48,
#     "palf": 50,
#     "ntscf": 60,
# }

UNITS = {
    "METERS": 1.0,  # Ref unit!
    "KILOMETERS": 0.001,
    'MILLIMETERS': 1000.0,
    'CENTIMETERS': 100.0,
    "FEET": 1.0 / 0.3048,
    "INCHES": 1.0 / 0.0254,
    "turn": 1.0,  # Ref unit!
    "DEGREES": 360.0,
    "RADIANS": math.pi * 2.0,
    "SECONDS": 1.0,  # Ref unit!
}

ANIM_TIME_UNITS = {
    # in fps
    15: "game",
    24: "film",
    25: "pal",
    30: "ntsc",
    48: "show",
    50: "palf",
    60: "ntscf"
}

ANIM_LINEAR_UNITS = {
    'MILLIMETERS': "mm",
    'CENTIMETERS': "cm",
    'METERS': "m",
    'KILOMETERS': "km",
    'INCHES': "in",
    'FEET': "ft",
    'MILES': "mi",
}

ANIM_ANGULAR_UNITS = {
    'DEGREES': "deg",
    'RADIANS': "rad"
}

ANIM_CYCLES_TYPE = {
    'REPEAT': 'cycle',
    'REPEAT_OFFSET': 'cycleRelative',
    'MIRROR': 'oscillate',
    'NONE': None,
}

ANIM_UNIT_TYPE = { # blender defaults:
    'TIME': 'time', # frame
    'LENGTH': 'linear', # meter
    'ROTATION': 'angular', # radians
    'NONE': 'unitless'
}

ANIM_TANGENT_TYPE = {
    'AUTO_CLAMPED': 'auto',
    'AUTO': 'spline',
    'VECTOR': 'linear',
    'ALIGNED': 'fixed',
    'FREE': 'fixed',

    # interpolation
    'BEZIER': 'spline',
    'LINEAR': 'linear', # doesn't write tangents
    'CONSTANT': 'step' # doesn't write tangents, only out tangent
}

# Return a convertor between specified units.
def units_convertor(u_from, u_to):
    conv = UNITS[u_to] / UNITS[u_from]
    return lambda v: v * conv

linear_converter = units_convertor('METERS', bpy.context.scene.unit_settings.length_unit) 
angular_converter = units_convertor('RADIANS', bpy.context.scene.unit_settings.system_rotation) 

# Sanitization replaces all special characters with underscores
def names_sanitize(name, wildcard=""):
    if wildcard:
        name_clean = name.replace(wildcard, '_')
    else:
        name_clean = ''.join(c if c.isalnum() else '_' for c in name)
    return name_clean

def bone_calculate_parentSpace(pBone):
    # pBone = bpy.types.PoseBone(pBone)
    # obj = bpy.types.Object(obj)
    # arm = bpy.types.Armature(obj.data)

    rotMode = pBone.rotation_mode

    # Get bone's parent-space matrix and if bone has no parent, then get armature-space matrix
    if pBone.parent:
        boneMat = Matrix(pBone.parent.matrix.inverted() @ pBone.matrix)
    else:
        boneMat = pBone.matrix
    
    trans, rot_quat, scale = boneMat.decompose()
    # print(f"Location: {trans}\nRotation: {rot_quat}\nScale: {scale}")

    if rotMode == 'QUATERNION':
        rot = rot_quat
    elif rotMode != 'AXIS_ANGLE':
        rot = boneMat.to_euler(rotMode)
    else:
        rot = None
        
    return (trans, rot, scale)

def anim_keys_elements(fc, dt_input, dt_output, scene, bone_transforms, fc_id, attr_name, **kwargs):
    keyString = io.StringIO()
    tab = "  "

    # defaults
    in_tan = 'fixed'
    out_tan = 'fixed'
    tan_lock = 1 # 0 is the "free" tangent option, while 1 is everything else I believe
    weight_lock = 0 # Blender tangents are always unlocked (free handle length)
    breakdown = 0 # Blender has no breakdown keys

    def tangent_calc(kp, handle):
        x = kp.co[0] - handle[0]
        y = kp.co[1] - handle[1]

        # do the math and avoid dividing by 0
        if x != 0:
            tan = (y)/(x) # get the tangent, also as a slope between keyframe point and left handle
            tan_angle = angular_converter(math.atan(tan)) # convert back to angular through "atan" and to degrees
            
            if tan_angle < 0.001 and tan_angle > -0.001: # round the number
                tan_angle = 0
        else:
            tan_angle = math.copysign(90, y) # 0 value is 90!

        # mag = math.sqrt(math.pow(x, 2)+math.pow(y, 2)) # line below is the same but much shorter lmao
        tan_mag = math.hypot(x, y)
        # if tan_mag < 0.001 and tan_mag > -0.001:
        #     tan_mag

        return round(tan_angle, 6), round(tan_mag, 6)

    keyString.write(tab+'keys {\n')
    fc = bpy.types.FCurve(fc)
    
    prev_interp = None
    # get keyframe frame and values
    for kp in fc.keyframe_points:
        kp = bpy.types.Keyframe(kp)
        keyString.write(tab*2+"{} ".format(round(kp.co[0], 6))) # write frame number
        v = kp.co[1]

        # Offset curves by bone's objectspace (armature) transforms
        # bone_transforms = False
        if bone_transforms:
            transform_map = {
                'translate': bone_transforms[0],
                'rotate': bone_transforms[1],
                'scale': bone_transforms[2]
                }

            # print(f"attribute: {attr_name}, ID: {fc_id}, value: {transform_map[attr_name][fc_id]}")
            t_value = transform_map[attr_name][fc_id]

            if attr_name != 'scale':
                kp.handle_left[1] += t_value
                kp.co[1] += t_value
                kp.handle_right[1] += t_value

        if dt_output == 'linear':
            v = linear_converter(kp.co[1])

        elif dt_output == 'angular':
            v = angular_converter(kp.co[1])

        keyString.write(f"{v:.6f} ") # write value
        # keyString.write((f"{v:.6f} ").replace('.', ',')) # write value

        if kp.interpolation != 'BEZIER':
            out_tan = ANIM_TANGENT_TYPE[kp.interpolation]
        else:
            out_tan = ANIM_TANGENT_TYPE[kp.handle_right_type]
            
        if prev_interp != 'BEZIER' and prev_interp is not None:
            in_tan = ANIM_TANGENT_TYPE[kp.interpolation]
        else:
            in_tan = ANIM_TANGENT_TYPE[kp.handle_left_type]

        if kp.handle_left_type == 'FREE' or kp.handle_right_type == 'FREE':
            tan_lock = 0

        keyString.write(f"{in_tan} {out_tan} {tan_lock} {weight_lock} {breakdown}")

        # Tangent angle and weight calculations needed for left and right handle respectivevly
        if in_tan == 'fixed':
            in_tan_angle, in_tan_weight = tangent_calc(kp, kp.handle_left)
            keyString.write(f" {in_tan_angle} {in_tan_weight}")

        if out_tan == 'fixed':
            out_tan_angle, out_tan_weight = tangent_calc(kp, kp.handle_right)
            keyString.write(f" {out_tan_angle} {out_tan_weight}")

        keyString.write(';\n')
        prev_interp = kp.interpolation

    keyString.write(tab+'}\n')

    keyString.seek(0)
    return keyString

def anim_animData_elements(fc, node, fc_path, scene, angularUnit, **kwargs):
    animDataString = io.StringIO()
    animDataString.write('animData {\n') # open the data block
    tab = "  "

    fc_unit_type = node.bl_rna.properties[fc_path].unit # get the curve unit (degrees, radians, linear, etc.)
    # for x, y in ANIM_UNIT_TYPE.items():
    #     fc_unit = fc_unit.replace(x, y)
    #     break

    dt_input = 'time'
    dt_output = ANIM_UNIT_TYPE[fc_unit_type]
    dt_weighted = 1 # Blender always has weighted tangents
    dt_tan = angularUnit
    dt_preInf = dt_postInf = fc.extrapolation.lower() # set either linear or constant
    

    # check for any cyclic modifiers and apply a different pre and post infinity type
    for mod in fc.modifiers:
        if mod.type == 'CYCLES':
            # for x, y in ANIM_CYCLES_TYPE.items():
            #     if mod.mode_before == x and y is not None:
            #         dt_preInf = mod.mode_before.replace(x, y)
                
            #     if mod.mode_after == x and y is not None:
            #         dt_postInf = mod.mode_after.replace(x, y)
            if mod.mode_before != 'NONE': dt_preInf = ANIM_CYCLES_TYPE[mod.mode_before]
            if mod.mode_after != 'NONE': dt_postInf = ANIM_CYCLES_TYPE[mod.mode_after]
            break

    
    animDataString.write(tab+'input {};\n'.format(dt_input))
    animDataString.write(tab+'output {};\n'.format(dt_output))
    animDataString.write(tab+'weighted {};\n'.format(dt_weighted))

    # check keys if any of them 'fixed' tangents (Blender's "Aligned")
    if any([kp for kp in fc.keyframe_points if kp.handle_left_type == 'ALIGNED' or kp.handle_right_type == 'ALIGNED']):
        animDataString.write(tab+'tangentAngleUnit {};\n'.format(dt_tan))

    animDataString.write(tab+'preInfinity {};\n'.format(dt_preInf))
    animDataString.write(tab+'postInfinity {};\n'.format(dt_postInf))

    # write keyframes
    animDataString.write(anim_keys_elements(fc, dt_input, dt_output, scene, **kwargs).read())
    animDataString.write('}\n') # close the data block

    animDataString.seek(0)
    return animDataString

def anim_fcurve_elements(self, objs, scene, sanitize_names, **kwargs):
    fcurveString = io.StringIO()
    kwargs_mod = kwargs.copy()

    for obj in objs:
        try: obj.animation_data.action.fcurves
        except: AttributeError(self.report({'ERROR'}, obj.name+" has no animation data."))
        else:
            # Get a dictionary of all the bones and amount of their fcurves
            # if obj.type == 'ARMATURE':
            #     fc_list = []
            #     for fc in obj.animation_data.action.fcurves:
            #         fc = bpy.types.FCurve(fc)

                    
            #         if 'pose.bones' in fc.data_path:
            #             bone_name = fc.data_path.split('"')[1]
            #             fc_list.append(bone_name)

            #     fc_map = {x: fc_list.count(x) for x in fc_list}

            attr_names = {
                    "location": 'translate',
                    "rotation_euler": 'rotate',
                    "rotation_quaternion": 'rotate',
                    "scale": 'scale'
                    }

            prev_node_name = ""
            i = 0
            for attr_i, fc in enumerate(obj.animation_data.action.fcurves):
                fc = bpy.types.FCurve(fc)
                fcurveString.write('anim ')
                
                if 'pose.bones' in fc.data_path:
                    fc_path = fc.data_path.split('.')[-1] # get only the last part
                    node_name = fc.data_path.split('"')[1]
                    node = obj.pose.bones[node_name]

                    # Sometimes there can be rogue fcurves that don't belong to anything so let's skip them.
                    if node_name not in obj.data.bones: continue

                    # limit indexing to each bone found in the fcurves
                    if node_name == prev_node_name or i == 1:
                        i += 1
                    else:
                        i = 1
                        # Do calcs only once per bone
                        # print(f"{i-1}: Node Switched! Bone: {node_name}")
                        kwargs_mod["bone_transforms"] = bone_calculate_parentSpace(node)

                    # print(f"{i}: continue...")

                    attr_i = i-1
                    prev_node_name = node_name
                else:
                    attr_i += 1
                    fc_path = fc.data_path
                    node = obj
                    kwargs_mod["bone_transforms"] = None

                kwargs_mod["fc_id"] = fc.array_index

                # translate attribute names
                try: kwargs_mod["attr_name"] = attr = attr_names[fc_path]
                except KeyError: attr = fc_path

                # proof of concept but here should actually be the code doing stuff here
                # print(f"'{node.name}', array_index: {fc.array_index} attr_i: {attr_i}")

                axis_ASCII = 88
                if fc_path.endswith("quaternion"):
                    axis_ASCII = 87

                fc_chan = chr(axis_ASCII+fc.array_index) # start counting and return a character of either W, X, Y or Z

                fcurveString.write('{0}.{0}{1} {0}{1} '.format(attr, fc_chan)) # write the fcurve down  

                # TODO FIGURE OUT WHY IT DOESN'T WORK IN MAYA
                # write the animcurve with data: obj/bone name, children count, fcurve number
                # if isinstance(node, bpy.types.PoseBone):
                #     row = len(node.parent_recursive)
                # else: row = 0 # TODO count hierarchy place for objects
                row = 0

                wildcard = ""
                # Clean the name of exported objects/bones
                if sanitize_names == 'EXPORT_SPACES' or sanitize_names == 'PROJECT_EXPORT_SPACES': # apply wildcard for spaces
                    wildcard = " "
                # Now sanitize either for project and export or just project, wildcard will be still applied depending on choice
                if sanitize_names == 'EXPORT_ALL' or sanitize_names == 'EXPORT_SPACES':
                    node_name = names_sanitize(node.name, wildcard)
                else:
                    node_name = node.name = names_sanitize(node.name, wildcard)

                child = len(node.children) # count children
                fcurveString.write("{} {} {} {};\n".format(node_name, row, child, attr_i)) 

                # write the animData block
                fcurveString.write(anim_animData_elements(fc, node, fc_path, scene, **kwargs_mod).read())


            # for group in obj.animation_data.action.groups:
            #     # Sometimes there can be rogue fcurves that don't belong to anything so let's skip them.
            #     # Usually they match group names so we should be good.
            #     # TODO make sure it's tied to fcurves not groups
            #     if group.name != 'Object Transforms' and group.name not in obj.pose.bones: continue

            #     if group.name in obj.pose.bones:
            #         node = obj.pose.bones[group.name]
            #         kwargs_mod["bone_transforms"] = bone_calculate_restPose(node)
            #     else:
            #         node = obj
            #         kwargs_mod["bone_transforms"] = None

            #     # Loop through the grouped fcurves so we can index them properly
            #     for attr_i, fc in enumerate(group.channels):
            #         # fc = bpy.types.FCurve(fc)
            #         fcurveString.write('anim ')
                    
            #         axis_ASCII = 88
            #         if fc.data_path.endswith("quaternion"):
            #             axis_ASCII = 87

            #         fc_chan = chr(axis_ASCII+fc.array_index) # start counting and return a character of either W, X, Y or Z

            #         # if the fcurve is for a bone
            #         if 'pose.bones' in fc.data_path:
            #             fc_path = fc.data_path.split('.')[-1] # get only the last part
            #         else:
            #             fc_path = fc.data_path

            #         # translate attribute names
            #         if fc_path == "location":
            #             attr = 'translate'
            #         elif(fc_path.startswith("rotation")):
            #             attr = 'rotate'
            #         else:
            #             attr = 'scale'

            #         fcurveString.write('{0}.{0}{1} {0}{1} '.format(attr, fc_chan)) # write the fcurve down  

            #         # TODO FIGURE OUT WHY IT DOESN'T WORK IN MAYA
            #         # write the animcurve with data: obj/bone name, children count, fcurve number
            #         # if isinstance(node, bpy.types.PoseBone):
            #         #     row = len(node.parent_recursive)
            #         # else: row = 0 # TODO count hierarchy place for objects
            #         row = 0

            #         node_name = node.name
            #         wildcard = ""
            #         # Clean the name of exported objects/bones
            #         if sanitize_names == 'EXPORT_SPACES' or sanitize_names == 'PROJECT_EXPORT_SPACES': # apply wildcard for spaces
            #             wildcard = " "
            #         # Now sanitize either for project and export or just project, wildcard will be still applied depending on choice
            #         if sanitize_names == 'EXPORT_ALL' or sanitize_names == 'EXPORT_SPACES':
            #             node_name = names_sanitize(node.name, wildcard)
            #         else:
            #             node_name = node.name = names_sanitize(node.name, wildcard)

            #         child = len(node.children) # count children
            #         fcurveString.write("{} {} {} {};\n".format(node_name, row, child, attr_i)) 

            #         # write the animData block
            #         fcurveString.write(anim_animData_elements(fc, node, fc_path, scene, **kwargs_mod).read())

    fcurveString.seek(0)
    return fcurveString

def anim_header_elements(scene, start_time, end_time, use_time_range, **kwargs):
    headerString = io.StringIO()

    kwargs_mod = kwargs.copy()

    animVersion  = 1.1
    blenderVersion = bpy.app.version_string
    try:
        timeUnit = ANIM_TIME_UNITS[scene.render.fps]
    except KeyError: timeUnit = "Unknown Time Unit"
    finally: kwargs_mod["timeUnit"] = timeUnit
    kwargs_mod["linearUnit"] = linearUnit = ANIM_LINEAR_UNITS[scene.unit_settings.length_unit]
    kwargs_mod["angularUnit"] = angularUnit = ANIM_ANGULAR_UNITS[scene.unit_settings.system_rotation]

    # use timeline range if no custom range is set
    if not use_time_range:
        start_time = scene.frame_start
        end_time = scene.frame_end

    startTime = start_time
    endTime = end_time

    headerString.write('animVersion {:n};\n'.format(animVersion))
    headerString.write('blenderVersion {}; # this should be mayaVersion but this signifies it was exported with Blender\n'.format(blenderVersion))
    headerString.write('timeUnit {};\n'.format(timeUnit))
    headerString.write('linearUnit {};\n'.format(linearUnit))
    headerString.write('angularUnit {};\n'.format(angularUnit))
    headerString.write('startTime {:n};\n'.format(startTime))
    headerString.write('endTime {:n};\n'.format(endTime))

    headerString.seek(0)
    return headerString, kwargs_mod

def write(fn, ioStream):
    with open(fn, "w", encoding='ascii') as a_file:
        a_file.write(ioStream.read())

def save_single(operator, scene, depsgraph, filepath="", context_objects=None, **kwargs):
    ioStream = io.StringIO()
    header, kwargs_mod = anim_header_elements(scene, **kwargs)
    ioStream.write(header.read())
    ioStream.write(anim_fcurve_elements(operator, context_objects, scene, **kwargs_mod).read())
    ioStream.seek(0)
    write(filepath, ioStream)
    
    # with open(Path(filepath).joinpath(filepath, filename), 'wb') as temp_file:
    #     temp_file.chow
    #     temp_file.write(buff)
    return {'FINISHED'}

def save(operator, context,
         filepath="",
         use_selection=False,
         use_visible=False,
         use_active_collection=False,
         **kwargs
        ):

        result = {'FINISHED'}

        active_object = context.view_layer.objects.active

        org_mode = None
        if active_object and active_object.mode != 'OBJECT' and bpy.ops.object.mode_set.poll():
            org_mode = active_object.mode
            bpy.ops.object.mode_set(mode='OBJECT')

        kwargs_mod = kwargs.copy()
        if use_active_collection:
            if use_selection:
                ctx_objects = tuple(obj
                                    for obj in context.view_layer.active_layer_collection.collection.all_objects
                                    if obj.select_get())
            else:
                ctx_objects = context.view_layer.active_layer_collection.collection.all_objects
        else:
            if use_selection:
                ctx_objects = context.selected_objects
            else:
                ctx_objects = context.view_layer.objects
        if use_visible:
            ctx_objects = tuple(obj for obj in ctx_objects if obj.visible_get())
        kwargs_mod["context_objects"] = ctx_objects

        depsgraph = context.evaluated_depsgraph_get()
        result = save_single(operator, context.scene, depsgraph, filepath, **kwargs_mod)

        if active_object and org_mode:
            context.view_layer.objects.active = active_object
            if bpy.ops.object.mode_set.poll():
                bpy.ops.object.mode_set(mode=org_mode)

        return result