cmake_minimum_required(VERSION 3.18)
project(innesto_tidepool LANGUAGES C)

find_path(INNESTO_INCLUDE_DIR innesto/mod.h REQUIRED)
add_library(tidepool MODULE tidepool.c)
target_include_directories(tidepool PRIVATE "${INNESTO_INCLUDE_DIR}")
target_compile_features(tidepool PRIVATE c_std_11)
set_target_properties(tidepool PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)

install(TARGETS tidepool LIBRARY DESTINATION tidepool)
install(FILES innesto.mod.json DESTINATION tidepool)
install(FILES assets/lagoon.png DESTINATION tidepool/assets)
