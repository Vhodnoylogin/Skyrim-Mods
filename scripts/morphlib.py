"""Общая часть сборщиков: как из описания ползунка получается поле сдвигов.

Живёт отдельно, потому что описание ползунка нужно двум сборщикам сразу —
и тому, что правит уже готовые формы тела, и тому, что вживляет новую
геометрию. Пока логика была в двух файлах, каждый писал свой файл морфов
и затирал чужой: в моде оставался последний собранный.

Три способа сдвига, каждый под свою задачу:

  rotate  -- поворот области вокруг оси, проходящей через кость. Уши прижать,
             стопу поставить на пальцы. Морф ведёт вершину по ХОРДЕ, а не по
             дуге, поэтому на середине ползунка деталь чуть подтягивается
             к центру: 0.9 % при 15 градусах, 3.4 % при 30, 13 % при 60.
             На краях геометрия точна всегда. Держать угол в пределах 30.
  grow    -- растяжение от основания кости. Длина: уши, хвост, морда.
             У каждой части своя опора, иначе парные кости получают общий
             центр на осевой линии тела и разъезжаются вбок.
  barrel  -- наружу от оси через кость. Обхват, маска по весам. Ось по умолчанию
             вертикальная; для руки, идущей вбок, и для хвоста, идущего назад,
             её надо задать своей -- иначе конечность толстеет только в одной
             плоскости.
  bumps   -- местные выпуклости или впадины в заданных точках: вершина едет
             по своей нормали, сила спадает от центра к краю. Ряд сосков,
             ниша вульвы -- всё, что не описывается ни костью, ни поясом.
  scaleAxis -- растяжение по каждой оси отдельно от кости-опоры. Длина морды,
             ширина челюсти, длина хвоста: там, где нужен не обхват, а размер
             вдоль своего направления.
  region  -- то же наружу от оси, но область задана поясом по высоте и суммой
             весов ПЕРЕЧИСЛЕННЫХ СВОИХ костей. Для живота и груди, где нужной
             одной кости у зверя просто нет.

Раздувание в `region` задаётся множителем обхвата, а не сдвигом в единицах:
одинаковый сдвиг переставляет вершины по радиусу местами и даёт на силуэте
жёсткий бортик. Потолок сдвига держит гриву, висящую вчетверо дальше от оси,
чем кожа; `min` двух растущих функций сама растёт, поэтому порядок цел.
"""
import math
from mathutils import Vector


def smooth(t):
    """Плавная ступенька 0..1: без неё край области видно швом."""
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return t * t * (3.0 - 2.0 * t)


def bone_head(arm, name):
    if arm is None or name not in arm.data.bones:
        return None
    return arm.matrix_world @ arm.data.bones[name].head_local


def _weight_of(v, gi):
    return min(1.0, sum(g.weight for g in v.groups if g.group in gi))


