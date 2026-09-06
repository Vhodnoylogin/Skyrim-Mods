#include "Settings.h"

#include "Config.h"

#include <spdlog/spdlog.h>

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

	float Settings::HoldWeight(std::int32_t a_costClass, bool a_revocable) const
	{
		// Дорогое остаётся дорогим, даже если объявлено отзывчивым: отменить
		// брошенное заклинание нельзя, сколько бы мод об этом ни заявлял.
		if (a_costClass >= 1) {
			return _holdWeight[2];
		}
		return a_revocable ? _holdWeight[0] : _holdWeight[1];
	}

	std::int32_t Settings::HoldCeilingMs(std::int32_t a_lengthClass) const
	{
		const auto index = a_lengthClass < 0 ? 0 : (a_lengthClass > 2 ? 2 : a_lengthClass);
		return _holdCeilingMs[index];
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
		holdTolerance      = cfg.Value<float>("/auction/hold/tolerance").value_or(0.27f);
		_holdWeight[0]     = cfg.Value<float>("/auction/hold/weight/revocable").value_or(0.1f);
		_holdWeight[1]     = cfg.Value<float>("/auction/hold/weight/plain").value_or(0.4f);
		_holdWeight[2]     = cfg.Value<float>("/auction/hold/weight/costly").value_or(1.0f);
		_holdCeilingMs[0]  = cfg.Value<std::int32_t>("/auction/hold/ceilingMs/short").value_or(2500);
		_holdCeilingMs[1]  = cfg.Value<std::int32_t>("/auction/hold/ceilingMs/middle").value_or(1500);
		_holdCeilingMs[2]  = cfg.Value<std::int32_t>("/auction/hold/ceilingMs/long").value_or(800);
		utteranceTtlSec    = cfg.Value<double>("/utterance/ttlSec").value_or(30.0);
		utteranceMaxStored = cfg.Value<std::size_t>("/utterance/maxStored").value_or(64);

		_read = true;

		// Ключей в файле больше, чем мост читает сегодня: остальные - точки
		// расширения, и по виду они неотличимы от рабочих настроек. Поэтому
		// вслух перечисляем прочитанные: иначе наладчик будет крутить ручку,
		// которая никуда не подключена, и не узнает об этом.
		spdlog::info(
			"настройки прочитаны: окно ставок {} мс, порог реплики {:.2f}, "
			"уверенность {:.2f}/{:.2f}, отрыв {:.2f}/{:.2f}, ничью берёт делящийся: {}, "
			"порядок участников: {}, хранение {:.0f} с не более {} реплик, "
			"допуск придержания {:.2f}, цена ошибки {:.2f}/{:.2f}/{:.2f}, "
			"потолок {}/{}/{} мс",
			bidWindowMs, minUtteranceScore, _minConfidence[0], _minConfidence[1],
			_minMargin[0], _minMargin[1], sharedWinsTie ? "да" : "нет", _priority.size(),
			utteranceTtlSec, utteranceMaxStored, holdTolerance,
			_holdWeight[0], _holdWeight[1], _holdWeight[2],
			_holdCeilingMs[0], _holdCeilingMs[1], _holdCeilingMs[2]);
	}
}
