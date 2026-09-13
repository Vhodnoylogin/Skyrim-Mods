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
  spike   -- острый отросток тянется вдоль своей оси от своего основания:
             коготь, клык. Каждый островок геометрии считается сам по себе,
             поэтому общая кость не разводит их веером, а основание остаётся
             на месте и деталь не отрывается от тела.
  toShape -- цель берётся у ДРУГОГО тела вершина в вершину: тела полов
             топологически одинаковы, и разница между ними - готовое поле.
             Знак ведёт к донору или, наоборот, продолжает разницу за него.
  swell   -- вздутие в одну сторону: живот вперёд, грудь вперёд. Все вершины
             едут одним направлением, сила спадает от оси роста в плоскости
             поперёк неё. Слои от этого не расходятся, а поверхность не комкается,
             как при сдвиге по нормалям.
  bumps   -- местные выпуклости или впадины в заданных точках: вершина едет
             по своей нормали, сила спадает от центра к краю. Ряд сосков,
             ниша вульвы, грудные полудиски, круглое брюхо -- всё, что не
             описывается ни костью, ни поясом. Область можно дополнительно
             ограничить костями: без этого выпуклость груди захватывает плечо.
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


ZERO = Vector((0.0, 0.0, 0.0))


def smooth(t):
    """Плавная ступенька 0..1: без неё край области видно швом."""
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return t * t * (3.0 - 2.0 * t)


def bone_head(arm, name):
    if arm is None or name not in arm.data.bones:
        return None
    return arm.matrix_world @ arm.data.bones[name].head_local


def _window(part, co):
    """Окно по координатам: 1 внутри, 0 снаружи, плавно на краях.

    Кость владеет всей своей территорией, а морфу порой нужна лишь её часть:
    челюсть должна укрупнять морду, но не затылок, хотя обе висят на одних
    и тех же костях головы. Окно и вырезает нужный кусок. Ключей нет - окна
    нет, и поведение прежнее.
    """
    factor = 1.0
    for key, value in (('xRange', co.x), ('yRange', co.y), ('zRange', co.z)):
        rng = part.get(key)
        if not rng:
            continue
        fade = float(part.get(key[0] + 'Fade', part.get('fade', 6.0)))
        factor *= smooth((value - rng[0]) / fade) * smooth((rng[1] - value) / fade)
    return factor


def _weight_of(v, gi):
    return min(1.0, sum(g.weight for g in v.groups if g.group in gi))


def _islands(obj, keep):
    """Разбивает выбранные вершины на связные куски по рёбрам меша.

    Когти лежат в одной форме, но каждый коготь - отдельный островок геометрии,
    ни одним ребром не связанный с соседями. Островки и есть отдельные когти.
    """
    parent = {i: i for i in keep}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for e in obj.data.edges:
        a, b = e.vertices[0], e.vertices[1]
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    groups = {}
    for i in keep:
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _spike(obj, part, gi, amount):
    """Отросток удлиняется вдоль СВОЕЙ оси от СВОЕГО основания.

    Основание не двигается вовсе, поэтому коготь не отрывается от пальца и
    остаётся в него утопленным при любом положении ползунка; вытягивается
    только остриё. Кость здесь нужна лишь чтобы выбрать вершины: опоры у неё
    не спрашивают, ось и основание находятся по самой геометрии когтя. Это
    важно для задних лап, где все когти висят на ОДНОЙ кости пальца и общей
    опорой их развело бы веером.

    `amount` - прибавка длины в единицах модели, а не множитель.
    """
    out = {}
    co = [obj.matrix_world @ v.co for v in obj.data.vertices]
    keep = set(i for i, v in enumerate(obj.data.vertices) if _weight_of(v, gi) > 0.01)
    if not keep:
        return out
    for island in _islands(obj, keep):
        if len(island) < 4:
            continue
        pts = [co[i] for i in island]
        centre = sum(pts, Vector((0.0, 0.0, 0.0))) / len(pts)
        p0 = max(pts, key=lambda p: (p - centre).length)
        p1 = max(pts, key=lambda p: (p - p0).length)
        axis = p1 - p0
        span = axis.length
        if span < 1e-4:
            continue
        axis = axis / span
        ts = [max(0.0, min(1.0, (p - p0).dot(axis) / span)) for p in pts]
        # Остриё - тот конец, где вершины ближе к оси: коготь сходит на конус.
        def radius(lo, hi):
            vals = [((p - p0) - axis * ((p - p0).dot(axis))).length
                    for p, t in zip(pts, ts) if lo <= t <= hi]
            return sum(vals) / len(vals) if vals else 0.0

        if radius(0.0, 0.25) < radius(0.75, 1.0):
            axis, ts = -axis, [1.0 - t for t in ts]
        for i, t in zip(island, ts):
            if t > 0.0:
                out[i] = axis * (amount * smooth(t))
    return out


