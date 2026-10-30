red = robot.position("red")
blue = robot.position("blue")
half_h = 0.02
t = 0.04

robot.gripper(closed=False)
robot.move_to([red[0], red[1], 0.24])
robot.gripper(closed=True)
robot.move_to([red[0], red[1], 0.06])
robot.move_to([blue[0], blue[1], blue[2] + t])
robot.gripper(closed=False)
robot.move_to([0.5, -0.1, 0.3])
