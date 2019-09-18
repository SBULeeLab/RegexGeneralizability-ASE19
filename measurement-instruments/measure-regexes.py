#!/usr/bin/env python3
# Measure regexes on (some) metrics
# The metric computations are CPU-bound, so this is parallelized to improve performance.
# The metrics are computed in the "MyTask" class, driven by the "MyTask.run()" method.

# Import libLF
import os
import sys
import re
sys.path.append(os.path.join(os.environ['REGEX_GENERALIZABILITY_PROJECT_ROOT'], 'lib'))
import libLF

import shutil
import json
import tempfile
import argparse
import traceback
import subprocess
from multiprocessing import Process, Queue

# NFA measures
import networkx

import time

### Globals

# Logging / debugging
DELETE_TMP_FILES = False
PRINT_SIMPLE_PATHS = False
VISUALIZE_NFAS = False

# Limiting cost per regex
AUTOMATACLI_BATCH_SIZE = 10
AUTOMATACLI_MAX_SECONDS_PER_REGEX = 5
AUTOMATACLI_TIMEOUT_SEC = AUTOMATACLI_BATCH_SIZE * AUTOMATACLI_MAX_SECONDS_PER_REGEX
LIMIT_SIMPLE_PATHS = True
SIMPLE_PATH_COUNT_LIMIT = 5000 # Based on a sample of 70K regexes, the distribution is heavily weighted towards 1-10 paths per regex. <=100 regexes fall above 50K simple paths. No need to exhaustively count for these outliers.
SIMPLE_PATH_TIME_LIMIT = 5 # seconds

# Dependencies
WINDOWS_OS = os.name == 'nt'
WINE_PATH = shutil.which("wine")
AutomataCLI = os.path.join(os.environ['REGEX_GENERALIZABILITY_PROJECT_ROOT'], 'bin', 'AutomataCLI.exe')
if WINDOWS_OS:
    # Workaround for broken symlink
    AutomataCLI = os.path.join(os.environ['REGEX_GENERALIZABILITY_PROJECT_ROOT'], 'measurement-instruments', 'automata', 'AutomataCLI.exe')
else:
    libLF.checkShellDependencies([WINE_PATH], mustBeExecutable=True)

libLF.checkShellDependencies([AutomataCLI], mustBeExecutable=False)

# Control analysis
class AnalysisStages:
  ANALYZE_AUTOMATON = 'automaton'
  ANALYZE_SIMPLE_PATHS = 'simple paths'
  ANALYZE_WORST_CASE = 'worst case'

# Misc
reg2lang = {
  'npm': 'JavaScript', # TypeScript is evaluated on a JS engine
  'crates.io': 'Rust',
  'packagist': 'PHP',
  'pypi': 'Python',
  'rubygems': 'Ruby',
  'cpan': 'Perl',
  'maven': 'Java',
  'godoc': 'Go',
}

##########
# Types

