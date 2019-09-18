#!/usr/bin/env perl

use strict;
use warnings;

mkdir "release";

my %pom2jar = (
  "pom.xml-instrumentor" => "regex-instrumentor-1.0.jar",
  "pom.xml-static"       => "regex-extractor-1.0.jar",
);

while (my ($pom, $jar) = each (%pom2jar)) {
  print "\n\nBuilding with $pom\n\n";
  for my $cmd ("rm -rf target/", "cp $pom pom.xml", "mvn clean compile", "mvn package", "cp target/$jar release/") {
    print "  $cmd\n";
    `$cmd`;
  }
}
