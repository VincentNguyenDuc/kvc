add_executable(kvc_v1_1_connection_pool
    main.c
    server.c
    protocol.c
    hashmap.c
)

target_compile_options(kvc_v1_1_connection_pool PRIVATE -Wall -Wextra -Wpedantic)

set_target_properties(kvc_v1_1_connection_pool PROPERTIES
    OUTPUT_NAME kvc
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/v1.1_connection_pool
)