class RegexMetrics:
  """
  Members:
      origPattern: str
        Use to key back to a libLF.Regex
      origLangsStatic: str[]
        Langs (registries) this regex appeared in STATICALLY
      origLangsDynamic: str[]
        Langs (registries) this regex appeared in DYNAMICALLY
      csharpPattern: str
        As determined by libLF.RegexTranslator

    All subsequent metrics are based on csharpPattern
      csharpRegexLen: int
        Length of regex (string)
      validInCSharp: bool
        True if translation worked
      featureVector: { 'FEATURE': COUNT, ... }
        A la Chapman&Stolee'16
      automatonMetrics: { 'METRIC': VALUE, ... }
        Metrics are all integers
        See AutomataCLI for details
      nSimplePaths: int
        Number of simple paths
      nDistinctFeaturesUsed: int
        Number of distinct features used
      predictedWorstCaseSpencer: str
        Prediction in Spencer-style engine according to Weideman et al.
      averageOutDegreeDensity: float
        |E| / m^2 from the e-free NFA
      usesSuperLinearFeatures: bool
        True if uses backreferences or lookaround assertions
  """
  def __init__(self,
    origPattern,
    origLangsStatic, origLangsDynamic,
    csharpPattern,
    csharpRegexLen,
    validInCSharp,
    featureVector,
    automatonMetrics,
    nSimplePaths,
    nDistinctFeaturesUsed,
    predictedWorstCaseSpencer,
    averageOutDegreeDensity,
    usesSuperLinearFeatures
    ):
    self.origPattern = origPattern
    self.origLangsStatic = origLangsStatic
    self.origLangsDynamic = origLangsDynamic
    self.csharpPattern = csharpPattern
    self.csharpRegexLen = csharpRegexLen
    self.validInCSharp = validInCSharp
    self.featureVector = featureVector
    self.automatonMetrics = automatonMetrics
    self.nSimplePaths = nSimplePaths
    self.nDistinctFeaturesUsed = nDistinctFeaturesUsed
    self.predictedWorstCaseSpencer = predictedWorstCaseSpencer
    self.averageOutDegreeDensity = averageOutDegreeDensity
    self.usesSuperLinearFeatures = usesSuperLinearFeatures
  
  def toNDJSON(self):
    return libLF.toNDJSON(self._toDict())
  
  def _toDict(self):
    obj = {
      "origPattern": self.origPattern,
      "origLangsStatic": self.origLangsStatic,
      "origLangsDynamic": self.origLangsDynamic,
      "csharpPattern": self.csharpPattern,
      "csharpRegexLen": self.csharpRegexLen,
      "validInCSharp": self.validInCSharp,
      "featureVector": self.featureVector,
      "automatonMetrics": self.automatonMetrics,
      "nSimplePaths": self.nSimplePaths,
      "nDistinctFeaturesUsed": self.nDistinctFeaturesUsed,
      "predictedWorstCaseSpencer": self.predictedWorstCaseSpencer,
      "averageOutDegreeDensity": self.averageOutDegreeDensity,
      "usesSuperLinearFeatures": self.usesSuperLinearFeatures,
    }
    return obj

##########
# Parallelization

