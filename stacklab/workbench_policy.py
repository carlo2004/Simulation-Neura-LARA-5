"""Bounded evaluation of the Prompt2Robo Python subset for live model output."""
import ast
from dataclasses import dataclass
import json
import math
import operator
import os
from pathlib import Path

import numpy as np

from stacklab.paths import ROOT
from stacklab.prompt2robo import METHODS

BUILTINS = {fn.__name__: fn for fn in (abs, min, max, len, round, sum, sorted, all, any, int, float, str, bool)}
NUMERIC = {'np.array': np.asarray, 'np.mean': np.mean, 'np.ptp': np.ptp, 'np.sign': np.sign,
           'np.linalg.norm': np.linalg.norm,
           **{'math.' + name: getattr(math, name) for name in ('hypot', 'sqrt', 'sin', 'cos', 'radians', 'degrees')}}
BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
          ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
COMPARE = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
           ast.Gt: operator.gt, ast.GtE: operator.ge, ast.In: lambda a, b: a in b,
           ast.NotIn: lambda a, b: a not in b, ast.Is: operator.is_, ast.IsNot: operator.is_not}
NODES = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Lambda, ast.Return, ast.Pass,
         ast.Assign, ast.Expr, ast.For, ast.If, ast.IfExp, ast.Name, ast.Load, ast.Store, ast.Constant,
         ast.List, ast.Tuple, ast.Subscript, ast.Slice, ast.BinOp, ast.UnaryOp, ast.UAdd, ast.USub, ast.Not,
         ast.Compare, ast.BoolOp, ast.And, ast.Or, ast.ListComp, ast.GeneratorExp, ast.comprehension,
         ast.Call, ast.Attribute, ast.Starred, ast.keyword, *BINARY, *COMPARE)
RESERVED = {'robot', 'np', 'math', 'range', 'zip', 'enumerate', 'reversed', *BUILTINS}


