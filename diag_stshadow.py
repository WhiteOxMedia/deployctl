"""AST AUDIT — the swallowed-widget bug class (Sep 12).

The disease: a local named `st` (a state abbreviation) bound anywhere
in a function scope — plain assignment, a plain `for st in ...` loop,
a with-as, or a parameter — makes `st` LOCAL for the whole scope.
Every `st.markdown` / `st.session_state` / widget call in that scope
then raises UnboundLocalError (load before the bind) or AttributeError
(load after the bind, st holding a state string like "OUT"). Inside a
fail-open `try/except: pass` the death is silent: the widget simply
never renders — exactly what killed the trail's toggle and dropdown
before their scars were found by hand.

Safe shapes (own scope, no leak): comprehension targets, lambda
params, nested defs — each handled as its own scope. Body order
matters: a load before the first bind in the body is the
UnboundLocalError variant; after the bind, the AttributeError variant
— both flagged, with swallow-risk (inside a try block) noted.

Read-only. Writes _stshadow.txt.
Run: .venv\\Scripts\\python.exe -X utf8 diag_stshadow.py
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent
TARGET = ROOT / "app.py"
OUT = ROOT / "_stshadow.txt"

WIDGETS = {
    "markdown", "write", "caption", "code", "header", "subheader",
    "text", "metric", "columns", "expander", "container", "empty",
    "checkbox", "selectbox", "multiselect", "radio", "button",
    "form", "text_input", "number_input", "slider", "toggle",
    "rerun", "session_state", "sidebar", "tabs", "toast", "spinner",
    "stop", "plotly_chart", "pyplot", "image", "error", "warning",
    "info", "success", "cache_data", "cache_resource", "divider",
    "badge", "chat_message", "dataframe", "table", "json", "link",
}

SCOPE_STMTS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
               ast.Lambda)


def _walk_own(node):
    """Yield every node in `node`'s OWN scope: descend into compound
    statements but PRUNE nested function/class/lambda subtrees (they
    are separate scopes with their own bindings)."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        for child in ast.iter_child_nodes(n):
            if isinstance(child, SCOPE_STMTS):
                continue          # pruned: another scope's territory
            stack.append(child)


def _binds_st(node):
    """(kind, name, lineno) for every `st` binding `node` makes in its
    own scope."""
    out = []
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                         ast.ClassDef, ast.Lambda)):
        if getattr(node, "name", None) == "st":
            out.append(("def", "st", node.lineno))
        args = getattr(node, "args", None)
        if args is not None:
            for a in (args.posonlyargs + args.args + args.kwonlyargs):
                if a.arg == "st":
                    out.append(("param", "st", node.lineno))
            if args.vararg and args.vararg.arg == "st":
                out.append(("param", "st", node.lineno))
            if args.kwarg and args.kwarg.arg == "st":
                out.append(("param", "st", node.lineno))
    elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        tgts = ([node.targets] if False else
                node.targets if isinstance(node, ast.Assign)
                else [node.target])
        for t in tgts:
            for n in ast.walk(t):
                if isinstance(n, ast.Name) and n.id == "st":
                    out.append((type(node).__name__, "st", node.lineno))
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        for n in ast.walk(node.target):
            if isinstance(n, ast.Name) and n.id == "st":
                out.append(("for", "st", node.lineno))
    elif isinstance(node, ast.withitem) and node.optional_vars is not None:
        for n in ast.walk(node.optional_vars):
            if isinstance(n, ast.Name) and n.id == "st":
                out.append(("with", "st", node.lineno))
    elif isinstance(node, (ast.Global, ast.Nonlocal)):
        if "st" in node.names:
            out.append((type(node).__name__, "st", node.lineno))
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
        for al in node.names:
            if (al.asname or al.name.split(".")[0]) == "st":
                out.append(("import", "st", node.lineno))
    return out


