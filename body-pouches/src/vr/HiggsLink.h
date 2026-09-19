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

	private:
		HiggsPluginAPI::IHiggsInterface001* _api{ nullptr };
		unsigned int                        _build{ 0 };
	};
}
