#include "Mod.h"

#include "Loc.h"
#include "Paths.h"
#include "core/SlotPlan.h"
#include "game/Forms.h"

#include <SKSE/SKSE.h>

#include <array>
#include <chrono>
#include <cstdint>
#include <span>
#include <thread>

namespace BodyPouches
{
	namespace
	{
		const char* HandName(bool a_isLeft) { return a_isLeft ? "left" : "right"; }

		// Milliseconds since the mod started. Only differences are ever used.
		std::int64_t Now()
		{
			using namespace std::chrono;
			static const auto start = steady_clock::now();
			return duration_cast<milliseconds>(steady_clock::now() - start).count();
		}

		// Where a bottle is put so that the hand can close on it. The first node that
		// exists wins; the VR wand nodes are tried first because in VR they are where
		// the controller actually is, and the skeleton hands follow them with a lag.
		constexpr std::array kLeftNodes{ "LeftWandNode", "NPC L Hand [LHnd]", "NPC L Finger02 [LF02]" };
		constexpr std::array kRightNodes{ "RightWandNode", "NPC R Hand [RHnd]", "NPC R Finger02 [RF02]" };

		// Deliberately not a member. The pacing thread outlives nothing else it can reach:
		// the singleton is a function-local static and is destroyed while that thread may
		// still be between two sleeps, so the thread reads this and hands every reading
		// that touches the mod to the game's own queue, which stops being drained first.
		std::atomic<bool> g_polling{ false };

		// Ten times a second. Four was enough to watch a hand, and not enough to catch the
		// press that follows it: a button squeezed within the gap saw no slot in reach and
		// was passed over without a word, which is the one answer a run must never get.
		constexpr auto kPollEvery = std::chrono::milliseconds(100);
	}

	Mod& Mod::GetSingleton()
	{
		static Mod instance;
		return instance;
	}

	void Mod::Connect()
	{
		const bool vrik = _vrik.Connect();
		const bool higgs = _higgs.Connect();
		if (!vrik || !higgs) {
			// Both are needed and neither can be replaced: VRIK owns the places on the
			// body, HIGGS owns the hands. Without either, the mod does nothing at all
			// rather than half of something. Said out loud, because from here on the log
			// falls silent and silence on its own explains nothing.
			Loc::Warn(Keys::kConnectGaveUp, vrik, higgs);
			return;
		}

		if (!_vrik.Subscribe(&Mod::OnHolsterAttempt)) {
			Loc::Error(Keys::kVrikNoCallback);
			return;
		}

		Loc::Info(Keys::kVrikSubscribed);

		_higgs.OnConsumed(&Mod::OnConsumed);
		_higgs.OnStashed(&Mod::OnStashed);
		_higgs.OnDropped(&Mod::OnDropped);
		Loc::Info(Keys::kHiggsSubscribed);
	}

	void Mod::OnDataLoaded()
	{
		_settings = LoadSettings();
		Loc::SetLevel(_settings.logLevel);
		Loc::Load(Paths::LangDir(), _settings.language);
		BuildPouches(_settings);
		WatchInput();
		StartPolling();
	}

	void Mod::StartPolling()
	{
		if (g_polling || !Working()) {
			return;
		}
		if (auto* tasks = SKSE::GetTaskInterface(); tasks != nullptr) {
			g_polling = true;
			Loc::Info(Keys::kReachWatch);
			std::thread(&Mod::PollLoop).detach();
		}
	}

	void Mod::PollReach()
	{
		// WHAT NOT TO DO HERE, LEARNED THE HARD WAY.
		//
		// This function used to end by putting itself back on the game's task queue,
		// with a comment claiming that made it run once a frame. It does not. The game
		// drains that queue before it finishes the frame, so a task that re-adds itself
		// is drained forever and the frame never ends. Version 0.1.4 hung Skyrim VR on
		// the loading screen twice, with a hundred WaitForTrackingData timeouts in the
		// compositor's log and no crash: the game was alive and never gave a frame back.
		//
		// The pace therefore comes from a thread that sleeps, and this task only ever
		// does one reading and returns.
		auto& mod = GetSingleton();
		if (mod.Working()) {
			mod.NoteReach();
		}
	}

