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
		float        minUtteranceScore{ 0.4f };
		bool         sharedWinsTie{ true };
		double       utteranceTtlSec{ 30.0 };
		std::size_t  utteranceMaxStored{ 64 };

		// Класс цены: 0 - обратимое действие, 1 - дорогое.
		float MinConfidence(std::int32_t a_costClass) const;
		float MinMargin(std::int32_t a_costClass) const;

		// Место участника в порядке из настроек; kNoPriority - не назван.
		std::size_t PriorityIndex(const std::string& a_ns) const;

	private:
		Settings() = default;

		static Settings& Instance();
		void             Read();

		float                    _minConfidence[2]{ 0.55f, 0.75f };
		float                    _minMargin[2]{ 0.05f, 0.15f };
		std::vector<std::string> _priority;
		bool                     _read{ false };
	};
}
