#include "FakePack.h"
#include "Harness.h"

#include "core/PouchSet.h"

using namespace BodyPouches::Core;

namespace
{
	constexpr int kHip = 1;
	constexpr int kChest = 14;

	const FormKey kRestoreHealth{ "Skyrim.esm", 0x03EAF3 };
	const FormKey kRestoreMagicka{ "Skyrim.esm", 0x03EAF4 };

	Item Healing(int a_count = 3)
	{
		Item item;
		item.key = FormKey{ "Skyrim.esm", 0x03EADE };
		item.effects = { kRestoreHealth };
		item.count = a_count;
		return item;
	}

	Item Magicka(int a_count = 2)
	{
		Item item;
		item.key = FormKey{ "Skyrim.esm", 0x039BE0 };
		item.effects = { kRestoreMagicka };
		item.count = a_count;
		return item;
	}

	Item Sword()
	{
		Item item;
		item.key = FormKey{ "Skyrim.esm", 0x012EB7 };
		item.count = 1;
		return item;
	}

	PouchSet HealingAt(int a_slot, Mode a_mode = Mode::Shared)
	{
		PouchSet set;
		set.Set(Pouch(a_slot, Filter::FromItem(Healing()), a_mode));
		return set;
	}

	Reach EmptyHandAt(int a_slot)
	{
		Reach r;
		r.slot = a_slot;
		r.leftHand = true;
		return r;
	}

	Reach FullHandAt(int a_slot)
	{
		Reach r = EmptyHandAt(a_slot);
		r.handOccupied = true;
		return r;
	}
}

// The first rule and the most important one: a slot nobody configured is still VRIK's,
// and the answer VRIK gets back is the one that means "carry on".
TEST(a_slot_that_is_not_a_pouch_stays_with_vrik)
{
	FakePack pack;
	pack.Put(Healing());

	const auto set = HealingAt(kHip);
	const auto d = set.Decide(EmptyHandAt(kChest), pack);
	CHECK(d.act == Act::PassToVrik);
	CHECK(d.LetVrikAct());
}

TEST(an_empty_hand_at_a_pouch_with_potions_in_the_pack_is_given_one)
{
	FakePack pack;
	pack.Put(Healing());
	pack.Put(Magicka());

	const auto set = HealingAt(kHip);
	const auto d = set.Decide(EmptyHandAt(kHip), pack);
	CHECK(d.act == Act::Draw);
	CHECK(!d.LetVrikAct());
	CHECK(d.item == Healing().key);
	CHECK(d.leftHand);
}

// The whole of "refilling" is this test. Nothing is transferred, nothing is counted
// into the pouch: the belt simply shows what the pack has, so buying a potion fills
// the pouch and selling the last one empties it, with no event in between.
TEST(the_pouch_is_a_window_on_the_pack_and_needs_no_refilling)
{
	const auto set = HealingAt(kHip);

	FakePack empty;
	CHECK(!set.Display(kHip, empty).anything);
	CHECK(set.Decide(EmptyHandAt(kHip), empty).act == Act::PassToVrik);

	FakePack bought;
	bought.Put(Healing(7));
	const auto shown = set.Display(kHip, bought);
	CHECK(shown.anything);
	CHECK(shown.item == Healing().key);
	CHECK_EQ(shown.count, 7);
	CHECK(set.Decide(EmptyHandAt(kHip), bought).act == Act::Draw);
}

// The difference between the two modes, and the place where it matters most: a shared
// slot that has run out steps aside so the sword in it still works, an exclusive one
// does not, because drawing a sword out of a potion pouch is a worse answer than
// drawing nothing.
TEST(with_an_empty_pack_a_shared_pouch_steps_aside_and_an_exclusive_one_refuses)
{
	FakePack empty;

	const auto shared = HealingAt(kHip, Mode::Shared);
	CHECK(shared.Decide(EmptyHandAt(kHip), empty).act == Act::PassToVrik);

	const auto exclusive = HealingAt(kHip, Mode::Exclusive);
	const auto d = exclusive.Decide(EmptyHandAt(kHip), empty);
	CHECK(d.act == Act::Refuse);
	CHECK(d.reason == Reason::NothingInPack);
	CHECK(!d.LetVrikAct());
}

// HIGGS can decline the hand for a frame. That is not the same as the pack being
// empty: the event is still ours, and handing it to VRIK would draw a weapon instead
// of doing nothing.
TEST(a_hand_higgs_cannot_fill_gets_nothing_rather_than_a_sword)
{
	FakePack pack;
	pack.Put(Healing());

	Reach r = EmptyHandAt(kHip);
	r.handCanHold = false;

	const auto d = HealingAt(kHip).Decide(r, pack);
	CHECK(d.act == Act::Refuse);
	CHECK(d.reason == Reason::HandUnavailable);
}

