"""Лепит анатомию вервольфа и вживляет её в готовое тело.

Геометрия строится заново, по числам из рецепта. Из мода ABC взяты только мерки
-- профиль радиусов, длина, положение узла и мошонки, -- потому что скелет
вервольфа у нас с ним общий (XP32 SE Extended) и координаты переносятся один
к одному. Ни одной вершины ABC здесь нет: чужой меш нельзя ни включать в мод,
ни распространять.

Три решения, каждое со своей причиной:

1. **Ножны и ствол -- одна непрерывная труба.** Отдельная деталь, приставленная
   к животу, дала бы видимый шов и щель при движении. Труба начинается внутри
   тела, поэтому стыка не видно вовсе.

2. **Состояние покоя -- базовая геометрия, а вытянутое -- морф.** Мод без единого
   заданного морфа показывает только ножны с небольшим кончиком, как у зверя
   в покое. Всё остальное включается ползунком. Обратный порядок сделал бы
   «взрослое» состоянием по умолчанию.

3. **Развёртка ложится на кожу с текстуры самого тела.** Отдельная текстура
   означала бы новый файл, новый материал и новый повод разойтись с телом по
   цвету. Пятно кожи ищется по вершинам тела вокруг основания ножен.

  blender.exe --background --python build-genitals.py -- \
      <тело.nif> <скелет.nif> <выход.nif> <рецепт-анатомии.json> \
      [--body-morphs <рецепт-морфов-тела.json>] [папка_показа]

Рецепт морфов тела подключается тем же проходом нарочно. Файл морфов пишется
один на весь меш, и два раздельных прогона затирали его друг другу: в моде
оставался только последний собранный набор ползунков.
"""
import sys, os, json, math, bpy, addon_utils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import morphlib

_v = bpy.context.preferences.view
try:
    _v.use_translate_new_dataname = False
    _v.use_translate_interface = False
    _v.language = 'en_US'
except Exception:
    pass
addon_utils.enable("io_scene_nifly", default_set=False, persistent=True)

argv = sys.argv[sys.argv.index("--") + 1:]
BODYMORPHS = None
DONOR = None
if '--donor' in argv:
    k = argv.index('--donor')
    DONOR = argv[k + 1]
    argv = argv[:k] + argv[k + 2:]
if '--body-morphs' in argv:
    k = argv.index('--body-morphs')
    BODYMORPHS = argv[k + 1]
    argv = argv[:k] + argv[k + 2:]
BODY, SKEL, OUT, SPEC = argv[0], argv[1], argv[2], argv[3]
PREVIEW = argv[4] if len(argv) > 4 else None
spec = json.load(open(SPEC, encoding='utf-8'))

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

donor_co = None
if DONOR:
    # Донор читается ОТДЕЛЬНЫМ проходом и сразу выбрасывается: PyNifly при
    # повторном импорте вливает данные в существующие объекты, и два тела
    # в одной сцене не уживаются.
    bpy.ops.import_scene.pynifly(filepath=DONOR)
    donor_co = {o.name: [v.co.copy() for v in o.data.vertices]
                for o in bpy.data.objects if o.type == 'MESH'}
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    print('GEN|донор прочитан: форм %d' % len(donor_co))
bpy.ops.import_scene.pynifly(filepath=BODY)
body = bpy.data.objects['body']
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
body_objs = [o for o in bpy.data.objects if o.type == 'MESH']


# ---------------------------------------------------------------- кости ------
# Кости половых органов есть в скелете вервольфа (и у XP32, и у Werewolf Body
# for VR -- координаты совпадают до сотой), но в мешах тела их нет: меш несёт
# только те кости, на которые сам развешен. Значит их надо перенести из скелета,
# иначе развесить ствол не на что.
before = {o.name for o in bpy.data.objects}
bpy.ops.import_scene.pynifly(filepath=SKEL)
skel_objs = [o for o in bpy.data.objects if o.name not in before]
skel_arm = next(o for o in skel_objs if o.type == 'ARMATURE')

wanted = list(spec['weights']['chain']) + list(spec['weights']['knot']) \
    + list(spec['weights']['ballsBones']) + ['WWD 1']
