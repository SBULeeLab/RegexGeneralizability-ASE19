#!/usr/bin/env python3
# Preprocessing for a maven module before instrumenting and running

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
import traceback

import xml.etree.ElementTree as ET

POM_XML_FILE = "pom.xml"

#####
# Globals

MIN_JAVA_VERSION_FOR_INSTRUMENTATION_APPROACH = -1

#####
# Helpers

def textToJavaVersion(text):
  match = re.match(r"1\.(\d+)", text)
  return int(match.group(1)) if match else None

def javaVersionToText(version):
  return "1.{}".format(version)

def getDefaultNamespace(elt):
  m = re.match(r'\{.*\}', elt.tag)
  return m.group(0) if m else ''

def addChildIfNotPresent(node, childTag, childNode):
  """Add childNode with childTag to node, if no child with that tag is present.
  
  Returns the childNode of node with tag childTag.
  """
  for child in node:
    if child.tag == childTag:
      return child
  
  # No match. Add a child.
  node.append(childNode)
  return childNode

def stripDefaultNamespace(etree):
  defaultNamespace = getDefaultNamespace(etree.getroot())
  for elt in etree.getroot().iter():
    if elt.tag.startswith(defaultNamespace):
      elt.tag = elt.tag.split('}', 1)[1]  # strip all namespaces

#####
# Maven-specific tree manipulations

def setPropertiesJavaVersionToAtLeast(etree, minVers):
  """Update the Java source version specified with global properties to minVers+.

  Returns the numeric versions[] for maven.compiler.{source,target}.
  The versions[] entries are None if the field is not in the etree.
  """
  # https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-source-and-target.html
  libLF.log("etree.findall")
  root = etree.getroot()

  defaultNamespace = getDefaultNamespace(root)

  versions = []
  for subPath in [
      ["properties", "maven.compiler.source"],
      ["properties", "maven.compiler.target"],
      ["properties", "java.version"]
    ]:
    fullPath = ["."] + [defaultNamespace + p for p in subPath]

    libLF.log("Searching fullPath: {}".format(fullPath))
    xmlMatch = root.find("/".join(fullPath))

    if xmlMatch is not None:
      libLF.log("Found {} - text {}".format(subPath, xmlMatch.text))

      currVers = textToJavaVersion(xmlMatch.text)
      if currVers is not None and currVers < minVers:
        libLF.log("Updating version from {} to {}".format(currVers, minVers))
        xmlMatch.text = javaVersionToText(minVers)
      versions.append(textToJavaVersion(xmlMatch.text))
    else:
      libLF.log("Did not find {}".format(subPath))
      versions.append(None)
  return versions

def setCompilerPluginJavaVersionToAtLeast(etree, minVers):
  """Update the Java source version specified through the maven-compiler-plugin to minVers+.

  Returns the version, or None if the field is not in the etree.
  """
  root = etree.getroot()

  defaultNamespace = getDefaultNamespace(root)

  # build / plugins / plugin <maven-compiler-plugin> / configuration / source
  subPath = ["build", "plugins", "plugin"]
  fullPath = ["."] + [defaultNamespace + p for p in subPath]

  libLF.log("Searching fullPath: {}".format(fullPath))
  for xmlMatch in root.findall("/".join(fullPath)):
    for child in xmlMatch:
      libLF.log("child tag: {}".format(child.tag))
      if child.tag == "{}artifactId".format(defaultNamespace) and \
         child.text == "maven-compiler-plugin":
        libLF.log("Found maven-compiler-plugin")

        versions = []
        for subRelPath in [
          ["configuration", "source"],
          ["configuration", "target"]
        ]:
          fullRelPath = ["."] + [defaultNamespace + p for p in subRelPath]
          subMatch = xmlMatch.find("/".join(fullRelPath))
          if subMatch is not None:
            currVers = textToJavaVersion(subMatch.text)
            # subMatch.text might be self-referential, e.g. "{java.version}",
            # in which case we will change it via the global properties
            libLF.log("{}-{}: text {}".format(fullPath, fullRelPath, subMatch.text))
            if currVers is not None and currVers < minVers:
              libLF.log("Updating {} version from {} to {}".format(subRelPath, currVers, minVers))
              subMatch.text = javaVersionToText(minVers)
            versions.append(textToJavaVersion(subMatch.text))
          else:
            libLF.log("Did not find match for {}".format(subRelPath))
            versions.append(None)
        return versions

  # Never found it
  return [None, None]

