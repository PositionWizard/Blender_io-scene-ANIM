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
    "blender" : (3, 4, 0),
    "version" : (1, 0, 0),
    "category": "Import-Export",
	"location": "File > Import/Export, Scene properties",
    "warning" : "",
}

if "bpy" in locals():
    import importlib
    if "export_anim" in locals():
        importlib.reload(export_anim)

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
class ExportANIM(bpy.types.Operator, ExportHelper):
    bl_idname = "maya_anim.export"
    bl_label = "Export ANIM"
    bl_description = "Export animation curves using Autodesk Maya file format"
    bl_options = {'UNDO', 'PRESET'}

    # filename: StringProperty(default="untitled.anim")
    filename_ext = ".anim"
    # filepath: StringProperty(subtype="FILE_PATH")
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
            items=(('EXPORT_SPACES', "Export only (spaces)", "Sanitize only spaces"),
                   ('EXPORT_ALL', "Export only", "Sanitize names only in the exported file"),
                   ('PROJECT_EXPORT_SPACES', "Project and Export (spaces)", "Sanitize only spaces both in current project and exported file"),
                   ('PROJECT_EXPORT_ALL', "Project and Export", "Sanitize names both in current project and exported file"),
                   ),
            description="Should object and bone names be sanitized.\n"
                        "Removes special characters and replaces them with '_'.\n\n"
                        "This has to be done at least for spaces to ensure continuity of strings.\n"
                        "For Autodesk Maya don't use '(spaces)' options",
            default='EXPORT_ALL',
            )

    use_time_range: BoolProperty(
            name="Use Time Range",
            description="If disabled, the start and end frame will be taken from the timeline",
            default=False
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

        # with open(Path(self.filepath).joinpath(self.filepath, self.filename), 'wb') as temp_file:
        #     temp_file.chow
        #     temp_file.write(buff)
        # return {'FINISHED'}

    # Optional custom invoke. I wanted to set start and end frame from the scene but that probably defeats the point of the "use_time_range" option.
    # def invoke(self, context, event):
    #     wm = bpy.context.window_manager
    #     wm.fileselect_add(self)
    #     self.start_time = bpy.context.scene.frame_start
    #     self.end_time = bpy.context.scene.frame_end
    #     return {'RUNNING_MODAL'}

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

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

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

        # sublayout = layout.column()
        # sublayout.prop(operator, 'use_time_range')

        # sublayout.use_property_split = False
        
        # sublayout = sublayout.split(factor = 0.5)
        # splitLayout = sublayout.split(factor = 0.5, align=True)
        # splitLayout.prop(operator, 'start_time')
        # splitLayout.prop(operator, 'end_time')
        # splitLayout.enabled = operator.use_time_range

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

def menu_func_export(self, context):
    self.layout.operator(ExportANIM.bl_idname, text="Maya Animation (.anim)")

classes = (
    ExportANIM,
    ANIM_PT_export_include,
    ANIM_PT_export_transform,
    ANIM_PT_export_animation
)

register_, unregister_ = bpy.utils.register_classes_factory(classes)

def register():
    register_()
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    unregister_()

if __name__ == "__main__":
    register()