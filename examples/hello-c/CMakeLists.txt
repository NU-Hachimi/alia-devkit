# The smallest native cart (docs/native.md). Cross-compile and put the program into the cart:
#   cmake -B build -DCMAKE_TOOLCHAIN_FILE=../../sysroot/toolchain-aarch64.cmake
#   cmake --build build && cmake --install build      -> cart/content/hello
#   acart check cart && acart pack cart
cmake_minimum_required(VERSION 3.20)
project(hello-c C)

find_package(SDL3 REQUIRED CONFIG)

add_executable(hello main.c)
set_target_properties(hello PROPERTIES C_STANDARD 99)
target_include_directories(hello PRIVATE ${CMAKE_CURRENT_LIST_DIR}/../../include)  # alia/save.h
target_link_libraries(hello PRIVATE SDL3::SDL3)
# libraries the cart brings itself go into content/lib (none here: SDL3 is in the baseline)
set_target_properties(hello PROPERTIES INSTALL_RPATH "$ORIGIN/lib")

set(CMAKE_INSTALL_PREFIX ${CMAKE_CURRENT_LIST_DIR}/cart CACHE PATH "" FORCE)
install(TARGETS hello RUNTIME DESTINATION content)
