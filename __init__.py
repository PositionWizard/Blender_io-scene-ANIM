# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
    "name" : "Maya ANIM format",
    "author" : "Czarpos",
    "description" : "Import/Export tool for .anim files created with Autodesk Maya.",
    "blender" : (3, 6, 20),
    "version" : (1, 3, 0),
    "category": "Import-Export",
	"location": "File > Import/Export, Scene properties",
    "warning" : "This addon is still in development.",
    "doc_url": "https://github.com/PositionWizard/Blender_io-scene-ANIM",
    "tracker_url": "https://github.com/PositionWizard/Blender_io-scene-ANIM/issues"
}

if "bpy" in locals():
    import importlib
    if "export_anim" in locals():
        importlib.reload(export_anim)
    if "import_anim" in locals():
        importlib.reload(import_anim)

import bpy
from bpy.props import (
        StringProperty,
        BoolProperty,
        FloatProperty,
        IntProperty,
        EnumProperty,
        CollectionProperty,
        )

from bpy_extras.io_utils import (
    ImportHelper,
    ExportHelper,
    orientation_helper,
    path_reference_mode,
    axis_conversion,
)

@orientation_helper(axis_forward='-Z', axis_up='Y')
class ImportANIM(bpy.types.Operator, ImportHelper):
    """Load a FBX file"""
    bl_idname = "maya_anim.import"
    bl_label = "Import ANIM"
    bl_description = "Import animation curves using Autodesk Maya file format"
    bl_options = {'UNDO', 'PRESET'}

    ###########################################
    # necessary to support multi-file import
    files: CollectionProperty(
        type=bpy.types.OperatorFileListElement,
        options={'HIDDEN', 'SKIP_SAVE'},
    )

    directory: StringProperty(
        subtype='DIR_PATH',
    )
    ##########################################

    filename_ext = ".anim"
    filter_glob: StringProperty(default="*.anim", options={'HIDDEN'})

    use_selected_bones: BoolProperty(
            name="Selected bones",
            description="Import animation only for bones selected in Pose Mode",
            default=False,
            )
    
    use_fps: BoolProperty(
        name="Frame Rate",
        description="Apply FPS settings from the file to scene",
        default=True
        )
    
    use_units: BoolProperty(
        name="Unit Systems",
        description="Set scene units from the file",
        default=False
        )
    
    use_timerange: BoolProperty(
        name="Time Range",
        description="Apply range for timeline as defined in the file",
        default=False
        )
    
    global_scale: FloatProperty(
            name="Bone Scale",
            description="Scale bone animation data\n\n"
                        "Some software may have all the boens scaled up or down.\n"
                        "Autodesk Maya may have top parent scale of 100 but still look normal,\n"
                        "however bones are actually 100 times smaller than they should be",
            min=0.001, max=1000.0,
            soft_min=0.01, soft_max=1000.0,
            default=1.0,
            )
    
    axis_transform: BoolProperty(
            name="",
            description="Whether to perform axis conversion or import raw keyframes",
            default=True,
        )
    
    apply_unit_linear: BoolProperty(
            name="Apply Linear Unit",
            description="Convert linear values by taking into account file's linear unit definition.",
            default=True,
        )
    
    bake_space_transform: BoolProperty(
            name="Apply Transform",
            description="Bake space transform into root bone animation. Avoids getting unwanted\n"
                        "rotations to objects when target space is not aligned with Blender's space\n\n"
                        "Disable for Autodesk Maya",
            default=False,
            )

    anim_offset: FloatProperty(
            name="Animation Offset",
            description="Offset to apply to animation during import, in frames",
            default=1.0,
            )
    
    use_custom_props: BoolProperty(
            name="Custom Properties",
            description="Import user properties as custom properties",
            default=True,
            )

    def draw(self, context):
        pass

    def execute(self, context):
        keywords = self.as_keywords(ignore=("filter_glob", "directory", "ui_tab", "filepath", "files"))

        global_matrix = (axis_conversion(from_forward=self.axis_forward,
                                         from_up=self.axis_up,
                                         ).to_4x4())


        keywords["global_matrix"] = global_matrix

        from . import import_anim

        return import_anim.load(self, context, directory=self.directory, files=self.files, filepath=self.filepath, file_ext=self.filename_ext, **keywords)

