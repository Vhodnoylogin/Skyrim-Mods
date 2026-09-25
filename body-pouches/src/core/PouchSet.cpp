#include "core/PouchSet.h"

namespace BodyPouches::Core
{
	namespace
	{
		// Which of two matching potions is the one to spend. Read as "less precious".
		bool Cheaper(const Item& a_lhs, const Item& a_rhs)
		{
			// Fewest effects first: a plain healing potion before a brew that also restores
			// magicka and cures disease, because the brew is good for errands this one is
			// not and spending it here throws the rest of it away.
			if (a_lhs.effects.size() != a_rhs.effects.size()) {
				return a_lhs.effects.size() < a_rhs.effects.size();
			}
			// Then the weaker of the two.
			if (a_lhs.strength != a_rhs.strength) {
				return a_lhs.strength < a_rhs.strength;
			}
			// Then by name, for no reason except that there has to be one: two potions
			// alike in every way above must still come out in the same order every time.
			if (a_lhs.key.plugin != a_rhs.key.plugin) {
				return a_lhs.key.plugin < a_rhs.key.plugin;
			}
			return a_lhs.key.localId < a_rhs.key.localId;
		}
	}

	void PouchSet::Set(Pouch a_pouch)
	{
		if (a_pouch.Slot() > 0) {
			_pouches.insert_or_assign(a_pouch.Slot(), std::move(a_pouch));
		}
	}

	void PouchSet::Clear() noexcept
	{
		_pouches.clear();
		_hands[0] = {};
		_hands[1] = {};
	}

	const Pouch* PouchSet::Find(int a_slot) const noexcept
	{
		const auto it = _pouches.find(a_slot);
		return it == _pouches.end() ? nullptr : &it->second;
	}

	Pouch* PouchSet::Find(int a_slot) noexcept
	{
		const auto it = _pouches.find(a_slot);
		return it == _pouches.end() ? nullptr : &it->second;
	}

	Decision PouchSet::Answer(int a_slot, bool a_leftHand, Act a_act, Reason a_reason, FormKey a_item)
	{
		Decision d;
		d.act = a_act;
		d.reason = a_reason;
		d.slot = a_slot;
		d.leftHand = a_leftHand;
		d.item = std::move(a_item);
		return d;
	}

	const Item* PouchSet::Choose(const std::vector<Item>& a_candidates)
	{
		// WHY THIS IS NOT SIMPLY THE FIRST ONE. The pack answers in an order of its own,
		// and in the game that order is a map keyed by where the form happens to sit in
		// memory - so "the first" is a different bottle on a different day and no rule at
		// all. Twelve healing potions in the pack would hand over whichever one, and the
		// player would rightly call that a fault. Something has to be picked on purpose,
		// and the purpose is to spend nothing rarer than the errand needs: see Cheaper.
		const Item* best = nullptr;
		for (const auto& item : a_candidates) {
			if (item.count > 0 && (best == nullptr || Cheaper(item, *best))) {
				best = &item;
			}
		}
		return best;
	}

