cmake_minimum_required(VERSION 3.8)
project(amr_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

# 由 .srv 產生 C++（rosidl_generator_cpp）與 Python（rosidl_generator_py）程式碼
rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/SetMapOrigin.srv"
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
