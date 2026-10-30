robot.gripper(closed=False)
red_pos = robot.position('red')
blue_pos = robot.position('blue')
# lift red cube a bit above table
robot.jog('z', 0.03)
# move tcp to red cube centre
robot.move_to(red_pos)
robot.gripper(closed=True)
# move horizontally over blue cube centre while holding red
robot.jog('x', blue_pos[0] - red_pos[0])
# lower to place on top of blue
robot.jog('z', -0.02)
robot.gripper(closed=False)
