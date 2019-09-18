#!/usr/bin/env python3
# Build and test an npm module.
# Exits with 1 if any of the "npm run test"-style commands exits non-zero

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

##############

NPM_CLI = 'npm'
libLF.checkShellDependencies([NPM_CLI], mustBeExecutable=True)

def main(npmProjDir):
  # cd to the dir
  libLF.log("cd {}".format(npmProjDir))
  os.chdir(npmProjDir)

  # Install dependencies
  libLF.log("CMD: {} install".format(NPM_CLI))
  subprocess.run([NPM_CLI, "install"])

  # Run the npm build and test command sequence
  fullInstallCmds = [
    "{} install".format(NPM_CLI) 
  ]
  for cmd in fullInstallCmds:
    libLF.log("CMD: {}".format(cmd))
    cmdWords = cmd.split(" ")
    subprocess.run(cmdWords)
  
  # Run build and test stages, if any
  optionalStages = {
    "build": ["build"],
    "test": ["unit", "test"],
  }
  optionalStageOrder = ["build", "test"]

  with open('package.json', 'r') as pkg:
    cfg = json.load(pkg)
    if "scripts" in cfg:
      cfgScripts = cfg["scripts"]
    elif "script" in cfg:
      cfgScripts = cfg["script"]
    else:
      cfgScripts = None
    
    # Track return codes
    npmCmdRC = {}
    if cfgScripts: 
      # Run the optional stages, if any
      for stage in optionalStageOrder:
        for cmd in optionalStages[stage]:
          if cmd in cfgScripts:
            fullCmd = "{} run {}".format(NPM_CLI, cmd)

            libLF.log("CMD: {}".format(fullCmd))
            cmdWords = fullCmd.split(" ")
            res = subprocess.run(cmdWords)

            libLF.log("rc {}".format(res.returncode))
            npmCmdRC[cmd] = res.returncode

  # Exit 1 if any test commands yielded non-zero rc
  for cmd in optionalStages["test"]:
    if cmd in npmCmdRC and npmCmdRC[cmd] != 0:
      sys.exit(1)
  sys.exit(0)

##################

if __name__ == '__main__':
  # Parse args
  parser = argparse.ArgumentParser(description='Build and run the test suite of an npm-managed project')
  parser.add_argument('--proj-dir',  help='Project root dir', required=True, dest='projDir')

  args = parser.parse_args()

  # Here we go!
  main(args.projDir)