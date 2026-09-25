#include "Mod.h"

#include "Loc.h"
#include "Paths.h"
#include "core/SlotPlan.h"
#include "game/Body.h"
#include "game/Forms.h"

#include <SKSE/SKSE.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <span>
#include <string>

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

		// How often the pouch is asked what it should show. It costs a walk of the
		// inventory; a bottle drawn or put away asks at once, so this only has to catch
		// what changes by other means - a potion bought, found, or drunk from the menu.
		constexpr std::int64_t kDisplayEvery = 1000;

		// How long to give HIGGS before asking whether the hand really closed on the
		// bottle. Long enough for a frame or two, short enough to be about that bottle.
		constexpr std::int64_t kGrabCheckMs = 200;

		// The grip, as the VR controllers number their buttons. Not a setting: nothing is
		// done on it any more but a measurement.
		constexpr int kGripButton = 2;

		constexpr auto kHeadBone = "NPC Head [Head]";
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
		_higgs.OnGrabbed(&Mod::OnGrabbed);
		Loc::Info(Keys::kHiggsSubscribed);

		// The frame, and with it the end of this mod having a thread of its own.
		_higgs.OnFrame(&Mod::OnFrame);
	}

	void Mod::OnDataLoaded()
	{
		_settings = LoadSettings();
		Loc::SetLevel(_settings.logLevel);
		Loc::Load(Paths::LangDir(), _settings.language);
		BuildPouches(_settings);
		WatchInput();

		// The picture. Our plugin has one art, so one pouch can show what it holds: the
		// first one a slot was given over to. A shared slot goes on showing whatever
		// VRIK keeps there - painting a bottle over the player's own sword would take
		// away something they put there themselves.
		for (const auto& setting : _settings.pouches) {
			if (Settings::ModeFromText(setting.mode) != Core::Mode::Exclusive) {
				continue;
			}
			if (_picture.Slot() != 0) {
				Loc::Info(Keys::kPictureOnlyOne, setting.slot, _picture.Slot());
				continue;
			}
			if (_picture.Load(setting.slot) && Working()) {
				// Once for the whole game: VRIK keeps this in its DLL's memory, and after
				// a load its scripts give it back only their own arts, never anyone else's.
				_vrik.SetArt(setting.slot, _picture.Art());
				Loc::Info(Keys::kPictureGiven, setting.slot);
			}
		}
	}

	void Mod::OnFrame()
	{
		auto& mod = GetSingleton();
		if (!mod.Working()) {
			return;
		}

		if (!mod._frameSeen) {
			mod._frameSeen = true;
			mod.FirstFrame();
		}

		mod.NoteReach();
		mod.RefreshDisplay();
	}

	void Mod::FirstFrame()
	{
		Loc::Info(Keys::kFrameAlive);

		// A new game raises no message this plugin ever receives: run 7 started one and
		// the slot stayed dead for twelve minutes, until the first reach VRIK let through.
		// Suspension lasts until the game is closed, so once, here, is enough.
		if (!_slotsArranged) {
			Loc::Info(Keys::kSlotsFirstFrame);
			ApplySlots();
		}

		DescribeSlots();
		_picture.Reset(Now());
	}

	void Mod::NoteReach()
	{
		const auto now = Now();

		for (int hand = 0; hand < 2; ++hand) {
			const bool secondary = hand == 1;

			// A bottle handed to this hand and never taken. The other ending - the hand did
			// close on it - arrives as an event of its own and clears this, so what is left
			// here when the time is up is a failure and nothing else.
			if (_checkGrabAt[hand] != 0 && now >= _checkGrabAt[hand]) {
				_checkGrabAt[hand] = 0;
				Loc::Warn(Keys::kGrabFailed, HandName(IsLeftHand(secondary)), _drawnFrom[hand]);
			}

			const int slot = _vrik.SlotInReach(secondary);
			if (slot == _reach[hand]) {
				continue;  // only changes are worth a line; this runs every frame
			}
			_reach[hand] = slot;
			Loc::Info(Keys::kReachChanged, HandName(IsLeftHand(secondary)), slot,
				_vrik.CanBeHolstered(secondary));
		}
	}

	void Mod::RefreshDisplay()
	{
		if (!_picture.Ready()) {
			return;
		}

		const auto now = Now();
		const int  slot = _picture.Slot();

		if (now >= _displayAt) {
			_displayAt = now + kDisplayEvery;

			// The picture says "there is a bottle here to take", so it is only ever what
			// the pack really holds for this pouch - up while there is one, down the moment
			// there is not, and nothing at all for a pouch nobody has set up yet.
			std::string model;
			std::string what;
			{
				std::scoped_lock guard(_lock);
				const auto shown = _pouches.Display(slot, _pack);
				auto*      form = shown.anything ? Game::Lookup(shown.item) : nullptr;
				if (auto* potion = form != nullptr ? form->As<RE::AlchemyItem>() : nullptr; potion != nullptr) {
					const char* path = potion->GetModel();
					const char* name = potion->GetName();
					model = path != nullptr ? path : "";
					what = name != nullptr ? name : "";
				}
			}
			_picture.Want(model, what);
		}

		_picture.Tick(now, _vrik.IsDisplayed(slot));
	}

	int Mod::PouchAt(bool a_isLeft)
	{
		const int slot = _vrik.SlotInReach(IsSecondaryHand(a_isLeft));
		if (slot == 0) {
			return 0;
		}
		std::scoped_lock guard(_lock);
		return _pouches.Find(slot) != nullptr ? slot : 0;
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
		// Again here and not only at the first frame: that frame may come in the start
		// cave, where the player has no body yet to measure the slot against.
		DescribeSlots();
		_picture.Reset(Now());
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
				// nor holsters one into it. A suspended slot is also one an empty hand
				// sees at all: without this, VRIK looks straight past a free hand at an
				// empty slot and the pouch raises nothing.
				_vrik.SetSuspended(setting.slot, true);
			}
		}

		_slotsArranged = true;
	}

	void Mod::DescribeSlots()
	{
		auto*       player = RE::PlayerCharacter::GetSingleton();
		const float feet = player != nullptr ? player->GetPositionZ() : 0.0f;
		const auto  head = Game::Body::BoneNamed(kHeadBone);

		for (const auto& setting : _settings.pouches) {
			const char* boneName = Game::Body::BoneOf(setting.slot);
			const auto  bone = Game::Body::Bone(setting.slot);

			// Where VRIK has the slot, in its own numbers - said even without a body, since
			// they are what shows whether VRIK read a moved slot at all - and, with a body,
			// as heights a person can picture: "a hand below the head" says more than three
			// coordinates do.
			const auto pos = _vrik.SlotPosition(setting.slot);
			if (!bone) {
				Loc::Warn(Keys::kBoneMissing, setting.slot, boneName != nullptr ? boneName : "?",
					pos.x, pos.y, pos.z);
				continue;
			}
			const auto centre = Game::Body::ToWorld(*bone, pos);
			Loc::Info(Keys::kSlotWhere, setting.slot, boneName, pos.x, pos.y, pos.z, centre.z - feet,
				head ? head->translate.z - centre.z : 0.0f, bone->scale);

			// Which way the bone's own axes point. The numbers in vrikslots.ini are along
			// these, and which of them runs down the body is up to the skeleton, not VRIK.
			const auto x = Game::Body::Axis(*bone, 0);
			const auto y = Game::Body::Axis(*bone, 1);
			const auto z = Game::Body::Axis(*bone, 2);
			Loc::Info(Keys::kBoneAxes, boneName, x.x, x.y, x.z, y.x, y.y, y.z, z.x, z.y, z.z);
		}

		if (player != nullptr) {
			const float yaw = player->GetAngleZ();
			Loc::Info(Keys::kFacing, std::sin(yaw), std::cos(yaw));
		}
	}

	void Mod::Measure(bool a_isLeft)
	{
		RE::NiPoint3 hand;
		const char*  node = HandAt(a_isLeft, hand);
		if (node == nullptr) {
			return;
		}

		auto*       player = RE::PlayerCharacter::GetSingleton();
		const float feet = player != nullptr ? player->GetPositionZ() : 0.0f;

		for (const auto& setting : _settings.pouches) {
			const auto bone = Game::Body::Bone(setting.slot);
			if (!bone) {
				continue;
			}
			// The numbers to write into vrikslots.ini to put the pouch exactly where the
			// hand is now, beside where the pouch is.
			const auto here = Game::Body::ToSlot(*bone, hand);
			const auto centre = Game::Body::ToWorld(*bone, _vrik.SlotPosition(setting.slot));
			Loc::Info(Keys::kSqueezeMeasured, HandName(a_isLeft), setting.slot, here.x, here.y, here.z,
				hand.GetDistance(centre), hand.z - feet, centre.z - feet, node);
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

	const char* Mod::HandAt(bool a_isLeft, RE::NiPoint3& a_out)
	{
		auto* player = RE::PlayerCharacter::GetSingleton();
		auto* root = player != nullptr ? player->Get3D() : nullptr;
		if (root == nullptr) {
			return nullptr;
		}

		for (const char* name : (a_isLeft ? std::span<const char* const>(kLeftNodes) : std::span<const char* const>(kRightNodes))) {
			if (auto* node = root->GetObjectByName(name); node != nullptr) {
				a_out = node->world.translate;
				return name;
			}
		}
		return nullptr;
	}

	bool Mod::HandPosition(bool a_isLeft, RE::NiPoint3& a_out)
	{
		const char* node = HandAt(a_isLeft, a_out);
		if (node == nullptr) {
			Loc::Warn(Keys::kHandNotFound, HandName(a_isLeft));
			return false;
		}
		Loc::Info(Keys::kHandNode, HandName(a_isLeft), node);
		return true;
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

		auto*        player = RE::PlayerCharacter::GetSingleton();
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
		{
			std::scoped_lock guard(_lock);
			_pouches.NoteDrawn(a_isLeft, a_slot, a_item);
		}

		const int hand = IsSecondaryHand(a_isLeft) ? 1 : 0;
		_drawnFrom[hand] = a_slot;
		_checkGrabAt[hand] = Now() + kGrabCheckMs;
		_displayAt = 0;  // the last bottle of its kind may just have left the pack

		Loc::Info(Keys::kPouchDrawn, a_slot, HandName(a_isLeft));
		return true;
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

		// A reference in the world is not always one bottle. Asked once, here, and used
		// both for the decision and for the picking up.
		const int count = std::max(1, a_object->extraList.GetCount());

		auto item = Game::Describe(potion);
		item.count = count;

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
		if (player == nullptr) {
			return;
		}

		// THE ENGINE ALREADY KNOWS HOW TO PICK A THING UP, AND THIS USED NOT TO USE IT.
		// What stood here was AddObjectToContainer for one, then Disable and SetDelete on
		// the reference - which looks like the same thing and is not. A reference in the
		// world can stand for more than one bottle, so a pile of five went into the pack
		// as one and the other four were deleted: the mod took the player's potions away.
		// PickUpObject counts, keeps whatever else the reference carried, and makes the
		// sound the game makes when anything else is picked up.
		player->PickUpObject(a_object, count, false, true);

		{
			std::scoped_lock guard(_lock);
			_pouches.NoteSettled(a_isLeft);
		}

		_drawnFrom[IsSecondaryHand(a_isLeft) ? 1 : 0] = 0;
		_displayAt = 0;  // a pouch just set up has something to show at once

		Loc::Info(Keys::kDropTaken, a_slot, HandName(a_isLeft), count);
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
		Loc::Info(Keys::kInputWatch, kGripButton);

		// Which hand VRIK's "secondary" is taken to mean here, and the setting it is read
		// from. Said out loud because the reading is ours and not VRIK's, and nobody can
		// check it unless what was read is in the log beside what was done with it.
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
				continue;  // keyboard, mouse, gamepad: not a hand
			}

			// Every press carries its real id into the log: out loud at any slot of VRIK's,
			// quietly everywhere else, because everywhere else is every press in the game.
			const int id = static_cast<int>(button->GetIDCode());
			const int reached = mod._reach[IsSecondaryHand(isLeft) ? 1 : 0];
			if (reached != 0) {
				Loc::Info(Keys::kButtonAtSlot, HandName(isLeft), id, reached);
			} else {
				Loc::Debug(Keys::kButtonElsewhere, HandName(isLeft), id);
			}

			// The grip of an empty hand is measured wherever the hand is: the place the
			// player reaches for is exactly the place the pouch is not yet. Out of the
			// input handler and onto the game queue, like everything that reads the body.
			if (id == kGripButton && !mod._higgs.IsHolding(isLeft)) {
				if (auto* tasks = SKSE::GetTaskInterface(); tasks != nullptr) {
					tasks->AddTask([isLeft]() { GetSingleton().Measure(isLeft); });
				}
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
		if (decision.act == Core::Act::Draw) {
			if (auto* tasks = SKSE::GetTaskInterface(); tasks != nullptr) {
				tasks->AddTask([slot = decision.slot, isLeft, item = decision.item]() {
					GetSingleton().Draw(slot, isLeft, item);
				});
				Loc::Info(Keys::kTaskQueued, decision.slot);
			} else {
				Loc::Error(Keys::kNoTasks, decision.slot);
			}
		} else if (decision.act == Core::Act::Refuse && decision.reason == Core::Reason::NothingInPack) {
			// An empty hand pulled out of the pouch and came back with nothing: worth its
			// own line, because to the player it looks exactly like a pouch that is broken.
			Loc::Info(Keys::kPouchEmpty, decision.slot);
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
			mod._displayAt = 0;  // the bottle is back in the pack, and may be the only one
		}
	}

	void Mod::OnGrabbed(bool a_isLeft, ::TESObjectREFR*)
	{
		auto&     mod = GetSingleton();
		const int hand = IsSecondaryHand(a_isLeft) ? 1 : 0;

		// This fires for everything the player picks up, so it is only worth a word when
		// a bottle of ours is waiting to be told whether it was taken.
		if (mod._checkGrabAt[hand] == 0) {
			Loc::Debug(Keys::kHiggsEvent, "grabbed", HandName(a_isLeft));
			return;
		}

		mod._checkGrabAt[hand] = 0;
		Loc::Info(Keys::kGrabConfirmed, HandName(a_isLeft), mod._drawnFrom[hand]);
	}

	void Mod::OnDropped(bool a_isLeft, ::TESObjectREFR* a_refr)
	{
		Loc::Info(Keys::kHiggsEvent, "dropped", HandName(a_isLeft));

		auto& mod = GetSingleton();
		if (!mod.Working()) {
			return;
		}

		// Letting go of something inside a pouch is how it goes in. VRIK is asked where
		// the hand is at this very moment, and nothing is remembered: the second and a
		// fifth of memory this used to have turned bottles carried away from the pouch
		// into bottles put back.
		if (const int slot = mod.PouchAt(a_isLeft); slot != 0 && a_refr != nullptr) {
			Loc::Info(Keys::kDropAtPouch, HandName(a_isLeft), slot);

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
