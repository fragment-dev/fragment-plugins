#!/bin/zsh
# Runs tools/loop1_tests.py. See that file for the tests.
HERE=${0:a:h}
python3 $HERE/loop1_tests.py "$@"
