#include "Config.h"

#include "Loc.h"
#include "Paths.h"

#include <nlohmann/json.hpp>

#include <fstream>

namespace BodyPouches
{
	namespace
	{
		nlohmann::json ToJson(const Settings& a_settings)
		{
			nlohmann::json pouches = nlohmann::json::array();
			for (const auto& pouch : a_settings.pouches) {
				pouches.push_back({ { "slot", pouch.slot }, { "mode", pouch.mode } });
			}
			return nlohmann::json{
				{ "language", a_settings.language },
				{ "logLevel", a_settings.logLevel },
				{ "mayEnableSlots", a_settings.mayEnableSlots },
				{ "pouches", pouches },
			};
		}

		void Write(const std::filesystem::path& a_file, const Settings& a_settings)
		{
			std::error_code ec;
			std::filesystem::create_directories(a_file.parent_path(), ec);

			std::ofstream out(a_file, std::ios::binary);
			if (out) {
				out << ToJson(a_settings).dump(2) << "\n";
				Loc::Info(Keys::kConfigWritten, a_file.string());
			}
		}
	}

	Settings Settings::Defaults()
	{
		Settings settings;
		settings.pouches = {
			{ 13, "exclusive" },
		};
		return settings;
	}

	Core::Mode Settings::ModeFromText(const std::string& a_text) noexcept
	{
		return a_text == "exclusive" ? Core::Mode::Exclusive : Core::Mode::Shared;
	}

	Settings LoadSettings()
	{
		const auto file = Paths::ConfigFile();

		std::error_code ec;
		if (!std::filesystem::exists(file, ec)) {
			const auto defaults = Settings::Defaults();
			Write(file, defaults);
			return defaults;
		}

		try {
			std::ifstream in(file, std::ios::binary);
			nlohmann::json json;
			in >> json;

			Settings settings = Settings::Defaults();
			settings.pouches.clear();

			settings.language = json.value("language", settings.language);
			settings.logLevel = json.value("logLevel", settings.logLevel);
			settings.mayEnableSlots = json.value("mayEnableSlots", settings.mayEnableSlots);
			for (const auto& entry : json.value("pouches", nlohmann::json::array())) {
				Settings::PouchSetting pouch;
				pouch.slot = entry.value("slot", 0);
				pouch.mode = entry.value("mode", std::string{ "shared" });
				if (pouch.slot >= 1 && pouch.slot <= 14) {
					settings.pouches.push_back(std::move(pouch));
				}
			}

			Loc::Info(Keys::kConfigRead, file.string(), settings.pouches.size());
			return settings;
		} catch (const std::exception& e) {
			Loc::Error(Keys::kConfigBad, file.string(), e.what());
			return Settings::Defaults();
		}
	}
}
