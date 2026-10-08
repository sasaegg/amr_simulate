// AMR 建圖面板（RViz 外掛）：輸入車輛 id 與地圖名稱，按「存圖」呼叫 /<id>/map_saver/save_map，
// 並顯示建圖狀態（地圖尺寸、已知比例、最後更新時間）。面板不直接寫檔，存圖由車上的服務完成。

#ifndef AMR_RVIZ_PLUGINS__MAPPING_PANEL_HPP_
#define AMR_RVIZ_PLUGINS__MAPPING_PANEL_HPP_

#include <chrono>
#include <string>

#include <QString>

#include "nav2_msgs/srv/save_map.hpp"
#include "nav_msgs/msg/occupancy_grid.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rviz_common/panel.hpp"

class QLabel;
class QLineEdit;
class QPushButton;
class QTimer;

namespace amr_rviz_plugins
{

class MappingPanel : public rviz_common::Panel
{
  Q_OBJECT

public:
  explicit MappingPanel(QWidget * parent = nullptr);

  // RViz 建好 DisplayContext 後呼叫：這時才拿得到 ROS 節點
  void onInitialize() override;

  // 車輛 id 與地圖名稱存進 .rviz 設定檔
  void load(const rviz_common::Config & config) override;
  void save(rviz_common::Config config) const override;

  // 存圖目錄（車上的執行資料目錄，與 navigation.launch.xml 的 /data/maps 一致）
  static constexpr const char * kMapsDir = "/data/maps";

  // 地圖名稱只允許英數字、底線、連字號（會變成檔名，防止 ../ 路徑穿越）
  static bool isValidMapName(const QString & name);

private Q_SLOTS:
  void onSaveClicked();
  void onRobotIdChanged();
  void refreshStatus();

private:
  void connectToRobot();
  void onMap(nav_msgs::msg::OccupancyGrid::ConstSharedPtr msg);
  void onSaveResult(rclcpp::Client<nav2_msgs::srv::SaveMap>::SharedFuture future, QString path);

  QLineEdit * robot_id_edit_;
  QLineEdit * map_name_edit_;
  QPushButton * save_button_;
  QLabel * status_label_;
  QLabel * result_label_;
  QTimer * timer_;

  rclcpp::Node::SharedPtr node_;
  rclcpp::Subscription<nav_msgs::msg::OccupancyGrid>::SharedPtr map_sub_;
  rclcpp::Client<nav2_msgs::srv::SaveMap>::SharedPtr save_client_;
  std::string robot_id_;

  // 建圖狀態（在 RViz 的執行緒更新，計時器負責刷新畫面）
  bool have_map_ = false;
  unsigned int map_width_ = 0;
  unsigned int map_height_ = 0;
  double known_ratio_ = 0.0;
  std::chrono::steady_clock::time_point last_map_time_;
  bool saving_ = false;
};

}  // namespace amr_rviz_plugins

#endif  // AMR_RVIZ_PLUGINS__MAPPING_PANEL_HPP_
