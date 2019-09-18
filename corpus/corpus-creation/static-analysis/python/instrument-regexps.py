from __future__ import print_function
import ast
import astor # Convert AST to source
import json
import sys

sourceFile = ''
outputFile = ''

# If you import re, these are the methods you might call on it.
regexpFuncNames = ['compile', 'search', 'match', 'fullmatch', 'split', 'findall', 'finditer', 'sub', 'subn', 'escape']


def log(msg):
    sys.stderr.write('{}\n'.format(msg))


# Wrap the given regex node with the instrumentation template.
def instrumentNode(node):
    # Create AST node for lambda function that writes a regex to a file and
    # returns it. Since lambda functions do not allow statements, wrap the file
    # methods in a tuple expression.
    templateCode = r"""lambda regex, flags, f, srcFile, json:(f.write(json.dumps({"file": srcFile, "pattern": regex, "flags": flags}) + '\n'), f.close(), regex)[2]"""
    template = ast.parse(templateCode, mode='eval')

    # Create AST node for call to open() for writing to the regex file.
    openCall = ast.Call(func=ast.Name(id='open', cxt=ast.Load()),
        args=[ast.Str(outputFile), ast.Str('a')], keywords=[])

    # Create AST node for call to __import__() to pass the json library to the
    # lambda since we can't use an import statement in a lambda body.
    importCall = ast.Call(func=ast.Name(id='__import__', cxt=ast.Load()),
        args=[ast.Str('json')], keywords=[])

    # Create AST node to immediately call the lambda function. Pass the original
    # regex node, flags (unimplemented), the open() call, and soure file name to
    # the lambda function.
    return ast.Call(func=template, args=[node, ast.Str('UNKNOWN'), openCall, ast.Str(sourceFile), importCall], keywords=[])

# Walk full AST for regexps
class RegexInstrumentor(ast.NodeTransformer):
    def __init__(self):
        self.reAliases = list()

    # ImportFrom: Detect missed aliases for re functions
    def visit_ImportFrom(self, node):
        if node.module == 're':
            log('Potentially-missed regexps: ImportFrom re: {}'.format(ast.dump(node)))
        return node

    # Import: Detect aliases for the re module
    def visit_Import(self, node):
        try:
            for alias in node.names:
                if alias.name == 're':
                    if alias.asname == None:
                        name = alias.name
                    else:
                        name = alias.asname

                    log('New alias for re: {}'.format(name))
                    self.reAliases.append(name)
        except:
            pass
        return node

    def visit_Call(self, node):
        try:
          # Is this a call of the form x.y, where x is an re alias and y is a regexpFuncName?
          if isinstance(node.func, ast.Attribute):
              funcID = node.func.value.id
              funcName = node.func.attr

              if funcID in self.reAliases and funcName in regexpFuncNames:
                  node.args[0] = instrumentNode(node.args[0])
        except Exception as e:
            log(e)
            pass

        # Recurse
        self.generic_visit(node)

        return node


# Usage
if len(sys.argv) != 3:
    log('Usage: {} source-to-instrument.py regex-log-file'.format(sys.argv[0]))
    sys.exit(1)

sourceFile = sys.argv[1]
outputFile = sys.argv[2]

# Read file and prep an AST.
try:
    with open(sourceFile, 'r') as f:
        tree = ast.parse(f.read(), sourceFile)
        instrumentedTree = RegexInstrumentor().visit(tree)
        ast.fix_missing_locations(instrumentedTree)
        print(astor.to_source(tree))

except Exception as e:
    # Easy-to-parse to stdout
    log(e)
    log('Could not instrument file.')
    sys.exit(1)
