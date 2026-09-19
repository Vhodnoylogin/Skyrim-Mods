#include "vr/VrikLink.h"

#include "Loc.h"
#include "vr/Handshake.h"

namespace BodyPouches::VR
{
	namespace
	{
		// VRIK's own message number, from the handshake its author ships. Not ours to
		// choose and not ours to change.
		constexpr std::uint32_t kGetInterface = 0xF2AFAEE6;
	}

	bool VrikLink::Connect()
	{
		_api = AskFor<vrikPluginApi::IVrikInterface001, kGetInterface>("VRIK");
		if (_api == nullptr) {
			Loc::Warn(Keys::kVrikMissing);
			return false;
		}

		_build = _api->getBuildNumber();
		if (_build < kRequiredBuild) {
			Loc::Warn(Keys::kVrikTooOld, _build, kRequiredBuild);
			return false;
		}

		Loc::Info(Keys::kVrikFound, _build);
		return true;
	}

	bool VrikLink::Subscribe(vrikPluginApi::IVrikInterface001::HolsterAttemptCallback a_callback)
	{
		if (!Ready() || a_callback == nullptr) {
			return false;
		}
		_api->AddHolsterAttemptCallback(a_callback);
		return true;
	}

	bool VrikLink::SetSuspended(int a_slot, bool a_suspended)
	{
		if (!Ready()) {
			return false;
		}
		const bool done = _api->SetSlotSuspended(a_slot, a_suspended);
		if (done && a_suspended) {
			Loc::Info(Keys::kPouchSuspended, a_slot);
		}
		return done;
	}

	bool VrikLink::IsSuspended(int a_slot)
	{
		return Ready() && _api->GetSlotSuspended(a_slot);
	}

	bool VrikLink::IsDisplayed(int a_slot)
	{
		return Ready() && _api->VrikGetSlotDisplayed(a_slot);
	}

	void VrikLink::SetArt(int a_slot, RE::BGSArtObject* a_art)
	{
		if (!Ready()) {
			return;
		}
		// The contract declares its own BGSArtObject - it was written against another
		// SDK - so the pointer changes vocabulary here and nowhere else.
		_api->VrikSetSlotForArt(a_slot, reinterpret_cast<::BGSArtObject*>(a_art));
	}
}
