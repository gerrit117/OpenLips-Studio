cmake_minimum_required(VERSION 3.20)
project(openlips_stfs LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(VELOCITY_ROOT "" CACHE PATH "External Velocity checkout (GPLv3)")
set(BOTAN_ROOT "" CACHE PATH "External configured/built Botan checkout")
if(NOT MSVC)
  message(FATAL_ERROR "This adapter currently requires MSVC (Velocity DWORD is Windows-sized)")
endif()
set(XI "${VELOCITY_ROOT}/XboxInternals")
find_library(BOTAN_LIB NAMES botan-3 PATHS "${BOTAN_ROOT}" NO_DEFAULT_PATH REQUIRED)
add_executable(openlips_stfs main.cpp
  "${XI}/Stfs/StfsPackage.cpp" "${XI}/Stfs/XContentHeader.cpp"
  "${XI}/Stfs/StfsDefinitions.cpp" "${XI}/IO/BaseIO.cpp"
  "${XI}/IO/FileIO.cpp" "${XI}/IO/MemoryIO.cpp"
  "${XI}/Cryptography/XeCrypt.cpp" "${XI}/Gpd/XdbfHelpers.cpp"
  "${XI}/AvatarAsset/AssetHelpers.cpp")
target_include_directories(openlips_stfs PRIVATE "${XI}" "${BOTAN_ROOT}/build/include/public")
target_compile_definitions(openlips_stfs PRIVATE XBOXINTERNALS_STATIC _CRT_SECURE_NO_WARNINGS)
target_compile_options(openlips_stfs PRIVATE /EHsc /bigobj)
target_link_libraries(openlips_stfs PRIVATE "${BOTAN_LIB}" bcrypt)
