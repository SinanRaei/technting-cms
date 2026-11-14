"""A small, safe expression language for form rules and calculations.

It reads like Python and is parsed with Python's own parser, but only a short list of node types and functions is
allowed, so an expression can never reach files, the database or Python internals.

    answer("G1") == "no_ai"                     visibility of an option, a field or a step
    total("score", "G1", "G2", "G3")            sum of the options' "score" values
    round(G_raw * 100 / 18)                     ROUND half up, like a spreadsheet
    band(G_score, [25, 50, 75], ["unmanaged", "partly", "managed", "improving"])
    "partly" if G_cap and G_band0 in ["managed", "improving"] else G_band0
    argmin(["govern", "enable", "transform"], [G_rank, E_rank, T_rank], [G_score, E_score, T_score])

Names are earlier calculations (or "this" in a results list). Functions: answer, answered, unknown, score, value,
total, unknowns, round, min, max, abs, sum, len, band, rank, choose, argmin, free_email, label, setting.
Visibility rules may only use answer, answered and unknown, so they can be checked in the browser too (to_client).
"""
import ast
import math
from decimal import ROUND_HALF_UP, Decimal

MAX_LEN = 4000
MAX_NODES = 600
CLIENT_FUNCS = {"answer", "answered", "unknown"}
FUNCS = {"answer", "answered", "unknown", "score", "value", "total", "unknowns", "round", "min", "max", "abs", "sum",
         "len", "band", "rank", "choose", "argmin", "free_email", "label", "setting"}
CMP = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.In: "in", ast.NotIn: "not in"}
BIN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%"}


class ExprError(ValueError):
    pass


def parse(src):
    """Parse and check an expression; raises ExprError with a short reason."""
    src = (src or "").strip()
    if not src:
        raise ExprError("empty expression")
    if len(src) > MAX_LEN:
        raise ExprError("expression is too long")
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"cannot read it: {exc.msg}") from None
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_NODES:
        raise ExprError("expression is too long")
    for n in nodes:
        if isinstance(n, ast.Call):
            if not isinstance(n.func, ast.Name) or n.func.id not in FUNCS:
                raise ExprError(f"unknown function {getattr(n.func, 'id', '?')}")
            if n.keywords:
                raise ExprError("named arguments are not allowed")
        elif isinstance(n, ast.Name):
            if n.id.startswith("_"):
                raise ExprError(f"name {n.id} is not allowed")
        elif isinstance(n, ast.Constant):
            if not isinstance(n.value, (int, float, str, bool, type(None))):
                raise ExprError("only numbers, text, True, False and None")
        elif not isinstance(n, (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
                                ast.BinOp, ast.Compare, ast.IfExp, ast.List, ast.Tuple, ast.Load, *CMP, *BIN)):
            raise ExprError(f"{type(n).__name__} is not allowed")
    return tree


def names_used(tree):
    calls = {id(c.func) for c in ast.walk(tree) if isinstance(c, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and id(n) not in calls}


def check(src, names=None, client=False):
    """Error message for an expression, or "" when it is fine.
    names: calculation names it may use (None = do not check); client=True: only answer/answered/unknown, no names."""
    try:
        tree = parse(src)
    except ExprError as exc:
        return str(exc)
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and client and n.func.id not in CLIENT_FUNCS:
            return f"{n.func.id}() cannot be used here; use answer(), answered() or unknown()"
    used = names_used(tree)
    if client and used:
        return f"{sorted(used)[0]} cannot be used here: rules shown in the browser can only look at answers"
    unknown = sorted(used - set(names or ()) - {"this", "emailed"}) if names is not None else []
    if unknown:
        return f"unknown name {unknown[0]}"
    return ""


def half_up(x, nd=0):
    try:
        q = Decimal(1).scaleb(-int(nd))
        r = Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP)
    except Exception:
        return 0
    return int(r) if int(nd) == 0 else float(r)


def num(x):
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, (int, float)):
        return x
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0


