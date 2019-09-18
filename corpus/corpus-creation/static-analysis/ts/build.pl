#!/usr/bin/env perl

use strict;
use warnings;

for my $cmd ("npm install", "npm run build") {
  print "$cmd\n";
  print `$cmd`;
}
