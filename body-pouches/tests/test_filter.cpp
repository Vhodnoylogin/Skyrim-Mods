#include "Harness.h"

#include "core/Filter.h"

using namespace BodyPouches::Core;

namespace
{
	const FormKey kRestoreHealth{ "Skyrim.esm", 0x03EAF3 };
	const FormKey kRestoreMagicka{ "Skyrim.esm", 0x03EAF4 };
	const FormKey kInvisibility{ "Skyrim.esm", 0x0AA00E };

	Item Potion(FormKey a_key, std::vector<FormKey> a_effects, int a_count = 1, bool a_harmful = false)
	{
		Item item;
		item.key = std::move(a_key);
		item.effects = std::move(a_effects);
		item.count = a_count;
		item.harmful = a_harmful;
		return item;
	}
}

// The point of a filter written in effects rather than in forms: one shop-bought
// bottle teaches the pouch to accept every other bottle that does the same thing,
// including the ones brewed at a table and the ones some mod added.
TEST(a_filter_made_from_one_bottle_accepts_every_bottle_that_does_the_same)
{
	const auto minor = Potion({ "Skyrim.esm", 0x03EADE }, { kRestoreHealth });
	const auto filter = Filter::FromItem(minor);

	CHECK(filter.Matches(minor));
	CHECK(filter.Matches(Potion({ "Skyrim.esm", 0x03EADF }, { kRestoreHealth })));   // stronger
	CHECK(filter.Matches(Potion({ "Dragonborn.esm", 0x01F2A3 }, { kRestoreHealth })));  // from a DLC
	CHECK(!filter.Matches(Potion({ "Skyrim.esm", 0x039BE0 }, { kRestoreMagicka })));
}

// A brew of two effects really is good for either purpose, so it belongs in both
// pouches. Nothing special is done about it - that is the answer.
TEST(a_potion_of_two_effects_belongs_in_both_pouches)
{
	Filter health;
	health.effects = { kRestoreHealth };
	Filter magicka;
	magicka.effects = { kRestoreMagicka };

	const auto both = Potion({ "", 0x800123 }, { kRestoreHealth, kRestoreMagicka });
	CHECK(health.Matches(both));
	CHECK(magicka.Matches(both));
}

// A poison goes on a blade, not to the mouth. A pouch that handed one over would be
// making a mistake on the player's behalf.
TEST(no_filter_ever_accepts_a_poison)
{
	const auto poison = Potion({ "Skyrim.esm", 0x0341A2 }, { kRestoreHealth }, 1, true);

	Filter byEffect;
	byEffect.effects = { kRestoreHealth };
	CHECK(!byEffect.Matches(poison));

	Filter byForm;
	byForm.exact = poison.key;
	CHECK(!byForm.Matches(poison));
}

TEST(an_exact_filter_takes_that_bottle_and_no_other)
{
	Filter filter;
	filter.exact = FormKey{ "Skyrim.esm", 0x03EADE };

	CHECK(filter.Matches(Potion({ "Skyrim.esm", 0x03EADE }, { kRestoreHealth })));
	CHECK(!filter.Matches(Potion({ "Skyrim.esm", 0x03EADF }, { kRestoreHealth })));
}

// The wildcard works one way only: a pouch may be vague about which plugin a potion
// comes from, a potion may not.
TEST(an_empty_plugin_is_a_wildcard_on_the_asking_side_only)
{
	Filter anyPlugin;
	anyPlugin.effects = { FormKey{ "", 0x03EAF3 } };
	CHECK(anyPlugin.Matches(Potion({ "Skyrim.esm", 0x03EADE }, { kRestoreHealth })));

	Filter named;
	named.effects = { kRestoreHealth };
	CHECK(!named.Matches(Potion({ "Skyrim.esm", 0x03EADE }, { FormKey{ "", 0x03EAF3 } })));
}

// A potion with no effects at all cannot teach a pouch what it is for, so setting up
// with one falls back to naming that exact bottle.
TEST(a_bottle_with_no_effects_sets_the_pouch_up_by_form)
{
	const auto odd = Potion({ "SomeMod.esp", 0x000800 }, {});
	const auto filter = Filter::FromItem(odd);

	CHECK(filter.exact == odd.key);
	CHECK(filter.effects.empty());
	CHECK(filter.Matches(odd));
}

TEST(an_unset_filter_matches_nothing)
{
	const Filter empty;
	CHECK(!empty.IsSet());
	CHECK(!empty.Matches(Potion({ "Skyrim.esm", 0x03EADE }, { kRestoreHealth })));
	CHECK(!empty.Matches(Potion({ "", 0 }, {})));
}

TEST(invisibility_is_nothing_special_to_a_pouch)
{
	const auto brew = Potion({ "Skyrim.esm", 0x03EB05 }, { kInvisibility });
	const auto filter = Filter::FromItem(brew);
	CHECK(filter.Matches(brew));
	CHECK(!filter.Matches(Potion({ "Skyrim.esm", 0x03EADE }, { kRestoreHealth })));
}
