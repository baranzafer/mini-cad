"""Üst düzey tanımları yeni modüllere taşır; orijinal modül hepsini yeniden dışa aktarır."""
import ast, sys, json
sys.path.insert(0, "/tmp/split")
from splitter import *

ROOT, MOD, spec = sys.argv[1], sys.argv[2], json.load(open(sys.argv[3]))
src = open(f"{ROOT}/{MOD}.py").read(); lines = src.split("\n"); tree = ast.parse(src); body = tree.body
import_map = {}
for n in body:
    if isinstance(n, (ast.Import, ast.ImportFrom)):
        for nm in top_names(n): import_map[nm] = n
segs = segments(lines, body, 1)
owner = {}
for mod, g in spec.items():
    for nm in g["names"]: owner[nm] = mod
def node_owner(n):
    ns = top_names(n)
    if not ns: return None
    os_ = {owner.get(x) for x in ns}
    assert len(os_) == 1, ns
    return os_.pop()
provided = {}
for n in body:
    if isinstance(n, (ast.Import, ast.ImportFrom)): continue
    o = node_owner(n)
    if o:
        for nm in top_names(n): provided[nm] = o
assert set(owner) <= set(provided), set(owner) - set(provided)
outs = {m: [] for m in spec}; keep = []
for n, a, b in segs:
    if isinstance(n, (ast.Import, ast.ImportFrom)) or n is body[0]:
        keep.append((n, a, b)); continue
    o = node_owner(n)
    if o: outs[o].append(text(lines, a, b, drop_sections=True))
    else: keep.append((n, a, b))
written = {}
for mod, g in spec.items():
    bt = "\n\n\n".join(outs[mod])
    used = loads(bt)
    bad = [u for u in used if u not in provided and u not in import_map and u in
           {x for n in body for x in top_names(n)}]
    assert not bad, (mod, "orijinal modüle bağımlı:", bad)
    imp = build_imports(used, import_map, provided, mod)
    written[mod] = f'"""{g["doc"]}\n"""\n\n' + imp + "\n\n\n" + bt + "\n"
# orijinal: docstring + importlar + yeniden dışa aktarım + kalanlar
first_import = next(i for i, (n, a, b) in enumerate(keep) if isinstance(n, (ast.Import, ast.ImportFrom)))
last_import = max(i for i, (n, a, b) in enumerate(keep) if isinstance(n, (ast.Import, ast.ImportFrom)))
head = "\n".join(lines[: keep[last_import][2]])
reexp = "\n".join(wrap(f"from .{m} import ", sorted(nm for nm, o in provided.items() if o == m)) for m in spec)
rest = keep[last_import + 1:]
rest_txt = ""
for n, a, b in rest:
    t = text(lines, a, b)
    rest_txt += ("\n\n\n" if isinstance(n, (ast.FunctionDef, ast.ClassDef)) else "\n\n") + t
main = head + "\n\n# Bölünmüş parçalar (v0.15.2); adlar geriye dönük uyum için burada da erişilebilir.\n" + reexp + rest_txt + "\n"
import re
main = re.sub(r"\n{4,}", "\n\n\n", main)
written[MOD] = main
for k, v in written.items():
    open(f"{ROOT}/{k}.py", "w").write(v); print(k, v.count("\n"))
