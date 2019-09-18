# python

1. `extract-regexps.py`, `instrument-regexps.py`
  These builds an AST of an input file, walks the AST, and { emit, instrument } the regexps they find.

  We parse python using the built-in python parser ([python2](https://docs.python.org/2/library/ast.html), [python3]](https://docs.python.org/3/library/ast.html)).
  As described [here](https://stackoverflow.com/questions/26655818/how-to-parse-python-2-x-with-python-3-x-ast-module), this uses the same parser as the interpreter running the program.

  Alas, Python2 syntax and Python3 syntax are not entirely compatible.
  Thus, if you run `extract-regexps.py` with a python3 interpreter and try to parse a python2-based python, the parse may fail.

  You should probably not invoke these programs directly.

2. `python-extract-regexps-wrapper.pl`, `python-instrument-regexps-wrapper.pl`

  This attempts { `extract-regexps.py`, `instrument-regexps.py` }.
	First it tries python2. If that fails it tries python3.
  On complete failure it emits a simple object of the form { filename: X, 'couldParse': 0 }.
