robot.move_to([0.38937, -0.121352, 0.019957])  # Move to red cube center to grasp
robot.gripper(closed=True)  # Close gripper to pick up red cube
robot.move_to([0.408124, 0.126165, 0.059957])  # Move to top of blue cube to release
robot.gripper(closed=False)  # Open gripper to release red cube
