cmake_minimum_required(VERSION 3.21)
project(XenosagaHostChecks LANGUAGES CXX)
include(CTest)
set(PS2RECOMP "${CMAKE_CURRENT_LIST_DIR}/../../../PS2Recomp" CACHE PATH "Patched PS2Recomp checkout")
add_subdirectory("${PS2RECOMP}/ps2xTest/gs_cache" gs_cache)
# The patched GS frontend uses the presentation hooks even in CPU-only tests.
target_sources(ps2_gs_cache_backend_under_test PRIVATE
    "${PS2RECOMP}/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp")
target_compile_options(ps2_gs_cache_backend_under_test PRIVATE -mavx2)
add_executable(xs_iso_test iso_test.cpp)
target_compile_features(xs_iso_test PRIVATE cxx_std_17)
add_test(NAME port.iso_lookup COMMAND xs_iso_test)

add_executable(xs_gs_present_test gs_present_test.cpp)
target_link_libraries(xs_gs_present_test PRIVATE ps2_gs_cache_backend_under_test)
add_test(NAME port.gs_field_presentation COMMAND xs_gs_present_test)

add_executable(xs_gs_q_latch_test gs_q_latch_test.cpp)
target_link_libraries(xs_gs_q_latch_test PRIVATE ps2_gs_cache_backend_under_test)
foreach(workers 1 8)
    add_test(NAME port.gs_q_latch_${workers}_worker COMMAND xs_gs_q_latch_test)
    set_tests_properties(port.gs_q_latch_${workers}_worker PROPERTIES
        ENVIRONMENT "PS2X_GS_THREADS=${workers}")
endforeach()

add_executable(xs_gs_presentation_order_test gs_presentation_order_test.cpp)
target_link_libraries(xs_gs_presentation_order_test PRIVATE ps2_gs_cache_backend_under_test)
foreach(workers 1 8)
    foreach(pack 0 1)
        add_test(NAME port.gs_presentation_order_${workers}_worker_pack_${pack}
            COMMAND xs_gs_presentation_order_test)
        set_tests_properties(port.gs_presentation_order_${workers}_worker_pack_${pack} PROPERTIES
            ENVIRONMENT "PS2X_GS_THREADS=${workers};PS2X_GS_PACK=${pack}" TIMEOUT 20)
    endforeach()
endforeach()