class Env:
    """What an expression can see: the answers, the form's options, calculated values and labels."""

    def __init__(self, fields=None, answers=None, calcs=None, labels=None, lang="en", settings=None, extra=None):
        self.fields = fields or {}        # key -> {"type", "options": {key: {"values", "is_unknown"}}}
        self.answers = answers or {}
        self.calcs = calcs if calcs is not None else {}
        self.labels = labels or {}
        self.lang = lang
        self.settings = settings or {}
        self.extra = extra or {}

    def option(self, key):
        f = self.fields.get(key)
        a = self.answers.get(key)
        if not f or a in (None, "", []):
            return []
        opts = f.get("options") or {}
        keys = a if isinstance(a, list) else [a]
        return [opts[k] for k in keys if k in opts]

    def call(self, name, args):
        a = args
        if name == "answer":
            v = self.answers.get(str(a[0]))
            return "" if v is None else v
        if name == "answered":
            return self.answers.get(str(a[0])) not in (None, "", [], False)
        if name == "unknown":
            return any(o.get("is_unknown") for o in self.option(str(a[0])))
        if name == "score":
            return self.value(str(a[0]), "score")
        if name == "value":
            return self.value(str(a[0]), str(a[1]) if len(a) > 1 else "score")
        if name == "total":
            return sum(self.value(str(k), str(a[0])) for k in a[1:])
        if name == "unknowns":
            keys = [str(k) for k in a] or [k for k, f in self.fields.items() if f.get("options")]
            return sum(1 for k in keys if self.call("unknown", [k]))
        if name == "round":
            return half_up(num(a[0]), a[1] if len(a) > 1 else 0)
        if name in ("min", "max"):
            vals = a[0] if len(a) == 1 and isinstance(a[0], list) else a
            vals = [num(v) for v in vals]
            return (min if name == "min" else max)(vals) if vals else 0
        if name == "abs":
            return abs(num(a[0]))
        if name == "sum":
            return sum(num(v) for v in (a[0] if a and isinstance(a[0], list) else a))
        if name == "len":
            return len(a[0]) if a and isinstance(a[0], (list, str)) else 0
        if name == "band":                         # band(x, [25, 50, 75], [l1, l2, l3, l4]): first threshold x fits under
            x, limits, names = num(a[0]), list(a[1]), list(a[2])
            for i, t in enumerate(limits):
                if x <= num(t):
                    return names[i] if i < len(names) else i
            return names[len(limits)] if len(limits) < len(names) else len(limits)
        if name == "rank":                         # rank(x, list): position of x in the list, -1 when missing
            lst = list(a[1])
            return lst.index(a[0]) if a[0] in lst else -1
        if name == "choose":                       # choose(x, [keys], [values], default)
            keys, vals = list(a[1]), list(a[2])
            default = a[3] if len(a) > 3 else 0
            return vals[keys.index(a[0])] if a[0] in keys and keys.index(a[0]) < len(vals) else default
        if name == "argmin":                       # argmin(keys, primary[, secondary]): first key on ties
            keys, p = list(a[0]), [num(v) for v in a[1]]
            s = [num(v) for v in a[2]] if len(a) > 2 else [0] * len(p)
            best = min(range(len(keys)), key=lambda i: (p[i], s[i], i)) if keys else None
            return keys[best] if best is not None else ""
        if name == "free_email":
            from crm.services import FREE_MAIL
            return str(a[0]).rsplit("@", 1)[-1].lower().strip() in FREE_MAIL
        if name == "label":
            item = self.labels.get(str(a[0]))
            if isinstance(item, dict):
                return item.get(self.lang) or item.get("en") or str(a[0])
            return str(a[0])
        if name == "setting":
            v = self.settings.get(str(a[0]), a[1] if len(a) > 1 else "")
            return v.get(self.lang) or v.get("en", "") if isinstance(v, dict) else v
        raise ExprError(f"unknown function {name}")

    def value(self, key, name):
        f = self.fields.get(key) or {}
        if f.get("type") == "scale":
            return num(self.answers.get(key))
        return sum(num((o.get("values") or {}).get(name, 0)) for o in self.option(key))


def evaluate(src_or_tree, env):
    tree = parse(src_or_tree) if isinstance(src_or_tree, str) else src_or_tree
    return _ev(tree.body, env)


def truthy(src, env, default=True):
    """Visibility: an empty rule means visible; a broken rule means visible too (the editor shows the error)."""
    if not (src or "").strip():
        return default
    try:
        return bool(evaluate(src, env))
    except (ExprError, TypeError, ValueError, ZeroDivisionError, IndexError):
        return default


