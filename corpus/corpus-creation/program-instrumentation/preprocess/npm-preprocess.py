#!/usr/bin/env python3
# Preprocessing for an npm module before instrumenting and running

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

def haveGitignoreStyleFileIgnoreAllJS(f):
  with open(f, 'a') as ignoreFile:
    ignoreFile.write("\n\n{}\n{}\n{}\n".format(
      "# Ignore all JS files",
      "# (added for dynamic instrumentation)",
      "**/*.js"))

def configureEslintToIgnoreAll():
  # eslint: https://eslint.org/docs/user-guide/configuring.html#eslintignore
  haveGitignoreStyleFileIgnoreAllJS(".eslintignore")

def configureStandardToIgnoreAll():
  # standard: https://www.npmjs.com/package/standard#how-do-i-ignore-files
  haveGitignoreStyleFileIgnoreAllJS(".gitignore")

def configureJSCSToIgnoreAll():
  # jscs: https://github.com/jscs-dev/node-jscs/blob/master/OVERVIEW.md#excludefiles
  configFile = ".jscsrc"
  if os.path.isfile(configFile):
    with open(configFile, "r") as _cfg:
      cfg = json.load(_cfg)
  else:
    cfg = {}
  
  if "excludeFiles" not in cfg:
    cfg["excludeFiles"] = []
  cfg["excludeFiles"].append("**/*.js")

  with open(configFile, "w") as _cfg:
    json.dump(cfg, _cfg)

def removeLinterFromPackageJsonStages(stages):
  try:
    with open('package.json', 'r', encoding="utf-8") as pkg:
      cfg = json.load(pkg)
      if "scripts" in cfg:
        for stage in stages:
          if stage in cfg["scripts"]:
            cfg["scripts"][stage] = cfg["scripts"][stage] \
              .replace("npm run lint && ", "") \
              .replace("npm run lint;", "")
    
    with open('package.json', 'w') as pkg:
      json.dump(cfg, pkg)
  except BaseException as e:
    libLF.log("removeLinterFromPackageJsonStages: Error manipulating package.json: {}".format(e))

def configureLintersToIgnore():
  # First effort: try to remove calls to linting from primary stages
  libLF.log("Removing linter from package.json stages")
  removeLinterFromPackageJsonStages(["build", "test", "unit"])

  # Backup plan: change linter configurations to ignore js files 
  libLF.log("Configuring linter: eslint")
  configureEslintToIgnoreAll()
  libLF.log("Configuring linter: standard")
  configureStandardToIgnoreAll()
  libLF.log("Configuring linter: JSCS")
  configureJSCSToIgnoreAll()

def main(npmProjDir):
  # cd to the dir
  libLF.log("cd {}".format(npmProjDir))
  os.chdir(npmProjDir)

  configureLintersToIgnore()

##################

# Parse args
parser = argparse.ArgumentParser(description='Pre-processing for an npm-managed project')
parser.add_argument('--proj-dir',  help='Project root dir', required=True, dest='projDir')

args = parser.parse_args()

# Here we go!
main(args.projDir)