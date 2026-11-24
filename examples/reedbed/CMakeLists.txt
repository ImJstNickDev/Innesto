cmake_minimum_required(VERSION 3.18)
project(innesto_reedbed LANGUAGES C)

find_path(INNESTO_INCLUDE_DIR innesto/mod.h REQUIRED)
add_library(reedbed MODULE reedbed.c)
target_include_directories(reedbed PRIVATE "${INNESTO_INCLUDE_DIR}")
target_compile_features(reedbed PRIVATE c_std_11)
set_target_properties(reedbed PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)

install(TARGETS reedbed LIBRARY DESTINATION reedbed)
install(FILES innesto.mod.json DESTINATION reedbed)
install(FILES assets/rush.png DESTINATION reedbed/assets)
