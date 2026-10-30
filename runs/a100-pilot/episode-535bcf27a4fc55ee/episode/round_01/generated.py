import robot

# Get current TCP position
tcp = robot.position('tcp')
red_pos = robot.position('red')
blue_pos = robot.position('blue')

# Calculate target height for lifting (above table, e.g., 0.24m)
height = 0.24

# Move to red cube center at elevated height
target_red = [red_pos[0], red_pos[1], height]
robot.move_to(target_red)

# Close gripper to grasp red cube
robot.gripper(closed=True)

# Move to blue cube center at elevated height
target_blue = [blue_pos[0], blue_pos[1], height]
robot.move_to(target_blue)

# Place red cube on top of blue cube (gripper stays, then we need to release? 
# Wait, the instruction says 'Staple', which usually implies holding or stacking. 
# In this context, placing one cube on another typically means moving it there and keeping it there 
# until the task is done. However, standard protocol often requires releasing unless specified 'hold'. 
# Given 'Staple' might imply a connection, but with simple cubes, we just stack them.
# Let's assume stacking by placing and then maybe holding or just leaving it? 
# Re-reading: 'Finish with the object released and the tool moved clear of the stack.'
# So we must release and move away.

# Place red cube on blue cube (at blue's position)
robot.move_to(target_blue)

# Open gripper to release
robot.gripper(closed=False)

# Move tool clear of the stack (e.g., 0.1m higher or to the side)
clear_pos = [tcp[0], tcp[1] + 0.1, height + 0.05]
robot.move_to(clear_pos)