	void Mod::PollLoop()
	{
		while (g_polling) {
			std::this_thread::sleep_for(kPollEvery);

			// VRIK may only be asked anything on the game's own thread, so this thread
			// asks nothing itself - it hands over one reading and goes back to sleep. It
			// touches nothing of the mod's either: see g_polling.
			if (auto* tasks = SKSE::GetTaskInterface(); tasks != nullptr) {
				tasks->AddTask(&Mod::PollReach);
			}
		}
	}

	void Mod::NoteReach()
	{
		const auto now = Now();

		for (int hand = 0; hand < 2; ++hand) {
			const bool secondary = hand == 1;
			const int  slot = _vrik.SlotInReach(secondary);

			// Remembered while the hand is there, because the moment that matters comes
			// afterwards: a bottle let go of at the stomach lands a beat later, by which
			// time the hand has usually moved on.
			if (slot != 0) {
				std::scoped_lock guard(_lock);
				if (_pouches.Find(slot) != nullptr) {
					_lastPouch[hand] = slot;
					_lastPouchAt[hand] = now;
				}
			}

			if (slot == _reach[hand]) {
				continue;  // only changes are worth a line; this runs four times a second
			}
			_reach[hand] = slot;
			Loc::Info(Keys::kReachChanged, HandName(IsLeftHand(secondary)), slot,
				_vrik.CanBeHolstered(secondary));
		}
	}

	int Mod::PouchAtHand(bool a_isLeft, bool a_remember)
	{
		const int hand = IsSecondaryHand(a_isLeft) ? 1 : 0;

		// One lock over the whole answer, because the whole answer is made of what
		// NoteReach writes under it.
		std::scoped_lock guard(_lock);

		if (_reach[hand] != 0 && _pouches.Find(_reach[hand]) != nullptr) {
			return _reach[hand];
		}

		if (!a_remember || _lastPouch[hand] == 0) {
			return 0;
		}
		return (Now() - _lastPouchAt[hand]) <= _settings.reachMemoryMs ? _lastPouch[hand] : 0;
	}

	std::int64_t Mod::SinceDrawnFrom(bool a_isLeft, int a_slot) const
	{
		const int hand = IsSecondaryHand(a_isLeft) ? 1 : 0;
		if (_drawnFrom[hand] != a_slot || _drawnAt[hand] == 0) {
			return -1;
		}
		return Now() - _drawnAt[hand];
	}

	bool Mod::IsSecondaryHand(bool a_isLeft)
	{
		// The way back from IsLeftHand, and by the same setting.
		static const bool leftHanded = [] {
			const auto* setting = RE::GetINISetting("bLeftHandedMode:VRInput");
			return setting != nullptr && setting->GetBool();
		}();
		return leftHanded ? !a_isLeft : a_isLeft;
	}

	void Mod::OnGameLoaded()
	{
		// Said out loud on purpose. A run of this mod once ended with a log that stopped
		// after the settings were read, and nothing in it could tell "the message never
		// arrived" from "it arrived and every step of it quietly did nothing".
		Loc::Info(Keys::kGameLoaded, _settings.pouches.size());
		ApplySlots();
		StartPolling();
	}

	void Mod::BuildPouches(const Settings& a_settings)
	{
		std::scoped_lock guard(_lock);
		_pouches.Clear();
		for (const auto& setting : a_settings.pouches) {
			_pouches.Set(Core::Pouch(setting.slot, Settings::ModeFromText(setting.mode)));
			Loc::Info(Keys::kPouchConfigured, setting.slot, setting.mode);
		}
	}

