#include "Harness.h"

#include "core/Pouch.h"

using namespace BodyPouches::Core;

namespace
{
	ItemKey Healing() { return ItemKey{ "Skyrim.esm", 0x03EADE }; }
	ItemKey Stamina() { return ItemKey{ "Skyrim.esm", 0x039BE0 }; }

	Pouch FullOfHealing(int a_capacity = 4)
	{
		Pouch p(3, Healing(), ItemKind::Potion, a_capacity, Mode::Shared);
		p.SetCount(a_capacity);
		return p;
	}
}

// A flask in the hand has left the pouch but has not been spent: until one of the
// three endings arrives it is in neither place, and this is the arithmetic that
// keeps it from being counted twice or lost.
TEST(drawing_moves_a_flask_out_of_the_count_but_not_out_of_existence)
{
	auto p = FullOfHealing();
	CHECK_EQ(p.Count(), 4);

	p.Drawn();
	CHECK_EQ(p.Count(), 3);
	CHECK_EQ(p.Outstanding(), 1);

	p.PutBack();
	CHECK_EQ(p.Count(), 4);
	CHECK_EQ(p.Outstanding(), 0);
}

TEST(drinking_spends_the_flask_for_good)
{
	auto p = FullOfHealing();
	p.Drawn();
	p.Consumed();
	CHECK_EQ(p.Count(), 3);
	CHECK_EQ(p.Outstanding(), 0);
}

// The adapter is the one reporting these, and a mod that hears the same event
// twice is the normal state of affairs, not an exotic one. It must not invent
// flasks or push the count below nothing.
TEST(a_repeated_ending_changes_nothing)
{
	auto p = FullOfHealing(2);
	p.Drawn();
	p.Consumed();
	p.Consumed();
	p.PutBack();
	CHECK_EQ(p.Count(), 1);
	CHECK_EQ(p.Outstanding(), 0);
}

TEST(an_empty_pouch_gives_nothing_away)
{
	Pouch p(3, Healing(), ItemKind::Potion, 4, Mode::Shared);
	p.SetCount(0);
	p.Drawn();
	CHECK_EQ(p.Count(), 0);
	CHECK_EQ(p.Outstanding(), 0);
	CHECK(!p.HasSomethingToGive());
}

// Room has to count what is in the air as well: four flasks and a capacity of four
// means the pouch is full even while one of them is in a hand, or putting that one
// back would overflow it.
TEST(room_counts_the_flask_in_the_hand)
{
	auto p = FullOfHealing(4);
	CHECK(!p.HasRoom());
	p.Drawn();
	CHECK(!p.HasRoom());
	CHECK_EQ(p.Fill(10), 0);
	p.Consumed();
	CHECK(p.HasRoom());
	CHECK_EQ(p.Fill(10), 1);
	CHECK_EQ(p.Count(), 4);
}

TEST(a_pouch_takes_back_only_what_it_holds)
{
	auto p = FullOfHealing();
	CHECK(p.Accepts(Healing()));
	CHECK(!p.Accepts(Stamina()));
	CHECK(!p.Accepts(ItemKey{}));
}

// "Any plugin" is how a rule like "the healing potion, whichever mod it came from"
// is written. It is the only wildcard the core has, and it works one way only: a
// pouch may be vague about the source, an offered item may not.
TEST(an_empty_plugin_in_the_pouch_is_a_wildcard)
{
	Pouch p(3, ItemKey{ "", 0x03EADE }, ItemKind::Potion, 4, Mode::Shared);
	CHECK(p.Accepts(Healing()));
	CHECK(p.Accepts(ItemKey{ "Dawnguard.esm", 0x03EADE }));
	CHECK(!p.Accepts(ItemKey{ "Skyrim.esm", 0x000001 }));
}
