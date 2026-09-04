#include "Auction.h"

#include "TopicRouter.h"
#include "UtteranceStore.h"
#include "core/Settings.h"
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

		constexpr auto kNoPriority = Settings::kNoPriority;

		// Спорят не все выжившие, а только те, кого от лучшего не отделяет запас.
		std::vector<BidRecord> Tied(const std::vector<BidRecord>& a_survivors, float a_need)
		{
			std::vector<BidRecord> tied;
			for (const auto& bid : a_survivors) {
				if (a_survivors.front().confidence - bid.confidence < a_need) {
					tied.push_back(bid);
				}
			}
			return tied;
		}

		// Одну ли команду они узнали. Пустая фраза значит "неизвестно", и тогда
		// безопаснее считать, что поняли разное: угадывать дороже, чем смолчать.
		bool SameCommand(const std::vector<BidRecord>& a_tied)
		{
			if (a_tied.front().phrase.empty()) {
				return false;
			}
			for (const auto& bid : a_tied) {
				if (bid.phrase != a_tied.front().phrase) {
					return false;
				}
			}
			return true;
		}

		// Ничья: уверенность спорщиков больше не разведёт. Одинаковая запись
		// словаря даёт одинаковое число всегда, поэтому ждать, что в следующий
		// раз кто-то опередит, бессмысленно - нужно правило.
		Auction::Result BreakTie(const std::vector<BidRecord>& a_survivors, float a_need,
			const std::vector<BidRecord>& a_all)
		{
			Auction::Result result;
			const auto tied = Tied(a_survivors, a_need);

			// Порядок из настроек - прямое указание игрока, и оно старше любых
			// наших рассуждений: если он назвал, кто здесь главный, спорить не
			// о чем.
			auto             best = kNoPriority;
			std::size_t      count = 0;
			const BidRecord* chosen = nullptr;
			for (const auto& bid : tied) {
				const auto place = Settings::Get().PriorityIndex(bid.ns);
				if (place < best) {
					best = place;
					count = 1;
					chosen = &bid;
				} else if (place == best) {
					++count;
				}
			}
			if (best != kNoPriority && count == 1) {
				return Exclusive(chosen->ns, a_all, "ставки неразличимы, спор решён порядком из настроек");
			}

			// Порядок молчит. Дальше всё зависит от того, об одном ли спор.
			// Разные команды при неразличимой уверенности - это двусмысленная
			// реплика: понять её можно двояко, и оба понимания равно
			// правдоподобны. Сделать по ней хоть что-нибудь значит угадывать.
			if (!SameCommand(tied)) {
				result.reason = "фразу поняли по-разному и одинаково уверенно - реплика двусмысленна";
				for (const auto& bid : tied) {
					result.denied[bid.ns] = result.reason;
				}
				return result;
			}

			// Двусмысленности нет: все узнали одну и ту же команду, и спор идёт
			// не о том, что сказано, а о том, чья это команда. Уверенность его
			// не решит никогда - одинаковая запись словаря даёт одинаковое
			// число, - поэтому решает объявленная готовность делиться.
			// Жадный при этом ничего не теряет: он сам объявил "мне одному или
			// никак" и при чужой победе выбывает по собственному условию.
			if (Settings::Get().sharedWinsTie) {
				Auction::Result shared;
				for (const auto& bid : a_survivors) {
					if (bid.greedy) {
						shared.denied[bid.ns] = "проиграл, а делиться отказался";
					} else {
						shared.winners.push_back(bid.ns);
					}
				}
				if (!shared.winners.empty()) {
					shared.reason = "одну команду просят несколько, порядок не задан - её делают те, кто делится";
					return shared;
				}
			}

			result.reason = "одну команду просят несколько, и все требуют её себе - не делает никто";
			for (const auto& bid : tied) {
				result.denied[bid.ns] = result.reason;
			}
			return result;
		}
	}

	Auction::Result Auction::Decide(const Utterance& a_utterance)
	{
		Result result;

		if (a_utterance.score < Settings::Get().minUtteranceScore) {
			result.reason = "реплика расслышана хуже порога";
			for (const auto& bid : a_utterance.bids) {
				result.denied[bid.ns] = result.reason;
			}
			return result;
		}

		// Отсутствие ставок и провал ставок - разные вещи, и сводить их к одной
		// строке журнала значит лгать в диагностике: в прогоне 04.09 такую
		// строку получили 34 реплики из 36, и ни у одной ставок не было.
		if (a_utterance.bids.empty()) {
			result.reason = "никто не заявился";
			return result;
		}

		std::vector<BidRecord> survivors;
		for (const auto& bid : a_utterance.bids) {
			if (bid.confidence >= Settings::Get().MinConfidence(bid.costClass)) {
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
			const auto pa = Settings::Get().PriorityIndex(a.ns);
			const auto pb = Settings::Get().PriorityIndex(b.ns);
			return pa != pb ? pa < pb : a.ns < b.ns;
		});

		const auto top = survivors.front();

		if (survivors.size() > 1) {
			const auto need = Settings::Get().MinMargin(top.costClass);
			if (top.confidence - survivors[1].confidence < need) {
				auto tie = BreakTie(survivors, need, a_utterance.bids);
				tie.denied.insert(result.denied.begin(), result.denied.end());
				return tie;
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
		item.offeredAt = std::chrono::steady_clock::now();
		UtteranceStore::Get().Update(a_id, item);

		// Уборка идёт здесь же: чаще реплик в хранилище ничего не происходит,
		// а отдельный поток-уборщик пришлось бы ещё и останавливать при выходе.
		UtteranceStore::Get().PruneIfDue(Settings::Get().utteranceTtlSec,
			Settings::Get().utteranceMaxStored);

		// Наблюдатели видят каждую реплику независимо от темы - именно так мод
		// может показать, что до него что-то не дошло и почему.
		// Событие - звонок в дверь: в нём только номер реплики. Тему подписчик
		// узнаёт по имени события, а для Envoy_Speech_Any - вызовом GetTopic.
		// Текст всегда берётся из моста: точная модель может уточнить его уже
		// после рассылки, и копия в событии разошлась бы с истиной.
		ModEventBus::Send("Envoy_Speech_Any", "", static_cast<float>(a_id));
		ModEventBus::Send(TopicRouter::EventName(item.topic), "", static_cast<float>(a_id));

		const auto window = Settings::Get().bidWindowMs;

		std::thread([a_id, window]() {
			std::this_thread::sleep_for(std::chrono::milliseconds(window));
			if (auto* task = SKSE::GetTaskInterface()) {
				task->AddTask([a_id]() { Auction::Settle(a_id); });
			}
		}).detach();
	}

	std::int64_t Auction::MsSinceOffer(std::int32_t a_id)
	{
		auto stored = UtteranceStore::Get().Find(a_id);
		if (!stored || stored->offeredAt.time_since_epoch().count() == 0) {
			return -1;
		}
		return std::chrono::duration_cast<std::chrono::milliseconds>(
			std::chrono::steady_clock::now() - stored->offeredAt).count();
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
