#pragma once

#include <optional>
#include <string>
#include <vector>

namespace Voice
{
	// Как поднимать службу модели, если она не отвечает на /health.
	struct AutoStart
	{
		bool                     enabled{ false };
		std::string              exec;
		std::vector<std::string> args;
		std::string              workingDir;
		std::string              parentPidArg;
		int                      waitSec{ 60 };  // сколько ждать, пока поднятая служба ответит
		int                      pollSec{ 1 };   // с каким шагом спрашивать её /health в это время
	};

	// Одна модель: служба, к которой адаптер ходит по HTTP. Частный случай
	// "быстрая плюс точная" - это две записи с разными классами.
	struct Model
	{
		std::string              id;
		bool                     fast{ false };  // class == "fast": отдаёт черновик, а не окончательный ответ
		bool                     enabled{ false };
		std::string              url;
		std::string              language;
		int                      listenTimeoutSec{ 30 };
		std::optional<AutoStart> autoStart;      // ключа нет - не поднимаем и не жалуемся
	};

	// Настройки адаптера. Файл читается один раз при загрузке плагина и
	// разбирается в поля сразу: потоки опроса и озвучки берут готовые значения,
	// а не ищут ключи в json на каждую реплику.
	//
	// Значения по умолчанию у полей - те, что подставляются при отсутствии
	// ключа в файле. Они же были зашиты в коде до того, как стали ключами,
	// поэтому файл без новых ключей ведёт себя ровно как прежде.
	class Config
	{
	public:
		// Читает файл. При отказе поля остаются со значениями по умолчанию,
		// но работать без файла адаптер не станет - об этом решает вызывающий.
		static bool Load();

		static const Config& Get();

		std::string        adapterId{ "voice" };
		std::string        adapterName;
		std::string        adapterProvides{ "asr" };
		std::vector<Model> models;
		std::string        speakModel;

		int correlateMs{ 2500 };     // точный ответ в этом окне после черновика считается его уточнением
		int retryDelayMs{ 2000 };    // пауза после неудачного /listen
		int healthTimeoutSec{ 2 };   // сколько ждать соединения на /health
		int listenGraceSec{ 10 };    // насколько дольше срока службы ждать ответ /listen
		int idleSleepMs{ 1000 };     // шаг ожидания, пока мост держит нас в запасе
		int sayTimeoutSec{ 120 };    // сколько ждать ответа /say

	private:
		Config() = default;

		static Config& Mutable();
	};
}
