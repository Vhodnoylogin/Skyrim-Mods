#include "Config.h"

#include <RE/Skyrim.h>
#include <SKSE/SKSE.h>

#include <nlohmann/json.hpp>

#include <filesystem>
#include <fstream>

namespace Voice
{
	namespace
	{
		constexpr auto kConfigPath = LR"(Data\SKSE\Plugins\envoy\adapters\voice\envoy-voice.json)";

		AutoStart ReadAutoStart(const nlohmann::json& a_doc)
		{
			AutoStart out;
			out.enabled = a_doc.value("enabled", out.enabled);
			out.exec = a_doc.value("exec", out.exec);
			out.workingDir = a_doc.value("workingDir", out.workingDir);
			out.parentPidArg = a_doc.value("parentPidArg", out.parentPidArg);
			out.waitSec = a_doc.value("waitSec", out.waitSec);
			out.pollSec = a_doc.value("pollSec", out.pollSec);
			for (const auto& arg : a_doc.value("args", nlohmann::json::array())) {
				out.args.push_back(arg.get<std::string>());
			}
			return out;
		}

		Model ReadModel(const nlohmann::json& a_doc)
		{
			Model out;
			out.id = a_doc.value("id", out.id);
			out.fast = a_doc.value("class", std::string{}) == "fast";
			out.enabled = a_doc.value("enabled", out.enabled);
			out.url = a_doc.value("url", out.url);
			out.language = a_doc.value("language", out.language);
			out.listenTimeoutSec = a_doc.value("listenTimeoutSec", out.listenTimeoutSec);
			if (a_doc.contains("autoStart")) {
				out.autoStart = ReadAutoStart(a_doc["autoStart"]);
			}
			return out;
		}
	}

	Config& Config::Mutable()
	{
		static Config instance;
		return instance;
	}

	const Config& Config::Get()
	{
		return Mutable();
	}

	bool Config::Load()
	{
		std::error_code ec;
		if (!std::filesystem::exists(kConfigPath, ec)) {
			SKSE::log::error("нет файла настроек: {}", std::filesystem::path{ kConfigPath }.string());
			return false;
		}

		nlohmann::json doc;
		auto&          self = Mutable();
		try {
			std::ifstream stream(kConfigPath);
			stream >> doc;

			const auto adapter = doc.value("adapter", nlohmann::json::object());
			self.adapterId = adapter.value("id", self.adapterId);
			self.adapterName = adapter.value("name", self.adapterName);
			self.adapterProvides = adapter.value("provides", self.adapterProvides);

			for (const auto& entry : doc.value("models", nlohmann::json::array())) {
				self.models.push_back(ReadModel(entry));
			}

			self.speakModel = doc.value("speakModel", self.speakModel);
			self.correlateMs = doc.value("correlateMs", self.correlateMs);
			self.retryDelayMs = doc.value("retryDelayMs", self.retryDelayMs);
			self.healthTimeoutSec = doc.value("healthTimeoutSec", self.healthTimeoutSec);
			self.listenGraceSec = doc.value("listenGraceSec", self.listenGraceSec);
			self.idleSleepMs = doc.value("idleSleepMs", self.idleSleepMs);
			self.sayTimeoutSec = doc.value("sayTimeoutSec", self.sayTimeoutSec);
			self.idMapLimit = doc.value("idMapLimit", self.idMapLimit);
		} catch (const std::exception& e) {
			SKSE::log::error("настройки не разобраны: {}", e.what());
			return false;
		}
		return true;
	}
}
