"""虛擬底盤的「把車體放進世界」：等世界出現 → 已有同名車就停下並移回出生點，沒有就生成。

真車上沒有這一步（車體本來就在現場）；模擬時相當於「把車推到出生點」。
Gazebo 端以 ign CLI 操作（service 清單、移除實體、列出模型），生成交給 ros_gz_sim create。

觀察到的 Gazebo 行為（task 5.8 實測）：
- 同名實體已存在時 create 仍回報 OK，但不會產生第二台 → 不能靠回報判斷。
- **移除同時帶 gpu_lidar 與 IMU 的模型後，Fortress 的場景服務壞掉**（模型清單查不到、之後無法生成；
  只有其中一種感測器時正常）→ 不移除，改用 UserCommands 的 set_pose 把車移回出生點。
- DiffDrive 會一直執行最後收到的速度指令 → 移回前先送一次零速度，否則車子會接著跑。
- create service 一出現就送出要求，世界可能還沒準備好而丟掉要求 → 生成後確認車輛真的出現，否則重試。
- `ign model` 沒有指定 world 的參數（只支援單一世界）。
- create 要用 `-string` 傳 URDF 內容：`-file` 只傳路徑，sim 與 robot 是不同容器，Gazebo 讀不到 robot 的檔案。
"""

import argparse
import math
import re
import subprocess
import sys
import time

CREATE_SERVICE = re.compile(r'^/world/([^/\s]+)/create$')
MODEL_LINE = re.compile(r'^\s*-\s+(\S+)\s*$')


# ---------- 純邏輯（可單元測試） ----------

def worlds_from_services(service_list):
    """從 `ign service -l` 的輸出找出所有 world 名稱（依 /world/<名稱>/create 判斷）。"""
    found = []
    for line in service_list.splitlines():
        match = CREATE_SERVICE.match(line.strip())
        if match and match.group(1) not in found:
            found.append(match.group(1))
    return found


def choose_world(worlds):
    """0 個 → None（世界還沒起來，繼續等）；1 個 → 它；多個 → 無法自動判斷，報錯。"""
    if not worlds:
        return None
    if len(worlds) > 1:
        raise RuntimeError(f'Gazebo 中有多個 world：{", ".join(worlds)}，無法判斷要放進哪一個')
    return worlds[0]


def models_from_list(model_list):
    """從 `ign model --list` 的輸出取出模型名稱。"""
    return [m.group(1) for m in map(MODEL_LINE.match, model_list.splitlines()) if m]


def yaw_to_quaternion(yaw):
    """只繞 z 軸旋轉的四元數 (x, y, z, w)。"""
    return (0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2))


def set_pose_request(name, x, y, yaw):
    qx, qy, qz, qw = yaw_to_quaternion(yaw)
    return (f'name: "{name}" position: {{x: {x}, y: {y}, z: 0}} '
            f'orientation: {{x: {qx}, y: {qy}, z: {qz}, w: {qw}}}')


def position_from_pose_output(output):
    """從 `ign model -m <名稱> -p` 的輸出取出位置 (x, y, z)；找不到時回傳 None。"""
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if 'XYZ' in line and i + 1 < len(lines):
            numbers = re.findall(r'-?\d+(?:\.\d+)?', lines[i + 1])
            if len(numbers) == 3:
                return tuple(float(n) for n in numbers)
    return None


# ---------- 與 Gazebo 互動 ----------

def _run(cmd, timeout=10):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def wait_for_world(timeout, poll=1.0, log=print):
    deadline = time.monotonic() + timeout
    announced = False
    while True:
        world = choose_world(worlds_from_services(_run(['ign', 'service', '-l']).stdout))
        if world:
            return world
        if time.monotonic() > deadline:
            raise TimeoutError(f'等了 {timeout:.0f} 秒仍沒有 Gazebo 世界（sim 容器的 world.launch.py 有啟動嗎？）')
        if not announced:
            log('等待 Gazebo 世界啟動中…')
            announced = True
        time.sleep(poll)


