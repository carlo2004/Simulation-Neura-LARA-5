# Locate red cube centre
red_centre = [0.402435, -0.129157, 0.019957]
# Close gripper and grasp red cube at its centre
robot.gripper(closed=True)
robot.move_to(red_centre)
# Lift red cube slightly above blue cube top; blue top at z = blue_centre_z + size/2 = 0.019957 + 0.02 = 0.039957
# Choose height ~0.06 m to clear table
target_z = 0.06
target_x = (red_centre[0] + blue_centre[0]) / 2  # approximate middle
target_y = (red_centre[1] + blue_centre[1]) / 2
# Move horizontally to above blue cube centre while keeping z ~target_z
# Use jog for x and y relative moves
# First jog in x to target_x, then y to target_y; small step approach
dx = target_x - robot.position("tcp")[0]
dy = target_y - robot.position("tcp")[1]
# Jog x by dx, then y by dy; keep z constant at current (already ~target_z after move_to?)
robot.jog("x", dx)
robot.jog("y", dy)
# Lower to contact blue cube top
blue_centre = [0.413958, 0.132719, 0.019957]
blue_half = 0.02
target_lower_z = blue_centre[2] + blue_half  # ~0.039957
robot.jog("z", target_lower_z - robot.position("tcp")[2])
# Open gripper to release
robot.gripper(closed=False)
