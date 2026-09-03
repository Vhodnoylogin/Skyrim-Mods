#include "Auction.h"

#include "TopicRouter.h"
#include "UtteranceStore.h"
#include "core/Config.h"
#include "game/ModEventBus.h"

#include <SKSE/SKSE.h>

#include <algorithm>
#include <chrono>
#include <mutex>
#include <thread>
#include <unordered_map>

namespace Envoy
{
	namespace
	{
		const char* ClassName(std::int32_t a_costClass)
		{
			return a_costClass == 1 ? "costly" : "reversible";
		}

		std::mutex                                                            g_offeredMutex;
		std::unordered_map<std::int32_t, std::chrono::steady_clock::time_point> g_offered;

		float Threshold(const char* a_group, const char* a_class, float a_fallback)
		{
			const auto pointer = std::string{ "/auction/" } + a_group + "/" + a_class;
			return Config::Get().Value<float>(pointer).value_or(a_fallback);
		}

		std::size_t PriorityIndex(const std::string& a_ns)
		{
			const auto list = Config::Get().Value<std::vector<std::string>>("/auction/priority");
			if (!list) {
				return static_cast<std::size_t>(-1);
			}
			const auto it = std::find(list->begin(), list->end(), a_ns);
			return it == list->end() ? static_cast<std::size_t>(-1)
			                         : static_cast<std::size_t>(std::distance(list->begin(), it));
		}

		Auction::Result Exclusive(const std::string& a_ns, const std::vector<BidRecord>& a_all,
			const std::string& a_reason)
		{
			Auction::Result result;
			result.winners.push_back(a_ns);
			result.reason = a_reason;
			for (const auto& bid : a_all) {
				if (bid.ns != a_ns) {
					result.denied[bid.ns] = a_reason;
				}
			}
			return result;
		}
	}

	Auction::Result Auction::Decide(const Utterance& a_utterance)
	{
		Result result;

		const auto minScore = Config::Get().Value<float>("/auction/minUtteranceScore").value_or(0.4f);
		if (a_utterance.score < minScore) {
			result.reason = "реплика расслышана хуже порога";
			for (const auto& bid : a_utterance.bids) {
				result.denied[bid.ns] = result.reason;
			}
			return result;
		}

		std::vector<BidRecord> survivors;
		for (const auto& bid : a_utterance.bids) {
			const auto need = Threshold("minConfidence", ClassName(bid.costClass), 0.55f);
			if (bid.confidence >= need) {
				survivors.push_back(bid);
			} else {
				result.denied[bid.ns] = "уверенность ниже порога своего класса";
			}
		}

		if (survivors.empty()) {
			result.reason = "ни одна ставка не прошла порог уверенности";
			return result;
		}

		std::sort(survivors.begin(), survivors.end(), [](const BidRecord& a, const BidRecord& b) {
			if (a.confidence != b.confidence) {
				return a.confidence > b.confidence;
			}
			const auto pa = PriorityIndex(a.ns);
			const auto pb = PriorityIndex(b.ns);
			return pa != pb ? pa < pb : a.ns < b.ns;
		});

		const auto top = survivors.front();

		if (survivors.size() > 1) {
			const auto margin = top.confidence - survivors[1].confidence;
			const auto need = Threshold("minMargin", ClassName(top.costClass), 0.05f);
			if (margin < need) {
				const auto pTop = PriorityIndex(top.ns);
				const auto pSecond = PriorityIndex(survivors[1].ns);
				if (pTop != static_cast<std::size_t>(-1) && pTop < pSecond) {
					// Ставки неразличимы: раздавать такой результат нескольким
					// значило бы удвоить действие по неясной фразе.
					auto exclusive = Exclusive(top.ns, a_utterance.bids,
						"ставки неразличимы, спор решён приоритетом игрока");
					exclusive.denied.insert(result.denied.begin(), result.denied.end());
					return exclusive;
				}
				result.reason = "ставки слишком близки, приоритет не задан - не делает никто";
				for (const auto& bid : survivors) {
					result.denied[bid.ns] = result.reason;
				}
				return result;
			}
		}

		if (top.greedy) {
			auto exclusive = Exclusive(top.ns, a_utterance.bids, "победитель жадный - результат только ему");
			exclusive.denied.insert(result.denied.begin(), result.denied.end());
			return exclusive;
		}

		for (const auto& bid : survivors) {
			if (bid.greedy) {
				result.denied[bid.ns] = "проиграл, а делиться отказался";
			} else {
				result.winners.push_back(bid.ns);
			}
		}
		result.reason = result.winners.size() > 1
		                    ? "победитель делится - результат достался всем нежадным"
		                    : "победитель делится, делить не с кем";
		return result;
	}

