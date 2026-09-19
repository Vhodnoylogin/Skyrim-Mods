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

		// Left Hip and Right Hip. VRIK counts its fourteen slots
		//   1 Left Hip     2 Right Hip     3 Left Thigh    4 Right Thigh
		//   5 Left Calf    6 Right Calf    7 Left Upper Arm 8 Right Upper Arm
		//   9 Left Forearm 10 Right Forearm 11 Left Shoulder 12 Right Shoulder
		//   13 Stomach     14 Chest
		// and the two hip slots are where a belt actually is. Shared rather than
		// exclusive on purpose: on a build that keeps a weapon there, a shared pouch
		// steps aside instead of taking the slot away.
		static Settings Defaults();

		[[nodiscard]] static Core::Mode ModeFromText(const std::string& a_text) noexcept;
	};

	// Reads the settings file, writing the defaults out first if it is not there.
	Settings LoadSettings();
}
