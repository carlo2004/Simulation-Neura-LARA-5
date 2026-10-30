import time

# Step 1: Close gripper on the red cube to grasp it
robot.gripper(closed=True)

# Step 2: Move the TCP of the red cube to be above the blue cube
# The blue cube is at z=0.019957, so we move the red cube higher (e.g., z=0.35)
# We need to move from current TCP position [0.4, -0.12, 0.26] to a position above the blue cube
# Let's target: x=0.41, y=-0.11, z=0.40 (above the blue cube at z≈0.02)
robot.move_to([0.41, -0.11, 0.40])

# Step 3: Open gripper to release the red cube onto the blue cube
robot.gripper(closed=False)
