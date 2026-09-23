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
	inline constexpr auto kVrikSubscribed = "vrik.subscribed";
	inline constexpr auto kHiggsSubscribed = "higgs.subscribed";
	inline constexpr auto kConnectGaveUp = "connect.gave_up";

	// Settings
	inline constexpr auto kConfigWritten = "config.written";
	inline constexpr auto kConfigRead = "config.read";
	inline constexpr auto kConfigBad = "config.bad";
	inline constexpr auto kPouchConfigured = "config.pouch";
	inline constexpr auto kConfigToppedUp = "config.topped_up";
	inline constexpr auto kLangWritten = "lang.written";

	// The pouches at work
	inline constexpr auto kPouchAssigned = "pouch.assigned";
	inline constexpr auto kPouchDrawn = "pouch.drawn";
	inline constexpr auto kPouchStowed = "pouch.stowed";
	inline constexpr auto kPouchEmpty = "pouch.empty";
	inline constexpr auto kPouchWrongItem = "pouch.wrong_item";
	inline constexpr auto kPouchHandBusy = "pouch.hand_busy";
	inline constexpr auto kPouchSuspended = "pouch.suspended";
	inline constexpr auto kSuspendRefused = "pouch.suspend_refused";
	inline constexpr auto kSlotSwitchedOn = "slot.switched_on";
	inline constexpr auto kSlotOff = "slot.off";
	inline constexpr auto kPouchConsumed = "pouch.consumed";
	inline constexpr auto kPouchReturned = "pouch.returned";
	inline constexpr auto kPouchLost = "pouch.lost";

	// What the mod is doing. A log that says nothing cannot be told from a mod that was
	// never called, and telling those two apart is worth a few lines of its own.
	inline constexpr auto kGameLoaded = "game.loaded";
	inline constexpr auto kNotArranging = "game.not_arranging";
	inline constexpr auto kSlotSeen = "slot.seen";
	inline constexpr auto kHolsterOffered = "holster.offered";
	inline constexpr auto kDecision = "decide.result";
	inline constexpr auto kTaskQueued = "task.queued";
	inline constexpr auto kNoTasks = "task.no_interface";
	inline constexpr auto kDrawStart = "draw.start";
	inline constexpr auto kGrabAsked = "draw.grab_asked";
	inline constexpr auto kGrabConfirmed = "draw.grab_confirmed";
	inline constexpr auto kGrabFailed = "draw.grab_failed";
	inline constexpr auto kStowStart = "stow.start";
	inline constexpr auto kNothingHeld = "stow.nothing_held";
	inline constexpr auto kHeldNotPotion = "stow.not_a_potion";
	inline constexpr auto kHeldIs = "stow.held_is";
	inline constexpr auto kHeldNoBase = "stow.no_base";
	inline constexpr auto kHiggsEvent = "higgs.event";
	inline constexpr auto kSkseMessage = "skse.message";
	inline constexpr auto kReachChanged = "reach.changed";
	inline constexpr auto kSlotsLate = "slots.late";

	// The mechanic as it actually works: VRIK gives the place, HIGGS and the controller
	// give the moment. VRIK's own holster event never fires for anything but weapons.
	inline constexpr auto kInputWatch = "input.watch";
	inline constexpr auto kButtonAtPouch = "input.button_at_pouch";
	inline constexpr auto kButtonAtSlot = "input.button_at_slot";
	inline constexpr auto kButtonElsewhere = "input.button_elsewhere";
	inline constexpr auto kHandState = "input.hand_state";
	inline constexpr auto kHandedness = "game.handedness";
	inline constexpr auto kFrameAlive = "frame.alive";
	inline constexpr auto kGestureOffered = "gesture.offered";
	inline constexpr auto kGestureMade = "gesture.made";
	inline constexpr auto kGestureNowhere = "gesture.nowhere";
	inline constexpr auto kShown = "slot.shown";
	inline constexpr auto kShownNothing = "slot.shown_nothing";
	inline constexpr auto kDropAtPouch = "drop.at_pouch";
	inline constexpr auto kDropTaken = "drop.taken";
	inline constexpr auto kDropNotOurs = "drop.not_ours";
	inline constexpr auto kDropBounced = "drop.bounced";
	inline constexpr auto kIdleHere = "mod.idle_here";

	// Things that can go wrong at the boundary with the game
	inline constexpr auto kItemNotFound = "item.not_found";
	inline constexpr auto kHandNotFound = "hand.not_found";
	inline constexpr auto kHandNode = "hand.node";
	inline constexpr auto kDropFailed = "drop.failed";
}
