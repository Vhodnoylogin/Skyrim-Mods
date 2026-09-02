// Адаптер голоса для Envoy.
//
// Это мод: обычный плагин SKSE, живущий в процессе игры. С мостом он говорит
// вызовом функции, а наружу - к моделям, которые частью игры быть не могут, -
// ходит сам по HTTP. Мост о моделях не знает ничего.
//
// Моделей может быть сколько угодно: список в envoy-voice.json. Частный случай
// "быстрая плюс точная" - это две записи с разными классами.

#include <RE/Skyrim.h>
#include <SKSE/SKSE.h>

#include "envoy-adapter.h"

#include <nlohmann/json.hpp>
#include <httplib.h>
#include <windows.h>

#include <spdlog/sinks/basic_file_sink.h>

#include <atomic>
#include <chrono>
#include <deque>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace
{
	constexpr auto kConfigPath = LR"(Data\SKSE\Plugins\envoy\adapters\voice\envoy-voice.json)";

	EnvoyAPI::IEnvoy* g_envoy = nullptr;
	nlohmann::json    g_config;
	std::atomic_bool  g_listening{ true };
	std::atomic_bool  g_stop{ false };

	// Пока у источника звука нет общего номера куска, результаты разных моделей
	// связываются по времени: точный ответ, пришедший вскоре после
	// предварительного, считается его уточнением. Это временно и честно помечено.
	std::mutex                            g_correlate;
	std::int32_t                          g_lastPreliminary{ 0 };
	std::chrono::steady_clock::time_point g_lastPreliminaryAt{};

	void InitLog()
	{
		auto path = SKSE::log::log_directory();
		if (!path) {
			return;
		}
		*path /= PLUGIN_NAME;
		*path += ".log";
		auto sink = std::make_shared<spdlog::sinks::basic_file_sink_mt>(path->string(), true);
		auto logger = std::make_shared<spdlog::logger>("global log", std::move(sink));
		logger->set_level(spdlog::level::info);
		logger->flush_on(spdlog::level::info);
		spdlog::set_default_logger(std::move(logger));
	}

	bool LoadConfig()
	{
		std::error_code ec;
		if (!std::filesystem::exists(kConfigPath, ec)) {
			SKSE::log::error("нет файла настроек: {}", std::filesystem::path{ kConfigPath }.string());
			return false;
		}
		try {
			std::ifstream stream(kConfigPath);
			stream >> g_config;
		} catch (const std::exception& e) {
			SKSE::log::error("настройки не разобраны: {}", e.what());
			return false;
		}
		return true;
	}

	std::wstring Widen(const std::string& a_text)
	{
		if (a_text.empty()) {
			return {};
		}
		const int size = ::MultiByteToWideChar(CP_UTF8, 0, a_text.c_str(),
			static_cast<int>(a_text.size()), nullptr, 0);
		std::wstring out(static_cast<std::size_t>(size), L'\0');
		::MultiByteToWideChar(CP_UTF8, 0, a_text.c_str(), static_cast<int>(a_text.size()),
			out.data(), size);
		return out;
	}

	struct Endpoint
	{
		std::string host;
		int         port{ 0 };
	};

	Endpoint Parse(const std::string& a_url)
	{
		Endpoint out{ "127.0.0.1", 80 };
		auto rest = a_url;
		const auto scheme = rest.find("://");
		if (scheme != std::string::npos) {
			rest = rest.substr(scheme + 3);
		}
		const auto colon = rest.find(':');
		if (colon != std::string::npos) {
			out.host = rest.substr(0, colon);
			out.port = std::atoi(rest.c_str() + colon + 1);
		} else {
			out.host = rest;
		}
		return out;
	}
}

namespace
{
	bool Alive(const nlohmann::json& a_model)
	{
		const auto ep = Parse(a_model.value("url", std::string{}));
		httplib::Client client(ep.host, ep.port);
		client.set_connection_timeout(2, 0);
		auto res = client.Get("/health");
		return res && res->status == 200;
	}

