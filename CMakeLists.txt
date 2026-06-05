cmake_minimum_required(VERSION 3.16)
project(kvc C CXX)

# Default to Release if not specified
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# Match Makefile's -O2 default for Release
set(CMAKE_C_FLAGS_RELEASE   "-O2 -DNDEBUG")
set(CMAKE_CXX_FLAGS_RELEASE "-O2 -DNDEBUG")

# RelWithDebInfo = profile build: matches Makefile's profile-build target
set(CMAKE_C_FLAGS_RELWITHDEBINFO   "-O2 -g -fno-omit-frame-pointer")
set(CMAKE_CXX_FLAGS_RELWITHDEBINFO "-O2 -g -fno-omit-frame-pointer")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_subdirectory(src/v1_baseline)
add_subdirectory(src/v1.1_connection_pool)
add_subdirectory(src/v1.2_conn_pool_cpp)
add_subdirectory(src/v2_better_hashmap)
