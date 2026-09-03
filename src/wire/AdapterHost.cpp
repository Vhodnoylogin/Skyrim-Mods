#include "AdapterHost.h"

#include "bus/Auction.h"
#include "bus/SubscriptionRegistry.h"
#include "bus/UtteranceStore.h"
#include "core/Config.h"
#include "game/ModEventBus.h"

#include <SKSE/SKSE.h>

#include <algorithm>

namespace Envoy
{
	namespace
	{
		std::vector<std::string> Split(const char* a_list)
		{
			std::vector<std::string> out;
			if (!a_list) {
				return out;
			}
			std::string current;
			for (const char* p = a_list; *p; ++p) {
				if (*p == ',') {
					if (!current.empty()) {
						out.push_back(current);
					}
					current.clear();
				} else if (*p != ' ') {
					current.push_back(*p);
				}
			}
			if (!current.empty()) {
				out.push_back(current);
			}
			return out;
		}

		std::string Safe(const char* a_text) { return a_text ? std::string{ a_text } : std::string{}; }
	}

	AdapterHost& AdapterHost::Get()
	{
		static AdapterHost instance;
		return instance;
	}

	bool AdapterHost::Register(const EnvoyAPI::AdapterInfo& a_info, EnvoyAPI::JobCallback a_onJob, void* a_user)
	{
		if (!a_info.id || !a_onJob) {
			return false;
		}
		if (a_info.contract != EnvoyAPI::kInterfaceVersion) {
			SKSE::log::error("адаптер {}: версия контракта {}, мост понимает {}",
				a_info.id, a_info.contract, EnvoyAPI::kInterfaceVersion);
			return false;
		}

		{
			std::scoped_lock lock(_mutex);
			auto& entry = _adapters[a_info.id];
			if (entry.order == 0) {
				entry.order = ++_order;
			}
			entry.name = Safe(a_info.name);
			entry.provides = Split(a_info.provides);
			entry.onJob = a_onJob;
			entry.user = a_user;
			RecomputeSources();
		}

		SKSE::log::info("адаптер зарегистрирован: {} ({})", a_info.id, Safe(a_info.name));

		const auto phrases = SubscriptionRegistry::Get().MergedVocabulary();
		SendVocabulary(phrases);
		return true;
	}

	void AdapterHost::Unregister(const char* a_id)
	{
		if (!a_id) {
			return;
		}
		std::scoped_lock lock(_mutex);
		_adapters.erase(a_id);
		RecomputeSources();
		SKSE::log::info("адаптер ушёл: {}", a_id);
	}

	void AdapterHost::RecomputeSources()
	{
		const auto& raw = Config::Get().Raw();
		nlohmann::json named = nlohmann::json::object();
		if (raw.contains("adapters") && raw["adapters"].contains("primary")) {
			named = raw["adapters"]["primary"];
		}

		std::unordered_map<std::string, std::string> chosen;
		for (const auto& entry : _adapters) {
			for (const auto& capability : entry.second.provides) {
				auto forced = _overrides.find(capability);
				const bool forcedHere = forced != _overrides.end() && forced->second == entry.first;
				const bool namedHere = forcedHere ||
				                       (forced == _overrides.end() && named.contains(capability) &&
				                        named[capability].get<std::string>() == entry.first);

				auto current = chosen.find(capability);
				if (current == chosen.end() || namedHere) {
					chosen[capability] = entry.first;
					continue;
				}

				const bool namedRival = (forced != _overrides.end() && forced->second == current->second) ||
				                        (forced == _overrides.end() && named.contains(capability) &&
				                         named[capability].get<std::string>() == current->second);
				if (!namedRival && entry.second.order < _adapters.at(current->second).order) {
					chosen[capability] = entry.first;
				}
			}
		}
		_sources = chosen;

		for (auto& entry : _adapters) {
			bool active = false;
			std::string role;
			for (const auto& capability : entry.second.provides) {
				auto it = chosen.find(capability);
				if (it != chosen.end() && it->second == entry.first) {
					active = true;
					role = capability;
					break;
				}
			}
			if (active == entry.second.active) {
				continue;
			}
			entry.second.active = active;

			const std::string reason = active ? "назначен источником: " + role
			                                  : "источником назначен другой";
			EnvoyAPI::Job job{};
			job.kind = EnvoyAPI::kJobListen;
			job.active = active;
			job.text = reason.c_str();
			entry.second.onJob(job, entry.second.user);

			SKSE::log::info("адаптер {}: {}", entry.first, active ? "источник" : "в запасе");
		}
	}