	void Auction::Offer(std::int32_t a_id)
	{
		auto stored = UtteranceStore::Get().Find(a_id);
		if (!stored) {
			return;
		}

		auto item = *stored;
		item.topic = TopicRouter::Pick(item);
		UtteranceStore::Get().Update(a_id, item);

		{
			// Отметка живёт и после итога: опоздавшая ставка должна суметь сказать,
			// насколько она опоздала. Чистим старое здесь же, чтобы не копилось.
			const auto now = std::chrono::steady_clock::now();
			std::scoped_lock lock(g_offeredMutex);
			std::erase_if(g_offered, [&](const auto& entry) {
				return now - entry.second > std::chrono::seconds(60);
			});
			g_offered[a_id] = now;
		}

		// Наблюдатели видят каждую реплику независимо от темы - именно так мод
		// может показать, что до него что-то не дошло и почему.
		// Событие - звонок в дверь: в нём только номер реплики. Тему подписчик
		// узнаёт по имени события, а для Envoy_Speech_Any - вызовом GetTopic.
		// Текст всегда берётся из моста: точная модель может уточнить его уже
		// после рассылки, и копия в событии разошлась бы с истиной.
		ModEventBus::Send("Envoy_Speech_Any", "", static_cast<float>(a_id));
		ModEventBus::Send(TopicRouter::EventName(item.topic), "", static_cast<float>(a_id));

		const auto window = Config::Get().Value<std::int32_t>("/auction/bidWindowMs").value_or(150);

		std::thread([a_id, window]() {
			std::this_thread::sleep_for(std::chrono::milliseconds(window));
			if (auto* task = SKSE::GetTaskInterface()) {
				task->AddTask([a_id]() { Auction::Settle(a_id); });
			}
		}).detach();
	}

	std::int64_t Auction::MsSinceOffer(std::int32_t a_id)
	{
		std::scoped_lock lock(g_offeredMutex);
		auto it = g_offered.find(a_id);
		if (it == g_offered.end()) {
			return -1;
		}
		return std::chrono::duration_cast<std::chrono::milliseconds>(
			std::chrono::steady_clock::now() - it->second).count();
	}

	void Auction::Settle(std::int32_t a_id)
	{
		auto stored = UtteranceStore::Get().Find(a_id);
		if (!stored || stored->awarded) {
			return;
		}

		auto result = Decide(*stored);

		std::string outcome;
		for (const auto& winner : result.winners) {
			outcome += outcome.empty() ? winner : ", " + winner;
		}
		if (outcome.empty()) {
			outcome = "никто";
		}

		UtteranceStore::Get().SetOutcome(a_id, result.winners, result.denied, outcome + " - " + result.reason);

		SKSE::log::info("реплика {} тема {} ставок {} -> {} ({})", a_id, stored->topic,
			stored->bids.size(), outcome, result.reason);

		// По одной рассылке на исход, а не на получателя: имени в событии больше
		// нет, и каждый участник сам спрашивает IsWinner или GetDenyReason.
		// Три имени сохранены не ради содержимого - оно у всех одно, - а ради
		// условия: Envoy_Award молчит, когда никто не выиграл, Envoy_Denied -
		// когда никому не отказано, а Envoy_Settled звучит всегда.
		if (!result.winners.empty()) {
			ModEventBus::Send("Envoy_Award", "", static_cast<float>(a_id));
		}
		if (!result.denied.empty()) {
			ModEventBus::Send("Envoy_Denied", "", static_cast<float>(a_id));
		}
		ModEventBus::Send("Envoy_Settled", "", static_cast<float>(a_id));
	}
}