	void Mod::ApplySlots()
	{
		if (!Working()) {
			Loc::Warn(Keys::kNotArranging, _vrik.Ready(), _higgs.Ready());
			return;
		}
		std::scoped_lock guard(_lock);

		// What to do with each slot is decided in the core, which can be tried without
		// VRIK and without the game; all that happens here is the doing of it. The three
		// steps are independent on purpose: a slot that is off and that we are allowed
		// to switch on is switched on AND then taken over, in that order.
		for (const auto& setting : _settings.pouches) {
			const auto* pouch = _pouches.Find(setting.slot);
			if (pouch == nullptr) {
				continue;
			}

			Core::SlotFacts facts;
			facts.slot = setting.slot;
			facts.detectable = _vrik.SeeSlot(setting.slot).detectable;
			facts.exclusive = pouch->PouchMode() == Core::Mode::Exclusive;
			facts.maySwitchOn = _settings.mayEnableSlots;

			const auto plan = Core::PlanFor(facts);
			if (plan.switchOn) {
				_vrik.SwitchOn(setting.slot);
			}
			if (plan.complain) {
				// VRIK's setting, arranged by whoever arranged it. We say what is wrong
				// and where it is fixed, and leave it alone.
				Loc::Warn(Keys::kSlotOff, setting.slot);
			}
			if (plan.suspend) {
				// So that VRIK detects the hand but neither draws a weapon from the slot
				// nor holsters one into it. Suspension is runtime-only by its author's
				// design, which is why this runs after every load.
				_vrik.SetSuspended(setting.slot, true);
			}
		}

		_slotsArranged = true;
	}

	bool Mod::IsLeftHand(bool a_secondaryHand)
	{
		// bLeftHandedMode swaps which controller is the primary one. Read once: it is a
		// launcher setting and does not change while the game runs.
		static const bool leftHanded = [] {
			const auto* setting = RE::GetINISetting("bLeftHandedMode:VRInput");
			return setting != nullptr && setting->GetBool();
		}();
		return leftHanded ? !a_secondaryHand : a_secondaryHand;
	}

	bool Mod::HandPosition(bool a_isLeft, RE::NiPoint3& a_out)
	{
		auto* player = RE::PlayerCharacter::GetSingleton();
		if (player == nullptr) {
			return false;
		}
		auto* root = player->Get3D();
		if (root == nullptr) {
			return false;
		}

		for (const char* name : (a_isLeft ? std::span<const char* const>(kLeftNodes) : std::span<const char* const>(kRightNodes))) {
			if (auto* node = root->GetObjectByName(name); node != nullptr) {
				a_out = node->world.translate;
				Loc::Info(Keys::kHandNode, HandName(a_isLeft), name);
				return true;
			}
		}

		Loc::Warn(Keys::kHandNotFound, HandName(a_isLeft));
		return false;
	}

	bool Mod::Draw(int a_slot, bool a_isLeft, const Core::FormKey& a_item)
	{
		Loc::Info(Keys::kDrawStart, a_slot, HandName(a_isLeft));

		auto* object = Game::PlayerPack::Held(a_item);
		if (object == nullptr) {
			Loc::Warn(Keys::kItemNotFound, a_item.plugin, a_item.localId);
			return false;
		}

		RE::NiPoint3 where;
		if (!HandPosition(a_isLeft, where)) {
			return false;
		}

		auto* player = RE::PlayerCharacter::GetSingleton();
		RE::NiPoint3 rotation{};

		// One call does both halves of what we need: the potion leaves the inventory and
		// a reference to it appears in the world, which is the only thing HIGGS can put
		// in a hand. Dropping it is not a metaphor - from here on it is an ordinary
		// bottle lying in the world that happens to be held.
		const auto handle = player->RemoveItem(
			object, 1, RE::ITEM_REMOVE_REASON::kDropping, nullptr, nullptr, &where, &rotation);

		const auto dropped = handle.get();
		if (!dropped) {
			Loc::Warn(Keys::kDropFailed);
			return false;
		}

		_higgs.Grab(dropped.get(), a_isLeft);
		Loc::Info(Keys::kGrabAsked, HandName(a_isLeft));
		_pouches.NoteDrawn(a_isLeft, a_slot, a_item);

		// Remembered so that the release which ends this very squeeze is not read as a
		// fresh reach to put something away. See SinceDrawnFrom.
		const int hand = IsSecondaryHand(a_isLeft) ? 1 : 0;
		_drawnFrom[hand] = a_slot;
		_drawnAt[hand] = Now();

		Loc::Info(Keys::kPouchDrawn, a_slot, HandName(a_isLeft));
		return true;
	}