	void Launch(const nlohmann::json& a_model)
	{
		const auto id = a_model.value("id", std::string{});
		if (!a_model.contains("autoStart")) {
			return;
		}
		const auto& start = a_model["autoStart"];
		if (!start.value("enabled", false) || start.value("exec", std::string{}).empty()) {
			SKSE::log::warn("модель {}: не отвечает, а поднимать её не разрешено", id);
			return;
		}

		std::string command = "\"" + start.value("exec", std::string{}) + "\"";
		if (start.contains("args")) {
			for (const auto& arg : start["args"]) {
				command += " \"" + arg.get<std::string>() + "\"";
			}
		}

		// Погасить службу при выходе из игры некому: адаптер уходит вместе с
		// процессом игры и своего завершения выполнить не успевает. Поэтому
		// службе сообщается, за кем следить, и она гасится сама. Без этого она
		// переживает игру, держит микрофон и модель, а Mod Organizer из-за неё
		// считает игру запущенной и запрещает править состав сборки.
		const auto pidArg = start.value("parentPidArg", std::string{});
		if (!pidArg.empty()) {
			command += " " + pidArg + " " + std::to_string(::GetCurrentProcessId());
		}

		auto wideDir = Widen(start.value("workingDir", std::string{}));
		STARTUPINFOW startup{};
		startup.cb = sizeof(startup);
		PROCESS_INFORMATION info{};

		SKSE::log::info("модель {}: поднимаю - {}", id, command);

		// Служба обязана выйти из объекта задания, в котором MO2 держит игру.
		// MO2 считает игру запущенной, пока не опустеет всё дерево процессов, а
		// служба сама не завершается никогда - без этого MO2 навсегда осталась бы
		// в состоянии "игра работает", и состав сборки стало бы нельзя менять.
		// Если задание запрещает выход, запускаем как получится: служба тогда
		// удержит MO2, и правильный порядок - поднимать её заранее, вне игры.
		const auto spawn = [&](DWORD a_flags) {
			auto line = Widen(command);   // CreateProcessW портит строку, поэтому каждый раз своя
			return ::CreateProcessW(nullptr, line.data(), nullptr, nullptr, FALSE, a_flags,
				nullptr, wideDir.empty() ? nullptr : wideDir.c_str(), &startup, &info) != FALSE;
		};

		if (!spawn(CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB)) {
			const auto why = ::GetLastError();
			SKSE::log::warn("модель {}: не выпустили из задания (код {}), запускаю внутри него - "
			                "MO2 будет считать игру запущенной, пока служба жива", id, why);
			if (!spawn(CREATE_NO_WINDOW)) {
				SKSE::log::error("модель {}: запустить не удалось, код {}", id, ::GetLastError());
				return;
			}
		}
		::CloseHandle(info.hThread);
		::CloseHandle(info.hProcess);

		const auto deadline = std::chrono::steady_clock::now() +
		                      std::chrono::seconds(start.value("waitSec", 60));
		while (std::chrono::steady_clock::now() < deadline && !g_stop.load()) {
			if (Alive(a_model)) {
				SKSE::log::info("модель {}: поднялась", id);
				return;
			}
			std::this_thread::sleep_for(std::chrono::seconds(1));
		}
		SKSE::log::warn("модель {}: не ответила за отведённое время", id);
	}

