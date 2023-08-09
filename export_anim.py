if "bpy" in locals():
    import importlib
    if "anim_utils" in locals():
        importlib.reload(anim_utils)

import bpy, io, math, time
from mathutils import Matrix, Euler, Vector, Quaternion

from . import anim_utils

"""
TODO
- Instead of baking all relevant channels, do a proper fcurve swapping when doing axis conversions and armature transformations
"""

def dupe_obj(obj):
    obj = obj.copy()
    arm = obj.data.copy()
    obj.data = arm

    bpy.context.scene.collection.objects.link(obj)
    obj.make_local()
    obj.data.make_local()

    return obj

# Sanitization replaces all special characters with underscores
def names_sanitize(name, wildcard=""):
    if wildcard:
        name_clean = name.replace(wildcard, '_')
    else:
        name_clean = ''.join(c if c.isalnum() else '_' for c in name)
    return name_clean

def bone_calculate_parentSpace(bone):
    # Get bone's parent-space matrix and if bone has no parent, then get armature-space matrix
    if bone.parent:
        boneMat = Matrix(bone.parent.matrix_local.inverted() @ bone.matrix_local)
    else:
        boneMat = bone.matrix_local
     
    return boneMat

def offset_rotation(keys_array, fc_path, node_rot):
    # get a rotation matrix of the animated values
    # TODO add option to retain original bone rotation  
    if fc_path.endswith('quaternion'):
        key_rotValues = Quaternion(keys_array)
    else:
        key_Euler = Euler(keys_array, 'XYZ')
        key_rotValues = key_Euler.to_quaternion()

    rotMat = node_rot @ key_rotValues

    return rotMat

# Offset transforms for multiple channels at once per transform type
def offset_transforms(node_tForm_Space, eulRef, frame, fc_group, fc_path, keys_array, apply_scaling, attr_name, global_scale, **kwargs):
    key_values_Space = [None]*3
    node_loc, node_rot, node_scale = node_tForm_Space.decompose()

    transform_map = {
        'translate': key_values_Space[0],
        'rotate': key_values_Space[1],
        'scale': node_scale
    }

    # Transform rotation and translation curves to a new space
    if attr_name == 'rotate':
        rotMat = offset_rotation(keys_array, fc_path, node_rot)

        # TODO add option to retain original bone rotation        
        # final rotation values need to be in Euler XYZ because anim format doesn't support different rotation orders
        # filter euler values (anti-gimbal lock) by a compatibile euler from the already converted first rotation keyframes, NOT current keyframes pre-conversion
        key_values_Space[1] = rotMat.to_euler('XYZ', eulRef)

        transform_map[attr_name] = key_values_Space[1]
    elif attr_name == 'translate':
        key_transValues = Vector(keys_array).to_3d()
        # scale curves according to Bone Scale but only for bones
        if apply_scaling:
            key_transValues *= global_scale
        newMat = node_tForm_Space @ Matrix.Translation(key_transValues)
        transform_map[attr_name] = key_values_Space[0] = newMat.translation

    # loop through those few curves' keyframes and find all keys on the same frame as the initial one
    for i, fc in enumerate(fc_group):
        if fc_path.endswith('quaternion') and i == 3:
            continue
        t_value = transform_map[attr_name][i]
        kp_found = False
        for k in fc.keyframe_points:
            if k.co[0] == frame:
                kp_value  = k.co[1] # get key's value
                # Offset curves by bone's parent-space transforms (replace original curves with posed parent-space ones)
                k.handle_left[1] = (k.handle_left[1]-kp_value)+t_value
                k.co[1] = t_value
                k.handle_right[1] = (k.handle_right[1]-kp_value)+t_value

                kp_found = True
                break # break early from looking for another keyframe since there's no need
            
        # insert keyframes for curves with missing keys on evaluated frame (this is pretty much baking)
        # TODO do a proper fcurve swapping when doing axis conversions and armature transformations, instead of baking all relevant channels
        if not kp_found:
            fc.keyframe_points.insert(frame=frame, value=t_value)

