# donors\ — чужие меши, лежащие здесь с разрешения

Два файла из мода **Elegant Werewolf Replacer with Player Only and Randomized Options**
([93336](https://www.nexusmods.com/skyrimspecialedition/mods/93336), авторы Wolflady500
и KaienHash). Это вход сборки: журнал в `recipes\build.json` описывает, как превратить
их в наши тела, но без самих файлов он не исполняется.

| файл | CRC32 | закреплён в журнале как |
|---|---|---|
| `malebodywerewolf_1.nif` | `300435BB` | `elegantMale` |
| `femalebodywerewolf_1.nif` | `01E04C78` | `elegantFemale` |

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

## Чего здесь НЕТ и почему

`skeleton.nif` из XP32 Maximum Skeleton Special Extended
([1988](https://www.nexusmods.com/skyrimspecialedition/mods/1988), Groovtama) — третий вход
сборки, и он **не покрыт** разрешением выше: оно от других авторов и про другой мод.
Пока условия XP32 не разобраны отдельно, скелет берётся с установленного мода на машине
сборщика, как и раньше, и в репозиторий не кладётся.