	bool Mod::TakeBack(int a_slot, bool a_isLeft, bool a_assigning)
	{
		Loc::Info(Keys::kStowStart, a_slot, HandName(a_isLeft));

		auto* held = _higgs.Held(a_isLeft);
		if (held == nullptr) {
			Loc::Info(Keys::kNothingHeld, HandName(a_isLeft));
			return false;
		}

		auto* base = held->GetBaseObject();
		if (base == nullptr) {
			Loc::Warn(Keys::kHeldNoBase, HandName(a_isLeft), held->GetFormID());
			return false;
		}

		// Said whether the thing turns out to be a potion or not. Run 5 got as far as
		// here and stopped at "not a potion", and that line alone could not tell a real
		// sword in the hand from a stale reference HIGGS had already let go of - which
		// is why what is in the hand is now named outright.
		const auto* name = base->GetName();
		Loc::Info(Keys::kHeldIs, HandName(a_isLeft), name != nullptr ? name : "",
			RE::FormTypeToString(base->GetFormType()), base->GetFormID(), held->GetFormID());

		auto* potion = base->As<RE::AlchemyItem>();
		if (potion == nullptr) {
			Loc::Info(Keys::kHeldNotPotion, HandName(a_isLeft));
			return false;
		}

		auto item = Game::Describe(potion);
		item.count = 1;

		const auto decision = _pouches.Offer(a_slot, a_isLeft, item);
		if (a_assigning) {
			if (decision.act != Core::Act::Assign || !_pouches.Assign(a_slot, item)) {
				Loc::Info(Keys::kPouchWrongItem, a_slot);
				return false;
			}
			Loc::Info(Keys::kPouchAssigned, a_slot);
		} else if (decision.act != Core::Act::Stow) {
			Loc::Info(Keys::kPouchWrongItem, a_slot);
			return false;
		}

		// Back into the pack, and the bottle in the world is gone. The pouch keeps no
		// count of its own, so there is nothing else to put right.
		auto* player = RE::PlayerCharacter::GetSingleton();
		auto* bound = base->As<RE::TESBoundObject>();
		if (player == nullptr || bound == nullptr) {
			return false;
		}
		player->AddObjectToContainer(bound, nullptr, 1, nullptr);
		held->Disable();
		held->SetDelete(true);

		_pouches.NoteSettled(a_isLeft);
		Loc::Info(Keys::kPouchStowed, a_slot, HandName(a_isLeft));
		return true;
	}

	void Mod::DrawAt(int a_slot, bool a_isLeft)
	{
		Core::Reach reach;
		reach.slot = a_slot;
		reach.leftHand = a_isLeft;
		reach.handOccupied = _higgs.IsHolding(a_isLeft);
		reach.handCanHold = _higgs.CanGrab(a_isLeft);

		// The two values every outcome below turns on, said before they decide anything.
		// A refusal with neither of them in the log is a refusal nobody can explain.
		Loc::Info(Keys::kHandState, HandName(a_isLeft), reach.handOccupied, reach.handCanHold);

		Core::Decision decision;
		{
			std::scoped_lock guard(_lock);
			decision = _pouches.Decide(reach, _pack);
		}

		Loc::Info(Keys::kDecision, decision.slot, Core::Name(decision.act),
			Core::Name(decision.reason), HandName(a_isLeft), decision.LetVrikAct());

		switch (decision.act) {
		case Core::Act::Draw:
			Draw(decision.slot, a_isLeft, decision.item);
			break;

		case Core::Act::Stow:
		case Core::Act::Assign:
			// A press is how a bottle comes out. Putting one in is a release and not a
			// press, so there is nothing to do here except say why nothing happened -
			// otherwise a full hand pressing at a pouch is a silence like any other.
			Loc::Info(Keys::kPouchHandBusy, HandName(a_isLeft));
			break;

		case Core::Act::Refuse:
			if (decision.reason == Core::Reason::NothingInPack) {
				Loc::Info(Keys::kPouchEmpty, decision.slot);
			}
			break;

		case Core::Act::PassToVrik:
		default:
			break;
		}
	}