class MyTask(libLF.parallel.ParallelTask):
  """ParallelTask to handle a set of regexes

  Uses a regexList and not an individual regex because
  the automata analysis depends on a C# CLI that performs a lot better
  if we give it a batch of regexes (fork+exec+wine = $).
  """
  def __init__(self, regexList, analyses):
    self.regexList = regexList
    self.analyses = analyses
  
  # Returns RegexMetrics[]
  def run(self):
    try:
      # Obtain C# patterns
      libLF.log("Generating C# patterns")
      # Replace u flag with i for compatibility with C# and to preserve the
      # presence or absence of flags.
      csharpPatterns = [
        libLF.RegexTranslator.translateRegex(regex.pattern, "", "C#", altUnicodeFlag='i')
        for regex in self.regexList
      ]

      for r, c in zip(self.regexList, csharpPatterns):
        libLF.log("MyTask: /{}/ -> /{}/".format(r.pattern, c))

      # Run the analyses
      if AnalysisStages.ANALYZE_AUTOMATON in self.analyses:
        libLF.log("ANALYZE_AUTOMATON")
        automataMeasures = self.runAutomataCLI(csharpPatterns)
        if len(automataMeasures) and AnalysisStages.ANALYZE_SIMPLE_PATHS in self.analyses:
          libLF.log("ANALYZE_SIMPLE_PATHS")
          nSimplePathsList, averageOutDegreeDensityList = self.computeGraphMetrics(automataMeasures)
        else:
          libLF.log("{} automataMeasures, analyses {} -- skipping computeGraphMetrics".format(len(automataMeasures), self.analyses))
          nSimplePathsList = [ -1 for i in range(len(self.regexList)) ]
          averageOutDegreeDensityList = [ -1 for i in range(len(self.regexList)) ]
      else:
        automataMeasures = [ {} for i in range(len(self.regexList)) ]
        nSimplePathsList = [ -1 for i in range(len(self.regexList)) ]
        averageOutDegreeDensityList = [ -1 for i in range(len(self.regexList)) ]

      if AnalysisStages.ANALYZE_WORST_CASE in self.analyses:
        libLF.log("ANALYZE_WORST_CASE")
        # Perform worst-case analysis on the C#-translated regexes
        regexes_csharp = [
          libLF.Regex().initFromRaw(csharpPattern, {}, {})
          for csharpPattern in csharpPatterns 
        ]
        worstCaseSpencerList = self.predictWorstCaseSpencerPerformance(regexes_csharp)
      else:
        worstCaseSpencerList = [ libLF.SLRegexDetectorOpinion.PRED_COMPLEXITY_UNKNOWN for i in range(len(self.regexList)) ]
      
      libLF.log("Asserting lengths")
      assert(len(self.regexList) == len(csharpPatterns))
      assert(len(self.regexList) == len(automataMeasures))
      assert(len(self.regexList) == len(nSimplePathsList))
      assert(len(self.regexList) == len(worstCaseSpencerList))

      # Prep and return RegexMetrics[]
      libLF.log("Prepping regexMetricsList")
      regexMetricsList = []
      for regex, csharpPattern, autMeasure, nSimplePaths, averageOutDegreeDensity, worstCaseSpencer in zip(
        self.regexList, csharpPatterns, automataMeasures, nSimplePathsList, averageOutDegreeDensityList, worstCaseSpencerList):
        # Prep members for a RegexMetrics
        csharpRegexLen = len(csharpPattern)
        if AnalysisStages.ANALYZE_AUTOMATON in self.analyses:
          validInCSharp = autMeasure['validCSharpRegex']
          if validInCSharp:
            featureVector = autMeasure['featureVector']
            automatonMetrics = autMeasure['automataMeasures']
          else:
            featureVector = {}
            automatonMetrics = {}

          if AnalysisStages.ANALYZE_SIMPLE_PATHS not in self.analyses:
            nSimplePaths = -1
        else:
          validInCSharp = False
          featureVector = {}
          automatonMetrics = {}
        
        # Misc metrics
        nDistinctFeaturesUsed = 0
        for v in featureVector.values():
          if v is not None and v > 0:
            nDistinctFeaturesUsed += 1

        usesSuperLinearFeatures = False
        for abbrv in ["NLKA", "LKA", "NLKB", "LKB", "BKR"]:
          if abbrv in featureVector and featureVector[abbrv] > 0:
            usesSuperLinearFeatures = True

        regexMetrics = RegexMetrics(
          regex.pattern,
          regex.langsUsedInStatic(), regex.langsUsedInDynamic(),
          csharpPattern, csharpRegexLen,
          validInCSharp,
          featureVector, automatonMetrics, nSimplePaths,
          nDistinctFeaturesUsed,
          worstCaseSpencer, averageOutDegreeDensity, usesSuperLinearFeatures
        )
        regexMetricsList.append(regexMetrics)
      libLF.log("Returning regexMetricsList")
      return regexMetricsList
    except BaseException as e:
      libLF.log("Uh oh, hit an exception")
      libLF.log(e)
      traceback.print_exc()
      return self.regexList

  ##########
  # Analysis

  def _automataCLI_prepQueryFile(self, queryFile, csharpPatterns):
    queries = [ { 'pattern': pattern }
                for pattern in csharpPatterns
              ]
    for q in queries:
      queryFile.write(libLF.toNDJSON(q) + "\n")
    queryFile.flush()

  def _automataCLI_runQuery(self, queryFile, outFile, errFile):
    try:
      if WINDOWS_OS:
        cmd = [AutomataCLI, queryFile.name]
      else:
        cmd = [WINE_PATH, AutomataCLI, queryFile.name]
      libLF.log("CMD: {} > {} 2>{}".format(' '.join(cmd), outFile.name, errFile.name))
      completedProcess = subprocess.run(cmd, stdout=outFile, stderr=errFile, timeout=AUTOMATACLI_TIMEOUT_SEC)
      rc = completedProcess.returncode
    except subprocess.TimeoutExpired:
      libLF.log("automataCLI timed out")
      rc = 1
    except Exception as e:
      libLF.log("automataCLI: non-timeout exception")
      libLF.log(e)
      rc = 1
    libLF.log("_automataCLI_runQuery: rc {}".format(rc))
    return rc

  def _automataCLI_processResultStream(self, csharpPatterns, resultFile):
    automataMetricsList = []
    for i, line in enumerate(resultFile):
      # Extract the metrics from the AutomataCLI measurements
      line = line.strip()
      libLF.log("Results for regex {} ( /{}/ ): {}".format(i, csharpPatterns[i], line))
      try:
        automataCLI_res = json.loads(line)
      except:
        libLF.log("Could not parse AutomataCLI output")
        # Fill in with a dummy metrics object
        automataMetricsList.append( { 'len': len(csharpPatterns[i]),
                                  'validCSharpRegex': False }
                              )
        continue

      # Parse-able -- pull out the 'regexMetrics' field
      assert('regexMetrics' in automataCLI_res)
      automataMetrics = automataCLI_res['regexMetrics']
      metrics = {
        'regexLen': len(csharpPatterns[i]),
        'validCSharpRegex': automataMetrics['validCSharpRegex']
      }
      if metrics['validCSharpRegex']:
        # Pull out the fields that worked
        if automataMetrics['featureVector']['valid']:
          metrics['features'] = automataMetrics['featureVector']
          del metrics['features']['valid']

        if automataMetrics['automataMeasures']['nfa_orig_completeInfo']:
          metrics['automata'] = automataMetrics['automataMeasures']

      # Keep it
      automataMetricsList.append(automataMetrics)

    return automataMetricsList
  
  def runAutomataCLI(self, csharpPatterns):
    """Run AutomataCLI.exe for these csharpPatterns

    Args:
      csharpPatterns: str[] -- Regex patterns translated to C#
    Returns:
      automateMeasures[]: the 'metrics' field produced by the AutomataCLI for each csharpPattern
        These are in the same order as the input csharpPatterns list
        For any csharpPattern's that cannot be processed by AutomataCLI, a simple metrics
        dict is returned with just the 'len' (valid) and validCSharpRegex' (False) set 

        If we could not obtain metrics, then returns a list of ["Error", "Error", ...] of the appropriate length
    """
    # The output can be quite verbose when using lists of inputs,
    # so redirect to a temp file to ensure buffering and piping aren't problematic
    # in the shell. 
    with tempfile.NamedTemporaryFile(prefix='RegexMetrics-queryFile-', 
                                      mode='w+',
                                      suffix='.json',
                                      delete=DELETE_TMP_FILES) as queryFile, \
        tempfile.NamedTemporaryFile(prefix='RegexMetrics-OutFile-', 
                                      suffix='.json',
                                      mode='w+',
                                      delete=DELETE_TMP_FILES) as outFile, \
        tempfile.NamedTemporaryFile(prefix='RegexMetrics-ErrFile-', 
                                      suffix='.json',
                                      mode='w+',
                                      delete=DELETE_TMP_FILES) as errFile:
      libLF.log("queryFile {} outFile {} errFile {}".format(queryFile.name, outFile.name, errFile.name))
      self._automataCLI_prepQueryFile(queryFile, csharpPatterns)
      queryFile.close() # Free file for Windows
      rc = self._automataCLI_runQuery(queryFile, outFile, errFile)

      if rc != 0:
        libLF.log("automataCLI returned {} -- check queryFile {} errFile {}".format(rc, queryFile.name, errFile.name))
        # Dump the log file
        with open(errFile.name) as errStream:
          for line in errStream:
            line = line.strip()
            libLF.log("  {}".format(line))
        # Return in error
        return [ {} for i in range(len(csharpPatterns)) ]

      # Success. Extract the RWM.
      # Use open() again so we have access to the 'errors' parameter.
      #   Some encoding errors, not sure what's happening here.
      #   Just replace them with "?" hehe.
      # NB: Pydoc says re-opening works on UNIX, though not on Windows.
      with open(outFile.name, 'r', encoding='utf-8', errors='replace') as automataCLIOutFile:
        automataMeasuresList = self._automataCLI_processResultStream(csharpPatterns, automataCLIOutFile)
      return automataMeasuresList

  def getNSimplePaths(self, sources, targets, graph):
    """Returns the simple path lengths for this graph"""
    nSimplePaths = 0
    libLF.log("Computing simple paths for automaton with {} sources, {} targets, {} nodes, {} edges" \
      .format(len(sources), len(targets),
        networkx.number_of_nodes(graph), networkx.number_of_edges(graph)))

    # Find up to SIMPLE_PATH_COUNT_LIMIT simple paths and their lengths.
    # In extreme situations, we are content simply to know there are many paths.
    count = 0
    bailout = False
    timeout = time.time() + SIMPLE_PATH_TIME_LIMIT
    for source in sources:
      # Are we done early?
      if bailout:
        libLF.log("bailing out")
        break

      # Look for S -> T paths
      for target in targets:
        # shortest_simple_paths is a generator.
        # We can thus bail partway through.
        # Starting from shortest minimizes the time spent here for complex graphs where we bail out anyway
        #for path in networkx.all_simple_paths(graph, source, target):
        for path in networkx.shortest_simple_paths(graph, source, target):
          count += 1
          if LIMIT_SIMPLE_PATHS and SIMPLE_PATH_COUNT_LIMIT < count:
            libLF.log('simple path limit reached')
            bailout = True
            break

          if LIMIT_SIMPLE_PATHS and time.time() > timeout:
            libLF.log('simple path timeout reached')
            bailout = True
            break

          # Add to our list
          #numEdges = len(path) - 1
          nSimplePaths += 1

          if PRINT_SIMPLE_PATHS:
            # What is the path?
            # This is expensive when there are many (K's+) simple paths
            simple = []
            for s, t in zip(path, path[1:]):
              simple.append( graph[s][t] ['label'] )
            libLF.log("  simple path: {}".format(path))
            libLF.log("  simple input: <{}>".format(" -> ".join(simple)))

    if VISUALIZE_NFAS:
      # Visualize
      import matplotlib.pyplot as plt
      libLF.log("Graph sources: {}".format(sources))
      libLF.log("Graph targets: {}".format(targets))
      pos = networkx.spring_layout(graph)
      networkx.draw_networkx(graph, pos=pos, arrows=True, with_labels=True)
      edgeLabels = networkx.get_edge_attributes(graph, 'label')
      networkx.draw_networkx_edge_labels(graph, pos=pos, edge_labels=edgeLabels) 
      plt.show()

    return nSimplePaths

  def graphStrToDiGraph(self, efreeNFAGraphStr):
    """
    Graph string format:
     S [S ...]
     T [T ...]
     U V Label
     U V Label
     ...
    
    Returns (sources, targets, networkx.DiGraph)
    """
    lines = efreeNFAGraphStr.split("\n")
    sourcesLine = lines[0]
    targetsLine = lines[1]

    # If not sources or not targets, it's an empty language
    if not sourcesLine or not targetsLine:
      return None
    sources = [int(s) for s in sourcesLine.split(" ")]
    targets = [int(t) for t in targetsLine.split(" ")]

    # Build edge pairs
    edges = [] # (u, v, label)
    for l in lines[2:]:
      edgeInfo = l.split()
      source = int(edgeInfo[0])
      target = int(edgeInfo[1])
      label = " ".join(edgeInfo[2:])
      edges.append((source, target, {"label": label}))

    # Convert to networkx graph
    graph = networkx.DiGraph(edges)
    return sources, targets, graph

  def getAvgOutDegreeDensity(self, graph):
    """
    Average outdegree density = 1/m * SUM_1^m (outdegree of this node / possible outdegree)
                              = 1/m * 1/m * SUM_1^m (outdegree of this node)
                              = 1/m * 1/m * (total outdegrees for all nodes)
                              = 1/m^2 * (number of directed edges)
                              = |E| / m^2
    """
    numEdges = networkx.number_of_edges(graph)
    possibleEdges = (networkx.number_of_nodes(graph) ** 2)
    if possibleEdges > 0:
      return numEdges / possibleEdges
    return 0
  
  def computeGraphMetrics(self, automataMeasures):
    """Compute graph metrics for these automata
    
    Args:
      automataMeasures: automateMeasure[] (from automataCLI['regexMetrics'])
        Each should have key 'efreeNFAGraph'
    Returns:
      (nSimplePaths[], averageOutDegreeDensity[])
        - the number of simple paths for the corresponding 'efreeNFAGraph'
          (If an entry is 0, the regex accepts the null language)
        - the average outdegree density of the graph
    """
    nSimplePathsList = []
    avgOutDegreeDensityList = []
    for i, autMeas in enumerate(automataMeasures):
      libLF.log("Simple paths for autom {}/{}".format(i+1, len(automataMeasures)))
      nSimplePaths = -1
      avgOutDegreeDensity = -1
      if 'efreeNFAGraph' in autMeas and autMeas['efreeNFAGraph'] is not None and autMeas['efreeNFAGraph'] != "TIMEOUT":
        try:
          # Build graph
          sources, targets, graph = self.graphStrToDiGraph(autMeas['efreeNFAGraph'])

          # Compute simple paths
          try:
            nSimplePaths = self.getNSimplePaths(sources, targets, graph)
            if nSimplePaths:
              libLF.log("{} simple paths".format(nSimplePaths))
          except:
            nSimplePaths = -1
          
          # Compute average outdegree density
          avgOutDegreeDensity = self.getAvgOutDegreeDensity(graph)
          libLF.log("avg outdegree density {}".format(avgOutDegreeDensity))
        except BaseException as e:
          libLF.log("Exception obtaining graph metrics: {}".format(e))
          traceback.print_exc()
      # Keep whatever we computed
      nSimplePathsList.append(nSimplePaths)
      avgOutDegreeDensityList.append(avgOutDegreeDensity)

    libLF.log("Done computing graph metricspaths")
    return nSimplePathsList, avgOutDegreeDensityList

  def predictWorstCaseSpencerPerformance(self, regexList):
    """Return predicted worst case performances for these regexes

    Args:
      regexList: libLF.Regex[]
    Returns:
      libLF.SLRegexDetectorOpinion.PREDICTED_COMPLEXITY_X[]
    """
    predictedPerformanceList = []
    for regex in regexList:
      slra = libLF.SLRegexAnalysis(regex)
      slra.queryDetectors(detectors=["weideman-RegexStaticAnalysis"], patternVariants=["leftanchor"])
      predictedPerformance = slra.getWorstCasePredictedSpencerPerformanceFromStaticOnly()
      predictedPerformanceList.append(predictedPerformance)
    return predictedPerformanceList