	void PushResult(const nlohmann::json& a_model, const nlohmann::json& a_item)
	{
		if (!g_envoy) {
			return;
		}

		const auto text = a_item.value("text", std::string{});
		const auto engine = a_item.value("engine", std::string{});
		const auto language = a_model.value("language", std::string{});
		const auto isFast = a_model.value("class", std::string{}) == "fast";

		EnvoyAPI::UtteranceIn in{};
		in.text = text.c_str();
		in.language = language.c_str();
		in.engine = engine.c_str();
		in.channel = "";
		in.score = a_item.value("score", 0.0f);
		in.margin = 0.0f;
		in.latencyMs = a_item.value("ms", 0);
		in.durationMs = 0;
		in.isFinal = !isFast;

		if (!isFast) {
			std::scoped_lock lock(g_correlate);
			const auto window = std::chrono::milliseconds(g_config.value("correlateMs", 2500));
			if (g_lastPreliminary != 0 &&
				std::chrono::steady_clock::now() - g_lastPreliminaryAt < window) {
				in.refinesId = g_lastPreliminary;
				g_lastPreliminary = 0;
			}
		}

		const auto id = g_envoy->PushUtterance(g_config["adapter"].value("id", "voice").c_str(), in);
		if (id == 0) {
			SKSE::log::warn("мост не принял реплику от модели {}", a_model.value("id", std::string{}));
			return;
		}

		if (isFast) {
			std::scoped_lock lock(g_correlate);
			g_lastPreliminary = id;
			g_lastPreliminaryAt = std::chrono::steady_clock::now();
		}
	}

	void PollModel(nlohmann::json a_model)
	{
		const auto id = a_model.value("id", std::string{});
		const auto ep = Parse(a_model.value("url", std::string{}));
		const auto timeout = a_model.value("listenTimeoutSec", 30);
		int since = 0;

		// Два разных исхода, и в журнале они обязаны различаться: иначе по нему
		// не понять, проверили мы самостоятельный запуск службы или подключились
		// к поднятой заранее руками.
		if (Alive(a_model)) {
			SKSE::log::info("модель {}: уже поднята, подключаюсь к ней", id);
		} else {
			Launch(a_model);
		}

		while (!g_stop.load()) {
			if (!g_listening.load()) {
				std::this_thread::sleep_for(std::chrono::seconds(1));
				continue;
			}

			httplib::Client client(ep.host, ep.port);
			client.set_read_timeout(timeout + 10, 0);
			const auto path = "/listen?since=" + std::to_string(since) +
			                  "&timeout=" + std::to_string(timeout);
			auto res = client.Get(path);
			if (!res || res->status != 200) {
				std::this_thread::sleep_for(
					std::chrono::milliseconds(g_config.value("retryDelayMs", 2000)));
				continue;
			}

			try {
				auto body = nlohmann::json::parse(res->body);
				for (const auto& item : body.value("utterances", nlohmann::json::array())) {
					since = std::max(since, item.value("id", 0));
					PushResult(a_model, item);
				}
			} catch (const std::exception& e) {
				SKSE::log::warn("модель {}: ответ не разобран - {}", id, e.what());
			}
		}
	}

	void Speak(const std::string& a_text, std::int32_t a_speechId)
	{
		const auto adapterId = g_config["adapter"].value("id", std::string{ "voice" });
		const auto wanted = g_config.value("speakModel", std::string{});

		for (const auto& model : g_config["models"]) {
			if (!model.value("enabled", false) || model.value("id", std::string{}) != wanted) {
				continue;
			}
			const auto ep = Parse(model.value("url", std::string{}));
			httplib::Client client(ep.host, ep.port);
			client.set_read_timeout(120, 0);
			nlohmann::json payload{ { "text", a_text } };
			auto res = client.Post("/say", payload.dump(), "application/json");

			const bool ok = res && res->status == 200;
			SKSE::log::info("озвучка {}: {}", a_speechId, ok ? "сказано" : "не вышло");
			if (g_envoy) {
				g_envoy->PushSpeechDone(adapterId.c_str(), a_speechId, ok, false);
			}
			return;
		}

		SKSE::log::warn("озвучка {}: модель {} не включена", a_speechId, wanted);
		if (g_envoy) {
			g_envoy->PushSpeechDone(adapterId.c_str(), a_speechId, false, false);
		}
	}

