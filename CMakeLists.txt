cmake_minimum_required(VERSION 3.24)

project(Envoy VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Мы никогда не ставим проект через install, а правила установки CommonLibSSE-NG
# рассчитаны на vcpkg и ломаются, когда fmt и spdlog приходят из FetchContent.
set(CMAKE_SKIP_INSTALL_RULES ON)

# ---------------------------------------------------------------- зависимости
# CommonLibSSE-NG ищет fmt и spdlog через find_package, поэтому мы подсовываем
# их FetchContent'ом с OVERRIDE_FIND_PACKAGE. vcpkg при этом не нужен.
include(FetchContent)

set(FMT_INSTALL OFF CACHE BOOL "" FORCE)
FetchContent_Declare(
    fmt
    GIT_REPOSITORY https://github.com/fmtlib/fmt.git
    GIT_TAG 11.0.2
    GIT_SHALLOW TRUE
    OVERRIDE_FIND_PACKAGE
)

set(SPDLOG_FMT_EXTERNAL ON CACHE BOOL "" FORCE)
set(SPDLOG_INSTALL OFF CACHE BOOL "" FORCE)
FetchContent_Declare(
    spdlog
    GIT_REPOSITORY https://github.com/gabime/spdlog.git
    GIT_TAG v1.15.0
    GIT_SHALLOW TRUE
    OVERRIDE_FIND_PACKAGE
)

FetchContent_Declare(
    nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.11.3
    GIT_SHALLOW TRUE
)

# rapidcsv нужен самой CommonLibSSE-NG: из CSV она читает адресную библиотеку,
# и именно этим путём поддерживается VR. Забираем только заголовок: у src/
# нет своего CMakeLists, поэтому проект rapidcsv не настраивается.
FetchContent_Declare(
    rapidcsv
    GIT_REPOSITORY https://github.com/d99kris/rapidcsv.git
    GIT_TAG v8.99
    GIT_SHALLOW TRUE
    SOURCE_SUBDIR src
)

FetchContent_MakeAvailable(fmt spdlog nlohmann_json rapidcsv)

set(RAPIDCSV_INCLUDE_DIRS "${rapidcsv_SOURCE_DIR}/src" CACHE PATH "" FORCE)

# Тесты самой библиотеки нам не нужны - иначе она потянет ещё и Catch2.
set(BUILD_TESTS OFF CACHE BOOL "" FORCE)

message(STATUS "Fetching CommonLibSSE-NG (первый раз это долго)...")
FetchContent_Declare(
    CommonLibSSE
    GIT_REPOSITORY https://github.com/CharmedBaryon/CommonLibSSE-NG.git
    GIT_TAG v3.7.0
    GIT_SHALLOW TRUE
)
FetchContent_MakeAvailable(CommonLibSSE)

FetchContent_Declare(
    httplib
    GIT_REPOSITORY https://github.com/yhirose/cpp-httplib.git
    GIT_TAG v0.18.3
    GIT_SHALLOW TRUE
)
FetchContent_MakeAvailable(httplib)

# ------------------------------------------------------------ эталон настроек
# Единственный источник истины - config/envoy.default.json. В двоичный файл он
# попадает целиком на этапе сборки: второй копии значений в коде нет, а плагин
# при первом запуске разворачивает этот набор в файл рядом с собой.
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/config/envoy.default.json" ENVOY_DEFAULT_JSON)
configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/EnvoyDefaults.h.in"
    "${CMAKE_CURRENT_BINARY_DIR}/generated/EnvoyDefaults.h"
    @ONLY
)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/config/envoy.default.json")

# ---------------------------------------------------------------- наш плагин
file(GLOB_RECURSE ENVOY_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp")
file(GLOB_RECURSE ENVOY_HEADERS CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/*.h")

add_library(${PROJECT_NAME} SHARED ${ENVOY_SOURCES} ${ENVOY_HEADERS})

# Строгие флаги - только на наш код. Чужие библиотеки собираются своими:
# ставить им /WX означало бы падать на чужих предупреждениях.
if(MSVC)
    target_compile_options(${PROJECT_NAME} PRIVATE
        /MP /W4 /WX /permissive- /Zc:preprocessor /EHsc /utf-8
        /wd4068 /wd4189 /wd4200 /wd4201 /wd4324
    )
endif()

set_target_properties(${PROJECT_NAME} PROPERTIES
    OUTPUT_NAME "${PROJECT_NAME}"
    SUFFIX ".dll"
    INTERPROCEDURAL_OPTIMIZATION_RELEASE ON
)

target_compile_definitions(${PROJECT_NAME} PRIVATE
    PLUGIN_NAME="${PROJECT_NAME}"
    PLUGIN_AUTHOR="Claude"
    PLUGIN_VERSION="${PROJECT_VERSION}"
)

target_include_directories(${PROJECT_NAME} PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${CMAKE_CURRENT_SOURCE_DIR}/contract"
    "${CMAKE_CURRENT_BINARY_DIR}/generated"
    # REL/Relocation.h из CommonLibSSE-NG включает rapidcsv.h, но путь к нему
    # библиотека наружу не отдаёт - приходится добавлять самим.
    "${RAPIDCSV_INCLUDE_DIRS}"
)

target_link_libraries(${PROJECT_NAME} PRIVATE
    CommonLibSSE::CommonLibSSE
    nlohmann_json::nlohmann_json
    httplib::httplib
)

# Раскладка в mods\ делается tools/deploy.ps1, а не постсборочным шагом:
# писать в сборку при запущенной игре нельзя.

add_subdirectory(providers)
# Адаптер здесь не собирается: это отдельный модуль со своим файлом сборки
# в adapters/voice. Мост о нём не знает вовсе - он отдаёт контракт папкой SDK,
# и этого достаточно. Ветка у Envoy пока одна: модули разъедутся по веткам
# позже, когда будут закончены основные настройки.
