#pragma once

#include "core/Decision.h"
#include "core/Pack.h"
#include "core/Pouch.h"

#include <map>
#include <optional>
#include <vector>

namespace BodyPouches::Core
{
	// One reach for one slot, in the words VRIK uses when it calls.
	//
	// Note what is NOT here: what the hand is holding. VRIK's callback says only
	// whether the hand is occupied, and it wants its answer at once. So the fast
	// question - "does VRIK act, or do we?" - is answered from this alone. What a hand
	// lets go of at a pouch is another event and another question: Offer.
	struct Reach
	{
		int  slot{};
		bool leftHand{};
		bool handOccupied{};
		bool handCanHold{ true };  // HIGGS: CanGrabObject for that hand
	};

	// What should be drawn at a pouch right now. The count is what the pack holds: one
	// bottle is shown today, but the number is already honest, so the belt of several
	// bottles can be built on top without the core changing.
	struct Shown
	{
		bool    anything{};
		FormKey item{};
		int     count{};
	};

	// Every pouch the player has, and the rule that decides what happens when they
	// reach for one.
	//
	// This class is the mod. Everything else - the callbacks, the interfaces, the
	// placing of a bottle in the world - is machinery for carrying its answers out; it
	// holds no pointer into the game, opens no file and writes no message, so the whole
	// rule can be run through in a test in a millisecond and read by somebody who has
	// never seen Skyrim.
	class PouchSet
	{
	public:
		void Set(Pouch a_pouch);
		void Clear() noexcept;

		[[nodiscard]] const Pouch* Find(int a_slot) const noexcept;
		[[nodiscard]] Pouch*       Find(int a_slot) noexcept;
		[[nodiscard]] std::size_t  Size() const noexcept { return _pouches.size(); }

		// The fast answer, the one VRIK is waiting for.
		[[nodiscard]] Decision Decide(const Reach& a_reach, const Pack& a_pack) const;

		// A bottle let go of at a pouch, once the adapter has looked at what it is: put
		// it away here, set this pouch up with it, or none of our business.
		[[nodiscard]] Decision Offer(int a_slot, bool a_leftHand, const Item& a_item) const;

		// Carrying out an Act::Assign. Kept apart from Offer on purpose: deciding is a
		// question with an answer, assigning is a change, and mixing the two makes a
		// rule that cannot be asked twice.
		bool Assign(int a_slot, const Item& a_item);

		// What to draw at this pouch. Empty when there is nothing to show.
		[[nodiscard]] Shown Display(int a_slot, const Pack& a_pack) const;

		// Which pouch this hand took its bottle from, if it took one. The adapter
		// reports the three endings by hand - HIGGS says "the left hand drank" and not
		// which pouch it came from - so the hand is where that is remembered.
		void                     NoteDrawn(bool a_leftHand, int a_slot, FormKey a_item);
		void                     NoteSettled(bool a_leftHand) noexcept;
		[[nodiscard]] std::optional<int> SlotOfHand(bool a_leftHand) const noexcept;

	private:
		[[nodiscard]] static Decision Answer(int a_slot, bool a_leftHand, Act a_act, Reason a_reason, FormKey a_item = {});

		// Which of the matching kinds to hand over. Today: the first the pack names.
		// The rule the player will eventually want - fewest unrelated effects first, so
		// a rare multi-effect brew is not spent where a plain potion would do - belongs
		// here and nowhere else, and is deliberately not written yet.
		[[nodiscard]] static const Item* Choose(const std::vector<Item>& a_candidates);

		struct HandRecord
		{
			bool    holding{};
			int     slot{};
			FormKey item{};
		};

		std::map<int, Pouch> _pouches;
		HandRecord           _hands[2]{};  // [0] left, [1] right
	};
}
