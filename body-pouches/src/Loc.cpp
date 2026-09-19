#include "Loc.h"

#include "Paths.h"

#include <algorithm>
#include <fstream>
#include <map>
#include <string_view>

namespace BodyPouches
{
	namespace
	{
		// The English table, and the only place in this mod where a sentence is
		// written. It is also the file a translator starts from: on first run it is
		// written out verbatim, comments and all.
		const std::map<std::string, std::string>& Builtin()
		{
			static const std::map<std::string, std::string> table{
				{ Keys::kPluginLoaded, "{0} {1} loaded" },
				{ Keys::kPluginNoMessaging, "SKSE gave no messaging interface; the mod can do nothing" },

				{ Keys::kVrikFound, "VRIK found, build {0}" },
				{ Keys::kVrikMissing, "VRIK not found: pouches need it for the places on the body" },
				{ Keys::kVrikTooOld, "VRIK build {0} is older than {1}: it has no pouch support, so the mod stays idle" },
				{ Keys::kVrikNoCallback, "VRIK refused the holster callback; the mod stays idle" },

				{ Keys::kHiggsFound, "HIGGS found, build {0}" },
				{ Keys::kHiggsMissing, "HIGGS not found: pouches need it to put a bottle in the hand" },

				{ Keys::kConfigWritten, "settings written to {0}" },
				{ Keys::kConfigRead, "settings read from {0}: {1} pouches" },
				{ Keys::kConfigBad, "settings at {0} could not be read ({1}); built-in defaults are used" },

				{ Keys::kPouchAssigned, "pouch {0} set up from what was put in it" },
				{ Keys::kPouchDrawn, "pouch {0} gave a bottle to the {1} hand" },
				{ Keys::kPouchStowed, "pouch {0} took back what the {1} hand held" },
				{ Keys::kPouchEmpty, "pouch {0} has nothing in the pack" },
				{ Keys::kPouchWrongItem, "pouch {0} does not hold that" },
				{ Keys::kPouchHandBusy, "the {0} hand is not free" },
				{ Keys::kPouchSuspended, "slot {0} suspended in VRIK" },
				{ Keys::kSlotSwitchedOn, "slot {0} was switched off in VRIK and has been switched on in memory - the ini on disk is not touched" },
				{ Keys::kPouchConsumed, "what came from pouch {0} was drunk" },
				{ Keys::kPouchReturned, "what came from pouch {0} went back to the pack" },
				{ Keys::kPouchLost, "what came from pouch {0} was dropped and is lying where it fell" },

				{ Keys::kItemNotFound, "{0}|{1:08X} is not in this load order" },
				{ Keys::kHandNotFound, "the {0} hand has no node to put a bottle at" },
				{ Keys::kDropFailed, "the game would not put the bottle into the world" },
			};
			return table;
		}

		std::map<std::string, std::string> g_table;
		std::string                        g_language{ "english" };

		void WriteOut(const std::filesystem::path& a_file)
		{
			std::error_code ec;
			std::filesystem::create_directories(a_file.parent_path(), ec);

			std::ofstream out(a_file, std::ios::binary);
			if (!out) {
				return;
			}
			out << "# Every line " << PLUGIN_NAME << " can put out, one per key.\n"
				<< "# Copy this file next to itself under another language name and translate the right side.\n"
				<< "# Placeholders are numbered - {0}, {1} - because another language puts the words in another order.\n\n";
			for (const auto& [key, text] : Builtin()) {
				out << key << " = " << text << "\n";
			}
		}

		std::string Trim(std::string_view a_text)
		{
			const auto first = a_text.find_first_not_of(" \t\r\n");
			if (first == std::string_view::npos) {
				return {};
			}
			const auto last = a_text.find_last_not_of(" \t\r\n");
			return std::string(a_text.substr(first, last - first + 1));
		}
	}

	void Loc::Load()
	{
		Load(Paths::LangDir(), g_language);
	}

	void Loc::Load(const std::filesystem::path& a_dir, const std::string& a_language)
	{
		g_table = Builtin();
		g_language = a_language.empty() ? "english" : a_language;

		// English is the built-in table; the file is written so that it can be read,
		// copied and translated, not because the mod needs to read it back.
		const auto english = a_dir / "english.txt";
		std::error_code ec;
		if (!std::filesystem::exists(english, ec)) {
			WriteOut(english);
		}

		const auto file = a_dir / (g_language + ".txt");
		std::ifstream in(file, std::ios::binary);
		if (!in) {
			return;
		}

		std::string line;
		while (std::getline(in, line)) {
			const auto trimmed = Trim(line);
			if (trimmed.empty() || trimmed.front() == '#') {
				continue;
			}
			const auto eq = trimmed.find('=');
			if (eq == std::string::npos) {
				continue;
			}
			auto key = Trim(std::string_view(trimmed).substr(0, eq));
			auto text = Trim(std::string_view(trimmed).substr(eq + 1));
			if (!key.empty() && !text.empty()) {
				g_table[std::move(key)] = std::move(text);
			}
		}
	}

	const char* Loc::Get(const char* a_key)
	{
		if (a_key == nullptr) {
			return "";
		}
		if (const auto it = g_table.find(a_key); it != g_table.end()) {
			return it->second.c_str();
		}
		// A key with no text is still better said than swallowed.
		return a_key;
	}

	const std::string& Loc::Language()
	{
		return g_language;
	}
}
