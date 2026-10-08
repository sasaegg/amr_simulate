#include "amr_rviz_plugins/mapping_panel.hpp"

#include <QFormLayout>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPushButton>
#include <QRegularExpression>
#include <QTimer>
#include <QVBoxLayout>

#include <algorithm>
#include <memory>

#include "pluginlib/class_list_macros.hpp"
#include "rviz_common/display_context.hpp"
#include "rviz_common/ros_integration/ros_node_abstraction_iface.hpp"

namespace amr_rviz_plugins
{

MappingPanel::MappingPanel(QWidget * parent)
: rviz_common::Panel(parent)
{
  robot_id_edit_ = new QLineEdit("amr1");
  robot_id_edit_->setObjectName("robot_id");
  map_name_edit_ = new QLineEdit("warehouse_small");
  map_name_edit_->setObjectName("map_name");
  save_button_ = new QPushButton("存圖");
  save_button_->setObjectName("save");
  status_label_ = new QLabel("尚未收到地圖（建圖有在執行嗎？）");
  status_label_->setObjectName("status");
  status_label_->setWordWrap(true);
  result_label_ = new QLabel;
  result_label_->setObjectName("result");
  result_label_->setWordWrap(true);

  auto form = new QFormLayout;
  form->addRow("車輛", robot_id_edit_);
  form->addRow("地圖名稱", map_name_edit_);

  auto layout = new QVBoxLayout;
  layout->addLayout(form);
  layout->addWidget(save_button_);
  layout->addWidget(status_label_);
  layout->addWidget(result_label_);
  layout->addStretch();
  setLayout(layout);

  connect(save_button_, &QPushButton::clicked, this, &MappingPanel::onSaveClicked);
  connect(robot_id_edit_, &QLineEdit::editingFinished, this, &MappingPanel::onRobotIdChanged);
  // 欄位一改就標記設定檔「有變更」，RViz 關閉時會提醒存檔
  connect(robot_id_edit_, &QLineEdit::textChanged, this, [this] {Q_EMIT configChanged();});
  connect(map_name_edit_, &QLineEdit::textChanged, this, [this] {Q_EMIT configChanged();});

  // 每秒刷新狀態（「最後更新 N 秒前」需要持續更新）
  timer_ = new QTimer(this);
  connect(timer_, &QTimer::timeout, this, &MappingPanel::refreshStatus);
}

void MappingPanel::onInitialize()
{
  node_ = getDisplayContext()->getRosNodeAbstraction().lock()->get_raw_node();
  connectToRobot();
  timer_->start(1000);
}

void MappingPanel::load(const rviz_common::Config & config)
{
  rviz_common::Panel::load(config);
  QString value;
  if (config.mapGetString("robot_id", &value)) {
    robot_id_edit_->setText(value);
  }
  if (config.mapGetString("map_name", &value)) {
    map_name_edit_->setText(value);
  }
  if (node_) {
    connectToRobot();
  }
}

void MappingPanel::save(rviz_common::Config config) const
{
  rviz_common::Panel::save(config);
  config.mapSetValue("robot_id", robot_id_edit_->text());
  config.mapSetValue("map_name", map_name_edit_->text());
}

bool MappingPanel::isValidMapName(const QString & name)
{
  static const QRegularExpression pattern("^[A-Za-z0-9_-]+$");
  return pattern.match(name).hasMatch();
}

void MappingPanel::onRobotIdChanged()
{
  if (node_ && robot_id_edit_->text().toStdString() != robot_id_) {
    connectToRobot();
  }
}

void MappingPanel::connectToRobot()
{
  robot_id_ = robot_id_edit_->text().trimmed().toStdString();
  have_map_ = false;

  // 地圖只在更新時發布一次，用 Transient Local 才收得到訂閱前發過的最後一筆
  auto qos = rclcpp::QoS(1).reliable().transient_local();
  map_sub_ = node_->create_subscription<nav_msgs::msg::OccupancyGrid>(
    "/" + robot_id_ + "/map", qos,
    [this](nav_msgs::msg::OccupancyGrid::ConstSharedPtr msg) {onMap(msg);});
  save_client_ = node_->create_client<nav2_msgs::srv::SaveMap>(
    "/" + robot_id_ + "/map_saver/save_map");
  refreshStatus();
}

void MappingPanel::onMap(nav_msgs::msg::OccupancyGrid::ConstSharedPtr msg)
{
  map_width_ = msg->info.width;
  map_height_ = msg->info.height;
  const auto total = msg->data.size();
  const auto unknown = std::count(msg->data.begin(), msg->data.end(), -1);
  known_ratio_ = total ? static_cast<double>(total - unknown) / total : 0.0;
  last_map_time_ = std::chrono::steady_clock::now();
  have_map_ = true;
  refreshStatus();
}

void MappingPanel::refreshStatus()
{
  const bool service_ready = save_client_ && save_client_->service_is_ready();
  save_button_->setEnabled(service_ready && !saving_);

  QString text;
  if (!have_map_) {
    text = QString("尚未收到 /%1/map（建圖有在執行嗎？）").arg(QString::fromStdString(robot_id_));
  } else {
    const auto age = std::chrono::duration_cast<std::chrono::seconds>(
      std::chrono::steady_clock::now() - last_map_time_).count();
    text = QString("地圖 %1 × %2，已知 %3%，最後更新 %4 秒前")
      .arg(map_width_).arg(map_height_)
      .arg(known_ratio_ * 100.0, 0, 'f', 0).arg(age);
  }
  if (!service_ready) {
    text += QString("\n存圖服務 /%1/map_saver/save_map 尚未就緒").arg(QString::fromStdString(robot_id_));
  }
  status_label_->setText(text);
}

void MappingPanel::onSaveClicked()
{
  const QString name = map_name_edit_->text().trimmed();
  if (!isValidMapName(name)) {
    QMessageBox::warning(this, "地圖名稱不正確", "地圖名稱只能包含英數字、底線（_）與連字號（-）。");
    return;
  }
  const QString path = QString("%1/%2").arg(kMapsDir, name);
  const auto answer = QMessageBox::question(
    this, "存圖",
    QString("把目前的地圖存成：\n%1.pgm\n%1.yaml\n\n同名的檔案會被覆蓋。確定要存嗎？").arg(path));
  if (answer != QMessageBox::Yes) {
    return;
  }

  auto request = std::make_shared<nav2_msgs::srv::SaveMap::Request>();
  request->map_topic = "/" + robot_id_ + "/map";
  request->map_url = path.toStdString();
  request->image_format = "pgm";
  request->map_mode = "trinary";
  request->free_thresh = 0.25;
  request->occupied_thresh = 0.65;

  saving_ = true;
  result_label_->setText("存圖中…");
  refreshStatus();
  // 非同步呼叫：結果在 RViz 的執行緒回呼，不卡住畫面
  save_client_->async_send_request(
    request,
    [this, path](rclcpp::Client<nav2_msgs::srv::SaveMap>::SharedFuture future) {
      onSaveResult(future, path);
    });
}

void MappingPanel::onSaveResult(
  rclcpp::Client<nav2_msgs::srv::SaveMap>::SharedFuture future, QString path)
{
  saving_ = false;
  if (future.get()->result) {
    result_label_->setText(QString("已存：%1.pgm／.yaml").arg(path));
  } else {
    result_label_->setText(QString("存圖失敗：%1（看 map_saver 的訊息）").arg(path));
  }
  refreshStatus();
}

}  // namespace amr_rviz_plugins

PLUGINLIB_EXPORT_CLASS(amr_rviz_plugins::MappingPanel, rviz_common::Panel)
