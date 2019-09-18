# static-analysis

Extract regexes using static analysis.

`static-regex-extractor.py` is a language-independent driver.

## Algorithm

This extraction methodology follows these steps:

1. Parse the software being studied and build an AST 
2. Walk the AST looking for regex creation sites
3. At each such site, emit the regex pattern

These extraction tools perform no dataflow analysis.
- If the regex pattern is a constant string, it is emitted.
- Otherwise, it is ignored

## Structure

Subdirectories hold specific extractor scripts.

Each language-specific extractor should emit NDJSON results of libLF.SimpleFileWithRegexes.
