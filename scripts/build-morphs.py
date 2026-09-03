"""Собирает именованные морфы BodySlide поверх готового тела вервольфа.

Отличия от первого пробника (tools/blender-morph-probe.py), каждое из которых
однажды стоило прогона:

1. Один ползунок кладётся сразу на ВСЕ формы, которые его касаются. Тело волка
   собрано слоями: кожа `body`, а поверх неё отдельные оболочки шерсти
   `fur_belly`, `fur_chest`, `fur_back`. Если сдвинуть только кожу, она вылезет
   сквозь шерсть, и вместо ползунка получится дыра.

2. У каждой стороны свой центр вращения. Общий центр для парных костей
   оказывается на осевой линии тела, и уши разъезжаются вбок вместо того,
   чтобы удлиняться.

3. Раздувание идёт от оси тела, а не по нормалям. Сдвиг вдоль нормалей на
   величину больше радиуса кривизны выворачивает поверхность наизнанку.

4. Область можно задать не костями, а куском пространства. У вервольфа кости
   спины держат в основном гриву на груди, а не живот, поэтому «раздуть по
   весам спины» распускает воротник и не трогает брюхо.

Способы сдвига:
  grow    -- растяжение от основания кости: длина. Для ушей, хвоста, морды.
  barrel  -- наружу от вертикальной оси через кость: обхват. Маска по весам.
  region  -- растяжение обхвата вокруг вертикальной оси. Область -- пояс по
             высоте, помноженный на сумму весов перечисленных СВОИХ костей.
             Для живота, груди, бёдер: там, где нужна одна кость на всю
             область, а таких костей у зверя нет.

PyNifly уводит форму-ключ с именем '>Имя' в файл морфов (nif/export_nif.py,
trip_morphs). Экспорт обязан идти в путь, содержащий папку `meshes`: метка
BODYTRI пишется обрезкой пути по этому имени.

  blender.exe --background --python build-morphs.py -- <in.nif> <out.nif> <spec.json> [preview_dir]

Если задана папка для показа, после сборки снимаются кадры: тело без морфов,
с каждым ползунком по отдельности и со всеми сразу. Рамка кадра берётся ОДНА
на все состояния -- иначе камера отъезжает от разбухшего тела и сравнение врёт.
"""
import sys, json, bpy, addon_utils
from mathutils import Vector

_v = bpy.context.preferences.view
try:
    _v.use_translate_new_dataname = False
    _v.use_translate_interface = False
    _v.language = 'en_US'
except Exception:
    pass
addon_utils.enable("io_scene_nifly", default_set=False, persistent=True)

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT, SPEC = argv[0], argv[1], argv[2]
PREVIEW = argv[3] if len(argv) > 3 else None
spec = json.load(open(SPEC, encoding='utf-8'))

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.pynifly(filepath=SRC)
arm = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)


def bone_head(name):
    if arm is None or name not in arm.data.bones:
        return None
    return arm.matrix_world @ arm.data.bones[name].head_local


def smooth(t):
    """Плавная ступенька 0..1: без неё край области видно швом."""
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return t * t * (3.0 - 2.0 * t)


def weight_of(v, gi):
    return min(1.0, sum(g.weight for g in v.groups if g.group in gi))


for item in spec:
    morph = item['morph']
    for shape in item['shapes']:
        obj = bpy.data.objects.get(shape)
        if obj is None:
            print("BUILD|%-12s нет формы %s" % (morph, shape))
            continue

        # плановый сдвиг на каждую вершину, накопленный по всем частям
        delta = {}
        for part in item['parts']:
            amount = float(part['amount'])
            mode = part.get('mode', 'barrel')

            if mode == 'region':
                # Раздувание задаётся МНОЖИТЕЛЕМ обхвата, а не сдвигом в единицах.
                # Сдвиг на одинаковую величину переставляет вершины местами:
                # внутренняя, сдвинутая на 22, обгоняет внешнюю, сдвинутую на 0,
                # и на силуэте появляется жёсткий бортик. Растяжение порядок
                # сохраняет, и поверхность остаётся гладкой.
                ax = Vector(part.get('axis', [0.0, 0.0]))
                z0, z1 = part['zRange']
                fade = float(part.get('zFade', 8.0))
                cap = float(part.get('maxShift', 1e9))
                # Принадлежность к области задаётся СПИСКОМ СВОИХ костей, а не
                # списком чужих. Отрицательный список приходится держать полным,
                # и он однажды пропустил пальцы: у вервольфа кисти висят на
                # уровне живота, кость называется Finger, и раздувание утащило
                # когти на полметра в стороны.
                good = [g.index for g in obj.vertex_groups
                        if any(k.lower() in g.name.lower()
                               for k in part.get('includeContains', []))]
                for i, v in enumerate(obj.data.vertices):
                    co = obj.matrix_world @ v.co
                    wz = smooth((co.z - z0) / fade) * smooth((z1 - co.z) / fade)
                    if wz <= 0.01:
                        continue
                    wb = min(1.0, sum(g.weight for g in v.groups
                                      if g.group in good))
                    w = wz * wb
                    if w <= 0.01:
                        continue
                    r = Vector((co.x - ax.x, co.y - ax.y, 0.0))
                    if r.length < 1e-4:
                        continue
                    # потолок сдвига держит гриву: она висит вчетверо дальше от
                    # оси, чем кожа, и тот же множитель разносит её пряди врозь.
                    # min от двух растущих функций сам растёт, поэтому порядок
                    # вершин по радиусу не переставляется и бортика не будет
                    shift = min(r.length * (amount - 1.0), cap)
                    delta[i] = delta.get(i, Vector((0, 0, 0))) +                         r.normalized() * (shift * w)
                continue

            gi = [obj.vertex_groups[b].index for b in part['bones']
                  if b in obj.vertex_groups]
            if not gi:
                continue
            pivot = bone_head(part.get('pivot') or part['bones'][0])
            if pivot is None:
                print("BUILD|%-12s %s: нет кости-опоры" % (morph, shape))
                continue
            for i, v in enumerate(obj.data.vertices):
                w = weight_of(v, gi)
                if w <= 0.01:
                    continue
                co = obj.matrix_world @ v.co
                if mode == 'grow':
                    # удлинение: растяжение от основания кости
                    d = (co - pivot) * ((amount - 1.0) * w)
                else:
                    # бочка: наружу от вертикальной оси, проходящей через опору
                    r = Vector((co.x - pivot.x, co.y - pivot.y, 0.0))
                    if r.length < 1e-4:
                        continue
                    d = r.normalized() * (amount * w)
                delta[i] = delta.get(i, Vector((0, 0, 0))) + d

        if not delta:
            print("BUILD|%-12s %-14s костей нет, пропуск" % (morph, shape))
            continue

        if obj.data.shape_keys is None:
            obj.shape_key_add(name='Basis', from_mix=False)
        sk = obj.shape_key_add(name='>' + morph, from_mix=False)
        inv = obj.matrix_world.inverted()
        mx = 0.0
        for i, d in delta.items():
            sk.data[i].co = inv @ ((obj.matrix_world @ obj.data.vertices[i].co) + d)
            mx = max(mx, d.length)
        print("BUILD|%-12s %-14s сдвинуто %6d из %6d, макс %6.2f"
              % (morph, shape, len(delta), len(obj.data.vertices), mx))