# Кость переносится ЦЕЛИКОМ -- матрицей, а не парой «голова-хвост».
#
# Голова и хвост задают направление кости, но не её поворот вокруг собственной
# оси. Скин пишет в ниф матрицу привязки каждой кости, и если она расходится
# с той, что стоит в живом скелете, игра при отрисовке применяет разницу:
# вершину сносит тем сильнее, чем дальше она от своей кости.
#
# Ровно это и вышло 04.09. Кольца ствола в покое сжаты к устью, а развешены на
# кости, стоящие в двадцати единицах впереди. Мелкий поворот у кости давал
# двадцатикратный вынос вершины, и наружу выходил длинный тонкий шип, да ещё
# и вбок. При вытянутом ползунке вершины оказывались рядом со своими костями,
# вынос пропадал -- отсюда наблюдение «длина не изменилась, ширина увеличилась».
rest = {}
for n in wanted:
    b = skel_arm.data.bones.get(n)
    if b is None:
        print("GEN|в скелете нет кости %s" % n)
        continue
    # родителем годится и кость, которую мы заводим этим же проходом, иначе
    # цепочка WWD 1..9 разваливается в веер от таза
    parent, pb = None, b.parent
    while pb is not None and parent is None:
        if pb.name in arm.data.bones or pb.name in wanted:
            parent = pb.name
        pb = pb.parent
    rest[n] = (arm.matrix_world.inverted() @ skel_arm.matrix_world @ b.matrix_local,
               b.length, parent)

bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
made = []
for n, (m, length, _p) in rest.items():
    if n in arm.data.edit_bones:
        continue
    eb = arm.data.edit_bones.new(n)
    eb.matrix = m
    eb.length = max(length, 0.5)
    made.append(n)
# родство ставится вторым проходом: родитель мог быть заведён только что
for n, (_m, _l, parent) in rest.items():
    eb = arm.data.edit_bones.get(n)
    if eb is None or parent is None:
        continue
    pb = arm.data.edit_bones.get(parent)
    if pb is not None and pb is not eb:
        eb.parent = pb
        eb.use_connect = False
bpy.ops.object.mode_set(mode='OBJECT')
print("GEN|перенесено костей: %d, заведено новых %d" % (len(rest), len(made)))
for n, (_m, _l, parent) in sorted(rest.items()):
    print("GEN|   %-10s родитель %s" % (n, parent or "(нет)"))

# Скелет свою службу отслужил, и в сцене ему делать нечего. Убирается ЦЕЛИКОМ,
# а не только его арматура: вместе с ним приходят корень, BSXFlags, BSBound и
# SkeletonID, и при выгрузке они уезжают в тело. Тело актёра с зашитым внутрь
# корнем чужого скелета игра при вызове зверя не переживает -- ровно на этом
# упали оба захода 04.09.
for o in skel_objs:
    try:
        bpy.data.objects.remove(o, do_unlink=True)
    except Exception:
        pass
print("GEN|скелет убран из сцены: %d объектов" % len(skel_objs))


# ------------------------------------------------------------- развёртка -----
# Медианный UV вершин тела вокруг основания ножен: цвет ляжет тот же, что
# у окружающей кожи, и отдельная текстура не понадобится.
uvspec = spec['uv']
c = Vector(uvspec['probeCenter'])
near = {i for i, v in enumerate(body.data.vertices)
        if (v.co - c).length < uvspec['probeRadius']}
uvl = body.data.uv_layers.active.data
us, vs = [], []
for poly in body.data.polygons:
    for li in poly.loop_indices:
        if body.data.loops[li].vertex_index in near:
            us.append(uvl[li].uv[0])
            vs.append(uvl[li].uv[1])
