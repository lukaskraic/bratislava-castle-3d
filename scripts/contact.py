"""Blender -b -P scripts/contact.py -- out.jpg img1.png img2.png ...  -> 2-column contact sheet (480px tiles)"""
import bpy, sys, numpy as np
a = sys.argv[sys.argv.index('--') + 1:]
out, ims = a[0], a[1:]
tw, th = 480, 270
tiles = []
for p in ims:
    im = bpy.data.images.load(p)
    im.scale(tw, th)
    px = np.array(im.pixels[:], dtype=np.float32).reshape(th, tw, 4)
    tiles.append(px)
cols = 2
rows = (len(tiles) + 1) // 2
sheet = np.ones((rows * th, cols * tw, 4), dtype=np.float32)
for i, t in enumerate(tiles):
    r, c = divmod(i, cols)
    r = rows - 1 - r
    sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = t
img = bpy.data.images.new('sheet', cols * tw, rows * th)
img.pixels.foreach_set(sheet.ravel())
img.filepath_raw = out
img.file_format = 'JPEG'
img.save()
