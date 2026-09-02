#include "TopicRouter.h"

#include "Utterance.h"
#include "core/Config.h"

#include <RE/Skyrim.h>

namespace Envoy
{
	namespace
	{
		bool DialogueOpen()
		{
			auto* ui = RE::UI::GetSingleton();
			if (!ui) {
				return false;
			}

			const auto names = Config::Get().Value<std::vector<std::string>>("/topics/dialogueMenuNames");
			if (!names) {
				return false;
			}

			for (const auto& name : *names) {
				if (ui->IsMenuOpen(name)) {
					return true;
				}
			}
			return false;
		}

		bool InCombat()
		{
			auto* player = RE::PlayerCharacter::GetSingleton();
			return player && player->IsInCombat();
		}
	}

	std::string TopicRouter::Pick(const Utterance& a_utterance)
	{
		const auto order = Config::Get().Value<std::vector<std::string>>("/topics/order");
		if (!order) {
			return "world";
		}

		for (const auto& name : *order) {
			if (name == "channel") {
				if (!a_utterance.channel.empty()) {
					return "channel:" + a_utterance.channel;
				}
			} else if (name == "dialogue") {
				if (DialogueOpen()) {
					return "dialogue";
				}
			} else if (name == "menu") {
				auto* ui = RE::UI::GetSingleton();
				if (ui && ui->GameIsPaused()) {
					return "menu";
				}
			} else if (name == "combat") {
				if (InCombat()) {
					return "combat";
				}
			} else if (name == "world") {
				return "world";
			}
		}

		return "world";
	}

	std::string TopicRouter::EventName(const std::string& a_topic)
	{
		if (a_topic.rfind("channel:", 0) == 0) {
			return "Envoy_Speech_Channel";
		}
		if (a_topic == "dialogue") {
			return "Envoy_Speech_Dialogue";
		}
		if (a_topic == "menu") {
			return "Envoy_Speech_Menu";
		}
		if (a_topic == "combat") {
			return "Envoy_Speech_Combat";
		}
		return "Envoy_Speech_World";
	}
}
