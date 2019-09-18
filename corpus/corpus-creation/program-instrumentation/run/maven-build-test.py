#!/usr/bin/env python3
# Build and test a maven module.
# Exits with 1 if any of the "maven run test"-style commands exits non-zero

# Import libLF
import os
import sys
import re
sys.path.append('{}/lib'.format(os.environ['ECOSYSTEM_REGEXP_PROJECT_ROOT']))
import libLF
import argparse
import subprocess
import sys
import json
import stat

MAVEN_CLI = '/home/davisjam/local-install/apache-maven-3.6.0/bin/mvn'
MAVEN_CLI = 'mvn'
libLF.checkShellDependencies([MAVEN_CLI], mustBeExecutable=True)

GRADLE_USER_HOME = '/tmp/.gradle'

#########
# Classes to drive the Maven and Gradle build systems

class BuildSystem:
  BUILD_SYSTEM_MAVEN = "maven"
  BUILD_SYSTEM_GRADLE = "gradle"
  def __init__(self):
    self.name = None
    self.cli = None
    self.buildFile = None
  
  def findBuildDir(self, projRoot):
    libLF.log("Searching for {} under {}".format(self.buildFile, projRoot))
    buildDir = self._findShallowestDirContaining(projRoot, self.buildFile)
    return buildDir

  # Default: check for existence of a buildDir
  def isSupported(self, projRoot):
    return self.findBuildDir(projRoot) is not None
  
  # Subclasses must override this
  def tryBuild(self, projRoot, JAVA_HOME):
    """Return (compilationSucceeded, testsPassed)"""
    assert(not "Error, you must subclass and override this")
    return False, False

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

class BuildSystem_Maven(BuildSystem):
  def __init__(self):
    self.name = BuildSystem.BUILD_SYSTEM_MAVEN
    self.cli = MAVEN_CLI
    self.buildFile = "pom.xml"
  
  def tryBuild(self, projRoot, JAVA_HOME):
    self._cdToBuildDir(projRoot)
    os.environ["JAVA_HOME"] = JAVA_HOME

    # Run the maven build cycle up through "test"
    # https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
    cycleStages = [
      "clean", # Make sure that, e.g., prior JAVA_HOME did not corrupt the environment
      "validate",
      "compile",
      "test"
    ]
    compilationStages = ["compile"]
    testStages = ["test"]

    MAVEN_ARGS = [
      "-Drat.skip=true", # Release Audit Tool
      "-Dpmd.skip=true", # PMD code analysis tool (linter)
    ]

    mavenCmdRC = {}
    for stage in cycleStages:
      fullCmd = " ".join([self.cli, stage, *MAVEN_ARGS])

      libLF.log("CMD: JAVA_HOME={} {}".format(JAVA_HOME, fullCmd))
      cmdWords = fullCmd.split(" ")
      res = subprocess.run(cmdWords)
      libLF.log("rc {}".format(res.returncode))
      mavenCmdRC[stage] = res.returncode

    compilationWorked = True
    for s in compilationStages:
      if mavenCmdRC[s] != 0:
        compilationWorked = False
        break

    testsPassed = True
    for s in testStages:
      if mavenCmdRC[s] != 0:
        testsPassed = False
        break
    
    return compilationWorked, testsPassed

