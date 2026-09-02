Scriptname EnvoyQuest extends Quest
{Носитель мода: поднимается при старте игры и сообщает о готовности моста.}

Event OnInit()
    RegisterForModEvent("Envoy_Ready", "OnEnvoyReady")
    OnGameReload()
EndEvent

Event OnEnvoyReady(string asEventName, string asUnused, float afContract)
    OnGameReload()
EndEvent

Function OnGameReload()
    if !Envoy.IsAvailable()
        Debug.Trace("[Envoy] мост недоступен: плагин не загрузился")
        return
    endIf
    Debug.Trace("[Envoy] контракт версии " + Envoy.GetInterfaceVersion())
EndFunction
