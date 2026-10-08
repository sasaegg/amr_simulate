cmake_minimum_required(VERSION 3.8)
project(amr_rviz_plugins)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(amr_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav2_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rcl_interfaces REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rviz_common REQUIRED)
find_package(rviz_default_plugins REQUIRED)
find_package(Qt5 REQUIRED COMPONENTS Widgets)

# Qt 的 signal／slot 需要 moc 產生程式碼；AUTOMOC 會掃描有 Q_OBJECT 的檔案
set(CMAKE_AUTOMOC ON)

add_library(${PROJECT_NAME} SHARED
  include/${PROJECT_NAME}/mapping_panel.hpp     # 列出標頭檔，AUTOMOC 才會處理它的 Q_OBJECT
  include/${PROJECT_NAME}/map_origin_panel.hpp
  src/mapping_panel.cpp
  src/map_origin_panel.cpp
  src/set_origin_tool.cpp
)
target_include_directories(${PROJECT_NAME} PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(${PROJECT_NAME} Qt5::Widgets)
ament_target_dependencies(${PROJECT_NAME}
  amr_interfaces geometry_msgs nav2_msgs nav_msgs pluginlib rcl_interfaces rclcpp rviz_common rviz_default_plugins)

# 把 plugins_description.xml 登記到 ament index（rviz_common__pluginlib__plugin），RViz 靠它找到外掛
pluginlib_export_plugin_description_file(rviz_common plugins_description.xml)

install(TARGETS ${PROJECT_NAME}
  LIBRARY DESTINATION lib
  ARCHIVE DESTINATION lib
  RUNTIME DESTINATION bin
)
install(DIRECTORY include/ DESTINATION include)
install(DIRECTORY launch config DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)
  # 實際用 pluginlib 載入面板並建立（不開 RViz；Qt 用 offscreen 平台）
  ament_add_gtest(test_mapping_panel_plugin test/test_mapping_panel_plugin.cpp
    ENV QT_QPA_PLATFORM=offscreen)
  target_link_libraries(test_mapping_panel_plugin ${PROJECT_NAME} Qt5::Widgets)
  ament_target_dependencies(test_mapping_panel_plugin pluginlib rviz_common)
  ament_add_gtest(test_map_origin_panel_plugin test/test_map_origin_panel_plugin.cpp
    ENV QT_QPA_PLATFORM=offscreen)
  target_link_libraries(test_map_origin_panel_plugin ${PROJECT_NAME} Qt5::Widgets)
  ament_target_dependencies(test_map_origin_panel_plugin pluginlib rviz_common)
  ament_add_pytest_test(test_panel_static test/test_panel_static.py)
endif()

ament_package()
