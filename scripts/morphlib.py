"""Общая часть сборщиков: как из описания ползунка получается поле сдвигов.

Живёт отдельно, потому что описание ползунка нужно двум сборщикам сразу —
и тому, что правит уже готовые формы тела, и тому, что вживляет новую
геометрию. Пока логика была в двух файлах, каждый писал свой файл морфов
и затирал чужой: в моде оставался последний собранный.

Три способа сдвига, каждый под свою задачу:

  grow    -- растяжение от основания кости. Длина: уши, хвост, морда.
             У каждой части своя опора, иначе парные кости получают общий
             центр на осевой линии тела и разъезжаются вбок.
  barrel  -- наружу от вертикальной оси через кость. Обхват, маска по весам.
  region  -- то же наружу от оси, но область задана поясом по высоте и суммой
             весов ПЕРЕЧИСЛЕННЫХ СВОИХ костей. Для живота и груди, где нужной
             одной кости у зверя просто нет.

Раздувание в `region` задаётся множителем обхвата, а не сдвигом в единицах:
одинаковый сдвиг переставляет вершины по радиусу местами и даёт на силуэте
жёсткий бортик. Потолок сдвига держит гриву, висящую вчетверо дальше от оси,
чем кожа; `min` двух растущих функций сама растёт, поэтому порядок цел.
"""
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
    amount = float(part['amount'])
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

    gi = [obj.vertex_groups[b].index for b in part['bones']
          if b in obj.vertex_groups]
    if not gi:
        return out
    pivot = bone_head(arm, part.get('pivot') or part['bones'][0])
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
            r = Vector((co.x - pivot.x, co.y - pivot.y, 0.0))
            if r.length < 1e-4:
                continue
            out[i] = r.normalized() * (amount * w)
    return out


def apply_recipe(spec, objects, arm, log=print):
    """Кладёт ползунки из рецепта на формы тела как ключи '>Имя'.

    PyNifly уводит форму-ключ с именем '>Имя' в файл морфов. Ползунок кладётся
    сразу на ВСЕ формы, которых касается: тело зверя собрано слоями, и сдвиг
    одной кожи выводит её сквозь оболочки шерсти.
    """
    for item in spec:
        morph = item['morph']
        for shape in item['shapes']:
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
            if obj.data.shape_keys is None:
                obj.shape_key_add(name='Basis', from_mix=False)
            sk = obj.shape_key_add(name='>' + morph, from_mix=False)
            inv = obj.matrix_world.inverted()
            mx = 0.0
            for i, d in delta.items():
                sk.data[i].co = inv @ ((obj.matrix_world @ obj.data.vertices[i].co) + d)
                mx = max(mx, d.length)
            log("MORPH|%-16s %-14s сдвинуто %6d из %6d, макс %6.2f"
                % (morph, shape, len(delta), len(obj.data.vertices), mx))
