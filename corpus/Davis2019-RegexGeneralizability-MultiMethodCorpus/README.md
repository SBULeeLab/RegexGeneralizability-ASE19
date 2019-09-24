# Davis2019-RegexGeneralizability-MultiMethodCorpus

The corpus generated during the experiment comparing the regex extraction methodologies.
Each line is a Regex type, serialized to NDJSON format.
Each Regex has two dictionaries indicating the extraction mode(s) in which we observed the regex.

`useCount_registry_to_nModules`: Found via static analysis
`useCount_registry_to_nModules_dynamic`: Found via program instrumentation