@dataclass(frozen=True)
class ExecutionLimits:
    """Resource budgets, independent of the task and its success criteria."""
    code_characters: int = 64000
    ast_nodes: int = 4096
    api_calls: int = 256
    sequence_items: int = 64

    def __post_init__(self):
        for name in ("code_characters", "ast_nodes", "api_calls", "sequence_items"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(name+" must be a positive integer")

    @classmethod
    def load(cls, path=None):
        path = Path(path or os.environ.get("STACKLAB_POLICY_LIMITS", ROOT/"config/policy.json"))
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Policy limits must be a JSON object")
        try:
            return cls(**data)
        except TypeError as error:
            raise ValueError("Unknown policy-limit setting: "+str(error)) from None


class PolicyError(ValueError):
    pass


class PolicyCancelled(PolicyError):
    pass


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e6:
        raise PolicyError('Expected a finite number with absolute value at most 1000000')
    return value



def qualified_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return qualified_name(node.value) + '.' + node.attr
    return ''


@dataclass
class Function:
    node: object
    scope: dict


class Returned(Exception):
    pass


class WorkbenchPolicy:
    """Evaluate syntax and bounded values without compiling or running Python bytecode."""

    def __init__(self, robot, on_action=None, should_stop=None, limits=None):
        self.limits = limits or ExecutionLimits.load()
        self.robot = robot
        self.variables = {}
        self.actions = []
        self.on_action = on_action
        self.should_stop = should_stop

    def run(self, code):
        if len(code) > self.limits.code_characters:
            raise PolicyError('Program too long')
        tree = ast.parse(code)
        if (len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef)
                or tree.body[0].name != 'run' or [a.arg for a in tree.body[0].args.args] != ['robot']):
            raise PolicyError('Expected one function def run(robot)')
        nodes = list(ast.walk(tree))
        if len(nodes) > self.limits.ast_nodes:
            raise PolicyError('Program exceeds the syntax budget')
        for node in nodes:
            if not isinstance(node, NODES):
                raise PolicyError('Unsupported Python construct: ' + type(node).__name__)
            if isinstance(node, ast.Attribute) and qualified_name(node) not in (
                    *NUMERIC, 'np.linalg', *('robot.' + name for name in METHODS)):
                raise PolicyError('Unsupported attribute: ' + qualified_name(node))
            if isinstance(node, ast.arguments) and (node.posonlyargs or node.kwonlyargs or node.vararg
                    or node.kwarg or node.defaults or any(a.annotation for a in node.args)):
                raise PolicyError('Use simple positional function parameters')
            if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.returns):
                raise PolicyError('Function decorators and annotations are unavailable')
            if isinstance(node, ast.Constant):
                if node.value is not None and type(node.value) not in (int, float, bool, str):
                    raise PolicyError('Only scalar literals are available')
                if isinstance(node.value, str) and len(node.value) > 64:
                    raise PolicyError('String literal too long')
                if type(node.value) in (int, float):
                    number(node.value)
        self.budget = self.limits.ast_nodes * 5
        self.depth = 0
        try:
            self.block(tree.body[0].body)
        except Returned:
            pass
        return self.actions

    def tick(self):
        self.budget -= 1
        if self.budget < 0:
            raise PolicyError('Evaluation budget reached')
        if self.should_stop and self.should_stop():
            raise PolicyCancelled('Execution deadline reached')

    def sequence(self, value):
        if not isinstance(value, (list, tuple, range)) or len(value) > self.limits.sequence_items:
            raise PolicyError('Expected a bounded sequence')
        return list(value)

    def data_value(self, value):
        remaining = self.limits.sequence_items * 4

        def visit(item, depth):
            nonlocal remaining
            remaining -= 1
            if remaining < 0 or depth > 4:
                raise PolicyError('Value exceeds the data budget')
            if isinstance(item, (list, tuple)):
                for member in self.sequence(item):
                    visit(member, depth + 1)
            elif type(item) in (int, float):
                number(item)
            elif item is not None and (type(item) not in (str, bool) or type(item) is str and len(item) > 64):
                raise PolicyError('Expected bounded scalar data')

        visit(value, 0)
        return value

    def assign(self, target, value):
        if isinstance(target, ast.Name) and target.id not in RESERVED and not target.id.startswith('_'):
            self.variables[target.id] = self.data_value(value)
        elif isinstance(target, (ast.Tuple, ast.List)):
            values = self.sequence(value)
            if len(values) != len(target.elts):
                raise PolicyError('Unpacking requires matching lengths')
            for item, member in zip(target.elts, values):
                self.assign(item, member)
        else:
            raise PolicyError('Assign only local variables')

    def block(self, statements):
        for stmt in statements:
            self.tick()
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                self.assign(stmt.targets[0], self.expression(stmt.value))
            elif isinstance(stmt, ast.Expr):
                self.expression(stmt.value)
            elif isinstance(stmt, ast.Return):
                raise Returned(self.expression(stmt.value) if stmt.value else None)
            elif isinstance(stmt, ast.If):
                self.block(stmt.body if self.expression(stmt.test) else stmt.orelse)
            elif isinstance(stmt, ast.For):
                for value in self.sequence(self.expression(stmt.iter)):
                    self.assign(stmt.target, value)
                    self.block(stmt.body)
                self.block(stmt.orelse)
            elif isinstance(stmt, ast.FunctionDef) and stmt.name not in RESERVED and not stmt.name.startswith('_'):
                self.variables[stmt.name] = Function(stmt, self.variables)
            elif not isinstance(stmt, ast.Pass):
                raise PolicyError('Unsupported statement: ' + type(stmt).__name__)

    def function(self, fn, args):
        names = [a.arg for a in fn.node.args.args]
        if self.depth >= 8 or len(args) != len(names) or any(name in RESERVED for name in names):
            raise PolicyError('Invalid function arguments or call depth')
        previous = self.variables
        self.variables = {**fn.scope, **dict(zip(names, args))}
        self.depth += 1
        try:
            if isinstance(fn.node, ast.Lambda):
                return self.expression(fn.node.body)
            self.block(fn.node.body)
        except Returned as result:
            return result.args[0]
        finally:
            self.variables = previous
            self.depth -= 1

    def expression(self, node):
        self.tick()
        if isinstance(node, ast.Call):
            return self.invoke(node)
        if isinstance(node, ast.Lambda):
            return Function(node, self.variables)
        if isinstance(node, (ast.List, ast.Tuple)):
            return self.data_value(self.sequence([self.expression(el) for el in node.elts]))
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            start, stop, step = (self.expression(x) if x else None
                                 for x in (node.slice.lower, node.slice.upper, node.slice.step))
            return self.sequence(self.expression(node.value))[slice(start, stop, step)]
        if isinstance(node, ast.IfExp):
            return self.expression(node.body if self.expression(node.test) else node.orelse)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not self.expression(node.operand)
        if isinstance(node, ast.BoolOp):
            values = (self.expression(el) for el in node.values)
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = self.expression(node.left)
            for op, operand in zip(node.ops, node.comparators):
                right = self.expression(operand)
                if not COMPARE[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.BinOp):
            left, right = self.expression(node.left), self.expression(node.right)
            if isinstance(node.op, ast.Pow) and abs(number(right)) > 8:
                raise PolicyError('Exponent exceeds the numeric budget')
            op = BINARY[type(node.op)]
            if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
                return [number(op(number(a), number(b))) for a, b in zip(left, right)]
            return number(op(number(left), number(right)))
        if isinstance(node, (ast.ListComp, ast.GeneratorExp)) and len(node.generators) == 1:
            loop, scope = node.generators[0], self.variables
            values = self.sequence(self.expression(loop.iter))
            self.variables = scope.copy()
            try:
                result = []
                for value in values:
                    self.assign(loop.target, value)
                    if all(self.expression(test) for test in loop.ifs):
                        result.append(self.expression(node.elt))
                return self.data_value(result)
            finally:
                self.variables = scope
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in self.variables:
                raise PolicyError('Undefined variable: '+node.id)
            return self.variables[node.id]
        if isinstance(node, ast.Subscript):
            value, index = self.expression(node.value), self.expression(node.slice)
            if not isinstance(value, list) or type(index) is not int or not -len(value) <= index < len(value):
                raise PolicyError('Index a position list with an in-range integer')
            return value[index]
        if isinstance(node, ast.UnaryOp):
            value = number(self.expression(node.operand))
            return value if isinstance(node.op, ast.UAdd) else -value
        raise PolicyError('Unsupported expression')

    def invoke(self, node):
        name = qualified_name(node.func)
        args = []
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                args.extend(self.sequence(self.expression(arg.value)))
            else:
                args.append(self.expression(arg))
        if len(args) > self.limits.sequence_items or any(kw.arg is None for kw in node.keywords):
            raise PolicyError('Too many arguments or unsupported keyword unpacking')
        kwargs = {kw.arg: self.expression(kw.value) for kw in node.keywords}
        if name.startswith('robot.') and name[6:] in METHODS:
            return self.call(name[6:], args, kwargs)
        if name in NUMERIC:
            options = {'axis'} if name in ('np.mean', 'np.ptp', 'np.linalg.norm') else set()
            if set(kwargs) - options or name.startswith('np.') and len(args) != 1:
                raise PolicyError('Unsupported numeric options')
            self.data_value(args)
            for value in kwargs.values():
                self.data_value(value)
            result = NUMERIC[name](*args, **kwargs)
            return self.data_value(result.tolist() if isinstance(result, (np.ndarray, np.generic)) else result)
        if name in BUILTINS:
            if isinstance(kwargs.get('key'), Function) and name in ('min', 'max', 'sorted'):
                key = kwargs['key']
                kwargs['key'] = lambda value: self.function(key, [value])
            self.data_value(args)
            for keyword, value in kwargs.items():
                if keyword != 'key':
                    self.data_value(value)
            result = BUILTINS[name](*args, **kwargs)
            return self.data_value(result)
        if name == 'range' and not kwargs:
            return self.sequence(range(*args))
        if name == 'enumerate' and not kwargs:
            return [list(item) for item in enumerate(self.sequence(args[0]), *args[1:])]
        if name == 'zip' and not kwargs:
            return [list(item) for item in zip(*(self.sequence(arg) for arg in args))]
        if name == 'reversed' and len(args) == 1 and not kwargs:
            return self.sequence(args[0])[::-1]
        fn = self.variables.get(name)
        if isinstance(fn, Function) and not kwargs:
            return self.function(fn, args)
        raise PolicyError('Unsupported call: ' + name)

    def call(self, method, args, kwargs):
        if self.should_stop and self.should_stop():
            raise PolicyCancelled('Execution cancelled')
        if len(self.actions) >= self.limits.api_calls:
            raise PolicyError(f'API call budget reached: {self.limits.api_calls}')
        action = dict(method=method, args=args, kwargs=kwargs, time_s=float(self.robot.data.time))
        self.actions.append(action)
        if self.on_action:
            self.on_action('start', action)
        try:
            result = self.dispatch(method, args, kwargs, action)
            action['status'] = 'ok'
            return result
        except Exception as error:
            action.update(status='error', error=type(error).__name__+': '+str(error))
            raise
        finally:
            if self.on_action:
                self.on_action('end', action)

    def dispatch(self, method, args, kwargs, action):
        if kwargs:
            raise PolicyError('Robot calls take positional arguments')
        self.data_value(args)
        result = getattr(self.robot, method)(*args)
        if result is not None:
            action['result'] = result.tolist()
            return action['result']
