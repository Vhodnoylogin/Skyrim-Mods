// Envoy Framework - прогон аукциона без игры.
//
//     envoy-host [--subscribers <папка>] [--scenario <файл>] [--report <файл>]
//
// Ядро здесь то же самое, что внутри игры: те же аукцион, хранилище реплик,
// выбор темы и словари. Разница ровно в трёх ответах, которые вместо Skyrim
// даёт этот хост:
//
//   работа        - делается на месте, а не в главном потоке игры;
//   состояние     - берётся из сценария, а не у движка;
//   события       - пишутся в журнал, а не рассылаются Papyrus.
//
// Подписчики здесь тоже не настоящие. От них нужны только объявленные данные -
// на какие темы подписаны и какой словарь заявили. Как подписчик поступит
// с выигрышем, проверку не занимает: вопрос в том, КОМУ мост отдал фрагмент
// и почему, а не в том, что победитель потом сделал.

#include "bus/Auction.h"
#include "bus/SubscriptionRegistry.h"
#include "bus/TopicRouter.h"
#include "bus/Utterance.h"
#include "bus/UtteranceStore.h"
#include "core/Config.h"
#include "core/GameState.h"
#include "core/Log.h"
#include "core/Scheduler.h"
#include "core/Settings.h"

#include <nlohmann/json.hpp>
#include <spdlog/spdlog.h>

#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#	include <windows.h>
#endif

namespace
{
	namespace fs = std::filesystem;
	using json = nlohmann::json;

	// Состояние игры по сценарию.
	//
	// Вне игры её нет, но выкинуть состояние из проверки нельзя: тема выбирается
	// именно по нему, и «сказано в бою» против «сказано в мире» - это разные
	// наборы подписчиков, а не оттенок.
	class ScriptedState final : public Envoy::GameState::Source
	{
	public:
		std::string menu;
		bool        paused{ false };
		bool        combat{ false };

		void Reset()
		{
			menu.clear();
			paused = false;
			combat = false;
		}

		bool IsMenuOpen(const std::string& a_name) const override
		{
			return !menu.empty() && a_name == menu;
		}
		bool IsPaused() const override { return paused; }
		bool IsInCombat() const override { return combat; }
	};

	// Тестовый подписчик: только то, что он о себе объявил.
	struct TestSubscriber
	{
		std::string              ns;
		std::vector<std::string> topics;
		std::vector<std::string> vocabulary;
		std::int32_t             costClass{ 0 };   // 0 обратимое, 1 дорогое
		bool                     greedy{ false };

		// Дойдёт ли до него оглашение этой темы. "any" - слышит всё; так
		// объявляют себя наблюдатели, которым важно видеть каждую реплику.
		bool Hears(const std::string& a_topic) const
		{
			for (const auto& mine : topics) {
				if (mine == "any" || mine == a_topic) {
					return true;
				}
				// Канал приходит темой вида "channel:имя".
				if (mine == "channel" && a_topic.rfind("channel:", 0) == 0) {
					return true;
				}
			}
			return false;
		}
	};

	std::string CostName(std::int32_t a_class)
	{
		return a_class == 1 ? "дорогое" : "обратимое";
	}

	json ReadJson(const fs::path& a_path)
	{
		std::ifstream in(a_path, std::ios::binary);
		if (!in) {
			return json{};
		}
		try {
			return json::parse(in);
		} catch (const std::exception& exc) {
			spdlog::error("не разобран {}: {}", a_path.string(), exc.what());
			return json{};
		}
	}

