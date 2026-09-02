#include "Log.h"

#include <spdlog/sinks/basic_file_sink.h>

#include <memory>

namespace Envoy
{
	namespace
	{
		spdlog::level::level_enum ToLevel(std::string_view a_level)
		{
			if (a_level == "trace") {
				return spdlog::level::trace;
			}
			if (a_level == "debug") {
				return spdlog::level::debug;
			}
			if (a_level == "warning" || a_level == "warn") {
				return spdlog::level::warn;
			}
			if (a_level == "error") {
				return spdlog::level::err;
			}
			return spdlog::level::info;
		}
	}

	void Log::Init(std::string_view a_level)
	{
		auto path = SKSE::log::log_directory();
		if (!path) {
			return;
		}

		*path /= PLUGIN_NAME;
		*path += ".log";

		auto sink = std::make_shared<spdlog::sinks::basic_file_sink_mt>(path->string(), true);
		auto logger = std::make_shared<spdlog::logger>("global log", std::move(sink));

		const auto level = ToLevel(a_level);
		logger->set_level(level);
		logger->flush_on(level);
		spdlog::set_default_logger(std::move(logger));
	}
}
