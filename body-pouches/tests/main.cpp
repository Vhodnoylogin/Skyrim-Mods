#include "Harness.h"

int main()
{
	for (const auto& c : Harness::Cases()) {
		std::cout << "- " << c.name << "\n";
		c.run();
	}

	const int failures = Harness::Failures();
	std::cout << "\n"
			  << Harness::Cases().size() << " checks, "
			  << failures << " failed\n";
	return failures == 0 ? 0 : 1;
}
