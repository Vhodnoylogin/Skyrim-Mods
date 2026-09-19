#include "vr/HiggsLink.h"

#include "Loc.h"
#include "vr/Handshake.h"

// The contract declares this global and expects the handshake to fill it. Our handshake
// is our own, so the definition lives here; HIGGS's own header is satisfied either way.
HiggsPluginAPI::IHiggsInterface001* g_higgsInterface = nullptr;

namespace BodyPouches::VR
{
	namespace
	{
		// HIGGS's own message number, from the handshake its author ships.
		constexpr std::uint32_t kGetInterface = 0xF9279A57;

		RE::TESObjectREFR* FromHiggs(::TESObjectREFR* a_refr)
		{
			return reinterpret_cast<RE::TESObjectREFR*>(a_refr);
		}

		::TESObjectREFR* ToHiggs(RE::TESObjectREFR* a_refr)
		{
			return reinterpret_cast<::TESObjectREFR*>(a_refr);
		}
	}

	bool HiggsLink::Connect()
	{
		_api = AskFor<HiggsPluginAPI::IHiggsInterface001, kGetInterface>("HIGGS");
		if (_api == nullptr) {
			Loc::Warn(Keys::kHiggsMissing);
			return false;
		}

		g_higgsInterface = _api;
		_build = _api->GetBuildNumber();
		Loc::Info(Keys::kHiggsFound, _build);
		return true;
	}

	bool HiggsLink::CanGrab(bool a_isLeft) const
	{
		return _api != nullptr && _api->CanGrabObject(a_isLeft);
	}

	bool HiggsLink::IsHolding(bool a_isLeft) const
	{
		return _api != nullptr && _api->IsHoldingObject(a_isLeft);
	}

	RE::TESObjectREFR* HiggsLink::Held(bool a_isLeft) const
	{
		return _api == nullptr ? nullptr : FromHiggs(_api->GetGrabbedObject(a_isLeft));
	}

	void HiggsLink::Grab(RE::TESObjectREFR* a_object, bool a_isLeft)
	{
		if (_api != nullptr && a_object != nullptr) {
			_api->GrabObject(ToHiggs(a_object), a_isLeft);
		}
	}

	void HiggsLink::OnConsumed(HiggsPluginAPI::IHiggsInterface001::ConsumedCallback a_callback)
	{
		if (_api != nullptr && a_callback != nullptr) {
			_api->AddConsumedCallback(a_callback);
		}
	}

	void HiggsLink::OnStashed(HiggsPluginAPI::IHiggsInterface001::StashedCallback a_callback)
	{
		if (_api != nullptr && a_callback != nullptr) {
			_api->AddStashedCallback(a_callback);
		}
	}

	void HiggsLink::OnDropped(HiggsPluginAPI::IHiggsInterface001::DroppedCallback a_callback)
	{
		if (_api != nullptr && a_callback != nullptr) {
			_api->AddDroppedCallback(a_callback);
		}
	}
}
