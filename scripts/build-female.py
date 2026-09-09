"""Собирает женское тело вервольфа: пара по весу, шерсть на предплечьях и морфы.

Три вещи, которых у женского тела Elegant нет и которые здесь появляются.

**Пара по весу.** `femalebodywerewolf_0.nif` и `_1.nif` у Elegant совпадают
побайтово — это дубликат, а не пара, и вес самкам не даёт ничего. Половина `_0`
строится здесь убавлением обхвата: у людей прибавка от веса даёт 1–7 %, у зверя
берём вчетверо больше.

**Шерсть на предплечьях.** У самки нет формы `fur_arms` — единственное отличие
в наборе форм между полами. Она переносится с мужского тела и подгоняется полем
сдвига кожи, иначе провалилась бы в руку.

**Ползунок «к мужской груди».** Тела полов топологически одинаковы: совпадает
и число вершин, и их порядок. Поэтому целевые координаты для `CLAWChestFlat` —
это буквально вершины мужского тела с теми же номерами. Донор читается первым
проходом; двух тел в сцене держать нельзя, PyNifly при повторном импорте вливает
данные в существующие объекты вместо того, чтобы завести вторые.

  blender.exe --background --python build-female.py -- \\
      <мужское.nif> <женское.nif> <выход.nif> <full-body.json> <female.json> [--slim 0.90]
"""
import sys, os, json, bpy, addon_utils
from mathutils import Vector, kdtree

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
SLIM = None
if '--slim' in argv:
    k = argv.index('--slim')
    SLIM = float(argv[k + 1])
    argv = argv[:k] + argv[k + 2:]
MALE, FEMALE, OUT, FULL, FEM = argv[0], argv[1], argv[2], argv[3], argv[4]


def wipe():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


# ---- проход первый: донор ----------------------------------------------------
wipe()
bpy.ops.import_scene.pynifly(filepath=MALE)
male_co = {o.name: [v.co.copy() for v in o.data.vertices]
           for o in bpy.data.objects if o.type == 'MESH'}
src_arms = bpy.data.objects.get('fur_arms')
arms_mesh = src_arms.data if src_arms else None
arms_co, arms_weights = [], {}
if src_arms:
    arms_mesh.name = 'fur_arms'
    arms_co = [v.co.copy() for v in src_arms.data.vertices]
    gnames = {g.index: g.name for g in src_arms.vertex_groups}
    for v in src_arms.data.vertices:
        for g in v.groups:
            arms_weights.setdefault(gnames[g.group], []).append((v.index, g.weight))
print("FEM|донор прочитан: форм %d, fur_arms %d вершин"
      % (len(male_co), len(arms_co)))

# ---- проход второй: женское тело ---------------------------------------------
wipe()
bpy.ops.import_scene.pynifly(filepath=FEMALE)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
body = bpy.data.objects['body']
if len(male_co['body']) != len(body.data.vertices):
    print("FEM|тела не родственные: %d вершин против %d"
          % (len(male_co['body']), len(body.data.vertices)))
    raise SystemExit(1)

# поле сдвига кожи: куда уехала каждая вершина при лепке самки из самца
skin_delta = [t.co - s for s, t in zip(male_co['body'], body.data.vertices)]
tree = kdtree.KDTree(len(male_co['body']))
for i, co in enumerate(male_co['body']):
    tree.insert(co, i)
tree.balance()

# ---- шерсть на предплечьях ---------------------------------------------------
if arms_mesh is not None and bpy.data.objects.get('fur_arms') is None:
    obj = bpy.data.objects.new('fur_arms', arms_mesh)
    bpy.context.collection.objects.link(obj)
    mx = 0.0
    for i, v in enumerate(obj.data.vertices):
        tot, acc = 0.0, Vector((0.0, 0.0, 0.0))
        for _c, j, dist in tree.find_n(arms_co[i], 8):
            w = 1.0 / max(dist, 1e-4)
            acc += skin_delta[j] * w
            tot += w
        d = acc / tot if tot else Vector((0, 0, 0))
        v.co = arms_co[i] + d
        mx = max(mx, d.length)
    for name, pairs in arms_weights.items():
        vg = obj.vertex_groups.new(name=name)
        for idx, w in pairs:
            vg.add([idx], w, 'REPLACE')
    obj.parent = arm
    obj.modifiers.new(name="Armature", type='ARMATURE').object = arm
    print("FEM|fur_arms перенесена: %d вершин, наибольшая подгонка %.3f"
          % (len(obj.data.vertices), mx))

meshes = {o.name: o for o in bpy.data.objects if o.type == 'MESH'}

# ---- половина по весу --------------------------------------------------------
# Убавление обхвата делается ГЕОМЕТРИЕЙ, а не морфом: пара _0/_1 - это встроенное
# смешивание движка, оно про два разных меша, а не про именованный сдвиг.
if SLIM is not None:
    slim = {"mode": "region", "axis": [0.0, -2.0], "zRange": [56.0, 116.0],
            "zFade": 12.0, "amount": SLIM,
            "includeContains": ["NPC Pelvis", "NPC Spine", "NPC Neck"]}
    d = morphlib.deltas_for(body, slim, arm)
    for i, v in enumerate(body.data.vertices):
        if i in d:
            v.co = v.co + d[i]
    for name in ('fur_belly', 'fur_chest', 'fur_back', 'fur_shoulders', 'ChestBlend'):
        o = meshes.get(name)
        if o is None:
            continue
        got = morphlib.carry_field(body, d, o)
        for i, v in enumerate(o.data.vertices):
            if i in got:
                v.co = v.co + got[i]
    print("FEM|половина по весу: обхват %.2f, сдвинуто %d вершин кожи" % (SLIM, len(d)))

# ---- ползунки ----------------------------------------------------------------
# Общий рецепт держит ползунки обоих полов: у ползунка «к форме другого пола»
# знак у самца и самки разный, поэтому запись помечена полом и чужая пропускается.
full = [it for it in json.load(open(FULL, encoding='utf-8'))
        if it.get('sex', 'any') in ('any', 'female')]
for it in full:
    if it.get('mode') == 'toShape':
        morphlib.apply_to_shape(it, meshes, {'body': male_co.get('body')}, print)
morphlib.apply_recipe([it for it in full if it.get('mode') != 'toShape'], meshes, arm)

fem = json.load(open(FEM, encoding='utf-8'))
plain = [it for it in fem if it.get('mode') != 'toShape']
morphlib.apply_recipe(plain, meshes, arm)

# Ползунки «к форме другого тела» считает morphlib: то же самое нужно и сборщику
# самца, и второй копии этой логики быть не должно.
for it in fem:
    if it.get('mode') == 'toShape':
        morphlib.apply_to_shape(it, meshes, {'body': male_co.get('body')}, print)

morphlib.export_clean(OUT)
print("FEM|экспорт ok ->", OUT)
