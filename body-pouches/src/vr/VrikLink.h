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

		// VRIK's own settings, the ones that live in vrikslots.ini and vrik.ini.
		//
		// IN MEMORY ONLY. The contract says it plainly - "files are not saved
		// automatically" - and saveSettings(), the call that would write them out, is
		// deliberately not wrapped here. A mod that quietly rewrote somebody's VRIK
		// configuration on disk would be doing the very thing we refuse to do by hand.
		[[nodiscard]] double GetSetting(const char* a_name);
		void                 SetSetting(const char* a_name, double a_value);

		// Does VRIK look at this slot at all?
		//
		// A slot that allows no weapon type is off - "set all weapon types to 0 to
		// disable a slot", says its author in the file - and an off slot raises no
		// event, so a pouch there is simply dead.
		[[nodiscard]] bool IsDetectable(int a_slot);

		// Switch a slot on. NOT called unless the player has asked for it in our own
		// settings: VRIK's configuration belongs to VRIK and to whoever set it, and a
		// mod that quietly changes it - even in memory, even reversibly - leaves that
		// person looking at one thing in their menu and getting another in the game.
		// Returns false when the slot was already on, so the caller can stay quiet.
		bool SwitchOn(int a_slot);

	private:
		vrikPluginApi::IVrikInterface001* _api{ nullptr };
		unsigned int                      _build{ 0 };
	};
}