	void Mod::StowDropped(int a_slot, bool a_isLeft, RE::TESObjectREFR* a_object)
	{
		if (a_object == nullptr) {
			return;
		}

		auto* base = a_object->GetBaseObject();
		if (base == nullptr) {
			Loc::Warn(Keys::kHeldNoBase, HandName(a_isLeft), a_object->GetFormID());
			return;
		}

		const auto* name = base->GetName();
		Loc::Info(Keys::kHeldIs, HandName(a_isLeft), name != nullptr ? name : "",
			RE::FormTypeToString(base->GetFormType()), base->GetFormID(), a_object->GetFormID());

		auto* potion = base->As<RE::AlchemyItem>();
		if (potion == nullptr) {
			// Not ours: it stays on the ground, exactly where it was let go of.
			Loc::Info(Keys::kHeldNotPotion, HandName(a_isLeft));
			return;
		}

		auto item = Game::Describe(potion);
		item.count = 1;

		bool taken = false;
		{
			std::scoped_lock guard(_lock);
			const auto decision = _pouches.Offer(a_slot, a_isLeft, item);
			if (decision.act == Core::Act::Assign) {
				if (_pouches.Assign(a_slot, item)) {
					Loc::Info(Keys::kPouchAssigned, a_slot);
					taken = true;
				}
			} else if (decision.act == Core::Act::Stow) {
				taken = true;
			}
		}

		if (!taken) {
			Loc::Info(Keys::kDropNotOurs, HandName(a_isLeft), a_slot);
			return;
		}

		auto* player = RE::PlayerCharacter::GetSingleton();
		auto* bound = base->As<RE::TESBoundObject>();
		if (player == nullptr || bound == nullptr) {
			return;
		}

		// Into the pack, and the bottle in the world is gone. The pouch keeps no count
		// of its own, so there is nothing else to put right.
		player->AddObjectToContainer(bound, nullptr, 1, nullptr);
		a_object->Disable();
		a_object->SetDelete(true);

		{
			std::scoped_lock guard(_lock);
			_pouches.NoteSettled(a_isLeft);
		}

		// Back where it came from, so the draw it came out of is over and the next release
		// at this pouch is a new gesture rather than the tail of that one.
		const int hand = IsSecondaryHand(a_isLeft) ? 1 : 0;
		_drawnFrom[hand] = 0;
		_drawnAt[hand] = 0;

		Loc::Info(Keys::kDropTaken, a_slot, HandName(a_isLeft));
	}

	void Mod::WatchInput()
	{
		if (_watchingInput) {
			return;
		}
		auto* manager = RE::BSInputDeviceManager::GetSingleton();
		if (manager == nullptr) {
			return;
		}
		manager->AddEventSink(&_input);
		_watchingInput = true;
		Loc::Info(Keys::kInputWatch, _settings.drawButton);

		// Which hand VRIK's "secondary" is taken to mean here, and the setting it is read
		// from. Said out loud because the reading is ours and not VRIK's: its own scripts
		// call the right hand primary whatever the game's left-handed setting says, so a
		// left-handed player may well be told the wrong hand - and nobody can see that
		// unless what was read is in the log beside what was done with it.
		const auto* setting = RE::GetINISetting("bLeftHandedMode:VRInput");
		Loc::Info(Keys::kHandedness, setting != nullptr && setting->GetBool(),
			HandName(IsLeftHand(true)));
	}

