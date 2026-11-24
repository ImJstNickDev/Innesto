cmake_minimum_required(VERSION 3.18)
project(innesto_break_guard LANGUAGES C)

find_path(INNESTO_INCLUDE_DIR innesto/block_break.h REQUIRED)
add_library(innesto-break-guard MODULE guard.c)
target_include_directories(innesto-break-guard PRIVATE "${INNESTO_INCLUDE_DIR}")
target_compile_features(innesto-break-guard PRIVATE c_std_11)
set_target_properties(innesto-break-guard PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)

install(TARGETS innesto-break-guard LIBRARY DESTINATION break-guard)
install(FILES innesto.mod.json DESTINATION break-guard)
