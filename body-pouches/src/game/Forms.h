#pragma once

#include "core/Item.h"

#include <RE/Skyrim.h>

namespace BodyPouches::Game
{
	// The boundary between how the core names a thing and how the game does.
	//
	// The core speaks in plugin-and-local-id because that survives a load order being
	// reshuffled; the game speaks in pointers and in FormIDs that mean nothing tomorrow.
	// Both directions are here, in one place, so that the rest of the mod never has to
	// think about it.

	// A form's name as the core writes it. A form created at runtime belongs to no
	// plugin and gets an empty one - it can still be compared within a session, which
	// is all such a form is good for anyway.
	[[nodiscard]] Core::FormKey KeyOf(const RE::TESForm* a_form);

	// The form that key names in this load order, or nullptr if this load order has no
	// such thing - a pouch set up in another profile, say.
	[[nodiscard]] RE::TESForm* Lookup(const Core::FormKey& a_key);

	// One potion described the way the core wants to hear about it: what it is, what it
	// does, whether it is a poison. The count is left at zero; the pack fills it in.
	[[nodiscard]] Core::Item Describe(const RE::AlchemyItem* a_potion);
}
