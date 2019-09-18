#!/usr/bin/env python3
# Dynamically extract regexes from a tarball of the GitHubProject
# corresponding to a module in a registry of interest.
#
# Algorithm:
#   Pick a regex output file name 
#   Untar the tarball
#   Identify the source files (cloc)
#   Transform the source files in place
#   Run the appropriate "build + run tests" incantation
#   Retrieve the regexes from the regex output file
#   Update centralized regex DB
#   Clean up unpacked tarball
#
# To add a new registry, write the following plugins as CLIs:
#   1. Pre-processing: Any registry-specific operations
#        e.g., building a TS-based module so the 'lib/' directory has JS code we can instrument
#   2. Instrumentation: Rewrite a source file to emit regexes
#   3. Run tests: Build and run the module's test suite
# Put the paths into the relevant dictionaries below.

# Import libLF
import os
import sys
import re
sys.path.append('{}/lib'.format(os.environ['REGEX_GENERALIZABILITY_PROJECT_ROOT']))
import libLF
import argparse
import tarfile
import re
import subprocess
import shutil

import time
import tempfile

#######
# Globals
#######

CLEAN_TMP_DIR = True # TODO
DELETE_TMP_FILES = False # TODO
CLEAN_REGEX_FILE = True
REQUIRE_TESTS_PASS = False # TODO Ponder this

tmpFilePrefix = 'dyn-regex-extractor-{}-{}'.format(time.time(), os.getpid())

# Per-registry plugins
MODULE_HOME = os.path.join(os.environ['REGEX_GENERALIZABILITY_PROJECT_ROOT'], 'corpus', 'corpus-generation', 'program-instrumentation')
MODULE_PREPROCESSOR_DIR = os.path.join(MODULE_HOME, "preprocess")
MODULE_INSTRUMENTOR_DIR = os.path.join(MODULE_HOME, "instrument")
MODULE_RUN_DIR = os.path.join(MODULE_HOME, "run")

# CLI:
# Preprocessor: X --proj-dir DIR
# Instrumentor: X source-file regex-log-file
#   When the instrumented source file is executed,
#   it should emit NDJSON records with keys: file pattern flags
# Runner: X --proj-dir DIR
#   returncode: 0 if tests pass

registryToPaths = {
  # npm
  'npm': {
    'preprocessor': os.path.join(MODULE_PREPROCESSOR_DIR, 'npm-preprocess.py'),
    'instrumentor':  {
      'javascript': os.path.join(MODULE_INSTRUMENTOR_DIR, 'npm-instrument-js.js')
    },
    'instrumentorInvocationPrefix':  {
      'javascript': ''
    },
    'moduleRunner': os.path.join(MODULE_RUN_DIR, 'npm-build-test.py')
  },

  # maven
  'maven': {
    'preprocessor': os.path.join(MODULE_PREPROCESSOR_DIR, 'maven-preprocess.py'),
    'instrumentor':  {
      'java': os.path.join(MODULE_INSTRUMENTOR_DIR, 'maven-instrument-java.jar')
    },
    'instrumentorInvocationPrefix':  {
      'java': 'java -jar'
    },
    'moduleRunner': os.path.join(MODULE_RUN_DIR, 'maven-build-test.py')
  },

  # pypi
  'pypi': {
    'preprocessor': os.path.join(MODULE_PREPROCESSOR_DIR, 'pypi-preprocess.py'),
    'instrumentor':  {
      'python': os.path.join(MODULE_INSTRUMENTOR_DIR, 'python-instrument-regexps-wrapper.pl')
    },
    'instrumentorInvocationPrefix':  {
      'python': ''
    },
    'moduleRunner': os.path.join(MODULE_RUN_DIR, 'pypi-build-test.py')
  },
}

def checkRegistryDependencies(registry):
  libLF.checkShellDependencies(['cloc'], mustBeExecutable=True)

  paths = [
    registryToPaths[registry]['preprocessor'],
    *registryToPaths[registry]['instrumentor'].values(),
    registryToPaths[registry]['moduleRunner']
  ]
  libLF.log("Checking paths for registry {}: {}".format(registry, paths))
  libLF.checkShellDependencies(paths, mustBeExecutable=False)

#######
# I/O
#######

def loadGHPFile(ghpFile):
  """Returns libLF.GitHubProject[]"""
  ghps = []
  libLF.log('Loading GHPs from {}'.format(ghpFile))
  with open(ghpFile, 'r') as inStream:
    for line in inStream:
      line = line.strip()
      if len(line) == 0:
        continue
      
      try:
        # Build the GHP
        ghp = libLF.GitHubProject()
        ghp.initFromJSON(line)
        ghps.append(ghp)
      except KeyboardInterrupt:
        raise
      except BaseException as err:
        libLF.log('Exception parsing line:\n  {}\n  {}'.format(line, err))
  return ghps

#######
# Analysis stages
#######

