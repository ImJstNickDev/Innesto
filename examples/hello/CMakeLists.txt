cmake_minimum_required(VERSION 3.18)
project(innesto_hello LANGUAGES C)

find_path(INNESTO_INCLUDE_DIR innesto/mod.h REQUIRED)
add_library(innesto-hello MODULE hello.c)
target_include_directories(innesto-hello PRIVATE "${INNESTO_INCLUDE_DIR}")
target_compile_features(innesto-hello PRIVATE c_std_11)
set_target_properties(innesto-hello PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)
