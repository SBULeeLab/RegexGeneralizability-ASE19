#!/usr/bin/env python3
# Convert Wang18's regex data into libLF.Regex format for comparison

# Import libLF
import os
import sys
import re
sys.path.append(os.path.join(os.environ['ECOSYSTEM_REGEXP_PROJECT_ROOT'], 'lib'))
import libLF

import json
import tempfile
import argparse
import traceback

import numpy as np

import csv

################

def wangPatternToLibLFRegex(pattern):
  return libLF.Regex().initFromRaw(
    pattern,
    {}, {}
  )

def buildFile2patterns(csvDir):
  """Return map from filename to set of unique patterns that appear in it"""
  file2patterns = {} # { filename: set(pattern, ...) }
  for fileName in os.listdir(csvDir):
    fullPath = os.path.join(csvDir, fileName)
    if fullPath.endswith(".csv"):
      libLF.log("Processing: {}".format(fullPath))
      with open(fullPath) as csvfile:
        line = 0
        try:
          reader = csv.DictReader(csvfile)
          for row in reader:
            line += 1
            if row['file'] not in file2patterns:
              file2patterns[row['file']] = set()
            file2patterns[row['file']].add(row['regex'])
        except BaseException as e:
          libLF.log("Exception handling line {} in {}".format(line, fullPath))
          libLF.log(e)
  return file2patterns

def filterOutlierFiles(file2patterns, countPercentileCutoff):
  """Return file2patterns for non-outlier files"""
  if countPercentileCutoff <= 0 or 100 <= countPercentileCutoff:
    # Ways to say "don't discard any"
    return file2patterns
  
  # Identify outlier files
  fileAndNUniqueRegexes = []
  for f in file2patterns:
    fileAndNUniqueRegexes.append( (f, len(file2patterns[f])) )
  # Sort from fewest to most regexes so that we can use percentile indexing
  fileAndNUniqueRegexes.sort(key=lambda x: x[1])
  
  counts = [x[1] for x in fileAndNUniqueRegexes]
  percentiles = [
    (p, np.percentile(counts, p, interpolation='lower'))
    for p in [10, 25, 50, 75, 90]
  ]
  libLF.log("regex percentiles: {}".format(percentiles))

  regCountAtCutoff = np.percentile(counts, countPercentileCutoff, interpolation='lower')
  cutoffIx = counts.index(regCountAtCutoff)
  libLF.log("You should omit the {} files above the {} p'ile (they have {} - {} unique regexes)" \
    .format(len(counts) - cutoffIx, countPercentileCutoff,
    counts[cutoffIx], counts[-1]))
  libLF.log("  Names of omitted files: {}".format([p[0] for p in fileAndNUniqueRegexes[cutoffIx:]]))
  
  nonOutlier_file2patterns = {}
  for f, _ in fileAndNUniqueRegexes[0:cutoffIx]:
    nonOutlier_file2patterns[f] = file2patterns[f]
  return nonOutlier_file2patterns

def main(wangCSVDir, filterOutliers, outFile):
  libLF.log('wangCSVDir {} filterOutliers {} outFile {}' \
    .format(wangCSVDir, filterOutliers, outFile))
 
  # Load data
  file2patterns = buildFile2patterns(wangCSVDir)

  # Filter outliers
  if filterOutliers:
    file2patterns = filterOutlierFiles(file2patterns, 99)
  
  # Build unique patterns across all files
  uniquePatterns = set()
  for patterns in file2patterns.values():
    for pattern in patterns:
      if pattern not in uniquePatterns:
        uniquePatterns.add(pattern)

  # Emit
  libLF.log("{} unique regexes".format(len(uniquePatterns)))
  with open(outFile, 'w') as outStream:
    for pattern in uniquePatterns:
      #libLF.log("pattern: /{}/".format(reg.pattern))
      reg = wangPatternToLibLFRegex(pattern)
      outStream.write(reg.toNDJSON() + '\n')
  libLF.log("Wrote all {} regexes to {}".format(len(uniquePatterns), outFile))

#####################################################

# Parse args
parser = argparse.ArgumentParser(description='Convert Wang18\'s data to libLF.Regex format')
parser.add_argument('--wang-csv-dir', type=str, help='In: Wang18\'s res_regex_merge/ dir', required=True,
  dest='wangCSVDir')
parser.add_argument('--filter-outliers', action='store_true', help='Filter outlier files -- 99%% and above ', default=False,
  dest='filterOutliers')
parser.add_argument('--out-file', type=str, help='Out: File of unique libLF.Regex objects', required=True,
  dest='outFile')
args = parser.parse_args()

# Here we go!
main(args.wangCSVDir, args.filterOutliers, args.outFile)
