"""AST tabanlı modül bölücü: satırları aynen taşır, importları otomatik üretir."""
import ast, re, sys, os

SECTION = re.compile(r"^\s*# -{6,}")

def top_names(node):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)): return [node.name]
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name): return [node.target.id]
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return [(a.asname or a.name).split(".")[0] for a in node.names]
    return []

def loads(src_text):
    t = ast.parse(src_text)
    s = set()
    for x in ast.walk(t):
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load): s.add(x.id)
        if isinstance(x, ast.Attribute):  # decorators like bpy.app...
            pass
    return s

def segments(lines, body, first_start):
    """Her düğüm için (start, end) satır aralığı: önceki düğümün bitişinden sonrası (yorumlar dahil)."""
    out = []
    prev_end = first_start - 1
    for n in body:
        start = prev_end + 1
        out.append((n, start, n.end_lineno))
        prev_end = n.end_lineno
    return out

def text(lines, a, b, drop_sections=False):
    seg = lines[a - 1:b]
    if drop_sections:
        seg = [l for l in seg if not SECTION.match(l)]
    # baştaki boş satırları kırp
    while seg and not seg[0].strip(): seg.pop(0)
    return "\n".join(seg)

def import_line(node, name, src):
    """Bir import düğümünden yalnızca `name`i getiren satır."""
    if isinstance(node, ast.Import):
        for a in node.names:
            if (a.asname or a.name).split(".")[0] == name:
                return f"import {a.name}" + (f" as {a.asname}" if a.asname else "")
    else:
        mod = "." * node.level + (node.module or "")
        for a in node.names:
            if (a.asname or a.name) == name:
                return f"from {mod} import {a.name}" + (f" as {a.asname}" if a.asname else "")
    raise KeyError(name)

def build_imports(used, import_map, provided, self_mod):
    """used: kullanılan adlar; import_map: ad->(düğüm); provided: ad->modül adı (yeni modüller)."""
    std, rel = [], {}
    for nm in sorted(used):
        if nm in import_map:
            std.append(import_line(import_map[nm], nm, None))
        elif nm in provided and provided[nm] != self_mod:
            rel.setdefault(provided[nm], []).append(nm)
    # grupla: önce mutlak, sonra göreli
    abs_ = sorted({l for l in std if not l.startswith("from .")}, key=lambda l: (l.startswith("from"), l))
    relstd = sorted({l for l in std if l.startswith("from .")})
    out = abs_[:]
    if relstd or rel: out.append("")
    out += relstd
    for mod in sorted(rel):
        names = sorted(rel[mod])
        out.append(wrap(f"from .{mod} import ", names))
    return "\n".join(out)

def wrap(prefix, names, width=96):
    one = prefix + ", ".join(names)
    if len(one) <= width: return one
    lines, cur = [], "    "
    for n in names:
        piece = n + ", "
        if len(cur) + len(piece) > width:
            lines.append(cur.rstrip()); cur = "    "
        cur += piece
    lines.append(cur.rstrip().rstrip(","))
    return prefix + "(\n" + "\n".join(lines) + ",\n)"
