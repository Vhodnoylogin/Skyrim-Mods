#pragma once

#include "core/Filter.h"

namespace BodyPouches::Core
{
	// How much of a VRIK slot the pouch claims.
	//
	// These are not two flavours of one setting: they are the two instruments VRIK
	// gives us, and each has a price.
	//
	//   Shared - the slot stays a VRIK slot. A sword in it is drawn by VRIK as always,
	//   and only our potion is ours. Costs nothing, and a pouch with an empty pack
	//   simply steps aside.
	//
	//   Exclusive - the slot is ours whatever is in it; the adapter also suspends it in
	//   VRIK so that VRIK neither draws from it nor shows a weapon there. A pouch with
	//   an empty pack then refuses rather than stepping aside, because stepping aside
	//   would hand the player a sword out of a place they are using for potions.
	enum class Mode
	{
		Shared,
		Exclusive
	};

	// One pouch: a place on the body and a standing question put to the pack.
	//
	// It holds no potions. See Pack.h for why that is the whole design and not a
	// simplification.
	class Pouch
	{
	public:
		Pouch() = default;
		Pouch(int a_slot, Mode a_mode) :
			_slot(a_slot), _mode(a_mode) {}
		Pouch(int a_slot, Filter a_filter, Mode a_mode) :
			_slot(a_slot), _filter(std::move(a_filter)), _mode(a_mode) {}

		[[nodiscard]] int           Slot() const noexcept { return _slot; }
		[[nodiscard]] Mode          PouchMode() const noexcept { return _mode; }
		[[nodiscard]] const Filter& PouchFilter() const noexcept { return _filter; }
		[[nodiscard]] bool          IsAssigned() const noexcept { return _slot > 0 && _filter.IsSet(); }

		// Setting up by hand: the bottle pushed into an empty slot says what the pouch
		// is for from now on.
		void Assign(Filter a_filter) { _filter = std::move(a_filter); }

		// Deliberately NOT called when the pack runs out. A pouch that forgot what it
		// was for every time the last potion was drunk would forget exactly when the
		// shop is furthest away.
		void Forget() noexcept { _filter = {}; }

	private:
		int    _slot{};
		Filter _filter{};
		Mode   _mode{ Mode::Shared };
	};
}
