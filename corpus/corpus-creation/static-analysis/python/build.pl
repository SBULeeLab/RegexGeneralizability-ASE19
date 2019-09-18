#!/usr/bin/env perl

use strict;
use warnings;

my $cmd = "pip install --user -r requirements.txt";
print "$cmd\n";
print `$cmd`;
