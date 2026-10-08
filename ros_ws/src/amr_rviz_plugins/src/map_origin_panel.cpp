#include "amr_rviz_plugins/map_origin_panel.hpp"

#include <QCheckBox>
#include <QFormLayout>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPushButton>
#include <QTimer>
#include <QVBoxLayout>

#include <cmath>
#include <memory>
#include <string>
#include <vector>

#include "pluginlib/class_list_macros.hpp"
#include "rviz_common/display_context.hpp"
#include "rviz_common/ros_integration/ros_node_abstraction_iface.hpp"

namespace amr_rviz_plugins
{

namespace
{
constexpr double kPi = 3.14159265358979323846;

double degrees(double rad) {return rad * 180.0 / kPi;}

double yawOf(const geometry_msgs::msg::Quaternion & q)
{
  return std::atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z));
}
}  // namespace

MapOriginPanel::MapOriginPanel(QWidget * parent)
: rviz_common::Panel(parent)
{
  robot_id_edit_ = new QLineEdit("amr1");
  robot_id_edit_->setObjectName("robot_id");
  map_label_ = new QLabel("（等待顯示用的地圖）");
  map_label_->setObjectName("map");
  candidate_label_ = new QLabel("用工具列「設定原點」在地圖上按下＝位置、拖曳＝x 軸方向");
  candidate_label_->setObjectName("candidate");
  candidate_label_->setWordWrap(true);
  snap_check_ = new QCheckBox("對齊 90° 倍數（不重新取樣，地圖不失真）");
  snap_check_->setObjectName("snap");
  snap_check_->setChecked(true);
  apply_button_ = new QPushButton("套用");
  apply_button_->setObjectName("apply");
  apply_button_->setEnabled(false);
  result_label_ = new QLabel;
  result_label_->setObjectName("result");
  result_label_->setWordWrap(true);

  auto form = new QFormLayout;
  form->addRow("車輛", robot_id_edit_);
  form->addRow("地圖", map_label_);

  auto layout = new QVBoxLayout;
  layout->addLayout(form);
  layout->addWidget(candidate_label_);
  layout->addWidget(snap_check_);
  layout->addWidget(apply_button_);
  layout->addWidget(result_label_);
  layout->addStretch();
  setLayout(layout);

  connect(apply_button_, &QPushButton::clicked, this, &MapOriginPanel::onApplyClicked);
  connect(robot_id_edit_, &QLineEdit::editingFinished, this, &MapOriginPanel::onRobotIdChanged);
  connect(snap_check_, &QCheckBox::toggled, this, [this] {refresh(); Q_EMIT configChanged();});
  connect(robot_id_edit_, &QLineEdit::textChanged, this, [this] {Q_EMIT configChanged();});

  timer_ = new QTimer(this);
  connect(timer_, &QTimer::timeout, this, &MapOriginPanel::refresh);
}

double MapOriginPanel::snapToRightAngle(double yaw)
{
  double snapped = std::round(yaw / (kPi / 2.0)) * (kPi / 2.0);
  snapped = std::atan2(std::sin(snapped), std::cos(snapped));     // 正規化到 (−π, π]
  if (std::abs(snapped) < 1e-12) {
    snapped = 0.0;                                                  // 避免 −0
  }
  return snapped;
}

std::string MapOriginPanel::mapNameFromYaml(const std::string & yaml_filename)
{
  const auto slash = yaml_filename.find_last_of('/');
  std::string base = slash == std::string::npos ? yaml_filename : yaml_filename.substr(slash + 1);
  const std::string suffix = ".yaml";
  if (base.size() > suffix.size() &&
    base.compare(base.size() - suffix.size(), suffix.size(), suffix) == 0)
  {
    return base.substr(0, base.size() - suffix.size());
  }
  return "";
}

void MapOriginPanel::onInitialize()
{
  node_ = getDisplayContext()->getRosNodeAbstraction().lock()->get_raw_node();
  connectToRobot();
  timer_->start(500);
}

void MapOriginPanel::load(const rviz_common::Config & config)
{
  rviz_common::Panel::load(config);
  QString value;
  if (config.mapGetString("robot_id", &value)) {
    robot_id_edit_->setText(value);
  }
  bool snap = true;
  if (config.mapGetBool("snap", &snap)) {
    snap_check_->setChecked(snap);
  }
  // RViz 先呼叫 onInitialize() 再 load()：車輛 id 沒變就不要重建連線（會丟掉進行中的請求）
  if (node_ && robot_id_edit_->text().trimmed().toStdString() != robot_id_) {
    connectToRobot();
  }
}

void MapOriginPanel::save(rviz_common::Config config) const
{
  rviz_common::Panel::save(config);
  config.mapSetValue("robot_id", robot_id_edit_->text());
  config.mapSetValue("snap", snap_check_->isChecked());
}

void MapOriginPanel::onRobotIdChanged()
{
  if (node_ && robot_id_edit_->text().trimmed().toStdString() != robot_id_) {
    connectToRobot();
  }
}

