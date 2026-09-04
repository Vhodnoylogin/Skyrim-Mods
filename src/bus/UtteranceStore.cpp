#include "UtteranceStore.h"

#include <algorithm>
#include <vector>

namespace Envoy
{
	UtteranceStore& UtteranceStore::Get()
	{
		static UtteranceStore instance;
		return instance;
	}

	std::int32_t UtteranceStore::Add(Utterance a_utterance)
	{
		std::scoped_lock lock(_mutex);

		// Номер обязан помещаться в число Papyrus без потери точности,
		// поэтому переполняемся в единицу, а не в отрицательные значения.
		if (_next >= 16'000'000) {
			_next = 1;
		}

		a_utterance.id = _next++;
		const auto id = a_utterance.id;
		_items.emplace(id, std::move(a_utterance));
		return id;
	}

	bool UtteranceStore::Update(std::int32_t a_id, const Utterance& a_utterance)
	{
		std::scoped_lock lock(_mutex);
		auto it = _items.find(a_id);
		if (it == _items.end()) {
			return false;
		}

		// Ставки переживают обновление: они принадлежат реплике, а не тексту.
		// А вот тему здесь именно НАЗНАЧАЮТ - её пишет аукцион в момент оглашения,
		// и сохранять вместо неё прежнюю нельзя: прежней не существует, и тема
		// осталась бы пустой навсегда. Уточнение текста темы не касается вовсе,
		// потому что идёт через Refine, который её не трогает.
		auto bids = std::move(it->second.bids);
		it->second = a_utterance;
		it->second.id = a_id;
		it->second.bids = std::move(bids);
		return true;
	}

	std::optional<Utterance> UtteranceStore::Find(std::int32_t a_id) const
	{
		std::scoped_lock lock(_mutex);
		auto it = _items.find(a_id);
		if (it == _items.end()) {
			return std::nullopt;
		}
		return it->second;
	}

	bool UtteranceStore::Refine(std::int32_t a_id, const Utterance& a_utterance)
	{
		std::scoped_lock lock(_mutex);
		auto it = _items.find(a_id);
		if (it == _items.end()) {
			return false;
		}

		it->second.text = a_utterance.text;
		it->second.alternatives = a_utterance.alternatives;
		it->second.score = a_utterance.score;
		it->second.margin = a_utterance.margin;
		it->second.engine = a_utterance.engine;
		it->second.latencyMs = a_utterance.latencyMs;
		it->second.isFinal = a_utterance.isFinal;
		return true;
	}

	bool UtteranceStore::AddBid(std::int32_t a_id, BidRecord a_bid)
	{
		std::scoped_lock lock(_mutex);
		auto it = _items.find(a_id);
		if (it == _items.end() || it->second.awarded) {
			return false;
		}

		auto same = std::find_if(it->second.bids.begin(), it->second.bids.end(),
			[&](const BidRecord& b) { return b.ns == a_bid.ns; });
		if (same != it->second.bids.end()) {
			*same = std::move(a_bid);
		} else {
			it->second.bids.push_back(std::move(a_bid));
		}
		return true;
	}

	bool UtteranceStore::SetOutcome(std::int32_t a_id, std::vector<std::string> a_winners,
		std::unordered_map<std::string, std::string> a_denied, std::string a_outcome)
	{
		std::scoped_lock lock(_mutex);
		auto it = _items.find(a_id);
		if (it == _items.end()) {
			return false;
		}
		it->second.awarded = true;
		it->second.winners = std::move(a_winners);
		it->second.denied = std::move(a_denied);
		it->second.outcome = std::move(a_outcome);
		if (!it->second.winners.empty()) {
			_lastAwardedTo = it->second.winners.front();
			_lastAwardAt = std::chrono::steady_clock::now();
		}
		return true;
	}

	void UtteranceStore::PruneIfDue(double a_ttlSec, std::size_t a_maxStored)
	{
		{
			std::scoped_lock lock(_mutex);
			const auto now = std::chrono::steady_clock::now();
			const auto due = _lastPrune + std::chrono::duration<double>(a_ttlSec / 4.0);
			if (_items.size() <= a_maxStored && now < due) {
				return;
			}
			_lastPrune = now;
		}
		Prune(a_ttlSec, a_maxStored);
	}

	void UtteranceStore::Prune(double a_ttlSec, std::size_t a_maxStored)
	{
		std::scoped_lock lock(_mutex);
		const auto now = std::chrono::steady_clock::now();

		for (auto it = _items.begin(); it != _items.end();) {
			const std::chrono::duration<double> age = now - it->second.born;
			it = (age.count() > a_ttlSec) ? _items.erase(it) : std::next(it);
		}

		if (_items.size() <= a_maxStored) {
			return;
		}

		std::vector<std::pair<std::int32_t, std::chrono::steady_clock::time_point>> byAge;
		byAge.reserve(_items.size());
		for (const auto& [id, item] : _items) {
			byAge.emplace_back(id, item.born);
		}
		std::sort(byAge.begin(), byAge.end(), [](const auto& a, const auto& b) { return a.second < b.second; });

		const auto excess = _items.size() - a_maxStored;
		for (std::size_t i = 0; i < excess; ++i) {
			_items.erase(byAge[i].first);
		}
	}

	std::size_t UtteranceStore::Count() const
	{
		std::scoped_lock lock(_mutex);
		return _items.size();
	}

	bool UtteranceStore::WonPrevious(const std::string& a_namespace) const
	{
		std::scoped_lock lock(_mutex);
		return _lastAwardedTo == a_namespace;
	}

	float UtteranceStore::SecondsSinceWin(const std::string& a_namespace) const
	{
		std::scoped_lock lock(_mutex);
		if (_lastAwardedTo != a_namespace) {
			return -1.0f;
		}
		const std::chrono::duration<float> age = std::chrono::steady_clock::now() - _lastAwardAt;
		return age.count();
	}
}
