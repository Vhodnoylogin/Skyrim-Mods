#include "core/PouchSet.h"

namespace BodyPouches::Core
{
	void PouchSet::Set(Pouch a_pouch)
	{
		if (a_pouch.Slot() > 0) {
			_pouches.insert_or_assign(a_pouch.Slot(), std::move(a_pouch));
		}
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

	std::vector<int> PouchSet::SlotsToSuspend() const
	{
		std::vector<int> slots;
		for (const auto& [slot, pouch] : _pouches) {
			if (pouch.IsConfigured() && pouch.PouchMode() == Mode::Exclusive) {
				slots.push_back(slot);
			}
		}
		return slots;
	}

	Decision PouchSet::Answer(const Reach& a_reach, Act a_act, Reason a_reason, ItemKey a_item)
	{
		Decision d;
		d.act = a_act;
		d.reason = a_reason;
		d.slot = a_reach.slot;
		d.leftHand = a_reach.leftHand;
		d.item = std::move(a_item);
		return d;
	}

	Decision PouchSet::Decide(const Reach& a_reach) const
	{
		const Pouch* pouch = Find(a_reach.slot);

		// Not a pouch at all, or a pouch nobody has filled in: VRIK was here first
		// and this is still its slot.
		if (pouch == nullptr || !pouch->IsConfigured()) {
			return Answer(a_reach, Act::PassToVrik, Reason::NotOurs);
		}

		const bool exclusive = pouch->PouchMode() == Mode::Exclusive;

		// A full hand is a reach to put something away, not to take something out.
		// We cannot yet say whether it belongs here - that is OfferStow's question -
		// but we can already say whose event it is, and for a shared slot with no
		// room it is VRIK's: let it holster the sword as it always did.
		if (a_reach.handOccupied) {
			if (!pouch->HasRoom()) {
				return exclusive
					? Answer(a_reach, Act::Refuse, Reason::PouchFull)
					: Answer(a_reach, Act::PassToVrik, Reason::NotOurs);
			}
			return Answer(a_reach, Act::Stow, Reason::HandBusy);
		}

		// An empty hand reaching for an empty pouch. In a shared slot we step aside
		// so that whatever VRIK keeps there still works; in an exclusive one we do
		// not, because the player set that slot aside for this and a sword coming
		// out of it would be a surprise.
		if (!pouch->HasSomethingToGive()) {
			return exclusive
				? Answer(a_reach, Act::Refuse, Reason::PouchEmpty)
				: Answer(a_reach, Act::PassToVrik, Reason::NotOurs);
		}

		// There is something to give and a hand to give it to - but HIGGS may be
		// unable to take it this frame. Refusing is right and passing to VRIK is
		// not: the pouch is not empty, and VRIK drawing a weapon here instead would
		// be the wrong thing happening rather than nothing happening.
		if (!a_reach.handCanHold) {
			return Answer(a_reach, Act::Refuse, Reason::HandUnavailable);
		}

		return Answer(a_reach, Act::Draw, Reason::Drawn, pouch->Item());
	}

	Decision PouchSet::OfferStow(int a_slot, const ItemKey& a_item, ItemKind a_kind) const
	{
		Reach reach;
		reach.slot = a_slot;
		reach.handOccupied = true;

		const Pouch* pouch = Find(a_slot);
		if (pouch == nullptr || !pouch->IsConfigured()) {
			return Answer(reach, Act::PassToVrik, Reason::NotOurs);
		}
		if (!pouch->Accepts(a_item)) {
			// The kind is carried for the log and for the adapter's own use; the
			// pouch decides by identity, because "a potion" is not a thing a player
			// puts in a pouch - a particular potion is.
			(void)a_kind;
			return pouch->PouchMode() == Mode::Exclusive
				? Answer(reach, Act::Refuse, Reason::WrongItem)
				: Answer(reach, Act::PassToVrik, Reason::WrongItem);
		}
		if (!pouch->HasRoom()) {
			return Answer(reach, Act::Refuse, Reason::PouchFull);
		}
		return Answer(reach, Act::Stow, Reason::Stowed, a_item);
	}
}