def analyzeGHP(ghp):
  """Analyze this libLF.GitHubProject
  
  Returns:
    (testsPassed, libLF.RegexUsage[])
  """
  dynoRegexFileName = getRegexOutputFileName()
  libLF.log("{}/{} will use dyno regex file {}".format(ghp.owner, ghp.name, dynoRegexFileName))

  libLF.log("Untarring")
  untarDir = unpackTarball(ghp)
  libLF.log("Untarred to {}".format(untarDir))

  libLF.log("Running preprocessing stage")
  preprocessProject(ghp, untarDir)

  libLF.log("Finding source files")
  sourceFiles = getSourceFiles(ghp, untarDir)
  libLF.log("source files: {}".format(sourceFiles))

  libLF.log("Instrumenting source files")
  instrumentSourceFiles(ghp, sourceFiles, dynoRegexFileName)

  libLF.log("Running test suite")
  testsSucceeded = runTestSuite(ghp, untarDir)
  if testsSucceeded:
    libLF.log("Application test suite succeeded")
  else:
    libLF.log("Application test suite failed")

  regexes = []
  if testsSucceeded or not REQUIRE_TESTS_PASS:
    libLF.log("Retrieving regexes from {}".format(dynoRegexFileName))
    regexes = retrieveRegexes(dynoRegexFileName)

  libLF.log("Cleaning up untarDir {}".format(untarDir))
  cleanUp(untarDir, dynoRegexFileName)

  return testsSucceeded, regexes

###
#   Pick a regex output file name 
###
def getRegexOutputFileName():
  """Returns a unique file name for dynamic regexes"""
  now = time.time()
  fd, name = tempfile.mkstemp(suffix=".json", prefix=tmpFilePrefix + "-dyno-regexes")
  os.close(fd)
  return name

###
#   Untar the tarball
###

def unpackTarball(ghp):
  """Unpack tarball. Returns untarred root dir"""
  tmpDir = tempfile.mkdtemp(prefix=tmpFilePrefix + "-untar-dir-")
  libLF.log('Unpacking {} to {}'.format(ghp.tarballPath, tmpDir))
   
  with tarfile.open(ghp.tarballPath, "r:gz") as tar:
    tar.extractall(path=tmpDir) 
    return tmpDir

def preprocessProject(ghp, untarDir):
  """Prepocess project using the appropriate plugin"""
  preprocessor = registryToPaths[ghp.registry]['preprocessor']
  libLF.log
  projDir = getProjDir(untarDir)

  cmd = [preprocessor, "--proj-dir", projDir]
  libLF.log(" ".join(cmd))
  subprocess.run(cmd)

###
#   Identify the source files
###

def getSourceFiles(ghp, untarDir):
  """Return lang2sourceFiles for the languages in this registry"""
  return libLF.getUnvendoredSourceFiles(untarDir, ghp.registry)

###
#   Transform the source files in place
###

def instrumentSourceFiles(ghp, lang2sourceFiles, regexDumpFile):
  for lang, sourceFiles in lang2sourceFiles.items():
    if lang in registryToPaths[ghp.registry]['instrumentor']:
      instrumentor = registryToPaths[ghp.registry]['instrumentor'][lang]
      libLF.log("registry {}: instrumentor {}".format(ghp.registry, instrumentor))
      libLF.log("instrumentSourceFiles: instrumenting {} {} files".format(len(sourceFiles), lang))

      fd, tmpFileName = tempfile.mkstemp(suffix=".instrumented", prefix="dyno-regexes-tmpfile-")
      os.close(fd)
      fd, logFileName = tempfile.mkstemp(suffix=".log", prefix="dyno-regexes-tmpfile-")
      os.close(fd)
      for sourceFile in sourceFiles:
        # Replace each sourceFile with the instrumented version
        with open(tmpFileName, 'w') as tmpFile, open(logFileName, 'w') as logFile:
          invocationPrefix = registryToPaths[ghp.registry]['instrumentorInvocationPrefix'][lang]
          libLF.log("instrumenting file: {} {} {} {} > {} 2>{}" \
            .format(invocationPrefix, instrumentor,
                    sourceFile['name'], regexDumpFile, tmpFileName, logFileName))
          if len(invocationPrefix):
            cmdWords = [*invocationPrefix.split(" "), instrumentor, sourceFile['name'], regexDumpFile]
          else:
            cmdWords = [instrumentor, sourceFile['name'], regexDumpFile]
          res = subprocess.run(cmdWords, stdout=tmpFile, stderr=logFile)

          # If successful, replace the original
          if res.returncode == 0:
            libLF.log("cp {} {}".format(tmpFile.name, sourceFile['name']))
            shutil.copy(tmpFileName, sourceFile['name'])
          else:
            libLF.log("Error on file {}, preserving original".format(sourceFile['name']))

          if DELETE_TMP_FILES:
            os.unlink(tmpFileName)
            os.unlink(logFileName)
    else:
      libLF.log("instrument: no instrumentor for {}, skipping {} files".format(lang, len(sourceFiles)))

###
#   Run the appropriate "build + run tests" incantation
###