// Setting a pouch up has no menu in it: push a bottle into an empty slot, and from
// then on the slot is for that kind of potion.
TEST(a_bottle_pushed_into_an_unassigned_pouch_sets_it_up)
{
	PouchSet set;
	set.Set(Pouch(kHip, Mode::Shared));

	FakePack pack;
	pack.Put(Healing());

	// An empty hand at an unassigned pouch leaves the slot to VRIK...
	CHECK(set.Decide(EmptyHandAt(kHip), pack).act == Act::PassToVrik);

	// ...while a full one is how the pouch gets its meaning.
	const auto fast = set.Decide(FullHandAt(kHip), pack);
	CHECK(fast.act == Act::Assign);
	CHECK(fast.reason == Reason::NotAssigned);

	const auto offer = set.Offer(kHip, true, Healing());
	CHECK(offer.act == Act::Assign);
	CHECK(set.Assign(kHip, Healing()));
	CHECK(set.Find(kHip)->IsAssigned());

	// And now it behaves as a set-up pouch: a stronger potion of the same effect is
	// accepted, a magicka one is not.
	Item stronger = Healing();
	stronger.key = FormKey{ "Skyrim.esm", 0x03EADF };
	CHECK(set.Offer(kHip, true, stronger).act == Act::Stow);
	CHECK(set.Offer(kHip, true, Magicka()).act == Act::PassToVrik);
}

// A pouch that forgot what it was for whenever the pack ran dry would forget exactly
// when the nearest shop is furthest away.
TEST(running_out_does_not_unassign_the_pouch)
{
	const auto set = HealingAt(kHip);
	FakePack empty;

	CHECK(!set.Display(kHip, empty).anything);
	CHECK(set.Find(kHip)->IsAssigned());
}

TEST(a_full_hand_at_a_set_up_pouch_claims_the_event_and_the_offer_decides)
{
	FakePack pack;
	pack.Put(Healing());
	const auto set = HealingAt(kHip);

	const auto fast = set.Decide(FullHandAt(kHip), pack);
	CHECK(fast.act == Act::Stow);
	CHECK(fast.reason == Reason::HandBusy);

	CHECK(set.Offer(kHip, true, Healing()).act == Act::Stow);

	// A sword offered to a shared potion pouch is VRIK's business after all.
	const auto wrong = set.Offer(kHip, true, Sword());
	CHECK(wrong.act == Act::PassToVrik);
	CHECK(wrong.reason == Reason::WrongItem);

	// In an exclusive slot the same offer cannot fall through: the slot is suspended,
	// so passing it on would mean nothing happens at all.
	const auto exclusive = HealingAt(kHip, Mode::Exclusive);
	CHECK(exclusive.Offer(kHip, true, Sword()).act == Act::Refuse);
}

TEST(a_poison_neither_sets_a_pouch_up_nor_goes_into_one)
{
	PouchSet set;
	set.Set(Pouch(kHip, Mode::Shared));

	Item poison = Healing();
	poison.harmful = true;

	CHECK(set.Offer(kHip, true, poison).act == Act::Refuse);
	CHECK(!set.Assign(kHip, poison));
	CHECK(!set.Find(kHip)->IsAssigned());
}

// HIGGS reports the endings by hand - "the left hand drank something" - and says
// nothing about pouches. So the hand is where we remember which pouch it emptied.
TEST(the_hand_remembers_which_pouch_it_drew_from)
{
	PouchSet set = HealingAt(kHip);

	CHECK(!set.SlotOfHand(true).has_value());
	set.NoteDrawn(true, kHip, Healing().key);
	CHECK(set.SlotOfHand(true).has_value());
	CHECK_EQ(*set.SlotOfHand(true), kHip);
	CHECK(!set.SlotOfHand(false).has_value());

	set.NoteSettled(true);
	CHECK(!set.SlotOfHand(true).has_value());
}


// WHICH OF SEVERAL MATCHING POTIONS. The pack answers in an order of its own - in the
// game, a map keyed by where the form happens to sit in memory - so a rule that takes
// "the first" takes a different bottle on a different day, and the player sees a rare
// brew spent on a scratch. Given the same three potions in any order, the same one has
// to come out: the plainest first, then the weakest.
TEST(the_plainest_and_weakest_matching_potion_is_the_one_drawn)
{
	Item weak = Healing();
	weak.strength = 25.0f;

	Item strong = Healing();
	strong.key = FormKey{ "Skyrim.esm", 0x03EADF };
	strong.strength = 100.0f;

	// Weaker than either, and still not the one to spend: it also restores magicka,
	// and that half of it would be thrown away here.
	Item brew = Healing();
	brew.key = FormKey{ "Skyrim.esm", 0x03EAE0 };
	brew.effects = { kRestoreHealth, kRestoreMagicka };
	brew.strength = 10.0f;

	const PouchSet set = HealingAt(kHip);

	FakePack first;
	first.Put(brew);
	first.Put(strong);
	first.Put(weak);

	FakePack second;
	second.Put(weak);
	second.Put(strong);
	second.Put(brew);

	FakePack third;
	third.Put(strong);
	third.Put(brew);
	third.Put(weak);

	const Pack* packs[]{ &first, &second, &third };
	for (const Pack* pack : packs) {
		const auto decision = set.Decide(EmptyHandAt(kHip), *pack);
		CHECK(decision.act == Act::Draw);
		CHECK(decision.item == weak.key);
	}
}

// A pouch with one matching potion left still hands that one over, however plain or
// strong it is: the rule above orders candidates, it does not turn any of them away.
TEST(the_only_matching_potion_is_drawn_whatever_it_is)
{
	Item brew = Healing();
	brew.effects = { kRestoreHealth, kRestoreMagicka };
	brew.strength = 500.0f;

	FakePack pack;
	pack.Put(brew);

	const auto decision = HealingAt(kHip).Decide(EmptyHandAt(kHip), pack);
	CHECK(decision.act == Act::Draw);
	CHECK(decision.item == brew.key);
}
