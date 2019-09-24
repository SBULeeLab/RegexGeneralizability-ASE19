#!/usr/bin/env python3
# Measure regexes on (some) metrics

# Import libLF
import os
import sys
import re
sys.path.append(os.path.join(os.environ['REGEX_GENERALIZABILITY_PROJECT_ROOT'], 'lib'))
import libLF

import json
import tempfile
import argparse
import traceback
import subprocess

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import pandas as pd

# Make sure plot labels are readable 
font = {'family' : 'normal',
      'weight' : 'normal',
      'size'   : 14}
matplotlib.rc('font', **font)

################

# I/O

def loadRegexesWithMetrics(rwmFile):
  """Return a list of regexes-with-metrics records"""
  regexes = []
  libLF.log('Loading regexes+metrics from {}'.format(rwmFile))
  with open(rwmFile, 'r') as inStream:
    for line in inStream:
      line = line.strip()
      if len(line) == 0:
        continue
      
      try:
        # Build a Regex
        regex = json.loads(line)
        regexes.append(regex)
      except KeyboardInterrupt:
        raise
      except BaseException as err:
        libLF.log('Exception parsing line:\n  {}\n  {}'.format(line, err))
        traceback.print_exc()

    libLF.log('Loaded {} regexes from {}'.format(len(regexes), rwmFile))
    return regexes

##########
# Identifying new features

def addFeatureCounts(regexesWithMetrics):
  """Add two keys to each rwm: numUniqueFeatures and numFeatures"""
  for rwm in regexesWithMetrics:
    numUniqueFeatures = 0
    numFeatures = 0
    for featureType, featureCount  in rwm['metrics']['featureVector'].items():
      if featureCount:
        numUniqueFeatures += 1
        numFeatures += featureCount
    rwm['numUniqueFeatures'] = numUniqueFeatures  
    rwm['numFeatures'] = numFeatures  

##########
# Reports

def makeReport_regexStringLen(df, visDir):
  libLF.log("Making report on regex string len distr ({} rows)".format(df.shape[0]))

  libLF.log("Regex string lengths, by language")
  print( df.groupby('lang')['len'].describe() )
  sns.boxplot(data=df, x="lang", y="len")
  plt.show()

def makeReport_regexFeatureCounts(df, visDir):
  libLF.log("Making report on regex feature counts distr ({} rows)".format(df.shape[0]))

  libLF.log("Regex num unique features, by language")
  print( df.groupby('lang')['numUniqueFeatures'].describe() )
  sns.boxplot(data=df, x="lang", y="len")
  plt.show()

  libLF.log("Regex count of total features used, by language")
  print( df.groupby('lang')['numUniqueFeatures'].describe() )
  sns.boxplot(data=df, x="lang", y="len")
  plt.show()

##########################

def main(rwmFile, langs, visDir):
  libLF.log('rwmFile {} langs {} visDir {}' \
    .format(rwmFile, langs, visDir))

  #### Load data
  regexesWithMetrics = loadRegexesWithMetrics(rwmFile)
  libLF.log("{} regexes with metrics".format(len(regexesWithMetrics)))

  #### Filter
  regexesWithMetrics = [rwm
                        for rwm in regexesWithMetrics
                        if rwm['metrics']['couldParse']
                       ]

  if langs:
    regexesWithMetrics = [rwm
                          for rwm in regexesWithMetrics
                          if rwm["lang"] in langs
                         ]
    libLF.log("Filtered down to {} regexes (those used in {})".format(len(regexesWithMetrics), langs))

  ### Compute new metrics for inclusion in the DF
  addFeatureCounts(regexesWithMetrics)
  
  ### Create DF
  print(regexesWithMetrics[0])
  df = pd.DataFrame(regexesWithMetrics) 
  
  #### Generate reports
  makeReport_regexStringLen(df, visDir)
  makeReport_regexFeatureCounts(df, visDir)

#####################################################

# Parse args
parser = argparse.ArgumentParser(description='Analyze regexes-with-metrics data')
parser.add_argument('--rwm-file', type=str, help='In: File of regexes-with-metrics (NDJSON)', required=True,
  dest='rwmFile')
parser.add_argument('--lang', type=str, help='In: Only consider and report about regexes actually used in these language(s)', required=False, action='append', default=[],
  dest='langs')
parser.add_argument('--vis-dir', help='Out: Where to save plots?', required=False, default='/tmp/vis',
  dest='visDir')
args = parser.parse_args()

# Here we go!
main(args.rwmFile, args.langs, args.visDir)