def anim_keys_elements(fc, dt_output, use_time_range, start_time, end_time, **kwargs):
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
            tan_angle = anim_utils.angular_converter(math.atan(tan)) # convert back to angular through "atan" and to degrees
            
            if tan_angle < 0.001 and tan_angle > -0.001: # round the number
                tan_angle = 0
        else:
            tan_angle = math.copysign(90, y) # 0 value is 90!

        # mag = math.sqrt(math.pow(x, 2)+math.pow(y, 2)) # line below is the same but much shorter lmao
        tan_mag = math.hypot(x, y)

        return round(tan_angle, 6), round(tan_mag, 6)    

    keyString.write(tab+'keys {\n')
    fc = bpy.types.FCurve(fc)
    
    prev_interp = None
    # get keyframe's frame and values
    for kp in fc.keyframe_points:
        kp = bpy.types.Keyframe(kp)

        if use_time_range:
            if not (kp.co[0] >= start_time and kp.co[0] <= end_time):
                continue

        keyString.write(tab*2+"{} ".format(round(kp.co[0], 6))) # write frame number
        kp_value = kp.co[1] # get key's value

        if dt_output == 'linear':
            kp_value = anim_utils.linear_converter(kp.co[1])

        elif dt_output == 'angular':
            kp_value = anim_utils.angular_converter(kp.co[1])

        keyString.write(f"{kp_value:.6f} ") # write value

        if kp.interpolation != 'BEZIER':
            out_tan = anim_utils.ANIM_TANGENT_TYPE[kp.interpolation]
        else:
            out_tan = anim_utils.ANIM_TANGENT_TYPE[kp.handle_right_type]
            
        if prev_interp != 'BEZIER' and prev_interp is not None:
            in_tan = anim_utils.ANIM_TANGENT_TYPE[kp.interpolation]
        else:
            in_tan = anim_utils.ANIM_TANGENT_TYPE[kp.handle_left_type]

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

def anim_animData_elements(fc, node, fc_path, angularUnit, **kwargs):
    animDataString = io.StringIO()
    animDataString.write('animData {\n') # open the data block
    tab = "  "

    if fc_path.endswith('quaternion'):
        fc_unit_type = 'ROTATION'       # have to change it because we're converting quaternions to eulers and quaternion is unitless even though it's in radians
    else:
        fc_unit_type = node.bl_rna.properties[fc_path].unit # get the curve unit (degrees, radians, linear, etc.)

    dt_input = 'time'
    dt_output = anim_utils.ANIM_UNIT_TYPE[fc_unit_type]
    dt_weighted = 1 # Blender always has weighted tangents
    dt_tan = angularUnit
    dt_preInf = dt_postInf = fc.extrapolation.lower() # set either linear or constant
    
    # check for any cyclic modifiers and apply a different pre and post infinity type
    for mod in fc.modifiers:
        if mod.type == 'CYCLES':
            if mod.mode_before != 'NONE': dt_preInf = anim_utils.ANIM_CYCLES_TYPE[mod.mode_before]
            if mod.mode_after != 'NONE': dt_postInf = anim_utils.ANIM_CYCLES_TYPE[mod.mode_after]
            break
 
    animDataString.write(tab+'input {};\n'.format(dt_input))
    animDataString.write(tab+'output {};\n'.format(dt_output))
    animDataString.write(tab+'weighted {};\n'.format(dt_weighted))

    # check keys if any of them are 'fixed' tangents (Blender's "Aligned")
    if any([kp for kp in fc.keyframe_points if kp.handle_left_type == 'ALIGNED' or kp.handle_right_type == 'ALIGNED']):
        animDataString.write(tab+'tangentAngleUnit {};\n'.format(dt_tan))

    animDataString.write(tab+'preInfinity {};\n'.format(dt_preInf))
    animDataString.write(tab+'postInfinity {};\n'.format(dt_postInf))

    # write keyframes
    animDataString.write(anim_keys_elements(fc, dt_output, **kwargs).read())
    animDataString.write('}\n') # close the data block

    animDataString.seek(0)
    return animDataString