	std::int32_t AdapterHost::PushUtterance(const char* a_adapterId, const EnvoyAPI::UtteranceIn& a_in)
	{
		Utterance utterance;
		utterance.isFinal = a_in.isFinal;
		utterance.text = Safe(a_in.text);
		utterance.score = a_in.score;
		utterance.margin = a_in.margin;
		utterance.language = Safe(a_in.language);
		utterance.engine = Safe(a_in.engine);
		utterance.channel = Safe(a_in.channel);
		utterance.latencyMs = a_in.latencyMs;
		utterance.durationMs = a_in.durationMs;

		for (std::int32_t i = 0; i < a_in.altCount; ++i) {
			utterance.alternatives.push_back({ Safe(a_in.altText[i]),
				a_in.altScore ? a_in.altScore[i] : 0.0f });
		}

		if (a_in.refinesId != 0) {
			// Уточнение от точной модели: реплика уже живёт и уже разослана.
			if (!UtteranceStore::Get().Refine(a_in.refinesId, utterance)) {
				return 0;
			}
			SKSE::log::info("реплика {} уточнена адаптером {} ({}): {}",
				a_in.refinesId, Safe(a_adapterId), utterance.engine, utterance.text);
			return a_in.refinesId;
		}

		const auto id = UtteranceStore::Get().Add(std::move(utterance));
		SKSE::log::info("реплика {} от адаптера {}: {}", id, Safe(a_adapterId), Safe(a_in.text));

		if (auto* task = SKSE::GetTaskInterface()) {
			task->AddTask([id]() { Auction::Offer(id); });
		}
		return id;
	}

	const char* AdapterHost::SourceOf(const char* a_capability) const
	{
		std::scoped_lock lock(_mutex);
		auto it = _sources.find(Safe(a_capability));
		_sourceScratch = it == _sources.end() ? std::string{} : it->second;
		return _sourceScratch.c_str();
	}

	bool AdapterHost::SetSource(const std::string& a_capability, const std::string& a_adapter)
	{
		std::scoped_lock lock(_mutex);
		if (!a_adapter.empty() && _adapters.find(a_adapter) == _adapters.end()) {
			return false;
		}
		if (a_adapter.empty()) {
			_overrides.erase(a_capability);
		} else {
			_overrides[a_capability] = a_adapter;
		}
		RecomputeSources();
		return true;
	}

	std::string AdapterHost::Source(const std::string& a_capability) const
	{
		std::scoped_lock lock(_mutex);
		auto it = _sources.find(a_capability);
		return it == _sources.end() ? std::string{} : it->second;
	}

	std::vector<std::string> AdapterHost::AdapterIds() const
	{
		std::scoped_lock lock(_mutex);
		std::vector<std::string> out;
		out.reserve(_adapters.size());
		for (const auto& entry : _adapters) {
			out.push_back(entry.first);
		}
		std::sort(out.begin(), out.end());
		return out;
	}

	void AdapterHost::ReloadConfig()
	{
		Config::Get().Load(Config::Get().Path());
		std::scoped_lock lock(_mutex);
		RecomputeSources();
	}

	void AdapterHost::SendVocabulary(const std::vector<std::string>& a_phrases)
	{
		std::vector<const char*> raw;
		raw.reserve(a_phrases.size());
		for (const auto& phrase : a_phrases) {
			raw.push_back(phrase.c_str());
		}

		EnvoyAPI::Job job{};
		job.kind = EnvoyAPI::kJobVocabulary;
		job.phrases = raw.data();
		job.phraseCount = static_cast<std::int32_t>(raw.size());

		std::scoped_lock lock(_mutex);
		for (auto& entry : _adapters) {
			entry.second.onJob(job, entry.second.user);
		}
	}

