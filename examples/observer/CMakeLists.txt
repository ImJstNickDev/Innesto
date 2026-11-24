cmake_minimum_required(VERSION 3.18)
project(innesto_observer LANGUAGES C)

find_path(INNESTO_INCLUDE_DIR innesto/mod.h REQUIRED)
add_library(innesto-observer MODULE observer.c)
target_include_directories(innesto-observer PRIVATE "${INNESTO_INCLUDE_DIR}")
target_compile_features(innesto-observer PRIVATE c_std_11)
set_target_properties(innesto-observer PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)

install(TARGETS innesto-observer LIBRARY DESTINATION observer)
install(FILES innesto.mod.json DESTINATION observer)