	RE::BSEventNotifyControl Mod::Input::ProcessEvent(RE::InputEvent* const* a_event,
		RE::BSTEventSource<RE::InputEvent*>*)
	{
		if (a_event == nullptr) {
			return RE::BSEventNotifyControl::kContinue;
		}

		auto& mod = GetSingleton();
		if (!mod.Working()) {
			return RE::BSEventNotifyControl::kContinue;
		}

		for (auto* event = *a_event; event != nullptr; event = event->next) {
			auto* button = event->AsButtonEvent();
			if (button == nullptr || !button->IsDown()) {
				continue;
			}

			bool isLeft = false;
			switch (event->GetDevice()) {
			case RE::INPUT_DEVICE::kVRLeft:
				isLeft = true;
				break;
			case RE::INPUT_DEVICE::kVRRight:
				isLeft = false;
				break;
			default:
				continue;  // keyboard, mouse, gamepad: not a hand at a pouch
			}

			// Every press carries its real id into the log, so that the button can be
			// named from a run instead of guessed at from a table. Where it is said
			// depends on where the hand was: at a pouch and at any other slot of VRIK's
			// out loud, because the first question a run has to answer is which ids this
			// game sends at all, and a line that only ever appears at a pouch cannot
			// answer it; everywhere else quietly, because that is every press in the game.
			const int id = static_cast<int>(button->GetIDCode());
			const int slot = mod.PouchAtHand(isLeft, false);
			if (slot == 0) {
				const int reached = mod._reach[IsSecondaryHand(isLeft) ? 1 : 0];
				if (reached != 0) {
					Loc::Info(Keys::kButtonAtSlot, HandName(isLeft), id, reached);
				} else {
					Loc::Debug(Keys::kButtonElsewhere, HandName(isLeft), id);
				}
				continue;
			}

			Loc::Info(Keys::kButtonAtPouch, HandName(isLeft), id, slot);
			if (id != mod._settings.drawButton) {
				continue;
			}

			// Out of the input handler and onto the game queue: taking an item out of
			// the inventory is not work to start inside an event of somebody else.
			if (auto* tasks = SKSE::GetTaskInterface(); tasks != nullptr) {
				tasks->AddTask([slot, isLeft]() { GetSingleton().DrawAt(slot, isLeft); });
			}
		}

		return RE::BSEventNotifyControl::kContinue;
	}

	bool Mod::OnHolsterAttempt(int a_slot, bool a_secondaryHand, bool a_handOccupied)
	{
		// Before anything is decided, so that the log answers the first question any run
		// asks: was this callback called at all? Said at info and not at debug on
		// purpose - a line that only appears when somebody remembered to raise the log
		// level is a line that is missing from the run that needed it.
		Loc::Info(Keys::kHolsterOffered, a_slot, a_secondaryHand, a_handOccupied);

		auto& mod = GetSingleton();
		if (!mod.Working()) {
			Loc::Debug(Keys::kIdleHere);
			return true;  // not our business: let VRIK do what it always did
		}

		// Run 3 ended with the slots never arranged, because neither kNewGame nor
		// kPostLoadGame ever reached this plugin. Whatever the reason for that turns out
		// to be, a reach proves a game is running, and it is a better moment to notice
		// than never.
		if (!mod._slotsArranged) {
			if (auto* tasks = SKSE::GetTaskInterface(); tasks != nullptr) {
				Loc::Warn(Keys::kSlotsLate);
				tasks->AddTask([]() {
					auto& late = GetSingleton();
					late.ApplySlots();
					late.StartPolling();
				});
			}
		}

		const bool isLeft = IsLeftHand(a_secondaryHand);

		Core::Reach reach;
		reach.slot = a_slot;
		reach.leftHand = isLeft;
		reach.handOccupied = a_handOccupied;
		reach.handCanHold = mod._higgs.CanGrab(isLeft);

		Core::Decision decision;
		{
			std::scoped_lock guard(mod._lock);
			decision = mod._pouches.Decide(reach, mod._pack);
		}

		// The whole point of the core is in this one value, so it is said before anything
		// is done with it: act, reason, hand, and the bool VRIK is about to be given.
		Loc::Info(Keys::kDecision, decision.slot, Core::Name(decision.act),
			Core::Name(decision.reason), HandName(isLeft), decision.LetVrikAct());

		// VRIK is waiting for an answer this very frame, so the decision is made here
		// and the doing is put on the game's task queue. Removing an item from the
		// inventory and placing a reference is not work to start inside somebody else's
		// callback.
		switch (decision.act) {
		case Core::Act::Draw:
			if (auto* tasks = SKSE::GetTaskInterface(); tasks != nullptr) {
				tasks->AddTask([slot = decision.slot, isLeft, item = decision.item]() {
					GetSingleton().Draw(slot, isLeft, item);
				});
				Loc::Info(Keys::kTaskQueued, decision.slot);
			} else {
				Loc::Error(Keys::kNoTasks, decision.slot);
			}
			break;

		case Core::Act::Stow:
		case Core::Act::Assign:
			if (auto* tasks = SKSE::GetTaskInterface(); tasks != nullptr) {
				const bool assigning = decision.act == Core::Act::Assign;
				tasks->AddTask([slot = decision.slot, isLeft, assigning]() {
					GetSingleton().TakeBack(slot, isLeft, assigning);
				});
				Loc::Info(Keys::kTaskQueued, decision.slot);
			} else {
				Loc::Error(Keys::kNoTasks, decision.slot);
			}
			break;

		case Core::Act::Refuse:
			if (decision.reason == Core::Reason::NothingInPack) {
				Loc::Debug(Keys::kPouchEmpty, decision.slot);
			}
			break;

		case Core::Act::PassToVrik:
		default:
			break;
		}

		return decision.LetVrikAct();
	}

