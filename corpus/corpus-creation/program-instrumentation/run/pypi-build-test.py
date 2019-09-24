#!/usr/bin/env python3
# Build and test a pypi module.

# Import libLF
import os
import sys
import re
sys.path.append('{}/lib'.format(os.environ['REGEX_GENERALIZABILITY_PROJECT_ROOT']))
import libLF
import argparse
import subprocess
import sys
import json
import stat
import shutil

#########
# Classes to drive the myriad python build systems

class BuildSystem:
  BUILD_SYSTEM_TOX = "tox"
  BUILD_SYSTEM_NOX = "nox"
  BUILD_SYSTEM_DISTUTILS = "setup.py"
  BUILD_SYSTEM_NOSE = "nose"
  BUILD_SYSTEM_PYTEST = "pytest"

  def __init__(self):
    self.name = None
    self.cli = None
    self.buildFile = None
  
  def findBuildDir(self, projRoot):
    if self.buildFile is not None:
      libLF.log("Searching for {} under {}".format(self.buildFile, projRoot))
      buildDir = self._findShallowestDirContaining(projRoot, self.buildFile)
      return buildDir
    return projRoot

  # Default: check for existence of a buildDir
  def isSupported(self, projRoot):
    return self.findBuildDir(projRoot) is not None
  
  # Subclasses must override this
  def tryBuild(self, projRoot, pythonBinary):
    """Return (compilationSucceeded, testsPassed)"""
    assert(not "Error, you must subclass and override this")
    return False

  def _findShallowestDirContaining(self, root, target):
    """Return the shallowest dir under root/ with a file named target

    None if no target found
    Tie goes to the first subdir visited by os.walk
    """
    minDepth = -1
    minTargetPath = None
    for dirpath, _, filenames in os.walk(root):
      if target in filenames:
        depth = len(dirpath.split(os.path.sep))
        if minDepth == -1 or depth < minDepth:
          minTargetPath = os.path.join(dirpath, target)
          minDepth = depth

    if minTargetPath is not None:
      return os.path.dirname(minTargetPath)
    return None
  
  def _cdToBuildDir(self, projRoot):
    bd = self.findBuildDir(projRoot)
    libLF.log("cd {}".format(bd))
    os.chdir(bd)

class BuildSystem_Tox(BuildSystem):
  def __init__(self):
    self.name = BuildSystem.BUILD_SYSTEM_TOX
    self.cli = shutil.which("tox")
    self.buildFile = "tox.ini"
  
  def tryBuild(self, projRoot, pythonBinary):
    if self.cli is not None:
      self._cdToBuildDir(projRoot)

      fullCmd = "{} {}".format(pythonBinary, self.cli)
      libLF.log("CMD: {}".format(fullCmd))
      cmdWords = fullCmd.strip().split(" ")

      res = subprocess.run(cmdWords)
      return res.returncode == 0
    return False

class BuildSystem_Nox(BuildSystem):
  def __init__(self):
    self.name = BuildSystem.BUILD_SYSTEM_NOX
    self.cli = shutil.which("nox")
    self.buildFile = "noxfile.py"
  
  def tryBuild(self, projRoot, pythonBinary):
    if self.cli is not None:
      self._cdToBuildDir(projRoot)

      fullCmd = "{} {}".format(pythonBinary, self.cli)
      libLF.log("CMD: {}".format(fullCmd))
      cmdWords = fullCmd.strip().split(" ")

      res = subprocess.run(cmdWords)
      return res.returncode == 0
    return False

class BuildSystem_DistUtils(BuildSystem):
  def __init__(self):
    self.name = BuildSystem.BUILD_SYSTEM_DISTUTILS
    self.buildFile = "setup.py"
  
  def tryBuild(self, projRoot, pythonBinary):
    self._cdToBuildDir(projRoot)

    fullCmd = "{} {} test".format(pythonBinary, self.buildFile)
    libLF.log("CMD: {}".format(fullCmd))
    cmdWords = fullCmd.strip().split(" ")

    res = subprocess.run(cmdWords)
    return res.returncode == 0

