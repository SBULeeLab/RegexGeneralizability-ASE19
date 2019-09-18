#!/usr/bin/env python3
# Description:
#   Extract regexes from a set of libLF GitHubProjects.
#   Can extract statically and/or dynamically.
#     static:  regex-extractor.py
#     dynamic: dyn-regex-extractor.py
#   This is compute intensive -- lots of parsing and tree walking.
#   Uses libLF.parallel to expedite the process.

# Import libLF
import os
import sys
import re
sys.path.append('{}/lib'.format(os.environ['REGEX_GENERALIZABILITY_PROJECT_ROOT']))
import libLF

import argparse
import json
import tempfile
import subprocess

################
# Globals

class ExtractionMode:
  """Represents an extraction request
  
  Fields:
    extractionType: str: static or dynamic
    timeout: int: 0 means no timeout, otherwise abort extraction after this many seconds
  """
  STATIC = "STATIC"
  DYNAMIC = "DYNAMIC"
  EXTRACTION_TYPES = [STATIC, DYNAMIC]
  def __init__(self, extractionType, timeout):
    assert(extractionType in ExtractionMode.EXTRACTION_TYPES)
    self.extractionType = extractionType
    self.timeout = timeout

# Dependencies
staticRegexExtractorCLI = os.path.join(os.environ['REGEX_GENERALIZABILITY_PROJECT_ROOT'], 'bin', 'static-regex-extractor.py')
dynamicRegexExtractorCLI = os.path.join(os.environ['REGEX_GENERALIZABILITY_PROJECT_ROOT'], 'bin', 'dyn-regex-extractor.py')

# Logging
DELETE_TMP_FILES = False # NB: tmp files are preserved on failures

################

class MyTask(libLF.parallel.ParallelTask):
  def __init__(self, githubProject, extractionModes):
    self.ghp = githubProject
    self.extractionModes = extractionModes
  
  def _staticRegexFileName(self):
    filename, _ = os.path.splitext(self.ghp.tarballPath)
    return filename + '-DR-static-regexes.json'

  def _dynamicRegexFileName(self):
    filename, _ = os.path.splitext(self.ghp.tarballPath)
    return filename + '-DR-dynamic-regexes.json'
  
  def run(self):
    try:
      libLF.log('Working on: {}/{}'.format(self.ghp.owner, self.ghp.name))

      # run the extractor
      libLF.log('Running the {} extractor'.format(self.ghp.registry))
      regexFiles = []
      nRegexes = {}
      for extractionMode in self.extractionModes:
        if extractionMode.extractionType == ExtractionMode.STATIC:
          regexFile = self._staticRegexFileName()
          libLF.log("Statically extracting regexes. Writing to {}".format(regexFile))
          try:
            self._extractStatic(regexFile, extractionMode.timeout)
          except BaseException as e:
            libLF.log("Exception doing static extraction")
            libLF.log(e)
          self.ghp.regexPath = regexFile
          regexFiles.append(regexFile)
          nRegexes[ExtractionMode.STATIC] = libLF.numLinesInFile(regexFile)
          libLF.log("Static extraction finished ({} regexes)".format(nRegexes[ExtractionMode.STATIC]))

        elif extractionMode.extractionType == ExtractionMode.DYNAMIC:
          regexFile = self._dynamicRegexFileName()
          libLF.log("Dynamically extracting regexes. Writing to {}".format(regexFile))
          try:
            self._extractDynamic(regexFile, extractionMode.timeout)
          except BaseException as e:
            libLF.log("Exception doing dynamic extraction")
            libLF.log(e)
          self.ghp.dynRegexPath = regexFile
          regexFiles.append(regexFile)
          nRegexes[ExtractionMode.DYNAMIC] = libLF.numLinesInFile(regexFile)
          libLF.log("Dynamic extraction finished ({} regexes)".format(nRegexes[ExtractionMode.DYNAMIC]))
      
      libLF.log('Finished working on {}/{}. Regexes written to {} (nRegexes: {})' \
        .format(self.ghp.owner, self.ghp.name, regexFiles, nRegexes))

      # Return
      libLF.log('Completed project: {}'.format(self.ghp.toNDJSON()))
      return self.ghp
    except KeyboardInterrupt:
      raise
    except BaseException as err:
      libLF.log(err)
      return err

  def _extractStatic(self, outputFile, timeout):
    """Static regex extraction"""
    cmd = [staticRegexExtractorCLI,
      "--out-file", outputFile,
      "--registry", self.ghp.registry,
      "--src-path", self.ghp.tarballPath
      ]
    fd, logFileName = tempfile.mkstemp(prefix="extract-regexes-static-log", suffix=".log")
    os.close(fd)
    with open(logFileName, 'w') as logFile:
      libLF.log("CMD: {} > {} 2>&1".format(" ".join(cmd), logFileName))
      rc = 1
      try:
        tmo = None if timeout <= 0 else timeout
        res = subprocess.run(cmd, stdout=logFile, stderr=logFile, timeout=tmo)
        rc = res.returncode
      except subprocess.TimeoutExpired:
        libLF.log("Static extraction timed out")
        rc = -1

    if rc != 0:
      raise IOError('Error, static extractor yielded rc {}. Examine {}'.format(rc, logFileName))

    if DELETE_TMP_FILES:
      os.unlink(logFileName)

  def _extractDynamic(self, outputFile, timeout):
    """Dynamic regex extraction"""
    # Prep GHP file
    fd, queryFileName = tempfile.mkstemp(suffix=".json", prefix="extract-regexes-GHP-")
    os.close(fd)
    with open(queryFileName, 'w') as queryFile:
      queryFile.write(self.ghp.toNDJSON())

    # Run dynamic extractor
    fd, logFileName = tempfile.mkstemp(prefix="extract-regexes-dynamic-log", suffix=".log")
    os.close(fd)
    cmd = [dynamicRegexExtractorCLI,
      "--ghp-file", queryFileName,
      "--out-file", outputFile
      ]
    with open(logFileName, 'w') as logFile:
      libLF.log("CMD: {} > {} 2>&1".format(" ".join(cmd), logFileName))
      rc = 1
      try:
        tmo = None if timeout <= 0 else timeout
        res = subprocess.run(cmd, stdout=logFile, stderr=logFile, timeout=tmo)
        rc = res.returncode
      except subprocess.TimeoutExpired:
        libLF.log("Dynamic extraction timed out")
        rc = -1

    if rc != 0:
      raise IOError('Error, dynamic extractor yielded rc {}. Examine {}'.format(rc, logFileName))

    if DELETE_TMP_FILES:
      os.unlink(queryFileName)
      os.unlink(logFileName)