def deltas_for(obj, part, arm, log=None):
    """Поле сдвигов одной части ползунка: {индекс вершины: смещение}."""
    out = {}
    amount = float(part.get('amount', 1.0))   # scaleAxis величину берёт из scale
    mode = part.get('mode', 'barrel')

    if mode == 'region':
        ax = Vector(part.get('axis', [0.0, 0.0]))
        z0, z1 = part['zRange']
        fade = float(part.get('zFade', 8.0))
        cap = float(part.get('maxShift', 1e9))
        # Область задаётся списком СВОИХ костей, а не списком чужих:
        # отрицательный список приходится держать полным, и он однажды
        # пропустил кости пальцев -- а кисти у зверя висят на уровне живота.
        good = [g.index for g in obj.vertex_groups
                if any(k.lower() in g.name.lower()
                       for k in part.get('includeContains', []))]
        for i, v in enumerate(obj.data.vertices):
            co = obj.matrix_world @ v.co
            wz = smooth((co.z - z0) / fade) * smooth((z1 - co.z) / fade)
            if wz <= 0.01:
                continue
            wb = min(1.0, sum(g.weight for g in v.groups if g.group in good))
            w = wz * wb
            if w <= 0.01:
                continue
            r = Vector((co.x - ax.x, co.y - ax.y, 0.0))
            if r.length < 1e-4:
                continue
            shift = min(r.length * (amount - 1.0), cap)
            out[i] = r.normalized() * (shift * w)
        return out

    if mode == 'bumps':
        # Работает без костей: область задана точками, а не развеской.
        centers = [Vector(c) for c in part.get('centers', [])]
        rad = float(part.get('radius', 5.0))
        obj.data.calc_normals_split() if hasattr(obj.data, 'calc_normals_split') else None
        for i, v in enumerate(obj.data.vertices):
            co = obj.matrix_world @ v.co
            best = 0.0
            for c in centers:
                t = 1.0 - (co - c).length / rad
                if t > best:
                    best = t
            if best <= 0.0:
                continue
            out[i] = v.normal.normalized() * (amount * smooth(best))
        return out

    gi = [obj.vertex_groups[b].index for b in part.get('bones', [])
          if b in obj.vertex_groups]
    if not gi:
        return out
    if mode == 'scaleAxis':
        pivot = bone_head(arm, part.get('pivot') or (part.get('bones') or [''])[0])
        if pivot is None:
            return out
        sc = Vector(part.get('scale', [1.0, 1.0, 1.0]))
        for i, v in enumerate(obj.data.vertices):
            w = _weight_of(v, gi)
            if w <= 0.01:
                continue
            co = obj.matrix_world @ v.co
            d = co - pivot
            out[i] = Vector((d.x * (sc.x - 1.0), d.y * (sc.y - 1.0),
                             d.z * (sc.z - 1.0))) * w
        return out

    if mode == 'rotate':
        from mathutils import Matrix
        pivot = bone_head(arm, part.get('pivot') or (part.get('bones') or [''])[0])
        if pivot is None:
            return out
        axis = Vector(part.get('axis', [1.0, 0.0, 0.0])).normalized()
        ang = math.radians(amount)
        for i, v in enumerate(obj.data.vertices):
            w = _weight_of(v, gi)
            if w <= 0.01:
                continue
            co = obj.matrix_world @ v.co
            m = Matrix.Rotation(ang * w, 4, axis)
            out[i] = (m @ (co - pivot)) + pivot - co
        return out
    pivot = bone_head(arm, part.get('pivot') or (part.get('bones') or [''])[0])
    if pivot is None:
        if log:
            log("нет кости-опоры для %s" % obj.name)
        return out
    for i, v in enumerate(obj.data.vertices):
        w = _weight_of(v, gi)
        if w <= 0.01:
            continue
        co = obj.matrix_world @ v.co
        if mode == 'grow':
            out[i] = (co - pivot) * ((amount - 1.0) * w)
        else:
            # обхват вокруг заданной оси: составляющая вдоль оси отбрасывается,
            # остаток и есть направление наружу
            ax = Vector(part.get('barrelAxis', [0.0, 0.0, 1.0])).normalized()
            d = co - pivot
            r = d - ax * d.dot(ax)
            if r.length < 1e-4:
                continue
            out[i] = r.normalized() * (amount * w)
    return out


def _put_key(obj, morph, delta, log):
    if obj.data.shape_keys is None:
        obj.shape_key_add(name='Basis', from_mix=False)
    sk = obj.shape_key_add(name='>' + morph, from_mix=False)
    inv = obj.matrix_world.inverted()
    mx = 0.0
    for i, d in delta.items():
        sk.data[i].co = inv @ ((obj.matrix_world @ obj.data.vertices[i].co) + d)
        mx = max(mx, d.length)
    log("MORPH|%-16s %-14s сдвинуто %6d из %6d, макс %6.2f"
        % (morph, obj.name, len(delta), len(obj.data.vertices), mx))


def carry_field(src_obj, src_delta, dst_obj, k=6):
    """Переносит поле сдвигов с кожи на оболочку, лежащую поверх неё.

    Тело зверя собрано слоями: кожа, шесть оболочек шерсти и сшивки между ними.
    Считать сдвиг на каждом слое отдельно нельзя. Раздувание задаётся
    множителем обхвата, а слои стоят на разном удалении от оси — значит
    оболочка, лежавшая в двух единицах над кожей, после умножения окажется
    в четырёх. Слои расходятся, между ними появляется просвет, и сшивка
    повисает ни на чём. Именно это и видел пользователь: «живот соединён
    с грудью, однако это не грудь, а шерсть на груди; сама грудь спрятана
    ниже и ни с чем не связана».

    Поэтому сдвиг считается ОДИН РАЗ на коже, а оболочки его наследуют: каждая
    вершина берёт усреднённый сдвиг ближайших вершин кожи. Зазор между слоями
    сохраняется, и разойтись им нечем. Тот же приём, что в
    toolslender-graft-shape.py при переносе формы между телами.
    """
    from mathutils import kdtree
    src = src_obj.data.vertices
    tree = kdtree.KDTree(len(src))
    for i, v in enumerate(src):
        tree.insert(src_obj.matrix_world @ v.co, i)
    tree.balance()
    out = {}
    for j, v in enumerate(dst_obj.data.vertices):
        co = dst_obj.matrix_world @ v.co
        tot, acc = 0.0, Vector((0.0, 0.0, 0.0))
        for _c, i, dist in tree.find_n(co, k):
            d = src_delta.get(i)
            if d is None:
                continue
            w = 1.0 / max(dist, 1e-4)
            acc += d * w
            tot += w
        if tot > 0.0 and (acc / tot).length > 0.001:
            out[j] = acc / tot
    return out


