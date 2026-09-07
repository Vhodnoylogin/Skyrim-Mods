#include "Speak.h"

#include "Bridge.h"
#include "Config.h"
#include "Service.h"

#include <RE/Skyrim.h>
#include <SKSE/SKSE.h>

#include <nlohmann/json.hpp>
#include <httplib.h>

namespace Voice
{
	void Speak(const std::string& a_text, std::int32_t a_speechId)
	{
		const auto& config = Config::Get();
		auto&       bridge = Bridge::Get();

		for (const auto& model : config.models) {
			if (!model.enabled || model.id != config.speakModel) {
				continue;
			}
			const Service   service(model);
			const auto&     ep = service.Where();
			httplib::Client client(ep.host, ep.port);
			client.set_read_timeout(config.sayTimeoutSec, 0);
			nlohmann::json payload{ { "text", a_text } };
			auto           res = client.Post("/say", payload.dump(), "application/json");

			const bool ok = res && res->status == 200;
			SKSE::log::info("озвучка {}: {}", a_speechId, ok ? "сказано" : "не вышло");
			bridge.PushSpeechDone(a_speechId, ok, false);
			return;
		}

		SKSE::log::warn("озвучка {}: модель {} не включена", a_speechId, config.speakModel);
		bridge.PushSpeechDone(a_speechId, false, false);
	}
}
