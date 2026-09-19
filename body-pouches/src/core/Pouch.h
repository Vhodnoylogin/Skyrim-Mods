#pragma once

#include "core/ItemKey.h"

namespace BodyPouches::Core
{
	// How much of a slot the pouch claims.
	//
	// These are not two flavours of one setting: they are the two instruments VRIK
	// gives us, and each has a price.
	//
	//   Shared - the slot stays a VRIK slot. A sword in it is drawn by VRIK as
	//   always, and only our item is ours. Costs nothing, and an empty pouch simply
	//   steps aside.
	//
	//   Exclusive - the slot is ours whatever is in it; the adapter also suspends it
	//   in VRIK so that VRIK neither draws from it nor shows a weapon there. An empty
	//   pouch then refuses rather than stepping aside, because stepping aside would
	//   hand the player a sword out of a place they are using as a potion pouch.
	enum class Mode
	{
		Shared,
		Exclusive
	};

	// One pouch: a place on the body, what it is told to hold, and how much of it is
	// left.
	//
	// COUNT AND OUTSTANDING ARE DIFFERENT NUMBERS. A flask that has been put in the
	// hand has left the pouch but has not been drunk: it may come back. Counting it
	// as spent at the moment it is drawn loses a flask every time somebody takes one
	// out and changes their mind; counting it as still in the pouch lets two hands
	// draw the same last flask. So it leaves `count` and enters `outstanding`, and it
	// is one of the three endings - drunk, put back, lost - that settles it.
	class Pouch
	{
	public:
		Pouch() = default;
		Pouch(int a_slot, ItemKey a_item, ItemKind a_kind, int a_capacity, Mode a_mode);

		[[nodiscard]] int      Slot() const noexcept { return _slot; }
		[[nodiscard]] Mode     PouchMode() const noexcept { return _mode; }
		[[nodiscard]] const ItemKey& Item() const noexcept { return _item; }
		[[nodiscard]] ItemKind Kind() const noexcept { return _kind; }
		[[nodiscard]] int      Count() const noexcept { return _count; }
		[[nodiscard]] int      Capacity() const noexcept { return _capacity; }
		[[nodiscard]] int      Outstanding() const noexcept { return _outstanding; }

		[[nodiscard]] bool IsConfigured() const noexcept { return _slot > 0 && _item.IsSet(); }
		[[nodiscard]] bool HasSomethingToGive() const noexcept { return _count > 0; }
		[[nodiscard]] bool HasRoom() const noexcept { return _count + _outstanding < _capacity; }

		// Does this pouch hold that particular thing? An empty plugin in the pouch's
		// key means "any plugin", which is how a rule like "any potion from any mod"
		// is written; it is the only wildcard the core knows.
		[[nodiscard]] bool Accepts(const ItemKey& a_item) const noexcept;

		void SetCount(int a_count) noexcept;

		// The three endings. Each of them closes exactly one outstanding item, and
		// none of them may be called for an item this pouch never gave out - the
		// caller is the adapter, and a double report there would silently invent or
		// destroy flasks.
		void Drawn() noexcept;      // left the pouch, is in a hand
		void Consumed() noexcept;   // drunk or eaten; it is not coming back
		void PutBack() noexcept;    // returned to the pouch
		void Lost() noexcept;       // dropped, thrown, or the reference went away

		// Filling the pouch from outside a draw - the player restocking, or the
		// adapter topping it up out of the inventory. Returns how many actually fit.
		int Fill(int a_howMany) noexcept;

	private:
		int      _slot{};
		ItemKey  _item{};
		ItemKind _kind{ ItemKind::Unknown };
		int      _capacity{};
		Mode     _mode{ Mode::Shared };

		int _count{};        // in the pouch, ready to be taken
		int _outstanding{};  // out of the pouch, in a hand, not yet settled
	};
}
