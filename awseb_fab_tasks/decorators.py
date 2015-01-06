from functools import wraps
import inspect
from fabric.api import env, prompt


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

            for arg_item in required_args:
                if len(arg_item) == 3:
                    arg, extra, default = arg_item
                elif len(arg_item) == 2:
                    arg, extra = arg_item
                    default = None
                else:
                    raise Exception("args_required takes only 2 or 3 arguments. Received {}".format(arg_item))

                val = newargs.get(arg, env.get(arg, Undefined))
                if val is Undefined:
                    if default:
                        val = prompt('Please enter {0} {1} [default: {2}]: '.format(arg, extra, default))
                        if not val:
                            val = default
                    else:
                        val = prompt('Please enter {0} {1}: '.format(arg, extra))
                newargs[arg] = val
                env[arg] = val

            fn(**newargs)
        return inner

    return deco


class Undefined(object):
    """ Sentinel used by args_required. """
    pass