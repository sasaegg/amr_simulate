# AMR 模擬共用映像：ROS 2 Humble + Gazebo Fortress（ros_gz）
# GPU 驅動不在映像內：由 NVIDIA Container Toolkit 於容器啟動時注入。

FROM osrf/ros:humble-desktop

# 只在建置期間有效（ARG 不會留在執行中的容器環境變數裡），避免 apt 跳出互動式問題。
ARG DEBIAN_FRONTEND=noninteractive

# 套件安裝：update 與 install 必須在同一個 RUN（同一層），清除 apt 清單也必須在同一層才會真的縮小映像。
RUN apt-get update && apt-get install -y --no-install-recommends \
        mesa-utils \
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
