add_executable(kvc_v2_better_hashmap
    main.c
    server.c
    protocol.c
    hashmap.c
    arena.c
)

target_compile_options(kvc_v2_better_hashmap PRIVATE -Wall -Wextra -Wpedantic)

set_target_properties(kvc_v2_better_hashmap PROPERTIES
    OUTPUT_NAME kvc
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/v2_better_hashmap
)
