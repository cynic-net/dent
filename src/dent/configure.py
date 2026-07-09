''' dent.configure - program configuration from command-line arguments '''

from    argparse  import (
        ArgumentParser, REMAINDER, RawDescriptionHelpFormatter)
from    dataclasses  import dataclass
from    importlib.metadata  import version
from    textwrap import dedent
from    typing  import Literal, get_args

#   Names of the files that -P can print; the functions producing their
#   text are in `dent.image.PRINT_FILE_ARGS`, whose keys mypy checks
#   against this type.
PrintFile = Literal['dockerfile', 'setup-pkg', 'setup-user']

@dataclass
class Config:
    ''' The program configuration, from command-line arguments and
        (eventually) configuration files as well.

        This is deliberately mutable: the program fills in some values as
        they are computed (e.g. `image_alias()` sets `tag`), and there is
        only a single user of this that uses it in a purely sequential
        manner.
    '''
    #   parseargs() exits before constructing this when given the options
    #   that may replace CONTAINER_NAME (--version, -L), so the name is
    #   always present here.
    CONTAINER_NAME  : str
    COMMAND         : list[str]
    base_image      : str|None
    dry_run         : bool
    force_rebuild   : bool
    image           : str|None
    keep_tmpdir     : bool
    print_file      : PrintFile|None
    progress        : bool
    quiet           : bool
    run_opt         : list[str]
    share_ro        : list[str]
    share_rw        : list[str]
    tag             : str|None
    tmpdir          : str|None

def parseargs(argv:list[str]|None=None) -> Config:
    p = ArgumentParser(formatter_class=RawDescriptionHelpFormatter,
        description=dedent('''
            Start a new process in a Docker container, creating the container
            and image if necessary. For detailed documentation, see:
                https://github.com/cynic-net/dent
        '''))

    #   General options
    p.add_argument('--keep-tmpdir', action='store_true',
        help='when done, do not delete tmpdir containing build files')
    p.add_argument('-B', '--base-image',
        help='base image from which to build container image')
    p.add_argument('-n', '--dry-run', action='store_true',
        help="don't execute docker image commands, just print them on stderr")
    p.add_argument('-P', '--print-file', choices=get_args(PrintFile),
        help='Instead of building image, print given file to stdout.')
    p.add_argument('-V', '--progress', action='store_true',
        help='Set --progress=plain on `docker build` to see all build output.')
    p.add_argument('-q', '--quiet', action='store_true')
    p.add_argument('-R', '--force-rebuild', action='store_true',
        help='untag any existing image and rebuild it, ignoring cached images'
             " (only if container doesn't exist)")
    p.add_argument('-r', '--run-opt', action='append', default=[],
        help="command-line option for 'docker run'; may be specifed multiple"
            " times. Use '-r=-e=FOO=bar' syntax!")
    p.add_argument('-s', '--share-ro', action='append', default=[],
        help='Read-only bind mount the given directories to the same paths'
            ' inside the container. Relative paths are relative to $HOME.')
    p.add_argument('-S', '--share-rw', action='append', default=[],
        help='Read-write bind mount the given directories to the same paths'
            ' inside the container. Relative paths are relative to $HOME.')
    p.add_argument('--tmpdir', help='directory to use for Docker build context')

    #   Mutually-exclusive options to determine image name
    pi = p.add_mutually_exclusive_group()
    pi.add_argument('-i', '--image', help='existing image to use'
        ' for creating a new container (downloaded if necessary)')
    pi.add_argument('-t', '--tag',
        help="tag to use for image (default: username); cannot be used with -i")

    #   We must have either a container name or one of the options that
    #   requests information.
    pe = p.add_mutually_exclusive_group(required=True)
    pe.add_argument('CONTAINER_NAME', nargs='?',
        help='container name or ID (required)')
    pe.add_argument('-L', '--list-base-images', action='store_true',
        help='list base images this script knows how to configure')
    pe.add_argument('--version', action='store_true',
        help='show program version information')

    #   All remaining args are the command to run in the container.
    p.add_argument('COMMAND', nargs=REMAINDER, default='SEE BELOW',
        help='command to run in container (default: bash -l)')

    ns = p.parse_args(argv)

    #   `default=` does not work with nargs=REMAINDER. We cannot use
    #   nargs='*' because that will cause options in the remainder to be
    #   interpreted as dent options unless the user adds `--` between,
    #   which is inconvenient.
    if not ns.COMMAND: ns.COMMAND = ['bash', '-l']

    #   We handle these simple options that don't actually run any real
    #   code here, rather than passing them on in the Config, mainly
    #   because version needs access to the ArgumentParser, and we'd
    #   prefer to keep that local.
    if ns.version:
        print(f'{p.prog} version {version(p.prog)}')
        exit(0)
    elif ns.list_base_images:
        #   Imported here because dent.image imports this module.
        from    dent.image  import BASE_IMAGES
        for i in BASE_IMAGES.keys(): print(i)
        exit(0)

    args = vars(ns)
    del args['version'], args['list_base_images']
    return Config(**args)