def anim_fcurve_elements(self, context, objs, sanitize_names, sanitize_spacesOnly, global_matrix, bake_space_transform, **kwargs):
    fcurveString = io.StringIO()
    bake_axis = kwargs["bake_axis"]
    global_scale = kwargs["global_scale"]
    only_deform_bones = kwargs["only_deform_bones"]
    use_time_range = kwargs["use_time_range"]
    start_time = kwargs["start_time"]
    end_time = kwargs["end_time"]
    kwargs_mod = kwargs.copy()

    def get_node_info(node):
        # TODO FIGURE OUT WHY IT DOESN'T WORK IN MAYA
        # if isinstance(node, bpy.types.PoseBone):
        #     row = len(node.parent_recursive)
        # else: row = 0 # TODO count hierarchy place for objects
        row = 0

        # Write data for anim line: obj/bone name, children count, fcurve number
        wildcard = ""
        # Clean the name of exported objects/bones
        if sanitize_spacesOnly: # apply wildcard for spaces
            wildcard = " "
        # Now sanitize either for project and export or just project, wildcard will be still applied depending on choice
        if sanitize_names == 'EXPORT_ONLY':
            node_name_final = names_sanitize(node.name, wildcard)
        else:
            node_name_final = node.name = names_sanitize(node.name, wildcard)

        child = len(node.children) # count children

        return node_name_final, row, child
    
    def write_fcurve(fc, node, node_info, fc_path, attr_i, attr_name, **kwargs):
        fc = bpy.types.FCurve(fc)
        fcurveString.write('anim ')
                
        # if fc_path.endswith("quaternion"):
        #     axis_ASCII = 87
        # else:
        #     axis_ASCII = 88
        
        fc_chan = chr(anim_utils.ASCII_X+fc.array_index) # start counting and return a character of either W, X, Y or Z
        node_name_final, row, child = node_info

        fcurveString.write('{0}.{0}{1} {0}{1} '.format(attr_name, fc_chan)) # write basic node info
        fcurveString.write("{} {} {} {};\n".format(node_name_final, row, child, attr_i)) # write node name and detailed info

        # write the animData block
        fcurveString.write(anim_animData_elements(fc, node, fc_path, **kwargs).read())

    def get_frames(fcurves, use_time_range, start_time, end_time, frames=set()):
        for fc in fcurves:
            if use_time_range:
                fri = [kp.co[0] for kp in fc.keyframe_points if kp.co[0] >= start_time and kp.co[0] <= end_time]
            else:
                fri = [kp.co[0] for kp in fc.keyframe_points]
            frames.update(fri)

        return frames

    # Prepare object or bone to apply offset transforms for all channels of a data type (either location, rotation or scale), all at once
    def prep_node(node, node_info, fcGroups, node_tForm_Space, apply_boneScale, action, bake_axis, **kwargs):
        use_time_range = kwargs["use_time_range"]
        start_time = kwargs["start_time"]
        end_time = kwargs["end_time"]
        kwargs_mod = kwargs.copy()
        kwargs_mod["rotMode"] = node.rotation_mode

        fc_i = 0
        for i, fc_group in enumerate(fcGroups):
            # translate attribute names
            fc_path = anim_utils.FCURVE_PATHS_ID_TO_NAME[i]
            try: attr = anim_utils.ANIM_ATTR_NAMES[fc_path]
            except KeyError: attr = fc_path

            # sort the fcurves according to array_index
            fc_group = sorted(fc_group, key=lambda fc: fc.array_index)

            kwargs_mod["attr_name"] = attr

            # do offsets only for locations and rotations, skip other data
            if fc_group:
                frames = set()
                frames = get_frames(fc_group, use_time_range, start_time, end_time, frames)

                if not frames:
                    continue

                if i<3 and bake_axis:
                    # create fcurves for entire array of a single property if one fcurve was keyed but others are straight up missing
                    # this is needed to properly evaluate fcurves and convert the axes
                    if not ((len(fc_group) == 3 and i != 2) or (len(fc_group) == 4)):
                        # only for quaternion
                        if i == 2:
                            fc_identity = [1,0,0,0]     # base for quaternion
                            fc_group_new = [None]*4
                        else:
                            fc_identity = [0,0,0]       # base for euler/location
                            fc_group_new = [None]*3

                        # get a list of fcurve indices for a given property
                        fc_ids = [fc.array_index for fc in fc_group]
                        
                        # create missing curves for the property and insert basic keyframes
                        for j, val in enumerate(fc_identity):
                            if j not in fc_ids:
                                fc = action.fcurves.new(data_path=fc_group[0].data_path, index=j)
                                fc.keyframe_points.insert(frame=list(frames)[0], value=val)
                                fc_group_new[j] = fc
                                
                            try:
                                pos_id = fc_group[j].array_index
                                fc_group_new[pos_id] = fc_group[j]
                            except IndexError: continue
                        fc_group = fc_group_new

                    # offset transforms for keys on all fcurves at once for each frame
                    keys_array_list = [[] for f in frames]
                    for j, fr in enumerate(frames):
                        # get all keyframe values for this data path
                        for fc in fc_group:
                            fc_value = fc.evaluate(fr)
                            keys_array_list[j].append(fc_value)
                    
                    # get rotation values as reference to properly filter next euler values
                    rotRef_mat = offset_rotation(keys_array_list[0], fc_path, node_tForm_Space.decompose()[1])
                    eulRef = rotRef_mat.to_euler('XYZ')

                    # have to loop through all the frames again to do the offset calculations, unfortunately...
                    # this is to avoid wrong offsets due to key modifications right after gathering them (it's offseting keys from already offset ones at previous frame, basically)
                    for j, fr in enumerate(frames):
                        # Do calculations for entire frames
                        offset_transforms(node_tForm_Space, eulRef, fr, fc_group, fc_path, keys_array_list[j], apply_boneScale, **kwargs_mod)

            for j, fc in enumerate(fc_group):
                if fc.data_path.endswith('quaternion') and j == 3:
                    continue
                else:
                    fc.update()
                    write_fcurve(fc, node, node_info, fc_path, fc_i, **kwargs_mod)
                    fc_i += 1

    # Return a correct bone hierarchy index if bone matches fcurve's data path
    def get_boneHierarchy_index(fc, obj):
        if 'pose.bones' in fc.data_path:
            data_name = fc.data_path.split('"')[1]
            data_index = obj.data.bones.find(data_name)
            return data_index
        else:
            return -1

    def convert_Axes(obj, global_matrix, global_scale, reverse=False):
        # Revert changes when done with the object
        if reverse:
            global_matrix = global_matrix.inverted()
            global_scale = 1/global_scale

        if bake_space_transform:
            dataMat = Matrix.Scale(global_scale, 4) @ global_matrix
        else: dataMat = Matrix.Scale(global_scale, 4)

        # transform armature or mesh by the new axis
        # this is basically "apply transforms"
        if hasattr (obj.data, 'transform'):
            obj.data.transform(dataMat)

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.object.mode_set(mode='OBJECT')
    
    for obj in objs:
        try: obj.animation_data.action.fcurves
        except: AttributeError(self.report({'ERROR'}, obj.name+" has no animation data."))
        else:
            # Create an internal copy of the action to avoid destructive workflow
            # TODO refactor this whole system to avoid making a copy altogether
            action = obj.animation_data.action.copy()
            kwargs_mod["action"] = action

            # Clone and convert the armature to different axis upon export
            if bake_axis:
                obj_og = obj
                obj = dupe_obj(obj)
                context.view_layer.objects.active = obj
                convert_Axes(obj, global_matrix, global_scale)
                
            objFcurves = [[] for i in range(5)]

            if obj.type == 'ARMATURE':
                # First off, sort all the bone's fcurves so their order aligns with bone hierarchy order.
                # This is extremely important, since Maya doesn't map curves by attribute name but by hierarchy, top-to-bottom.
                fcurves = sorted(action.fcurves, key=lambda fc: get_boneHierarchy_index(fc, obj))

                if only_deform_bones:
                    eval_bones = [b.name for b in obj.data.bones if b.use_deform]
                else:
                    eval_bones = obj.data.bones
                    
                boneCheckList = [None]*len(obj.data.bones)

                # get a list of bones that need to have "anim" line written down and also the ones that don't (for proper line skipping in the file)
                for fc in fcurves:
                    if 'pose.bones' in fc.data_path:
                        data_name = fc.data_path.split('"')[1]
                        fc_path = fc.data_path.split('.')[-1] # get only the last part
                        if data_name in eval_bones:
                            bone = bpy.types.Bone(obj.data.bones[data_name])
                            bone_id = obj.data.bones.find(data_name)

                            array_id = anim_utils.FCURVE_PATHS_NAME_TO_ID.get(fc_path, 4)
                            # add the bone to a list and mark as animated bone
                            if boneCheckList[bone_id] == None:
                                fc_list = [[] for i in range(5)]
                                fc_list[array_id].append(fc)
                                boneCheckList[bone_id] = [bone, True, fc_list]
                            else:
                                # update the entry with any fcurves left
                                boneCheckList[bone_id][2][array_id].append(fc)
                    else:
                        array_id = anim_utils.FCURVE_PATHS_NAME_TO_ID.get(fc.data_path, 4)
                        objFcurves[array_id].append(fc)

                # look for all the required but non-animated bones and flag them to skip keying
                lastValid_i = 0
                for i, b in enumerate(obj.data.bones):
                    if not boneCheckList[i]:
                        boneCheckList[i] = [b, False, []]
                    else:
                        lastValid_i = i

                # cull all the non-animated after last animated one
                boneCheckList = boneCheckList[:lastValid_i+1]

                # write obj animation data
                obj_info = get_node_info(obj)
                prep_node(obj, obj_info, objFcurves, global_matrix, False, **kwargs_mod)

                # write bone animation data
                # fcBoneData structure: [Bone], [animated?], [list(ActionFCurves):  [location], [rotation_euler], [rotation_quaternion], [scale], [other custom data]]
                for fcBoneData in boneCheckList:
                    if fcBoneData != None:
                        bone_info = get_node_info(fcBoneData[0])

                        # get frames for keys in a given time range, to check if curves should be written or not
                        bone_frames = set()
                        for fc_group in fcBoneData[2]:
                            bone_frames = get_frames(fc_group, use_time_range, start_time, end_time, bone_frames)

                        if fcBoneData[1] and bone_frames:
                            pbone = obj.pose.bones[fcBoneData[0].name]
                            # Do matrix transformations only once per bone!
                            bone_tForm_parentSpace = bone_calculate_parentSpace(fcBoneData[0])
                            prep_node(pbone, bone_info, fcBoneData[2], bone_tForm_parentSpace, True, **kwargs_mod)

                        else:
                            # if bone has no animation data, write a basic anim line
                            node_name_final, row, child = bone_info
                            fcurveString.write("anim {} {} {} {};\n".format(node_name_final, row, child, 0))
                                
            else:
                for fc in action.fcurves:
                    array_id = anim_utils.FCURVE_PATHS_NAME_TO_ID.get(fc.data_path, 4)
                    objFcurves[array_id].append(fc)

                # write obj animation data
                obj_info = get_node_info(obj)
                prep_node(obj, obj_info, objFcurves, global_matrix, False, **kwargs_mod)

            if bake_axis:
                bpy.data.armatures.remove(obj.data)
                context.view_layer.objects.active = obj = obj_og

                # (OBSOLETE) Restore original Armature transforms for non-destructive exporting
                # convert_Axes(obj, global_matrix, global_scale, True)

            bpy.data.actions.remove(action)

    fcurveString.seek(0)
    return fcurveString