###
# Stages of main()

def updateSourceAndTargetToMinVers():
  try:
    libLF.log("Parsing pom.xml")
    etree = ET.parse(POM_XML_FILE)

    MIN_JAVA_VERSION_FOR_INSTRUMENTATION_APPROACH = 8

    # Existing target can be specified through either
    #  - properties/maven.compiler.source
    #  - build/plugins/plugin/<maven-compiler-plugin>.configuration/source
    # https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-source-and-target.html

    libLF.log("Getting configured Java version")
    propertiesJavaVersions = setPropertiesJavaVersionToAtLeast(etree, MIN_JAVA_VERSION_FOR_INSTRUMENTATION_APPROACH)
    libLF.log("propertiesJavaVersion: {}".format(propertiesJavaVersions))
    compilerPluginJavaVersions = setCompilerPluginJavaVersionToAtLeast(etree, MIN_JAVA_VERSION_FOR_INSTRUMENTATION_APPROACH)
    libLF.log("compilerPluginJavaVersion: {}".format(compilerPluginJavaVersions))

    if propertiesJavaVersions == [None, None] and compilerPluginJavaVersions == [None, None]:
      defaultNamespace = getDefaultNamespace(etree.getroot())
      libLF.log("Didn't find source/target globally or in maven compiler plugin")

      libLF.log("Adding global.properties if not present")
      propTag = "{}properties".format(defaultNamespace)
      propertiesChild = addChildIfNotPresent(etree.getroot(), propTag, ET.Element(propTag))

      # Add maven.compiler.source if not present
      mavenSourceTag = "{}maven.compiler.source".format(defaultNamespace)
      libLF.log("Adding global.properties.{} if not present".format(mavenSourceTag))
      sourceElt = ET.Element(mavenSourceTag)
      sourceElt.text = javaVersionToText(MIN_JAVA_VERSION_FOR_INSTRUMENTATION_APPROACH)
      addChildIfNotPresent(propertiesChild, mavenSourceTag, sourceElt)

      # Add maven.compiler.target if not present
      mavenTargetTag = "{}maven.compiler.target".format(defaultNamespace)
      libLF.log("Adding global.properties.{} if not present".format(mavenTargetTag))
      targetElt = ET.Element(mavenTargetTag)
      targetElt.text = javaVersionToText(MIN_JAVA_VERSION_FOR_INSTRUMENTATION_APPROACH)
      addChildIfNotPresent(propertiesChild, mavenTargetTag, targetElt)

      # This worked, right?
      assert(setPropertiesJavaVersionToAtLeast(etree, MIN_JAVA_VERSION_FOR_INSTRUMENTATION_APPROACH)[0] >= MIN_JAVA_VERSION_FOR_INSTRUMENTATION_APPROACH)

    # ET adds "ns0" namespace.
    # Maven does not seem to like namespaces
    stripDefaultNamespace(etree)

    outFile = POM_XML_FILE
    libLF.log("Writing out to {}".format(outFile))
    etree.write(outFile)
  except BaseException as e:
    libLF.log("Failed to update pom.xml to use Java 8: {}".format(e))
    traceback.print_exc()

##################

def main(mavenProjDir):
  # cd to the dir
  libLF.log("cd {}".format(mavenProjDir))
  os.chdir(mavenProjDir)
  
  if MIN_JAVA_VERSION_FOR_INSTRUMENTATION_APPROACH >= 0:
    libLF.log("Updating source/target to Java {}".format(MIN_JAVA_VERSION_FOR_INSTRUMENTATION_APPROACH))
    updateSourceAndTargetToMinVers()

##################

if __name__ == '__main__':
  # Parse args
  parser = argparse.ArgumentParser(description='Pre-processing for a maven-managed project')
  parser.add_argument('--proj-dir',  help='Project root dir', required=True, dest='projDir')

  args = parser.parse_args()

  # Here we go!
  main(args.projDir)
