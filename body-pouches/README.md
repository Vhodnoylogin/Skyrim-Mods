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

## Where the mechanic comes from

VRIK owns the place on the body, and `GetHolsterSlotInReach(secondaryHand)` answers for any hand
whatever it holds - that part is flawless and is what this mod leans on. What VRIK does not give
is a moment. Its holster callback is part of its weapon logic: it fires when a weapon could be
drawn or put away, and for a pouch of potions that is never. Six sessions in the game settled it:

| what the hand held | slot 13 in reach | holster callback |
|---|---|---|
| a two-hander | yes | yes, twice |
| a potion, either hand, four tries | yes, every time | never |
| nothing, at an empty slot | yes, six times | never |

So the place comes from VRIK and the moment comes from elsewhere:

    putting in   HIGGS lets go of something while the hand is at a pouch
    taking out   a button is pressed by a hand at a pouch (grip by default)

Neither needs anything of VRIK beyond the question "which slot is this hand at", and the pouch
keeps working the day VRIK starts raising an event of its own.

The two halves share a button, and that is not an oversight: the squeeze that draws is the squeeze
HIGGS holds a thing with. A tap is therefore a draw and a put-back in one movement, too quick to
see. A release at the pouch within `settleMs` of a draw is named for what it is - the end of that
gesture rather than a fresh reach - and said so out loud, which is the whole difference between
"the button did nothing" and "the button did both halves at once".

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

## Building

    cmake -S . -B build-core -DBODYPOUCHES_BUILD_PLUGIN=OFF   # core and checks, no network
    cmake --build build-core --config Release
    build-core\tests\Release\bodypouches_tests.exe

    cmake -S . -B build                                       # the mod itself, fetches CommonLibSSE-NG
    cmake --build build --config Release --target BodyPouches
    tools\package.ps1 -Apply                                  # archive into downloads, installed through the MO2 bridge

The settings file and the table of text are written by the plugin on first run into
`Data\SKSE\Plugins\bodypouches\`, so the mod itself is one library.

## State

The simple variant is written and builds. One pouch, on the stomach (slot 13), shows one
bottle, the contents come straight from the pack, and setting up is done by hand.

The slot needs two things at once, and that is not a choice but a consequence of how VRIK
works: a slot allowing no weapon type is not detected at all ("set all weapon types to 0 to
disable a slot" is its author's own comment in `vrikslots.ini`), and the slots a build leaves
free are switched off in exactly that way.

**The mod does not change VRIK's settings.** It reads them, and when a slot is off it says so in
the log and names where it is switched on: VRIK's MCM, the Weapon / Leg / Body / Arm Holsters
pages, any one weapon type for that slot. Somebody else's setting is not ours to change on their
behalf - not even in memory, not even reversibly: another mod may be arranging the same value,
and the player would see one thing in the menu and get another in the game.

Anyone who would rather the mod did it sets `mayEnableSlots: true` in `bodypouches.json`; the
slot is then switched on from code and every such change is written to the log. Off by default.

Suspension is unaffected: a slot given over to a pouch entirely is suspended after every load -
that state VRIK keeps for plugins and, by its author's design, never saves.

The first session in the game, on 20 September, settled nothing about the pouches and one thing
about the handshake: the interfaces were asked for at `kPostLoad`, and both dispatches returned
false because at that moment neither VRIK nor HIGGS had registered a listener yet. Load order
decides who is ready first, so that moment is a race. The request now goes out at
`kPostPostLoad`, and everything below is still what the next session settles:

| What | Why it is unknown |
|---|---|
| whether switching the slot on at runtime takes effect | `setSettingDouble` changes the setting in memory, but whether VRIK rereads it without waiting for a recalibration is not visible in the code |
| whether VRIK will draw a potion in a slot | `VrikSetSlotForArt` takes an art object, but what it does with something that is not a weapon is not visible in the code |
| whether "secondary hand" is read correctly | VRIK says secondary, HIGGS and the game say left; the translation is made from the left-handed setting and is untested |
| which node the bottle appears at | `LeftWandNode`, the hand, the finger are tried in turn - which exists in VR shows only in the game |
| whether HIGGS lets go of a bottle we put back in the pack | the reference is deleted out of its hand, and nothing says how it takes that |
