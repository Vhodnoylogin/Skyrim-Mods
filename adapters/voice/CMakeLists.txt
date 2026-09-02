# Адаптер голоса - обычный плагин SKSE, то есть мод. С мостом говорит вызовом
# функции внутри процесса игры; наружу, к моделям, ходит сам по HTTP.
project(EnvoyVoiceAdapter VERSION 0.1.0 LANGUAGES CXX)

file(GLOB_RECURSE ADAPTER_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp")

add_library(EnvoyVoiceAdapter SHARED ${ADAPTER_SOURCES})

if(MSVC)
    target_compile_options(EnvoyVoiceAdapter PRIVATE
        /MP /W4 /WX /permissive- /Zc:preprocessor /EHsc /utf-8
        /wd4068 /wd4189 /wd4200 /wd4201 /wd4324
    )
endif()

set_target_properties(EnvoyVoiceAdapter PROPERTIES OUTPUT_NAME "EnvoyVoiceAdapter" SUFFIX ".dll")

target_compile_definitions(EnvoyVoiceAdapter PRIVATE
    PLUGIN_NAME="EnvoyVoiceAdapter"
    PLUGIN_AUTHOR="Claude"
    PLUGIN_VERSION="${PROJECT_VERSION}"
)

target_include_directories(EnvoyVoiceAdapter PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${CMAKE_SOURCE_DIR}/contract"
    "${RAPIDCSV_INCLUDE_DIRS}"
)

target_link_libraries(EnvoyVoiceAdapter PRIVATE
    CommonLibSSE::CommonLibSSE
    nlohmann_json::nlohmann_json
    httplib::httplib
)
