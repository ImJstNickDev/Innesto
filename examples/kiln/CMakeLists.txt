cmake_minimum_required(VERSION 3.18)
project(innesto_kiln LANGUAGES C)

find_path(INNESTO_INCLUDE_DIR innesto/mod.h REQUIRED)
add_library(kiln MODULE kiln.c)
target_include_directories(kiln PRIVATE "${INNESTO_INCLUDE_DIR}")
target_compile_features(kiln PRIVATE c_std_11)
set_target_properties(kiln PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)

install(TARGETS kiln LIBRARY DESTINATION kiln)
install(FILES innesto.mod.json DESTINATION kiln)
install(FILES assets/ochre.png DESTINATION kiln/assets)