	std::vector<TestSubscriber> LoadSubscribers(const fs::path& a_dir)
	{
		std::vector<TestSubscriber> out;
		if (!fs::exists(a_dir)) {
			spdlog::error("нет папки подписчиков: {}", a_dir.string());
			return out;
		}

		std::vector<fs::path> files;
		for (const auto& entry : fs::directory_iterator(a_dir)) {
			if (entry.is_regular_file() && entry.path().extension() == ".json") {
				files.push_back(entry.path());
			}
		}
		// По имени файла: порядок объявления не должен зависеть от того,
		// как файловая система решила их отдать.
		std::sort(files.begin(), files.end());

		for (const auto& file : files) {
			const auto doc = ReadJson(file);
			if (!doc.is_object()) {
				continue;
			}

			TestSubscriber sub;
			sub.ns = doc.value("namespace", file.stem().string());
			sub.topics = doc.value("topics", std::vector<std::string>{ "world" });
			sub.vocabulary = doc.value("vocabulary", std::vector<std::string>{});
			sub.costClass = doc.value("cost", std::string{ "reversible" }) == "costly" ? 1 : 0;
			sub.greedy = doc.value("greedy", false);
			out.push_back(std::move(sub));
		}
		return out;
	}

	void Declare(const std::vector<TestSubscriber>& a_subs)
	{
		auto& registry = Envoy::SubscriptionRegistry::Get();
		for (const auto& sub : a_subs) {
			registry.Subscribe(sub.ns, sub.topics);
			if (!sub.vocabulary.empty()) {
				registry.SetVocabulary(sub.ns, sub.vocabulary);
			}

			std::string topics;
			for (const auto& topic : sub.topics) {
				topics += topics.empty() ? topic : ", " + topic;
			}
			spdlog::info("подписчик {}: темы [{}], фраз {}, {}{}", sub.ns, topics,
				sub.vocabulary.size(), CostName(sub.costClass),
				sub.greedy ? ", жадный" : "");
		}
	}
}

