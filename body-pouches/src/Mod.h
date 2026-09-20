#pragma once

#include "Config.h"
#include "core/PouchSet.h"
#include "game/PlayerPack.h"
#include "vr/HiggsLink.h"
#include "vr/VrikLink.h"

#include <atomic>
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

		// A save was loaded or a new game started. Suspension in VRIK is runtime-only
		// state by its author's design, so it has to be asked for again every time.
		void OnGameLoaded();

		[[nodiscard]] bool Working() const noexcept { return _vrik.Ready() && _higgs.Ready(); }

	private:
		Mod() = default;

		// --- what the two mods call, and the only functions that may be static ---
		static bool OnHolsterAttempt(int a_slot, bool a_secondaryHand, bool a_handOccupied);
		static void OnConsumed(bool a_isLeft, ::TESForm* a_form);
		static void OnStashed(bool a_isLeft, ::TESForm* a_form);
		static void OnDropped(bool a_isLeft, ::TESObjectREFR* a_refr);

		// --- the work itself, always on the game's own thread ---
		bool Draw(int a_slot, bool a_isLeft, const Core::FormKey& a_item);
		bool TakeBack(int a_slot, bool a_isLeft, bool a_assigning);

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

		// What the last poll saw, so that only changes are said.
		int  _reach[2]{ 0, 0 };
		bool _slotsArranged{ false };
		std::atomic<bool> _polling{ false };

		Core::PouchSet   _pouches;
		Game::PlayerPack _pack;
		VR::VrikLink     _vrik;
		VR::HiggsLink    _higgs;
		Settings         _settings;
		std::mutex       _lock;
	};
}
