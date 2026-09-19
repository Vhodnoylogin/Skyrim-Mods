# body-pouches — pouches worn on the body

A working name for the module. The name the mod is released under will be a different one.

The mod turns the VRIK holsters worn on the body into pouches: a slot holds not only a weapon but
a flask, food or a throwing knife, and the hand takes it straight out of there — no menu, no wheel,
no hotkey. Take a potion off the hip, bring it to the mouth, drink it, put the empty flask back.

## How this differs from what already exists

| Mod | What it does | What it does not |
|---|---|---|
| HIGGS | drink by bringing a bottle to the mouth; stow an item over the shoulder | does not keep potions on the body |
| VRIK | 14 holsters on the body, tied to the figure and surviving calibration | only weapons, shields and torches go into them |
| Spell Wheel VR | puts a potion in the hand | the item comes out of a menu, not off the body |
| Immersive Equipment Displays | shows an arbitrary item on the body | it is a display case: nothing can be taken from it by hand |

Half the work is therefore already done by other people, and this mod builds neither its own
geometry on the body nor its own "the hand is near" detection. It sits exactly in the middle: the
place on the body comes from VRIK, handing the item over and drinking come from HIGGS, and what
belongs to the mod is only the rule of what lies in this slot and what to do when somebody reaches
for it.

## What made it possible

The VRIK holster mechanic lived in Papyrus and was not exposed. Build 80700 (VRIK 0.8.7) ships a
public C++ interface, and in it three things that did not exist before:

```cpp
typedef bool (*HolsterAttemptCallback)(int slotNumber, bool secondaryHand, bool handOccupied);
virtual bool SetSlotSuspended(int slotNumber, bool suspended) = 0;
virtual bool GetSlotSuspended(int slotNumber) = 0;
virtual void AddHolsterAttemptCallback(HolsterAttemptCallback callback) = 0;
```

The callback fires for **every** slot, and its return decides who serves the attempt: `true` is the
normal VRIK action, `false` means the plugin took the attempt and VRIK does nothing. Suspension is
the blunter instrument, for a slot given over to the mod entirely; a suspended slot stays visible
and detectable, and the suspended state lives in memory only and never reaches a save.

Because of that `bool`, the mod does not take slots away from VRIK: in one and the same slot a sword
is still a sword and is drawn by VRIK, while a flask is drawn by us.

## What it is made of

    contract\      foreign contracts as they came: vrikinterface001.h (build 80700), higgsinterface001.h
    src\core\      the core: slots, their contents and the rule of handing over. Not a line about VR, SKSE or the game
    src\vr\        two adapters: VRIK (subscription and slot state) and HIGGS (hand-over, drinking)
    src\           the SKSE entry points, settings, log
    localization\  every line of text the mod puts out, by key
    tests\         checks of the core, built and run without the game
    docs\          the reasoning and the decisions

The core builds and is checked without SKSE and without the game — the game is attached as the layer
above. That buys a second way out as well: in flat Skyrim a slot may hand the item over differently,
and the core has no need to know.

## State

A skeleton. The core and the adapters are not written yet.
