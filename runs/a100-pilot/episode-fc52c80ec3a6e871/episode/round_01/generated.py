import time

# Get current positions of objects
red_tcp = robot.position('red')
blue_tcp = robot.position('blue')
print(f"Red cube TCP: {red_tcp}")
print(f"Blue cube TCP: {blue_tcp}")

# Close gripper to grasp the red cube
robot.gripper(closed=True)

# Move red cube so its TCP aligns with blue cube center
# The red cube is at [0.414372, -0.121311, 0.019957], blue at [0.406565, 0.127047, 0.019957]
# We need to move the red cube horizontally to align with blue
# Target: move red TCP to be directly above/on top of blue center
# Since they are close, we can use a small jog or move_to

# Calculate displacement needed (in world coordinates)
dx = blue_tcp[0] - red_tcp[0]
dy = blue_tcp[1] - red_tcp[1]
print(f"Displacement: dx={dx}, dy={dy}")

# Use jog to move the tool center relative to current TCP
# Move in x and y directions to align with blue cube
robot.jog('x', dx)  # Move along X axis
robot.jog('y', dy)  # Then move along Y axis

# Now open gripper to release/place on top of blue cube
robot.gripper(closed=False)

print("Stapling complete: red cube placed on blue cube")
