import time

# Get current positions of both cubes
red_tcp = robot.position("red")
blue_tcp = robot.position("blue")
print(f"Red cube TCP: {red_tcp}")
print(f"Blue cube TCP: {blue_tcp}")

# The red cube needs to be placed on top of the blue cube.
# First, grasp the blue cube (it's already near the target position).
robot.gripper(closed=True)  # Close gripper around blue cube

# Move the blue cube slightly above/on top of where the red is
# We need to move it so its center is above the red cube.
# The red cube center: [0.389445, -0.116521, 0.019957]
# Let's move blue up by a small amount (e.g., 0.02m) and slightly adjust x/y
blue_new_pos = [
    blue_tcp[0] + 0.01,   # shift right
    blue_tcp[1] - 0.05,   # shift left
    blue_tcp[2] + 0.03    # move up a bit
]
print(f"Moving blue to: {blue_new_pos}")
robot.move_to(blue_new_pos)

# Close the gripper on red cube (now we have blue in place, close around red)
robot.gripper(closed=True)  # Close gripper around red cube
print("Stapled red cube onto blue cube.")