def _st_widget_loads(node):
    """(attr, lineno) for every st.<widget/session> load in the node's
    own scope (comprehension bodies INCLUDED — they resolve `st`
    against the enclosing function's locals, so a leaky bind poisons
    them too)."""
    out = []
    for n in _walk_own(node):
        if (isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name)
                and n.value.id == "st" and n.attr in WIDGETS):
            out.append((n.attr, n.lineno))
    return out


class Scope:
    def __init__(self, name, node, parent):
        self.name = name
        self.node = node
        self.parent = parent
        self.binds = []       # (kind, lineno)
        self.loads = []       # (attr, lineno)
        self.try_spans = []   # (start, end) try regions
        self.children = []

    def label(self):
        chain, s = [], self
        while s is not None:
            chain.append(s.name)
            s = s.parent
        return " > ".join(reversed(chain))


def build_scope(node, name, parent):
    sc = Scope(name, node, parent)
    if parent is not None:
        parent.children.append(sc)
    body = (node.body if isinstance(node, (ast.FunctionDef,
                                           ast.AsyncFunctionDef,
                                           ast.ClassDef, ast.Module))
            else [node.body] if isinstance(node, ast.Lambda)
            else [])

    def visit(stmts):
        for stmt in stmts:
            for kind, _, ln in _binds_st(stmt):
                sc.binds.append((kind, ln))
            for attr, ln in _st_widget_loads(stmt):
                sc.loads.append((attr, ln))
            # comprehension targets bind in an implicit scope but
            # resolve against THIS scope's locals when not comp-local:
            # a comp target named st shadows for the comp body only,
            # so record it as a scoped bind (its own loads stay here)
            for n in _walk_own(stmt):
                if isinstance(n, (ast.ListComp, ast.SetComp,
                                  ast.DictComp, ast.GeneratorExp)):
                    for gen in n.generators:
                        for t in ast.walk(gen.target):
                            if isinstance(t, ast.Name) and t.id == "st":
                                sc.binds.append(("comp-target",
                                                 t.lineno))
            if isinstance(stmt, ast.Try):
                end = max((getattr(s, "end_lineno", s.lineno)
                           for s in _walk_own(stmt)), default=stmt.lineno)
                sc.try_spans.append((stmt.lineno, end))
                visit(stmt.body)
                visit(stmt.orelse)
                visit(stmt.finalbody)
                for h in stmt.handlers:
                    visit(h.body)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef,
                                   ast.ClassDef)):
                build_scope(stmt, stmt.name, sc)
            elif isinstance(stmt, ast.Lambda):
                build_scope(stmt, f"<lambda:{stmt.lineno}>", sc)
            elif isinstance(stmt, (ast.If, ast.While)):
                visit(stmt.body)
                visit(stmt.orelse)
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                visit(stmt.body)
                visit(stmt.orelse)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                visit(stmt.body)

    visit(body)
    return sc


def iter_scopes(root):
    stack = [root]
    while stack:
        s = stack.pop()
        yield s
        stack.extend(s.children)


def analyze_text(src):
    tree = ast.parse(src, filename="memory")
    imported = any(kind == "import"
                   for n in tree.body for kind, _, _ in _binds_st(n))
    mod = build_scope(tree, "<module>", None)
    findings = []
    for sc in iter_scopes(mod):
        if not sc.binds:
            continue
        for attr, ln in sc.loads:
            prior = [b for b in sc.binds if b[1] <= ln]
            variant = ("before-bind (UnboundLocalError)"
                       if not prior else
                       "after-bind (st is "
                       f"{prior[-1][0]!r}-bound -> AttributeError)")
            in_try = any(a <= ln <= b for a, b in sc.try_spans)
            findings.append((sc.label(), attr, ln, variant, in_try))
    return imported, mod, findings


def analyze():
    return analyze_text(TARGET.read_text(encoding="utf-8"))


