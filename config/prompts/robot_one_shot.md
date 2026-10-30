Write ONE complete straight-line Python program for the supplied robot task.
There is one model call only: no later correction or execution feedback.
Return only JSON: {"code":"...","done":true}. No message or Markdown.

robot already exists. Allowed: assignments, lists/tuples, indexing, numeric
+ - * /, and these calls:
robot.position(name) -> [x,y,z]: object centre; use "tcp" for the tool centre.
robot.move_to([x,y,z]): absolute TCP move; waits until finished.
robot.jog(axis, distance): relative to measured TCP; axis "x", "y" or "z".
robot.gripper(closed=True): close fingers; closed=False opens; waits.
robot.step(seconds): advance physics within the supplied wait budgets.
No imports, print, function definitions, loops, if statements or docstrings.

All motion commands move the TCP, not an object directly.
WORLD units are metres: right +X, forward +Y, up +Z.
TCP is between the fingertips. Objects move only through physical contact.
To grasp, lower the open gripper to the object centre before closing.
Object sizes are full side lengths. Use current positions for object tasks.
Table surface is z=0. For pick-and-place, use z=0.24 m for horizontal transport.
After placing, release the object and move the TCP clear.
TCP bounds: x 0.20..0.60, y -0.30..0.30, z 0.01..0.45.
Stay inside the supplied call and wait budgets.
