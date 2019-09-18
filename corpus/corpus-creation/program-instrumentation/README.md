# program-instrumentation

Extract regexes using program instrumentation.

`dyn-regex-extractor.py` is a language-independent driver.

## Algorithm

This extraction methodology follows these steps:

| Step | Subdirectory |
|------|--------------|
| 1. Instrument the software being studied                                | `instrument/` |
| 2. Perform preprocessing meant to handle issues due to instrumentation (e.g. remove linting stages) | `preprocess/` |
| 3. Install dependencies for the software, build, and run the test suite | `run/`        |

## Structure

Each subdirectory has a script for each software registry considered in our experiment.
