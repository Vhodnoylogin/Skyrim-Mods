#include "Loc.h"

#include "Paths.h"

#include <algorithm>
#include <fstream>
#include <iterator>
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
				{ Keys::kVrikSubscribed, "VRIK took the holster callback: every reach for a slot now comes here first" },
				{ Keys::kHiggsSubscribed, "HIGGS took the consumed, stashed and dropped callbacks" },
				{ Keys::kConnectGaveUp, "the mod stays idle and nothing else will be logged: VRIK = {0}, HIGGS = {1}" },

				{ Keys::kConfigWritten, "settings written to {0}" },
				{ Keys::kConfigRead, "settings read from {0}: {1} pouches" },
				{ Keys::kPouchConfigured, "pouch on slot {0}, mode {1}" },
				{ Keys::kConfigToppedUp, "this build knows a setting \"{0}\" that {1} has no line for, so the file has been written out again with every setting in it and nothing that was in it changed" },
				{ Keys::kLangWritten, "{0} did not have a line for every message this build can put out, so it has been written out again" },
				{ Keys::kConfigBad, "settings at {0} could not be read ({1}); built-in defaults are used" },

				{ Keys::kPouchAssigned, "pouch {0} set up from what was put in it" },
				{ Keys::kPouchDrawn, "pouch {0} gave a bottle to the {1} hand" },
				{ Keys::kPouchStowed, "pouch {0} took back what the {1} hand held" },
				{ Keys::kPouchEmpty, "pouch {0} has nothing in the pack" },
				{ Keys::kPouchWrongItem, "pouch {0} does not hold that" },
				{ Keys::kPouchHandBusy, "the {0} hand is not free" },
				{ Keys::kPouchSuspended, "slot {0} suspended in VRIK" },
				{ Keys::kSuspendRefused, "VRIK would not suspend slot {0}: the pouch there cannot take the slot over" },
				{ Keys::kSlotSwitchedOn, "slot {0} was off in VRIK and has been switched on in memory because mayEnableSlots is set - VRIK's own files are not touched, but its menu will disagree with the game until you set it there too" },
				{ Keys::kSlotOff, "slot {0} allows no weapon type, so VRIK never looks at it and the pouch there cannot work. Allow any one weapon type for it in VRIK's MCM (the Weapon / Leg / Body / Arm Holsters pages), or set mayEnableSlots in bodypouches.json to let this mod do it" },
				{ Keys::kPouchConsumed, "what came from pouch {0} was drunk" },
				{ Keys::kPouchReturned, "what came from pouch {0} went back to the pack" },
				{ Keys::kPouchLost, "what came from pouch {0} was dropped and is lying where it fell" },

				{ Keys::kGameLoaded, "a game was loaded: arranging {0} pouches" },
				{ Keys::kNotArranging, "no pouches are arranged: VRIK ready = {0}, HIGGS ready = {1}" },
				{ Keys::kSlotSeen, "slot {0} as VRIK reads it: small={1} medium={2} large={3} ranged={4} shield={5} torch={6}, visible={7}, watched={8}" },
				{ Keys::kHolsterOffered, "VRIK offers slot {0}: secondaryHand = {1}, handOccupied = {2}" },
				{ Keys::kDecision, "slot {0}: act = {1}, reason = {2}, {3} hand, VRIK acts = {4}" },
				{ Keys::kTaskQueued, "slot {0}: the doing of it is queued for the game's next task" },
				{ Keys::kNoTasks, "slot {0}: SKSE gave no task interface, so nothing can be done" },
				{ Keys::kDrawStart, "slot {0}: drawing into the {1} hand" },
				{ Keys::kGrabAsked, "HIGGS asked to close the {0} hand on the bottle" },
				{ Keys::kGrabConfirmed, "the {0} hand closed on what pouch {1} gave it" },
				{ Keys::kGrabFailed, "the {0} hand never closed on what pouch {1} gave it - the bottle should be lying on the ground" },
				{ Keys::kStowStart, "slot {0}: the {1} hand offers what it holds" },
				{ Keys::kNothingHeld, "the {0} hand holds nothing HIGGS knows of" },
				{ Keys::kHeldNotPotion, "what the {0} hand holds is not a potion" },
				{ Keys::kHeldIs, "the {0} hand holds \"{1}\", form type {2}, form {3:08X}, reference {4:08X}" },
				{ Keys::kHeldNoBase, "what the {0} hand holds has no base object at all, reference {1:08X}" },
				{ Keys::kHiggsEvent, "HIGGS says {0}, {1} hand" },
				{ Keys::kSkseMessage, "SKSE message {0} (number {1}) from {2}, {3} bytes of data" },
				{ Keys::kReachChanged, "the {0} hand reaches slot {1} (VRIK would holster there: {2})" },
				{ Keys::kSlotsLate, "no load message ever arrived, so the slots are being arranged now, at the first reach" },
				{ Keys::kInputWatch, "watching the controllers: button {0} at a pouch takes a bottle out" },
				{ Keys::kButtonAtPouch, "the {0} hand pressed button {1} at slot {2}" },
				{ Keys::kButtonAtSlot, "the {0} hand pressed button {1} at slot {2}, which is not a pouch" },
				{ Keys::kButtonElsewhere, "the {0} hand pressed button {1}, away from every slot" },
				{ Keys::kHandState, "the {0} hand: HIGGS holds something = {1}, HIGGS could take something = {2}" },
				{ Keys::kHandedness, "bLeftHandedMode = {0}, so VRIK's secondary hand is read here as the {1} hand" },
				{ Keys::kFrameAlive, "HIGGS hands this mod the frame: both hands are read every one of them, and no thread of our own is needed" },
				{ Keys::kGestureOffered, "VRIK took an action of ours into its own gesture menu under the name \"{0}\" - bind it there to whichever gesture suits you" },
				{ Keys::kGestureMade, "the gesture came ({0} presses): the {1} hand is at slot {2} and free" },
				{ Keys::kGestureNowhere, "the gesture came ({0} presses), but no free hand is at a pouch" },
				{ Keys::kShown, "slot {0} now shows \"{1}\", {2} of them in the pack" },
				{ Keys::kShownNothing, "slot {0} shows nothing: the pack has none" },
				{ Keys::kDropAtPouch, "the {0} hand let go of something at slot {1}" },
				{ Keys::kDropTaken, "slot {0} took in what the {1} hand let go of, {2} of them" },
				{ Keys::kDropNotOurs, "what the {0} hand let go of at slot {1} does not belong in that pouch" },
				{ Keys::kDropBounced, "what the {0} hand let go of at slot {1} had come out of that very pouch {2} ms ago: the squeeze that draws is the squeeze that holds, so this is the same gesture ending and not a new one" },
				{ Keys::kIdleHere, "a reach came in while the mod is idle; VRIK keeps the slot" },

				{ Keys::kItemNotFound, "{0}|{1:08X} is not in this load order" },
				{ Keys::kHandNotFound, "the {0} hand has no node to put a bottle at" },
				{ Keys::kHandNode, "the {0} hand is at node {1}" },
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

		// Whether a file on disk still speaks for every key this binary knows. Cheap, done
		// once at load, and the only thing standing between a line changed in the code and
		// a run that goes on reading the old one out of a file nobody remembers writing.
		bool HasEveryKey(const std::filesystem::path& a_file)
		{
			std::ifstream in(a_file, std::ios::binary);
			if (!in) {
				return false;
			}

			std::map<std::string, bool> seen;
			std::string                 line;
			while (std::getline(in, line)) {
				const auto trimmed = Trim(line);
				const auto eq = trimmed.find('=');
				if (trimmed.empty() || trimmed.front() == '#' || eq == std::string::npos) {
					continue;
				}
				seen[Trim(std::string_view(trimmed).substr(0, eq))] = true;
			}

			for (const auto& [key, text] : Builtin()) {
				if (!seen.contains(key)) {
					return false;
				}
			}
			return true;
		}
	}

	void Loc::SetLevel(const std::string& a_level)
	{
		// An unreadable name must not silence the log: spdlog answers "off" for anything
		// it does not know, and a mod whose log is off by a typo cannot be diagnosed at
		// all. Only the word "off" itself is allowed to mean off.
		auto level = spdlog::level::from_str(a_level);
		if (level == spdlog::level::off && a_level != "off") {
			level = spdlog::level::info;
		}
		spdlog::set_level(level);
		spdlog::flush_on(level);
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
		// Written out when it is missing, and equally when it is older than the binary and
		// short of a line. It is read back as an override, so a file left behind by an
		// earlier build would go on speaking for every key it does have and silently hide
		// any wording changed since - and a translator copying it would never see the keys
		// added since either.
		const auto english = a_dir / "english.txt";
		std::error_code ec;
		if (!std::filesystem::exists(english, ec)) {
			WriteOut(english);
		} else if (!HasEveryKey(english)) {
			WriteOut(english);
			Say(spdlog::level::info, Keys::kLangWritten, english.string());
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
