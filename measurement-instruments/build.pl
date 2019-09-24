#!/usr/bin/env perl

use strict;
use warnings;

runcmd("pip install --user -r requirements.txt");
runcmd("pip3 install --user -r requirements.txt");

sub runcmd {
  my ($cmd) = @_;
  print "$cmd\n";
  print `$cmd`;
}