int main(int argc, char** argv)
{
#ifdef _WIN32
	::SetConsoleOutputCP(CP_UTF8);
#endif

	fs::path subscribersDir = ENVOY_TEST_DIR "/subscribers";
	fs::path scenarioFile = ENVOY_TEST_DIR "/scenarios/default.json";
	fs::path configFile = "envoy-host.json";
	fs::path reportFile;

	for (int i = 1; i + 1 < argc; ++i) {
		const std::string key = argv[i];
		if (key == "--subscribers") {
			subscribersDir = argv[++i];
		} else if (key == "--scenario") {
			scenarioFile = argv[++i];
		} else if (key == "--config") {
			configFile = argv[++i];
		} else if (key == "--report") {
			reportFile = argv[++i];
		}
	}

	Envoy::Log::ToConsole("info");

	// Файл настроек хост заводит себе сам: встроенный эталон разворачивается
	// рядом с исполняемым, и правила аукциона получаются ровно те же, что
	// в игре, - без единого пути, заданного здесь.
	auto& config = Envoy::Config::Get();
	config.Load(configFile);
	spdlog::info("{}: {}", Envoy::Config::Describe(config.Source()), config.Path().string());

	static ScriptedState state;
	Envoy::GameState::Install(&state);

	const auto subs = LoadSubscribers(subscribersDir);
	if (subs.empty()) {
		spdlog::error("ни одного подписчика - проверять нечего");
		return 2;
	}
	Declare(subs);

	const auto scenario = ReadJson(scenarioFile);
	const auto steps = scenario.contains("steps") ? scenario["steps"] : json::array();
	if (steps.empty()) {
		spdlog::error("в сценарии нет шагов: {}", scenarioFile.string());
		return 2;
	}

	spdlog::info("сценарий «{}», шагов {}",
		scenario.value("name", scenarioFile.stem().string()), steps.size());

	std::ostringstream report;
	report << "=== прогон аукциона без игры ===\n\n";
	report << "сценарий: " << scenario.value("name", scenarioFile.stem().string()) << "\n";
	report << "окно ставок: " << Envoy::Settings::Get().bidWindowMs << " мс\n\n";

	for (const auto& step : steps) {
		state.Reset();
		if (step.contains("state")) {
			const auto& s = step["state"];
			state.menu = s.value("menu", std::string{});
			state.paused = s.value("paused", false);
			state.combat = s.value("combat", false);
		}

		Envoy::Utterance utterance;
		utterance.text = step.value("text", std::string{});
		utterance.score = step.value("score", 0.9f);
		utterance.margin = step.value("margin", 0.3f);
		utterance.channel = step.value("channel", std::string{});
		utterance.language = step.value("language", std::string{ "ru" });
		utterance.engine = step.value("engine", std::string{ "host" });
		utterance.isFinal = true;

		const auto id = Envoy::UtteranceStore::Get().Add(utterance);

		spdlog::info("--- реплика {}: «{}» ---", id, utterance.text);

		// Оглашение выбирает тему и рассылает события. Отсюда и дальше всё
		// делает ядро - ровно то же, что в игре.
		Envoy::Auctioneer::Get().Offer(id);

		auto offered = Envoy::UtteranceStore::Get().Find(id);
		const std::string topic = offered ? offered->topic : std::string{ "?" };

		// Ставки вместо скриптов Papyrus. Уверенность берётся из совпадения
		// со словарём - тем самым, что подписчик объявил: своего мнения
		// у тестового подписчика нет и быть не должно.
		std::size_t placed = 0;
		for (const auto& sub : subs) {
			if (!sub.Hears(topic)) {
				continue;
			}
			const auto match = Envoy::SubscriptionRegistry::Get().Match(sub.ns, utterance.text);
			if (match.score <= 0.0f) {
				continue;
			}

			// Уверенность - произведение двух разных величин: насколько хорошо
			// реплику вообще расслышали и насколько она похожа на объявленную
			// фразу. Одного совпадения со словарём мало: невнятно сказанная
			// команда совпадает со словарём ровно так же, как чётко сказанная,
			// и без множителя разница между ними пропадала - шаг «сказано тихо»
			// давал тот же исход, что и «сказано ясно».
			//
			// Настоящий подписчик считает свою уверенность сам; здесь взято
			// простейшее защитимое правило, потому что поведение подписчиков
			// проверку не занимает.
			const float confidence = match.score * utterance.score;

			Envoy::UtteranceStore::Get().AddBid(id,
				Envoy::BidRecord{ sub.ns, confidence, sub.costClass, sub.greedy, match.phrase });
			++placed;
			spdlog::info("ставка {}: уверенность {:.2f} (слышимость {:.2f} x словарь {:.2f}), "
			             "фраза «{}», {}{}",
				sub.ns, confidence, utterance.score, match.score, match.phrase,
				CostName(sub.costClass), sub.greedy ? ", жадный" : "");
		}
		if (placed == 0) {
			spdlog::info("ставок нет - никто из подписчиков темы {} не узнал фразу", topic);
		}

		// Итог подводит сам аукционист по истечении окна ставок, из потока
		// планировщика. Ждём его, а не подводим за него: проверять надо то,
		// что работает в игре.
		std::this_thread::sleep_for(
			std::chrono::milliseconds(Envoy::Settings::Get().bidWindowMs + 250));

		auto done = Envoy::UtteranceStore::Get().Find(id);

		report << "реплика " << id << ": «" << utterance.text << "»\n";
		report << "    тема      : " << topic << "\n";
		report << "    ставок    : " << (done ? done->bids.size() : 0) << "\n";
		if (done) {
			for (const auto& bid : done->bids) {
				report << "        " << bid.ns << "  " << bid.confidence
				       << "  " << CostName(bid.costClass)
				       << (bid.greedy ? ", жадный" : "")
				       << "  фраза «" << bid.phrase << "»\n";
			}
			std::string winners;
			for (const auto& who : done->winners) {
				winners += winners.empty() ? who : ", " + who;
			}
			report << "    выиграл   : " << (winners.empty() ? "никто" : winners) << "\n";
			for (const auto& [who, why] : done->denied) {
				report << "    отказано  : " << who << " - " << why << "\n";
			}
			report << "    итог      : " << done->outcome << "\n";
		}
		report << "\n";
	}

	Envoy::Scheduler::Get().Stop();

	const auto text = report.str();
	if (!reportFile.empty()) {
		std::ofstream out(reportFile, std::ios::binary);
		out << text;
		spdlog::info("отчёт: {}", reportFile.string());
	} else {
		std::fputs(text.c_str(), stdout);
	}
	return 0;
}
