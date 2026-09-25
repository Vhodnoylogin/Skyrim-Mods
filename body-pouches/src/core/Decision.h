#pragma once

#include "core/Item.h"

namespace BodyPouches::Core
{
	// What the core tells the mod to do about one reach for one slot.
	//
	// The names are the answer to the question VRIK actually asks. Its callback wants a
	// bool back - true "you do it, VRIK", false "I took this" - so every act below has
	// to be one or the other and nothing in between, and the mapping is fixed here
	// rather than argued about in the adapter:
	//
	//   PassToVrik -> true    everything else -> false
	enum class Act
	{
		PassToVrik,  // not our business: a sword in a holster is still VRIK's sword
		Draw,        // put the named item in that hand
		Stow,        // the hand is full and the pouch will take what is in it
		Assign,      // an empty unassigned pouch is being set up by hand
		Refuse       // ours, and nothing is to happen
	};

	// Why the core decided so. Not a message and not a log line: a key, because every
	// line the mod puts out is looked up by key and translated. The core names the
	// reason, the layer above says it in the player's language.
	enum class Reason
	{
		NotOurs,
		Drawn,
		Stowed,
		Assigned,
		NothingInPack,   // the pouch is set up, the pack has run out
		NotAssigned,     // the pouch has never been told what it is for
		WrongItem,
		CarriedAway,     // a full hand leaving the pouch: it takes its bottle along
		HandUnavailable
	};

	// The names of the two vocabularies above, for the log and for nothing else. They
	// are identifiers, not sentences: a line that says what the core decided is looked
	// up by key and translated like every other, and these fill its placeholders the
	// way a slot number does.
	[[nodiscard]] constexpr const char* Name(Act a_act) noexcept
	{
		switch (a_act) {
		case Act::PassToVrik: return "pass-to-vrik";
		case Act::Draw:       return "draw";
		case Act::Stow:       return "stow";
		case Act::Assign:     return "assign";
		case Act::Refuse:     return "refuse";
		default:              return "?";
		}
	}

	[[nodiscard]] constexpr const char* Name(Reason a_reason) noexcept
	{
		switch (a_reason) {
		case Reason::NotOurs:         return "not-ours";
		case Reason::Drawn:           return "drawn";
		case Reason::Stowed:          return "stowed";
		case Reason::Assigned:        return "assigned";
		case Reason::NothingInPack:   return "nothing-in-pack";
		case Reason::NotAssigned:     return "not-assigned";
		case Reason::WrongItem:       return "wrong-item";
		case Reason::CarriedAway:     return "carried-away";
		case Reason::HandUnavailable: return "hand-unavailable";
		default:                      return "?";
		}
	}

	struct Decision
	{
		Act     act{ Act::PassToVrik };
		Reason  reason{ Reason::NotOurs };
		int     slot{};      // the VRIK slot number this is about, 1..14
		bool    leftHand{};  // which hand reached
		FormKey item{};      // what to hand over, for Act::Draw

		// The single place where our vocabulary meets VRIK's callback contract.
		[[nodiscard]] bool LetVrikAct() const noexcept { return act == Act::PassToVrik; }
	};
}
