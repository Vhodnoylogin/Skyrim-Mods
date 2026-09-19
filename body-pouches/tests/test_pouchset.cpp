#include "Harness.h"

#include "core/PouchSet.h"

using namespace BodyPouches::Core;

namespace
{
	constexpr int kHip = 3;
	constexpr int kChest = 7;

	ItemKey Healing() { return ItemKey{ "Skyrim.esm", 0x03EADE }; }
	ItemKey Sword() { return ItemKey{ "Skyrim.esm", 0x012EB7 }; }

	PouchSet WithHipPouch(Mode a_mode, int a_count, int a_capacity = 4)
	{
		PouchSet set;
		Pouch p(kHip, Healing(), ItemKind::Potion, a_capacity, a_mode);
		p.SetCount(a_count);
		set.Set(std::move(p));
		return set;
	}

	Reach EmptyHandAt(int a_slot)
	{
		Reach r;
		r.slot = a_slot;
		r.leftHand = true;
		r.handOccupied = false;
		return r;
	}

	Reach FullHandAt(int a_slot)
	{
		Reach r = EmptyHandAt(a_slot);
		r.handOccupied = true;
		return r;
	}
}

// The first rule and the most important one: a slot nobody configured is still
// VRIK's, and the answer VRIK gets back is the one that means "carry on".
TEST(a_slot_that_is_not_a_pouch_stays_with_vrik)
{
	const auto set = WithHipPouch(Mode::Shared, 4);
	const auto d = set.Decide(EmptyHandAt(kChest));
	CHECK(d.act == Act::PassToVrik);
	CHECK(d.LetVrikAct());
}

TEST(an_empty_hand_at_a_stocked_pouch_is_given_a_flask)
{
	const auto set = WithHipPouch(Mode::Shared, 4);
	const auto d = set.Decide(EmptyHandAt(kHip));
	CHECK(d.act == Act::Draw);
	CHECK(!d.LetVrikAct());
	CHECK(d.item == Healing());
	CHECK(d.leftHand);
}

// The difference between the two modes lives here, and nowhere else it matters as
// much: a shared slot that has run out steps aside so the sword in it still works,
// an exclusive one does not, because drawing a sword out of a potion pouch is a
// worse answer than drawing nothing.
TEST(an_empty_shared_pouch_steps_aside_and_an_exclusive_one_refuses)
{
	const auto shared = WithHipPouch(Mode::Shared, 0);
	CHECK(shared.Decide(EmptyHandAt(kHip)).act == Act::PassToVrik);

	const auto exclusive = WithHipPouch(Mode::Exclusive, 0);
	const auto d = exclusive.Decide(EmptyHandAt(kHip));
	CHECK(d.act == Act::Refuse);
	CHECK(d.reason == Reason::PouchEmpty);
	CHECK(!d.LetVrikAct());
}

// HIGGS can decline the hand for a frame. That is not the same as the pouch being
// empty: the event is still ours, and handing it to VRIK would draw a weapon
// instead of doing nothing.
TEST(a_hand_higgs_cannot_fill_gets_nothing_rather_than_a_sword)
{
	auto set = WithHipPouch(Mode::Shared, 4);
	Reach r = EmptyHandAt(kHip);
	r.handCanHold = false;

	const auto d = set.Decide(r);
	CHECK(d.act == Act::Refuse);
	CHECK(d.reason == Reason::HandUnavailable);
	CHECK(!d.LetVrikAct());
}

// A full hand is a reach to put something away. What exactly is in it, VRIK does
// not say, so the fast answer only claims the event; the offer decides.
TEST(a_full_hand_claims_the_event_and_the_offer_decides)
{
	const auto set = WithHipPouch(Mode::Shared, 1);

	const auto fast = set.Decide(FullHandAt(kHip));
	CHECK(fast.act == Act::Stow);
	CHECK(fast.reason == Reason::HandBusy);

	const auto good = set.OfferStow(kHip, Healing(), ItemKind::Potion);
	CHECK(good.act == Act::Stow);
	CHECK(good.reason == Reason::Stowed);

	// A sword offered to a shared potion pouch is VRIK's business after all.
	const auto wrong = set.OfferStow(kHip, Sword(), ItemKind::Other);
	CHECK(wrong.act == Act::PassToVrik);
	CHECK(wrong.reason == Reason::WrongItem);
}

// The same offer in an exclusive slot cannot fall through to VRIK: the slot is
// suspended there, so "pass to VRIK" would mean nothing happens at all, and a
// refusal that says so is the honest answer.
TEST(an_exclusive_pouch_refuses_the_wrong_item_instead_of_passing_it_on)
{
	const auto set = WithHipPouch(Mode::Exclusive, 1);
	const auto d = set.OfferStow(kHip, Sword(), ItemKind::Other);
	CHECK(d.act == Act::Refuse);
	CHECK(d.reason == Reason::WrongItem);
}

TEST(a_full_shared_pouch_lets_vrik_have_the_holster_back)
{
	auto set = WithHipPouch(Mode::Shared, 4, 4);
	const auto d = set.Decide(FullHandAt(kHip));
	CHECK(d.act == Act::PassToVrik);

	auto exclusive = WithHipPouch(Mode::Exclusive, 4, 4);
	const auto e = exclusive.Decide(FullHandAt(kHip));
	CHECK(e.act == Act::Refuse);
	CHECK(e.reason == Reason::PouchFull);
}

// Suspension is runtime state inside somebody else's mod, so we ask for exactly as
// much of it as the settings call for and not one slot more.
TEST(only_exclusive_pouches_are_asked_to_be_suspended)
{
	PouchSet set;
	Pouch shared(kHip, Healing(), ItemKind::Potion, 4, Mode::Shared);
	Pouch exclusive(kChest, Healing(), ItemKind::Potion, 4, Mode::Exclusive);
	set.Set(std::move(shared));
	set.Set(std::move(exclusive));

	const auto slots = set.SlotsToSuspend();
	CHECK_EQ(slots.size(), std::size_t{ 1 });
	CHECK_EQ(slots.front(), kChest);
}

TEST(a_pouch_with_no_item_configured_is_not_a_pouch_yet)
{
	PouchSet set;
	set.Set(Pouch(kHip, ItemKey{}, ItemKind::Unknown, 4, Mode::Exclusive));

	const auto d = set.Decide(EmptyHandAt(kHip));
	CHECK(d.act == Act::PassToVrik);
	CHECK(d.reason == Reason::NotOurs);
	CHECK(set.SlotsToSuspend().empty());
}
