# About
Maya's ANIM import/export plugin v1.3.0 for Blender 3.6

Source: [ANIM file format | Maya 2020 - Autodesk Knowledge Network](https://help.autodesk.com/view/MAYAUL/2020/ENU/?guid=GUID-87541258-2463-497A-A3D7-3DEA4C852644)

# Installation
1. Download a Release zip
2. Go to Preferences window -> Add-ons -> Install...
3. Select the zip file
4. Enjoy

# Usage
File -> Import -> Maya Animation (.anim)
File -> Export -> Maya Animation (.anim)

Works for objects and armature bones.

Imported animations are converted to current bone rotation mode. "Axis Angle" mode is not supported.

Exported rotations are always converted to Eulers with 'XYZ' order. This also means Quaternion rotation curves are prone to gimbal lock due to conversion.
Gimbal lock may also occur in other software if animation was exported with different axes.

## Features:
- Export and Import raw animation curves as presented by Blender ("Transform" OFF)
- Animation axis conversion between differently oriented world directions and bone transformation of a parent-space instead of Blender's rest-space ("Transform" ON)
- Control the bone scale for exported and imported animations, in case top hierarchy node is in different scale
- Baking world tranfsorm data to exported and imorted object and bone animations
- Presets!

### Import Features:
- Support for handling multiple files
- Offset the imported animation on the timeline
- Match framerate, Units and Time Range of Blender scene to the animation
- Limit import to selected bones

### Export Features:
- Option to limit the range of frames for exported animation instead of using all keyframes from timeline
- Option to export animation only for Deform bones instead of all that have animation data
- Name conversion for exported curves to either avoid spaces (necessary for this file format) or spaces and special characters - both can be performed for either export only or blender scene as well.

*This plugin contains content adapted from the Autodesk® Maya® Help, available under a Creative Commons Attribution-NonCommercial-Share Alike license. Copyright © Autodesk, Inc.*