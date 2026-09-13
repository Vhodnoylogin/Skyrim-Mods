# donors\ — чужие меши, лежащие здесь с разрешения

Три чужих файла — все входы сборки. Это вход сборки: журнал в `recipes\build.json` описывает, как превратить
их в наши тела, но без самих файлов он не исполняется.

| файл | из мода | CRC32 | в журнале |
|---|---|---|---|
| `malebodywerewolf_1.nif` | Elegant | `300435BB` | `elegantMale` |
| `femalebodywerewolf_1.nif` | Elegant | `01E04C78` | `elegantFemale` |
| `skeleton.nif` | XP32 | `1221F7AC` | `xp32Skeleton` |

Суммы совпадают с закреплёнными в `build.json`: сборка откажется работать, если файл
подменят.

---

## Разрешение

Спрошено отдельно и получено 13.09.2026 от Wolflady500 личным сообщением
([forums.nexusmods.com/messenger/6102798](https://forums.nexusmods.com/messenger/6102798/)),
дословно:

> Oh lovely! I'm gonna answer twice anyway because like you said, comments are easy
> to miss. Yes go ahead and do the public repository of just the two meshes included!
> As long as textures aren't there, it's fine! Since it's incomplete.

Разрешение спрашивалось **именно про хранение файлов в открытом репозитории**, а не про
использование моделей в моде: последнее и так разрешено условиями страницы. Разница
существенная, поэтому вопрос задавался отдельно.

**Границы разрешения, и выходить за них нельзя:**

| можно | нельзя |
|---|---|
| эти **два** меша | любые другие файлы Elegant |
| открытый репозиторий | — |
| — | **текстуры** — ни одной, ни в каком виде |

Условие про текстуры не формальность, а суть довода автора: без них модель неполна
(«since it's incomplete»), и мод остаётся нужным. Наши меши ссылаются на текстуры Elegant
и своих не возят — то есть без установленного Elegant зверь выходит нетекстурированным.
Положить сюда хоть одну текстуру значит разрушить и договорённость, и этот довод.

---

## Разрешение XP32: скелет свободен по условиям страницы

`skeleton.nif` — из **XP32 Maximum Skeleton Special Extended**
([1988](https://www.nexusmods.com/skyrimspecialedition/mods/1988), Groovtama). Спрашивать
никого не понадобилось: условия страницы говорят об этом прямо.

> Skeleton files: Skeleton .nifs and .hkx files are **permission free**, because they are
> based on Bethesdas original files.

> YOU DON'T HAVE TO ASK ME FOR PERMISSION WHEN YOU HAVE TO MODIFY XPMS(S)E FILES AND
> RELEASE THESE MODIFICATIONS, OR INCLUDE ORIGINAL OR MODIFIED XPMS(S)E SKELETONS IN MODS…
> YOU ARE NOT ALLOWED TO USE XPMS(S)E FILES TO REPACKAGE THEM IN A MOD TO DO AN XPM(S)SE
> REPLACEMENT.

Единственный запрет — **замена самого XP32**: собрать из его файлов мод, который ставят
вместо него. Мы делаем обратное: требуем XP32 установленным и меняем числа капсул в одном
его файле, на одном пути одной расы. Это ровно тот случай, который в условиях назван
разрешённым — «modify XPMSSE files and release these modifications».

Там же просьба автора, которую мы соблюдаем не нарочно, а по устройству: не заводить
своих рас с отдельными путями скелета. У нас путь ванильный, `actors\werewolfbeast`.

Отдельно: загрузка XPMSSE на другие площадки разрешена с указанием автора. Groovtama
указывается зависимостью и благодарностью на странице мода.