class ANIM_PT_import_include(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Include"
    bl_parent_id = "FILE_PT_operator"
    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "MAYA_ANIM_OT_import"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        sublayout = layout.column(heading="Limit to")
        sublayout.prop(operator, "use_selected_bones")

        sublayout = layout.column(heading="Scene settings")
        sublayout.prop(operator, "use_fps")
        sublayout.prop(operator, "use_units")
        sublayout.prop(operator, "use_timerange")

class ANIM_PT_import_transform(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Transform"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "MAYA_ANIM_OT_import"
    
    def draw_header(self, context):
        sfile = context.space_data
        operator = sfile.active_operator

        self.layout.prop(operator, "axis_transform", text="")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, "global_scale")
        layout.prop(operator, "axis_forward")
        layout.prop(operator, "axis_up")
        col = layout.column()
        col.prop(operator, "apply_unit_linear")
        col.prop(operator, "bake_space_transform")

class ANIM_PT_import_animation(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Animation"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "MAYA_ANIM_OT_import"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, "anim_offset")
        layout.prop(operator, "use_custom_props")

@orientation_helper(axis_forward='-Z', axis_up='Y')
class ExportANIM(bpy.types.Operator, ExportHelper):
    bl_idname = "maya_anim.export"
    bl_label = "Export ANIM"
    bl_description = "Export animation curves using Autodesk Maya file format"
    bl_options = {'UNDO', 'PRESET'}

    filename_ext = ".anim"
    filter_glob: StringProperty(
        default = "*.anim",
        options = {'HIDDEN'}
    )

    use_selection: BoolProperty(
            name="Selected Objects",
            description="Export selected and visible objects only",
            default=True,
            )
    use_visible: BoolProperty(
            name='Visible Objects',
            description='Export visible objects only',
            default=False
            )
    use_active_collection: BoolProperty(
            name="Active Collection",
            description="Export only objects from the active collection (and its children)",
            default=False,
            )

    bake_axis: BoolProperty(
            name="",
            description="Whether to perform axis conversion or export raw keyframes\n\n"
                        "WARNING!: Disabling this for Quaternion rotation will break it!",
            default=True,
        )

    global_scale: FloatProperty(
            name="Bone Scale",
            description="Scale bone animation data\n\n"
                        "Some software may have all the boens scaled up or down.\n"
                        "Autodesk Maya may have top parent scale of 100 but still look normal,\n"
                        "however bones are actually 100 times smaller than they should be",
            min=0.001, max=1000.0,
            soft_min=0.01, soft_max=1000.0,
            default=1.0,
            )

    bake_space_transform: BoolProperty(
            name="Apply Transform",
            description="Bake bones' space transform into armature, avoids getting unwanted\n"
                        "rotations to objects when target space is not aligned with Blender's space\n\n"
                        "Disable for Autodesk Maya",
            default=False,
            )

    object_types: EnumProperty(
            name="Object Types",
            options={'ENUM_FLAG'},
            items=(('EMPTY', "Empty", ""),
                   ('CAMERA', "Camera", ""),
                   ('LIGHT', "Lamp", ""),
                   ('ARMATURE', "Armature", "WARNING: not supported in dupli/group instances"),
                   ('MESH', "Mesh", ""),
                   ('OTHER', "Other", "Other geometry types, like curve, metaball, etc. (converted to meshes)"),
                   ),
            description="Which kind of object to export",
            default={'EMPTY', 'CAMERA', 'LIGHT', 'ARMATURE', 'MESH', 'OTHER'},
            )

    sanitize_names: EnumProperty(
            name="Sanitize Names",
            items=(('EXPORT_ONLY', "Export only", "Sanitize names only in the exported file"),
                   ('EXPORT_AND_PROJECT', "Project and Export", "Sanitize names both in current project and exported file"),
                   ),
            description="Should object and bone names be sanitized.\n"
                        "Removes special characters and replaces them with '_'.\n\n"
                        "This has to be done at least for spaces to ensure continuity of strings",
            default='EXPORT_ONLY',
            )
    
    sanitize_spacesOnly: BoolProperty(
            name="Spaces",
            description="Sanitize only spaces\n\n"
                        "For Autodesk Maya this should be disabled",
            default=False
        )

    use_time_range: BoolProperty(
            name="Use Time Range",
            description="If disabled, the start and end frame will be taken from the timeline",
            default=False
            )

    only_deform_bones: BoolProperty(
            name="Only Deform Bones",
            description="Export cruves only for bones tagged with Deform flag",
            default=True
            )

    def upd_end(self, context):
        if self.start_time >= self.end_time:
            self.start_time = self.end_time - 1

    def upd_start(self, context):
        if self.end_time <= self.start_time:
            self.end_time = self.start_time + 1

    start_time: IntProperty(
            name="Start",
            description="Starting frame of animation",
            default=0,
            min=0,
            update=upd_start
            )

    end_time: IntProperty(
            name="End",
            description="Ending frame of animation",
            default=30,
            min=0,
            update=upd_end
            )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        sublayout = layout.column()
        sublayout.prop(operator, "sanitize_names")
        sublayout = layout.column(heading="Sanitize only")
        sublayout.prop(operator, "sanitize_spacesOnly")

    def execute(self, context):
        from . import export_anim

        if not self.filepath:
            raise Exception("filepath not set")
        
        global_matrix = (axis_conversion(to_forward=self.axis_forward,
                                         to_up=self.axis_up,
                                         ).to_4x4())

        keywords = self.as_keywords(ignore=("check_existing",
                                            "filter_glob",
                                            "ui_tab",
                                            ))

        keywords["global_matrix"] = global_matrix
        return export_anim.save(self, context, **keywords)

class ANIM_PT_export_include(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Include"
    bl_parent_id = "FILE_PT_operator"
    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "MAYA_ANIM_OT_export"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        sublayout = layout.column(heading="Limit to")
        sublayout.prop(operator, "use_selection")
        sublayout.prop(operator, "use_visible")
        sublayout.prop(operator, "use_active_collection")

        layout.column().prop(operator, "object_types")

class ANIM_PT_export_transform(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Transform"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "MAYA_ANIM_OT_export"

    def draw_header(self, context):
        sfile = context.space_data
        operator = sfile.active_operator

        self.layout.prop(operator, "bake_axis", text="")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.enabled = operator.bake_axis
        layout.prop(operator, "global_scale")
        layout.prop(operator, "axis_forward")
        layout.prop(operator, "axis_up")
        layout.prop(operator, "bake_space_transform")

class ANIM_PT_export_animation(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Animation"
    bl_parent_id = "FILE_PT_operator"
    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "MAYA_ANIM_OT_export"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        flow = layout.grid_flow()
        col = flow.column()

        row = col.row()
        row.prop(operator, 'use_time_range')

        col.use_property_split = False

        row = col.row()
        row.label(text="Time:")
        splitrow = row.split(factor = 0.5, align=True)
        splitrow.prop(operator, 'start_time')
        splitrow.prop(operator, 'end_time')
        row.enabled = operator.use_time_range

        col.use_property_split = True

        row = col.row()
        row.prop(operator, 'only_deform_bones')

def menu_func_import(self, context):
    self.layout.operator(ImportANIM.bl_idname, text="Maya Animation (.anim)")

def menu_func_export(self, context):
    self.layout.operator(ExportANIM.bl_idname, text="Maya Animation (.anim)")

classes = (
    ImportANIM,
    ANIM_PT_import_include,
    ANIM_PT_import_transform,
    ANIM_PT_import_animation,
    ExportANIM,
    ANIM_PT_export_include,
    ANIM_PT_export_transform,
    ANIM_PT_export_animation
)

register_, unregister_ = bpy.utils.register_classes_factory(classes)

def register():
    register_()
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    unregister_()

if __name__ == "__main__":
    register()