#include "PapyrusApi.h"

#include "bus/StateStore.h"
#include "bus/SubscriptionRegistry.h"
#include "bus/Auction.h"
#include "bus/UtteranceStore.h"
#include "core/Config.h"

#include <algorithm>
#include "wire/AdapterHost.h"

namespace Envoy
{
	namespace
	{
		std::vector<std::string> ToStrings(const std::vector<RE::BSFixedString>& a_items)
		{
			std::vector<std::string> out;
			out.reserve(a_items.size());
			for (const auto& item : a_items) {
				out.emplace_back(item.c_str());
			}
			return out;
		}
	}

	std::int32_t PapyrusApi::GetInterfaceVersion(Tag)
	{
		return Config::Get().Value<std::int32_t>("/interfaceVersion").value_or(0);
	}

	bool PapyrusApi::IsAvailable(Tag)
	{
		// Если библиотеки нет, функция не зарегистрирована, вызов не проходит и мод
		// получает false. Поэтому "да" здесь означает именно то, что нужно.
		return true;
	}

	void PapyrusApi::Subscribe(Tag, Str a_ns, std::vector<Str> a_topics)
	{
		SubscriptionRegistry::Get().Subscribe(a_ns.c_str(), ToStrings(a_topics));
	}

	void PapyrusApi::Unsubscribe(Tag, Str a_ns)
	{
		SubscriptionRegistry::Get().Unsubscribe(a_ns.c_str());
	}

	void PapyrusApi::SetActive(Tag, Str a_ns, bool a_active)
	{
		SubscriptionRegistry::Get().SetActive(a_ns.c_str(), a_active);
	}

	void PapyrusApi::RegisterVocabulary(Tag, Str a_ns, std::vector<Str> a_phrases)
	{
		SubscriptionRegistry::Get().SetVocabulary(a_ns.c_str(), ToStrings(a_phrases));
		// Словарь нужен той стороне, которая слушает: пусть адаптеры узнают сразу.
		AdapterHost::Get().SendVocabulary(SubscriptionRegistry::Get().MergedVocabulary());
	}

	void PapyrusApi::ClearVocabulary(Tag, Str a_ns)
	{
		SubscriptionRegistry::Get().ClearVocabulary(a_ns.c_str());
		AdapterHost::Get().SendVocabulary(SubscriptionRegistry::Get().MergedVocabulary());
	}