def getTasks(regexFile, setStaticToAll, langs, parallelism, analyses):
  regexes = loadRegexFile(regexFile, setStaticToAll)

  if langs:
    libLF.log("Filtering for only those regexes used in {}".format(langs))
    nOrig = len(regexes)
    langs = [l.lower() for l in langs]
    regexes = [
      regex
      for regex in regexes
      if set([l.lower() for l in regex.langsUsedIn()]).intersection(langs)
    ]
    nRemaining = len(regexes)
    libLF.log("Filtered from {} down to {} regexes".format(nOrig, nRemaining))

  # Break into consecutive sublists (preserving order)
  # to facilitate concurrent jobs
  # Use relatively small batches to minimize losses in case of regexes that cause errors
  regexLists = [
    regexes[i:i+AUTOMATACLI_BATCH_SIZE]
    for i in range(0, len(regexes), AUTOMATACLI_BATCH_SIZE)
  ]
  tasks = [MyTask(rl, analyses) for rl in regexLists]
  libLF.log('Prepared {} tasks for {} regexes'.format(len(tasks), len(regexes)))
  return tasks

################
# I/O

def loadRegexFile(regexFile, setStaticToAll):
  """Return a list of Regex's"""
  regexes = []
  libLF.log('Loading regexes from {}'.format(regexFile))
  with open(regexFile, 'r') as inStream:
    for line in inStream:
      line = line.strip()
      if len(line) == 0:
        continue
      
      try:
        # Build a Regex
        regex = libLF.Regex()
        regex.initFromNDJSON(line)

        # Filter
        if type(regex.pattern) is not str or len(regex.pattern) < 1:
          continue
        
        # Populate static langs used in if it is not set.
        # This should only be because it was not set during the LF project.
        if setStaticToAll:
          if len(regex.useCount_registry_to_nModules_static) != 0:
            raise ValueError("Error, you told me to setStaticToAll but it looks like static language use is non-empty")
          regex.useCount_registry_to_nModules_static = regex.useCount_registry_to_nModules

        regexes.append(regex)
      except KeyboardInterrupt:
        raise
      except BaseException as err:
        libLF.log('Exception parsing line:\n  {}\n  {}'.format(line, err))
        traceback.print_exc()

    libLF.log('Loaded {} regexes from {}'.format(len(regexes), regexFile))
    return regexes

