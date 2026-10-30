tcp = robot.position("tcp")
x = tcp[0] + 0.05
y = tcp[1]
z = tcp[2]
robot.move_to([x, y, z])