def apply_recipe(spec, objects, arm, log=print):
    """Кладёт ползунки из рецепта на формы тела как ключи '>Имя'.

    PyNifly уводит форму-ключ с именем '>Имя' в файл морфов.

    Два способа задать, куда ползунок ложится:

      base + carry -- сдвиг считается на ОДНОЙ форме (обычно на коже `body`),
                      остальные его наследуют полем. Слои не расходятся.
                      Это способ по умолчанию для всего, что трогает туловище.
      shapes       -- сдвиг считается на каждой форме отдельно. Годится там,
                      где формы не лежат друг над другом, например уши.
    """
    for item in spec:
        if 'morph' not in item:
            continue          # запись-пояснение в рецепте, а не ползунок
        morph = item['morph']
        if item.get('base'):
            src = objects.get(item['base'])
            if src is None:
                log("MORPH|%-16s нет опорной формы %s" % (morph, item['base']))
                continue
            delta = {}
            for part in item['parts']:
                for i, d in deltas_for(src, part, arm, log).items():
                    delta[i] = delta.get(i, Vector((0, 0, 0))) + d
            if not delta:
                log("MORPH|%-16s %-14s костей нет, пропуск" % (morph, item['base']))
                continue
            _put_key(src, morph, delta, log)
            for shape in item.get('carry', []):
                dst = objects.get(shape)
                if dst is None:
                    log("MORPH|%-16s нет формы %s" % (morph, shape))
                    continue
                got = carry_field(src, delta, dst, int(item.get('carryNeighbours', 6)))
                if got:
                    _put_key(dst, morph, got, log)
                else:
                    log("MORPH|%-16s %-14s поле не дотянулось" % (morph, shape))
            continue

        for shape in item.get('shapes', []):
            obj = objects.get(shape)
            if obj is None:
                log("MORPH|%-16s нет формы %s" % (morph, shape))
                continue
            delta = {}
            for part in item['parts']:
                for i, d in deltas_for(obj, part, arm, log).items():
                    delta[i] = delta.get(i, Vector((0, 0, 0))) + d
            if not delta:
                log("MORPH|%-16s %-14s костей нет, пропуск" % (morph, shape))
                continue
            _put_key(obj, morph, delta, log)


def export_clean(out_path, log=print):
    """Выгружает сцену в NIF, выбросив мусор, который накапливает PyNifly.

    PyNifly заводит объект Blender на КАЖДЫЙ узел нифа, включая служебные:
    метку BODYTRI, флаги BSXFlags, границы BSBound, опознание скелета
    SkeletonID и корни. На выгрузке он пишет их все обратно, поэтому метки
    множатся от прогона к прогону -- в теле, собранном третьим поколением,
    их оказалось тридцать штук.

    Само по себе это ещё не смертельно, но если в сцену импортировали ЧУЖОЙ
    файл (скелет, чтобы взять из него кости), то его корень и его служебные
    узлы уедут в тело. Тело актёра с зашитым внутрь корнем скелета и его
    опознанием игра при загрузке зверя не переживает.

    Поэтому: метки BODYTRI сносятся все -- нужную запишет сам экспорт по
    ключу write_bodytri, -- а выбор объектов делается явным, а не «выделить
    всё подряд».
    """
    import bpy
    dropped = []
    for o in list(bpy.data.objects):
        if o.type == 'EMPTY' and 'BODYTRI' in o.name:
            dropped.append(o.name)
            bpy.data.objects.remove(o, do_unlink=True)
    if dropped:
        log("EXPORT|снято старых меток BODYTRI: %d" % len(dropped))
    left = {}
    for o in bpy.data.objects:
        o.select_set(True)
        left[o.type] = left.get(o.type, 0) + 1
    log("EXPORT|в выгрузку идёт: %s"
        % ", ".join("%s %d" % (t, n) for t, n in sorted(left.items())))
    bpy.ops.export_scene.pynifly(filepath=out_path, target_game='SKYRIMSE',
                                 write_tris=True, write_bodytri=True)