class BuildSystem_Nose(BuildSystem):
  def __init__(self):
    self.name = BuildSystem.BUILD_SYSTEM_NOSE
    self.cli = shutil.which("nosetests")
    self.buildFile = None
  
  def tryBuild(self, projRoot, pythonBinary):
    if self.cli is not None:
      os.chdir(projRoot)

      fullCmd = "{} {}".format(pythonBinary, self.cli)
      libLF.log("CMD: {}".format(fullCmd))
      cmdWords = fullCmd.strip().split(" ")

      res = subprocess.run(cmdWords)
      return res.returncode == 0
    return False

class BuildSystem_Pytest(BuildSystem):
  def __init__(self):
    self.name = BuildSystem.BUILD_SYSTEM_PYTEST
    self.cli = shutil.which("pytest")
    self.buildFile = None
  
  def tryBuild(self, projRoot, pythonBinary):
    if self.cli is not None:
      os.chdir(projRoot)

      fullCmd = "{} {}".format(pythonBinary, self.cli)
      libLF.log("CMD: {}".format(fullCmd))
      cmdWords = fullCmd.strip().split(" ")

      res = subprocess.run(cmdWords)
      return res.returncode == 0
    return False

# Ordered from cheapest to most expensive
BUILD_SYSTEMS = [
  # Cheap and easy
  BuildSystem_DistUtils(),
  BuildSystem_Nose(), BuildSystem_Pytest(),
  # Expensive but more consistent
  BuildSystem_Tox(), BuildSystem_Nox(),
  ]

### Utilities

def getAvailablePythonBinaries():
  optionShortNames = ["python2", "python3"]
  availablePythonBinaries = []
  for osn in optionShortNames:
    w = shutil.which(osn)
    if w is not None:
      availablePythonBinaries.append(w)
  return availablePythonBinaries

def determineAvailableBuildSystems(root):
  """Return subset of BUILD_SYSTEMS, or exits if none work"""
  availableBuildSystems = [
    bs
    for bs in BUILD_SYSTEMS
    if bs.isSupported(root)
  ]

  if availableBuildSystems:
    libLF.log("Available build systems: {}".format([bs.name for bs in availableBuildSystems]))
    return availableBuildSystems
  else:
    libLF.log("Error, no available build systems")
    sys.exit(1)

###########
# main

def main(pypiProjDir):
  # Which python's do we have?
  pythonBinaries = getAvailablePythonBinaries()
  if not pythonBinaries:
    libLF.log("Error, could not find any available python binaries")
    sys.exit(1)
  libLF.log("Available python binaries: {}".format(pythonBinaries))

  # Which build system(s) might work on this project?
  availableBuildSystems = determineAvailableBuildSystems(pypiProjDir)

  # Give it a whirl
  for buildSystem in availableBuildSystems:
    for pythonBin in pythonBinaries:
      libLF.log("Testing with python {}, buildSystem {}".format(pythonBin, buildSystem.name))
      testsPassed = buildSystem.tryBuild(pypiProjDir, pythonBin)
      if testsPassed:
        libLF.log("Tests ran and passed (python {})".format(pythonBin))
        # Don't exit in triump.
        # "python setup.py test" often returns after executing 0 tests because it can't find them.
        # Easier to just try to run the test suite using every available build system.
      else:
        libLF.log("Tests did not run, or ran and failed (python {})".format(pythonBin))

  libLF.log("Finished attempting tests")
  sys.exit(0)

##################

if __name__ == '__main__':
  # Parse args
  parser = argparse.ArgumentParser(description='Build and run the test suite of a Python project that uses the distutils, tox, or nox distribution system.')
  parser.add_argument('--proj-dir',  help='Project root dir', required=True, dest='projDir')

  args = parser.parse_args()

  # Here we go!
  main(args.projDir)
