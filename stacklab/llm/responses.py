"""Decode transport formats without changing or repairing a model's program."""
import ast
import json
import re
from stacklab.policy import validate

def parse_reply(raw, limits=None):
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "code" in value:
            if (set(value) <= {"code", "done", "message"} and isinstance(value["code"], str)
                    and type(value.get("done", True)) is bool
                    and isinstance(value.get("message", ""), str)):
                return dict(code=value["code"], done=value.get("done", True), message=value.get("message", ""))
            raise ValueError("Expected code:string, optional done:boolean and message:string")
    blocks = re.findall(r"\x60\x60\x60(?:python|py)?[ \t]*\n([\s\S]*?)\x60\x60\x60", raw)
    if "\x60\x60\x60" in raw and len(blocks) != 1:
        raise ValueError("Return one Python block or one JSON code object")
    code = blocks[0].strip() if blocks else raw.strip()
    try:
        tree = validate(code, limits)
        if not any(isinstance(node, (ast.Assign, ast.Call)) for node in ast.walk(tree)):
            raise ValueError("No Python program found")
    except ValueError as error:
        raise ValueError("Expected JSON code, one fenced Python block or a Python program: "+str(error)) from None
    return dict(code=code, done=True, message="")
