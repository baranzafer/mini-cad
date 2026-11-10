import ast, sys, glob, os
orig_file, new_glob = sys.argv[1], sys.argv[2:]
def defs(path):
    t = ast.parse(open(path).read()); out = {}
    for n in t.body:
        if isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, ast.FunctionDef): out[("M", m.name)] = ast.dump(m)
                elif isinstance(m, ast.Assign): out[("A", ast.unparse(m.targets[0]))] = ast.dump(m)
        elif isinstance(n, (ast.FunctionDef,)): out[("F", n.name)] = ast.dump(n)
        elif isinstance(n, ast.Assign): out[("V", ast.unparse(n.targets[0]))] = ast.dump(n)
    return out
o = defs(orig_file); nw = {}
for p in new_glob:
    for k, v in defs(p).items():
        if k in nw and k[0] != "A": print("DUP", k, p)
        nw[k] = v
miss = [k for k in o if k not in nw]; diff = [k for k in o if k in nw and nw[k] != o[k]]
extra = [k for k in nw if k not in o]
print("orig:", len(o), "missing:", miss, "changed:", diff, "extra:", extra)
