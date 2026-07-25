''' dent.util - constants and utility functions used throughout dent '''

from    pwd import getpwuid
from    sys import argv, stderr
from    typing  import NoReturn
import  os

PROGNAME    = os.path.basename(argv[0])
PWENT       = getpwuid(os.getuid())

def qprint(quiet:bool, *args, force_print=False, **kwargs):
    ''' Call `print()` on arguments unless `quiet` is set.

        `force_print` will print even if `quiet` is set; this allows the
        caller to test on a second condition without having to use ``if``
        and a duplicate call to `print()`.
    '''
    if force_print or not quiet:
        print('-----', *args, **kwargs)

def warn(msg):
    print(PROGNAME + ': warning:', msg, file=stderr)

def die(msg) -> NoReturn:
    print(PROGNAME + ':', msg, file=stderr)
    exit(1)
