tcp = robot.position("tcp")
x, y, z = tcp[0], tcp[1], tcp[2]
robot.move_to([x + 0.05, y, z])
