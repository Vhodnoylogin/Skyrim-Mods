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

VRIK owns the place on the body and the moment of taking out; HIGGS owns the moment of putting in.
How VRIK behaves was settled by a reading of its own code (`claude-skyrim-vr/knowledge/vrik-holster-api.md`
in the project journal), and the mod is built on exactly that:

    taking out    close the grip inside the pouch and pull the hand out with it still closed:
                  VRIK raises a holster attempt for the empty hand, and the mod puts a bottle in it
    putting in    let go of the bottle inside the pouch: HIGGS says "dropped", VRIK says the hand
                  is at the pouch at that very moment, and the bottle goes back into the pack
    carrying off  a hand holding a bottle that leaves the pouch with the grip closed keeps it

The pouch's slot is suspended, and that does three things at once: VRIK neither draws a weapon from
it nor holsters one into it; an empty hand sees the slot at all, where without suspension VRIK looks
straight past a free hand at an empty slot; and the controller buzzes as a hand enters it.
Suspension lasts until the game is closed and is set at the first frame of play, because a new game
sends a plugin no message to set it on.

There is no button and no gesture of the mod's own any more, and no memory of where a hand was a
moment ago. Run 7 showed what they cost: a press drew a bottle, the hand leaving the pouch with it
was taken for putting it back, and a bottle let go of a second after the hand had left still
counted as put away.

## What a pouch shows

The potion it would hand over, hanging on the body where the pouch is - and only for a pouch the
slot was given over to entirely; a shared slot still shows the sword VRIK keeps there.

VRIK draws a thing in a slot only as an art object played on the player: its DLL catches the moment
the art's model is set up, hangs the model on the slot's bone and keeps it in the middle of the
slot. So the mod carries a small plugin, `BodyPouches.esp`, written by `tools\make-esp.py`: an art,
a constant effect whose hit effect is that art, and an ability made of the effect. The DLL gives
VRIK the art once per game (`VrikSetSlotForArt`), gives the art the model of the potion that would
come out next, and adds the ability to the player - or takes it away when the pack has none left.
Changing the potion is taking the ability off, waiting until VRIK says the old model is gone
(`VrikGetSlotDisplayed`), and putting it on again.

`VrikSetSlotWeaponType` was tried first and could not have worked: for anything but a weapon, a
shield or a torch it records "empty".

## What is not written yet

**A pouch forgets what it is for when the game is closed.** It is set up by letting go of a bottle
in it, and that choice lives in memory only.

**The pouch sits wherever VRIK's Stomach slot sits.** In the author's build that is up at the chest,
close to HIGGS's mouth, where a bottle meant for the pouch can be drunk instead. The slot is moved
in VRIK's own configuration - the copy of `vrikslots.ini` in the build's VRIK config mod - and the
numbers come from the game: every squeeze of an empty hand's grip writes into the log the
`posX13`, `posY13` and `posZ13` that would put the pouch exactly where the hand is.

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
    src\game\      the game side: the pack, forms, where a slot is on the body, the picture
    src\           the SKSE entry points, settings, the log and its texts (Loc.cpp, by key)
    tests\         checks of the core, built and run without the game
    tools\         staging and packing, and make-esp.py, which writes BodyPouches.esp

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

Version 0.1.8. One pouch, on the stomach slot (13), given over to the mod entirely: it draws on
VRIK's own holster attempt, stows when a bottle is let go of inside it, and shows the potion it
holds. Run 7 (0.1.7) proved the moment of drawing and every step of the hand-over; this version is
the first to take out and put in by VRIK's rules rather than against them, and the first with a
picture.

The slot needs two things at once, and that is not a choice but a consequence of how VRIK works: a
slot allowing no weapon type is not detected at all ("set all weapon types to 0 to disable a slot"
is its author's own comment in `vrikslots.ini`), and the slots a build leaves free are switched off
in exactly that way.

**The mod's code does not change VRIK's settings.** It reads them, and when a slot is off it says
so in the log and names where it is switched on: VRIK's MCM, the Weapon / Leg / Body / Arm Holsters
pages, any one weapon type for that slot. Anyone who would rather the mod did it sets
`mayEnableSlots: true` in `bodypouches.json`; the slot is then switched on from code, in memory, and
every such change is written to the log. Off by default. What does have to change in VRIK's
configuration - the pouch's place, for one - is changed openly, in the build's VRIK config mod.

What the next run settles:

| What | What says it |
|---|---|
| whether the potion appears on the body, and where | `picture.up`, then `picture.on_body`: VRIK's own word that the model is on the bone |
| whether a free hand still raises an attempt without `VrikSetSlotWeaponType` | `holster.offered` with `handOccupied = false` as the hand pulls out of the pouch |
| whether HIGGS holds the bottle while VRIK keeps the grip from the game | `draw.grab_confirmed` rather than `draw.grab_failed` |
| where the pouch should hang | `body.squeeze`: the numbers that would put it at the hand |
