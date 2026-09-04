# Envoy — игровое API

Версия контракта 1. Объявления — в `Envoy.psc`.

## Пять фаз

| Фаза | Что происходит | Кто |
|---|---|---|
| `SUBSCRIBE` | мод объявляет темы, словарь и условие активности | мод, один раз |
| `OFFER`     | приходит событие темы — **предложение**, не поручение | мост |
| `INSPECT`   | мод забирает подробности и решает, участвовать ли | мод |
| `BID`       | `Envoy.Bid(...)` — или молчание | мод |
| `AWARD`     | мост объявляет победителя | мост |
| `SETTLE`    | `Envoy.Done(...)`; при провале приз уходит второму | мод |

## Подпись обработчика — четыре параметра, и это не обсуждается

```papyrus
Event OnSomething(string asEventName, string asEmpty, float afNumber, Form akSender)
```

**Три параметра не работают.** Машина Papyrus отвергает вызов целиком и пишет в журнал
`Incorrect number of arguments passed to function ... Expected 3, got 4 instead!`,
а обработчик не запускается вовсе. Снаружи это выглядит как «события не доходят»,
и на поиск этой причины ушло три игровых прогона.

Из четырёх параметров осмысленный один — `afNumber`: в нём номер реплики, запроса или
задания. Строка всегда пуста, потому что событие только будит, а данные читаются из моста
по номеру. Отправителя мост не заполняет.

## События

| Имя | Когда |
|---|---|
| `Envoy_Speech_Dialogue` | открыто окно диалога |
| `Envoy_Speech_Menu`     | открыто иное меню |
| `Envoy_Speech_Combat`   | игрок в бою |
| `Envoy_Speech_World`    | ничего из перечисленного |
| `Envoy_Speech_Channel`  | сработал явный канал |
| `Envoy_Award`           | лот разыгран |

Сигнатуру задаёт SKSE, менять её нельзя: **имя события, одна строка, одно число**.
Строка — распознанный текст (для `Envoy_Award` — имя победителя), число — номер реплики.

Реплика попадает **ровно в одну** тему. Фраза, сказанная вне окна диалога, до подписчиков
`Envoy_Speech_Dialogue` не дойдёт никогда — это отсечение по факту состояния игры, а не по догадке.

## Классы цены

    0  reversible  — ошибку легко отменить (выбор реплики, открытие меню)
    1  costly      — ошибка дорога (заклинание, удар, трата ресурса)

Для `costly` конфигурация требует более высокой уверенности и большего отрыва от второго
претендента. Если условие не выполнено — **не делает никто**: молчание всегда дешевле
неверного действия.

## Минимальный подписчик

```papyrus
Scriptname MySpellVoice extends Quest

string Property NS = "MySpells" AutoReadOnly

Event OnInit()
    if !Envoy.IsAvailable()
        return
    endIf
    string[] topics = new string[1]
    topics[0] = "world"
    Envoy.Subscribe(NS, topics)
    Envoy.RegisterVocabulary(NS, GetKnownSpellNames())
    RegisterForModEvent("Envoy_Speech_World", "OnHeard")
    RegisterForModEvent("Envoy_Award", "OnAward")
EndEvent

Event OnHeard(string asEventName, string asText, float afId)
    int id = afId as int
    if !Envoy.IsFinal(id)
        return
    endIf
    float mine = Envoy.GetVocabularyScore(id, NS)
    if mine < 0.7
        return
    endIf
    if Envoy.GetStateStatus(id, "core.target.looked") == 1
        Form t = Envoy.GetStateForm(id, "core.target.looked")
        ; ... оценить цель
    endIf
    Envoy.Bid(id, NS, mine, 1)
EndEvent

Event OnAward(string asEventName, string asWinner, float afId)
    if asWinner != NS
        return
    endIf
    int id = afId as int
    bool ok = CastSpellNamed(Envoy.GetVocabularyMatch(id, NS))
    Envoy.Done(id, NS, ok)
EndEvent
```

## Правила для подписчика

1. **Различай «нет» и «неизвестно».** `GetStateStatus` вернёт `0`, если ключ некому заполнить.
   Принять это за «нет» — тихая и потому худшая ошибка.
2. **Не считай в обработчике долго.** Окно ставок измеряется десятками миллисекунд.
   Все тяжёлые проверки — после `Envoy_Award`.
3. **Не действуй в `OFFER`.** Действует только победитель.
4. **Всегда отчитывайся `Done`.** Иначе лот будет висеть до истечения таймаута и глушить фразу.
