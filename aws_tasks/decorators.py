#import logging
from functools import wraps
import inspect
#import sys

from fabric.api import env, prompt

# remove dependency on boulanger, from boulanger.decorators import args_required

def args_required(*required_args):
    def deco(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            argspec = inspect.getargspec(fn)
            oldargs = list(args)
            newargs = kwargs.copy()
            for arg in argspec.args:
                if arg not in kwargs:
                    try:
                        newargs[arg] = oldargs.pop(0)
                    except IndexError:
                        pass
            for arg, extra in required_args:
                val = newargs.get(arg, env.get(arg, Undefined))
                if val is Undefined:
                    val = prompt('Please enter {0} {1}: '.format(arg, extra))
                newargs[arg] = val
                env[arg] = val

            fn(**newargs)
        return inner
    return deco


class Undefined(object):
    """ Sentinel used by args_required. """
    pass