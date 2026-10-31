"""Terminal output must not turn a valid robot program into a failed episode."""
import sys


def print_safe(*values, sep=' ', end='\n', file=None, flush=False):
    stream = sys.stdout if file is None else file
    text = sep.join(map(str, values))+end
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, 'encoding', None) or 'utf-8'
        stream.write(text.encode(encoding, errors='backslashreplace').decode(encoding))
    if flush:
        stream.flush()
