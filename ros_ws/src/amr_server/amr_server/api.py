"""HTTP／WebSocket API（FastAPI）。

只認識 bridge.RobotBridge 介面，不碰 rclpy：正式執行時 main.py 傳入 ROS 版本的 bridge，測試時傳入假的。
所有座標都是地圖座標系 map（公尺、弧度）。
"""

import asyncio
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from amr_server.bridge import NavigationUnavailable, NoActiveGoal
from amr_server.geometry import in_map_bounds

NOT_BUILT_MESSAGE = (
    '網頁尚未建置。在 server 容器執行：\n'
    '  cd /web && npm install && npm run build\n'
    '開發時也可以用 npm run dev（http://localhost:5173）。API 在 /api/ 照常運作。\n'
)


class PoseIn(BaseModel):
    """派車與初始位姿的輸入。allow_inf_nan=False：NaN、無限大直接 422。"""

    model_config = ConfigDict(allow_inf_nan=False)

    x: float
    y: float
    yaw: float


def pose_json(pose):
    return None if pose is None else {'x': pose.x, 'y': pose.y, 'yaw': pose.yaw}


def state_json(state):
    return {
        'pose': pose_json(state.pose),
        'goal': pose_json(state.goal),
        'status': state.status,
        'message': state.message,
        'distance_remaining': state.distance_remaining,
        'plan': [[x, y] for x, y in state.plan],
        'map_version': state.map_version,
        'map_ready': state.map_ready,
        'nav_ready': state.nav_ready,
    }


def create_app(bridges, web_dir=None, push_period=0.1):
    """bridges：{車輛 id: RobotBridge}；web_dir：建置好的網頁（npm run build 的 dist/）。"""
    app = FastAPI(title='AMR 中控')

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # 預設的 422 會把原始輸入放回回應裡；輸入是 NaN 時 JSON 編不出來、反而變成 500。
        # 改成一行可讀的字串（和其他錯誤一樣是 {"detail": "..."}，前端直接顯示）
        reasons = []
        for error in exc.errors():
            field = '.'.join(str(p) for p in error['loc'] if p != 'body') or '內容'
            reasons.append(f'{field}：{error["msg"]}')
        return JSONResponse({'detail': '輸入不正確：' + '；'.join(reasons)}, status_code=422)

    def bridge_of(robot_id):
        if robot_id not in bridges:
            raise HTTPException(404, f'沒有車輛 {robot_id}（管理中的車輛：{", ".join(bridges)}）')
        return bridges[robot_id]

    def require_map(robot_id, bridge):
        info = bridge.map_info()
        if info is None:
            raise HTTPException(503, f'尚未收到 {robot_id} 的地圖（車上的導航有在執行嗎？）')
        return info

    def require_in_map(robot_id, bridge, pose, what):
        info = require_map(robot_id, bridge)
        if not in_map_bounds(info, pose.x, pose.y):
            max_x = info.origin_x + info.width * info.resolution
            max_y = info.origin_y + info.height * info.resolution
            raise HTTPException(
                422, f'{what} ({pose.x:.2f}, {pose.y:.2f}) 在地圖範圍外'
                     f'（x {info.origin_x:.2f}～{max_x:.2f}、y {info.origin_y:.2f}～{max_y:.2f}）')

    # 會呼叫 bridge 的路由都用一般 def：FastAPI 把它們放到執行緒池，等待（最多 0.5 s）時不會卡住事件迴圈

    @app.get('/api/robots')
    def list_robots():
        result = []
        for robot_id, bridge in bridges.items():
            state = bridge.state()
            result.append({'id': robot_id, 'map_ready': state.map_ready,
                           'pose_ready': state.pose is not None, 'nav_ready': state.nav_ready})
        return result

    @app.get('/api/robots/{robot_id}/map')
    def get_map(robot_id: str):
        bridge = bridge_of(robot_id)
        return asdict(require_map(robot_id, bridge))

    @app.get('/api/robots/{robot_id}/map.png')
    def get_map_png(robot_id: str):
        bridge = bridge_of(robot_id)
        png = bridge.map_png()
        if png is None:
            raise HTTPException(503, f'尚未收到 {robot_id} 的地圖（車上的導航有在執行嗎？）')
        # 前端以 ?v=<版本> 區分新舊地圖；no-cache 讓瀏覽器每次都和後端確認
        return Response(png, media_type='image/png', headers={'Cache-Control': 'no-cache'})

    @app.post('/api/robots/{robot_id}/goal', status_code=202)
    def send_goal(robot_id: str, pose: PoseIn):
        bridge = bridge_of(robot_id)
        require_in_map(robot_id, bridge, pose, '目標')
        try:
            bridge.send_goal(pose.x, pose.y, pose.yaw)
        except NavigationUnavailable as e:
            raise HTTPException(503, str(e))
        return {'detail': '已送出目標'}

    @app.delete('/api/robots/{robot_id}/goal', status_code=202)
    def cancel_goal(robot_id: str):
        bridge = bridge_of(robot_id)
        try:
            bridge.cancel()
        except NoActiveGoal as e:
            raise HTTPException(409, str(e))
        return {'detail': '已要求取消'}

    @app.post('/api/robots/{robot_id}/initial_pose', status_code=202)
    def set_initial_pose(robot_id: str, pose: PoseIn):
        bridge = bridge_of(robot_id)
        require_in_map(robot_id, bridge, pose, '初始位姿')
        bridge.set_initial_pose(pose.x, pose.y, pose.yaw)
        return {'detail': '已送出初始位姿'}

    @app.websocket('/api/ws')
    async def push_state(websocket: WebSocket):
        # 連上後定期推送所有車輛的狀態；用戶端斷線就結束這個迴圈
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(
                    {'robots': {robot_id: state_json(b.state()) for robot_id, b in bridges.items()}})
                await asyncio.sleep(push_period)
        except WebSocketDisconnect:
            pass

    # 網頁：放在所有 /api 路由之後掛載，否則 "/" 會先攔下 /api 的請求
    if web_dir and (Path(web_dir) / 'index.html').is_file():
        app.mount('/', StaticFiles(directory=web_dir, html=True), name='web')
    else:
        @app.get('/', response_class=PlainTextResponse)
        def not_built():
            return NOT_BUILT_MESSAGE

    return app
