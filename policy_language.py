"""A bounded Python subset for generated policies; no eval/exec or general Python access."""
import ast
import math
import operator

METHODS = {'position', 'move_to', 'gripper', 'step'}
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


class PolicyError(ValueError):
    pass


def validate(code):
    if not isinstance(code, str) or len(code) > 16000:
        raise PolicyError('Program must be a string of at most 16000 characters')
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        raise PolicyError(f'Invalid Python on line {error.lineno}: {error.msg}') from None
    if not 1 <= len(tree.body) <= 64 or len(list(ast.walk(tree))) > 1200:
        raise PolicyError('Program must have 1–64 statements and at most 1200 AST nodes')
    allowed = (ast.Module, ast.Assign, ast.Expr, ast.Name, ast.Load, ast.Store, ast.Constant,
               ast.List, ast.Tuple, ast.Subscript, ast.BinOp, ast.Add, ast.Sub, ast.Mult,
               ast.Div, ast.UnaryOp, ast.UAdd, ast.USub, ast.Call, ast.Attribute, ast.keyword)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise PolicyError('Unsupported Python construct: '+type(node).__name__)
        if isinstance(node, ast.Name) and (node.id.startswith('_') or len(node.id) > 40):
            raise PolicyError('Invalid variable name')
        if isinstance(node, ast.Constant):
            if type(node.value) not in (str, int, float, bool):
                raise PolicyError('Only strings, numbers and booleans are allowed')
            if isinstance(node.value, str) and len(node.value) > 64:
                raise PolicyError('String literal too long')
            if type(node.value) in (int, float):
                number(node.value)
        if isinstance(node, ast.Attribute):
            if not isinstance(node.value, ast.Name) or node.value.id != 'robot' or node.attr not in METHODS:
                raise PolicyError('Only the four documented robot methods are accessible')
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Attribute) or node.func.attr not in METHODS:
                raise PolicyError('Only calls to robot.position/move_to/gripper/step are allowed')
            if any(k.arg is None for k in node.keywords):
                raise PolicyError('Argument unpacking is not allowed')
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1:
                raise PolicyError('Use one assignment target')
            targets = node.targets[0].elts if isinstance(node.targets[0], (ast.Tuple, ast.List)) else [node.targets[0]]
            if not all(isinstance(n, ast.Name) and n.id != 'robot' for n in targets):
                raise PolicyError('Assign only local variables; robot cannot be overwritten')
    # Do not allow a method to be stored as a variable or exposed as a value.
    calls = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    if any(isinstance(n, ast.Attribute) and id(n) not in calls for n in ast.walk(tree)):
        raise PolicyError('Robot methods must be called directly')
    return tree


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e6:
        raise PolicyError('Expected a finite number with absolute value at most 1000000')
    return value


class Interpreter:
    def __init__(self, robot):
        self.robot = robot
        self.variables = {}
        self.actions = []
        self.wait_total = 0.

    def expression(self, node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in self.variables:
                raise PolicyError('Undefined variable: '+node.id)
            return self.variables[node.id]
        if isinstance(node, (ast.List, ast.Tuple)):
            if len(node.elts) > 3:
                raise PolicyError('Lists/tuples may have at most three entries')
            values = [self.expression(v) for v in node.elts]
            if any(type(v) not in (str, int, float, bool) for v in values):
                raise PolicyError('Lists/tuples must be flat lists of scalar values')
            return values
        if isinstance(node, ast.Subscript):
            value, index = self.expression(node.value), self.expression(node.slice)
            if not isinstance(value, list) or type(index) is not int or not -len(value) <= index < len(value):
                raise PolicyError('Index a position list with an in-range integer')
            return value[index]
        if isinstance(node, ast.UnaryOp):
            value = number(self.expression(node.operand))
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left, right = number(self.expression(node.left)), number(self.expression(node.right))
            try:
                return number(OPS[type(node.op)](left, right))
            except ZeroDivisionError:
                raise PolicyError('Division by zero') from None
        if isinstance(node, ast.Call):
            return self.call(node.func.attr, [self.expression(a) for a in node.args],
                             {k.arg: self.expression(k.value) for k in node.keywords})
        raise PolicyError('Unsupported expression')

    def call(self, method, args, kwargs):
        if len(self.actions) >= 48:
            raise PolicyError('At most 48 robot API calls are allowed')
        action = dict(method=method, args=args, kwargs=kwargs, time_s=float(self.robot.data.time))
        self.actions.append(action)
        if method == 'position':
            if kwargs or len(args) != 1 or not isinstance(args[0], str):
                raise PolicyError('position expects one object name')
            if args[0] not in self.robot.object_names:
                raise PolicyError('Unknown object: '+args[0])
            result = self.robot.position(args[0]).tolist()
            action['result'] = result
            return result
        if method == 'move_to':
            if kwargs or len(args) != 1 or not isinstance(args[0], list) or len(args[0]) != 3:
                raise PolicyError('move_to expects one three-number position list')
            xyz = [number(v) for v in args[0]]
            try:
                self.robot.validate_tcp(xyz)
            except ValueError as error:
                raise PolicyError(str(error)) from None
            self.robot.move_to(xyz)
        elif method == 'gripper':
            if args and not kwargs and len(args) == 1:
                closed = args[0]
            elif not args and set(kwargs) == {'closed'}:
                closed = kwargs['closed']
            else:
                raise PolicyError('Use gripper(closed=True) or gripper(closed=False)')
            if type(closed) is not bool:
                raise PolicyError('closed must be a boolean')
            self.robot.gripper(closed)
        elif method == 'step':
            if kwargs or len(args) != 1:
                raise PolicyError('step expects one duration in seconds')
            seconds = number(args[0])
            self.wait_total += seconds
            if not 0 <= seconds <= 5 or self.wait_total > 15:
                raise PolicyError('Wait 0–5 seconds per call, at most 15 seconds total')
            self.robot.step(seconds)
        return None

    def run(self, code):
        tree = validate(code)
        for statement in tree.body:
            if isinstance(statement, ast.Expr):
                self.expression(statement.value)
            else:
                value = self.expression(statement.value)
                target = statement.targets[0]
                if isinstance(target, ast.Name):
                    self.variables[target.id] = value
                else:
                    if not isinstance(value, list) or len(value) != len(target.elts):
                        raise PolicyError('Unpacking requires matching list lengths')
                    self.variables.update((n.id, v) for n, v in zip(target.elts, value))
        return self.actions
