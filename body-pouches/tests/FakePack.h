#pragma once

#include "core/Pack.h"

// A pack made of a list, so that the rule can be asked questions without a game.
// It answers exactly the way the real adapter will: it filters what it holds and
// reports counts, and it keeps nothing of its own.
class FakePack final : public BodyPouches::Core::Pack
{
public:
	void Put(BodyPouches::Core::Item a_item) { _items.push_back(std::move(a_item)); }

	[[nodiscard]] std::vector<BodyPouches::Core::Item> Matching(
		const BodyPouches::Core::Filter& a_filter) const override
	{
		std::vector<BodyPouches::Core::Item> out;
		for (const auto& item : _items) {
			if (item.count > 0 && a_filter.Matches(item)) {
				out.push_back(item);
			}
		}
		return out;
	}

private:
	std::vector<BodyPouches::Core::Item> _items;
};
