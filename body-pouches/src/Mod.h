#pragma once

#include "Config.h"
#include "core/PouchSet.h"
#include "game/PlayerPack.h"
#include "vr/HiggsLink.h"
#include "vr/VrikLink.h"

#include <atomic>
#include <cstdint>
#include <mutex>
#include <thread>

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

		// Ask VRIK and HIGGS for their interfaces and subscribe. Called at PostLoad,
		// the earliest moment both authors sanction.
		void Connect();

		// The game's data is up: settings can be read and pouches built.
		void OnDataLoaded();

		// Start listening for the press that draws from a pouch. VRIK's holster event is
		// part of its weapon logic and never fires for a hand holding a potion, so the
		// press is ours to notice.
		//
		// Called from OnDataLoaded and not from kInputLoaded, which arrives two messages
		// earlier: the controllers do exist by then, but the settings do not, so the mod
		// would announce the button it was built with rather than the one it will obey.
		void WatchInput();

		// A save was loaded or a new game started. Suspension in VRIK is runtime-only
		// state by its author's design, so it has to be asked for again every time.
		void OnGameLoaded();

		[[nodiscard]] bool Working() const noexcept { return _vrik.Ready() && _higgs.Ready(); }

	private:
		Mod() = default;

		// WHERE THE MECHANIC ACTUALLY COMES FROM.
		//
		// VRIK owns the place on the body and answers GetHolsterSlotInReach for any hand
		// and any contents - that part is flawless. What it does not do is raise an
		// event: its holster callback fires only when a weapon could be drawn or put
		// away, which for a pouch of potions means never. Six runs in the game settled
		// that beyond doubt.
		//
		// So the place comes from VRIK and the moment comes from elsewhere: putting
		// something in is HIGGS letting go of it at a slot, and taking something out is
		// a button pressed by an empty hand at a slot.
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

		// --- the work itself, always on the game's own thread ---
		bool Draw(int a_slot, bool a_isLeft, const Core::FormKey& a_item);
		bool TakeBack(int a_slot, bool a_isLeft, bool a_assigning);

		// A hand reached a pouch and pressed: give it what the pouch holds.
		void DrawAt(int a_slot, bool a_isLeft);
		// A hand let go of something at a pouch: take it in, or set the pouch up with it.
		void StowDropped(int a_slot, bool a_isLeft, RE::TESObjectREFR* a_object);

		// How long ago this hand was given a bottle out of this very pouch, or -1. The two
		// gestures share a button and a place, so a release that follows a draw closely
		// enough is the end of that draw and not a new stow.
		[[nodiscard]] std::int64_t SinceDrawnFrom(bool a_isLeft, int a_slot) const;

		// Which pouch this hand is at, or 0. Answers from the last reading while the
		// hand is still there, and for a short while after it has left - a bottle let go
		// of at the stomach lands a moment later, by which time the hand has moved on.
		[[nodiscard]] int PouchAtHand(bool a_isLeft, bool a_remember);

		// VRIK says "secondary hand", HIGGS says "left". This is the way back.
		[[nodiscard]] static bool IsSecondaryHand(bool a_isLeft);

		void BuildPouches(const Settings& a_settings);

		// Ask VRIK, every frame, which slot each hand has reached, and say so whenever
		// the answer changes. This is how a hand held at a slot that raises no holster
		// attempt can be told from a hand VRIK does not see at that slot at all - the
		// two look exactly alike from the callback, and look nothing alike from here.
		//
		// It re-queues itself on the game's task queue, so it runs on the game's own
		// thread and stops costing anything the moment the mod is idle.
		// One reading, on the game's thread. Never re-queues itself: see PollReach.
		static void PollReach();
		// The pace, on a thread of its own - sleep, hand over one reading, sleep.
		static void PollLoop();
		void        NoteReach();
		void        StartPolling();
		// Switch on the slots the pouches sit in, then suspend the exclusive ones. Runs
		// after every load: both halves live in VRIK's memory and not in its files.
		void ApplySlots();

		// VRIK says "the secondary hand"; HIGGS and the game say "the left hand". The
		// two only agree for a right-handed player, so the translation is made once,
		// here, out of the game's own left-handed setting.
		[[nodiscard]] static bool IsLeftHand(bool a_secondaryHand);

		// Where to put a bottle so that a hand can close around it.
		[[nodiscard]] static bool HandPosition(bool a_isLeft, RE::NiPoint3& a_out);

		// What the last poll saw, so that only changes are said. Indexed by hand the way
		// VRIK counts them: [0] primary, [1] secondary.
		int                 _reach[2]{ 0, 0 };
		int                 _lastPouch[2]{ 0, 0 };
		std::int64_t        _lastPouchAt[2]{ 0, 0 };
		// Which pouch each hand was last given a bottle out of, and when. Indexed the same
		// way: [0] primary, [1] secondary.
		int                 _drawnFrom[2]{ 0, 0 };
		std::int64_t        _drawnAt[2]{ 0, 0 };
		Input               _input;
		bool                _slotsArranged{ false };
		bool                _watchingInput{ false };

		Core::PouchSet   _pouches;
		Game::PlayerPack _pack;
		VR::VrikLink     _vrik;
		VR::HiggsLink    _higgs;
		Settings         _settings;
		std::mutex       _lock;
	};
}