void MapOriginPanel::connectToRobot()
{
  robot_id_ = robot_id_edit_->text().trimmed().toStdString();
  const std::string ns = "/" + robot_id_;
  have_candidate_ = false;
  map_name_.clear();
  // 換掉客戶端時，舊客戶端等待中的回覆會一起被丟掉、回呼不會執行；忙碌狀態要歸零，否則按鈕永遠是灰的
  busy_ = false;
  candidate_sub_ = node_->create_subscription<geometry_msgs::msg::PoseStamped>(
    ns + "/map_origin/candidate", 10,
    [this](geometry_msgs::msg::PoseStamped::ConstSharedPtr msg) {
      if (ignore_next_candidate_) {
        ignore_next_candidate_ = false;
        return;
      }
      cand_x_ = msg->pose.position.x;
      cand_y_ = msg->pose.position.y;
      cand_yaw_ = yawOf(msg->pose.orientation);
      have_candidate_ = true;
      refresh();
    });
  candidate_pub_ = node_->create_publisher<geometry_msgs::msg::PoseStamped>(
    ns + "/map_origin/candidate", 10);
  set_client_ = node_->create_client<amr_interfaces::srv::SetMapOrigin>(ns + "/map_origin/set");
  load_client_ = node_->create_client<nav2_msgs::srv::LoadMap>(ns + "/map_origin_viewer/load_map");
  // 讀顯示用 map_server 的 yaml_filename：呼叫它的 get_parameters 服務
  viewer_params_ = node_->create_client<rcl_interfaces::srv::GetParameters>(
    ns + "/map_origin_viewer/get_parameters");
  refresh();
}

void MapOriginPanel::requestMapName()
{
  if (!viewer_params_ || !viewer_params_->service_is_ready() || busy_) {
    return;
  }
  busy_ = true;
  auto request = std::make_shared<rcl_interfaces::srv::GetParameters::Request>();
  request->names = {"yaml_filename"};
  viewer_params_->async_send_request(
    request,
    [this](rclcpp::Client<rcl_interfaces::srv::GetParameters>::SharedFuture future) {
      busy_ = false;
      const auto & values = future.get()->values;
      if (!values.empty() && values[0].type == rcl_interfaces::msg::ParameterType::PARAMETER_STRING) {
        yaml_filename_ = values[0].string_value;
        map_name_ = mapNameFromYaml(yaml_filename_);
      }
      refresh();
    });
}

double MapOriginPanel::appliedYaw() const
{
  return snap_check_->isChecked() ? snapToRightAngle(cand_yaw_) : cand_yaw_;
}

void MapOriginPanel::refresh()
{
  if (map_name_.empty()) {
    requestMapName();
    map_label_->setText(QString("（等待 /%1/map_origin_viewer）").arg(QString::fromStdString(robot_id_)));
  } else {
    map_label_->setText(QString::fromStdString(map_name_));
  }

  if (have_candidate_) {
    candidate_label_->setText(
      QString("原點 (%1, %2)　方向：拖曳 %3° → 套用 %4°")
      .arg(cand_x_, 0, 'f', 3).arg(cand_y_, 0, 'f', 3)
      .arg(degrees(cand_yaw_), 0, 'f', 1).arg(degrees(appliedYaw()), 0, 'f', 1));
  }

  const bool ready = set_client_ && set_client_->service_is_ready();
  apply_button_->setEnabled(have_candidate_ && ready && !map_name_.empty() && !busy_);
}

void MapOriginPanel::onApplyClicked()
{
  const double yaw = appliedYaw();
  const QString name = QString::fromStdString(map_name_);
  const auto answer = QMessageBox::question(
    this, "套用地圖原點",
    QString("把地圖 %1 的原點改到 (%2, %3)、x 軸方向 %4°。\n\n"
    "會改寫 %5 與同名 .pgm；\n原檔備份成 %1.bak.pgm／%1.bak.yaml。確定要套用嗎？")
    .arg(name).arg(cand_x_, 0, 'f', 3).arg(cand_y_, 0, 'f', 3).arg(degrees(yaw), 0, 'f', 1)
    .arg(QString::fromStdString(yaml_filename_)));
  if (answer != QMessageBox::Yes) {
    return;
  }

  auto request = std::make_shared<amr_interfaces::srv::SetMapOrigin::Request>();
  request->map_name = map_name_;
  request->x = cand_x_;
  request->y = cand_y_;
  request->yaw = yaw;
  busy_ = true;
  result_label_->setText("套用中…");
  refresh();
  set_client_->async_send_request(
    request,
    [this](rclcpp::Client<amr_interfaces::srv::SetMapOrigin>::SharedFuture future) {
      busy_ = false;
      const auto response = future.get();
      result_label_->setText(QString::fromStdString(
        (response->success ? "已套用：" : "失敗：") + response->message));
      if (response->success) {
        // 原點變了，剛才的選取以舊座標表示，不能再用
        have_candidate_ = false;
        candidate_label_->setText("已套用。地圖重新載入後，座標軸就是新原點。");
        auto load = std::make_shared<nav2_msgs::srv::LoadMap::Request>();
        load->map_url = yaml_filename_;
        if (load_client_->service_is_ready()) {
          load_client_->async_send_request(load);
        }
        // 預覽座標軸還在舊座標的位置：移到新原點 (0, 0)，也就是剛才選的位置
        geometry_msgs::msg::PoseStamped origin;
        origin.header.frame_id = "map";
        origin.header.stamp = node_->now();
        origin.pose.orientation.w = 1.0;
        ignore_next_candidate_ = true;
        candidate_pub_->publish(origin);
      }
      refresh();
    });
}

}  // namespace amr_rviz_plugins

PLUGINLIB_EXPORT_CLASS(amr_rviz_plugins::MapOriginPanel, rviz_common::Panel)
