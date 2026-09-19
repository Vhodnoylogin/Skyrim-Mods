#pragma once

#include "LocStrings.h"

#include <spdlog/spdlog.h>

#include <exception>
#include <filesystem>
#include <string>
#include <utility>

namespace BodyPouches
{
	// The text of the mod, which for now is its log: it has no window and no notices of
	// its own yet.
	//
	// A line is a key; the text behind it is read from
	// SKSE\Plugins\bodypouches\lang\<language>.txt, a plain UTF-8 file of `key = text`
	// lines. The English table is built into the binary and written out as that file on
	// first run, so a translator has something to copy and nobody has to invent the
	// format.
	//
	// A pattern that comes out of a file anybody may edit will sooner or later have the
	// wrong number of placeholders in it. That must not silence the line: a broken
	// pattern falls back to the bare key, because a mod that cannot be diagnosed is
	// worse than one whose log reads badly.
	class Loc
	{
	public:
		static void Load();
		static void Load(const std::filesystem::path& a_dir, const std::string& a_language);

		[[nodiscard]] static const char*        Get(const char* a_key);
		[[nodiscard]] static const std::string& Language();

		template <class... Args>
		static void Say(spdlog::level::level_enum a_level, const char* a_key, Args&&... a_args)
		{
			try {
				spdlog::log(a_level, fmt::runtime(Get(a_key)), std::forward<Args>(a_args)...);
			} catch (const std::exception&) {
				spdlog::log(a_level, "{}", a_key);
			}
		}

		template <class... Args>
		static void Debug(const char* a_key, Args&&... a_args)
		{
			Say(spdlog::level::debug, a_key, std::forward<Args>(a_args)...);
		}

		template <class... Args>
		static void Info(const char* a_key, Args&&... a_args)
		{
			Say(spdlog::level::info, a_key, std::forward<Args>(a_args)...);
		}

		template <class... Args>
		static void Warn(const char* a_key, Args&&... a_args)
		{
			Say(spdlog::level::warn, a_key, std::forward<Args>(a_args)...);
		}

		template <class... Args>
		static void Error(const char* a_key, Args&&... a_args)
		{
			Say(spdlog::level::err, a_key, std::forward<Args>(a_args)...);
		}
	};
}
