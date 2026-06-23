add_executable(pr_lidar_native main.cpp)

set_target_properties(pr_lidar_native PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
)

set_property(TARGET pr_lidar_native PROPERTY VS_DEBUGGER_WORKING_DIRECTORY "${CMAKE_BINARY_DIR}")

target_link_libraries(pr_lidar_native PRIVATE
  picpr_drc
  picpr_route_lidar
  picpr_io
  picpr_db
  picpr_utility
  yaml-cpp::yaml-cpp
  spdlog::spdlog
  Boost::boost
)

target_compile_definitions(pr_lidar_native PRIVATE
  PR_LIDAR_NATIVE_SCRIPT_DIR="${CMAKE_CURRENT_SOURCE_DIR}/scripts"
  PR_LIDAR_NATIVE_PICBENCH_FLOW_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../picbench_flow"
)
