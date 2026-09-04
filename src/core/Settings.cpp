#include "Settings.h"

#include "Config.h"

#include <SKSE/SKSE.h>

#include <algorithm>

namespace Envoy
{
	Settings& Settings::Instance()
	{
		static Settings instance;
		if (!instance._read) {
			instance.Read();
		}
		return instance;
	}

	const Settings& Settings::Get()
	{
		return Instance();
	}

	void Settings::Reload()
	{
		Instance().Read();
	}

	float Settings::MinConfidence(std::int32_t a_costClass) const
	{
		return _minConfidence[a_costClass == 1 ? 1 : 0];
	}

	float Settings::MinMargin(std::int32_t a_costClass) const
	{
		return _minMargin[a_costClass == 1 ? 1 : 0];
	}

	std::size_t Settings::PriorityIndex(const std::string& a_ns) const
	{
		const auto it = std::find(_priority.begin(), _priority.end(), a_ns);
		return it == _priority.end() ? kNoPriority
		                             : static_cast<std::size_t>(std::distance(_priority.begin(), it));
	}

	void Settings::Read()
	{
		const auto& cfg = Config::Get();

		bidWindowMs        = cfg.Value<std::int32_t>("/auction/bidWindowMs").value_or(750);
		minUtteranceScore  = cfg.Value<float>("/auction/minUtteranceScore").value_or(0.4f);
		sharedWinsTie      = cfg.Value<bool>("/auction/sharedWinsTie").value_or(true);
		_minConfidence[0]  = cfg.Value<float>("/auction/minConfidence/reversible").value_or(0.55f);
		_minConfidence[1]  = cfg.Value<float>("/auction/minConfidence/costly").value_or(0.75f);
		_minMargin[0]      = cfg.Value<float>("/auction/minMargin/reversible").value_or(0.05f);
		_minMargin[1]      = cfg.Value<float>("/auction/minMargin/costly").value_or(0.15f);
		_priority          = cfg.Value<std::vector<std::string>>("/auction/priority")
		                        .value_or(std::vector<std::string>{});
		utteranceTtlSec    = cfg.Value<double>("/utterance/ttlSec").value_or(30.0);
		utteranceMaxStored = cfg.Value<std::size_t>("/utterance/maxStored").value_or(64);

		_read = true;

		// Ключей в файле больше, чем мост читает сегодня: остальные - точки
		// расширения, и по виду они неотличимы от рабочих настроек. Поэтому
		// вслух перечисляем прочитанные: иначе наладчик будет крутить ручку,
		// которая никуда не подключена, и не узнает об этом.
		SKSE::log::info(
			"настройки прочитаны: окно ставок {} мс, порог реплики {:.2f}, "
			"уверенность {:.2f}/{:.2f}, отрыв {:.2f}/{:.2f}, ничью берёт делящийся: {}, "
			"порядок участников: {}, хранение {:.0f} с не более {} реплик",
			bidWindowMs, minUtteranceScore, _minConfidence[0], _minConfidence[1],
			_minMargin[0], _minMargin[1], sharedWinsTie ? "да" : "нет", _priority.size(),
			utteranceTtlSec, utteranceMaxStored);
	}
}
