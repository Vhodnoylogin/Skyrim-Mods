#pragma once

#include "higgsinterface001.h"

#include <RE/Skyrim.h>

namespace BodyPouches::VR
{
	// Our side of HIGGS.
	//
	// HIGGS owns the hands: what they hold, whether they can take anything, and what
	// happens to a bottle once it is in one. Everything the player does with a potion
	// after it leaves the pouch - bringing it to the mouth and drinking, stowing it over
	// the shoulder, dropping it, knocking it against a table - is HIGGS's work and was
	// working long before this mod. We only put the bottle there and listen for how it
	// ended.
	class HiggsLink
	{
	public:
		[[nodiscard]] bool Connect();
		[[nodiscard]] bool Ready() const noexcept { return _api != nullptr; }
		[[nodiscard]] unsigned int Build() const noexcept { return _build; }

		[[nodiscard]] bool CanGrab(bool a_isLeft) const;
		[[nodiscard]] bool IsHolding(bool a_isLeft) const;
		[[nodiscard]] RE::TESObjectREFR* Held(bool a_isLeft) const;

		void Grab(RE::TESObjectREFR* a_object, bool a_isLeft);

		// The three endings of a bottle that left a pouch.
		void OnConsumed(HiggsPluginAPI::IHiggsInterface001::ConsumedCallback a_callback);
		void OnStashed(HiggsPluginAPI::IHiggsInterface001::StashedCallback a_callback);
		void OnDropped(HiggsPluginAPI::IHiggsInterface001::DroppedCallback a_callback);

		// And its beginning: the hand really did close on something. GrabObject takes no
		// answer and returns none, so this is the only way to learn that the asking
		// worked - and it fires for every grab the player makes, ours or not.
		void OnGrabbed(HiggsPluginAPI::IHiggsInterface001::GrabbedCallback a_callback);

		// A call once a frame, on the game's own thread, after both VRIK and HIGGS have
		// done their work for it.
		//
		// THIS IS WHY THIS MOD NO LONGER HAS A THREAD OF ITS OWN. VRIK may only be asked
		// anything from the game thread, and it raises no event when a hand reaches a
		// slot, so the question has to be put over and over. That used to be a thread
		// that slept and handed a task to the game every hundred milliseconds - two
		// moving parts, a pace that was always either too slow or too costly, and one
		// version that hung the game outright. HIGGS gives the frame away for free.
		void OnFrame(HiggsPluginAPI::IHiggsInterface001::NoArgCallback a_callback);

	private:
		HiggsPluginAPI::IHiggsInterface001* _api{ nullptr };
		unsigned int                        _build{ 0 };
	};
}
