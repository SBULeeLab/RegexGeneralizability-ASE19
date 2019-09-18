#!/usr/bin/env perl
# Author: Jamie Davis <davisjam@vt.edu>
# Description: Attempt to instrument a python program, using first python2 and then python3.
#   Same dependencies, usage, and restrictions as extract-regexps.py.

use strict;
use warnings;

use IPC::Cmd qw[can_run]; # Check PATH
use JSON::PP; # I/O

# Check dependencies.
if (not defined $ENV{ECOSYSTEM_REGEXP_PROJECT_ROOT}) {
  die "Error, ECOSYSTEM_REGEXP_PROJECT_ROOT must be defined\n";
}

my $extractRegexps = "$ENV{ECOSYSTEM_REGEXP_PROJECT_ROOT}/ecosystems/per-module/extract-regexps/static/python/instrument-regexps.py";
if (not -f $extractRegexps) {
  die "Error, could not find: $extractRegexps>\n";
}

# Need both python2 and python3
if (not can_run("python2")) {
  die "Error, no python2\n";
}

if (not can_run("python3")) {
  die "Error, no python3\n";
}

# Check args.
if (scalar(@ARGV) != 2) {
  die "Usage: $0 python-filename.py regex-log-file\n";
}

my $pythonFile = $ARGV[0];
my $regexLogFile = $ARGV[1];

my ($rc, $out);
# Try python2
($rc, $out) = &cmd("python2 $extractRegexps '$pythonFile' '$regexLogFile'");

if ($rc eq 0) {
  print STDOUT $out;
  exit 0;
}
else {
  print STDERR "Could not instrument $pythonFile using python2\n";
  # Try python3
  ($rc, $out) = &cmd("python3 $extractRegexps '$pythonFile' '$regexLogFile'");
  if ($rc eq 0) {
    print STDOUT $out;
    exit 0;
  }
  else {
    print STDERR "Could not instrument $pythonFile using python3\n";
    exit 1;
  }
}

########

sub cmd {
  my ($cmd) = @_;
  my $out = `$cmd`;
  return ($? >> 8, $out);
}
