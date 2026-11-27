"""Reposition one existing source excerpt using a public Python traceback."""
import ast
from pathlib import PurePosixPath
import re


FRAME = re.compile(r'^\s*File "(?P<path>[^"\n]+\.py)", line (?P<line>[1-9]\d{0,7}), in (?P<name>[A-Za-z_]\w*)\s*$')


def traceback_frames(issue):
    lines = issue.splitlines()
    frames = []
    for i, line in enumerate(lines[:-1]):
        match = FRAME.fullmatch(line)
        if match:
            path, number, name = match.groups()
            statement = lines[i + 1].strip()
            if statement:
                frames.append((path.replace("\\", "/"), int(number), name, statement))
    return frames


def anchor(path, source, issue, frames):
    parts = PurePosixPath(path).parts
    # An installed package may omit the repository's src/ layout prefix.
    suffix = parts[1:] if parts[:1] == ("src",) else parts
    relevant = [f for f in frames if PurePosixPath(f[0]).parts[-len(suffix):] == suffix]
    if not relevant:
        return None
    try:
        functions = [n for n in ast.walk(ast.parse(source))
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    except (SyntaxError, ValueError, RecursionError):
        return None
    lines = source.splitlines()
    prose = issue.split("Traceback (most recent call last)", 1)[0]
    choices = []
    for order, (_, reported, name, statement) in enumerate(relevant):
        hits = {line for node in functions if node.name == name
                for line in range(node.lineno, node.end_lineno + 1)
                if lines[line - 1].strip() == statement}
        if reported in hits:
            selected = reported
        elif len(hits) == 1:
            selected = hits.pop()
        else:
            continue
        named = bool(re.search(r"\b" + re.escape(name) + r"\b", prose))
        choices.append(((named, order), selected, name, reported))
    return max(choices) if choices else None


def reposition(window, source, issue, frames):
    """Keep both line and UTF-8 byte counts at or below the original excerpt."""
    found = anchor(window["path"], source, issue, frames)
    if found is None:
        return window, "retained (no confirmed frame)"
    _, number, name, reported = found
    lines = source.splitlines(keepends=True)
    original = window["content"]
    limit = len(original.encode())
    width = len(original.splitlines())
    center = number - 1
    if len(lines[center].encode()) > limit:
        return window, "retained (anchor exceeds byte budget)"
    start = max(0, min(center - width // 2, len(lines) - width))
    stop = min(len(lines), start + width)
    sizes = [len(line.encode()) for line in lines[start:stop]]
    byte_count = sum(sizes)
    first = start
    while byte_count > limit:
        if center - start >= stop - 1 - center:
            byte_count -= sizes[start - first]
            start += 1
        else:
            stop -= 1
            byte_count -= sizes[stop - first]
    return {"path": window["path"], "start_line": start + 1, "content": "".join(lines[start:stop])}, (
        f"{name} (reported {reported}, confirmed {number})")
