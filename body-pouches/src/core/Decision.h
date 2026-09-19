#pragma once

#include "core/ItemKey.h"

namespace BodyPouches::Core
{
	// What the core tells the mod to do about one reach for one slot.
	//
	// The names are the answer to the question VRIK actually asks. Its callback
	// wants a bool back - true "you do it, VRIK", false "I took this" - so every
	// act below has to be one or the other and nothing in between, and the mapping
	// is fixed here rather than argued about in the adapter:
	//
	//   PassToVrik -> true    everything else -> false
	enum class Act
	{
		PassToVrik,  // not our business: a sword in a holster is still VRIK's sword
		Draw,        // put our item in that hand
		Stow,        // the hand is full and the pouch will take what is in it
		Refuse       // ours, and nothing is to happen - an empty pouch, a hand that cannot hold
	};

	// Why the core decided so. Not a message and not a log line: a key, because
	// every line the mod puts out is looked up by key and translated. The core
	// names the reason, the layer above says it in the player's language.
	enum class Reason
	{
		NotOurs,
		Drawn,
		Stowed,
		PouchEmpty,
		PouchFull,
		WrongItem,
		HandBusy,
		HandUnavailable
	};

	struct Decision
	{
		Act      act{ Act::PassToVrik };
		Reason   reason{ Reason::NotOurs };
		int      slot{};       // the VRIK slot number this is about, 1..14
		bool     leftHand{};   // which hand reached
		ItemKey  item{};       // what to hand over, for Act::Draw

		// The single place where our vocabulary meets VRIK's callback contract.
		[[nodiscard]] bool LetVrikAct() const noexcept { return act == Act::PassToVrik; }
	};
}
