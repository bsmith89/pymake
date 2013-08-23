#!/usr/bin/env python3
"""The utility classes and functions for pymake.

"""

import re
import os
import contextlib
import threading
import math
import subprocess
import logging


LOG = logging.getLogger(__name__)


class Rule():
    """Prescription for going from prerequisites to target.

    Defines the target, prerequisites, and rules for going from the latter
    to the former.

    >>> r = Rule(trgt="(.*).{txt_exten}",
    ...          preqs=["{0}.{tsv_exten}"],
    ...          recipe="./tsv2txt {preqs[0]} > {trgt}",
    ...          txt_exten="txt", tsv_exten="tsv")
    >>> # a new rule describing how to go from a tsv to a txt file

    """

    def __init__(self, trgt, preqs=[], recipe="", order_only=False, **env):
        """Create a new Rule object.

        *trgt* - a regex pattern which matches applicable targets
        *preqs* - [optional] a list of str.format() style prerequisite templates
        *recipe* - [optional] a str.format() style recipe (shell commands)
        *order_only* - should the target be updated when prerequisites are newer.
        *env* - additional variables available to templates

        """
        self.trgt_pattern = trgt
        self.preqs_template = preqs
        self.recipe_template = recipe
        self.order_only = order_only
        self.env = env

    def __repr__(self):
        return ("{self.__class__.__name__}(trgt={self.trgt_pattern!r}, "
                "preqs={self.preqs_template!r}, "
                "recipe={self.recipe_template!r}, "
                "order_only={self.order_only}, "
                "**{self.env})").format(self=self)

    def update_env(self, env):
        """Add or update the *self.env* dictionary with *env*."""
        self.env.update(env)

    def _match(self, trgt):
        """Return groups matched by the target pattern in *trgt*.

        value: A tuple of strings.

        """
        pattern = "^" + self.trgt_pattern + "$"
        match = re.match(pattern, trgt)
        if match is not None:
            return match.groups()
        else:
            raise ValueError("{trgt} does not match {ptrn}".\
                             format(trgt=trgt, ptrn=pattern))

    def applies(self, trgt):
        """Return if the value of *trgt* matches the target pattern."""
        try:
            self._match(trgt)
        except ValueError:
            return False
        else:
            return True

    def get_preqs(self, trgt):
        """Return the prerequisite templates filled for *trgt*."""
        groups = self._match(trgt)
        preqs = [template.format(*groups, trgt=trgt, **self.env)
                 for template in self.preqs_template]
        return preqs

    def get_recipe(self, trgt):
        """Return the recipe template filled for *trgt*."""
        groups = self._match(trgt)
        preqs = self.get_preqs(trgt)
        # Make the str representation of *preqs* a space delimited list.
        class list_wrapper(list):
            def __str__(self):
                return " ".join(self.__iter__())
        wrapped_preqs = list_wrapper(preqs)
        recipe = self.recipe_template.format(*groups, trgt=trgt,
                                             preqs=wrapped_preqs, **self.env)
        return recipe


@contextlib.contextmanager
def backup(path, append="~", prepend="", on_fail=None):
    """Backup path while context manager is active.

    Names the backup using the prefix *prepend* and the suffix *append*.

    If an error occurs while active, *on_fail* is called on *path* before
    exiting.

    """
    backup_path = os.path.join(os.path.dirname(path),
                               prepend + os.path.basename(path) + append)
    original_exists = os.path.exists(path)
    if original_exists:
        os.rename(path, backup_path)
    try:
        yield
    except Exception as err:
        new_exists = os.path.exists(path)
        if original_exists:
            os.rename(backup_path, path)
        elif new_exists and else_on_fail:
            on_fail(path)
        raise err
    else:
        if original_exists:
            os.remove(backup_path)


def extract_rule(trgt, rules):
    """Return the first rule in *rules* that matches *trgt* and the remainder.

    """
    rules = list(rules)
    req = None
    for i, rule in enumerate(rules):
        if rule.applies(trgt):
            del rules[i]
            return rule, rules
    else:
        return None, rules


def make_req(trgt, rules):
    """Return a fully initialized Req object for *trgt*.

    Will fill the requirements of trgt recursively.

    """
    rule, remaining = extract_rule(trgt, rules)
    if rule:
        requires = [make_req(preq, remaining) for preq in rule.get_preqs(trgt)]
        recipe = rule.get_recipe(trgt)
        if recipe:
            return TaskReq(trgt, requires, recipe, order_only=rule.order_only)
        else:
            return DummyReq(trgt, requires)
    else:
        return FileReq(trgt)