	void Mod::OnConsumed(bool a_isLeft, ::TESForm*)
	{
		Loc::Info(Keys::kHiggsEvent, "consumed", HandName(a_isLeft));

		auto& mod = GetSingleton();
		std::scoped_lock guard(mod._lock);
		if (const auto slot = mod._pouches.SlotOfHand(a_isLeft); slot.has_value()) {
			Loc::Info(Keys::kPouchConsumed, *slot);
			mod._pouches.NoteSettled(a_isLeft);
		}
	}

	void Mod::OnStashed(bool a_isLeft, ::TESForm*)
	{
		Loc::Info(Keys::kHiggsEvent, "stashed", HandName(a_isLeft));

		auto& mod = GetSingleton();
		std::scoped_lock guard(mod._lock);
		if (const auto slot = mod._pouches.SlotOfHand(a_isLeft); slot.has_value()) {
			Loc::Info(Keys::kPouchReturned, *slot);
			mod._pouches.NoteSettled(a_isLeft);
		}
	}

	void Mod::OnDropped(bool a_isLeft, ::TESObjectREFR* a_refr)
	{
		Loc::Info(Keys::kHiggsEvent, "dropped", HandName(a_isLeft));

		auto& mod = GetSingleton();
		if (!mod.Working()) {
			return;
		}

		// Letting go of something at a pouch is how something goes into it. This is the
		// event VRIK never gives: its holster callback is part of its weapon logic and
		// stays silent for a hand holding a potion, however long the hand is held there.
		if (const int slot = mod.PouchAtHand(a_isLeft, true); slot != 0 && a_refr != nullptr) {
			// The squeeze that draws is the squeeze that holds, so letting go at the pouch
			// a moment after drawing is the end of that gesture and not a new one. It is
			// still taken in - the bottle belongs in the pack either way - but it is said
			// under its own name, so that a run can tell "the press did nothing" from "the
			// press did both halves at once, too quickly to see".
			if (const auto since = mod.SinceDrawnFrom(a_isLeft, slot);
				since >= 0 && since <= mod._settings.settleMs) {
				Loc::Info(Keys::kDropBounced, HandName(a_isLeft), slot, since);
			} else {
				Loc::Info(Keys::kDropAtPouch, HandName(a_isLeft), slot);
			}

			// By id and not by pointer: the reference is handed to a task that runs
			// later, and what HIGGS let go of may be gone by then.
			const auto id = reinterpret_cast<RE::TESObjectREFR*>(a_refr)->GetFormID();
			if (auto* tasks = SKSE::GetTaskInterface(); tasks != nullptr) {
				tasks->AddTask([slot, a_isLeft, id]() {
					GetSingleton().StowDropped(slot, a_isLeft,
						RE::TESForm::LookupByID<RE::TESObjectREFR>(id));
				});
			}
			return;
		}

		std::scoped_lock guard(mod._lock);
		if (const auto slot = mod._pouches.SlotOfHand(a_isLeft); slot.has_value()) {
			// It stays where it fell. That is the whole of it: the bottle is an
			// ordinary thing in the world now, and picking it up is the player's
			// business.
			Loc::Info(Keys::kPouchLost, *slot);
			mod._pouches.NoteSettled(a_isLeft);
		}
	}
}
