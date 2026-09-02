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
		// Сколько раз лучшая фраза подписчика встречается во фразе целиком.
		// Решать, две это команды или одна оговорка, мост не берётся - он лишь
		// считает, потому что Papyrus со строками работает плохо.
		std::int32_t             Repeats(const std::string& a_ns, const std::string& a_text) const;
		std::vector<std::string> MergedVocabulary() const;
		std::size_t              Count() const;

	private:
		SubscriptionRegistry() = default;

		struct Entry
		{
			std::vector<std::string> topics;
			std::vector<std::string> vocabulary;
			bool                     active{ true };
		};

		mutable std::mutex                     _mutex;
		std::unordered_map<std::string, Entry> _entries;
	};
}
