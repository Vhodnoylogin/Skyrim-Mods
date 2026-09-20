#include "Mod.h"

#include "Loc.h"
#include "Paths.h"
#include "core/SlotPlan.h"
#include "game/Forms.h"

#include <SKSE/SKSE.h>

#include <array>
#include <span>

namespace BodyPouches
{
	namespace
	{
		const char* HandName(bool a_isLeft) { return a_isLeft ? "left" : "right"; }

		// Where a bottle is put so that the hand can close on it. The first node that
		// exists wins; the VR wand nodes are tried first because in VR they are where
		// the controller actually is, and the skeleton hands follow them with a lag.
		constexpr std::array kLeftNodes{ "LeftWandNode", "NPC L Hand [LHnd]", "NPC L Finger02 [LF02]" };
		constexpr std::array kRightNodes{ "RightWandNode", "NPC R Hand [RHnd]", "NPC R Finger02 [RF02]" };
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
	}

	void Mod::OnGameLoaded()
	{
		// Said out loud on purpose. A run of this mod once ended with a log that stopped
		// after the settings were read, and nothing in it could tell "the message never
		// arrived" from "it arrived and every step of it quietly did nothing".
		Loc::Info(Keys::kGameLoaded, _settings.pouches.size());
		ApplySlots();
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
		auto* potion = base != nullptr ? base->As<RE::AlchemyItem>() : nullptr;
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

	void Mod::OnDropped(bool a_isLeft, ::TESObjectREFR*)
	{
		Loc::Info(Keys::kHiggsEvent, "dropped", HandName(a_isLeft));

		auto& mod = GetSingleton();
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