################

def regexUsedInLangs(regex, langs): 
  # lower-case "languages used in" and "langs of interest"
  lui = regex.langsUsedIn()
  langs = [l.lower() for l in langs]

  # Any overlap?
  for lang in lui:
    if lang in langs:
      return True 
  return False

##########################

#def throwaway():
#  mytask = MyTask([], {})
#  with open("/tmp/RegexMetrics-OutFile-853pbgwz.json") as inStream:
#    automMeasures = mytask._automataCLI_processResultStream(["a" for a in range(10)], inStream)
#    mytask.computeNSimplePaths(automMeasures)
#
#libLF.log("Here we go")
#throwaway()
#libLF.log("Done")
#sys.exit(1)

def main(regexFile, setStaticToAll, analyses, langs, outFile, parallelism):
  libLF.log('regexFile {} setStaticToAll {} analyses {} langs {} outFile {} parallelism {}' \
    .format(regexFile, setStaticToAll, analyses, langs, outFile, parallelism))

  #### Load data
  libLF.log('\n\n-----------------------')
  libLF.log('Loading regexes from {}'.format(regexFile))
  tasks = getTasks(regexFile, setStaticToAll, langs, parallelism, analyses)
  nRegexes = 0
  for t in tasks:
    nRegexes += len(t.regexList)
  libLF.log('Loaded {} regexes'.format(nRegexes))

  #### Process data
  libLF.log('\n\n-----------------------')
  libLF.log('Submitting to map')

  nSuccesses = 0
  nExceptions = 0

  # CPU-bound, no limits
  LINE_BUFFERING = 1
  with open(outFile, 'w', buffering=LINE_BUFFERING) as outStream:
    i = 0
    for resultList in libLF.parallel.imap_unordered_genr(tasks, parallelism,
      libLF.parallel.RateLimitEnums.NO_RATE_LIMIT, libLF.parallel.RateLimitEnums.NO_RATE_LIMIT,
      jitter=False):
      i += 1

      #### Emit results
      libLF.log("Emitting batch {} ({} results)".format(i, len(resultList)))
      for maybeRegexMetrics in resultList:
        if type(maybeRegexMetrics) is RegexMetrics:
          nSuccesses += 1
          outStream.write(maybeRegexMetrics.toNDJSON() + '\n')
        else:
          nExceptions += 1
  libLF.log("Successfully computed metrics for {}/{} ({}%) of the regexes" \
    .format(nSuccesses, nRegexes,
      '%.2f' % (100 * nSuccesses / nRegexes)
      ))

  #### Filter
