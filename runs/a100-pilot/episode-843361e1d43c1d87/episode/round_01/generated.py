# Close gripper to grasp the red cube
robot.gripper(closed=True)

# Lift the red cube slightly above the table (z ≈ 0.1 m) while keeping x,y over the cube
# Use jog to increase z by about 0.08 m (from current z 0.26 down to 0.18? Wait we need to lift)
# Actually current TCP at z=0.26 is already above red cube (cube centre 0.02). So maybe just move up a bit?
# Safer: move TCP to red cube centre with a small height offset, e.g., z = 0.30 (cube top at ~0.04+0.02=0.06? Actually cube size 0.04, centre 0.02, top at 0.06. So z=0.30 is well above.
# Let's compute target position: red cube centre [0.38937, -0.121352, 0.019957]. Want TCP at cube centre? Usually to grasp, TCP should be at cube centre with a small downward offset? The gripper is below TCP? They said "keeping the gripper vertically downward". So TCP at cube centre works.
# Move to red centre with z = 0.30 (clear above).
target_red = [0.38937, -0.121352, 0.30]
robot.move_to(target_red)

# Now move horizontally to above blue cube centre with same height
# Blue cube centre [0.408124, 0.126165, 0.019957]. Use z = 0.30 as well.
target_blue = [0.408124, 0.126165, 0.30]
robot.move_to(target_blue)

# Lower to place on top of blue cube: need TCP at blue cube centre plus half cube height? Actually to place red on top of blue, TCP should be above blue cube centre at a height equal to blue cube top + small clearance. Cube side 0.04, so half height 0.02. Blue top z = centre_z + 0.02 = 0.019957+0.02 ≈ 0.039957. Add a small clearance, say 0.01 m above top. So target place z ≈ 0.05 m.
target_place = [0.408124, 0.126165, 0.05]
robot.move_to(target_place)

# Release gripper
robot.gripper(closed=False)

# Move TCP away to clear stack (e.g., to [0.4, 0.0, 0.2])
robot.move_to([0.4, 0.0, 0.2])
