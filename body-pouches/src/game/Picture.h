#pragma once

#include <RE/Skyrim.h>

#include <cstdint>
#include <string>

namespace BodyPouches::Game
{
	// The potion a pouch holds, hung on the body where the pouch is.
	//
	// VRIK draws a thing in a slot only as an art object played on the player. Its DLL
	// catches the moment that art's model is set up, hangs the model on the slot's bone
	// and puts it in the middle of the slot every frame (vrik-holster-api.md, "Показ
	// предмета в слоте"). So our plugin, BodyPouches.esp, carries such an art, an effect
	// that plays it and a constant ability made of that effect (tools/make-esp.py).
	// Showing a potion is giving the art that potion's model and the player the ability;
	// changing the potion is taking the ability away, waiting until VRIK has let go of
	// the old model, and giving it back.
	//
	// A call to VrikSetSlotWeaponType was here before and showed nothing, and could not
	// have: for anything but a weapon, a shield or a torch it records "empty".
	class Picture
	{
	public:
		// Find our three records and remember which slot they are for. False, and said
		// why, when the plugin is not loaded - everything else still works without it.
		bool Load(int a_slot);

		[[nodiscard]] bool              Ready() const noexcept { return _art != nullptr && _ability != nullptr; }
		[[nodiscard]] RE::BGSArtObject* Art() const noexcept { return _art; }
		[[nodiscard]] int               Slot() const noexcept { return _slot; }

		// What should hang there: a model path and the potion's name, or two empty
		// strings for nothing. Only a change does anything.
		void Want(const std::string& a_model, const std::string& a_what);

		// One step, every frame. a_displayed is VRIK's answer to "is the model on the
		// bone, and did you place it this frame" - which is how a model being taken
		// down is known to be gone, and how a model put up is known to have arrived.
		void Tick(std::int64_t a_now, bool a_displayed);

		// After a load, and at the first frame of a new game: the ability may have come
		// back with the save, carrying the plugin's own model rather than the pouch's.
		void Reset(std::int64_t a_now);

	private:
		void Put();
		void TakeDown();

		RE::BGSArtObject* _art{ nullptr };
		RE::SpellItem*    _ability{ nullptr };
		int               _slot{ 0 };

		std::string  _wanted;      // model path; empty for nothing
		std::string  _wantedWhat;  // the potion's name, for the log
		std::string  _shown;       // what the art carries while the ability is on
		bool         _waiting{ false };
		std::int64_t _waitingSince{ 0 };
		bool         _displayed{ false };
	};
}
