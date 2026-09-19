#include "core/Pouch.h"

#include <algorithm>

namespace BodyPouches::Core
{
	Pouch::Pouch(int a_slot, ItemKey a_item, ItemKind a_kind, int a_capacity, Mode a_mode) :
		_slot(a_slot),
		_item(std::move(a_item)),
		_kind(a_kind),
		_capacity(std::max(0, a_capacity)),
		_mode(a_mode)
	{}

	bool Pouch::Accepts(const ItemKey& a_item) const noexcept
	{
		if (!_item.IsSet() || !a_item.IsSet()) {
			return false;
		}
		if (_item.localId != a_item.localId) {
			return false;
		}
		// An empty plugin on our side is the wildcard; on the offered item it is
		// not, because an item that does not know where it came from is not a
		// thing we can put back later.
		return _item.plugin.empty() || _item.plugin == a_item.plugin;
	}

	void Pouch::SetCount(int a_count) noexcept
	{
		_count = std::clamp(a_count, 0, _capacity);
	}

	void Pouch::Drawn() noexcept
	{
		if (_count > 0) {
			--_count;
			++_outstanding;
		}
	}

	void Pouch::Consumed() noexcept
	{
		if (_outstanding > 0) {
			--_outstanding;
		}
	}

	void Pouch::PutBack() noexcept
	{
		if (_outstanding > 0) {
			--_outstanding;
			if (_count < _capacity) {
				++_count;
			}
		}
	}

	void Pouch::Lost() noexcept
	{
		Consumed();  // the same arithmetic; the difference is only what the log says
	}

	int Pouch::Fill(int a_howMany) noexcept
	{
		if (a_howMany <= 0) {
			return 0;
		}
		const int room = _capacity - _count - _outstanding;
		const int took = std::clamp(a_howMany, 0, std::max(0, room));
		_count += took;
		return took;
	}
}
