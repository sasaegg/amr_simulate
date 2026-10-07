# 08 場景產生器（TDD）

檔案：[`gen_world.py`](../../ros_ws/src/amr_worlds/amr_worlds/gen_world.py)、[`test_gen_world.py`](../../ros_ws/src/amr_worlds/test/test_gen_world.py)、[`warehouse_small.yaml`](../../ros_ws/src/amr_worlds/scenes/warehouse_small.yaml)、[`README.md`](../../ros_ws/src/amr_worlds/README.md)

## 為什麼要做

倉庫地圖要能用文字編輯、版本控制、比對差異，所以用 YAML 描述場景，再由程式轉成 Gazebo 的 SDF。產生器是整個專案最容易寫單元測試的部分（純 Python、不依賴 ROS），所以用 TDD 開發。

## TDD 流程

```
紅：先寫測試描述「應該做到什麼」→ 執行 → 失敗
綠：寫剛好讓測試通過的程式 → 執行 → 通過
重構：在測試保護下整理程式
```

**為什麼要先看到失敗**：證明測試真的在檢查東西。程式還沒寫測試就通過，代表測試寫錯了。

本專案的實際過程：

| 階段 | task | 結果 |
|---|---|---|
| 先寫測試，import 不存在的模組 | 3.2 | `ModuleNotFoundError`（collection error，0 個測試被執行） |
| 建立 `NotImplementedError` 空殼 | 3.2 | 每個測試各自執行、各自失敗（`3 failed` → `10 failed`） |
| 補驗證錯誤與 main 的測試 | 3.3 | `57 failed`，全部是 `NotImplementedError` |
| 實作 `wall_pose`（自己寫） | 3.4 | `3 passed` |
| 實作 `validate`、`generate` | 3.4 | `49 passed, 8 failed`（剩 main） |
| 實作 `main` | 3.4 | `57 passed` |
| 發現輸出檔權限 600 → 先補測試（`1 failed`）再修 | 3.4 | `58 passed` |

**空殼用 `raise NotImplementedError` 而不是 `pass`**：`pass` 會默默回傳 `None`，測試可能因為別的原因失敗甚至意外通過；`NotImplementedError` 讓失敗原因一目了然。

**在沒有 ROS 的環境執行測試**（spec 要求產生器不依賴 ROS）：

```bash
cd /ros_ws/src/amr_worlds
env -i PATH=/usr/bin:/bin python3 -m pytest -q test
```

- `env -i`：清空所有環境變數（沒有 `AMENT_PREFIX_PATH`、`PYTHONPATH`），等於沒 source ROS；只留 `PATH` 才找得到 python3。
- `python3 -m pytest`：以模組方式執行，Python 會把目前目錄加進 import 路徑，才找得到 `./amr_worlds/`。
- `-k wall_pose`：只跑名稱含 `wall_pose` 的測試。

## 介面設計：純邏輯與 I/O 分開

| 函式 | 作用 | 誰寫 |
|---|---|---|
| `wall_pose(start, end)` | 兩端點 → `(cx, cy, length, yaw)` | 自己 |
| `validate(scene)` | 不合法就拋 `SceneError`，訊息指出位置（`shelves[0].pos`） | Claude |
| `generate(scene) -> str` | 已驗證的 dict → SDF 字串（純函式） | Claude |
| `main(argv) -> int` | 命令列：讀 YAML → validate → generate → 原子寫檔；回傳結束碼 | Claude |

只有 `main` 碰檔案；其他三個直接給 dict、檢查回傳值，測試又快又簡單。
公開介面沒有底線；內部工具函式以 `_` 開頭（`_number`、`_corners`…）——Python 慣例，表示「內部用，可以隨時改」。測試只針對公開介面寫，所以內部可以自由重構。

## pytest 技巧

| 技巧 | 用法 |
|---|---|
| `assert` | 不成立就失敗；pytest 會自動顯示兩邊的實際值 |
| `pytest.approx` | 浮點數比較（`0.1 + 0.2 == 0.3` 是 False）。預設相對誤差 1e-6、絕對誤差 1e-12（期望值是 0 時靠這個）；對 tuple／list 逐元素比較 |
| `@pytest.fixture` | 「準備測試材料的函式」。測試參數與 fixture 同名，pytest 自動呼叫並注入（依賴注入）；**每個測試拿到全新的一份**，彼此不干擾。可設 `scope`、用 `yield` 收尾、組合其他 fixture |
| 內建 fixture | `tmp_path`（全新暫存資料夾）、`capsys`（攔截 stdout／stderr） |
| `pytest.raises(SceneError) as excinfo` | 預期拋出指定例外；**其他類型的例外不會被攔下**（所以 NotImplementedError 讓它失敗、bug 造成的 KeyError 也不會被誤判為正確拒絕） |
| `@pytest.mark.parametrize` | 同一測試套用多組輸入，每組是獨立的測試；可搭配 `lambda` 描述「如何把場景改壞」 |
| `assert x, 訊息` | 在迴圈中指出是哪一個出錯 |

