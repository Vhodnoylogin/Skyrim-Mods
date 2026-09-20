// body-pouches: the SKSE entry points, and nothing else.
//
// Everything this file does is arrange for Mod to exist and to be told about the two
// moments that matter: when every plugin is loaded (so VRIK and HIGGS can be asked for
// their interfaces), and when a save is loaded (so the pouches can be read back).
//
// The mod itself is Mod.cpp. The rule of the pouches is src/core, which knows nothing
// about any of this.

#include "Loc.h"
#include "Mod.h"

#include <RE/Skyrim.h>
#include <SKSE/SKSE.h>

#include <spdlog/sinks/basic_file_sink.h>

namespace
{
	void SetUpLog()
	{
		auto path = SKSE::log::log_directory();
		if (!path) {
			return;
		}
		*path /= std::format("{}.log", PLUGIN_NAME);

		auto sink = std::make_shared<spdlog::sinks::basic_file_sink_mt>(path->string(), true);
		auto log = std::make_shared<spdlog::logger>("global", std::move(sink));
		log->set_level(spdlog::level::info);
		log->flush_on(spdlog::level::info);
		spdlog::set_default_logger(std::move(log));
		spdlog::set_pattern("[%H:%M:%S.%e] [%l] %v");
	}

	void OnMessage(SKSE::MessagingInterface::Message* a_message)
	{
		if (a_message == nullptr) {
			return;
		}
		switch (a_message->type) {
		case SKSE::MessagingInterface::kPostPostLoad:
			// Every plugin has answered kPostLoad by now, which is the first moment every
			// plugin that replies to messages is certain to have registered its listener.
			//
			// Both the VRIK and the HIGGS header say to ask "after kPostLoad", and taking
			// them at their word is what the first run in the game died of: Dispatch simply
			// returned false for both, because at kPostLoad neither of them was listening
			// yet. Load order decides who is ready first, so kPostLoad is a race - and one
			// this plugin loses whenever it is loaded before the plugin it is asking.
			BodyPouches::Mod::GetSingleton().Connect();
			break;
		case SKSE::MessagingInterface::kDataLoaded:
			BodyPouches::Mod::GetSingleton().OnDataLoaded();
			break;
		case SKSE::MessagingInterface::kPostLoadGame:
		case SKSE::MessagingInterface::kNewGame:
			// Suspension in VRIK is runtime-only state by its author's design, so it
			// has to be asked for again after every load. This is that moment.
			BodyPouches::Mod::GetSingleton().OnGameLoaded();
			break;
		default:
			break;
		}
	}
}

// HOW A PLUGIN INTRODUCES ITSELF, AND WHY THERE ARE THREE OF THESE.
//
// SKSE VR is the 1.4.15 branch and knows only the old handshake: it looks for an exported
// SKSEPlugin_Query, and a library without one is refused outright with "does not appear to
// be an SKSE plugin" - which is exactly what happened to the first build of this mod. Later
// Skyrim reads SKSEPlugin_Version instead. Both are declared so that one library serves
// both, which is the point of building on CommonLibSSE-NG at all.
//
// The convenience macro SKSEPluginLoad() writes only the modern pair. In VR that is a
// plugin the game never even looks inside.
extern "C" __declspec(dllexport) bool SKSEAPI SKSEPlugin_Query(const SKSE::QueryInterface* a_skse, SKSE::PluginInfo* a_info)
{
	a_info->infoVersion = SKSE::PluginInfo::kVersion;
	a_info->name = PLUGIN_NAME;
	a_info->version = 1;
	return !a_skse->IsEditor();
}

extern "C" __declspec(dllexport) constinit auto SKSEPlugin_Version = []() {
	SKSE::PluginVersionData v;
	v.PluginVersion(REL::Version{ 0, 1, 1 });
	v.PluginName(PLUGIN_NAME);
	v.AuthorName(PLUGIN_AUTHOR);
	v.UsesAddressLibrary(true);
	v.UsesStructsPost629(true);
	v.CompatibleVersions({ SKSE::RUNTIME_SSE_LATEST });
	return v;
}();

extern "C" __declspec(dllexport) bool SKSEAPI SKSEPlugin_Load(const SKSE::LoadInterface* a_skse)
{
	SKSE::Init(a_skse);
	SetUpLog();

	BodyPouches::Loc::Load();
	BodyPouches::Loc::Info("plugin.loaded", PLUGIN_NAME, PLUGIN_VERSION);

	if (auto* messaging = SKSE::GetMessagingInterface(); messaging != nullptr) {
		messaging->RegisterListener(OnMessage);
	} else {
		BodyPouches::Loc::Error("plugin.no_messaging");
		return false;
	}

	return true;
}
