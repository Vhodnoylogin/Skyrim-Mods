#pragma once

#include "core/Decision.h"
#include "core/Pouch.h"

#include <map>
#include <vector>

namespace BodyPouches::Core
{
	// One reach for one slot, in the words VRIK uses when it calls.
	//
	// Note what is NOT here: what the hand is holding. VRIK's callback says only
	// whether the hand is occupied, and it wants its answer at once. So the fast
	// question - "does VRIK act, or do we?" - is answered from this alone, and the
	// slower question of whether what is in the hand may go into this pouch is asked
	// afterwards, by OfferStow, when the adapter has looked at the hand.
	struct Reach
	{
		int  slot{};
		bool leftHand{};
		bool handOccupied{};
		bool handCanHold{ true };  // HIGGS: CanGrabObject for that hand
	};

	// Every pouch the player has, and the rule that decides what happens when they
	// reach for one.
	//
	// This class is the mod. Everything else - the callbacks, the interfaces, the
	// placing of a flask in the world - is machinery for carrying its answers out;
	// it holds no pointer into the game, opens no file and writes no message, so
	// the whole rule can be run through in a test in a millisecond and read by
	// somebody who has never seen Skyrim.
	class PouchSet
	{
	public:
		void Set(Pouch a_pouch);
		void Clear() noexcept { _pouches.clear(); }

		[[nodiscard]] const Pouch* Find(int a_slot) const noexcept;
		[[nodiscard]] Pouch*       Find(int a_slot) noexcept;
		[[nodiscard]] std::size_t  Size() const noexcept { return _pouches.size(); }

		// The slots the adapter must suspend in VRIK, and only those: suspension is
		// runtime-only state in somebody else's mod, so we ask for as little of it
		// as the settings actually call for.
		[[nodiscard]] std::vector<int> SlotsToSuspend() const;

		// The fast answer, the one VRIK is waiting for.
		[[nodiscard]] Decision Decide(const Reach& a_reach) const;

		// The slow half of a reach with a full hand: now that the adapter knows what
		// is in it, may it go into that pouch?
		[[nodiscard]] Decision OfferStow(int a_slot, const ItemKey& a_item, ItemKind a_kind) const;

	private:
		[[nodiscard]] static Decision Answer(const Reach& a_reach, Act a_act, Reason a_reason, ItemKey a_item = {});

		std::map<int, Pouch> _pouches;
	};
}
