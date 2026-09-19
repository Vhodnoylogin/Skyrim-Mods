#pragma once

#include "vrikinterface001.h"

#include <RE/Skyrim.h>

namespace BodyPouches::VR
{
	// Our side of VRIK.
	//
	// VRIK owns the places on the body: where a slot is, whether a hand is near it, what
	// is drawn there, and how all of that survives a recalibration. This mod owns none
	// of that and wants none of it. What it needs is three things, and all three arrived
	// in build 80700:
	//
	//   AddHolsterAttemptCallback  - tell me when a hand reaches for a slot, and let my
	//                                answer decide whether you act or I do
	//   SetSlotSuspended           - for a slot given over to pouches entirely
	//   VrikSetSlotForArt          - what to draw there
	//
	// An older VRIK has none of them, and then this mod does nothing at all rather than
	// half of something.
	class VrikLink
	{
	public:
		// The build that first had the pouch functions. Anything older and the v-table
		// ends before the ones we need - calling them would not fail, it would jump
		// into whatever lies past the end.
		static constexpr unsigned int kRequiredBuild = 80700;

		[[nodiscard]] bool Connect();
		[[nodiscard]] bool Ready() const noexcept { return _api != nullptr && _build >= kRequiredBuild; }
		[[nodiscard]] unsigned int Build() const noexcept { return _build; }

		bool Subscribe(vrikPluginApi::IVrikInterface001::HolsterAttemptCallback a_callback);
		bool SetSuspended(int a_slot, bool a_suspended);
		[[nodiscard]] bool IsSuspended(int a_slot);
		[[nodiscard]] bool IsDisplayed(int a_slot);

		// What VRIK draws in the slot. Whether it will draw a potion at all is the one
		// thing about this mod that cannot be settled outside the game.
		void SetArt(int a_slot, RE::BGSArtObject* a_art);

	private:
		vrikPluginApi::IVrikInterface001* _api{ nullptr };
		unsigned int                      _build{ 0 };
	};
}
