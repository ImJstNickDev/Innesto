cmake_minimum_required(VERSION 3.18)
project(innesto_copperfield LANGUAGES C)

find_path(INNESTO_INCLUDE_DIR innesto/mod.h REQUIRED)
add_library(copperfield MODULE copperfield.c)
target_include_directories(copperfield PRIVATE "${INNESTO_INCLUDE_DIR}")
target_compile_features(copperfield PRIVATE c_std_11)
set_target_properties(copperfield PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)

install(TARGETS copperfield LIBRARY DESTINATION copperfield)
install(FILES innesto.mod.json DESTINATION copperfield)
install(FILES assets/ochre.png DESTINATION copperfield/assets)
