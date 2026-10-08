// 用 pluginlib 實際載入面板並建立（和 RViz 找外掛的方式相同），不需要開 RViz。
// Qt 用 offscreen 平台（CMakeLists 設定 QT_QPA_PLATFORM=offscreen），沒有螢幕也能建立元件。

#include <gtest/gtest.h>

#include <QApplication>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>

#include <memory>

#include "amr_rviz_plugins/mapping_panel.hpp"
#include "pluginlib/class_loader.hpp"
#include "rviz_common/panel.hpp"

class MappingPanelPlugin : public ::testing::Test
{
protected:
  static void SetUpTestSuite()
  {
    static int argc = 1;
    static char name[] = "test";
    static char * argv[] = {name, nullptr};
    app_ = new QApplication(argc, argv);
  }

  static QApplication * app_;
};
QApplication * MappingPanelPlugin::app_ = nullptr;

TEST_F(MappingPanelPlugin, pluginlib_finds_and_creates_panel)
{
  pluginlib::ClassLoader<rviz_common::Panel> loader("rviz_common", "rviz_common::Panel");
  ASSERT_TRUE(loader.isClassAvailable("amr_rviz_plugins/MappingPanel"));
  auto panel = loader.createSharedInstance("amr_rviz_plugins/MappingPanel");
  ASSERT_NE(panel, nullptr);

  // 面板上的元件（建構時建立；onInitialize 需要 RViz 的 DisplayContext，這裡不呼叫）
  auto robot_id = panel->findChild<QLineEdit *>("robot_id");
  auto map_name = panel->findChild<QLineEdit *>("map_name");
  auto save = panel->findChild<QPushButton *>("save");
  ASSERT_NE(robot_id, nullptr);
  ASSERT_NE(map_name, nullptr);
  ASSERT_NE(save, nullptr);
  EXPECT_NE(panel->findChild<QLabel *>("status"), nullptr);
  EXPECT_EQ(robot_id->text().toStdString(), "amr1");
  EXPECT_EQ(map_name->text().toStdString(), "warehouse_small");
}

TEST(MappingPanelNames, only_safe_map_names_are_accepted)
{
  using amr_rviz_plugins::MappingPanel;
  EXPECT_TRUE(MappingPanel::isValidMapName("warehouse_small"));
  EXPECT_TRUE(MappingPanel::isValidMapName("floor-2_v3"));
  EXPECT_FALSE(MappingPanel::isValidMapName(""));
  EXPECT_FALSE(MappingPanel::isValidMapName("../etc/passwd"));
  EXPECT_FALSE(MappingPanel::isValidMapName("a/b"));
  EXPECT_FALSE(MappingPanel::isValidMapName("my map"));
  EXPECT_FALSE(MappingPanel::isValidMapName("地圖"));
}
