#!/usr/bin/env perl

use strict;
use warnings;

my $artifactName = "vuln-regex-detector-ASE19-Artifact";
my $tarball = "$artifactName.tar.gz";
my $dest = "vuln-regex-detector";

if (-d $dest) {
  print "I see $dest -- Looks like it already built\n";
  exit 0;
}

print "Untarring the artifact";
chkcmd("tar -xzvf $tarball");
chkcmd("mv $artifactName $dest");

print "Configuring the artifact\n  (This may prompt for sudo to install dependencies)\n";
fixDetectors($dest);
chkcmd("cd $dest; ./configure");

sub chkcmd {
  my ($cmd) = @_;
  my $rc = runcmd($cmd);
  if ($rc != 0) {
    die "Error, rc $rc\n";
  }
}

sub runcmd {
  my ($cmd) = @_;
  print "$cmd\n";
  print `$cmd`;
  return $? >> 8;
}

sub fixDetectors {
  my ($vrdRoot) = @_;
  my $detectorSrc = "$vrdRoot/src/detect/src/detectors/";

  my $detector2paths = {
    "weideman" => {
      "dest": "weideman-RegexStaticAnalysis",
      "artifact": "weideman-ASE19-artifact.tar.gz",
      "untarDir": "RegexStaticAnalysis-ASE19-artifact",
    },
    "shen" => {
      "path": "shen-ReScue",
      "artifact": "shen-ASE19-artifact.tar.gz",
      "untarDir": "ReScue-ASE19-artifact",
    }
  }

  for my $detector (keys %$detector2paths) {
    print "Fixing up $detector\n";
    chkcmd("rm -rf $detectorSrc/$detector2paths->{$detector}->{dest}");
    chkcmd("cp $detector2paths->{$detector}->{artifact} $detectorSrc");
    chkcmd("cd $detectorSrc; tar -xzvf $detector2paths->{$detector}->{artifact}; mv $detector2paths->{$detector}->{untarDir} $detector2paths->{$detector}->{dest}");
  }
}