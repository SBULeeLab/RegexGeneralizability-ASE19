#!/usr/bin/env python3
# Preprocessing for a pypi module before instrumenting and running

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
import traceback

##################

def main(pypiProjDir):
  # cd to the dir
  libLF.log("cd {}".format(pypiProjDir))
  os.chdir(pypiProjDir)

  # TODO Anything else?
  
##################

if __name__ == '__main__':
  # Parse args
  parser = argparse.ArgumentParser(description='Pre-processing for a pypi-managed project')
  parser.add_argument('--proj-dir',  help='Project root dir', required=True, dest='projDir')

  args = parser.parse_args()

  # Here we go!
  main(args.projDir)