def deltas_for(obj, part, arm, log=None, strict=True):
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
            # Потолок держит гриву, висящую вчетверо дальше от оси, чем кожа.
            # Но ОБРЫВ на потолке даёт плоскую площадку: всё, что за ним, сдвигается
            # на одно и то же, и туловище становится коробкой с рёбрами. Поэтому
            # насыщение мягкое: до половины потолка сдвиг почти линеен, дальше плавно
            # выходит на предел и площадки не образует.
            want = r.length * (amount - 1.0)
            shift = cap * math.tanh(want / cap) if cap < 1e8 else want
            out[i] = r.normalized() * (shift * w)
        return out

    if mode == 'swell':
        # ВЗДУТИЕ: живот, грудные полудиски. Все затронутые вершины едут в ОДНУ
        # сторону, а не каждая по своей нормали.
        #
        # Почему не по нормалям. У низкополигонального тела нормали соседних
        # вершин смотрят заметно врозь, и сдвиг по ним не раздувает поверхность,
        # а комкает её: вместо одной выпуклости получаются две-три складки
        # с оврагами между. Пользователь это и увидел на брюхе.
        #
        # Сила спада меряется в плоскости, ПЕРПЕНДИКУЛЯРНОЙ направлению роста.
        # Тогда кожа и шерсть над ней, стоящие на одной высоте и на одном боку,
        # получают одинаковый сдвиг независимо от того, насколько шерсть дальше
        # от оси, - зазор между слоями сохраняется, и уступа на границе нет.
        # Спереди участвует только то, что впереди самой точки роста, и переход
        # задан положением, а не нормалью, иначе вернулась бы та же огранка.
        d = Vector(part.get('direction', [0.0, 1.0, 0.0])).normalized()
        rad = float(part.get('radius', 20.0))
        front = float(part.get('frontFade', 12.0))
        centers = [Vector(c) for c in part.get('centers', [])]
        keep = [g.index for g in obj.vertex_groups
                if any(k.lower() in g.name.lower()
                       for k in part.get('includeContains', []))]
        for i, v in enumerate(obj.data.vertices):
            co = obj.matrix_world @ v.co
            best = 0.0
            for c in centers:
                rel = co - c
                along = rel.dot(d)
                across = (rel - d * along).length
                t = smooth(1.0 - across / rad) * smooth(along / front)
                if t > best:
                    best = t
            if best <= 0.01:
                continue
            if keep:
                w = min(1.0, sum(g.weight for g in v.groups if g.group in keep))
                best *= smooth((w - 0.15) / 0.25)
                if best <= 0.01:
                    continue
            # Окно по высоте отделяет грудь от живота. Одного спада от точки роста
            # мало: у зверя грудь и брюхо стоят вплотную, и круглая область
            # непременно залезает на соседа - тогда ползунок груди раздувает пресс.
            best *= _window(part, co)
            if best <= 0.01:
                continue
            out[i] = d * (amount * best)
        return out

    if mode == 'bumps':
        # Область задаётся точками, но её можно ещё и ограничить костями.
        # Без ограничения выпуклость груди захватывала плечо и руку: они рядом,
        # а расстояние до точки роста ничего не знает про то, чья это часть тела.
        centers = [Vector(c) for c in part.get('centers', [])]
        rad = float(part.get('radius', 5.0))
        keep = [g.index for g in obj.vertex_groups
                if any(k.lower() in g.name.lower()
                       for k in part.get('includeContains', []))]
        drop = [g.index for g in obj.vertex_groups
                if any(k.lower() in g.name.lower()
                       for k in part.get('excludeContains', []))]
        facing = part.get('direction')
        facing = Vector(facing).normalized() if facing else None
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
            # Кости здесь - ПРОПУСК, а не сила: вопрос "принадлежит ли вершина
            # туловищу", а не "насколько". Умножение на самый вес глушило морф
            # в разы: кожа груди делит вес между позвоночником, ключицей и
            # скрутками, и на позвоночник ей достаётся едва треть.
            if keep:
                w = min(1.0, sum(g.weight for g in v.groups if g.group in keep))
                best *= smooth((w - 0.15) / 0.25)
            if drop:
                w = min(1.0, sum(g.weight for g in v.groups if g.group in drop))
                best *= 1.0 - smooth((w - 0.15) / 0.25)
            if best <= 0.01:
                continue
            nrm = v.normal.normalized()
            if facing is not None:
                # Брюхо пухнет ВПЕРЁД, а не во все стороны. Точка роста лежит внутри
                # тела, чтобы дотянуться и до кожи, и до шерсти над ней, а сторону
                # задаёт направление: участвует только та поверхность, что смотрит
                # туда. Без этого спина раздувалась наравне с животом.
                side = nrm.dot(facing)
                if side <= 0.0:
                    continue
                best *= side
                if best <= 0.01:
                    continue
            out[i] = nrm * (amount * smooth(best))
        return out

    wanted = part.get('bones', [])
    gi = [obj.vertex_groups[b].index for b in wanted if b in obj.vertex_groups]
    # Опечатка в имени кости раньше проходила молча: ползунок собирался, попадал
    # в файл, принимал значение и не двигал ничего. Так пропал CLAWNeck. Теперь
    # о каждой ненайденной кости говорится вслух, а часть без единой найденной -
    # это ошибка рецепта, а не пустой результат.
    missing = [b for b in wanted if b not in obj.vertex_groups]
    if missing and log and strict:
        log("MORPH|%s: нет привязок %s" % (obj.name, ", ".join(missing)))
    if wanted and not gi and strict:
        raise KeyError("%s: ни одна из костей %s не найдена в форме"
                       % (obj.name, ", ".join(wanted)))
    if not gi:
        return out
    if mode == 'spike':
        return _spike(obj, part, gi, amount)

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
            w *= _window(part, co)
            if w <= 0.01:
                continue
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
            w *= _window(part, co)
            if w <= 0.01:
                continue
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
        w *= _window(part, co)
        if w <= 0.01:
            continue
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


