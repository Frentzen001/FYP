#!/usr/bin/env bash
set -euo pipefail

set +u
source /opt/ros/humble/setup.bash
set -u
exec ros2 topic echo /eye_expression std_msgs/msg/Int32
