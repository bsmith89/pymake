#! /usr/bin/env python
"""Try running the script with the -V option (override vars).

e.g.

python [script-name].py -V this 5 -V that ii -V other who?

"""

# Simple one line import statetment.
from pymake import Rule, maker

rules = [Rule("all",
              recipe=("echo environmental variables [this, that, other] \n"
                      "echo equal [{this} {that} {other}]. \n"
                      "echo DEFAULT [1 2 3]"),
              this=1, that=2, other=3)]


if __name__ == '__main__':
    maker(rules)
