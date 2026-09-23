#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace BodyPouches::Core
{
	// A form, written the way a person writes it in the settings file: the plugin it
	// comes from and the id inside that plugin.
	//
	// THE CORE DELIBERATELY DOES NOT HOLD A FORM POINTER. A pointer is a thing of the
	// running game, and the whole point of this half is that it runs without one; and
	// a plugin's index in the load order changes between profiles, so a full FormID is
	// not a name for anything - it is only a name for today's load order. The pair
	// below survives a reorder, and turning it into a form is the job of the layer
	// that has the game in front of it.
	//
	// The same type names a potion and names a magic effect, because in the game both
	// are forms and a pouch has to be able to speak about either.
	struct FormKey
	{
		std::string   plugin;     // "Skyrim.esm"; empty means "any plugin"
		std::uint32_t localId{};  // 0x03EADE - the id inside that plugin, without the index

		[[nodiscard]] bool IsSet() const noexcept { return localId != 0; }

		[[nodiscard]] bool operator==(const FormKey& a_rhs) const noexcept
		{
			return localId == a_rhs.localId && plugin == a_rhs.plugin;
		}

		// "Any plugin" is a wildcard on the side that describes what is wanted, never
		// on the side that describes a thing that exists: a potion that does not know
		// where it came from is not something we could find again later.
		[[nodiscard]] bool Covers(const FormKey& a_thing) const noexcept
		{
			return IsSet() && a_thing.IsSet() && localId == a_thing.localId &&
			       (plugin.empty() || plugin == a_thing.plugin);
		}
	};

	// One kind of potion as it exists in the player's pack, described by the adapter
	// the moment it is asked about. The core never keeps one of these: it is a snapshot
	// of somebody else's inventory, and a snapshot kept is a snapshot that goes stale.
	struct Item
	{
		FormKey              key;
		std::vector<FormKey> effects;   // every magic effect on it, in the game's order
		bool                 harmful{}; // a poison: it goes on a blade, it is not drunk
		int                  count{};   // how many are in the pack right now

		// The largest magnitude among its effects, as the game states it. Not a judgement
		// of worth and not comparable between unlike potions - only enough to tell the
		// small bottle of a kind from the large one, so that the small one is spent first.
		float                strength{};
	};
}