us.sort()
vs.sort()
u0 = us[len(us) // 2] if us else 0.5
v0 = vs[len(vs) // 2] if vs else 0.5
half = uvspec['patchSize'] / 2.0
print("GEN|пятно развёртки U %.4f V %.4f, сторона %.3f  (вершин тела рядом %d)"
      % (u0, v0, uvspec['patchSize'], len(near)))


# ------------------------------------------------------------- геометрия -----
SEG = spec['segments']


def ring_points(y, r, zc, seg=SEG):
    """Кольцо в плоскости XZ вокруг точки (0, y, zc)."""
    return [Vector((math.sin(2 * math.pi * k / seg) * r, y,
                    zc + math.cos(2 * math.pi * k / seg) * r))
            for k in range(seg)]


def tube(rings, cap_back, tip):
    """Труба по списку колец: вершины, четырёхугольники, крышки."""
    verts, faces = [], []
    base = 0
    if cap_back:
        y, r, zc = rings[0]
        verts.append(Vector((0.0, y - r * 0.6, zc)))
        base = 1
    ringstart = []
    for (y, r, zc) in rings:
        ringstart.append(len(verts))
        verts.extend(ring_points(y, r, zc))
    if cap_back:
        s = ringstart[0]
        for k in range(SEG):
            faces.append((0, s + (k + 1) % SEG, s + k))
    for a, b in zip(ringstart, ringstart[1:]):
        for k in range(SEG):
            k2 = (k + 1) % SEG
            faces.append((a + k, a + k2, b + k2, b + k))
    if tip is not None:
        ty, tz = tip
        ti = len(verts)
        verts.append(Vector((0.0, ty, tz)))
        s = ringstart[-1]
        for k in range(SEG):
            faces.append((s + k, s + (k + 1) % SEG, ti))
    return verts, faces, ringstart


def ellipsoid(center, radii, rings, seg):
    cx, cy, cz = center
    rx, ry, rz = radii
    verts, faces = [], []
    verts.append(Vector((cx, cy + ry, cz)))
    for i in range(1, rings):
        phi = math.pi * i / rings
        for k in range(seg):
            th = 2 * math.pi * k / seg
            verts.append(Vector((cx + rx * math.sin(phi) * math.sin(th),
                                 cy + ry * math.cos(phi),
                                 cz + rz * math.sin(phi) * math.cos(th))))
    verts.append(Vector((cx, cy - ry, cz)))
    top, bot = 0, len(verts) - 1
    for k in range(seg):
        faces.append((top, 1 + (k + 1) % seg, 1 + k))
    for i in range(rings - 2):
        a = 1 + i * seg
        b = a + seg
        for k in range(seg):
            k2 = (k + 1) % seg
            faces.append((a + k, a + k2, b + k2, b + k))
    last = 1 + (rings - 2) * seg
    for k in range(seg):
        faces.append((bot, last + k, last + (k + 1) % seg))
    return verts, faces


sheath = [tuple(r) for r in spec['sheath']['rings']]
shaft = [tuple(r) for r in spec['shaft']['rings']]
ext_rings = sheath + shaft
verts, faces, ringstart = tube(ext_rings, True, spec['shaft']['tip'])
n_tube = len(verts)
n_sheath = len(sheath)

# положение в покое: кольца ствола сжимаются в короткий отрезок за устьем
ret = spec['retracted']
ry0, ry1 = ret['yRange']
ext_only = shaft
y_lo = ext_only[0][0]
y_hi = spec['shaft']['tip'][0]
retracted = list(sheath)
for (y, r, zc) in ext_only:
    t = (y - y_lo) / (y_hi - y_lo)
    retracted.append((ry0 + (ry1 - ry0) * t,
                      min(r * ret['radiusScale'], ret['radiusCap']),
                      ret['zCenter']))
ret_tip = (ry1 + 0.35, ret['zCenter'])

# Мошонка садится по ЛУЧУ, а не по числу из рецепта. Прошлый раз координаты
# были взяты по «передней точке тела в слое высоты», и этот замер врёт: вершина,
# сместившись по высоте, переезжает в соседний слой и подменяет собой переднюю.
# Шары повисли в воздухе с просветом в ладонь. Теперь из каждой точки пускается
# луч назад и ищется настоящая поверхность паха, а шар ставится так, чтобы
# задняя его половина ушла в тело на `bury`, и шва не было.
bspec = spec['balls']
brx, bry, brz = bspec['radii']
bury = float(bspec.get('bury', 2.0))
ball_spans = []
for sgn in (-1, 1):
    sx = sgn * bspec['center'][0]
    cz = bspec['center'][2]
    hit, loc, _n, _i = body.ray_cast(Vector((sx, 80.0, cz)), Vector((0, -1, 0)),
                                     distance=200)
    if hit:
        cy = loc.y + (bry - bury)
        print("GEN|мошонка x=%+.1f: поверхность на Y %.2f, центр Y %.2f"
              % (sx, loc.y, cy))
    else:
        cy = bspec['center'][1]
        print("GEN|мошонка x=%+.1f: поверхность не найдена, беру Y %.2f из рецепта"
              % (sx, cy))
    bv, bf = ellipsoid((sx, cy, cz), bspec['radii'],
                       bspec['rings'], bspec['segments'])
    off = len(verts)
    ball_spans.append((off, off + len(bv), Vector((sx, cy, cz))))
    verts.extend(bv)
    faces.extend(tuple(k + off for k in f) for f in bf)

mesh = bpy.data.meshes.new(spec['shape'])
mesh.from_pydata([tuple(v) for v in verts], [], faces)
mesh.validate()
gen = bpy.data.objects.new(spec['shape'], mesh)
bpy.context.collection.objects.link(gen)
print("GEN|построено: %d вершин, %d граней" % (len(mesh.vertices), len(mesh.polygons)))

# развёртка: труба разворачивается по кольцам, шары -- по сфере
mesh.uv_layers.new(name="UVMap")
uvd = mesh.uv_layers.active.data
ymin = min(v.y for v in verts)
ymax = max(v.y for v in verts)
for poly in mesh.polygons:
    for li in poly.loop_indices:
        v = mesh.vertices[mesh.loops[li].vertex_index].co
        ang = math.atan2(v.x, v.z - 70.0) / (2 * math.pi) + 0.5
        t = (v.y - ymin) / max(ymax - ymin, 1e-6)
        uvd[li].uv = (u0 - half + ang * uvspec['patchSize'],
                      v0 - half + t * uvspec['patchSize'])

# материал тела: та же текстура, тот же шейдер, никаких новых файлов
mesh.materials.append(body.data.materials[0])

# ------------------------------------------------------------- развеска ------
w = spec['weights']
chain = [(n, rest[n][0].translation.y) for n in w['chain'] if n in rest]
chain.sort(key=lambda t: t[1])
for n in [w['root']] + [c[0] for c in chain] + list(w['knot']) + list(w['ballsBones']):
    if n not in gen.vertex_groups:
        gen.vertex_groups.new(name=n)

ky0, ky1 = w['knotYRange']
for i, v in enumerate(mesh.vertices):
    if i < n_tube and w.get('tubeSingleBone'):
        # Вся труба на одной кости. Раньше задняя половина висела на тазе,
        # а передняя на цепочке WWD, и на стыке поверхность рвалась: в игре
        # было видно два обрубка с открытыми торцами.
        gen.vertex_groups[w['root']].add([i], 1.0, 'REPLACE')
    elif i < n_tube:
        y = verts[i].y
        if y <= sheath[-1][0]:
            gen.vertex_groups[w['root']].add([i], 1.0, 'REPLACE')
            continue
        lo = hi = None
        for n, by in chain:
            if by <= y:
                lo = (n, by)
            if by >= y and hi is None:
                hi = (n, by)
        if lo is None:
            lo = chain[0]
        if hi is None:
            hi = chain[-1]
        if lo[0] == hi[0]:
            gen.vertex_groups[lo[0]].add([i], 1.0, 'REPLACE')
        else:
            f = (y - lo[1]) / max(hi[1] - lo[1], 1e-6)
            gen.vertex_groups[lo[0]].add([i], 1.0 - f, 'REPLACE')
            gen.vertex_groups[hi[0]].add([i], f, 'REPLACE')
        if ky0 <= y <= ky1:
            kb = w['knot'][0] if verts[i].x < 0 else w['knot'][1]
            if kb in gen.vertex_groups:
                gen.vertex_groups[kb].add([i], w['knotWeight'], 'REPLACE')
    else:
        # Костей мошонки может быть две (своя на каждый шар) или одна на обе:
        # когда она одна, стороны не различаются - вся мошонка висит на теле.
        bones = w['ballsBones']
        bb = bones[0] if len(bones) < 2 or verts[i].x < 0 else bones[1]
        if bb == w['root'] or bb not in gen.vertex_groups:
            # Мошонка на той же кости, что и труба: остаток отдавать некому,
            # и второе присвоение той же группе просто затёрло бы вес нулём.
            gen.vertex_groups[w['root']].add([i], 1.0, 'REPLACE')
        else:
            gen.vertex_groups[bb].add([i], w['ballsWeight'], 'REPLACE')
            gen.vertex_groups[w['root']].add([i], 1.0 - w['ballsWeight'], 'REPLACE')

gen.parent = arm
gen.modifiers.new(name="Armature", type='ARMATURE').object = arm

# ---------------------------------------------------- покой -- это база ------
ret_verts, _rf, ret_ringstart = tube(retracted, True, ret_tip)
extended = [Vector(v) for v in verts]
for i in range(n_tube):
    mesh.vertices[i].co = ret_verts[i]
# Мошонка — такая же часть анатомии, и в покое её быть видно не должно. Она
# уводится за поверхность паха и уменьшается; обратно её выводит тот же
# ползунком втягивания, что и ствол.
pull = float(ret.get('ballsPullback', 0.0))
bscale = float(ret.get('ballsScale', 1.0))
for a, bnd, c in ball_spans:
    for i in range(a, bnd):
        e = extended[i]
        mesh.vertices[i].co = c + (e - c) * bscale - Vector((0.0, pull, 0.0))
print("GEN|состояние покоя: ствол сжат в Y %.1f..%.1f" % (ry0, ry1))

# ---------------------------------------------------------------- морфы ------
gen.shape_key_add(name='Basis', from_mix=False)
ms = spec['morphs']

# Имена паховых ползунков берутся из рецепта по их отличительным полям, а не
# зашиты здесь: переименовать ползунок в рецепте - право рецепта, и сборка от
# этого падать не должна.
def _role(field):
    for name, spec in ms.items():
        if isinstance(spec, dict) and field in spec:
            return name
    raise KeyError("в рецепте нет пахового ползунка с полем %r" % field)


M_STATE = _role('from')
M_LONG = _role('lengthScale')
M_KNOT = _role('knotScale')
M_BALLS = _role('spread')



def add_key(name, coords):
    sk = gen.shape_key_add(name='>' + name, from_mix=False)
    moved = 0
    for i, co in coords.items():
        if (Vector(co) - mesh.vertices[i].co).length > 1e-5:
            moved += 1
        sk.data[i].co = co
    print("GEN|ползунок %-18s сдвинуто %4d из %4d" % (name, moved, len(mesh.vertices)))


# State: покой -> вытянутое
add_key(M_STATE,
        {i: extended[i] for i in
         list(range(n_tube)) + [k for a, bnd, _c in ball_spans for k in range(a, bnd)]})

# Size: прибавка ПОВЕРХ вытянутого, поэтому дельта считается от вытянутого
sz = ms[M_LONG]
y_base = sheath[-1][0]
big = {}
for i in range(n_tube):
    e = extended[i]
    if e.y <= y_base:
        big[i] = mesh.vertices[i].co
        continue
    yy = y_base + (e.y - y_base) * sz['lengthScale']
    big[i] = Vector((e.x * sz['girthScale'], yy,
                     69.2 + (e.z - 69.2) * sz['girthScale']))
    big[i] = mesh.vertices[i].co + (big[i] - e)
add_key(M_LONG, big)

# Knot: только узел, тоже поверх вытянутого
kn = ms[M_KNOT]
kyy0, kyy1 = kn['yRange']
knot = {}
for i in range(n_tube):
    e = extended[i]
    if not (kyy0 <= e.y <= kyy1):
        knot[i] = mesh.vertices[i].co
        continue
    s = kn['knotScale']
    d = Vector((e.x * (s - 1.0), 0.0, (e.z - 68.7) * (s - 1.0)))
    knot[i] = mesh.vertices[i].co + d
add_key(M_KNOT, knot)

# Balls: мошонка видна всегда, поэтому её дельта считается от базы
bs = ms[M_BALLS]
spread = float(bs.get('spread', 1.0))
balls = {}
for a, bnd, c in ball_spans:
    # центр шара разъезжается вбок на тот же множитель, что и его радиус:
    # без этого при 1.4 шары перекрывали осевую линию и сливались в овал
    c2 = Vector((c.x * spread, c.y, c.z))
    for i in range(a, bnd):
        e = extended[i]
        big = c2 + (e - c) * bs['scale']
        balls[i] = mesh.vertices[i].co + (big - e)
add_key(M_BALLS, balls)

# ------------------------------------------------- морфы самого тела ---------
if BODYMORPHS:
    meshes = {o.name: o for o in bpy.data.objects if o.type == 'MESH'}
    _spec = [_it for _it in json.load(open(BODYMORPHS, encoding='utf-8'))
             if _it.get('sex', 'any') in ('any', 'male')]
    # Ползунки «к форме другого тела» требуют донора и считаются отдельно.
    for _it in _spec:
        if _it.get('mode') == 'toShape':
            morphlib.apply_to_shape(_it, {o.name: o for o in bpy.data.objects
                                          if o.type == 'MESH'}, donor_co, print)
    morphlib.apply_recipe([_it for _it in _spec if _it.get('mode') != 'toShape'],
                          meshes, arm)

# ------------------------------------------------------- проверка -----------
# Деталь должна быть СПРЯТАНА в покое и ВИДНА в вытянутом состоянии. Глазом это
# по отрисовке не определить: бёдра и живот заслоняют пах почти с любого угла.
# Поэтому вершины считаются лучами: из каждой в пять сторон, нечётное число
# пересечений с телом -- вершина внутри.
_DIRS = [Vector(d).normalized() for d in
         ((0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, -1))]

# Луч пускается по СНИМКУ кожи, а не по живому объекту. Object.ray_cast бьёт
# по вычисленной геометрии, и как только на теле появляются ключи-формы,
# ответ начинает от них зависеть: с одним набором морфов проверка давала
# 410 вершин внутри, с другим -- 59, при неизменной геометрии самой детали.
# Снимок берётся один раз, до того как на тело легли ползунки.
from mathutils.bvhtree import BVHTree
_snap_v = [body.matrix_world @ v.co for v in body.data.vertices]
_snap_f = [tuple(p.vertices) for p in body.data.polygons]
_skin = BVHTree.FromPolygons(_snap_v, _snap_f)


def _inside(p):
    votes = 0
    for d in _DIRS:
        n, o = 0, p + d * 0.01
        while True:
            loc, _nr, _i, _dist = _skin.ray_cast(o, d, 500)
            if loc is None:
                break
            n += 1
            o = loc + d * 0.01
        votes += (n % 2)
    return votes >= 3


def report_hidden(label, active):
    for kb in gen.data.shape_keys.key_blocks:
        if kb.name.startswith('>'):
            kb.value = active.get(kb.name[1:], 0.0)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = gen.evaluated_get(dg)
    me = ev.to_mesh()
    tube_in = sum(1 for i, v in enumerate(me.vertices) if i < n_tube and _inside(v.co.copy()))
    ball_in = sum(1 for i, v in enumerate(me.vertices) if i >= n_tube and _inside(v.co.copy()))
    print("GEN|скрытость %-10s труба внутри %3d/%3d, мошонка внутри %3d/%3d"
          % (label, tube_in, n_tube, ball_in, len(me.vertices) - n_tube))
    ev.to_mesh_clear()
    for kb in gen.data.shape_keys.key_blocks:
        if kb.name.startswith('>'):
            kb.value = 0.0


report_hidden('покой', {})
report_hidden('вытянуто', {M_STATE: 1.0})

# ---------------------------------------------------------------- вывод ------
morphlib.export_clean(OUT)
print("GEN|экспорт ok ->", OUT)

if not PREVIEW:
    sys.exit(0)

# ---------------------------------------------------------------- показ ------
import os
import mathutils
PREVIEW = os.path.abspath(PREVIEW)
os.makedirs(PREVIEW, exist_ok=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
sh = scene.display.shading
sh.light = 'STUDIO'
sh.color_type = 'SINGLE'
sh.single_color = (0.62, 0.60, 0.58)
sh.show_shadows = True
sh.show_cavity = True
sh.cavity_type = 'BOTH'
scene.render.resolution_x = 900
scene.render.resolution_y = 900
world = bpy.data.worlds.new("W")
scene.world = world
world.use_nodes = True
for n in world.node_tree.nodes:
    if n.type == 'BACKGROUND':
        n.inputs[0].default_value = (0.05, 0.05, 0.06, 1)
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


def place(center, rad, deg, pad=1.2, slab=None, elev=0.0):
    # Ломоть вместо всей глубины: у вервольфа кисти висят как раз на уровне паха
    # и при взгляде сбоку заслоняют его целиком. Ближняя и дальняя плоскости
    # отсечения оставляют только слой вокруг осевой линии.
    cam_data.ortho_scale = rad * 2 * pad
    ang = math.radians(deg)
    dist = rad * 14
    if slab is None:
        cam_data.clip_start, cam_data.clip_end = 0.1, dist * 3
    else:
        cam_data.clip_start, cam_data.clip_end = dist - slab, dist + slab
    el = math.radians(elev)
    cam.location = center + mathutils.Vector(
        (math.sin(ang) * dist * math.cos(el), -math.cos(ang) * dist * math.cos(el),
         math.sin(el) * dist))
    cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
    for lo, ld, pos, energy in lights:
        ld.energy = energy * rad * rad * 0.6
        ld.size = rad
        lo.location = center + pos * rad * 3.0
        lo.rotation_euler = (center - lo.location).to_track_quat('-Z', 'Y').to_euler()


def setkeys(active):
    for o in bpy.data.objects:
        if o.type != 'MESH' or not o.data.shape_keys:
            continue
        for kb in o.data.shape_keys.key_blocks:
            if kb.name.startswith('>'):
                kb.value = active.get(kb.name[1:], 0.0)


groin = mathutils.Vector((0.0, 12.0, 66.0))
states = [
    ("0-pokoy", {}),
    ("1-state", {M_STATE: 1.0}),
    ("2-size", {M_STATE: 1.0, M_LONG: 1.0}),
    ("3-knot", {M_STATE: 1.0, M_KNOT: 1.0}),
    ("4-balls", {M_STATE: 1.0, M_BALLS: 1.0}),
]
others = [o for o in bpy.data.objects if o.type == 'MESH' and o is not gen]
for label, active in states:
    setkeys(active)
    # сама деталь, без тела: видно построенную поверхность целиком
    for o in others:
        o.hide_render = True
    for dname, ddeg, delev in (("sboku", 90.0, 0.0), ("kosoy", 130.0, -25.0)):
        place(groin, 24.0, ddeg, elev=delev)
        scene.render.filepath = os.path.join(PREVIEW, "detal-%s-%s.png" % (dname, label))
        bpy.ops.render.render(write_still=True)
        print("SHOT|%s" % scene.render.filepath)
    # деталь на теле, ломтем вокруг осевой линии
    for o in others:
        o.hide_render = False
    for vname, cen, rr, deg, elev, slab in (
            ("bok", mathutils.Vector((0.0, 5.0, 62.0)), 40.0, 90.0, 0.0, None),
            ("snizu", mathutils.Vector((0.0, 10.0, 62.0)), 26.0, 180.0, -80.0, None),
            ("razrez", groin, 30.0, 90.0, 0.0, 3.5)):
        place(cen, rr, deg, slab=slab, elev=elev)
        scene.render.filepath = os.path.join(PREVIEW, "%s-%s.png" % (vname, label))
        bpy.ops.render.render(write_still=True)
        print("SHOT|%s" % scene.render.filepath)