def anim_header_elements(scene, **kwargs):
    headerString = io.StringIO()

    start_time = kwargs["start_time"]
    end_time = kwargs["end_time"]
    use_time_range = kwargs["use_time_range"]
    kwargs_mod = kwargs.copy()

    animVersion  = 1.1
    blenderVersion = bpy.app.version_string
    try:
        timeUnit = anim_utils.ANIM_TIME_UNITS[scene.render.fps]
    except KeyError: timeUnit = "Unknown Time Unit"
    finally: kwargs_mod["timeUnit"] = timeUnit
    kwargs_mod["linearUnit"] = linearUnit = anim_utils.ANIM_LINEAR_UNITS[scene.unit_settings.length_unit]
    kwargs_mod["angularUnit"] = angularUnit = anim_utils.ANIM_ANGULAR_UNITS[scene.unit_settings.system_rotation]

    # use timeline range if no custom range is set
    if not use_time_range:
        start_time = scene.frame_start
        end_time = scene.frame_end

    headerString.write('animVersion {:n};\n'.format(animVersion))
    headerString.write('mayaVersion {}; # this is actually Blender version\n'.format(blenderVersion))
    headerString.write('timeUnit {};\n'.format(timeUnit))
    headerString.write('linearUnit {};\n'.format(linearUnit))
    headerString.write('angularUnit {};\n'.format(angularUnit))
    headerString.write('startTime {:n};\n'.format(start_time))
    headerString.write('endTime {:n};\n'.format(end_time))

    headerString.seek(0)
    return headerString, kwargs_mod

def write(fn, ioStream):
    with open(fn, "w", encoding='ascii') as a_file:
        a_file.write(ioStream.read())

def save_single(operator, context, depsgraph, filepath="", context_objects=None, **kwargs):
    ioStream = io.StringIO()

    operator.report({'INFO'}, "Exporting ANIM...%r" % filepath)
    start_time = time.process_time()

    header, kwargs_mod = anim_header_elements(context.scene, **kwargs)
    ioStream.write(header.read())
    ioStream.write(anim_fcurve_elements(operator, context, context_objects, **kwargs_mod).read())
    ioStream.seek(0)
    write(filepath, ioStream)

    operator.report({'INFO'}, "Export finished in %.4f sec." % (time.process_time() - start_time))
    
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
        result = save_single(operator, context, depsgraph, filepath, **kwargs_mod)

        if active_object and org_mode:
            context.view_layer.objects.active = active_object
            if bpy.ops.object.mode_set.poll():
                bpy.ops.object.mode_set(mode=org_mode)

        return result