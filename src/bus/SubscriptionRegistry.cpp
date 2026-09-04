#include "SubscriptionRegistry.h"

#include <algorithm>
#include <cctype>

namespace Envoy
{
	namespace
	{
		std::string Normalize(const std::string& a_text)
		{
			std::string out;
			out.reserve(a_text.size());
			for (unsigned char ch : a_text) {
				if (std::isspace(ch)) {
					if (!out.empty() && out.back() != ' ') {
						out.push_back(' ');
					}
				} else if (!std::ispunct(ch)) {
					out.push_back(static_cast<char>(std::tolower(ch)));
				}
			}
			while (!out.empty() && out.back() == ' ') {
				out.pop_back();
			}
			return out;
		}

		// Похожесть строк без внешних библиотек: расстояние редактирования,
		// приведённое к доле от длины. Для команд и коротких фраз этого хватает.
		float Similarity(const std::string& a_left, const std::string& a_right)
		{
			if (a_left.empty() || a_right.empty()) {
				return 0.0f;
			}
			if (a_left == a_right) {
				return 1.0f;
			}

			std::vector<std::size_t> previous(a_right.size() + 1);
			std::vector<std::size_t> current(a_right.size() + 1);
			for (std::size_t j = 0; j <= a_right.size(); ++j) {
				previous[j] = j;
			}

			for (std::size_t i = 1; i <= a_left.size(); ++i) {
				current[0] = i;
				for (std::size_t j = 1; j <= a_right.size(); ++j) {
					const std::size_t cost = (a_left[i - 1] == a_right[j - 1]) ? 0u : 1u;
					current[j] = std::min({ current[j - 1] + 1, previous[j] + 1, previous[j - 1] + cost });
				}
				previous.swap(current);
			}

			const auto distance = static_cast<float>(previous[a_right.size()]);
			const auto longest = static_cast<float>(std::max(a_left.size(), a_right.size()));
			return std::max(0.0f, 1.0f - distance / longest);
		}
	}

	SubscriptionRegistry& SubscriptionRegistry::Get()
	{
		static SubscriptionRegistry instance;
		return instance;
	}

	void SubscriptionRegistry::Subscribe(const std::string& a_ns, std::vector<std::string> a_topics)
	{
		std::scoped_lock lock(_mutex);
		_entries[a_ns].topics = std::move(a_topics);
	}

	void SubscriptionRegistry::Unsubscribe(const std::string& a_ns)
	{
		std::scoped_lock lock(_mutex);
		_entries.erase(a_ns);
	}

	void SubscriptionRegistry::SetActive(const std::string& a_ns, bool a_active)
	{
		std::scoped_lock lock(_mutex);
		_entries[a_ns].active = a_active;
	}

	void SubscriptionRegistry::SetVocabulary(const std::string& a_ns, std::vector<std::string> a_phrases)
	{
		std::scoped_lock lock(_mutex);
		_entries[a_ns].vocabulary = std::move(a_phrases);
	}

	void SubscriptionRegistry::ClearVocabulary(const std::string& a_ns)
	{
		std::scoped_lock lock(_mutex);
		_entries[a_ns].vocabulary.clear();
	}

	VocabularyMatch SubscriptionRegistry::Match(const std::string& a_ns, const std::string& a_text) const
	{
		std::scoped_lock lock(_mutex);
		VocabularyMatch best;

		auto it = _entries.find(a_ns);
		if (it == _entries.end()) {
			return best;
		}

		const auto text = Normalize(a_text);
		float second = 0.0f;

		for (const auto& phrase : it->second.vocabulary) {
			const auto score = Similarity(text, Normalize(phrase));
			if (score > best.score) {
				second = best.score;
				best.score = score;
				best.phrase = phrase;
			} else if (score > second) {
				second = score;
			}
		}

		best.margin = best.score - second;
		return best;
	}

	std::vector<std::string> SubscriptionRegistry::Namespaces() const
	{
		std::scoped_lock lock(_mutex);
		std::vector<std::string> out;
		out.reserve(_entries.size());
		for (const auto& entry : _entries) {
			out.push_back(entry.first);
		}
		std::sort(out.begin(), out.end());
		return out;
	}

	std::vector<std::string> SubscriptionRegistry::TopicsOf(const std::string& a_ns) const
	{
		std::scoped_lock lock(_mutex);
		auto it = _entries.find(a_ns);
		return it == _entries.end() ? std::vector<std::string>{} : it->second.topics;
	}

	std::vector<std::string> SubscriptionRegistry::MergedVocabulary() const
	{
		std::scoped_lock lock(_mutex);
		std::vector<std::string> out;
		for (const auto& entry : _entries) {
			if (!entry.second.active) {
				continue;
			}
			out.insert(out.end(), entry.second.vocabulary.begin(), entry.second.vocabulary.end());
		}
		std::sort(out.begin(), out.end());
		out.erase(std::unique(out.begin(), out.end()), out.end());
		return out;
	}

	std::size_t SubscriptionRegistry::Count() const
	{
		std::scoped_lock lock(_mutex);
		return _entries.size();
	}
}
