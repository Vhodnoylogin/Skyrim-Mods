#pragma once

#include <SKSE/SKSE.h>

namespace BodyPouches::VR
{
	// How a mod asks another mod for its API.
	//
	// Both VRIK and HIGGS use the same trick and it is worth stating once: you send an
	// SKSE message addressed to them by name, with a pointer to a small struct; they
	// fill in a function pointer; you call it with the revision you want and get the
	// interface back. Each ships a .cpp that does this, but those are written against
	// the old SKSE64 messaging interface, so the four lines are done here through
	// CommonLibSSE instead. The message numbers are theirs and must not be invented.
	//
	// Must be called no earlier than SKSE's PostLoad, when every plugin is loaded and
	// able to answer.
	template <class TInterface, std::uint32_t TMessage>
	TInterface* AskFor(const char* a_modName)
	{
		struct Request
		{
			void* (*getApiFunction)(unsigned int revisionNumber) = nullptr;
		};

		auto* messaging = SKSE::GetMessagingInterface();
		if (messaging == nullptr) {
			return nullptr;
		}

		Request request;
		// The length passed here is sizeof(pointer), not sizeof(struct) - that is what
		// both authors' own code sends, and the receiver reads the pointer, so it is
		// their protocol rather than a mistake to be corrected.
		messaging->Dispatch(TMessage, static_cast<void*>(&request), sizeof(Request*), a_modName);
		if (request.getApiFunction == nullptr) {
			return nullptr;
		}
		return static_cast<TInterface*>(request.getApiFunction(1));
	}
}
