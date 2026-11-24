cmake_minimum_required(VERSION 3.18)
project(Innesto LANGUAGES C)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64|AMD64)$")
    message(FATAL_ERROR "This Innesto target requires Linux x86-64")
endif()

add_library(innesto-bootstrap MODULE src/bootstrap.c src/block_break.c)
target_include_directories(innesto-bootstrap PRIVATE include)
set_target_properties(innesto-bootstrap PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)
target_compile_features(innesto-bootstrap PRIVATE c_std_11)
target_link_libraries(innesto-bootstrap PRIVATE ${CMAKE_DL_LIBS})

# Keep the checked identity with the built bootstrap, including multi-config builds.
add_custom_target(innesto-loader ALL
    COMMAND "${CMAKE_COMMAND}" "-Dlibrary=$<TARGET_FILE:innesto-bootstrap>"
        -P "${PROJECT_SOURCE_DIR}/cmake/BootstrapIdentity.cmake"
    DEPENDS innesto-bootstrap
    VERBATIM)

include(CTest)
if(BUILD_TESTING)
    find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
    add_executable(innesto-test-host tests/host.c)
    # Both executables use exactly the same simulation objects. The adapted
    # executable adds a decision-site wrapper and an Innesto adapter at link time.
    add_library(innesto-test-simulation OBJECT tests/block_break_host.c tests/block_break_rules.c)
    # Keep the rule call visible to the native linker even in an LTO build.
    target_compile_options(innesto-test-simulation PRIVATE -fno-lto)
    add_executable(innesto-test-block-break-vanilla $<TARGET_OBJECTS:innesto-test-simulation>)
    add_library(innesto-test-break-adapter SHARED tests/block_break_adapter.c)
    target_include_directories(innesto-test-break-adapter PRIVATE include src)
    add_executable(innesto-test-block-break-host
        $<TARGET_OBJECTS:innesto-test-simulation> tests/block_break_wrap.c)
    target_link_options(innesto-test-block-break-host PRIVATE "LINKER:--wrap=fixture_break_permitted")
    target_link_libraries(innesto-test-block-break-host PRIVATE innesto-test-break-adapter)
    add_executable(innesto-test-break-dispatch tests/block_break_dispatch.c src/block_break.c)
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
    add_test(NAME mod-packages COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/tests/test_packages.py")
    add_test(NAME launch-validation COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/tests/test_launch.py")
endif()
