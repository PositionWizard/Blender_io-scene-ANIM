# About
Maya's ANIM import/export plugin for Blender v1.2.3

Source: [ANIM file format | Maya 2020 - Autodesk Knowledge Network](https://help.autodesk.com/view/MAYAUL/2020/ENU/?guid=GUID-87541258-2463-497A-A3D7-3DEA4C852644)


# Usage
File -> Export -> Maya Animation (.anim)

Simply install as addon through Preferences window.
Currently only supports exporting. Works for objects and armature bones.

Animated rotations are always converted to Eulers with 'XYZ' order. This also means Quaternion rotation curves are prone to gimbal lock due to conversion.
Gimbal lock may also occur in other software if animation was exported with different axes.

## Features:
- Export raw animation curves as presented by Blender ("Transform" OFF)
- Animation axis conversion to differently oriented world directions and bone transformation to a parent-space instead of Blender's rest-space ("Transform" ON)
- Control the bone scale for exported animations, in case target software top hierarchy node is in different scale
- Baking world tranfsorm data to exported object and bone animations
- Option to limit the range of frames for exported animation instead of using all keyframes from timeline
- Option to export animation only for Deform bones instead of all that have animation data
- Name conversion for exported curves to either avoid spaces (necessary for this file format) or spaces and special characters - both can be performed for either export only or blender scene as well.
- Presets!
