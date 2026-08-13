''' dent.configure - program configuration from command-line arguments '''

from    dent.util import die

from    argparse  import (
        ArgumentParser, REMAINDER, RawDescriptionHelpFormatter)
from    dataclasses  import dataclass
from    textwrap import dedent
from    typing  import Literal, get_args

####################################################################

class ConfigError(RuntimeError): ...

@dataclass
class BuildImage:
    ''' Create a new image from `base_image`, adding a layer with general
        setup (etckeeper, package updates, minimal extra package set
        including bash, etc.) and a layer for the particular user (user,
        dot-home, etc.).
    '''
    base_image      : str
    force_rebuild   : bool          # default: False
    tag             : str|None      # default `tag` supplied by build system

@dataclass
class UseImage:
    ''' Create a container from the existing image named `image`. No
        extra layers are generated; it's used as-is.
    '''
    image           : str

ImageSource = BuildImage | UseImage | None

@dataclass
class Config:
    ''' The program configuration for building and entering a container.
        Built from command-line arguments and (eventually) configuration
        files as well.

        This is deliberately mutable: the program fills in some values as
        they are computed (e.g. `build_image()` sets `tmpdir`), and there
        is only a single user of this that uses it in a purely sequential
        manner.
    '''

    CONTAINER_NAME  : str
    COMMAND         : list[str]
    image_source    : ImageSource
    dry_run         : bool
    env_copy        : list[str]
    keep_tmpdir     : bool
    progress        : bool
    quiet           : bool
    run_opt         : list[str]
    share_ro        : list[str]
    share_rw        : list[str]
    tmpdir          : str|None

    @staticmethod
    def from_args(**args) -> 'Config':
        #   argparse always sets arguments; `None`/`False` indicates not given.
        for a in ('image', 'base_image', 'force_rebuild', 'tag'):
            if not args.get(a): del args[a]

        image_source:ImageSource = None
        if 'base_image' in args:
            if 'image' in args:             die('-i conflicts with -B')
            image_source = BuildImage(args['base_image'],
                args.get('force_rebuild', False), args.get('tag', None))
            for a in ('base_image', 'force_rebuild', 'tag'):  args.pop(a, None)
        elif 'image' in args:
            if 'force_rebuild' in args:     die('-R conflicts with -i')
            if 'tag' in args:               die('-R conflicts with -t')
            image_source = UseImage(args['image'])
            del args['image']

        #   If `base_image` is not specified, `force_rebuild` and `tag` are
        #   ignored, just as they are ignored when `base_image` is specified
        #   but we don't force a rebuild.
        args.pop('force_rebuild', None); args.pop('tag', None)
        return Config(image_source=image_source, **args)


    @staticmethod
    def testconfig(**kwargs) -> 'Config':
        defaults:dict = {
            'CONTAINER_NAME':'Xcname', 'COMMAND':[],
            'dry_run':False, 'keep_tmpdir':False,
            'progress':False, 'quiet':False,
            'image_source':None, 'tmpdir':None,
            'run_opt':[], 'share_ro':[], 'share_rw':[],
            'env_copy':[],
            }
        return Config(**(defaults|kwargs))

####################################################################
#   Actions that tell the program what to do.

@dataclass(frozen=True)
class PrintVersion: ...

@dataclass(frozen=True)
class ListBaseImages: ...

@dataclass(frozen=True)
class PrintFile:
    #   Names of the files that -P can print; the functions producing their
    #   text are in `dent.image.PRINT_FILE_ARGS`, whose keys mypy checks
    #   against this type.
    Name = Literal['dockerfile', 'setup-pkg', 'setup-user']

    file        : Name
    base_image  : str|None      # the file contents depend on this

@dataclass(frozen=True)
class Enter:
    ''' Not technically necessary, as we could just make this directly
        a `Config`, but this better matches the "Action is a verb saying
        what to do" format here, and Haskell's
        ``data Action = Entry Config | PrintVersion | …``.
    '''

    config      : Config

Action = Enter | PrintVersion | ListBaseImages | PrintFile

def action(argv:list[str]|None=None) -> Action:
    ''' Parse the command line, returning the `Action` it requests.

        This is pure but for one exception: ArgumentParser itself prints
        and exits for bad arguments and --help.
    '''
    p = ArgumentParser(formatter_class=RawDescriptionHelpFormatter,
        description=dedent('''
            Start a new process in a Docker container, creating the container
            and image if necessary. For detailed documentation, see:
                https://github.com/cynic-net/dent
        '''))

    #   General options that apply to most commands
    p.add_argument('-n', '--dry-run', action='store_true',
        help="don't execute docker image commands, just print them on stderr")
    p.add_argument('-q', '--quiet', action='store_true')

    #   The image for a new container is either built by us fromR a base
    #   image or taken as-is; -R and -t configure onlRy the former, which
    #   `Config.from_args()` checks after parsing.
    pi = p.add_mutually_exclusive_group()
    pi.add_argument('-B', '--base-image',
        help='base image from which to build container image')
    pi.add_argument('-i', '--image', help='existing image to use'
        ' for creating a new container (downloaded if necessary)')

    #   Options that apply to building images and containers
    p.add_argument('--keep-tmpdir', action='store_true',
        help='when done, do not delete tmpdir containing build files')
    p.add_argument('-V', '--progress', action='store_true',
        help='Set --progress=plain on `docker build` to see all build output.')
    p.add_argument('-R', '--force-rebuild', action='store_true',
        help='untag any existing image and rebuild it, ignoring cached images'
             " (requires -B; only if container doesn't exist)")
    p.add_argument('-t', '--tag', help='tag for the image built from -B'
        ' (default: username); requires -B')
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

    #   Options that apply to entering containers
    p.add_argument('-e', '--env-copy', metavar='NAME',
        action='append', default=[], help='environment passthrough: copy'
        ' into the container (at entry time) the named env vars')

    #   We must have either a container name or one of the options that
    #   requests information.
    pe = p.add_mutually_exclusive_group(required=True)
    pe.add_argument('CONTAINER_NAME', nargs='?',
        help='container name or ID (required)')
    pe.add_argument('-L', '--list-base-images', action='store_true',
        help='list base images this script knows how to configure')
    pe.add_argument('-P', '--print-file', choices=get_args(PrintFile.Name),
        help='instead of entering a container, print given file to stdout')
    pe.add_argument('--version', action='store_true',
        help='show program version information')

    #   All remaining args are the command to run in the container.
    p.add_argument('COMMAND', nargs=REMAINDER, default='SEE BELOW',
        help='command to run in container (default: bash -l)')

    ns = p.parse_args(argv)

    if ns.version:              return PrintVersion()
    if ns.list_base_images:     return ListBaseImages()
    if ns.print_file:           return PrintFile(ns.print_file, ns.base_image)

    #   `default=` does not work with nargs=REMAINDER. We cannot use
    #   nargs='*' because that will cause options in the remainder to be
    #   interpreted as Dent options unless the user adds `--` between,
    #   which is inconvenient.
    if not ns.COMMAND: ns.COMMAND = ['bash', '-l']

    args = vars(ns)
    del args['version'], args['list_base_images'], args['print_file']
    return Enter(Config.from_args(**args))
