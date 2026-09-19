#pragma once

#include "core/Pack.h"

#include <RE/Skyrim.h>

namespace BodyPouches::Game
{
	// The player's inventory, answering the core's one question.
	//
	// It keeps nothing. Every call walks the inventory afresh, because that is the whole
	// point of the design: the belt shows what is in the pack at this instant, and an
	// answer cached for even a second is an answer that can be wrong after a sale, a
	// theft or a load.
	//
	// Only potions are looked at. Food and ingredients are alchemy items too and will
	// belong here eventually, but nothing asks for them yet.
	class PlayerPack final : public Core::Pack
	{
	public:
		[[nodiscard]] std::vector<Core::Item> Matching(const Core::Filter& a_filter) const override;

		// The bound object behind a key, ready to be taken out of the inventory. Null
		// when this load order has no such form, or when the player has none of it.
		[[nodiscard]] static RE::TESBoundObject* Held(const Core::FormKey& a_key);
	};
}