**為什麼用 `str(excinfo.value)` 檢查訊息、不用 `raises(match=...)`**：`match` 是正規表示式，`shelves[0]` 的中括號要跳脫。

## 測試設計重點

- **先確認正確輸入不被誤判**（`test_validate_accepts_sample_scene`）：否則「永遠拋錯」的 validate 也能通過所有錯誤測試。
- **邊界值分析**：出生點距 box 0.2 m 要擋、0.4 m 要過——只測一側抓不到「太嚴格」的 bug。
- **`True` 當數字**：`bool` 是 `int` 的子類別，`isinstance(True, int)` 為 True，要明確排除。
- **`name: '../evil'`**：name 會當檔名，允許 `../` 就是路徑穿越漏洞；只允許英數字、底線、連字號。
- **輸出檔名取自 `name`**：測試故意把 YAML 檔取名 `any_file_name.yaml`，證明不是巧合。
- **ElementTree 的陷阱**：沒有子元素的 Element 布林值是 False，所以要寫 `find(...) is not None`。

## 實作重點

**`wall_pose`**

```python
dx, dy = x2 - x1, y2 - y1
cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
length = math.hypot(dx, dy)     # hypotenuse：斜邊 √(dx²+dy²)
yaw = math.atan2(dy, dx)        # arc tangent 2 參數：看正負號得到完整方向、dx=0 也沒問題
return cx, cy, length, yaw
```
`atan(dy/dx)` 不行：dx = 0 會除以零；只回傳 ±90°，分不出方向。
參數用 `start, end`：`from` 是 Python 保留字。
一行寫兩個賦值要用 tuple 拆包 `a, b = x, y`，`a = x, b = y` 是 SyntaxError。

**`validate`**
- `_number`／`_vector`／`_field` 帶著 `where` 字串，出錯時放進訊息開頭。
- 每個元素轉成佔地形狀：牆／貨架／box → 旋轉矩形 `('rect', cx, cy, 半長, 半寬, yaw)`；圓柱 → `('circle', cx, cy, r)`。
- **點到旋轉矩形的距離**：先把點轉到矩形自己的座標系（中心為原點、長邊沿 x），再算超出半長／半寬的部分。「轉到物體自己的座標系再計算」是機器人學常用技巧（之後的 TF 也是）。
- `_corners`：矩形座標系 → 世界座標系（旋轉矩陣 + 平移），方向與 `_distance` 相反。
- 出界：牆看兩端點（端點常貼著邊界，算厚度會誤判），貨架／box 看四角。
- `_` 當變數名：「這個值不需要」（`x, y, _ = pose`）。

**`generate`**
- `_fmt`：固定 6 位小數再去尾 0（`1.5707963…` → `1.570796`、`5.0` → `5`）——**輸出可重現**的關鍵。
- `_link`：同一份幾何同時產生 collision（物理、光達）與 visual（外觀）。
- link = 一塊剛體（visual／collision／inertial）；joint 連接 link；一群 link + joint = model。整個倉庫是一個 `static` model（物理引擎不計算受力）。
- box 以中心定位，所以 z = 高度／2；地板 0.1 m 厚、中心 z = -0.05，頂面在 z = 0。
- 外牆放在地板外側、內側面貼齊邊界，可用空間剛好是 `size`；南北牆長度 = 寬 + 2 × 厚度，封住四角。

**`main`**
- `argparse`：位置參數必填、`--out-dir` 選填（取值用 `args.out_dir`）；`--help` 自動產生；`parse_args(argv)` 在 argv 為 None 時讀真正的命令列，測試時傳 list。
- 只捕捉預期錯誤 `(OSError, yaml.YAMLError, SceneError)`：印到 stderr、回傳 1。真正的 bug 不被吞掉。
- 所有錯誤都發生在寫檔之前 → 失敗時不會留下或改動檔案。
- `resolve()` 先轉絕對路徑，`parent.parent` 才正確。
- **原子寫入**：先寫同資料夾的暫存檔，再 `os.replace` 換上。同一檔案系統上 `replace` 是原子操作，其他程式只會看到完整的舊版或新版，不會看到寫一半的檔案（所以暫存檔必須 `dir=out_dir`）。
- `mkstemp` 建立的檔案權限是 600（安全考量），改名後保留 → 加 `os.chmod(tmp, 0o644)`。資料檔用 644，只有可執行檔與資料夾用 755（資料夾的 x 是「可以進入」）。更嚴謹可用 `0o666 & ~umask`。
- `yaml.safe_load`：只建立基本型別；`yaml.load` 讀不信任的檔案可能執行任意程式碼。
- `if __name__ == '__main__': sys.exit(main())`：直接執行（`python3 -m amr_worlds.gen_world`）時才呼叫 main；被 import 時不執行。
- `setup.py` 註冊 `'gen_world = amr_worlds.gen_world:main'`，**改 entry_points 要重新 build**。

## 範例場景 warehouse_small

