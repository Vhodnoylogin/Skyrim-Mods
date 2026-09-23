#pragma once

#include "core/Pouch.h"

#include <string>
#include <vector>

namespace BodyPouches
{
	// Everything about this mod that a person may want to change, and nothing that they
	// may not.
	//
	// The defaults are built into the binary and written out as bodypouches.json on
	// first run, so the file always exists to be read and edited and never has to be
	// written from a wiki page. A file that cannot be parsed is reported and ignored -
	// the mod runs on the defaults rather than not at all.
	struct Settings
	{
		struct PouchSetting
		{
			int         slot{};
			std::string mode{ "shared" };
		};

		std::string               language{ "english" };
		std::string               logLevel{ "info" };
		std::vector<PouchSetting> pouches;

		// May this mod switch a VRIK slot on by itself?
		//
		// Off by default, and that is the whole point. VRIK's settings belong to VRIK
		// and to whoever arranged them; a mod that changes them behind the player's
		// back - even in memory, even reversibly - leaves somebody looking at one thing
		// in their menu and getting another in the game, and leaves two mods quietly
		// overwriting each other. So by default the mod only says what is wrong and
		// where to fix it, and this flag is how a player says "go ahead, do it for me".
		bool mayEnableSlots{ false };

		// Which controller button takes a bottle out of a pouch.
		//
		// VRIK raises no event for an empty hand at an empty slot - its holster callback
		// is part of its weapon logic and never fires for anything else - so drawing is
		// on us, and a press is the only thing a hand at the stomach can be said to have
		// done. The number is the VR button id; 2 is the grip, the same squeeze that
		// picks things up in HIGGS.
		int drawButton{ 2 };

		// How long after a hand leaves a slot a release still counts as happening there,
		// in milliseconds. The hand is read ten times a second, and a bottle dropped at
		// the stomach usually lands a moment after the hand has already moved on.
		int reachMemoryMs{ 1200 };

		// How long a bottle just taken out of a pouch is left alone, in milliseconds.
		//
		// The two gestures share a button and a place, so without this they collide: the
		// squeeze that draws is also the squeeze HIGGS holds a thing with, and letting it
		// go is what puts a thing away. Tap the button and the bottle is drawn and swallowed
		// again in the same breath, with nothing to show for it. Inside this window a
		// release at the same pouch is said out loud as a bounce, so that a run can tell
		// "the button did nothing" from "the button did both halves at once".
		int settleMs{ 800 };

		// One pouch, on the stomach. VRIK counts its fourteen slots
		//   1 Left Hip     2 Right Hip     3 Left Thigh    4 Right Thigh
		//   5 Left Calf    6 Right Calf    7 Left Upper Arm 8 Right Upper Arm
		//   9 Left Forearm 10 Right Forearm 11 Left Shoulder 12 Right Shoulder
		//   13 Stomach     14 Chest
		// and 13 is the belt buckle, reachable by either hand and used for a weapon by
		// almost nobody.
		//
		// Exclusive, not shared, and that pair of decisions goes together. VRIK ignores
		// a slot that allows no weapon type at all, so an unused slot is a slot nothing
		// can be done with - the hand is never even noticed there. The slot therefore
		// has to be switched on in vrikslots.ini (that is what the overlay mod built by
		// tools\slots-mod.ps1 does), and then suspended by us, so that VRIK sees the
		// hand but neither draws from the slot nor puts anything into it. Shared would
		// mean leaving it switched on for weapons as well, and then a hand reaching for
		// a potion could come back with a dagger.
		static Settings Defaults();

		[[nodiscard]] static Core::Mode ModeFromText(const std::string& a_text) noexcept;
	};

	// Reads the settings file, writing the defaults out first if it is not there.
	Settings LoadSettings();
}
