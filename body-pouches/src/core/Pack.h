#pragma once

#include "core/Filter.h"
#include "core/Item.h"

#include <vector>

namespace BodyPouches::Core
{
	// The player's pack, as far as the core is concerned: one question, asked of
	// somebody who can see the game.
	//
	// THIS INTERFACE IS THE WHOLE REASON THE MOD HAS NO BOOKKEEPING. A pouch could
	// have been a container with its own contents, filled and refilled and saved and
	// reconciled - and then every one of those words would have been a way for it to
	// disagree with the pack it was supposed to reflect. Selling potions to a merchant
	// would have emptied the pack and not the belt; a save loaded out of order would
	// have restored a belt holding bottles that no longer exist.
	//
	// So a pouch owns nothing. It asks, every time it needs to know, and the answer is
	// the truth by construction.
	class Pack
	{
	public:
		Pack() = default;
		Pack(const Pack&) = default;
		Pack(Pack&&) = default;
		Pack& operator=(const Pack&) = default;
		Pack& operator=(Pack&&) = default;
		virtual ~Pack() = default;

		// Every kind of item in the pack the filter accepts, each with how many there
		// are. Order is the pack's own; the core does not assume it means anything.
		[[nodiscard]] virtual std::vector<Item> Matching(const Filter& a_filter) const = 0;
	};
}
