# Blender_io-scene-ANIM
Maya's ANIM import/export plugin for Blender

Source: [ANIM file format | Maya 2020 - Autodesk Knowledge Network](https://knowledge.autodesk.com/support/maya/learn-explore/caas/CloudHelp/cloudhelp/2022/ENU/Maya-Animation/files/GUID-87541258-2463-497A-A3D7-3DEA4C852644-htm.html)


# Usage
File -> Export -> Maya Animation (.anim)

Simply install as addon through Preferences window.
Currently only supports exporting. Works for objects and armature bones.

Known bugs:
- All of either position, rotation or translation channels must be keyframed, otherwise animation may be exported broken
- Euler curves are prone to gimbal lock on exported files
