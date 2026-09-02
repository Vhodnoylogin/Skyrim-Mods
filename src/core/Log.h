#pragma once

#include <SKSE/SKSE.h>
#include <string_view>

namespace Envoy
{
	// Журнал плагина. Уровень берётся из конфигурации, в коде его нет.
	class Log
	{
	public:
		static void Init(std::string_view a_level);
	};
}
