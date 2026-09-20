cmake_minimum_required(VERSION 3.24)

# body-pouches: pouches worn on the body. An ordinary SKSE plugin, which is to say
# a mod, built in two pieces on purpose.
#
#   BodyPouchesCore - the rule of the pouches. What lies in a slot, whether it may
#   be taken, what happens to the slot once it is taken. It knows nothing of VRIK,
#   of HIGGS, of SKSE or of the game, links against nothing at all, and is built
#   and tested on a machine with no Skyrim on it.
#
#   BodyPouches - the mod. The SKSE entry points and the two adapters that carry
#   the decisions of the core to VRIK and HIGGS.
#
# The split is not decoration: the whole of the reasoning sits in the half that can
# be run in a second, and the half that needs a headset holds no reasoning at all.
project(BodyPouches VERSION 0.1.6 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_SKIP_INSTALL_RULES ON)

option(BODYPOUCHES_BUILD_PLUGIN "Build the SKSE plugin (needs CommonLibSSE-NG)" ON)
option(BODYPOUCHES_BUILD_TESTS  "Build the checks of the core" ON)

# ------------------------------------------------------------------------ core
# No dependencies by design. A new file under src/core is picked up by the next
# build without anybody having to remember this line.
file(GLOB_RECURSE BODYPOUCHES_CORE_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/core/*.cpp")
file(GLOB_RECURSE BODYPOUCHES_CORE_HEADERS CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/core/*.h")
add_library(BodyPouchesCore STATIC ${BODYPOUCHES_CORE_SOURCES} ${BODYPOUCHES_CORE_HEADERS})
target_include_directories(BodyPouchesCore PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/src")
source_group(TREE "${CMAKE_CURRENT_SOURCE_DIR}/src" FILES ${BODYPOUCHES_CORE_SOURCES} ${BODYPOUCHES_CORE_HEADERS})

if(MSVC)
    target_compile_options(BodyPouchesCore PRIVATE
        /MP /W4 /WX /permissive- /Zc:preprocessor /EHsc /utf-8
    )
endif()

# The checks come before the plugin on purpose: they need the core and nothing
# else, so -DBODYPOUCHES_BUILD_PLUGIN=OFF gives a configure that fetches nothing
# from the network and builds in seconds on a machine with no Skyrim on it.
if(BODYPOUCHES_BUILD_TESTS AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/tests/CMakeLists.txt")
    add_subdirectory(tests)
endif()

if(NOT BODYPOUCHES_BUILD_PLUGIN)
    return()
endif()

# ---------------------------------------------------------------- dependencies
# CommonLibSSE-NG looks for fmt and spdlog through find_package, so they are slipped
# in with FetchContent and OVERRIDE_FIND_PACKAGE. vcpkg is not needed for this.
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

# rapidcsv is wanted by CommonLibSSE-NG itself: it reads the address library out of
# a CSV, and that is exactly the path by which VR is supported.
FetchContent_Declare(
    rapidcsv
    GIT_REPOSITORY https://github.com/d99kris/rapidcsv.git
    GIT_TAG v8.99
    GIT_SHALLOW TRUE
    SOURCE_SUBDIR src
)

FetchContent_MakeAvailable(fmt spdlog nlohmann_json rapidcsv)
set(RAPIDCSV_INCLUDE_DIRS "${rapidcsv_SOURCE_DIR}/src" CACHE PATH "" FORCE)

set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
message(STATUS "Fetching CommonLibSSE-NG (the first time this takes a while)...")
FetchContent_Declare(
    CommonLibSSE
    GIT_REPOSITORY https://github.com/CharmedBaryon/CommonLibSSE-NG.git
    GIT_TAG v3.7.0
    GIT_SHALLOW TRUE
)
FetchContent_MakeAvailable(CommonLibSSE)

# ------------------------------------------------------------------- the mod
# contract/ holds the headers of VRIK and HIGGS exactly as their authors published
# them, and src/compat supplies the SKSE64 names those headers were written against -
# see src/compat/skse64/PluginAPI.h. The authors' own handshake .cpp files are NOT
# compiled in: they call the old messaging interface, and ours goes through
# CommonLibSSE instead (src/vr/Handshake.h).
file(GLOB_RECURSE BODYPOUCHES_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp")
file(GLOB_RECURSE BODYPOUCHES_HEADERS CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/*.h")
list(REMOVE_ITEM BODYPOUCHES_SOURCES ${BODYPOUCHES_CORE_SOURCES})
list(REMOVE_ITEM BODYPOUCHES_HEADERS ${BODYPOUCHES_CORE_HEADERS})

add_library(BodyPouches SHARED
    ${BODYPOUCHES_SOURCES}
    ${BODYPOUCHES_HEADERS}
)

source_group(TREE "${CMAKE_CURRENT_SOURCE_DIR}" FILES ${BODYPOUCHES_SOURCES} ${BODYPOUCHES_HEADERS})

if(MSVC)
    target_compile_options(BodyPouches PRIVATE
        /MP /W4 /WX /permissive- /Zc:preprocessor /EHsc /utf-8
        /wd4068 /wd4189 /wd4200 /wd4201 /wd4324
    )
endif()

set_target_properties(BodyPouches PROPERTIES OUTPUT_NAME "BodyPouches" SUFFIX ".dll")

target_compile_definitions(BodyPouches PRIVATE
    PLUGIN_NAME="BodyPouches"
    PLUGIN_AUTHOR="Vhodnoylogin"
    PLUGIN_VERSION="${PROJECT_VERSION}"
)

target_include_directories(BodyPouches PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/compat"
    "${CMAKE_CURRENT_SOURCE_DIR}/contract"
    "${RAPIDCSV_INCLUDE_DIRS}"
)

target_link_libraries(BodyPouches PRIVATE
    BodyPouchesCore
    CommonLibSSE::CommonLibSSE
    nlohmann_json::nlohmann_json
)
