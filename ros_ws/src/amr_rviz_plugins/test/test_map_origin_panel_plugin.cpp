// 地圖原點面板與「設定原點」工具：用 pluginlib 載入（和 RViz 相同的方式），檢查元件與角度計算。

#include <gtest/gtest.h>

#include <QApplication>
#include <QCheckBox>
#include <QPushButton>

#include <cmath>

#include "amr_rviz_plugins/map_origin_panel.hpp"
#include "pluginlib/class_loader.hpp"
#include "rviz_common/panel.hpp"
#include "rviz_common/tool.hpp"

namespace
{
constexpr double kPi = 3.14159265358979323846;
double rad(double deg) {return deg * kPi / 180.0;}
}

class MapOriginPlugins : public ::testing::Test
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
QApplication * MapOriginPlugins::app_ = nullptr;

TEST_F(MapOriginPlugins, panel_loads_with_apply_disabled)
{
  pluginlib::ClassLoader<rviz_common::Panel> loader("rviz_common", "rviz_common::Panel");
  ASSERT_TRUE(loader.isClassAvailable("amr_rviz_plugins/MapOriginPanel"));
  auto panel = loader.createSharedInstance("amr_rviz_plugins/MapOriginPanel");
  auto apply = panel->findChild<QPushButton *>("apply");
  auto snap = panel->findChild<QCheckBox *>("snap");
  ASSERT_NE(apply, nullptr);
  ASSERT_NE(snap, nullptr);
  EXPECT_FALSE(apply->isEnabled());        // 還沒選取原點
  EXPECT_TRUE(snap->isChecked());          // 預設對齊 90° 倍數
}

TEST_F(MapOriginPlugins, set_origin_tool_is_registered)
{
  pluginlib::ClassLoader<rviz_common::Tool> loader("rviz_common", "rviz_common::Tool");
  EXPECT_TRUE(loader.isClassAvailable("amr_rviz_plugins/SetOriginTool"));
}

TEST(MapOriginMath, snaps_to_nearest_right_angle)
{
  using amr_rviz_plugins::MapOriginPanel;
  EXPECT_DOUBLE_EQ(MapOriginPanel::snapToRightAngle(rad(2.3)), 0.0);
  EXPECT_DOUBLE_EQ(MapOriginPanel::snapToRightAngle(rad(-44)), 0.0);
  EXPECT_NEAR(MapOriginPanel::snapToRightAngle(rad(46)), kPi / 2, 1e-12);
  EXPECT_NEAR(MapOriginPanel::snapToRightAngle(rad(-91)), -kPi / 2, 1e-12);
  EXPECT_NEAR(std::abs(MapOriginPanel::snapToRightAngle(rad(179))), kPi, 1e-12);
  EXPECT_NEAR(std::abs(MapOriginPanel::snapToRightAngle(rad(-179))), kPi, 1e-12);
}

TEST(MapOriginMath, map_name_from_yaml_filename)
{
  using amr_rviz_plugins::MapOriginPanel;
  EXPECT_EQ(MapOriginPanel::mapNameFromYaml("/data/maps/warehouse_small.yaml"), "warehouse_small");
  EXPECT_EQ(MapOriginPanel::mapNameFromYaml("floor-2.yaml"), "floor-2");
  EXPECT_EQ(MapOriginPanel::mapNameFromYaml("/data/maps/x.pgm"), "");
  EXPECT_EQ(MapOriginPanel::mapNameFromYaml(""), "");
}
