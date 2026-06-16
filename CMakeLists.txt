cmake_minimum_required(VERSION 3.16)
project(kvc C CXX)

set(CMAKE_C_FLAGS_RELEASE   "-O2 -DNDEBUG")
set(CMAKE_CXX_FLAGS_RELEASE "-O2 -DNDEBUG")

set(CMAKE_C_FLAGS_DEBUG   "-O0 -g")
set(CMAKE_CXX_FLAGS_DEBUG "-O0 -g")

# RelWithDebInfo = profile build: optimized with frame pointers for flamegraphs
set(CMAKE_C_FLAGS_RELWITHDEBINFO   "-O2 -g -fno-omit-frame-pointer")
set(CMAKE_CXX_FLAGS_RELWITHDEBINFO "-O2 -g -fno-omit-frame-pointer")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_subdirectory(src/v1_baseline)
add_subdirectory(src/v1.1_connection_pool)
add_subdirectory(src/v1.2_conn_pool_cpp)
add_subdirectory(src/v2_better_hashmap)
add_subdirectory(src/v3.1_multicore_shared_map)
