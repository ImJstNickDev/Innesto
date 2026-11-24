find_program(INNESTO_READELF NAMES readelf llvm-readelf REQUIRED)

function(strip_fixture target)
    add_custom_command(TARGET ${target} POST_BUILD
        COMMAND "${CMAKE_STRIP}" --strip-all "$<TARGET_FILE:${target}>"
        VERBATIM)
endfunction()

foreach(revision IN ITEMS 1 2)
    set(host innesto-mapping-fixture-${revision})
    add_executable(${host} exercise.c fixture.c)
    target_compile_definitions(${host} PRIVATE FIXTURE_REVISION=${revision})
    target_link_libraries(${host} PRIVATE innesto-native-adapter)
    set_target_properties(${host} PROPERTIES C_VISIBILITY_PRESET hidden)
    strip_fixture(${host})
    add_custom_command(TARGET ${host} POST_BUILD
        COMMAND "${CMAKE_COMMAND}" "-Dimage=$<TARGET_FILE:${host}>" -P "${CMAKE_CURRENT_SOURCE_DIR}/RecordIdentity.cmake"
        VERBATIM)
endforeach()

add_test(NAME native-mappings COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_mappings.py"
    "$<TARGET_FILE:innesto-mapping-fixture-1>" "$<TARGET_FILE:innesto-mapping-fixture-2>" "${INNESTO_READELF}")

set(INNESTO_GUM_DEVKIT "" CACHE PATH "Optional unpacked Frida Gum 17.9.11 Linux x86-64 devkit for the fixture evaluation")
if(INNESTO_GUM_DEVKIT)
    file(SHA256 "${INNESTO_GUM_DEVKIT}/frida-gum.h" header_sha256)
    file(SHA256 "${INNESTO_GUM_DEVKIT}/libfrida-gum.a" library_sha256)
    if(NOT header_sha256 STREQUAL "b1ff3978cd65aef57383c489999e523a16e414f591f5ae32962f8c60ff6a4a3f" OR
       NOT library_sha256 STREQUAL "95731bc27b6d7b9f646ed7bb8efd3a3dedaffdf739f5ab03e38674157c2503e8")
        message(FATAL_ERROR "Gum probe requires the pinned upstream devkit documented in native-mappings.md")
    endif()
    find_package(Threads REQUIRED)
    add_executable(innesto-gum-probe gum_probe.c)
    target_compile_features(innesto-gum-probe PRIVATE c_std_11)
    target_compile_options(innesto-gum-probe PRIVATE -O0 -fno-lto)
    target_include_directories(innesto-gum-probe SYSTEM PRIVATE "${INNESTO_GUM_DEVKIT}")
    target_link_libraries(innesto-gum-probe PRIVATE "${INNESTO_GUM_DEVKIT}/libfrida-gum.a"
        rt resolv ${CMAKE_DL_LIBS} m Threads::Threads)
    strip_fixture(innesto-gum-probe)
    add_test(NAME native-gum-probe COMMAND innesto-gum-probe)
endif()
