cmake_minimum_required(VERSION 3.20)
project(foundry_intel VERSION 1.0.0 LANGUAGES CXX ASM_NASM)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# NASM flags — Windows x64 ELF-compatible object format
if(WIN32)
    set(CMAKE_ASM_NASM_OBJECT_FORMAT win64)
    set(CMAKE_ASM_NASM_FLAGS "-f win64")
else()
    set(CMAKE_ASM_NASM_OBJECT_FORMAT elf64)
    set(CMAKE_ASM_NASM_FLAGS "-f elf64")
endif()

# NASM assembly objects
set(ASM_SOURCES asm/sha256_nasm.asm)
set_source_files_properties(${ASM_SOURCES} PROPERTIES LANGUAGE ASM_NASM)

# Main library — C++ + NASM
add_library(foundry_core STATIC
    src/goldilocks.cpp
    src/pmat.cpp
    src/spectral.cpp
    src/recurrence.cpp
    src/gate.cpp
    src/certify.cpp
    src/audit.cpp
    src/linker.cpp
    src/sha256.cpp
    ${ASM_SOURCES}
)
target_include_directories(foundry_core PUBLIC include)
target_compile_definitions(foundry_core PUBLIC PMC_SHA256_NASM=1)

# Main executable
add_executable(foundry src/main.cpp)
target_link_libraries(foundry PRIVATE foundry_core)

# Test executable
add_executable(foundry_test src/test.cpp)
target_link_libraries(foundry_test PRIVATE foundry_core)