class Req():
    """The base class for all requirements.

    TODO: Make a self.err_event
    """

    instances = {}

    def __init__(self, trgt):
        """Create a new Req object for trgt."""
        self.trgt = trgt
        Req.instances[trgt] = self
        self.err_event = threading.Event()

    def __repr__(self):
        return "{self.__class__.__name__}({self.trgt!r})".format(self=self)

    def __str__(self):
        return "{self.__class__.__name__}({self.trgt!r})".format(self=self)

    def formatted(self):
        return self.__str__()

    def __eq__(self, other):
        """req1 == req2 <==> req1.trgt == req2.trgt"""
        return self.trgt == other.trgt

    def trgt_exists(self):
        return os.path.exists(self.trgt)

    def __hash__(self):
        return hash(self.trgt)

    def last_update(self):
        """Return the last time *trgt* was updated."""
        raise NotImplementedError("last_update() has not been implemented "
                                  "for this class, which is therefore not "
                                  "a functioning Req subclass.")

    def check_uptodate(self):
        """Determine if the requirement needs to be updated."""
        raise NotImplementedError("find_needs_update() has not been "
                                  "implemented for this class, which is "
                                  "therefore not a functioning Req subclass.")


class FileReq(Req):
    """Subclass of Req for files."""

    def last_update(self):
        """Return the last time the file, *trgt*, was updated.

        Returns float('nan') if *trgt* does not exist.

        """
        if os.path.exists(self.trgt):
            return os.path.getmtime(self.trgt)
        else:
            return float('nan')

    def check_uptodate(self):
        """Return the last time *self.trgt* was updated.

        Since FileReq objects are always up-to-date if they exist,
        this doesn't actually set a property.deleter(

        It just returns the last update time for recursive purposes.

        """
        return self.last_update()

    def run(self, *args, **kwargs):
        """Ensure that *self.trgt* exists."""
        if not self.trgt_exists():
            self.err_event.set()
            raise ValueError(("{self.trgt!r} not found. "
                              "Did you expect this file to exist? "
                              "Maybe you're missing a rule...?").\
                             format(self=self))
        LOG.debug("{self!s} exists".format(self=self))


def of_non_nan(func, iterable):
    """Return the value of func for non-NaN elements of *iterable*.

    If all values are NaN or iterable is of length zero, return NaN.

    """
    non_nan_vals = [val for val in iterable if not math.isnan(val)]
    if non_nan_vals:
        return func(non_nan_vals)
    else:
        return None


class HierReq(Req):
    """Subclass of Req for any target that is runnable or has prerequisites.

    """


    def __init__(self, trgt, requires):
        """Create a new HierReq object for *trgt*, given *requires*."""
        super(HierReq, self).__init__(trgt)
        self.requires = requires
        self.uptodate = False
        # Doesn't this mean uptodate is getting checked two
        # or more times?  Once for construction, and
        # then once every time it's called recursively?
        # TODO
        self.run_lock = threading.Lock()

    def __repr__(self):
        return super(HierReq, self).__repr__().rstrip(')') + \
               ", {self.requires})".format(self=self)

    def formatted(self):
        """Return a pretty-formatted description of the Req."""
        out_string = super(HierReq, self).formatted()
        out_string += "\n  |UP TO DATE| {}".format(self.uptodate)
        req_strings = []
        for req in self.requires:
            for line in req.formatted().split('\n'):
                 req_strings += ["    {}".format(line)]
        if req_strings:
            out_string += '\n'.join(["\n  |REQUIRES|"] + req_strings)
        return out_string

    def check_uptodate(self):
        """Determine if the requirement needs to be updated.

        An update is required if any upstream requirements exist and
        they are newer than *trgt*, or if neither upstream requirements
        nor *trgt* exist.

        """
        if self.uptodate:
            LOG.debug(("{self!s} is flagged up-to-date and will not be, "
                      "re-checked.").format(self=self))
            # By definition, if the requirement is uptodate than its
            # timestamp is the largest.
            return self.last_update()
        LOG.debug("determining if {self!s} is up-to-date".\
                  format(self=self))
        last_update = self.last_update()
        max_usts = of_non_nan(max, (preq.check_uptodate()
                                    for preq in self.requires))
        if not self.trgt_exists():
            LOG.debug(("since {self.trgt!r} does not exist, flagging {self!s} "
                       "as not up-to-date").format(self=self))
            self.uptodate = False
            if max_usts:
                return max_usts
            else:
                return float('nan')
        elif not max_usts:
            LOG.debug(("since {self.trgt!r} exists, and no preqs exist, "
                        "flagging {self!s} as up-to-date").format(self=self))
            self.uptodate = True
            return last_update
        elif last_update > max_usts:
            LOG.debug(("{self.trgt!r} is newer than all preqs; flagging "
                       "{self!s} as up-to-date").format(self=self))
            self.uptodate = True
            return last_update
        elif last_update <= max_usts:
            LOG.debug(("{self.trgt!r} is older ({}) than all preqs (max={}); "
                       "flagging {self!s} as uptodate").\
                     format(last_update, max_usts, self=self))
            self.uptodate = False
            return max_usts
        else:
            raise ValueError(("Somehow the up-to-date status of {self!s} "
                              "cannot be determined.").format(self=self))

    def do(self, *args, **kwargs):
        """Execute the work defined for the requirement.""" 
        raise NotImplementedError("do() has not been implemented "
                                  "for this class, which is therefore not "
                                  "a functioning HierReq subclass.")

    def run(self, *args, err_event=None, **kwargs):
        """Run, recursively, the requirement and all of its prerequisites.

        Requirements which are already up-to-date are not run and neither are
        their prerequisites.

        TODO: This method is clearly far too large!

        """
        self.run_lock.acquire()
        if self.uptodate:
            LOG.info("{self!s} already up-to-date".format(self=self))
            self.run_lock.release()
            return
        elif self.err_event.is_set():
            LOG.debug("{self!s had an error".format(self=self))
            self.run_lock.release()
            return
        else:
            LOG.debug("attempting to run {self!s}".format(self=self))
            if self.requires:
                LOG.debug("running all preqs of {self!s}".format(self=self))
                preq_threads = []
                for preq in self.requires:
                    thread = threading.Thread(target=preq.run,
                                              args=args, kwargs=kwargs)
                    preq_threads += [thread]
                    thread.start()
                for preq, thread in zip(self.requires, preq_threads):
                    thread.join()
                    if preq.err_event.is_set():
                        LOG.critical("preq: {preq!s} had an error; exiting.".\
                                     format(preq=preq))
                        self.err_event.set()
                        self.run_lock.release()
                        return
        LOG.debug("calling {self!s}.do()".format(self=self))
        self.do(*args, **kwargs)
        self.done = True
        if self.err_event.is_set():
            LOG.critical("{self!s} had an error; exiting".format(self=self))
            self.run_lock.release()
            return
        LOG.debug("{self!s} done".format(self=self))
        self.run_lock.release()
        return