	std::int32_t AdapterHost::SendSpeak(const std::string& a_text, const std::string& a_voice,
		std::int32_t a_priority)
	{
		std::scoped_lock lock(_mutex);

		auto source = _sources.find("tts");
		if (source == _sources.end()) {
			SKSE::log::warn("озвучить некому: нет источника tts");
			return 0;
		}
		auto adapter = _adapters.find(source->second);
		if (adapter == _adapters.end()) {
			return 0;
		}

		const auto speechId = _nextSpeech++;
		EnvoyAPI::Job job{};
		job.kind = EnvoyAPI::kJobSpeak;
		job.text = a_text.c_str();
		job.service = a_voice.c_str();
		job.speechId = speechId;
		job.requestId = a_priority;
		adapter->second.onJob(job, adapter->second.user);

		SKSE::log::info("озвучка {} -> адаптер {}: {}", speechId, source->second, a_text);
		return speechId;
	}

	void AdapterHost::SendStop(std::int32_t a_speechId)
	{
		std::scoped_lock lock(_mutex);
		EnvoyAPI::Job job{};
		job.kind = EnvoyAPI::kJobStop;
		job.speechId = a_speechId;
		for (auto& entry : _adapters) {
			entry.second.onJob(job, entry.second.user);
		}
	}

	std::int32_t AdapterHost::SendAsk(const std::string& a_service, const std::string& a_payload)
	{
		std::scoped_lock lock(_mutex);

		// Способность и есть имя службы: кто объявил "llm", тот и отвечает на "llm".
		auto source = _sources.find(a_service);
		if (source == _sources.end()) {
			SKSE::log::warn("спросить некого: нет источника {}", a_service);
			return 0;
		}
		auto adapter = _adapters.find(source->second);
		if (adapter == _adapters.end()) {
			return 0;
		}

		const auto requestId = _nextRequest++;
		EnvoyAPI::Job job{};
		job.kind = EnvoyAPI::kJobAsk;
		job.requestId = requestId;
		job.service = a_service.c_str();
		job.payload = a_payload.c_str();
		adapter->second.onJob(job, adapter->second.user);

		SKSE::log::info("запрос {} к {} -> адаптер {}", requestId, a_service, source->second);
		return requestId;
	}

	std::string AdapterHost::Answer(std::int32_t a_requestId) const
	{
		std::scoped_lock lock(_mutex);
		auto it = _answers.find(a_requestId);
		return it == _answers.end() ? std::string{} : it->second;
	}

	std::string AdapterHost::SpeechResult(std::int32_t a_speechId) const
	{
		std::scoped_lock lock(_mutex);
		auto it = _speechResults.find(a_speechId);
		return it == _speechResults.end() ? std::string{} : it->second;
	}

	void AdapterHost::PushAnswer(const char* a_adapterId, std::int32_t a_requestId, bool a_ok,
		const char* a_payload)
	{
		{
			std::scoped_lock lock(_mutex);
			_answers[a_requestId] = Safe(a_payload);
		}
		SKSE::log::info("ответ {} от адаптера {}: {}", a_requestId, Safe(a_adapterId),
			a_ok ? "успех" : "неудача");

		if (auto* task = SKSE::GetTaskInterface()) {
			task->AddTask([a_requestId]() {
				ModEventBus::Send("Envoy_Answer", "", static_cast<float>(a_requestId));
			});
		}
	}

	void AdapterHost::PushSpeechDone(const char* a_adapterId, std::int32_t a_speechId, bool a_ok,
		bool a_interrupted)
	{
		const std::string how = a_interrupted ? "interrupted" : (a_ok ? "ok" : "failed");
		{
			std::scoped_lock lock(_mutex);
			_speechResults[a_speechId] = how;
		}
		SKSE::log::info("озвучка {} у адаптера {}: {}", a_speechId, Safe(a_adapterId), how);

		if (auto* task = SKSE::GetTaskInterface()) {
			task->AddTask([a_speechId]() {
				ModEventBus::Send("Envoy_SpeechDone", "", static_cast<float>(a_speechId));
			});
		}
	}
}
