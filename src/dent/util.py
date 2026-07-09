''' dent.util - constants and utility functions used throughout dent '''

from    argparse  import Namespace
from    pwd import getpwuid
from    sys import argv, stderr
import  os

PROGNAME    = os.path.basename(argv[0])
PWENT       = getpwuid(os.getuid())

def qprint(conf:Namespace, *args, force_print=False, **kwargs):
    ''' Call `print()` on arguments unless quiet flag is set.

        `force_print` will print even if args.quiet is set; this allows the
        caller to test on a second condition without having to use ``if``
        and a duplicate call to `print()`.
    '''
    if force_print or not conf.quiet:
        print('-----', *args, **kwargs)

def die(msg):
    print(PROGNAME + ':', msg, file=stderr)
    exit(1)
