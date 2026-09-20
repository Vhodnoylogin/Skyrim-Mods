#pragma once

namespace BodyPouches::Core
{
	// What to do with the VRIK slot a pouch sits on, decided away from VRIK.
	//
	// The decision itself is three lines of reasoning and no calls at all, which is
	// exactly why it lives here: in the adapter it could only ever be tried by loading
	// the game with a slot switched off by hand, and here it is tried in a second on any
	// machine. The adapter is left with the doing - ask VRIK, say the line, suspend.

	// Everything the decision depends on. Gathered by the adapter, which is the only
	// part that knows how to ask VRIK anything.
	struct SlotFacts
	{
		int  slot{};
		bool detectable{};   // VRIK allows some weapon type here, so it watches the slot
		bool exclusive{};    // the pouch was given this slot outright
		bool maySwitchOn{};  // the player allowed the mod to switch a slot on itself
	};

	// Three independent steps, not three choices: a slot that is off and that we are
	// allowed to switch on is switched on AND then taken over.
	struct SlotPlan
	{
		bool switchOn{};
		bool complain{};
		bool suspend{};
	};

	[[nodiscard]] constexpr SlotPlan PlanFor(const SlotFacts& a_facts) noexcept
	{
		SlotPlan plan;

		if (!a_facts.detectable) {
			// A slot that allows no weapon type is one VRIK never looks at, so a pouch
			// there is dead. Switching it on is somebody else's setting to change, and
			// we do it only when told we may; otherwise we say so and leave it alone.
			plan.switchOn = a_facts.maySwitchOn;
			plan.complain = !a_facts.maySwitchOn;
		}

		// Suspension is for a slot given to a pouch outright - and only for one VRIK
		// will actually watch. Asking to suspend a slot that stays off achieves nothing
		// and shows up in the log as a refusal by VRIK, which is a lie about what
		// happened and would send the next run looking in the wrong place.
		plan.suspend = a_facts.exclusive && (a_facts.detectable || plan.switchOn);

		return plan;
	}
}
