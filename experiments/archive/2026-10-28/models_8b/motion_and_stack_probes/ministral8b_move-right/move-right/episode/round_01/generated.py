pos = robot.position("tcp")
new_pos = [pos[0] + 0.05, pos[1], pos[2]]
robot.move_to(new_pos)