20 × 15 m；兩排貨架（y = 8、11，走道 2.4 m，含 spec 指定的 `[3, 8]`）；x = 12 的隔間牆（南側留 6 m 通道）；東區 y = 9 的短牆（讓地圖不對稱，利於 SLAM 定位）；旋轉的 box、兩根圓柱；出生點 (1, 1)。共 17 個 link（地板 1 + 外牆 4 + 內牆 2 + 貨架 6 + 障礙物 4）。

設計考量：走道 ≥ 1.5 m（車寬 0.4 m 加上 Nav2 的膨脹區）、不要太對稱（SLAM 靠特徵定位）、出生點周圍空曠。

## 怎麼驗證（2026-10-08 實測）

```bash
# 容器內
env -i PATH=/usr/bin:/bin python3 -m pytest -q test            # 58 passed
ros2 run amr_worlds gen_world /ros_ws/src/amr_worlds/scenes/warehouse_small.yaml
grep -c '<link ' /ros_ws/src/amr_worlds/worlds/warehouse_small.sdf   # 17
ign gazebo /ros_ws/src/amr_worlds/worlds/warehouse_small.sdf    # 外牆封閉、貨架與障礙物位置正確、無 [Err]
cd /ros_ws && colcon build --symlink-install
ls -l install/amr_worlds/share/amr_worlds/{worlds,scenes}/       # 新檔案以 symlink 安裝
# 依 README 重新產生後，主機上 git diff --stat 無輸出（可重現）
```

`ign gazebo` 的兩種警告無害：
- `XDG_RUNTIME_DIR not set`：容器沒經過登入流程，Qt 自動改用 `/tmp/runtime-ros`。
- `libEGL warning: egl: failed to create dri2 screen`：GLVND 依序嘗試 EGL 廠商，Mesa 試著用 Toolkit 注入的 NVIDIA DRM 裝置（`/dev/dri/card2`）失敗後放棄，接著 NVIDIA 成功。可用 `__EGL_VENDOR_LIBRARY_FILENAMES` 只留 NVIDIA 來消除，但會與 CPU 模式衝突，所以不設。

## 面試追問

**Q：什麼是 TDD？為什麼要先看到測試失敗？**
A：先寫測試定義行為，看它失敗，再寫剛好讓它通過的程式，最後重構。先失敗是為了證明測試真的在檢查東西。我實際的流程是 57 個測試全紅，依序實作 wall_pose、validate／generate、main，一批批變綠。

**Q：怎麼讓程式好測試？**
A：純邏輯和 I/O 分開。validate、generate 是純函式，直接給 dict 檢查回傳值；只有 main 碰檔案，用 tmp_path 測。

**Q：pytest fixture 是什麼？跟 class 有什麼不同？**
A：準備測試材料的工廠函式，由 pytest 依參數名稱注入，每個測試拿到新的一份。比自己 new 一個 class 多了 scope 控制、yield 收尾、組合其他 fixture。

**Q：為什麼不能直接用 == 比較浮點數？**
A：二進位浮點數有捨入誤差（0.1+0.2 ≠ 0.3），要用容許誤差比較，pytest 用 `approx`。

**Q：怎麼避免寫檔寫到一半產生壞檔？**
A：原子寫入：寫到同資料夾的暫存檔再 `os.replace`。同一檔案系統上 rename 是原子的。

**Q：發現 bug 時你怎麼處理？**
A：先寫一個會因為這個 bug 失敗的測試、確認它紅，再修到綠。例如輸出檔權限是 600 的問題。這個測試之後就成為回歸測試。

**Q：為什麼用 atan2 不用 atan？**
A：atan2 看 dy、dx 的正負號，能回傳完整 ±180° 的方向，dx = 0 也能算；atan(dy/dx) 會除以零且分不出相反方向。

**Q：輸出怎麼保證可重現？為什麼重要？**
A：元素依 YAML 順序輸出、數字用固定格式。可重現才能把產物放進版控，用 git diff 看出每次修改真正改了什麼。

## 踩坑紀錄

- `dx = x2 - x1,  dy = y2 - y1`：被解析成連續賦值 → `SyntaxError: cannot assign to expression`；整個測試檔無法載入，所有測試都變 error。改成兩行或 tuple 拆包。
- 函式沒寫 `return` → 回傳 None → `cannot unpack non-iterable NoneType object`。
- `mkstemp` 建出的檔案權限 600，`os.replace` 後保留 → 補測試再加 `chmod`。
- `bash -c` 非互動 shell 不讀 `.bashrc` → `ros2: command not found`；要用 `bash -ic` 或 exec.sh 開互動 shell。
- README 寫了 `python3 -m amr_worlds.gen_world` 但檔案沒有 `if __name__ == '__main__'` → 執行了什麼都不做。文件裡的每個指令都要實際跑過一次。
- 小實驗把 `[3, 8]` 改成 `[2, 8]` 後忘了改回來——spec 情境依賴這個座標，commit 前要再檢查一次。
