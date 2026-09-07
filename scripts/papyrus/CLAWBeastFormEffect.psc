Scriptname CLAWBeastFormEffect extends ActiveMagicEffect
{Переключает облик цели между обычной расой и расой вервольфа.

Превращения заклинанием у игры нет: своё она делает квестовым скриптом,
который меняет расу вызовом SetRace. Здесь то же самое, только поводом
служит наложенный эффект.

Обе расы заданы свойствами, а прежняя НЕ запоминается. Так сделано нарочно:
хранить её негде — эффект живёт недолго и памяти между применениями не имеет,
а единственное общее хранилище, StorageUtil, тянет за собой PapyrusUtil,
а тот SKSE-заголовки. Для нашей спутницы это ничего не стоит: она нордка,
и возвращать её надо именно в нордку.}

Race Property BeastRace Auto
{Раса зверя. WerewolfBeastRace из Skyrim.esm.}

Race Property HumanRace Auto
{Раса, в которую возвращать. NordRace из Skyrim.esm.}

Event OnEffectStart(Actor akTarget, Actor akCaster)
    If akTarget == None || BeastRace == None || HumanRace == None
        Return
    EndIf

    If akTarget.GetRace() == BeastRace
        akTarget.SetRace(HumanRace)
        Debug.Notification("Облик человека возвращён")
    Else
        akTarget.SetRace(BeastRace)
        Debug.Notification("Облик зверя принят")
    EndIf
EndEvent
