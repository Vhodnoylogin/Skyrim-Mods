# The checks of the core.
#
# They link against BodyPouchesCore and nothing else - no CommonLib, no SKSE, no
# game - which is the point: the rule of the pouches can be run on any machine in
# a second, and a mistake in it is found before a headset is ever put on.
project(BodyPouchesTests LANGUAGES CXX)

add_executable(bodypouches_tests
    "${CMAKE_CURRENT_SOURCE_DIR}/Harness.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_pouch.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_pouchset.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/main.cpp"
)

target_include_directories(bodypouches_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(bodypouches_tests PRIVATE BodyPouchesCore)

if(MSVC)
    target_compile_options(bodypouches_tests PRIVATE /W4 /WX /permissive- /EHsc /utf-8)
endif()

enable_testing()
add_test(NAME core COMMAND bodypouches_tests)
