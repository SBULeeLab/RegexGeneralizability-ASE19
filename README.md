[![DOI](https://zenodo.org/badge/208951153.svg)](https://zenodo.org/badge/latestdoi/208951153)

# Regex Generalizability

Welcome to the artifact for the ASE'19 paper [*"Testing Regex Generalizability And Its Implications: A Large-Scale Many-Language Measurement Study"*](https://people.cs.vt.edu/davisjam/downloads/publications/DavisMoyerKazerouniLee-RegexGeneralizability-ASE19.pdf), by J.C. Davis, D. Moyer, A.M. Kazerouni, all of Virginia Tech, and D. Lee, of Stony Brook University and Virginia Tech.

This paper describes our study on regex generalizability across programming languages.
In this empirical work we:
- Compared two competing methodologies for regex extraction. We found that the two approaches yield different (but comparable) regexes
- Compared regexes extracted from software written in different programming languages. We found that in some metrics these regexes are similar, while in other metrics they differ.
- Replicated prior research. We describe replicable and non-replicable research and methodological subtleties.

## Artifact

This artifact includes the following:

| Item | Description | Corresponding content in the paper | Scientific interest | Relation to prior work |
|------|-------------|---------------------|------------------------------------|------------------------|
| Regex measurement instruments | Instruments to characterize a regex using the metrics in the paper | Section 4 | Comprehensive regex metrics | Unifies metrics from several previous works |
| Multi-method regex corpus | Corpus containing regexes extracted using both static analysis and program instrumentation | Section 5 | Permits comparison of regex extraction methodology | Prior work followed one of these methods. They have not previously been compared. |
| Measured corpuses | Regex patterns with accompanying measurements, for the two regex corpuses studied | Section 5, 6 | Experimental results | Measures of old and new metrics on corpuses |

In addition to this directory's `README.md`, each sub-tree comes with one or more READMEs describing its contents.

## Dependencies

Export the following environment variables to ensure the tools know how to find each other.
- `REGEX_GENERALIZABILITY_PROJECT_ROOT` (set to wherever you cloned this repo)
- `VULN_REGEX_DETECTOR_ROOT` (dependency, set it to `REGEX_GENERALIZABILITY_PROJECT_ROOT/measurement-instruments/worst-case-performance/performance/vuln-regex-detector`)

See `.env` for examples.

## Installation

### By hand

To install, execute the script `./configure.sh` on an Ubuntu 16.04 machine with root privileges.
This will obtain and install the various dependencies (e.g. OS packages, REDOS detectors) and compile all analysis tools.

The final line of this script is `echo "Configuration complete. I hope everything works!"`.
If you see this printed to the console, great!
Otherwise...alas.

## Use

### One stop shop

We have prepared a script to compute various metrics on a set of regexes from a single node.
The actual analyses were performed on a compute cluster, as detailed in the paper.

To use this script, run the following command and wait about 10 minutes for all of the phases to complete.

TODO XXX

## Contact

Contact J.C. Davis at davisjam@vt.edu with any questions.
