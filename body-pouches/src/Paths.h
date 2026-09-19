#pragma once

#include <filesystem>

namespace BodyPouches::Paths
{
	// Where the mod keeps its own files. Everything is under one folder named after the
	// plugin, so that uninstalling it is one delete and so that nothing of ours lands
	// among somebody else's settings.
	//
	// These are the only paths written into the code, and they are fixed by where SKSE
	// looks rather than chosen by us.
	inline std::filesystem::path Root()
	{
		return std::filesystem::path("Data") / "SKSE" / "Plugins" / "bodypouches";
	}

	inline std::filesystem::path ConfigFile()
	{
		return Root() / "bodypouches.json";
	}

	inline std::filesystem::path LangDir()
	{
		return Root() / "lang";
	}
}