def carry_field(src_obj, src_delta, dst_obj, k=6, max_dist=6.0):
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
        # Наследование обязано быть МЕСТНЫМ. Оболочки шерсти лежат в одной-двух
        # единицах над кожей, а голова, морда и заплатки головы - в десятках:
        # без предела голова целиком уезжала вместе с грудью, потому что её
        # ближайшими вершинами кожи оказывалась шея.
        #
        # Предел этот обязан быть ПЛАВНЫМ. Резкая отсечка "дальше max_dist не
        # наследуем" рвёт поверхность ровно так же, как рвал пропуск несдвинутых
        # вершин: соседние вершины оболочки по разные стороны порога получают
        # одна полный сдвиг, другая ноль. Замер это показал сразу - у шерсти
        # живота растяжение подскочило с 6.45 до 23.25. Поэтому сила наследования
        # спадает по расстоянию до ближайшей вершины источника, а не обрывается.
        nearest = None
        for _c, i, dist in tree.find_n(co, k):
            # Вершину кожи, которую морф не двигает, надо взять НУЛЁМ, а не пропустить.
            # Пропуск означал, что оболочка над краем области получала полный сдвиг
            # единственной сдвинутой соседки, тогда как кожа под ней почти не двигалась:
            # у гладкого поля на коже появлялся обрыв на оболочке, и она рвалась там,
            # где кожа цела. Замер это и показывал - растяжение рёбер на шерсти вдвое
            # больше, чем на коже, при любом положении ползунка.
            if nearest is None:
                nearest = dist
            d = src_delta.get(i, ZERO)
            w = 1.0 / max(dist, 1e-4)
            acc += d * w
            tot += w
        if tot <= 0.0 or nearest is None:
            continue
        # Полная сила до половины предела, ноль на пределе, плавно между ними.
        atten = smooth((max_dist - nearest) / max(max_dist * 0.5, 1e-4))
        if atten <= 0.0:
            continue
        got = (acc / tot) * atten
        if got.length > 0.001:
            out[j] = got
    return out


