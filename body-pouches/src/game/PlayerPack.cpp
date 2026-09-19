#include "game/PlayerPack.h"

#include "game/Forms.h"

namespace BodyPouches::Game
{
	namespace
	{
		bool IsPotion(RE::TESBoundObject& a_object)
		{
			return a_object.Is(RE::FormType::AlchemyItem);
		}
	}

	std::vector<Core::Item> PlayerPack::Matching(const Core::Filter& a_filter) const
	{
		std::vector<Core::Item> matching;
		if (!a_filter.IsSet()) {
			return matching;
		}

		auto* player = RE::PlayerCharacter::GetSingleton();
		if (player == nullptr) {
			return matching;
		}

		for (auto& [object, entry] : player->GetInventory(IsPotion)) {
			const auto count = entry.first;
			if (count <= 0 || object == nullptr) {
				continue;
			}

			auto item = Describe(object->As<RE::AlchemyItem>());
			item.count = count;
			if (a_filter.Matches(item)) {
				matching.push_back(std::move(item));
			}
		}
		return matching;
	}

	RE::TESBoundObject* PlayerPack::Held(const Core::FormKey& a_key)
	{
		auto* form = Lookup(a_key);
		if (form == nullptr) {
			return nullptr;
		}

		auto* object = form->As<RE::TESBoundObject>();
		if (object == nullptr) {
			return nullptr;
		}

		auto* player = RE::PlayerCharacter::GetSingleton();
		if (player == nullptr || player->GetItemCount(object) <= 0) {
			return nullptr;
		}
		return object;
	}
}