	void OnJob(const EnvoyAPI::Job& a_job, void*)
	{
		switch (a_job.kind) {
		case EnvoyAPI::kJobListen:
			g_listening.store(a_job.active);
			SKSE::log::info("мост: {} ({})", a_job.active ? "я источник" : "я в запасе",
				a_job.text ? a_job.text : "");
			break;
		case EnvoyAPI::kJobVocabulary:
			SKSE::log::info("словарь подписчиков: {} фраз", a_job.phraseCount);
			break;
		case EnvoyAPI::kJobSpeak:
			if (a_job.text) {
				// Озвучка идёт в своём потоке: держать поток игры на время
				// синтеза нельзя.
				std::string text = a_job.text;
				const auto speechId = a_job.speechId;
				std::thread([text, speechId]() { Speak(text, speechId); }).detach();
			}
			break;
		case EnvoyAPI::kJobAsk:
			// Голосовой адаптер языковых моделей не держит: эта способность
			// объявляется другим адаптером, и мост направит запрос ему.
			SKSE::log::info("запрос к {} мне не адресован", a_job.service ? a_job.service : "?");
			break;
		default:
			break;
		}
	}
}

namespace
{
	void Start()
	{
		if (!g_envoy) {
			return;
		}

		EnvoyAPI::AdapterInfo info{};
		const auto id = g_config["adapter"].value("id", std::string{ "voice" });
		const auto name = g_config["adapter"].value("name", std::string{});
		const auto provides = g_config["adapter"].value("provides", std::string{ "asr" });
		info.id = id.c_str();
		info.name = name.c_str();
		info.provides = provides.c_str();
		info.contract = EnvoyAPI::kInterfaceVersion;

		if (!g_envoy->Register(info, OnJob, nullptr)) {
			SKSE::log::error("мост отказал в регистрации");
			return;
		}
		SKSE::log::info("зарегистрирован в мосту как {}", id);

		int started = 0;
		for (const auto& model : g_config["models"]) {
			if (!model.value("enabled", false)) {
				SKSE::log::info("модель {}: выключена", model.value("id", std::string{}));
				continue;
			}
			std::thread(PollModel, model).detach();
			++started;
		}
		SKSE::log::info("моделей в работе: {}", started);
	}

	void OnMessage(SKSE::MessagingInterface::Message* a_message)
	{
		if (!a_message || a_message->type != EnvoyAPI::kMessageInterface) {
			return;
		}
		if (a_message->dataLen != sizeof(EnvoyAPI::IEnvoy*)) {
			return;
		}
		g_envoy = *static_cast<EnvoyAPI::IEnvoy**>(a_message->data);
		if (!g_envoy || g_envoy->Version() != EnvoyAPI::kInterfaceVersion) {
			SKSE::log::error("версия интерфейса моста не та, что я понимаю");
			g_envoy = nullptr;
			return;
		}
		SKSE::log::info("интерфейс моста получен, версия {}", g_envoy->Version());
		Start();
	}
}

extern "C" __declspec(dllexport) bool SKSEAPI SKSEPlugin_Query(const SKSE::QueryInterface* a_skse, SKSE::PluginInfo* a_info)
{
	a_info->infoVersion = SKSE::PluginInfo::kVersion;
	a_info->name = PLUGIN_NAME;
	a_info->version = 1;
	return !a_skse->IsEditor();
}

extern "C" __declspec(dllexport) constinit auto SKSEPlugin_Version = []() {
	SKSE::PluginVersionData v;
	v.PluginVersion(REL::Version{ 0, 1, 0 });
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
	InitLog();

	SKSE::log::info("{} v{} загружен", PLUGIN_NAME, PLUGIN_VERSION);
	if (!LoadConfig()) {
		SKSE::log::error("без настроек работать не могу");
		return true;
	}

	// Мост рассылает интерфейс от своего имени - слушаем именно его.
	if (auto* messaging = SKSE::GetMessagingInterface()) {
		messaging->RegisterListener("Envoy", OnMessage);
	}
	return true;
}