class TaskReq(HierReq, FileReq):
    """Subclass of HierReq for a requirement which involves _doing_ something.

    """

    def __init__(self, trgt, requires, recipe, order_only=False):
        """Create a new TaskReq."""
        self.order_only = order_only
        self.recipe = recipe
        super(TaskReq, self).__init__(trgt, requires)


    def __repr__(self):
        return super(TaskReq, self).__repr__().rstrip(')') + \
               (", {self.recipe!r}, order_only={self.order_only})").\
               format(self=self)

    def formatted(self):
        """Return a pretty-formatted description of the Req."""
        out_string = super(TaskReq, self).formatted()
        recipe_strings = []
        for line in self.recipe.split('\n'):
            recipe_strings += ["    {}".format(line)]
        out_string += '\n'.join(["\n  |RECIPE|"] + recipe_strings)
        return out_string


    def do(self, *args, execute=True, **kwargs):
        """Print and execute the recipe."""
        if self.order_only and self.trgt_exists():
            LOG.debug("order-only requirement; will not be executed")
        else:
            LOG.info(self.recipe)
            if execute:
                with backup(self.trgt, append="~pymake-backup", prepend=".",
                            on_fail=os.remove):
                    proc = subprocess.Popen(self.recipe, shell=True,
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT,
                                            bufsize=4096)
                    for encoded_line in proc.stdout:
                        line = encoded_line.decode()
                        LOG.info(line.rstrip("\n"))
                    if proc.wait() != 0:
                        self.err_event.set()
                        raise subprocess.CalledProcessError(proc.returncode,
                                                            self.recipe)


class DummyReq(HierReq):
    """Subclass of HierReq for a requirement which has preqs, but no recipe.

    """

    def last_update(self):
        return float('nan')

    def do(self, *args, verbose=True, **kwargs):
        LOG.info("finished {self.trgt!r}".format(self=self))


def main():
    logging.basicConfig(level=logging.DEBUG,
                        format=("(%(threadName)s):"
                                "%(levelname)s\t"
                                "%(message)s"))
    rules = [Rule("all", ["final.txt"]),
             Rule("final.txt", ["extant.txt", "to_make.txt"],
                  "cat {preqs} > final.txt"),
             Rule("to_make.txt", ["required_to_make.txt"],
                  "cat required_to_make.txt > to_make.txt"),
             Rule("required_to_make.txt", [],
                  "echo 'this is a msg' > required_to_make.txt")]
    requirement = make_req("all", rules)
    requirement.check_uptodate()
    requirement.run(execute=True)
    pass

if __name__ == '__main__':
    main()
