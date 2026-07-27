''' dent.configure - program configuration from command-line arguments '''

from    argparse  import (
        ArgumentParser, REMAINDER, RawDescriptionHelpFormatter)
from    dataclasses  import dataclass
from    pathlib  import Path
from    textwrap import dedent
from    typing  import Literal, get_args

#   Names of the files that -P can print; the functions producing their
#   text are in `dent.image.PRINT_FILE_ARGS`, whose keys mypy checks
#   against this type.
PrintFileName = Literal['dockerfile', 'setup-pkg', 'setup-user']

####################################################################
#   Commands: requests that main() do something entirely different
#   from the standard Dent container entry (which is specified by a
#   Config, below).

@dataclass(frozen=True)
class PrintVersion: ...

@dataclass(frozen=True)
class ListBaseImages: ...

@dataclass(frozen=True)
class PrintFile:
    file        : PrintFileName
    base_image  : str|None      # the file contents depend on this

Command = PrintVersion | ListBaseImages | PrintFile

def share_shaped(m:dict) -> bool:
    ''' `m` looks like a Dent share option's mount: bind-mounted at the
        same path inside and outside the container.

        >>> share_shaped({ 'Type':'bind', 'Source':'/a', 'Destination':'/a' })
        True
        >>> share_shaped({ 'Type':'volume', 'Source':'/a', 'Destination':'/a' })
        False
        >>> share_shaped({ 'Type':'bind', 'Source':'/a', 'Destination':'/b' })
        False
    '''
    return is_bind(m) and m.get('Source') == m.get('Destination')

@dataclass
class Config:
    ''' The program configuration, from command-line arguments and
        (eventually) configuration files as well.

        This is deliberately mutable: the program fills in some values as
        they are computed (e.g. `image_alias()` sets `tag`), and there is
        only a single user of this that uses it in a purely sequential
        manner.
    '''
    #   parseargs() returns a Command instead of constructing this when
    #   given the options that may replace CONTAINER_NAME (--version, -L,
    #   -P), so the name is always present here.
    CONTAINER_NAME  : str
    COMMAND         : list[str]
    base_image      : str|None
    dry_run         : bool
    env_copy        : list[str]
    force_rebuild   : bool
    image           : str|None
    keep_tmpdir     : bool
    progress        : bool
    quiet           : bool
    run_opt         : list[str]
    set_env         : dict[str,str]
    share_ro        : list[str]
    share_rw        : list[str]
    tag             : str|None
    tmpdir          : str|None

    @staticmethod
    def testconfig(**kwargs) -> 'Config':
        defaults:dict = { 'CONTAINER_NAME':'Xcname', 'COMMAND':[],
            'base_image':None, 'dry_run':False, 'env_copy':[],
            'force_rebuild':False, 'image':None, 'keep_tmpdir':False,
            'progress':False, 'quiet':False, 'run_opt':[], 'set_env':{},
            'share_ro':[], 'share_rw':[], 'tag':None, 'tmpdir':None,
            }
        return Config(**(defaults|kwargs))

    def container_mismatches(self, inspect:dict, share:Path) -> list[str]:
        ''' Return warnings describing how this container differs from the
            configuration requested for this container. (These are normally
            displayed as warnings, just to let you know you might want to
            rebuild.)
        '''
        ms  = self.mount_mismatches(inspect, share)
        ms += self.env_mismatches(inspect)
        #   XXX Enable these once we have config files to hold the options
        #   that would suppress the messages; otherwise we have to write
        #   the whole creation command line every time.
        #ms += self.extra_mounts(inspect, share)
        #ms += self.extra_env(...)
        #ms += self.image_mismatches(...)
        return ms

    def mount_mismatches(self, inspect:dict, share:Path) -> list[str]:
        ''' Warnings for configured shares that are not bind-mounted at the
            same path in the container with the requested writability, and
            for the Dent share when not mounted read-write from `share` on
            the host.
        '''
        mounts = inspect.get('Mounts') or []
        def mounted(p:Path, rw:bool) -> bool:
            return any( share_shaped(m) and src_is(m, p) and rw_is(m, rw)
                        for m in mounts )
        ms = [ 'existing container does not mount {} {}'
                    .format(p, 'read-write' if rw else 'read-only')
                for p, rw in self.share_paths() if not mounted(p, rw) ]
        #   For the Dent share only the host-side Source and writability
        #   matter: the in-container path may differ in older containers,
        #   which the dent-share script handles itself.
        if not any( is_bind(m) and src_is(m, share) and rw_is(m, True)
                    for m in mounts ):
            ms.append('existing container does not mount the Dent share {}'
                ' read-write'.format(share))
        return ms

    def env_mismatches(self, inspect:dict) -> list[str]:
        ''' Warnings for configured environment variables (`set_env`) that
            the existing container described by the ``docker inspect``
            output `inspect` was not created with, per its ``Config.Env``.
        '''
        env = { k: v for k, v in
                ( kv.split('=', 1)
                  for kv in (inspect.get('Config') or {}).get('Env') or []
                  if '=' in kv ) }
        return [ 'existing container does not set {}={}'.format(k, v)
                 for k, v in sorted(self.set_env.items())
                 if env.get(k) != v ]

    def extra_mounts(self, inspect:dict, share:Path) -> list[str]:
        ''' Descriptions of mounts in the existing container described by
            `inspect` that look like shares (bind mounts at the same path
            inside and out) but are neither requested by this Config nor
            the Dent share `share`. These tell the user the container does
            *more* than the current invocation requests, typically due to
            options given when it was created.

            XXX These are not yet displayed to the user: until config
            files land (supplying the full share list on every entry, and
            allowing suppression for regularly-used foreign images) they
            would nag on every entry that varies options from creation.
        '''
        requested = { str(p) for p, _ in self.share_paths() } | { str(share) }
        return [ 'existing container also mounts {} {}'
                    .format(m['Destination'],
                        'read-write' if m.get('RW') else 'read-only')
                 for m in (inspect.get('Mounts') or [])
                 if share_shaped(m) and m.get('Destination') not in requested ]

    def share_paths(self) -> list[tuple[Path,bool]]:
        ''' Absolute paths of the `share_ro` and `share_rw` entries, each
            paired with a writability flag. Relative paths are taken as
            relative to `Path.home()`.
        '''
        home = Path.home()
        return [ (home / s, False) for s in self.share_ro ] \
             + [ (home / s, True)  for s in self.share_rw ]

    def extra_env(self):
        ''' Warnings for environment variables the existing container was
            created with but that this configuration does not request.
        '''
        #   Unlike extra_mounts(), where shares are recognizable by shape,
        #   the container's Config.Env does not distinguish user-requested
        #   variables from the image's own ENV and those Dent itself sets
        #   at creation (DENT_CONTAINER, LOGNAME, USER, XDG_*, etc.). So
        #   this needs the *image's* Config.Env (from the image inspection
        #   that image_mismatches() will also need) to subtract, plus an
        #   exclusion list of Dent's own variables.

    def image_mismatches(self):
        ''' Check that the base-images's layers are a prefix of the
            container's image's layers.
        '''
        #   To do this we need to inspect the base image and the
        #   container's image (which ID we get from the container
        #   inspection).

