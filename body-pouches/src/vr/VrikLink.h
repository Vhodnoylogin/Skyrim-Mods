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

		// Make a slot exist as far as VRIK is concerned.
		//
		// VRIK ignores a slot that allows no weapon type at all - "set all weapon types
		// to 0 to disable a slot", says its author in the file - and the slots a build
		// leaves free for a pouch are switched off in exactly that way. So one type is
		// allowed and the slot is made visible; the plugin then suspends it, and nothing
		// is ever actually holstered there.
		//
		// A slot that is already on is left alone: somebody put a weapon there on
		// purpose, and that is their arrangement, not ours to overwrite.
		bool EnsureDetectable(int a_slot);

	private:
		vrikPluginApi::IVrikInterface001* _api{ nullptr };
		unsigned int                      _build{ 0 };
	};
}
