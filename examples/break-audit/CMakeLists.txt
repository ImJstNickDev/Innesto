cmake_minimum_required(VERSION 3.18)
project(innesto_break_audit LANGUAGES C)

find_path(INNESTO_INCLUDE_DIR innesto/block_break.h REQUIRED)
add_library(innesto-break-audit MODULE audit.c)
target_include_directories(innesto-break-audit PRIVATE "${INNESTO_INCLUDE_DIR}")
target_compile_features(innesto-break-audit PRIVATE c_std_11)
set_target_properties(innesto-break-audit PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)

install(TARGETS innesto-break-audit LIBRARY DESTINATION break-audit)
install(FILES innesto.mod.json DESTINATION break-audit)
