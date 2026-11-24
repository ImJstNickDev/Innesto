cmake_minimum_required(VERSION 3.18)
project(innesto_aster LANGUAGES C)

find_path(INNESTO_INCLUDE_DIR innesto/mod.h REQUIRED)
add_library(aster MODULE aster.c)
target_include_directories(aster PRIVATE "${INNESTO_INCLUDE_DIR}")
target_compile_features(aster PRIVATE c_std_11)
set_target_properties(aster PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)

install(TARGETS aster LIBRARY DESTINATION aster)
install(FILES innesto.mod.json DESTINATION aster)
install(FILES assets/chalk.png DESTINATION aster/assets)
