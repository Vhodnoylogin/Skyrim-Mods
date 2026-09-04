#pragma once

#include <chrono>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace Envoy
{
	struct Alternative
	{
		std::string text;
		float       score{ 0.0f };
	};

	struct BidRecord
	{
		std::string  ns;
		float        confidence{ 0.0f };
		std::int32_t costClass{ 0 };   // 0 - обратимое, 1 - дорогое
		// Жадность - заявка на исключительность. Срабатывает только если
		// заявитель победил; при чужой победе жадный выбывает из раздачи
		// по собственному условию "мне одному или никак".
		bool         greedy{ false };
		// Фраза словаря, которую заявитель узнал в реплике. Мост определяет её
		// сам, потому что словари принадлежат ему. Нужна она затем, что ничья
		// бывает двух разных родов: двое поняли РАЗНОЕ одинаково уверенно -
		// реплика двусмысленна; двое поняли ОДНО и то же - спор о том, чья это
		// команда. Решать их одинаково нельзя.
		std::string  phrase;
	};

	// Реплика живёт в игре под своим номером: событие приносит подписчику только
	// номер, всё остальное он забирает функциями.
	struct Utterance
	{
		std::int32_t             id{ 0 };
		bool                     isFinal{ false };
		std::string              text;
		std::vector<Alternative> alternatives;
		float                    score{ 0.0f };
		float                    margin{ 0.0f };
		std::string              language;
		std::string              engine;
		std::string              channel;
		std::int32_t             latencyMs{ 0 };
		std::int32_t             durationMs{ 0 };
		bool                     wakeWord{ false };

		std::string              topic;
		// Длина - это не свойство текста, а способ нарезки: короткие куски
		// режутся по короткой паузе, длинные склеиваются из них по длинной.
		std::int32_t             lengthClass{ 0 };   // 0 короткая, 1 средняя, 2 длинная
		// Номер куска у источника звука; 0 - соотносить не с чем.
		std::int32_t             sliceId{ 0 };
		// Номер длинной реплики, вобравшей эту; 0 - пока не вобрана.
		std::int32_t             supersededBy{ 0 };
		std::vector<BidRecord>                       bids;
		std::vector<std::string>                     winners;
		std::unordered_map<std::string, std::string> denied;   // кому отказано и почему
		std::string                                  outcome;  // текст итога для наблюдателя
		bool                                         awarded{ false };

		std::chrono::steady_clock::time_point born{ std::chrono::steady_clock::now() };
		// Когда реплику огласили подписчикам. Отметка нужна и после итога:
		// опоздавшая ставка должна суметь сказать, насколько опоздала. Раньше
		// она жила в отдельной карте с собственным мьютексом и собственной
		// чисткой - хотя это обычное поле реплики.
		std::chrono::steady_clock::time_point offeredAt{};

		// Сколько миллисекунд прошло с оглашения; -1 - ещё не оглашали. Нужно
		// затем, чтобы в журнале было видно, успевает ли Papyrus ответить внутри
		// окна ставок: в первом живом прогоне ни одна ставка не пришла, и
		// отличить "скрипт промолчал" от "скрипт опоздал" было нечем.
		std::int64_t MsSinceOffer() const
		{
			if (offeredAt.time_since_epoch().count() == 0) {
				return -1;
			}
			return std::chrono::duration_cast<std::chrono::milliseconds>(
				std::chrono::steady_clock::now() - offeredAt).count();
		}
	};
}
