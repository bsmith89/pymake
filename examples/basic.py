#! /usr/bin/env python
"""An example pymake script"""

# Simple one line import statetment.
from pymake import Rule, maker
import sys

EXT = 'test'

# Standard python code
# each rule is an object with several attributes
rules = [Rule("all", preqs=["top"]),
         Rule(trgt="top", preqs=("test_end.{EXT}",), EXT=EXT),
         # trgt strings are regex patters.  Be sure to escape special
         # characters.  You can also math groups.  You'll want to use raw
         # strings in most cases.
         Rule(trgt=r"test_end\.(.*)",
              # And then they can be used in pre-requistite templates
              preqs=("second1.{0}", "second2.{0}"),
              # Recipe is just a set of bash commands
              # Leading white space is ignored by bash, so it's ignored
              # here.
              recipe=("echo {preqs}\n"
                      "echo {trgt}\n"
                      "cat {preqs} > {trgt}\n"
                      "sleep 1")),
              # Regex can be used in target (don't forget to escape
              # \'s or use raw strings.) and groups found in the target
              # can be substituted in the pre-reqs and the recipe.
         Rule(trgt=r"second(.*)\.(.*)",
              preqs=("first{0}-1.{1}", r"first{0}-2.{1}"),
              # Various keywords are available to the recipes.
              recipe=("echo {preqs}\n"
                      "echo {trgt}\n"
                      "cat {preqs} > {trgt}\n"
                      "sleep 1")),
         Rule(trgt=r"first([0-9])-([0-9])\.(.*)",
              # Groups from the regex can also be used in the recipe.
              recipe=("echo {0} {1}\n"
                      "touch {trgt}\n"
                      "sleep 1")),
         # If an error occurs in a task, the pipeline will fail any
         # downstream tasks, but everything else will run as expected.
         Rule("all-fail", preqs=["top", "fail"]),
         Rule(trgt="fail", recipe="[ 8 == 7 ]"),
         # If no argument is given, the first rule in the iterable will be,
         # run.
         Rule(trgt="clean", recipe="rm *.{EXT}", EXT=EXT)]

# Make just requires a list, sequence, or iterator of rules
# And takes arbitrary targets and environmental variables
# are available to recipes.

if __name__ == '__main__':
    maker(rules)

# Environmental variables can not be set in recipes.
# Rules which have already been fulfilled (based on file modification times),
# are not re-run.