#  if langs:
#    regexes = [r for r in regexes if regexUsedInLangs(r, langs)]
#    libLF.log("Filtered down to {} regexes (those used in {})".format(len(regexes), langs))
#  else:
#    langs = [l.lower() for l in list(reg2lang.values())]
#  
#  regexesWithMetrics = getRegexesWithMetrics(regexes)
#  succeededRWM = [(reg, metr)
#                  for reg, metr in regexesWithMetrics
#                  if 'features' in metr
#                 ]
#  failedRWM = [(reg, metr)
#               for reg, metr in regexesWithMetrics
#               if 'features' not in metr
#              ]
#  libLF.log("Succeeded on metrics for {}/{} ({}%) of the regexes" \
#    .format(len(succeededRWM),
#            len(regexes),
#            '%.2f' % (len(succeededRWM) / len(regexes))
#           )
#    )
#
#  #### Dump
#  dumpDataForExternalAnalysis(succeededRWM, outFile)

#####################################################

if __name__ == "__main__":
  # Parse args
  parser = argparse.ArgumentParser(description='Measure some libLF.Regex\'s. Translates them to C#, then performs analyses using AutomataCLI')
  parser.add_argument('--regex-file', type=str, help='In: File of libLF.Regex objects', required=True,
    dest='regexFile')
  parser.add_argument('--set-static-to-all', help='Set static languages to all languages. Useful if using the LF dataset, all of whose regexes are static. Otherwise you should not need this', required=False, action='store_true', default=False,
    dest='setStaticToAll')
  parser.add_argument('--analyze-automaton', help='Analyze the regex features and automaton', required=False, action='store_true', default=False,
    dest='analyzeAutomaton')
  parser.add_argument('--analyze-simple-paths', help='Analyze the simple paths of the automaton. Requires --analyze-automaton. Stops counting after {} paths or {} seconds'.format(SIMPLE_PATH_COUNT_LIMIT, SIMPLE_PATH_TIME_LIMIT), required=False, action='store_true', default=False,
    dest='analyzeSimplePaths')
  parser.add_argument('--analyze-worst-case', help='Analyze the predicted worst-case behavior of a regex in a Spencer-style regex engine according to Weideman et al.', required=False, action='store_true', default=False,
    dest='analyzeWorstCase')
  parser.add_argument('--lang', type=str, help='In: Only consider and report about regexes actually used in these language(s)', required=False, action='append', default=[],
    dest='langs')
  parser.add_argument('--out-file', help='Out: Where to save data for external analysis? Input order is not preserved.', required=True,
    dest='outFile')
  parser.add_argument('--parallelism', type=int, help='Maximum cores to use', required=False, default=libLF.parallel.CPUCount.CPU_BOUND,
    dest='parallelism')
  args = parser.parse_args()

  analyses = []
  if args.analyzeAutomaton:
    analyses.append(AnalysisStages.ANALYZE_AUTOMATON)
  if args.analyzeSimplePaths:
    assert(args.analyzeAutomaton)
    analyses.append(AnalysisStages.ANALYZE_SIMPLE_PATHS)
  if args.analyzeWorstCase:
    analyses.append(AnalysisStages.ANALYZE_WORST_CASE)
  if not analyses:
    libLF.log("Error, you must choose at least one analysis")
    sys.exit(1)

  # Here we go!
  main(args.regexFile, args.setStaticToAll, analyses, args.langs, args.outFile, args.parallelism)
