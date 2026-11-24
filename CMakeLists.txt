cmake_minimum_required(VERSION 3.18)
project(Innesto LANGUAGES C)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64|AMD64)$")
    message(FATAL_ERROR "This Innesto target requires Linux x86-64")
endif()

add_library(innesto-bootstrap MODULE src/bootstrap.c)
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
    add_library(innesto-test-prior MODULE tests/prior.c)
    add_library(innesto-test-reject MODULE tests/reject.c)
    target_include_directories(innesto-test-reject PRIVATE include)
    set_target_properties(innesto-test-prior innesto-test-reject PROPERTIES PREFIX "")
    add_test(NAME native-init COMMAND "${Python3_EXECUTABLE}"
        "${PROJECT_SOURCE_DIR}/tests/native_init.py" "$<TARGET_FILE_DIR:innesto-bootstrap>"
        "${CMAKE_C_COMPILER}")
    add_test(NAME launch-validation COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/tests/test_launch.py")
endif()
