add_executable(kvc_v1_2_conn_pool_cpp
    main.cpp
    server.cpp
    protocol.cpp
    hashmap.cpp
)

target_compile_options(kvc_v1_2_conn_pool_cpp PRIVATE -Wall -Wextra -Wpedantic)

set_target_properties(kvc_v1_2_conn_pool_cpp PROPERTIES
    OUTPUT_NAME kvc
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/v1.2_conn_pool_cpp
)
