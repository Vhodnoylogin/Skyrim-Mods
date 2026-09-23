#include "game/Forms.h"

#include <algorithm>

namespace BodyPouches::Game
{
	Core::FormKey KeyOf(const RE::TESForm* a_form)
	{
		Core::FormKey key;
		if (a_form == nullptr) {
			return key;
		}

		key.localId = a_form->GetLocalFormID();
		if (const auto* file = a_form->GetFile(0); file != nullptr) {
			key.plugin = file->GetFilename();
		}
		return key;
	}

	RE::TESForm* Lookup(const Core::FormKey& a_key)
	{
		if (!a_key.IsSet()) {
			return nullptr;
		}

		auto* data = RE::TESDataHandler::GetSingleton();
		if (data == nullptr) {
			return nullptr;
		}
		if (!a_key.plugin.empty()) {
			return data->LookupForm(a_key.localId, a_key.plugin);
		}

		// No plugin named: the id can only be read as a whole FormID, which is what a
		// runtime-created form has. Anything else would be a guess at a load order.
		return RE::TESForm::LookupByID(a_key.localId);
	}

	Core::Item Describe(const RE::AlchemyItem* a_potion)
	{
		Core::Item item;
		if (a_potion == nullptr) {
			return item;
		}

		item.key = KeyOf(a_potion);
		item.harmful = const_cast<RE::AlchemyItem*>(a_potion)->IsPoison();

		for (const auto* effect : a_potion->effects) {
			if (effect != nullptr && effect->baseEffect != nullptr) {
				item.effects.push_back(KeyOf(effect->baseEffect));
				// The strongest thing it does, which is as close to "how big a bottle is
				// this" as the game will say without being asked about a particular effect.
				item.strength = std::max(item.strength, effect->GetMagnitude());
			}
		}
		return item;
	}
}
