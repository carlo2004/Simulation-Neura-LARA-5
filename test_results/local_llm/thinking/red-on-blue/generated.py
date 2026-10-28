red_pos = robot.position("red")
blue_pos = robot.position("blue")
red_center = [red_pos[0], red_pos[1], 0.24]
blue_center = [blue_pos[0], blue_pos[1], 0.24]
robot.move_to(red_center)
robot.gripper(closed=True)
robot.move_to(blue_center)
robot.gripper(closed=False)
robot.step(1)
robot.move_to([0.5, 0, 0.4])
