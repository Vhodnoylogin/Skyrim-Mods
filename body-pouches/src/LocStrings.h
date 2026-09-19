#pragma once

// Every line this mod can put out, by key.
//
// Not one sentence is written in the code: a line is a key, and the text behind it
// comes out of a file anybody may translate or reword. The keys are gathered here so
// that a line cannot be invented at the call site and then never translated.
//
// Placeholders are numbered - {0}, {1} - because another language puts the words in
// another order.

namespace BodyPouches::Keys
{
	// Loading and the two handshakes
	inline constexpr auto kPluginLoaded = "plugin.loaded";
	inline constexpr auto kPluginNoMessaging = "plugin.no_messaging";
	inline constexpr auto kVrikFound = "vrik.found";
	inline constexpr auto kVrikMissing = "vrik.missing";
	inline constexpr auto kVrikTooOld = "vrik.too_old";
	inline constexpr auto kVrikNoCallback = "vrik.no_callback";
	inline constexpr auto kHiggsFound = "higgs.found";
	inline constexpr auto kHiggsMissing = "higgs.missing";

	// Settings
	inline constexpr auto kConfigWritten = "config.written";
	inline constexpr auto kConfigRead = "config.read";
	inline constexpr auto kConfigBad = "config.bad";

	// The pouches at work
	inline constexpr auto kPouchAssigned = "pouch.assigned";
	inline constexpr auto kPouchDrawn = "pouch.drawn";
	inline constexpr auto kPouchStowed = "pouch.stowed";
	inline constexpr auto kPouchEmpty = "pouch.empty";
	inline constexpr auto kPouchWrongItem = "pouch.wrong_item";
	inline constexpr auto kPouchHandBusy = "pouch.hand_busy";
	inline constexpr auto kPouchSuspended = "pouch.suspended";
	inline constexpr auto kPouchConsumed = "pouch.consumed";
	inline constexpr auto kPouchReturned = "pouch.returned";
	inline constexpr auto kPouchLost = "pouch.lost";

	// Things that can go wrong at the boundary with the game
	inline constexpr auto kItemNotFound = "item.not_found";
	inline constexpr auto kHandNotFound = "hand.not_found";
	inline constexpr auto kDropFailed = "drop.failed";
}