for o in bpy.data.objects:
    o.select_set(True)
bpy.ops.export_scene.pynifly(filepath=OUT, target_game='SKYRIMSE',
                             write_tris=True, write_bodytri=True)
print("BUILD|экспорт ok ->", OUT)

if not PREVIEW:
    sys.exit(0)

# ---------------------------------------------------------------- показ ------
import os, math, mathutils
PREVIEW = os.path.abspath(PREVIEW)
os.makedirs(PREVIEW, exist_ok=True)
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
keys = sorted({item['morph'] for item in spec})


def frame(objs):
    mins = mathutils.Vector((1e18,) * 3)
    maxs = mathutils.Vector((-1e18,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            for k in range(3):
                mins[k] = min(mins[k], w[k])
                maxs[k] = max(maxs[k], w[k])
    return (mins + maxs) / 2, (max(maxs - mins) / 2 or 20.0)


scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
sh = scene.display.shading
sh.light = 'STUDIO'
sh.color_type = 'SINGLE'
sh.single_color = (0.62, 0.60, 0.58)
sh.show_shadows = True
sh.show_cavity = True
sh.cavity_type = 'BOTH'
sh.curvature_ridge_factor = 1.0
sh.curvature_valley_factor = 1.0
scene.render.resolution_x = 800
scene.render.resolution_y = 800
world = bpy.data.worlds.new("W")
scene.world = world
world.use_nodes = True
for n in world.node_tree.nodes:
    if n.type == 'BACKGROUND':
        n.inputs[0].default_value = (0.05, 0.05, 0.06, 1)
for m in bpy.data.materials:
    try:
        m.blend_method = 'HASHED'
    except Exception:
        pass

cam_data = bpy.data.cameras.new("Cam")
cam_data.type = 'ORTHO'
cam_data.clip_start = 0.1
cam = bpy.data.objects.new("Cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
lights = []
for pos, energy in (((1, -1, 1), 6.0), ((-1, -0.6, 0.4), 3.0), ((0, 1, 0.6), 2.5)):
    ld = bpy.data.lights.new("L", type='AREA')
    lo = bpy.data.objects.new("L", ld)
    scene.collection.objects.link(lo)
    lights.append((lo, ld, mathutils.Vector(pos), energy))

# рамки считаются по телу БЕЗ морфов, до того как ползунки что-то раздули
head = [o for o in meshes if o.name in ('head', 'fur_face', 'FurfaceBlend')]
views = [("body", frame(meshes), 200.0, 1.15),
         ("side", frame(meshes), 90.0, 1.15),
         ("head", frame(head or meshes), 95.0, 1.35)]


def place(center, rad, deg, pad):
    cam_data.ortho_scale = rad * 2 * pad
    cam_data.clip_end = rad * 40
    ang = math.radians(deg)
    dist = rad * 12
    cam.location = center + mathutils.Vector(
        (math.sin(ang) * dist, -math.cos(ang) * dist, rad * 0.15))
    cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
    for lo, ld, pos, energy in lights:
        ld.energy = energy * rad * rad * 0.6
        ld.size = rad
        lo.location = center + pos * rad * 3.0
        lo.rotation_euler = (center - lo.location).to_track_quat('-Z', 'Y').to_euler()


def setkeys(active):
    for o in meshes:
        if not o.data.shape_keys:
            continue
        for kb in o.data.shape_keys.key_blocks:
            if kb.name.startswith('>'):
                kb.value = 1.0 if kb.name[1:] in active else 0.0


states = [("0-base", set())] + [("%d-%s" % (i + 1, k), {k}) for i, k in enumerate(keys)]
if len(keys) > 1:
    states.append(("%d-all" % (len(keys) + 1), set(keys)))

for label, active in states:
    setkeys(active)
    for vname, (center, rad), deg, pad in views:
        place(center, rad, deg, pad)
        scene.render.filepath = os.path.join(PREVIEW, "%s-%s.png" % (vname, label))
        bpy.ops.render.render(write_still=True)
        print("SHOT|%s" % scene.render.filepath)

