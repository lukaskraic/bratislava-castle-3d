import bpy, sys, numpy as np
a = sys.argv[sys.argv.index('--') + 1:]
src, out, x0, y0, x1, y1 = a[0], a[1], *map(float, a[2:6])
im = bpy.data.images.load(src); w, h = im.size
px = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
c = px[int(h * (1 - y1)):int(h * (1 - y0)), int(w * x0):int(w * x1)]
o = bpy.data.images.new('c', c.shape[1], c.shape[0]); o.pixels.foreach_set(c.ravel()); o.filepath_raw = out; o.file_format = 'JPEG'; o.save()
