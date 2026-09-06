#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace Envoy
{
	// Разобранные настройки вместо указателей в документе JSON.
	//
	// Файл читается дважды за сессию - при первом обращении и по ReloadSettings, -
	// а в бою берутся готовые поля. До этого порядок участников извлекался из
	// JSON на каждое сравнение внутри сортировки ставок, с выделением вектора
	// строк на каждое; пороги склеивали указатель из кусков на каждую ставку.
	class Settings
	{
	public:
		static constexpr std::size_t kNoPriority = static_cast<std::size_t>(-1);

		static const Settings& Get();
		static void            Reload();

		std::int32_t bidWindowMs{ 750 };
		// Сколько риска мы согласны терпеть, отдавая реплику. Настраивается
		// именно допуск, а не порог завершённости: порог считается от него
		// и от состава зала.
		float        holdTolerance{ 0.15f };
		float        minUtteranceScore{ 0.4f };
		bool         sharedWinsTie{ true };
		double       utteranceTtlSec{ 30.0 };
		std::size_t  utteranceMaxStored{ 64 };

		// Класс цены: 0 - обратимое действие, 1 - дорогое.
		float MinConfidence(std::int32_t a_costClass) const;
		float MinMargin(std::int32_t a_costClass) const;

		// Цена ошибки одного подписчика, если отдать ему обрывок фразы.
		float HoldWeight(std::int32_t a_costClass, bool a_revocable) const;
		// Дольше этого реплику своего класса длины не держим ни при чём.
		std::int32_t HoldCeilingMs(std::int32_t a_lengthClass) const;

		// Место участника в порядке из настроек; kNoPriority - не назван.
		std::size_t PriorityIndex(const std::string& a_ns) const;

	private:
		Settings() = default;

		static Settings& Instance();
		void             Read();

		float                    _minConfidence[2]{ 0.55f, 0.75f };
		float                    _minMargin[2]{ 0.05f, 0.15f };
		// Отзывчивый / обычный обратимый / дорогой.
		float                    _holdWeight[3]{ 0.1f, 0.4f, 1.0f };
		// Короткая / средняя / длинная.
		//
		// Это не бюджет задержки, а страховка от молчащего адаптера. Потолок
		// обязан пережить приход продолжения: если он короче, чем пауза, после
		// которой движок отдаёт следующий кусок, придержание кончится раньше,
		// чем мы узнаем то, ради чего держали.
		std::int32_t             _holdCeilingMs[3]{ 2500, 1500, 800 };
		std::vector<std::string> _priority;
		bool                     _read{ false };
	};
}
