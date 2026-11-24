cmake_minimum_required(VERSION 3.18)
project(innesto_environments LANGUAGES C)

find_path(INNESTO_INCLUDE_DIR innesto/runtime.h REQUIRED)
foreach(environment IN ITEMS shared client server)
    set(id "${environment}-hello")
    add_library(${id} MODULE hello.c)
    target_include_directories(${id} PRIVATE "${INNESTO_INCLUDE_DIR}")
    target_compile_features(${id} PRIVATE c_std_11)
    set_target_properties(${id} PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)
    install(TARGETS ${id} LIBRARY DESTINATION ${id})
    install(FILES "${id}.json" DESTINATION ${id} RENAME innesto.mod.json)
endforeach()

# The two environment-specific packages explicitly request their own module.
target_compile_definitions(client-hello PRIVATE EXAMPLE_SIDE_MODULE=INNESTO_CAP_CLIENT)
target_compile_definitions(server-hello PRIVATE EXAMPLE_SIDE_MODULE=INNESTO_CAP_SERVER)
