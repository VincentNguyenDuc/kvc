add_executable(kvc_v31_multicore_shared_map
    main.cpp
    server.cpp
    hashmap.cpp
    protocol.cpp
)

target_compile_options(kvc_v31_multicore_shared_map PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(kvc_v31_multicore_shared_map PRIVATE pthread)

set_target_properties(kvc_v31_multicore_shared_map PROPERTIES
    OUTPUT_NAME kvc
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/v3.1_multicore_shared_map
)
