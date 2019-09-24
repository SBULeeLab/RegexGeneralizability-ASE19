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
