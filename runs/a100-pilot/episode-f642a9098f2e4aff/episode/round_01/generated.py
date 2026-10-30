import time

# Step 1: Close the gripper on the red cube to grasp it
robot.gripper(closed=True)

# Step 2: Move the red cube so its TCP is above the blue cube
# The red cube center is at [0.38937, -0.121352, 0.019957]
# We need to move it upward (increase z) and slightly adjust x/y to align with blue cube
# Blue cube center: [0.408124, 0.126165, 0.019957]
# Target TCP position above blue cube: around [0.40, 0.13, 0.35] (z should be > 0.02)
red_tcp_target = [0.405, 0.125, 0.35]

robot.move_to(red_tcp_target)

# Step 3: Close the gripper again to secure the red cube on top of the blue cube
robot.gripper(closed=True)