def list_models():
    return models_from_list(_run(['ign', 'model', '--list']).stdout)


def wait_until(condition, timeout, poll=0.2):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        time.sleep(poll)
    return True


def stop_and_move(world, name, x, y, yaw, log=print):
    """已有同名車（前一次車子系統停止後留下的車體）：先停下，再移回出生點。"""
    log(f'世界中已有 {name}（前一次車子系統停止後留下的車體），停下並移回出生點')
    # 空的 Twist = 全部為 0；DiffDrive 會一直執行最後一筆指令，不先停下車子會接著跑
    _run(['ign', 'topic', '-t', f'/{name}/cmd_vel_gz', '-m', 'ignition.msgs.Twist', '-p', ''])
    _run(['ign', 'service', '-s', f'/world/{world}/set_pose',
          '--reqtype', 'ignition.msgs.Pose', '--reptype', 'ignition.msgs.Boolean',
          '--timeout', '3000', '--req', set_pose_request(name, x, y, yaw)])

    def arrived():
        pos = position_from_pose_output(_run(['ign', 'model', '-m', name, '-p']).stdout)
        return pos is not None and math.hypot(pos[0] - x, pos[1] - y) < 0.05

    if not wait_until(arrived, timeout=5):
        raise RuntimeError(f'無法把 {name} 移回 ({x}, {y})')


def spawn(world, name, urdf_text, x, y, yaw, attempts=5, log=print):
    # 用 -string 把 URDF「內容」經 Gazebo transport 送過去，不能用 -file：
    # -file 只傳路徑，Gazebo 在 sim 容器裡讀檔，而這個檔案在 robot 容器（兩邊檔案系統不同）
    command = ['ros2', 'run', 'ros_gz_sim', 'create', '-world', world, '-name', name,
               '-string', urdf_text, '-x', str(x), '-y', str(y), '-z', '0.0', '-Y', str(yaw)]
    for attempt in range(1, attempts + 1):
        _run(command, timeout=30)
        # create 回報 OK 不代表真的生成（世界還沒準備好時要求會被丟掉，但仍回 OK）
        if wait_until(lambda: name in list_models(), timeout=5):
            return
        log(f'第 {attempt} 次生成後沒看到 {name}，重試')
    raise RuntimeError(f'嘗試 {attempts} 次仍無法生成 {name}')


def main(argv=None):
    parser = argparse.ArgumentParser(description='把車輛放進 Gazebo 世界（先移除同名舊車）')
    parser.add_argument('--robot-id', required=True)
    parser.add_argument('--x', type=float, default=0.0)
    parser.add_argument('--y', type=float, default=0.0)
    parser.add_argument('--yaw', type=float, default=0.0)
    parser.add_argument('--timeout', type=float, default=60.0, help='等待世界出現的秒數')
    args, _ = parser.parse_known_args(argv)   # 忽略 launch 附加的 --ros-args

    def log(msg):
        print(f'[spawn {args.robot_id}] {msg}', flush=True)

    try:
        from ament_index_python.packages import get_package_share_directory
        import xacro
        xacro_file = f'{get_package_share_directory("amr_description")}/urdf/amr.urdf.xacro'
        urdf = xacro.process_file(xacro_file, mappings={'robot_id': args.robot_id}).toxml()

        world = wait_for_world(args.timeout, log=log)
        if args.robot_id in list_models():
            stop_and_move(world, args.robot_id, args.x, args.y, args.yaw, log=log)
        else:
            spawn(world, args.robot_id, urdf, args.x, args.y, args.yaw, log=log)
    except (RuntimeError, TimeoutError, subprocess.TimeoutExpired) as e:
        log(f'錯誤：{e}')
        return 1
    log(f'已放進世界 {world}：({args.x}, {args.y})，yaw={args.yaw}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