####################################################################
#   Parseargs options must stay in sync with Config's fields:
#   Config(**args) enforces the match at runtime. XXX To be truly
#   generated from a directive table once config-file support lands.

def parseargs(argv:list[str]|None=None) -> Command|Config:
    ''' Parse the command line, returning a `Command` for options that
        request something other than the standard container entry, or
        otherwise the `Config` describing that entry.

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

    #   Options that apply to building images and containers
    p.add_argument('--keep-tmpdir', action='store_true',
        help='when done, do not delete tmpdir containing build files')
    p.add_argument('-B', '--base-image',
        help='base image from which to build container image')
    p.add_argument('-V', '--progress', action='store_true',
        help='Set --progress=plain on `docker build` to see all build output.')
    p.add_argument('-R', '--force-rebuild', action='store_true',
        help='untag any existing image and rebuild it, ignoring cached images'
             " (only if container doesn't exist)")
    p.add_argument('-r', '--run-opt', action='append', default=[],
        help="command-line option for 'docker run'; may be specifed multiple"
            " times. Use '-r=-e=FOO=bar' syntax!")
    p.add_argument('--set-env', metavar='NAME=VALUE', action='append',
        default=[], help='set the given environment variable when creating'
            " the container (i.e., pass --env to 'docker run')")
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

    #   Options that apply to entering containers
    pi.add_argument('-e', '--env-copy', metavar='NAME',
        action='append', default=[], help='environment passthrough: copy'
        ' into the container (at entry time) the named env vars')

    #   We must have either a container name or one of the options that
    #   requests information.
    pe = p.add_mutually_exclusive_group(required=True)
    pe.add_argument('CONTAINER_NAME', nargs='?',
        help='container name or ID (required)')
    pe.add_argument('-L', '--list-base-images', action='store_true',
        help='list base images this script knows how to configure')
    pe.add_argument('-P', '--print-file', choices=get_args(PrintFileName),
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
    #   argparse collects repeated --set-env options as a list; Config
    #   wants a dict.
    try:
        args['set_env'] = { k: v for k, v in
                            (kv.split('=', 1) for kv in args['set_env']) }
    except ValueError:
        p.error('--set-env arguments must be NAME=VALUE')
    return Config(**args)

####################################################################
#   Predicates used to compare configuration against inspect output.

def is_bind(cont:dict) -> bool:
    return cont.get('Type') == 'bind'

def src_is(cont:dict, p:Path) -> bool:
    return cont.get('Source') == str(p)

def rw_is(cont:dict, rw:bool) -> bool:
    ' A missing ``RW`` key is taken as read-only. '
    return bool(cont.get('RW')) == rw

