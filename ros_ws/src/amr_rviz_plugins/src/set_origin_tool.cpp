// 「設定原點」工具：和 RViz 內建的 2D Goal Pose 一樣（按下＝位置、拖曳＝方向，發布 PoseStamped），
// 只是名稱不同、topic 由 map_origin.rviz 設為 /<id>/map_origin/candidate——避免在地圖原點畫面上
// 看到「2D Goal Pose」而以為是導航目標。

#include "rviz_default_plugins/tools/goal_pose/goal_tool.hpp"

#include "pluginlib/class_list_macros.hpp"

namespace amr_rviz_plugins
{

class SetOriginTool : public rviz_default_plugins::tools::GoalTool
{
public:
  void onInitialize() override
  {
    GoalTool::onInitialize();
    setName("設定原點");
  }
};

}  // namespace amr_rviz_plugins

PLUGINLIB_EXPORT_CLASS(amr_rviz_plugins::SetOriginTool, rviz_common::Tool)
