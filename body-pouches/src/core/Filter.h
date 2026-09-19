#pragma once

#include "core/Item.h"

namespace BodyPouches::Core
{
	// What a pouch is for.
	//
	// A pouch does not hold potions - it holds this. The potions are in the pack, and
	// the pouch is only a standing question put to it: "anything like this?"
	//
	// TWO WAYS TO ASK, AND THE SECOND IS THE ONE THAT MATTERS. `exact` names one
	// particular potion and nothing else. `effects` names what the potion must DO: a
	// potion matches if any of these effects is among its own. That is what makes a
	// pouch set up with a shop-bought Potion of Minor Healing also accept the stronger
	// one, and the twelve home-brewed ones, and a healing potion added by some mod
	// nobody has heard of - because all of them restore health, and the pouch was told
	// to hold "restores health", not "this bottle".
	//
	// It also answers the question of what to do about a potion with several effects:
	// nothing special. A brew of healing and magicka has both effects, so it belongs in
	// both pouches. The pack is one pack, and it really is good for either.
	struct Filter
	{
		FormKey              exact;    // if set, only this form
		std::vector<FormKey> effects;  // otherwise, any potion doing any of these

		[[nodiscard]] bool IsSet() const noexcept { return exact.IsSet() || !effects.empty(); }

		[[nodiscard]] bool Matches(const Item& a_item) const noexcept
		{
			// Poisons are never drawn from a pouch. In this game a poison is put on a
			// blade rather than drunk, so handing one to a hand about to go to the
			// mouth would be a mistake we made, not a choice the player made.
			if (a_item.harmful) {
				return false;
			}
			if (exact.IsSet()) {
				return exact.Covers(a_item.key);
			}
			for (const auto& wanted : effects) {
				for (const auto& has : a_item.effects) {
					if (wanted.Covers(has)) {
						return true;
					}
				}
			}
			return false;
		}

		// Setting a pouch up by hand: a bottle is pushed into an empty slot and the
		// pouch takes its meaning from it. What is written down is deliberately NOT
		// that bottle but what that bottle does - see the note above. A potion with no
		// effects at all (there are a few) leaves the exact form as the only thing we
		// can honestly say.
		static Filter FromItem(const Item& a_item)
		{
			Filter f;
			if (a_item.effects.empty()) {
				f.exact = a_item.key;
			} else {
				f.effects = a_item.effects;
			}
			return f;
		}
	};
}