class BuildSystem_Gradle(BuildSystem):
  def __init__(self):
    self.name = BuildSystem.BUILD_SYSTEM_GRADLE
    self.cli = "./gradlew"
    self.buildFile = "gradlew"
  
  def tryBuild(self, projRoot, JAVA_HOME):
    self._cdToBuildDir(projRoot)

    # Set env vars, and track for printing commands later
    cmdLineEnvSettings = []
    os.environ["JAVA_HOME"] = JAVA_HOME
    cmdLineEnvSettings.append("JAVA_HOME={}".format(JAVA_HOME))

    os.environ["GRADLE_USER_HOME"] = GRADLE_USER_HOME
    cmdLineEnvSettings.append("GRADLE_USER_HOME={}".format(GRADLE_USER_HOME))

    cli = os.path.join(".", self.cli)
    # Make gradlew executable, just in case
    libLF.log("chmod +x {}".format(cli))
    st = os.stat(cli)
    os.chmod(cli, st.st_mode | stat.S_IEXEC)

    GRADLE_ARGS = [
      # Keep going even if tasks (e.g. linters) fail
      "--continue",
    ]

    # Run the gradle build cycle up through "test"
    # Gradle apps don't always distinguish cleanly between "compile" and "test".
    # I've seen variations on compile: assemble | compileJava
    # I've seen variations on test: test | check | build
    # But every app I've checked supports "build" as a catch-all compile+build.
    cycleStages = [
      "clean", # In case previous attempts left traces
      "build" # Common way to request compile+test
    ]

    # Set both to "build" -- all or nothing
    compilationStages = ["build"]
    testStages = ["build"]

    cmdRc = {}
    for stage in cycleStages:
      fullCmd = " ".join([cli, stage, *GRADLE_ARGS])

      libLF.log("CMD: {} {}".format(" ".join(cmdLineEnvSettings), fullCmd))
      cmdWords = fullCmd.strip().split(" ")
      res = subprocess.run(cmdWords)
      libLF.log("rc {}".format(res.returncode))
      cmdRc[stage] = res.returncode

    compilationWorked = True
    for s in compilationStages:
      if cmdRc[s] != 0:
        compilationWorked = False
        break

    testsPassed = True
    for s in testStages:
      if cmdRc[s] != 0:
        testsPassed = False
        break
    
    return compilationWorked, testsPassed


# Ordered from highest priority to lowest priority
BUILD_SYSTEMS = [BuildSystem_Maven(), BuildSystem_Gradle()]

### Utilities

def getAvailableJAVA_HOMES():
  # For system installs, grab the third column from update-java-alternatives --list 
  res = subprocess.run(['update-java-alternatives', '--list'], stdout=subprocess.PIPE, universal_newlines=True)
  javaAlternatives = []
  for line in res.stdout.split("\n"):
    line = line.strip()
    if not line:
      continue
    # Example line:
    # java-1.11.0-openjdk-amd64      1111       /usr/lib/jvm/java-1.11.0-openjdk-amd64
    match = re.match(r'(\S+)\s+(\S+)\s+(\S+)', line)
    if match:
      alternative = {
        'name': match.group(1),
        'vrmf': match.group(2),
        'home': match.group(3)
      }
      javaAlternatives.append(alternative)
  return [alt['home'] for alt in javaAlternatives]

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

def main(mavenProjDir):
  JAVA_HOMES = getAvailableJAVA_HOMES()
  libLF.log("JAVA_HOME's: {}".format(JAVA_HOMES))

  availableBuildSystems = determineAvailableBuildSystems(mavenProjDir)

  for buildSystem in availableBuildSystems:
    for jh in JAVA_HOMES:
      libLF.log("Testing with JAVA_HOME={}".format(jh))
      compilationWorked, testsPassed = buildSystem.tryBuild(mavenProjDir, jh)
      if testsPassed:
        libLF.log("Tests passed with JAVA_HOME={}".format(jh))
        sys.exit(0)
      elif compilationWorked:
        libLF.log("Tests failed but compilation passed with JAVA_HOME={}".format(jh))
      else:
        libLF.log("Could not compile with JAVA_HOME={}".format(jh))

    libLF.log("Could not get tests to pass using {}, under any of JAVA_HOME's {}".format(buildSystem.name, JAVA_HOMES))
  libLF.log("Could not get tests to pass under any of the availableBuildSystems {}".format([bs.name for bs in availableBuildSystems]))
  sys.exit(1)

##################

if __name__ == '__main__':
  # Parse args
  parser = argparse.ArgumentParser(description='Build and run the test suite of a Java project that uses the gradlew or mvn build systems. If you intend to build Android projects, set the appropriate environment (ANDROID_HOME=...)')
  parser.add_argument('--proj-dir',  help='Project root dir', required=True, dest='projDir')

  args = parser.parse_args()

  # Here we go!
  main(args.projDir)
