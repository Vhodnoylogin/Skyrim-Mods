#pragma once

#include <cstdint>
#include <string>

namespace BodyPouches::Core
{
	// What a pouch is told to hold, written the way a person writes it in the
	// settings file: the plugin it comes from and the id inside that plugin.
	//
	// THE CORE DELIBERATELY DOES NOT HOLD A FORM POINTER. A pointer is a thing of
	// the running game, and the whole point of this half is that it runs without
	// one; and a plugin's index in the load order changes between profiles, so a
	// full FormID is not a name for anything - it is only a name for today's load
	// order. The pair below survives a reorder, and turning it into a form is the
	// job of the layer that has the game in front of it.
	struct ItemKey
	{
		std::string   plugin;   // "Skyrim.esm"; empty means "any plugin", used by rules
		std::uint32_t localId{};  // 0x03EADE - the last three bytes, without the index

		[[nodiscard]] bool IsSet() const noexcept { return localId != 0; }

		[[nodiscard]] bool operator==(const ItemKey& a_rhs) const noexcept
		{
			return localId == a_rhs.localId && plugin == a_rhs.plugin;
		}
	};

	// What kind of thing a pouch holds. The core needs this for one decision only -
	// whether taking the item ends with the hand full or with the item gone - and
	// it is the adapter's business to work the kind out from the game's own record.
	enum class ItemKind
	{
		Unknown,
		Potion,       // drunk from the hand; HIGGS reports it consumed
		Food,         // the same, and the core does not distinguish it
		Ingredient,   // eaten as well, but a stack is spent one at a time
		Throwable,    // leaves the hand and does not come back
		Other
	};
}
