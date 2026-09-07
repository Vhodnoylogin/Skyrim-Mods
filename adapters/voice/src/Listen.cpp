#include "Listen.h"

#include "Bridge.h"
#include "Service.h"

#include <RE/Skyrim.h>
#include <SKSE/SKSE.h>

#include <nlohmann/json.hpp>
#include <httplib.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

namespace Voice
{
	namespace
	{
		// Связь между результатами разных моделей и перевод номеров между
		// службой и мостом. Одно состояние на все потоки опроса, под одним замком.
		//
		// Пока у источника звука нет общего номера куска, результаты разных моделей
		// связываются по времени: точный ответ, пришедший вскоре после
		// предварительного, считается его уточнением. Это временно и честно помечено.
		//
		// Номер реплики у службы и у моста - разные числа. Служба говорит, какие
		// СВОИ куски вобрал новый; мост понимает только свои. Перевод живёт здесь:
		// адаптер - единственный, кто знает обе стороны, и держать эту карту
		// где-либо ещё значило бы заставить одну из сторон знать про другую.
		class Correlation
		{
		public:
			// Номера службы -> номера моста; неизвестные службе номера пропускаются.
			std::vector<std::int32_t> Translate(const nlohmann::json& a_serviceIds)
			{
				std::vector<std::int32_t> out;
				std::scoped_lock          lock(_lock);
				for (const auto& mark : a_serviceIds) {
					const auto found = _serviceToBridge.find(mark.get<std::int32_t>());
					if (found != _serviceToBridge.end()) {
						out.push_back(found->second);
					}
				}
				return out;
			}

			// Для точного ответа: номер черновика, который он уточняет, либо 0.
			// Черновик отдаётся один раз - второй точный ответ его уже не получит.
			std::int32_t TakePreliminary(std::chrono::milliseconds a_window)
			{
				std::scoped_lock lock(_lock);
				if (_lastPreliminary != 0 &&
					std::chrono::steady_clock::now() - _lastPreliminaryAt < a_window) {
					return std::exchange(_lastPreliminary, 0);
				}
				return 0;
			}

			void Remember(bool a_fast, std::int32_t a_serviceId, std::int32_t a_bridgeId)
			{
				std::scoped_lock lock(_lock);
				if (a_fast) {
					_lastPreliminary = a_bridgeId;
					_lastPreliminaryAt = std::chrono::steady_clock::now();
				}
				// Запоминаем перевод, чтобы следующий кусок мог назвать поглощённые.
				// Карта растёт на реплику за ход разговора; чистим её по тому же
				// сроку, по которому мост забывает сами реплики.
				if (a_serviceId != 0) {
					_serviceToBridge[a_serviceId] = a_bridgeId;
					if (_serviceToBridge.size() > 256) {
						_serviceToBridge.clear();
					}
				}
			}

		private:
			std::mutex                                     _lock;
			std::int32_t                                   _lastPreliminary{ 0 };
			std::chrono::steady_clock::time_point          _lastPreliminaryAt{};
			std::unordered_map<std::int32_t, std::int32_t> _serviceToBridge;
		};

		Correlation g_correlation;

		void PushResult(const Model& a_model, const nlohmann::json& a_item)
		{
			auto& bridge = Bridge::Get();
			if (!bridge.Ready()) {
				return;
			}

			const auto text = a_item.value("text", std::string{});
			const auto engine = a_item.value("engine", std::string{});

			EnvoyAPI::UtteranceIn in{};
			in.text = text.c_str();
			in.language = a_model.language.c_str();
			in.engine = engine.c_str();
			in.channel = "";
			in.score = a_item.value("score", 0.0f);
			in.margin = a_item.value("margin", 0.0f);
			in.latencyMs = a_item.value("ms", 0);
			in.durationMs = 0;
			in.isFinal = !a_model.fast;

			// --- третья версия контракта ----------------------------------------
			// Служба на новом движке отдаёт не целую фразу после молчания, а куски
			// по ходу речи, и о каждом говорит, насколько уверена, что фраза на нём
			// кончилась. Мост придерживает незаконченное - но только если ему это
			// сказали, а сказать может лишь тот, кто слышит паузу.
			//
			// Служба, которая об этом ничего не знает, полей не пришлёт, и значения
			// останутся прежними: завершённость единица, поглощать нечего.
			in.complete = a_item.value("complete", 1.0f);
			in.lengthClass = a_item.value("lengthClass", 0);

			// Номера служба даёт свои, сквозные; мост знает только свои. Перевод
			// держим здесь: это ровно та работа, ради которой адаптер и существует -
			// он один знает обе стороны.
			std::vector<std::int32_t> swallowed;
			if (a_item.contains("supersedes")) {
				swallowed = g_correlation.Translate(a_item["supersedes"]);
			}
			if (!swallowed.empty()) {
				in.supersedes = swallowed.data();
				in.supersedesCount = static_cast<std::int32_t>(swallowed.size());
			}

			if (!a_model.fast) {
				in.refinesId = g_correlation.TakePreliminary(
					std::chrono::milliseconds(Config::Get().correlateMs));
			}

			const auto id = bridge.PushUtterance(in);
			if (id == 0) {
				SKSE::log::warn("мост не принял реплику от модели {}", a_model.id);
				return;
			}

			g_correlation.Remember(a_model.fast, a_item.value("id", 0), id);

			if (!swallowed.empty()) {
				SKSE::log::info("реплика {} поглощает {} прежних, завершённость {:.2f}",
					id, swallowed.size(), in.complete);
			}
		}
	}

	void PollModel(const Model& a_model)
	{
		const auto&   config = Config::Get();
		const Service service(a_model);
		const auto&   ep = service.Where();
		const auto    timeout = a_model.listenTimeoutSec;
		int           since = 0;

		// Два разных исхода, и в журнале они обязаны различаться: иначе по нему
		// не понять, проверили мы самостоятельный запуск службы или подключились
		// к поднятой заранее руками.
		if (service.Alive()) {
			SKSE::log::info("модель {}: уже поднята, подключаюсь к ней", a_model.id);
		} else {
			service.Launch();
		}

		// Выхода из цикла нет намеренно: поток отсоединён и умирает вместе с
		// процессом игры, а своего завершения адаптер выполнить не успевает.
		for (;;) {
			if (!Bridge::Get().Listening()) {
				std::this_thread::sleep_for(std::chrono::milliseconds(config.idleSleepMs));
				continue;
			}

			httplib::Client client(ep.host, ep.port);
			// Служба держит /listen весь свой срок, пока не наберётся речи; ждать её
			// надо дольше, чем она держит, иначе клиент оборвёт законный ответ на пороге.
			client.set_read_timeout(timeout + config.listenGraceSec, 0);
			const auto path = "/listen?since=" + std::to_string(since) +
			                  "&timeout=" + std::to_string(timeout);
			auto res = client.Get(path);
			if (!res || res->status != 200) {
				std::this_thread::sleep_for(std::chrono::milliseconds(config.retryDelayMs));
				continue;
			}

			try {
				auto body = nlohmann::json::parse(res->body);
				for (const auto& item : body.value("utterances", nlohmann::json::array())) {
					since = std::max(since, item.value("id", 0));
					PushResult(a_model, item);
				}
			} catch (const std::exception& e) {
				SKSE::log::warn("модель {}: ответ не разобран - {}", a_model.id, e.what());
			}
		}
	}
}
