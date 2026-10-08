// AMR 地圖原點面板（RViz 外掛）：顯示「設定原點」工具選取的位置與方向，按「套用」呼叫
// /<id>/map_origin/set 改寫地圖檔，成功後請顯示用的 map_server 重新載入。
// 要改寫哪張地圖，取自顯示用 map_server（/<id>/map_origin_viewer）的 yaml_filename 參數——
// 面板顯示的地圖一定就是要改的那張，不會手打名稱打錯。

#ifndef AMR_RVIZ_PLUGINS__MAP_ORIGIN_PANEL_HPP_
#define AMR_RVIZ_PLUGINS__MAP_ORIGIN_PANEL_HPP_

#include <memory>
#include <string>

#include "amr_interfaces/srv/set_map_origin.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "nav2_msgs/srv/load_map.hpp"
#include "rcl_interfaces/srv/get_parameters.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rviz_common/panel.hpp"

class QCheckBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QTimer;

namespace amr_rviz_plugins
{

class MapOriginPanel : public rviz_common::Panel
{
  Q_OBJECT

public:
  explicit MapOriginPanel(QWidget * parent = nullptr);

  void onInitialize() override;
  void load(const rviz_common::Config & config) override;
  void save(rviz_common::Config config) const override;

  // 取最接近的 90° 倍數，結果在 (−π, π]（「對齊 90° 倍數」選項）
  static double snapToRightAngle(double yaw);
  // yaml_filename（例如 /data/maps/warehouse_small.yaml）→ 地圖名稱（warehouse_small）
  static std::string mapNameFromYaml(const std::string & yaml_filename);

private Q_SLOTS:
  void onApplyClicked();
  void onRobotIdChanged();
  void refresh();

private:
  void connectToRobot();
  void requestMapName();
  double appliedYaw() const;

  QLineEdit * robot_id_edit_;
  QLabel * map_label_;
  QLabel * candidate_label_;
  QCheckBox * snap_check_;
  QPushButton * apply_button_;
  QLabel * result_label_;
  QTimer * timer_;

  rclcpp::Node::SharedPtr node_;
  std::string robot_id_;
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr candidate_sub_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr candidate_pub_;  // 套用後把預覽移到新原點
  rclcpp::Client<amr_interfaces::srv::SetMapOrigin>::SharedPtr set_client_;
  rclcpp::Client<nav2_msgs::srv::LoadMap>::SharedPtr load_client_;
  rclcpp::Client<rcl_interfaces::srv::GetParameters>::SharedPtr viewer_params_;

  std::string map_name_;          // 空字串＝還不知道
  std::string yaml_filename_;
  bool have_candidate_ = false;
  double cand_x_ = 0.0;
  double cand_y_ = 0.0;
  double cand_yaw_ = 0.0;
  bool busy_ = false;
  bool ignore_next_candidate_ = false;   // 自己發布的 (0,0,0) 不算使用者的選取
};

}  // namespace amr_rviz_plugins

#endif  // AMR_RVIZ_PLUGINS__MAP_ORIGIN_PANEL_HPP_
