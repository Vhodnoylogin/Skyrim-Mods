#pragma once

#include "Config.h"
#include "core/PouchSet.h"
#include "game/Picture.h"
#include "game/PlayerPack.h"
#include "vr/HiggsLink.h"
#include "vr/VrikLink.h"

#include <cstdint>
#include <mutex>

namespace BodyPouches
{
	// The mod: one object, and there can only be one.
	//
	// THAT IS NOT A PREFERENCE, IT IS THE CONTRACT. Every callback in both APIs is a
	// plain function pointer with no context argument:
	//
	//     typedef bool (*HolsterAttemptCallback)(int slot, bool secondaryHand, bool handOccupied);
	//     typedef void (*ConsumedCallback)(bool isLeft, TESForm *consumedForm);
	//
	// There is nowhere to hand `this` through, so the subscriber has to be reachable
	// from a static function, which means exactly one of it per process. Rather than
	// scatter globals about, everything that has to be reachable that way lives here.
	class Mod
	{
	public:
		static Mod& GetSingleton();

		// Ask VRIK and HIGGS for their interfaces and subscribe. Called at PostPostLoad,
		// when every plugin that answers messages is certain to be listening.
		void Connect();

		// The game's data is up: settings can be read, pouches built and our plugin's
		// records found.
		void OnDataLoaded();

		// Start listening to the controllers. No button draws anything any more - VRIK
		// raises that moment itself - but every squeeze of the grip by an empty hand is
		// still worth a line: it says where the hand was in each pouch's own numbers,
		// which is how a pouch is moved to where the player's hand actually goes.
		void WatchInput();

		// A save was loaded. Suspension in VRIK lasts until the game is closed, so this
		// only matters for the picture - but it is also the one load message that has
		// ever arrived, and the slots are arranged here as well as at the first frame.
		void OnGameLoaded();

		[[nodiscard]] bool Working() const noexcept { return _vrik.Ready() && _higgs.Ready(); }

	private:
		Mod() = default;

		// WHERE THE MECHANIC COMES FROM, as the reading of VRIK's own code settled it
		// (claude-skyrim-vr/knowledge/vrik-holster-api.md).
		//
		// VRIK owns the place on the body and says which slot each hand is at. For a
		// suspended slot it also raises the moment of taking something out: a hand that
		// closes its grip inside the pouch and leaves it with the grip still closed makes
		// a holster attempt, and an empty hand's attempt is a draw. Putting something in
		// is not VRIK's: a bottle goes in when the hand lets go of it inside the pouch,
		// and letting go is HIGGS's event. A full hand leaving the pouch is carrying its
		// bottle away, and VRIK's attempt for it is answered with nothing.
		class Input final : public RE::BSTEventSink<RE::InputEvent*>
		{
		public:
			RE::BSEventNotifyControl ProcessEvent(RE::InputEvent* const* a_event,
				RE::BSTEventSource<RE::InputEvent*>*) override;
		};

		// --- what the two mods call, and the only functions that may be static ---
		static bool OnHolsterAttempt(int a_slot, bool a_secondaryHand, bool a_handOccupied);
		static void OnConsumed(bool a_isLeft, ::TESForm* a_form);
		static void OnStashed(bool a_isLeft, ::TESForm* a_form);
		static void OnDropped(bool a_isLeft, ::TESObjectREFR* a_refr);
		static void OnGrabbed(bool a_isLeft, ::TESObjectREFR* a_refr);

		// --- the work itself, always on the game's own thread ---
		bool Draw(int a_slot, bool a_isLeft, const Core::FormKey& a_item);
		// A hand let go of something inside a pouch: take it in, or set the pouch up with it.
		void StowDropped(int a_slot, bool a_isLeft, RE::TESObjectREFR* a_object);

		// Which pouch this hand is at this very moment, or 0. Asked of VRIK and not
		// remembered: a bottle let go of after the hand has left the pouch is a bottle
		// dropped, not one put away.
		[[nodiscard]] int PouchAt(bool a_isLeft);

		// VRIK says "secondary hand", HIGGS says "left". This is the way back.
		[[nodiscard]] static bool IsSecondaryHand(bool a_isLeft);

		void BuildPouches(const Settings& a_settings);

		// Once a frame, on the game's own thread, given to us by HIGGS. Everything that
		// has to be asked over and over rather than waited for happens here: which slot
		// each hand has reached, whether a bottle just handed over was taken, and what
		// the pouch should be showing.
		static void OnFrame();

		// The first frame of play. A new game sends this plugin no message at all - run 7
		// waited twelve minutes for one - so this is where the slots are arranged and the
		// picture is set straight, whatever did or did not arrive before.
		void FirstFrame();

		// Ask VRIK which slot each hand has reached, and say so whenever the answer
		// changes.
		void NoteReach();

		// What the pouch should be showing, worked out on a slow beat or at once after a
		// bottle came out or went in, and one step of putting it up every frame.
		void RefreshDisplay();

		// Switch on the slots the pouches sit in, then suspend the exclusive ones.
		void ApplySlots();

		// Where each pouch is, in VRIK's numbers and in the world, and which way its
		// bone's axes point. Said at the first frame.
		void DescribeSlots();

		// Where this hand is in each pouch's own numbers: the posX, posY and posZ that
		// would put the pouch right there, and how far that is from where it is now.
		void Measure(bool a_isLeft);

		// VRIK says "the secondary hand"; HIGGS and the game say "the left hand". The
		// two only agree for a right-handed player, so the translation is made once,
		// here, out of the game's own left-handed setting.
		[[nodiscard]] static bool IsLeftHand(bool a_secondaryHand);

		// Where a hand is in the world, and the name of the node that said so; nullptr
		// when the hand has no node at all.
		[[nodiscard]] static const char* HandAt(bool a_isLeft, RE::NiPoint3& a_out);

		// Where to put a bottle so that a hand can close around it. Says which node.
		[[nodiscard]] static bool HandPosition(bool a_isLeft, RE::NiPoint3& a_out);

		// What the last poll saw, so that only changes are said. Indexed by hand the way
		// VRIK counts them: [0] primary, [1] secondary.
		int          _reach[2]{ 0, 0 };
		// Which pouch each hand was last given a bottle out of. Indexed the same way.
		int          _drawnFrom[2]{ 0, 0 };
		// When to look back and see whether the hand really closed on the bottle. HIGGS
		// takes no answer and gives none, so the only honest report is one made afterwards.
		std::int64_t _checkGrabAt[2]{ 0, 0 };
		// When the pouch is next asked what it should show. Zero means at once.
		std::int64_t _displayAt{ 0 };
		bool         _frameSeen{ false };
		Input        _input;
		bool         _slotsArranged{ false };
		bool         _watchingInput{ false };

		Core::PouchSet   _pouches;
		Game::PlayerPack _pack;
		Game::Picture    _picture;
		VR::VrikLink     _vrik;
		VR::HiggsLink    _higgs;
		Settings         _settings;
		std::mutex       _lock;
	};
}
