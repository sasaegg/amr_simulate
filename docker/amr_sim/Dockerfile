# AMR 模擬共用映像：ROS 2 Humble + Gazebo Fortress（ros_gz）
# GPU 驅動不在映像內：由 NVIDIA Container Toolkit 於容器啟動時注入。

FROM osrf/ros:humble-desktop

# 只在建置期間有效（ARG 不會留在執行中的容器環境變數裡），避免 apt 跳出互動式問題。
ARG DEBIAN_FRONTEND=noninteractive

# 套件安裝：update 與 install 必須在同一個 RUN（同一層），清除 apt 清單也必須在同一層才會真的縮小映像。
# fonts-noto-cjk：中日韓字型。沒有它，RViz 建圖面板等 Qt 介面的中文會變成方塊
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
        mesa-utils \
        python3-pip \
        python3-pytest \
        python3-yaml \
        ros-humble-nav2-bringup \
        ros-humble-navigation2 \
        ros-humble-ros-gz \
        ros-humble-slam-toolbox \
        ros-humble-teleop-twist-keyboard \
        ros-humble-xacro \
        sudo \
        x11-apps \
    && rm -rf /var/lib/apt/lists/*

# 中控後端（amr_server）：FastAPI + uvicorn。apt 的 python3-fastapi 是 0.78（Pydantic v1），太舊，改用 pip 並釘死版本。
# 不用 uvicorn[standard]：它會拉 PyYAML 等，和 apt 裝的版本衝突（pip 無法移除 apt 裝的套件）；WebSocket 只需要 websockets。
# websockets 17 起需要 Python 3.11，映像是 3.10，所以用 16.x。httpx：FastAPI 測試用的 TestClient 需要。
RUN pip install --no-cache-dir \
        fastapi==0.142.4 \
        uvicorn==0.54.0 \
        websockets==16.1.1 \
        httpx==0.28.1

# 上面的 anyio（starlette 的相依）會自動註冊一個 pytest 外掛，它需要 pytest 7 以上；
# apt 的 pytest 是 6.2，載入外掛時就崩潰，連其他套件的 colcon test 也一起壞掉。我們不需要這個外掛，停用它。
ENV PYTEST_ADDOPTS="-p no:anyio"

# 前端（web/）建置與開發用 Node.js 24 LTS：Ubuntu 22.04 apt 的 Node 是 12，Vite 需要 18 以上。
# 從 nodejs.org 下載官方 tarball，SHA256 寫死在這裡比對（版本與雜湊取自官方 SHASUMS256.txt），下載內容被換掉就會建置失敗。
ARG NODE_VERSION=24.21.0
ARG NODE_SHA256=fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6
RUN curl -fsSLo /tmp/node.tar.xz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
    && echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum -c - \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 --no-same-owner \
    && rm /tmp/node.tar.xz

# 建立與主機相同 UID/GID 的使用者：掛載進來的 ros_ws 中產生的 build/、install/ 才會屬於主機使用者。
# 預設 1000；compose 以 ${USER_UID:-1000} 傳入，docker/build.sh 會自動帶入 id -u / id -g。
ARG USERNAME=ros
ARG USER_UID=1000
ARG USER_GID=1000
RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd --uid ${USER_UID} --gid ${USER_GID} --create-home --shell /bin/bash ${USERNAME} \
    && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME}

USER ${USERNAME}
WORKDIR /ros_ws

# docker exec 不經過 entrypoint，互動式 shell 只會讀 ~/.bashrc：在這裡也 source ROS 與工作區
RUN printf '%s\n' \
        "source /opt/ros/${ROS_DISTRO}/setup.bash" \
        "[ -f /ros_ws/install/setup.bash ] && source /ros_ws/install/setup.bash" \
        >> ~/.bashrc


COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
