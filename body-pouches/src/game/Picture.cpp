#include "game/Picture.h"

#include "Loc.h"

namespace BodyPouches::Game
{
	namespace
	{
		constexpr auto kPlugin = "BodyPouches.esp";

		// The local form ids tools/make-esp.py writes. The effect in between is found
		// through the ability and never needed by name.
		constexpr RE::FormID kArtId = 0x800;
		constexpr RE::FormID kAbilityId = 0x802;

		// How long to wait for VRIK to let go of a model being taken down before the next
		// one goes up anyway. VRIK's own scripts wait up to 25 x 0.25 s for the same thing.
		constexpr std::int64_t kTakeDownMs = 3000;

		const char* OrNothing(const std::string& a_text) { return a_text.empty() ? "-" : a_text.c_str(); }
	}

	bool Picture::Load(int a_slot)
	{
		_slot = a_slot;

		auto* data = RE::TESDataHandler::GetSingleton();
		if (data != nullptr) {
			_art = data->LookupForm<RE::BGSArtObject>(kArtId, kPlugin);
			_ability = data->LookupForm<RE::SpellItem>(kAbilityId, kPlugin);
		}

		if (!Ready()) {
			Loc::Warn(Keys::kPictureNoPlugin, kPlugin, _art != nullptr, _ability != nullptr);
			_art = nullptr;
			_ability = nullptr;
			return false;
		}

		const char* model = _art->GetModel();
		Loc::Info(Keys::kPictureReady, a_slot, _art->GetFormID(), _ability->GetFormID(),
			model != nullptr ? model : "");
		return true;
	}

	void Picture::Want(const std::string& a_model, const std::string& a_what)
	{
		if (a_model == _wanted) {
			return;
		}
		_wanted = a_model;
		_wantedWhat = a_what;
		Loc::Info(Keys::kPictureWanted, _slot, OrNothing(_wantedWhat), OrNothing(_wanted));
	}

	void Picture::Tick(std::int64_t a_now, bool a_displayed)
	{
		if (!Ready()) {
			return;
		}

		// VRIK's own word on whether the model is on the body, said whenever it changes:
		// "the ability is on" and "the player can see a bottle" are two different claims,
		// and only this one is the second.
		if (a_displayed != _displayed) {
			_displayed = a_displayed;
			if (a_displayed) {
				Loc::Info(Keys::kPictureOnBody, _slot, OrNothing(_shown));
			} else {
				Loc::Info(Keys::kPictureOffBody, _slot);
			}
		}

		if (_waiting) {
			const bool gone = !a_displayed;
			if (!gone && a_now - _waitingSince < kTakeDownMs) {
				return;
			}
			_waiting = false;
			if (gone) {
				Loc::Info(Keys::kPictureGone, _slot, a_now - _waitingSince);
			} else {
				Loc::Warn(Keys::kPictureStuck, _slot, a_now - _waitingSince);
			}
			if (!_wanted.empty()) {
				Put();
			}
			return;
		}

		if (_wanted == _shown) {
			return;
		}

		if (!_shown.empty()) {
			TakeDown();
			// Something else is to go up: only once VRIK has let go of this one, or the
			// new model would be set up while the old one still hangs there.
			if (!_wanted.empty()) {
				_waiting = true;
				_waitingSince = a_now;
			}
			return;
		}

		Put();
	}

	void Picture::Reset(std::int64_t a_now)
	{
		if (!Ready()) {
			return;
		}
		auto* player = RE::PlayerCharacter::GetSingleton();
		if (player == nullptr) {
			return;
		}

		const bool had = player->HasSpell(_ability);
		if (had) {
			player->RemoveSpell(_ability);
			_waiting = true;
			_waitingSince = a_now;
		}
		_shown.clear();
		Loc::Info(Keys::kPictureReset, _slot, had);
	}

	void Picture::Put()
	{
		auto* player = RE::PlayerCharacter::GetSingleton();
		if (player == nullptr) {
			return;
		}

		// The model first and the ability second: the model is read when the effect
		// starts, and VRIK catches it at that same moment.
		_art->SetModel(_wanted.c_str());
		const bool added = player->AddSpell(_ability);
		_shown = _wanted;
		Loc::Info(Keys::kPictureUp, _slot, OrNothing(_wantedWhat), _shown, added);
	}

	void Picture::TakeDown()
	{
		auto* player = RE::PlayerCharacter::GetSingleton();
		if (player == nullptr) {
			return;
		}

		const bool removed = player->RemoveSpell(_ability);
		Loc::Info(Keys::kPictureTakenDown, _slot, _shown, removed);
		_shown.clear();
	}
}