def getProjDir(untarRoot):
  """Return the project dir from this tarball.
  
  The tarball might contain solely a (series of) root dirs.
  That's what happens if you run "tar -czvf x.tgz cloneDir/".
  Could be extra layers too.

  If so we conclude that the project dir is the first dir containing more than just a dir.
  Otherwise (more than one dir file), we conclude that the untarRoot is the tarball.
  """
  files = list(os.scandir(untarRoot))
  nonDotFiles = [f for f in files if not f.name.startswith(".")]
  if len(nonDotFiles) == 1 and nonDotFiles[0].is_dir():
    # Recurse until we stop finding nested one-dir dirs
    return getProjDir(nonDotFiles[0].path)
  return untarRoot

def runTestSuite(ghp, untarDir):
  """Returns True if tests succeed, else False"""
  runner = registryToPaths[ghp.registry]['moduleRunner']

  projDir = getProjDir(untarDir)
  libLF.log("runTestSuite: untarDir {} projDir {}".format(untarDir, projDir))

  fd, logFile = tempfile.mkstemp(suffix=".log", prefix="moduleRunner-")
  os.close(fd)

  cmd = "{} --proj-dir {}".format(runner, projDir)
  libLF.log("CMD: {} > {} 2>&1".format(cmd, logFile))
  with open(logFile, 'w') as logStream:
    res = subprocess.run(cmd.split(" "), stdout=logStream, stderr=logStream)

  if DELETE_TMP_FILES:
    os.unlink(logFile)
  return res.returncode == 0

###
#   Retrieve the regexes from the regex output file
###
def retrieveRegexes(regexOutputFileName):
  """Returns libLF.RegexUsage[]

  (Since regexOutputFileName contains regexes from multiple source files,
  multiple files are represented in the returned libLF.RegexUsage[])

  Duplicates by <file, pattern> are removed.
  """

  libLF.log("Loading regexes from {}".format(regexOutputFileName))
  
  # Bin by file, removing duplicates
  file2uniqRegexes = {} # x[filename][pattern] = record
  with open(regexOutputFileName, mode='r') as regexStream:
    for line in regexStream:
      # Try to parse as NDJSON.
      # In Java we rely on a "poor man's JSON" implementation which may sometimes
      # produce malformed strings. In other languages, this should always work.
      try:
        obj = libLF.fromNDJSON(line)
      except:
        libLF.log("Could not fromNDJSON line: {}".format(line))
        continue

      if obj['file'] not in file2uniqRegexes:
        file2uniqRegexes[obj['file']] = {}
      file2uniqRegexes[obj['file']][obj['pattern']] = \
        {
          'pattern': obj['pattern'],
          'flags': obj['flags']
        }
  
  # Convert to libLF.RegexUsage[] via libLF.SimpleFileWithRegexes
  ruList = []
  for fileName in file2uniqRegexes:
    sfwr = libLF.SimpleFileWithRegexes().initFromRaw(
      fileName, "XXX", True, list(file2uniqRegexes[fileName].values())
    )
    ruList += libLF.sfwrToRegexUsageList(sfwr)

  return ruList

###
#   Clean up
###

def cleanUp(tmpDir, intermediateRegexFile):
  if CLEAN_TMP_DIR:
      libLF.log('cleanUp: Wiping tmpDir {}'.format(tmpDir))
      try:
          if os.path.isdir(tmpDir): # Make sure we don't touch tarballs
              shutil.rmtree(tmpDir)
      except:
          pass
  
  if CLEAN_REGEX_FILE:
    os.unlink(intermediateRegexFile)

#########################

def main(ghpFile, outFile):
  libLF.log('main: ghpFile {} outFile {}'.format(ghpFile, outFile))

  # Load GHPs
  libLF.log("main: Loading libLF.GitHubProject from {}".format(ghpFile))
  ghps = loadGHPFile(ghpFile)
  libLF.log("main: Loaded {} GHPs".format(len(ghps)))
  assert(len(ghps) == 1)
  ghp = ghps[0]

  # Check dependencies
  libLF.log("main: Checking dependencies for registry: {}".format(ghp.registry))
  checkRegistryDependencies(ghp.registry)
  
  # Off we go!
  libLF.log("main: Analyzing GHP")
  testsSucceeded, regexUsages = analyzeGHP(ghp)

  if testsSucceeded:
    libLF.log("main: All tests succeeded (rc 0)")
  else:
    libLF.log("main: Not all tests succeeded; some failed (rc was non-zero)")
  libLF.log("main: Emitting all {} captured libLF.RegexUsages to {}".format(len(regexUsages), outFile))
  with open(outFile, 'w') as outStream:
    for ru in regexUsages:
      ru.regexes = ghp.registry
      outStream.write(ru.toNDJSON() + '\n')

###############################################

# Parse args
parser = argparse.ArgumentParser(description='Dynamically extract regexes from a libLF.GitHubProject. Only regexes in the primary language of the project will be extracted. Extraction is performed by instrumenting the project source, installing its dependencies, and then running the test suite of the project. cf. ghp-extract-regexes.py')
parser.add_argument('--ghp-file', '-r',  help='File containing NDJSON of a libLF.GitHubProject', required=True, dest='ghpFile')
parser.add_argument('--out-file', '-o', help='Where to write NDJSON of libLF.RegexUsage[]', required=True, dest='outFile')

args = parser.parse_args()

# Here we go!
main(args.ghpFile, args.outFile)
