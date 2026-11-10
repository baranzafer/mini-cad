import ast, sys, builtins, os
root=sys.argv[1]
bad=0
for fn in sorted(os.listdir(root)):
    if not fn.endswith(".py"): continue
    src=open(os.path.join(root,fn)).read()
    tree=ast.parse(src)
    defined=set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)): defined.add(node.name)
        elif isinstance(node,ast.Import):
            for a in node.names: defined.add((a.asname or a.name).split(".")[0])
        elif isinstance(node,ast.ImportFrom):
            for a in node.names: defined.add(a.asname or a.name)
        elif isinstance(node,ast.Name) and isinstance(node.ctx,(ast.Store,ast.Del)): defined.add(node.id)
        elif isinstance(node,ast.arg): defined.add(node.arg)
        elif isinstance(node,ast.ExceptHandler) and node.name: defined.add(node.name)
        elif isinstance(node,(ast.Global,ast.Nonlocal)): defined.update(node.names)
    defined.add("__file__"); defined.add("__package__"); defined.add("__name__")
    for node in ast.walk(tree):
        if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Load) and node.id not in defined:
            print(fn, node.lineno, node.id); bad+=1
print("undefined:",bad)