BAD_SNIPPET = '''
import streamlit as st

def trail_block(evidence):
    try:
        rows = []
        for st in evidence:          # <-- the leak: st becomes local
            st = str(st.get("state") or "")
        st.markdown("".join(rows))   # AttributeError, swallowed below
    except Exception:
        pass
    st.selectbox("verdict", ["a"])   # before-bind variant, uncaught

def clean_block(evidence):
    for st in evidence:              # comp target only: safe
        pass
    return [str(st) for st in evidence]
'''


def selftest():
    """The analyzer must flag the bad snippet's both variants and the
    swallow, and must NOT flag the comprehension-safe function."""
    _, _, bad = analyze_text(BAD_SNIPPET)
    lines = [f"line {ln}: st.{attr} in {lbl} — {variant}"
             f"{'; SWALLOWED by try/except' if tr else ''}"
             for lbl, attr, ln, variant, tr in bad]
    got_markdown = any(attr == "markdown" and tr
                       for _, attr, _, _, tr in bad)
    got_select = any(attr == "selectbox" and not tr
                     for _, attr, _, _, tr in bad)
    got_clean = not any("clean_block" in lbl
                        for lbl, _, _, _, _ in bad)
    return lines, (got_markdown and got_select and got_clean
                   and len(bad) == 2), bad


def main():
    imported, mod, findings = analyze()
    scopes = list(iter_scopes(mod))
    check_lines = []

    def check(name, ok, detail=""):
        check_lines.append(f"{'PASS' if ok else 'FAIL'}  {name}"
                           + (f"  [{detail}]" if detail and not ok
                              else ""))

    st_lines, st_ok, st_detail = selftest()
    check("selftest: the bad snippet's swallow + uncaught variants are "
          "both flagged, the comp-safe function is not", st_ok,
          st_detail)

    # no double attribution: every (scope-label, line) pair is unique
    seen = [(f.label(), ln) for f, (lbl, attr, ln, _, _) in
            zip(iter_scopes(mod), [f2 for s in iter_scopes(mod)
                                   for f2 in [(s.label(), l[1])
                                              for l in s.loads]])]
    dupes = {p for p in seen if seen.count(p) > 1}
    check("no widget load is attributed to two scopes (pruned walk)",
          not dupes, sorted(dupes)[:5])

    total_loads = sum(len(s.loads) for s in scopes)
    check("the audit saw the module's own st widget calls",
          any(s.name == "<module>" and s.loads for s in scopes),
          f"{total_loads} scoped loads")
    check("app.py imports streamlit as st at module level", imported)

    lines = ["ST-SHADOW AUDIT — app.py (the swallowed-widget class)",
             f"module-level 'import streamlit as st': {imported}",
             f"scopes analyzed: {len(scopes)}",
             f"st.<widget/session> loads in scopes: {total_loads}",
             "", "SELFTEST (the analyzer against a known-bad snippet):"]
    lines.extend("  " + s for s in st_lines)
    if findings:
        lines.append("")
        lines.append("FINDINGS (leaky st bind + st.<widget> load in "
                     "the same scope):")
        for lbl, attr, ln, variant, tr in sorted(findings,
                                                 key=lambda f: f[2]):
            lines.append(f"  line {ln}: st.{attr} in {lbl}")
            lines.append(f"     {variant}; "
                         + ("SWALLOWED by try/except" if tr
                            else "uncaught"))
    else:
        lines.append("")
        lines.append("FINDINGS: none — no scope both binds a local st "
                     "and calls st widgets")
    lines.append("")
    lines.extend(check_lines)
    verdict = ("CLEAN — the bug class is absent" if not findings else
               f"{len({f[0] for f in findings})} scope(s) affected, "
               f"{len(findings)} call(s) at risk")
    lines.append(f"VERDICT: {verdict}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if all(cl.startswith("PASS") for cl in check_lines) else 1


if __name__ == "__main__":
    sys.exit(main())
