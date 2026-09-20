#include "Harness.h"

#include "core/SlotPlan.h"

using namespace BodyPouches::Core;

namespace
{
	constexpr int kStomach = 13;

	SlotFacts Facts(bool a_detectable, bool a_exclusive, bool a_maySwitchOn)
	{
		SlotFacts facts;
		facts.slot = kStomach;
		facts.detectable = a_detectable;
		facts.exclusive = a_exclusive;
		facts.maySwitchOn = a_maySwitchOn;
		return facts;
	}
}

// The ordinary case, and the only one a working build ever sees: VRIK watches the slot,
// the pouch has it outright, so the pouch takes it over and nothing is said about
// settings that are already right.
TEST(a_slot_vrik_watches_is_simply_taken_over)
{
	const auto plan = PlanFor(Facts(true, true, false));
	CHECK(plan.suspend);
	CHECK(!plan.switchOn);
	CHECK(!plan.complain);
}

// A shared pouch leaves the slot to VRIK: a sword in it is still drawn as a sword, and
// suspension would take that away.
TEST(a_shared_pouch_does_not_take_the_slot_away_from_vrik)
{
	const auto plan = PlanFor(Facts(true, false, false));
	CHECK(!plan.suspend);
	CHECK(!plan.switchOn);
	CHECK(!plan.complain);
}

// The slot is off and the player has not allowed us to touch VRIK's settings. Then the
// only thing to do is say so - and NOT suspend, because a slot VRIK does not watch
// cannot be taken over and the attempt would be logged as a refusal by VRIK.
TEST(an_off_slot_is_complained_about_and_not_suspended)
{
	const auto plan = PlanFor(Facts(false, true, false));
	CHECK(plan.complain);
	CHECK(!plan.switchOn);
	CHECK(!plan.suspend);
}

// The same slot, once the player has set mayEnableSlots: switched on and then taken
// over in one go, and no complaint, because there is nothing left to complain about.
TEST(an_off_slot_we_may_switch_on_is_switched_on_and_then_taken_over)
{
	const auto plan = PlanFor(Facts(false, true, true));
	CHECK(plan.switchOn);
	CHECK(plan.suspend);
	CHECK(!plan.complain);
}

// Permission to switch a slot on says nothing about who owns it: a shared pouch gets
// its slot switched on and still leaves it to VRIK.
TEST(permission_to_switch_on_does_not_make_a_shared_pouch_exclusive)
{
	const auto plan = PlanFor(Facts(false, false, true));
	CHECK(plan.switchOn);
	CHECK(!plan.suspend);
	CHECK(!plan.complain);
}
