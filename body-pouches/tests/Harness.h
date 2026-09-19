#pragma once

// A test harness of thirty lines, and on purpose.
//
// The core has no dependencies at all, and the checks are the place where that is
// worth the most: no framework to fetch, nothing to install, so `cmake --build`
// and run is the whole of it on any machine. If these ever grow past a few hundred
// lines, that is the moment to reach for a real framework - not before.

#include <iostream>
#include <string>
#include <vector>

namespace Harness
{
	struct Case
	{
		const char* name;
		void (*run)();
	};

	inline std::vector<Case>& Cases()
	{
		static std::vector<Case> cases;
		return cases;
	}

	inline int& Failures()
	{
		static int failures = 0;
		return failures;
	}

	inline void Fail(const char* a_file, int a_line, const std::string& a_what)
	{
		++Failures();
		std::cout << "  FAILED " << a_file << ":" << a_line << "  " << a_what << "\n";
	}

	struct Register
	{
		Register(const char* a_name, void (*a_run)()) { Cases().push_back({ a_name, a_run }); }
	};
}

#define TEST(name)                                                       \
	static void name();                                                  \
	static ::Harness::Register name##_registered(#name, name);           \
	static void name()

#define CHECK(expr)                                                      \
	do {                                                                 \
		if (!(expr)) {                                                   \
			::Harness::Fail(__FILE__, __LINE__, #expr);                  \
		}                                                                \
	} while (false)

#define CHECK_EQ(lhs, rhs)                                               \
	do {                                                                 \
		const auto _l = (lhs);                                           \
		const auto _r = (rhs);                                           \
		if (!(_l == _r)) {                                               \
			::Harness::Fail(__FILE__, __LINE__,                          \
				std::string(#lhs) + " != " + #rhs);                      \
		}                                                                \
	} while (false)