def getTasks(projectFile, extractionModes):
  ghps = getGHPs(projectFile)
  tasks = [MyTask(ghp, extractionModes) for ghp in ghps]
  libLF.log('Prepared {} tasks'.format(len(tasks)))
  return tasks

def getGHPs(projectFile):
  ghps = []
  with open(projectFile, 'r') as inStream:
    for line in inStream:
      line = line.strip()
      if len(line) == 0:
        continue
      
      try:
        # Build a GitHubProject
        ghp = libLF.GitHubProject().initFromJSON(line)
        ghps.append(ghp)
      except KeyboardInterrupt:
        raise
      except BaseException as err:
        libLF.log('Exception parsing line:\n  {}\n  {}'.format(line, err))

    libLF.log('Loaded {} ghps'.format(len(ghps)))
    return ghps

#################################################

def main(projectFile, extractionModes, outFile, nWorkers):
  libLF.log("projectFile {} extractionModes {} outFile {} nWorkers {}" \
    .format(projectFile, [em.extractionType for em in extractionModes], outFile, nWorkers))

  tasks = getTasks(projectFile, extractionModes)
  libLF.log("Collected {} tasks".format(len(tasks)))

  # CPU-bound, no limits
  libLF.log('Submitting to imap')
  libLF.log('Emitting results to {} as they come in'.format(outFile))
  nSuccesses = 0
  nExceptions = 0
  LINE_BUFFERING = 1
  with open(outFile, 'w', buffering=LINE_BUFFERING) as outStream:
    for maybeGHP in libLF.parallel.imap_unordered_genr(tasks, nWorkers, libLF.parallel.RateLimitEnums.NO_RATE_LIMIT, libLF.parallel.RateLimitEnums.NO_RATE_LIMIT, jitter=False):
      libLF.log("Got a result")
      # Emit
      if type(maybeGHP) is libLF.GitHubProject:
        libLF.log("Succeeded on {}/{}".format(maybeGHP.owner, maybeGHP.name))
        nSuccesses += 1
        outStream.write(maybeGHP.toNDJSON() + '\n')
      else:
        libLF.log("Failed")
        nExceptions += 1
    libLF.log('Extracted regexes from {} libLF.GitHubProject\'s, {} exceptions'.format(nSuccesses, nExceptions))

###############################################

if __name__ == '__main__':
  # Parse args
  parser = argparse.ArgumentParser(description='Extract regexes from a list of GitHubProject\'s. They should have tarballPath set. The extracted regexes are written to a file next to the tarball. Input order is not preserved. If a GHP times out, it is not emitted.')
  parser.add_argument('--project-file', help='File containing NDJSON of GitHubProject\'s', required=True, dest='projectFile')
  parser.add_argument('--static', help='Statically extract regexes', action='store_true', required=False, dest='static')
  parser.add_argument('--static-timeout', help='Timeout (sec) for statically extracting regexes', type=int, required=False, default=0, dest='staticTimeout')
  parser.add_argument('--dynamic', help='Dynamically extract regexes', action='store_true', required=False, dest='dynamic')
  parser.add_argument('--dynamic-timeout', help='Timeout (sec) for dynamically extracting regexes', type=int, required=False, default=0, dest='dynamicTimeout')
  parser.add_argument('--out-file', '-o', help='Where to write NDJSON results? These are updated GitHubProject\'s with the regexPath and/or dynRegexPath set', required=True, dest='outFile')
  parser.add_argument('--parallelism', '-p', help='Maximum cores to use', type=int, required=False, default=libLF.parallel.CPUCount.CPU_BOUND)
  args = parser.parse_args()

  extractionModes = []
  if args.static:
    mode = ExtractionMode(ExtractionMode.STATIC, args.staticTimeout)
    extractionModes.append(mode)
  if args.dynamic:
    mode = ExtractionMode(ExtractionMode.DYNAMIC, args.dynamicTimeout)
    extractionModes.append(mode)

  if not extractionModes:
    libLF.log("Usage: must provide --static or --dynamic (or both!)")
    sys.exit(1)

  # Here we go!
  main(args.projectFile, extractionModes, args.outFile, args.parallelism)
