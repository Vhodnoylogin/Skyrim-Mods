#pragma once

#include <cstddef>
#include <cstdint>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace Envoy
{
	struct VocabularyMatch
	{
		std::string phrase;
		float       score{ 0.0f };
		float       margin{ 0.0f };
	};

	// Фраза словаря вместе со своей приведённой формой. Приведение делается
	// один раз, при объявлении словаря: прежде оно повторялось на каждый вопрос
	// о совпадении, то есть по разу на подписчика на каждую реплику.
	struct Phrase
	{
		std::string    text;        // как объявил мод - её и возвращаем наружу
		std::u32string normalized;  // по ней сравниваем
	};

	// Кто на что подписан и какие фразы объявил. Словарями владеет мост:
	// сопоставление делается здесь, на C++, чтобы не заставлять Papyrus
	// возиться со строками - он это делает плохо и медленно.
	class SubscriptionRegistry
	{
	public:
		static SubscriptionRegistry& Get();

		void Subscribe(const std::string& a_ns, std::vector<std::string> a_topics);
		void Unsubscribe(const std::string& a_ns);
		void SetActive(const std::string& a_ns, bool a_active);
		void SetVocabulary(const std::string& a_ns, std::vector<std::string> a_phrases);
		void ClearVocabulary(const std::string& a_ns);

		VocabularyMatch          Match(const std::string& a_ns, const std::string& a_text) const;
		std::vector<std::string> MergedVocabulary() const;
		// Кто объявился и на какие темы - чтобы участник мог показать это игроку.
		std::vector<std::string> Namespaces() const;
		std::vector<std::string> TopicsOf(const std::string& a_ns) const;
		std::size_t              Count() const;

	private:
		SubscriptionRegistry() = default;

		struct Entry
		{
			std::vector<std::string> topics;
			std::vector<Phrase>      vocabulary;
			bool                     active{ true };
		};

		mutable std::mutex                     _mutex;
		std::unordered_map<std::string, Entry> _entries;
	};
}
