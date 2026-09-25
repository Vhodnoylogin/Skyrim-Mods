"""Writes BodyPouches.esp: the three records that let a pouch show what it holds.

    python tools/make-esp.py <output.esp>

WHY A PLUGIN AT ALL. VRIK draws a thing in a slot only as an art object played on
the player: its DLL catches the moment the art's model is set up, hangs the model on
the slot's bone and moves it to the centre of the slot every frame. The art has to be
a record, and something has to play it - so the plugin carries an art, a magic effect
whose hit effect is that art, and a constant ability made of that effect. The DLL
gives VRIK the art (VrikSetSlotForArt), puts the potion's model on it, and adds or
removes the ability.

WHY WRITTEN BY A SCRIPT. Three records do not need an editor, and a script says what
is in them in words that can be read and diffed; the binary is built, not kept.

The local form ids below are the contract with src/game/Picture.cpp.
"""

import struct
import sys

ART_ID = 0x800      # ARTO, a magic hit effect art; its model is replaced at run time
EFFECT_ID = 0x801   # MGEF, script archetype, constant, self, hit effect art = ART_ID
ABILITY_ID = 0x802  # SPEL, an ability with that one effect

MASTER = "Skyrim.esm"
# With one master, the plugin's own records carry the load index 01.
SELF = 0x01000000

# Any potion model the game certainly has. The DLL sets the model of the potion that
# is actually in the pouch before it plays the art, so this one only shows if the
# engine restarts the ability from a save before the DLL has had its say.
DEFAULT_MODEL = "Clutter\\Potions\\PotionHealthLesser.nif"

FORM_VERSION = 44   # Skyrim SE and VR
HEDR_VERSION = 1.70


def zstring(text):
    return text.encode("cp1252") + b"\x00"


def sub(tag, data):
    return tag.encode("ascii") + struct.pack("<H", len(data)) + data


def record(tag, form_id, subrecords, flags=0):
    data = b"".join(subrecords)
    header = struct.pack("<4sIIIHHHH", tag.encode("ascii"), len(data), flags, form_id,
                         0, 0, FORM_VERSION, 0)
    return header + data


def group(tag, records):
    data = b"".join(records)
    header = struct.pack("<4sI4siHHI", b"GRUP", 24 + len(data), tag.encode("ascii"), 0, 0, 0, 0)
    return header + data


def art():
    return record("ARTO", SELF | ART_ID, [
        sub("EDID", zstring("BodyPouchesPotionArt")),
        sub("OBND", bytes(12)),
        sub("MODL", zstring(DEFAULT_MODEL)),
        sub("DNAM", struct.pack("<I", 1)),  # 1 = magic hit effect
    ])


def effect():
    no_duration = 1 << 9
    no_magnitude = 1 << 10
    no_area = 1 << 11
    fx_persist = 1 << 12   # the hit effect art stays for as long as the effect does
    hide_in_ui = 1 << 15
    painless = 1 << 26
    flags = no_duration | no_magnitude | no_area | fx_persist | hide_in_ui | painless

    none_av = -1
    script_archetype = 1
    constant_effect = 0
    self_delivery = 0
    silent = 2

    data = struct.pack(
        "<IfIiiHHIfIIIIffffIiIIIIiIIIfIfIIIIIIIff",
        flags,
        0.0,                 # base cost
        0,                   # associated item
        none_av,             # magic skill
        none_av,             # resist value
        0, 0,                # counter effect count, unused
        0,                   # casting light
        0.0,                 # taper weight
        0, 0,                # hit shader, enchant shader
        0,                   # minimum skill level
        0,                   # spellmaking area
        0.0,                 # spellmaking casting time
        0.0, 0.0,            # taper curve, taper duration
        0.0,                 # second actor value weight
        script_archetype,
        none_av,             # primary actor value
        0, 0,                # projectile, explosion
        constant_effect,
        self_delivery,
        none_av,             # second actor value
        0,                   # casting art
        SELF | ART_ID,       # hit effect art: the one thing this effect is for
        0,                   # impact data set
        0.0,                 # skill usage multiplier
        0,                   # dual casting data
        1.0,                 # dual casting scale
        0,                   # enchant art
        0, 0,                # hit visuals, enchant visuals
        0,                   # equip ability
        0,                   # image space modifier
        0,                   # perk to apply
        silent,              # casting sound level
        0.0, 0.0,            # script effect AI score, AI delay time
    )
    assert len(data) == 152, len(data)

    return record("MGEF", SELF | EFFECT_ID, [
        sub("EDID", zstring("BodyPouchesPotionShown")),
        sub("FULL", zstring("Body Pouches: potion on show")),
        sub("DATA", data),
        sub("DNAM", zstring("")),
    ])


def ability():
    manual_cost = 1 << 0
    ability_type = 4
    constant_effect = 0
    self_delivery = 0
    spit = struct.pack("<IIIfIIffI", 0, manual_cost, ability_type, 0.0,
                       constant_effect, self_delivery, 0.0, 0.0, 0)
    assert len(spit) == 36

    return record("SPEL", SELF | ABILITY_ID, [
        sub("EDID", zstring("BodyPouchesPotionShownAbility")),
        sub("OBND", bytes(12)),
        sub("FULL", zstring("Body Pouches: potion on show")),
        sub("DESC", zstring("")),
        sub("SPIT", spit),
        sub("EFID", struct.pack("<I", SELF | EFFECT_ID)),
        sub("EFIT", struct.pack("<fII", 0.0, 0, 0)),
    ])


def header(record_and_group_count):
    return record("TES4", 0, [
        sub("HEDR", struct.pack("<fiI", HEDR_VERSION, record_and_group_count, ABILITY_ID + 1)),
        sub("CNAM", zstring("Vhodnoylogin")),
        sub("SNAM", zstring("Body Pouches: shows the potion a pouch holds, through VRIK")),
        sub("MAST", zstring(MASTER)),
        sub("DATA", bytes(8)),
    ])


def build():
    # Groups in the order the engine's own files keep them.
    groups = [group("MGEF", [effect()]), group("SPEL", [ability()]), group("ARTO", [art()])]
    return header(len(groups) * 2) + b"".join(groups)


def main():
    if len(sys.argv) != 2:
        print(__doc__.splitlines()[2].strip())
        return 2
    data = build()
    with open(sys.argv[1], "wb") as out:
        out.write(data)
    print(f"{sys.argv[1]}: {len(data)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