	RE::BSFixedString PapyrusApi::GetText(Tag, std::int32_t a_id)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item ? RE::BSFixedString{ item->text } : RE::BSFixedString{};
	}

	float PapyrusApi::GetScore(Tag, std::int32_t a_id)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item ? item->score : 0.0f;
	}

	float PapyrusApi::GetMargin(Tag, std::int32_t a_id)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item ? item->margin : 0.0f;
	}

	bool PapyrusApi::IsFinal(Tag, std::int32_t a_id)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item && item->isFinal;
	}

	RE::BSFixedString PapyrusApi::GetEngineId(Tag, std::int32_t a_id)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item ? RE::BSFixedString{ item->engine } : RE::BSFixedString{};
	}

	RE::BSFixedString PapyrusApi::GetLanguage(Tag, std::int32_t a_id)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item ? RE::BSFixedString{ item->language } : RE::BSFixedString{};
	}

	RE::BSFixedString PapyrusApi::GetChannel(Tag, std::int32_t a_id)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item ? RE::BSFixedString{ item->channel } : RE::BSFixedString{};
	}

	std::int32_t PapyrusApi::GetLatencyMs(Tag, std::int32_t a_id)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item ? item->latencyMs : 0;
	}

	std::vector<RE::BSFixedString> PapyrusApi::GetAlternatives(Tag, std::int32_t a_id)
	{
		std::vector<RE::BSFixedString> out;
		auto item = UtteranceStore::Get().Find(a_id);
		if (item) {
			for (const auto& alt : item->alternatives) {
				out.emplace_back(alt.text);
			}
		}
		return out;
	}

	std::vector<float> PapyrusApi::GetAlternativeScores(Tag, std::int32_t a_id)
	{
		std::vector<float> out;
		auto item = UtteranceStore::Get().Find(a_id);
		if (item) {
			for (const auto& alt : item->alternatives) {
				out.push_back(alt.score);
			}
		}
		return out;
	}

	RE::BSFixedString PapyrusApi::GetVocabularyMatch(Tag, std::int32_t a_id, Str a_ns)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		if (!item) {
			return {};
		}
		return RE::BSFixedString{ SubscriptionRegistry::Get().Match(a_ns.c_str(), item->text).phrase };
	}

	float PapyrusApi::GetVocabularyScore(Tag, std::int32_t a_id, Str a_ns)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item ? SubscriptionRegistry::Get().Match(a_ns.c_str(), item->text).score : 0.0f;
	}

	float PapyrusApi::GetVocabularyMargin(Tag, std::int32_t a_id, Str a_ns)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item ? SubscriptionRegistry::Get().Match(a_ns.c_str(), item->text).margin : 0.0f;
	}

	void PapyrusApi::Bid(Tag, std::int32_t a_id, Str a_ns, float a_confidence, std::int32_t a_costClass,
		bool a_greedy)
	{
		const bool accepted = UtteranceStore::Get().AddBid(a_id,
			BidRecord{ a_ns.c_str(), a_confidence, a_costClass, a_greedy });

		// Отличить "подписчик промолчал" от "подписчик опоздал" по журналу иначе
		// нечем, а разница решающая: в первом случае до него не дошло событие,
		// во втором - окно ставок короче, чем задержка Papyrus.
		SKSE::log::info("ставка {} за реплику {}: уверенность {:.2f}, {}, через {} мс{}",
			a_ns.c_str(), a_id, a_confidence, a_greedy ? "жадная" : "делится",
			Auction::MsSinceOffer(a_id), accepted ? "" : " - ОПОЗДАЛА, торги закрыты");
	}

	void PapyrusApi::Done(Tag, std::int32_t a_id, Str a_ns, bool a_succeeded)
	{
		SKSE::log::debug("реплика {}: {} отчитался, успех={}", a_id, a_ns.c_str(), a_succeeded);
	}

	RE::BSFixedString PapyrusApi::GetWinner(Tag, std::int32_t a_id)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return (item && !item->winners.empty()) ? RE::BSFixedString{ item->winners.front() }
		                                       : RE::BSFixedString{};
	}

	std::vector<RE::BSFixedString> PapyrusApi::GetWinners(Tag, std::int32_t a_id)
	{
		std::vector<RE::BSFixedString> out;
		auto item = UtteranceStore::Get().Find(a_id);
		if (item) {
			for (const auto& winner : item->winners) {
				out.emplace_back(winner);
			}
		}
		return out;
	}

	bool PapyrusApi::IsWinner(Tag, std::int32_t a_id, Str a_ns)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		if (!item) {
			return false;
		}
		const std::string ns{ a_ns.c_str() };
		return std::find(item->winners.begin(), item->winners.end(), ns) != item->winners.end();
	}

	RE::BSFixedString PapyrusApi::GetDenyReason(Tag, std::int32_t a_id, Str a_ns)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		if (!item) {
			return {};
		}
		auto it = item->denied.find(a_ns.c_str());
		return it == item->denied.end() ? RE::BSFixedString{} : RE::BSFixedString{ it->second };
	}

	RE::BSFixedString PapyrusApi::GetOutcome(Tag, std::int32_t a_id)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item ? RE::BSFixedString{ item->outcome } : RE::BSFixedString{};
	}

	RE::BSFixedString PapyrusApi::GetTopic(Tag, std::int32_t a_id)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item ? RE::BSFixedString{ item->topic } : RE::BSFixedString{};
	}

	// Снимок мира. Пока в нём только то, что опубликовали скриптовые поставщики:
	// ядро и внешние поставщики появятся отдельно, и до тех пор их ключи честно
	// отвечают "спросить некому", а не подставляют ложь.

	std::int32_t PapyrusApi::GetStateStatus(Tag, std::int32_t, Str a_key)
	{
		return StateStore::Get().Status(a_key.c_str());
	}

	float PapyrusApi::GetStateAge(Tag, std::int32_t, Str a_key)
	{
		return StateStore::Get().Age(a_key.c_str());
	}

	bool PapyrusApi::GetStateBool(Tag, std::int32_t, Str a_key, bool a_default)
	{
		auto entry = StateStore::Get().Value(a_key.c_str());
		return entry.hasValue ? entry.boolean : a_default;
	}

	std::int32_t PapyrusApi::GetStateInt(Tag, std::int32_t, Str a_key, std::int32_t a_default)
	{
		auto entry = StateStore::Get().Value(a_key.c_str());
		return entry.hasValue ? entry.integer : a_default;
	}

	float PapyrusApi::GetStateFloat(Tag, std::int32_t, Str a_key, float a_default)
	{
		auto entry = StateStore::Get().Value(a_key.c_str());
		return entry.hasValue ? entry.number : a_default;
	}

	RE::BSFixedString PapyrusApi::GetStateString(Tag, std::int32_t, Str a_key, Str a_default)
	{
		auto entry = StateStore::Get().Value(a_key.c_str());
		return entry.hasValue ? RE::BSFixedString{ entry.text } : a_default;
	}

	RE::TESForm* PapyrusApi::GetStateForm(Tag, std::int32_t, Str a_key)
	{
		auto entry = StateStore::Get().Value(a_key.c_str());
		return entry.hasValue ? RE::TESForm::LookupByID(entry.formId) : nullptr;
	}

	std::vector<RE::BSFixedString> PapyrusApi::GetKeys(Tag)
	{
		std::vector<RE::BSFixedString> out;
		for (const auto& key : StateStore::Get().Keys()) {
			out.emplace_back(key);
		}
		return out;
	}

	bool PapyrusApi::WonPrevious(Tag, Str a_ns)
	{
		return UtteranceStore::Get().WonPrevious(a_ns.c_str());
	}

	float PapyrusApi::SecondsSinceWin(Tag, Str a_ns)
	{
		return UtteranceStore::Get().SecondsSinceWin(a_ns.c_str());
	}

	void PapyrusApi::DeclareKey(Tag, Str a_key, Str a_type, float a_ttlSec, Str a_description)
	{
		if (!StateStore::Get().Declare(a_key.c_str(), a_type.c_str(), a_ttlSec, a_description.c_str())) {
			SKSE::log::warn("ключ {} не принят: пустое имя или чужое пространство", a_key.c_str());
		}
	}

	void PapyrusApi::RetractKey(Tag, Str a_key) { StateStore::Get().Retract(a_key.c_str()); }

	void PapyrusApi::PublishBool(Tag, Str a_key, bool a_value)
	{
		StateStore::Get().PublishBool(a_key.c_str(), a_value);
	}

	void PapyrusApi::PublishInt(Tag, Str a_key, std::int32_t a_value)
	{
		StateStore::Get().PublishInt(a_key.c_str(), a_value);
	}

	void PapyrusApi::PublishFloat(Tag, Str a_key, float a_value)
	{
		StateStore::Get().PublishFloat(a_key.c_str(), a_value);
	}

	void PapyrusApi::PublishString(Tag, Str a_key, Str a_value)
	{
		StateStore::Get().PublishString(a_key.c_str(), a_value.c_str());
	}

	void PapyrusApi::PublishForm(Tag, Str a_key, RE::TESForm* a_value)
	{
		StateStore::Get().PublishForm(a_key.c_str(), a_value ? a_value->GetFormID() : 0);
	}

	std::vector<RE::BSFixedString> PapyrusApi::GetAdapters(Tag)
	{
		std::vector<RE::BSFixedString> out;
		for (const auto& id : AdapterHost::Get().AdapterIds()) {
			out.emplace_back(id);
		}
		return out;
	}

	RE::BSFixedString PapyrusApi::GetSource(Tag, Str a_capability)
	{
		return RE::BSFixedString{ AdapterHost::Get().Source(a_capability.c_str()) };
	}

	bool PapyrusApi::SetSource(Tag, Str a_capability, Str a_adapter)
	{
		return AdapterHost::Get().SetSource(a_capability.c_str(), a_adapter.c_str());
	}

	void PapyrusApi::ReloadSettings(Tag)
	{
		AdapterHost::Get().ReloadConfig();
	}

	std::int32_t PapyrusApi::GetRepeats(Tag, std::int32_t a_id, Str a_ns)
	{
		auto item = UtteranceStore::Get().Find(a_id);
		return item ? SubscriptionRegistry::Get().Repeats(a_ns.c_str(), item->text) : 0;
	}

	std::int32_t PapyrusApi::Say(Tag, Str a_text, Str a_voice, std::int32_t a_priority)
	{
		return AdapterHost::Get().SendSpeak(a_text.c_str(), a_voice.c_str(), a_priority);
	}

	void PapyrusApi::StopSpeech(Tag, std::int32_t a_speechId)
	{
		AdapterHost::Get().SendStop(a_speechId);
	}

	std::int32_t PapyrusApi::Ask(Tag, Str a_service, Str a_payload)
	{
		return AdapterHost::Get().SendAsk(a_service.c_str(), a_payload.c_str());
	}

	bool PapyrusApi::Register(RE::BSScript::IVirtualMachine* a_vm)
	{
		if (!a_vm) {
			return false;
		}

		a_vm->RegisterFunction("GetInterfaceVersion", kScriptName, GetInterfaceVersion);
		a_vm->RegisterFunction("IsAvailable", kScriptName, IsAvailable);

		a_vm->RegisterFunction("Subscribe", kScriptName, Subscribe);
		a_vm->RegisterFunction("Unsubscribe", kScriptName, Unsubscribe);
		a_vm->RegisterFunction("SetActive", kScriptName, SetActive);
		a_vm->RegisterFunction("RegisterVocabulary", kScriptName, RegisterVocabulary);
		a_vm->RegisterFunction("ClearVocabulary", kScriptName, ClearVocabulary);

		a_vm->RegisterFunction("GetText", kScriptName, GetText);
		a_vm->RegisterFunction("GetScore", kScriptName, GetScore);
		a_vm->RegisterFunction("GetMargin", kScriptName, GetMargin);
		a_vm->RegisterFunction("IsFinal", kScriptName, IsFinal);
		a_vm->RegisterFunction("GetEngineId", kScriptName, GetEngineId);
		a_vm->RegisterFunction("GetLanguage", kScriptName, GetLanguage);
		a_vm->RegisterFunction("GetChannel", kScriptName, GetChannel);
		a_vm->RegisterFunction("GetLatencyMs", kScriptName, GetLatencyMs);
		a_vm->RegisterFunction("GetAlternatives", kScriptName, GetAlternatives);
		a_vm->RegisterFunction("GetAlternativeScores", kScriptName, GetAlternativeScores);

		a_vm->RegisterFunction("GetVocabularyMatch", kScriptName, GetVocabularyMatch);
		a_vm->RegisterFunction("GetVocabularyScore", kScriptName, GetVocabularyScore);
		a_vm->RegisterFunction("GetVocabularyMargin", kScriptName, GetVocabularyMargin);

		a_vm->RegisterFunction("Bid", kScriptName, Bid);
		a_vm->RegisterFunction("Done", kScriptName, Done);
		a_vm->RegisterFunction("GetWinner", kScriptName, GetWinner);
		a_vm->RegisterFunction("GetWinners", kScriptName, GetWinners);
		a_vm->RegisterFunction("IsWinner", kScriptName, IsWinner);
		a_vm->RegisterFunction("GetDenyReason", kScriptName, GetDenyReason);
		a_vm->RegisterFunction("GetOutcome", kScriptName, GetOutcome);
		a_vm->RegisterFunction("GetTopic", kScriptName, GetTopic);
		a_vm->RegisterFunction("GetRepeats", kScriptName, GetRepeats);
		a_vm->RegisterFunction("Say", kScriptName, Say);
		a_vm->RegisterFunction("StopSpeech", kScriptName, StopSpeech);
		a_vm->RegisterFunction("Ask", kScriptName, Ask);

		a_vm->RegisterFunction("GetStateStatus", kScriptName, GetStateStatus);
		a_vm->RegisterFunction("GetStateAge", kScriptName, GetStateAge);
		a_vm->RegisterFunction("GetStateBool", kScriptName, GetStateBool);
		a_vm->RegisterFunction("GetStateInt", kScriptName, GetStateInt);
		a_vm->RegisterFunction("GetStateFloat", kScriptName, GetStateFloat);
		a_vm->RegisterFunction("GetStateString", kScriptName, GetStateString);
		a_vm->RegisterFunction("GetStateForm", kScriptName, GetStateForm);
		a_vm->RegisterFunction("GetKeys", kScriptName, GetKeys);
		a_vm->RegisterFunction("WonPrevious", kScriptName, WonPrevious);
		a_vm->RegisterFunction("SecondsSinceWin", kScriptName, SecondsSinceWin);
		a_vm->RegisterFunction("DeclareKey", kScriptName, DeclareKey);
		a_vm->RegisterFunction("RetractKey", kScriptName, RetractKey);
		a_vm->RegisterFunction("PublishBool", kScriptName, PublishBool);
		a_vm->RegisterFunction("PublishInt", kScriptName, PublishInt);
		a_vm->RegisterFunction("PublishFloat", kScriptName, PublishFloat);
		a_vm->RegisterFunction("PublishString", kScriptName, PublishString);
		a_vm->RegisterFunction("PublishForm", kScriptName, PublishForm);

		a_vm->RegisterFunction("GetAdapters", kScriptName, GetAdapters);
		a_vm->RegisterFunction("GetSource", kScriptName, GetSource);
		a_vm->RegisterFunction("SetSource", kScriptName, SetSource);
		a_vm->RegisterFunction("ReloadSettings", kScriptName, ReloadSettings);

		SKSE::log::info("Papyrus: скрипт {} зарегистрирован", kScriptName);
		return true;
	}
}
