robot.move_to([0.3, -0.15, 0.24]); robot.gripper(closed=True); robot.step(1.0); robot.move_to([0.3, -0.15, 0.15]); robot.gripper(closed=False); robot.step(1.0)
