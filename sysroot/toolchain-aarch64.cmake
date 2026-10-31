# CMake toolchain for native carts (docs/native.md): clang/lld and the sysroot that
# sysroot/fetch.sh builds.
#   cmake -B build -DCMAKE_TOOLCHAIN_FILE=<devkit>/sysroot/toolchain-aarch64.cmake [-DALIA_SYSROOT=DIR]
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

if(NOT ALIA_SYSROOT)
  if(DEFINED ENV{SYSROOT_OUT})
    set(ALIA_SYSROOT "$ENV{SYSROOT_OUT}/aarch64")
  else()
    set(ALIA_SYSROOT "${CMAKE_CURRENT_LIST_DIR}/out/aarch64")
  endif()
endif()
if(NOT EXISTS "${ALIA_SYSROOT}/usr/include")
  message(FATAL_ERROR "no sysroot at ${ALIA_SYSROOT}: run sysroot/fetch.sh first")
endif()
set(CMAKE_SYSROOT "${ALIA_SYSROOT}")

set(CMAKE_C_COMPILER clang)
set(CMAKE_CXX_COMPILER clang++)
set(CMAKE_C_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_CXX_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_EXE_LINKER_FLAGS_INIT "-fuse-ld=lld")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "-fuse-ld=lld")
set(CMAKE_MODULE_LINKER_FLAGS_INIT "-fuse-ld=lld")  # MODULE libraries: Python extensions

set(ENV{PKG_CONFIG_SYSROOT_DIR} "${ALIA_SYSROOT}")
set(ENV{PKG_CONFIG_LIBDIR} "${ALIA_SYSROOT}/usr/lib/aarch64-linux-gnu/pkgconfig:${ALIA_SYSROOT}/usr/share/pkgconfig")

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