	Decision PouchSet::Decide(const Reach& a_reach, const Pack& a_pack) const
	{
		const Pouch* pouch = Find(a_reach.slot);
		const bool   exclusive = pouch != nullptr && pouch->PouchMode() == Mode::Exclusive;

		// Not a pouch at all: VRIK was here first and this is still its slot.
		if (pouch == nullptr) {
			return Answer(a_reach.slot, a_reach.leftHand, Act::PassToVrik, Reason::NotOurs);
		}

		// A FULL HAND IS NEVER PUTTING SOMETHING IN, NOT FROM HERE. VRIK raises a reach
		// for a hand holding a thing when that hand leaves the pouch with its grip still
		// closed - which is a hand carrying its bottle away. Run 7 read it the other way
		// and put back every bottle the moment it came out. A bottle goes in when the
		// hand lets go of it inside the pouch; that is HIGGS's event and Offer's question.
		// An exclusive pouch keeps the reach to itself so that nothing of VRIK's happens
		// either; a shared one leaves it to VRIK, whose slot it also is.
		if (a_reach.handOccupied) {
			return exclusive
				? Answer(a_reach.slot, a_reach.leftHand, Act::Refuse, Reason::CarriedAway)
				: Answer(a_reach.slot, a_reach.leftHand, Act::PassToVrik, Reason::CarriedAway);
		}

		// A pouch nobody has set up yet has nothing to give, so the slot goes on working
		// as VRIK's. It is set up by letting go of a bottle in it - see Offer.
		if (!pouch->IsAssigned()) {
			return Answer(a_reach.slot, a_reach.leftHand, Act::PassToVrik, Reason::NotAssigned);
		}

		const auto  candidates = a_pack.Matching(pouch->PouchFilter());
		const Item* chosen = Choose(candidates);

		// Set up, but the pack has run out. A shared slot steps aside so that whatever
		// VRIK keeps there still works; an exclusive one does not, because the player
		// set that slot aside for this and a sword coming out of it would be a surprise.
		if (chosen == nullptr) {
			return exclusive
				? Answer(a_reach.slot, a_reach.leftHand, Act::Refuse, Reason::NothingInPack)
				: Answer(a_reach.slot, a_reach.leftHand, Act::PassToVrik, Reason::NothingInPack);
		}

		// There is something to give and a hand to give it to - but HIGGS may be unable
		// to take it this frame. Refusing is right and passing to VRIK is not: the pouch
		// is not empty, and VRIK drawing a weapon here instead would be the wrong thing
		// happening rather than nothing happening.
		if (!a_reach.handCanHold) {
			return Answer(a_reach.slot, a_reach.leftHand, Act::Refuse, Reason::HandUnavailable);
		}

		return Answer(a_reach.slot, a_reach.leftHand, Act::Draw, Reason::Drawn, chosen->key);
	}

	Decision PouchSet::Offer(int a_slot, bool a_leftHand, const Item& a_item) const
	{
		const Pouch* pouch = Find(a_slot);
		if (pouch == nullptr) {
			return Answer(a_slot, a_leftHand, Act::PassToVrik, Reason::NotOurs);
		}

		if (!pouch->IsAssigned()) {
			// Setting up by hand. A poison is turned away here as everywhere else: a
			// pouch that would never hand its contents back is not a pouch.
			return a_item.harmful
				? Answer(a_slot, a_leftHand, Act::Refuse, Reason::WrongItem)
				: Answer(a_slot, a_leftHand, Act::Assign, Reason::Assigned, a_item.key);
		}

		if (!pouch->PouchFilter().Matches(a_item)) {
			// In a shared slot the wrong item is VRIK's business after all - let it
			// holster the sword as it always did. In an exclusive one the slot is
			// suspended, so passing it on would mean nothing happens at all, and saying
			// no out loud is the honest answer.
			return pouch->PouchMode() == Mode::Exclusive
				? Answer(a_slot, a_leftHand, Act::Refuse, Reason::WrongItem)
				: Answer(a_slot, a_leftHand, Act::PassToVrik, Reason::WrongItem);
		}

		return Answer(a_slot, a_leftHand, Act::Stow, Reason::Stowed, a_item.key);
	}

	bool PouchSet::Assign(int a_slot, const Item& a_item)
	{
		Pouch* pouch = Find(a_slot);
		if (pouch == nullptr || pouch->IsAssigned() || a_item.harmful) {
			return false;
		}
		pouch->Assign(Filter::FromItem(a_item));
		return true;
	}

	Shown PouchSet::Display(int a_slot, const Pack& a_pack) const
	{
		Shown shown;
		const Pouch* pouch = Find(a_slot);
		if (pouch == nullptr || !pouch->IsAssigned()) {
			return shown;
		}

		const auto candidates = a_pack.Matching(pouch->PouchFilter());
		for (const auto& item : candidates) {
			shown.count += item.count;
		}
		if (const Item* chosen = Choose(candidates); chosen != nullptr) {
			shown.anything = true;
			shown.item = chosen->key;
		}
		return shown;
	}

	void PouchSet::NoteDrawn(bool a_leftHand, int a_slot, FormKey a_item)
	{
		auto& hand = _hands[a_leftHand ? 0 : 1];
		hand.holding = true;
		hand.slot = a_slot;
		hand.item = std::move(a_item);
	}

	void PouchSet::NoteSettled(bool a_leftHand) noexcept
	{
		_hands[a_leftHand ? 0 : 1] = {};
	}

	std::optional<int> PouchSet::SlotOfHand(bool a_leftHand) const noexcept
	{
		const auto& hand = _hands[a_leftHand ? 0 : 1];
		return hand.holding ? std::optional<int>{ hand.slot } : std::nullopt;
	}
}