def apply_to_shape(item, objects, donor, log=print):
    """Ползунок «к форме другого тела»: цель берётся у донора вершина в вершину.

    Тела полов топологически одинаковы - совпадает и число вершин, и их порядок, -
    поэтому разница между ними это готовое поле сдвига, считать нечего. Знак решает,
    в какую сторону по этому полю идти: `sign` 1 ведёт К донору, -1 ведёт ОТ него,
    то есть продолжает ту же разницу за пределы обоих тел. Второе и позволяет отдать
    самцу тот же ползунок, что и самке: у самца поле «к самцу» было бы нулевым.

    Область режется тремя ограничителями сразу, и все три нужны: пояс по высоте,
    предел по ширине и пропуск по привязке. Грудь и плечо лежат на одной высоте
    и на одном удалении от осевой линии, а тела полов различаются не только грудью,
    но и рукой - ни высота, ни ширина их не разделяют, разделяет только кость.
    """
    base = objects.get(item['base'])
    if base is None or donor is None:
        log("MORPH|%-16s нет опорной формы или донора" % item['morph'])
        return
    target = donor.get(base.name)
    if target is None or len(target) != len(base.data.vertices):
        log("MORPH|%-16s донор не подходит к форме %s" % (item['morph'], base.name))
        return
    gate = [g.index for g in base.vertex_groups
            if any(k.lower() in g.name.lower() for k in item.get('includeContains', []))]
    z0, z1 = item['zRange']
    fade = float(item.get('zFade', 8.0))
    xlim = item.get('xLimit')
    sign = float(item.get('sign', 1.0))
    delta = {}
    for i, v in enumerate(base.data.vertices):
        co = base.matrix_world @ v.co
        w = smooth((co.z - z0) / fade) * smooth((z1 - co.z) / fade)
        if xlim:
            w *= smooth((float(xlim) - abs(co.x)) / 4.0)
        if gate:
            wb = min(1.0, sum(g.weight for g in v.groups if g.group in gate))
            w *= smooth((wb - 0.15) / 0.25)
        if w <= 0.01:
            continue
        d = (target[i] - v.co) * (w * sign)
        if d.length > 0.001:
            delta[i] = d
    if not delta:
        log("MORPH|%-16s поле пустое" % item['morph'])
        return
    _put_key(base, item['morph'], delta, log)
    for shape in item.get('carry', []):
        dst = objects.get(shape)
        if dst is None:
            continue
        got = carry_field(base, delta, dst)
        if got:
            _put_key(dst, item['morph'], got, log)


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
            # Наследование идёт ЦЕПОЧКОЙ, а не веером от кожи ко всем сразу.
            # Тело собрано в несколько слоёв: кожа, над ней шерсть живота и спины,
            # а шерсть груди, заплатки швов и голова лежат уже над ЭТОЙ шерстью,
            # в десятках единиц от кожи. Поле от кожи до них не достаёт, и до
            # порога расстояния они получали чужой сдвиг, а после порога -
            # никакого. Поэтому запись наследника может назвать свой источник:
            # {"shape": "fur_chest", "from": "fur_belly"}. Простая строка
            # означает прежнее поведение - наследование прямо от опорной формы.
            fields = {item['base']: delta}
            for entry in item.get('carry', []):
                shape = entry if isinstance(entry, str) else entry['shape']
                origin = item['base'] if isinstance(entry, str) else entry.get('from', item['base'])
                dst = objects.get(shape)
                if dst is None:
                    log("MORPH|%-16s нет формы %s" % (morph, shape))
                    continue
                if origin not in fields:
                    log("MORPH|%-16s %-14s источник %s ещё не посчитан"
                        % (morph, shape, origin))
                    continue
                reach = float(entry.get('maxDist', 6.0)) if isinstance(entry, dict) else 6.0
                got = carry_field(objects[origin], fields[origin], dst,
                                  int(item.get('carryNeighbours', 6)), reach)
                # Приращённая ДЕТАЛЬ следует за телом целиком, а не растягивается
                # поперёк себя. Узел длиной пятнадцать единиц лежит поперёк области
                # морфа, и разные его концы наследовали разный сдвиг: сборка рвалась
                # по собственному шву. Жёсткое следование берёт средний сдвиг и
                # двигает деталь как одно тело.
                if got and isinstance(entry, dict) and entry.get('rigid'):
                    mean = Vector((0.0, 0.0, 0.0))
                    for d in got.values():
                        mean += d
                    mean /= len(got)
                    got = {j: mean.copy() for j in range(len(dst.data.vertices))}
                fields[shape] = got
                if got:
                    _put_key(dst, morph, got, log)
                else:
                    log("MORPH|%-16s %-14s поле не дотянулось от %s"
                        % (morph, shape, origin))
            continue

        # Морф, заданный КОСТЬЮ - поворот, рост, растяжение вдоль оси, обхват, -
        # считается на каждой части меша по ЕЁ СОБСТВЕННЫМ привязкам, а не берётся
        # с кожи полем по близости. Кость двигает и кожу, и коготь, и шерсть хвоста
        # согласованно - ровно так, как это делает движок при анимации.
        #
        # Наследование по близости для таких морфов было прямой ошибкой: коготь,
        # шерсть хвоста и нижняя челюсть висят далеко от кожи, и ближайшая вершина
        # кожи к ним не имеет отношения. Коготь получал сдвиг ближайшей точки пальца
        # и улетал; хвост рассыпался; челюсть уезжала без зубов.
        #
        # Звёздочка означает "на всех частях": часть без нужных костей просто ничего
        # не получит, и это законно, а не ошибка рецепта.
        wanted = item.get('shapes', [])
        every = wanted == '*'
        names = sorted(objects) if every else wanted
        touched = []
        for shape in names:
            obj = objects.get(shape)
            if obj is None:
                log("MORPH|%-16s нет формы %s" % (morph, shape))
                continue
            delta = {}
            for part in item['parts']:
                for i, d in deltas_for(obj, part, arm, log, not every).items():
                    delta[i] = delta.get(i, Vector((0, 0, 0))) + d
            if not delta:
                if not every:
                    log("MORPH|%-16s %-14s костей нет, пропуск" % (morph, shape))
                continue
            _put_key(obj, morph, delta, log)
            touched.append(shape)
        if every and not touched:
            raise KeyError("%s: ни одна часть меша не отозвалась на кости рецепта" % morph)


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
