#pragma once

#include "envoy-adapter.h"

#include <cstdint>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace Envoy
{
	// Приёмная моста для адаптеров. Мост не знает ни одной внешней программы:
	// адаптеры - такие же моды, они приходят сами и называются сами.
	//
	// Задания отдаются вызовом обратной функции прямо в потоке вызывающего,
	// поэтому адаптер обязан лишь положить задание в свою очередь и вернуться.
	class AdapterHost final : public EnvoyAPI::IEnvoy
	{
	public:
		static AdapterHost& Get();

		std::uint32_t Version() const override { return EnvoyAPI::kInterfaceVersion; }

		bool         Register(const EnvoyAPI::AdapterInfo& a_info, EnvoyAPI::JobCallback a_onJob, void* a_user) override;
		void         Unregister(const char* a_id) override;
		std::int32_t PushUtterance(const char* a_adapterId, const EnvoyAPI::UtteranceIn& a_utterance) override;
		const char*  SourceOf(const char* a_capability) const override;

		// Для меню и скриптов.
		bool                     SetSource(const std::string& a_capability, const std::string& a_adapter);
		std::string              Source(const std::string& a_capability) const;
		std::vector<std::string> AdapterIds() const;
		void                     ReloadConfig();

		void PushAnswer(const char* a_adapterId, std::int32_t a_requestId, bool a_ok,
			const char* a_payload) override;
		void PushSpeechDone(const char* a_adapterId, std::int32_t a_speechId, bool a_ok,
			bool a_interrupted) override;

		void         SendVocabulary(const std::vector<std::string>& a_phrases);
		std::int32_t SendSpeak(const std::string& a_text, const std::string& a_voice, std::int32_t a_priority);
		void         SendStop(std::int32_t a_speechId);
		std::int32_t SendAsk(const std::string& a_service, const std::string& a_payload);

	private:
		AdapterHost() = default;

		struct Entry
		{
			std::string              name;
			std::vector<std::string> provides;
			EnvoyAPI::JobCallback    onJob{ nullptr };
			void*                    user{ nullptr };
			std::uint64_t            order{ 0 };
			bool                     active{ false };
		};

		void RecomputeSources();

		mutable std::mutex                           _mutex;
		std::unordered_map<std::string, Entry>       _adapters;
		std::unordered_map<std::string, std::string> _sources;
		std::unordered_map<std::string, std::string> _overrides;
		mutable std::string                          _sourceScratch;
		std::uint64_t                                _order{ 0 };
		std::int32_t                                 _nextSpeech{ 1 };
		std::int32_t                                 _nextRequest{ 1 };
	};
}
