#!/usr/bin/env python3
"""Parse eligibility criteria into a logic TREE, not a flat list.

The flat version was wrong in a way that produced confidently wrong exclusions:
indentation is the only thing encoding hierarchy in ClinicalTrials.gov criteria,
and `line.strip()` deletes it. A nested "at least 2 of the following" group then
becomes six independent mandatory requirements.

This keeps depth, detects group operators, and emits AND / OR / N_OF nodes.
Leaves are evaluated separately (by a model, or deterministically); the tree is
combined in code with three-valued logic, where UNKNOWN never excludes anyone.

    python3 criteria_tree.py NCT03432533        # show the tree for one trial
"""
import re

# "at least 2 of the following", "one of the following", "any of", "all of" …
NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
GROUP = re.compile(
    r"(?i)\b(?:(?P<atleast>at\s+least|a\s+minimum\s+of|)\s*"
    r"(?P<n>\d+|one|two|three|four|five|six)\s+(?:or\s+more\s+)?of\s+the\s+following"
    r"|(?P<any>any|either)\s+of\s+the\s+following"
    r"|(?P<all>all)\s+of\s+the\s+following)")

BULLET = re.compile(r"^(\s*)(?:[-*•·o]|\(?\d+[.)]|\(?[a-z][.)])\s+")
HEADER = re.compile(r"(?i)^\s*(inclusion|exclusion)\b[^:]{0,30}:?\s*$")
INLINE_HEADER = re.compile(r"(?i)^\s*(inclusion|exclusion)\s+criteria\s*:?\s*")

TRUE, FALSE, UNKNOWN = "true", "false", "unknown"


class Node:
    """op is 'AND' | 'OR' | 'N_OF' | 'LEAF'."""

    def __init__(self, op, text="", n=0, depth=-1):
        self.op, self.text, self.n, self.depth = op, text, n, depth
        self.children = []

    def leaves(self):
        if self.op == "LEAF":
            yield self
        for c in self.children:
            yield from c.leaves()

    def show(self, ind=0):
        pad = "  " * ind
        if self.op == "LEAF":
            return "%s- %s\n" % (pad, self.text[:88])
        head = {"AND": "ALL of:", "OR": "ANY of:",
                "N_OF": "AT LEAST %d of:" % self.n}[self.op]
        s = "%s%s%s\n" % (pad, head, ("   « " + self.text[:60]) if self.text else "")
        for c in self.children:
            s += c.show(ind + 1)
        return s


def _lines(text):
    """(depth, text) per criterion line, continuations merged into their parent."""
    out = []
    for raw in text.replace("\r", "").split("\n"):
        if not raw.strip():
            continue
        m = BULLET.match(raw)
        if m:
            depth = len(m.group(1))
            body = raw[m.end():].strip()
            # a stray "-foo" glued onto the end of a previous line
            body = re.sub(r"\s+-(?=[A-Z])", "\n", body)
            parts = [p.strip() for p in body.split("\n") if p.strip()]
            for k, p in enumerate(parts):
                out.append((depth + (2 if k else 0), p.lstrip("-\u2013 ").strip()))
        else:
            body = raw.strip()
            if out and not HEADER.match(body) and body[:1].islower():
                # continuation of the previous criterion
                out[-1] = (out[-1][0], (out[-1][1] + " " + body).strip())
            else:
                out.append((len(raw) - len(raw.lstrip()), body))
    return out


def _group_op(text):
    """(op, n) if this line introduces a group, else None."""
    m = GROUP.search(text)
    if not m:
        return None
    if m.group("all"):
        return ("AND", 0)
    if m.group("any"):
        return ("OR", 0)
    n = m.group("n")
    n = NUMWORD.get(n.lower(), None) if not n.isdigit() else int(n)
    if n is None:
        return ("OR", 0)
    if not m.group("atleast") and n == 1:
        return ("OR", 0)
    return ("N_OF", n)


def parse(text):
    """-> {'inclusion': Node(AND), 'exclusion': Node(AND)}"""
    roots = {"inclusion": Node("AND", depth=-1), "exclusion": Node("AND", depth=-1)}
    section = "inclusion"
    stack = [roots["inclusion"]]

    for depth, line in _lines(text):
        h = HEADER.match(line) or INLINE_HEADER.match(line)
        if h:
            section = "exclusion" if "exclu" in h.group(1).lower() else "inclusion"
            stack = [roots[section]]
            rest = INLINE_HEADER.sub("", line).strip() if INLINE_HEADER.match(line) else ""
            if not rest:
                continue
            line, depth = rest, 0
        if len(line) < 3:
            continue

        while len(stack) > 1 and depth <= stack[-1].depth:
            stack.pop()

        g = _group_op(line)
        if g:
            m = GROUP.search(line)
            lead = line[:m.start()].strip(" ,;:") if m else ""
            # "X or at least 2 of the following" -> OR[ X , N_OF(2, ...) ]
            alt = re.search(r"(?i)^(.*?)\s+\bor\b\s+\S[^,]*$", lead)
            node = Node(g[0], text=line, n=g[1], depth=depth)
            if alt and len(alt.group(1)) > 12:
                holder = Node("OR", text=lead, depth=depth)
                holder.children.append(Node("LEAF", text=alt.group(1).strip(),
                                            depth=depth + 1))
                holder.children.append(node)
                node.depth = depth + 1
                stack[-1].children.append(holder)
            else:
                stack[-1].children.append(node)
            stack.append(node)
        else:
            stack[-1].children.append(Node("LEAF", text=line, depth=depth))
    return roots


# ---------------------------------------------------------------- three-valued logic

def evaluate(node, values):
    """Kleene logic over {true,false,unknown}. `values` maps id(leaf) -> verdict."""
    if node.op == "LEAF":
        return values.get(id(node), UNKNOWN)
    kids = [evaluate(c, values) for c in node.children]
    if not kids:
        return UNKNOWN
    t, f = kids.count(TRUE), kids.count(FALSE)
    if node.op == "AND":
        return FALSE if f else (TRUE if t == len(kids) else UNKNOWN)
    if node.op == "OR":
        return TRUE if t else (FALSE if f == len(kids) else UNKNOWN)
    if node.op == "N_OF":
        if t >= node.n:
            return TRUE
        return FALSE if t + kids.count(UNKNOWN) < node.n else UNKNOWN
    return UNKNOWN


def explain(node, values, ind=0):
    """Why the tree came out as it did — what a coordinator would read."""
    v = evaluate(node, values)
    pad = "  " * ind
    if node.op == "LEAF":
        return "%s[%-7s] %s\n" % (pad, v, node.text[:78])
    head = {"AND": "ALL", "OR": "ANY", "N_OF": "AT LEAST %d" % node.n}[node.op]
    s = "%s[%-7s] %s of:\n" % (pad, v, head)
    for c in node.children:
        s += explain(c, values, ind + 1)
    return s
