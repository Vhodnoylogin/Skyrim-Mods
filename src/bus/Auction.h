#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace Envoy
{
	struct Utterance;

	// Спор за реплику решается объявленными величинами, а не порядком, в котором
	// движок разбудил скрипты: иначе одна и та же фраза вела бы себя по-разному
	// от запуска к запуску.
	class Auction
	{
	public:
		struct Result
		{
			std::vector<std::string>                     winners;  // пусто - не делает никто
			std::unordered_map<std::string, std::string> denied;   // кому отказано и почему
			std::string                                  reason;
		};

		// Предложить реплику подписчикам и запустить окно ставок.
		// Вызывать из главного потока.
		static void Offer(std::int32_t a_id);

		// Подвести итог. Вызывать из главного потока по истечении окна.
		static void Settle(std::int32_t a_id);

		static Result Decide(const Utterance& a_utterance);

		// Сколько миллисекунд прошло с оглашения реплики. Нужно затем, чтобы
		// в журнале было видно, успевает ли Papyrus ответить внутри окна ставок:
		// в первом живом прогоне ни одна ставка не пришла, и отличить "скрипт
		// промолчал" от "скрипт опоздал" было нечем.
		static std::int64_t MsSinceOffer(std::int32_t a_id);
	};
}