def _ev(n, env):
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, ast.Name):
        if n.id in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[n.id]
        if n.id in env.extra:
            return env.extra[n.id]
        return env.calcs.get(n.id, 0)
    if isinstance(n, (ast.List, ast.Tuple)):
        return [_ev(e, env) for e in n.elts]
    if isinstance(n, ast.BoolOp):
        if isinstance(n.op, ast.And):
            v = True
            for e in n.values:
                v = _ev(e, env)
                if not v:
                    return v
            return v
        v = False
        for e in n.values:
            v = _ev(e, env)
            if v:
                return v
        return v
    if isinstance(n, ast.UnaryOp):
        v = _ev(n.operand, env)
        if isinstance(n.op, ast.Not):
            return not v
        return -num(v) if isinstance(n.op, ast.USub) else num(v)
    if isinstance(n, ast.BinOp):
        l, r = _ev(n.left, env), _ev(n.right, env)
        op = type(n.op)
        if op is ast.Add and (isinstance(l, str) or isinstance(r, str)):
            return f"{l}{r}"
        l, r = num(l), num(r)
        if op is ast.Add:
            return l + r
        if op is ast.Sub:
            return l - r
        if op is ast.Mult:
            return l * r
        if r == 0:
            return 0                                  # dividing by zero gives 0 instead of an error
        if op is ast.Div:
            v = l / r
            return int(v) if float(v).is_integer() else v
        if op is ast.FloorDiv:
            return math.floor(l / r)
        return l % r
    if isinstance(n, ast.Compare):
        left = _ev(n.left, env)
        for op, comp in zip(n.ops, n.comparators):
            right = _ev(comp, env)
            if not _cmp(type(op), left, right):
                return False
            left = right
        return True
    if isinstance(n, ast.IfExp):
        return _ev(n.body, env) if _ev(n.test, env) else _ev(n.orelse, env)
    if isinstance(n, ast.Call):
        return env.call(n.func.id, [_ev(a, env) for a in n.args])
    raise ExprError(f"{type(n).__name__} is not allowed")


def _cmp(op, l, r):
    if op in (ast.In, ast.NotIn):
        inside = l in r if isinstance(r, (list, str)) else False
        if isinstance(l, list) and isinstance(r, list):  # checkbox answers: any of them
            inside = any(x in r for x in l)
        return inside if op is ast.In else not inside
    if op is ast.Eq:
        return l == r or (isinstance(l, list) and r in l)
    if op is ast.NotEq:
        return not (l == r or (isinstance(l, list) and r in l))
    try:
        l, r = (num(l), num(r)) if not (isinstance(l, str) and isinstance(r, str)) else (l, r)
        return {ast.Lt: l < r, ast.LtE: l <= r, ast.Gt: l > r, ast.GtE: l >= r}[op]
    except TypeError:
        return False


def to_client(src):
    """A visibility rule as a small JSON tree the browser can evaluate (form-runner.js). None when empty."""
    if not (src or "").strip():
        return None
    err = check(src, names=(), client=True)
    if err:
        raise ExprError(err)
    return _js(parse(src).body)


def _js(n):
    if isinstance(n, ast.Constant):
        return {"k": "c", "v": n.value}
    if isinstance(n, ast.Name):
        return {"k": "c", "v": {"True": True, "False": False}.get(n.id)}
    if isinstance(n, (ast.List, ast.Tuple)):
        return {"k": "l", "v": [_js(e) for e in n.elts]}
    if isinstance(n, ast.BoolOp):
        return {"k": "and" if isinstance(n.op, ast.And) else "or", "v": [_js(e) for e in n.values]}
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
        return {"k": "not", "v": _js(n.operand)}
    if isinstance(n, ast.Compare):
        parts, left = [], n.left
        for op, comp in zip(n.ops, n.comparators):
            parts.append({"k": "cmp", "op": CMP[type(op)], "l": _js(left), "r": _js(comp)})
            left = comp
        return parts[0] if len(parts) == 1 else {"k": "and", "v": parts}
    if isinstance(n, ast.IfExp):
        return {"k": "if", "t": _js(n.test), "a": _js(n.body), "b": _js(n.orelse)}
    if isinstance(n, ast.Call):
        return {"k": n.func.id, "v": str(_ev(n.args[0], Env())) if n.args else ""}
    raise ExprError(f"{type(n).__name__} cannot be checked in the browser")
