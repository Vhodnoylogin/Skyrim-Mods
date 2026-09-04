#include "SubscriptionRegistry.h"

#include <algorithm>
#include <cctype>

namespace Envoy
{
	namespace
	{
		// Кодовые точки, а не байты. Кириллица в UTF-8 занимает два байта, и
		// std::tolower их не трогает, а расстояние редактирования по байтам
		// назначает заглавной букве цену от того, в какой половине блока она
		// стоит: "З" стоила 1 байт из 23, а "Ч" - 2 из 19. Регистронезависимость
		// для русского не работала вовсе, и все пороги значили не то, чем казались.
		std::u32string Decode(const std::string& a_text)
		{
			std::u32string out;
			out.reserve(a_text.size());
			for (std::size_t i = 0; i < a_text.size();) {
				const auto lead = static_cast<unsigned char>(a_text[i]);
				std::size_t extra = 0;
				char32_t    point = lead;
				if (lead >= 0xF0) {
					extra = 3;
					point = lead & 0x07u;
				} else if (lead >= 0xE0) {
					extra = 2;
					point = lead & 0x0Fu;
				} else if (lead >= 0xC0) {
					extra = 1;
					point = lead & 0x1Fu;
				} else if (lead >= 0x80) {
					// Одиночный продолжающий байт - строка битая; пропускаем.
					++i;
					continue;
				}
				if (i + extra >= a_text.size()) {
					break;
				}
				for (std::size_t k = 1; k <= extra; ++k) {
					point = (point << 6) | (static_cast<unsigned char>(a_text[i + k]) & 0x3Fu);
				}
				out.push_back(point);
				i += extra + 1;
			}
			return out;
		}

		char32_t Lower(char32_t a_point)
		{
			if (a_point >= U'A' && a_point <= U'Z') {
				return a_point + 0x20;
			}
			if (a_point >= 0x0410 && a_point <= 0x042F) {   // А-Я
				return a_point + 0x20;
			}
			if (a_point >= 0x0400 && a_point <= 0x040F) {   // Ѐ-Џ, сюда же Ё
				return a_point + 0x50;
			}
			return a_point;
		}

		bool IsSpace(char32_t a_point)
		{
			// Пробельные - числами: табулятор, перевод строки, возврат каретки
			// и неразрывный пробел.
			return a_point == U' ' || a_point == 0x09 || a_point == 0x0A ||
			       a_point == 0x0D || a_point == 0x00A0;
		}

		bool IsPunct(char32_t a_point)
		{
			if (a_point < 0x80) {
				return std::ispunct(static_cast<int>(a_point)) != 0;
			}
			// Знаки, которые в самом деле приходят от распознавания: кавычки-ёлочки,
			// типографские кавычки и тире, многоточие.
			return a_point == 0x00AB || a_point == 0x00BB ||
			       (a_point >= 0x2010 && a_point <= 0x2015) ||
			       (a_point >= 0x2018 && a_point <= 0x201F) ||
			       a_point == 0x2026;
		}

		std::u32string Normalize(const std::string& a_text)
		{
			std::u32string out;
			for (const auto point : Decode(a_text)) {
				if (IsSpace(point)) {
					if (!out.empty() && out.back() != U' ') {
						out.push_back(U' ');
					}
				} else if (!IsPunct(point)) {
					out.push_back(Lower(point));
				}
			}
			while (!out.empty() && out.back() == U' ') {
				out.pop_back();
			}
			return out;
		}

		// Похожесть строк без внешних библиотек: расстояние редактирования,
		// приведённое к доле от длины. Для команд и коротких фраз этого хватает.
		float Similarity(const std::u32string& a_left, const std::u32string& a_right)
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
		std::vector<Phrase> prepared;
		prepared.reserve(a_phrases.size());
		for (auto& phrase : a_phrases) {
			prepared.push_back(Phrase{ phrase, Normalize(phrase) });
		}

		std::scoped_lock lock(_mutex);
		_entries[a_ns].vocabulary = std::move(prepared);
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
			const auto score = Similarity(text, phrase.normalized);
			if (score > best.score) {
				second = best.score;
				best.score = score;
				best.phrase = phrase.text;
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
			for (const auto& phrase : entry.second.vocabulary) {
				out.push_back(phrase.text);
			}
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
