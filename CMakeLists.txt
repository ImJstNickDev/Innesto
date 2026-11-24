cmake_minimum_required(VERSION 3.18)
project(Innesto LANGUAGES C)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64|AMD64)$")
    message(FATAL_ERROR "This Innesto target requires Linux x86-64")
endif()

# Private adapter/host contract. Public mod SDKs do not link this library.
add_library(innesto-native-adapter STATIC src/native_adapter.c)
target_include_directories(innesto-native-adapter PUBLIC src)
target_compile_features(innesto-native-adapter PUBLIC c_std_11)
set_target_properties(innesto-native-adapter PROPERTIES POSITION_INDEPENDENT_CODE ON C_VISIBILITY_PRESET hidden)

add_library(innesto-bootstrap MODULE src/bootstrap.c src/runtime.c src/block_break.c src/adapters/a1_2_10/simulation.c)
target_include_directories(innesto-bootstrap PRIVATE include)
set_target_properties(innesto-bootstrap PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)
target_compile_features(innesto-bootstrap PRIVATE c_std_11)
target_link_libraries(innesto-bootstrap PRIVATE innesto-native-adapter ${CMAKE_DL_LIBS})

option(INNESTO_SAVED_BLOCKS "Build the read-only saved block totals adapter" OFF)
if(INNESTO_SAVED_BLOCKS)
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(JANSSON REQUIRED IMPORTED_TARGET jansson>=2.11)
    target_sources(innesto-bootstrap PRIVATE src/adapters/a1_2_10/saved_blocks.c)
    target_link_libraries(innesto-bootstrap PRIVATE PkgConfig::JANSSON)
    target_compile_definitions(innesto-bootstrap PRIVATE INNESTO_SAVED_BLOCKS=1)
endif()

# Keep the checked identity with the built bootstrap, including multi-config builds.
add_custom_target(innesto-loader ALL
    COMMAND "${CMAKE_COMMAND}" "-Dlibrary=$<TARGET_FILE:innesto-bootstrap>"
        -P "${PROJECT_SOURCE_DIR}/cmake/BootstrapIdentity.cmake"
    DEPENDS innesto-bootstrap
    VERBATIM)

include(CTest)
if(BUILD_TESTING)
    find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
    add_subdirectory(tests/mappings)
    add_executable(innesto-test-host tests/host.c)
    if(INNESTO_SAVED_BLOCKS)
        add_test(NAME saved-blocks COMMAND "${Python3_EXECUTABLE}"
            "${PROJECT_SOURCE_DIR}/tests/saved_blocks.py" "$<TARGET_FILE_DIR:innesto-bootstrap>"
            "${CMAKE_C_COMPILER}")
    endif()
    # Plain, dedicated and integrated links share the same simulation objects.
    add_library(innesto-test-simulation OBJECT tests/block_break_host.c tests/block_break_rules.c)
    # Keep the rule call visible to the native linker even in an LTO build.
    target_compile_options(innesto-test-simulation PRIVATE -fno-lto)
    add_executable(innesto-test-block-break-vanilla $<TARGET_OBJECTS:innesto-test-simulation>)
    function(add_simulation_fixture target environment)
        add_executable(${target} $<TARGET_OBJECTS:innesto-test-simulation> tests/block_break_wrap.c)
        target_link_libraries(${target} PRIVATE innesto-native-adapter)
        target_compile_definitions(${target} PRIVATE FIXTURE_ENVIRONMENT="${environment}"
            FIXTURE_STAMP="$<TARGET_FILE_DIR:${target}>/${target}.sha256")
        target_link_options(${target} PRIVATE "LINKER:--wrap=fixture_break_permitted" "LINKER:--strip-all")
        add_custom_command(TARGET ${target} POST_BUILD COMMAND "${CMAKE_COMMAND}"
            "-Dimage=$<TARGET_FILE:${target}>" -P "${PROJECT_SOURCE_DIR}/tests/mappings/RecordIdentity.cmake"
            VERBATIM)
    endfunction()
    add_simulation_fixture(innesto-test-block-break-host server)
    add_simulation_fixture(innesto-test-block-break-integrated client)
    add_executable(innesto-test-break-dispatch tests/block_break_dispatch.c src/block_break.c src/runtime.c)
    target_include_directories(innesto-test-break-dispatch PRIVATE include src)
    target_compile_features(innesto-test-break-dispatch PRIVATE c_std_11)
    add_test(NAME block-break-dispatch COMMAND innesto-test-break-dispatch)
    add_test(NAME block-break-unattached COMMAND innesto-test-break-dispatch unattached)
    add_test(NAME block-break-packages COMMAND "${Python3_EXECUTABLE}"
        "${PROJECT_SOURCE_DIR}/tests/block_break.py" "$<TARGET_FILE_DIR:innesto-bootstrap>"
        "${CMAKE_C_COMPILER}")
    add_library(innesto-test-prior MODULE tests/prior.c)
    add_library(innesto-test-reject MODULE tests/reject.c)
    target_include_directories(innesto-test-reject PRIVATE include)
    set_target_properties(innesto-test-prior innesto-test-reject PROPERTIES PREFIX "")
    add_test(NAME native-init COMMAND "${Python3_EXECUTABLE}"
        "${PROJECT_SOURCE_DIR}/tests/native_init.py" "$<TARGET_FILE_DIR:innesto-bootstrap>"
        "${CMAKE_C_COMPILER}")
    find_package(Threads REQUIRED)
    add_executable(innesto-test-runtime tests/runtime_contract.c src/runtime.c)
    target_include_directories(innesto-test-runtime PRIVATE include src)
    target_compile_features(innesto-test-runtime PRIVATE c_std_11)
    target_link_libraries(innesto-test-runtime PRIVATE Threads::Threads)
    add_test(NAME runtime-contract COMMAND innesto-test-runtime)
    add_test(NAME environments COMMAND "${Python3_EXECUTABLE}"
        "${PROJECT_SOURCE_DIR}/tests/environments.py" "$<TARGET_FILE_DIR:innesto-bootstrap>"
        "${CMAKE_C_COMPILER}")
    add_test(NAME mod-packages COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/tests/test_packages.py")
    add_test(NAME launch-validation COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/tests/test_launch.py")
endif()
