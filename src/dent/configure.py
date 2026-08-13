''' dent.configure - program configuration from command-line arguments '''

from    dent.util import die

from    argparse  import (
        ArgumentParser, REMAINDER, RawDescriptionHelpFormatter)
from    dataclasses  import dataclass, fields, field
from    pathlib  import Path
from    textwrap import dedent
from    typing  import Literal, get_args

####################################################################

class ConfigError(RuntimeError): ...

class InternalError(RuntimeError): ...

def consinterr(msg):
    def r(): raise InternalError(msg)
    return r

#####################################################################
#   Argument Parsing Setup Support

def add_dataclass_args(p:ArgumentParser, cls:type) -> None:
    ''' Read through all fields and configure an `ArgumentParser` to parse
        the options (short and long) for each field. See the code for the
        data types that are understood. Anything that isn't one of these or
        is otherwise unusual can be ignored with ``'ignore': True`` in the
        metadata or configured in a custom way with a ``@staticmethod
        cls.add_arg_FIELDNAME()`` function.
    '''
    for f in fields(cls):
        if f.name.isupper():  continue  # Upper-case fields are positional;
                                        # action() must add those at end.
        add_arg = getattr(cls, 'add_arg_' + f.name, None)
        if add_arg:  add_arg(p); continue

        long_opt = '--' + f.name.replace('_', '-')
        args = [long_opt]
        short_opt = short_options.get(long_opt)
        if short_opt:  args = [short_opt] + args
        if f.metadata.get('ignore'):  continue
        help = f.metadata.get('help')
        if f.type is bool:
            p.add_argument(*args, action='store_true', help=help)
        elif f.type == str|None:
            p.add_argument(*args, action='store', default='',
                metavar=f.metadata.get('metavar'), help=help)
        elif f.type == list[str]:   # `is` fails; each subscript is new
            p.add_argument(*args, action='append', default=[],
                metavar=f.metadata.get('metavar'), help=help)
        elif f.type == dict[str,str]:
            p.add_argument(*args, action='append', default=[],
                metavar=f.metadata.get('metavar'), help=help)
        else:
            raise InternalError(
                f"add_dataclass_args didn't handle field '{f.name}'")

def dataclass_fieldnames(cls):
    return tuple( f.name for f in fields(cls) )

####################################################################
#   Configuration Classes

#   We keep a separate list of all short options all together, and sorted
#   by short option name, so we can easily see which short options are
#   assigned and which are free. This includes options for BuildImage,
#   RunImage, Config and options that action() adds itself.
#
short_options = {
    '--base-image':         '-B',
    '--env-copy':           '-e',
   #'--help':               '-h',   # supplied by argparse itself
    '--image':              '-i',
    '--list-base-images':   '-L',
    '--dry-run':            '-n',
    '--print-file':         '-P',
    '--quiet':              '-q',
    '--force-rebuild':      '-R',
    '--run-opt':            '-r',
    '--share-rw':           '-S',
    '--share-ro':           '-s',
    '--tag':                '-t',
    '--progress':           '-V',
}

@dataclass
class BuildImage:
    ''' Create a new image from `base_image`, adding a layer with general
        setup (etckeeper, package updates, minimal extra package set
        including bash, etc.) and a layer for the particular user (user,
        dot-home, etc.).
    '''
    base_image      : str               = field(metadata={ 'ignore':True })
    tag             : str|None          = field(default=None, metadata={
                    'help':'tag for the image built from -B (default: username); requires -B' })
    tmpdir          : str|None          = field(default=None, metadata={
                    'help':'directory to use for Docker build context'})
    keep_tmpdir     : bool              = field(default=False, metadata={
                    'help':'when done, do not delete tmpdir containing build files' })
    force_rebuild   : bool              = field(default=False, metadata={
                    'help':"untag any existing image and rebuild it, ignoring cached images' (requires -B; only if container doesn't exist)" })
    progress        : bool              = field(default=False, metadata={
                    'help':'Set --progress=plain on `docker build` to see all build output.' })

@dataclass
class UseImage:
    ''' Create a container from the existing image named `image`. No
        extra layers are generated; it's used as-is.
    '''
    image           : str

ImageSource = BuildImage | UseImage | None

@dataclass
class RunConfig:
    ' `docker run` parameters: the final step of building the container. '
    run_opt         : list[str]         = field(default_factory=list, metadata={
                    'help':"command-line option for 'docker run'; may be specifed multiple times. Use '-r=-e=FOO=bar' syntax!" })
    set_env         : dict[str,str]     = field(default_factory=dict, metadata={
                    'help':"set the given environment variable when creating the container (i.e., pass --env to 'docker run')" })
    share_ro        : list[str]         = field(default_factory=list, metadata={
                    'help':'Read-only bind mount the given directories to the same paths inside the container. Relative paths are relative to $HOME.' })
    share_rw        : list[str]         = field(default_factory=list, metadata={
                    'help':'Read-write bind mount the given directories to the same paths inside the container. Relative paths are relative to $HOME.' })

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

    ####################################################################
    #   Constructors

    @staticmethod
    def from_args(**args) -> 'Config':
        build_opts = dataclass_fieldnames(BuildImage)
        image_opts = dataclass_fieldnames(UseImage)

        #   argparse always sets arguments; `None`/`False` indicates not given.
        for a in build_opts + image_opts:
            if not args.get(a): del args[a]

        image_source:ImageSource = None
        if 'base_image' in args:
            if 'image' in args:             die('-i conflicts with -B')
            image_source = BuildImage(args['base_image'],
                tag=args.get('tag', None),
                tmpdir=args.get('tmpdir', None),
                keep_tmpdir=args.get('keep_tmpdir', False),
                force_rebuild=args.get('force_rebuild', False),
                progress=args.get('progress', False),
            )
            for a in build_opts: args.pop(a, None)
        elif 'image' in args:
            for b in build_opts:
                if b in args: die(f'force_rebuild conflicts with {b}')
            image_source = UseImage(args['image'])
            del args['image']

        run_config = RunConfig(
            run_opt=args['run_opt'],
            set_env=args['set_env'],
            share_ro=args['share_ro'],
            share_rw=args['share_rw'],
        )
        for a in dataclass_fieldnames(RunConfig):
            args.pop(a, None)

        #   If `base_image` is not specified, other build options like
        #   `force_rebuild` and `tag` are ignored, just as they are ignored
        #   when `base_image` is specified but we don't force a rebuild.
        for a in build_opts:
            args.pop(a, None)
        return Config(image_source=image_source, run_config=run_config, **args)

    @staticmethod
    def testconfig(**kwargs) -> 'Config':
        if 'run_config' not in kwargs:
            #   Config does not have a default RunConfig to ensure that
            #   from_args constructs one. So we need to follow along.
            kwargs['run_config'] = RunConfig()
        return Config(**( { 'CONTAINER_NAME':'Xcname', } | kwargs))

    ####################################################################
    #   Configuration variables and argument parsing

    CONTAINER_NAME  : str
    COMMAND         : list[str]         = field(default_factory=list)
    image_source    : ImageSource       = None
    run_config      : RunConfig         = field(default_factory=consinterr('RunConfig'))
    dry_run         : bool              = field(default=False, metadata={
                    'help':"don't execute docker image commands, just print them on stderr" })
    env_copy        : list[str]         = field(default_factory=list, metadata={
                    'metavar':'NAME',
                    'help':'environment passthrough: copy into the container (at entry time) the named env vars' })
    quiet           : bool              = False

    @staticmethod
    def add_arg_image_source(p:ArgumentParser) -> None:
        #   The image for a new container is either built by us from a base
        #   image or taken as-is; -R and -t configure only the former,
        #   which `Config.from_args()` checks after parsing.
        pi = p.add_mutually_exclusive_group()
        pi.add_argument('-B', '--base-image',
            help='base image from which to build container image')
        pi.add_argument('-i', '--image', help='existing image to use'
            ' for creating a new container (downloaded if necessary)')
        add_dataclass_args(p, BuildImage)

    @staticmethod
    def add_arg_run_config(p:ArgumentParser) -> None:
        add_dataclass_args(p, RunConfig)

    ####################################################################
    #   Configuration matching

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
            return any( dent_shared(m) and src_is(m, p) and rw_is(m, rw)
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
                 for k, v in sorted(self.run_config.set_env.items())
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
                 if dent_shared(m) and m.get('Destination') not in requested ]

    def share_paths(self) -> list[tuple[Path,bool]]:
        ''' Absolute paths of the `share_ro` and `share_rw` entries, each
            paired with a writability flag. Relative paths are taken as
            relative to `Path.home()`.
        '''
        home = Path.home()
        return [ (home / s, False) for s in self.run_config.share_ro ] \
             + [ (home / s, True)  for s in self.run_config.share_rw ]

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

#   action()'s options must stay in sync with Config's fields:
#   Config(**args) enforces the match at runtime. XXX To be truly
#   generated from a directive table once config-file support lands.
def action(argv:list[str]|None=None) -> Action:
    ''' Parse the command line, returning the `Action` it requests.

        This is pure but for one exception: ArgumentParser itself prints
        and exits for bad arguments and --help.
    '''
    parser = ArgumentParser(formatter_class=RawDescriptionHelpFormatter,
        description=dedent('''
            Start a new process in a Docker container, creating the container
            and image if necessary. For detailed documentation, see:
                https://github.com/cynic-net/dent
        '''))
    add_dataclass_args(parser, Config)
    #   Options indicating the action we take.
    pact = parser.add_mutually_exclusive_group(required=True)
    pact.add_argument('CONTAINER_NAME', nargs='?',
        help='container name or ID (required)')
    pact.add_argument('-L', '--list-base-images', action='store_true',
        help='list base images this script knows how to configure')
    pact.add_argument('-P', '--print-file', choices=get_args(PrintFile.Name),
        help='instead of entering a container, print given file to stdout')
    pact.add_argument('--version', action='store_true',
        help='show program version information')
    #   For Entry action, all remaining args are the command to run in the
    #   container.
    parser.add_argument('COMMAND', nargs=REMAINDER, default='SEE BELOW',
        help='command to run in container (default: bash -l)')

    ns = parser.parse_args(argv)
    if ns.version:              return PrintVersion()
    if ns.list_base_images:     return ListBaseImages()
    if ns.print_file:           return PrintFile(ns.print_file, ns.base_image)
    #   Otherwise fallthrough to validate and set up `Entry`.

    #   `default=` does not work with nargs=REMAINDER. We cannot use
    #   nargs='*' because that will cause options in the remainder to be
    #   interpreted as Dent options unless the user adds `--` between,
    #   which is inconvenient.
    if not ns.COMMAND: ns.COMMAND = ['bash', '-l']

    args = vars(ns)
    del args['version'], args['list_base_images'], args['print_file']
    #   argparse collects --set-env options as a list; RunConfig wants a dict.
    try: args['set_env'] = dict( kv.split('=', 1) for kv in args['set_env'] )
    except ValueError: parser.error('--set-env arguments must be NAME=VALUE')
    return Enter(Config.from_args(**args))

####################################################################
#   Predicates used to compare configuration against inspect output.

def is_bind(cont:dict) -> bool:
    return cont.get('Type') == 'bind'

def src_is(cont:dict, p:Path) -> bool:
    return cont.get('Source') == str(p)

def rw_is(cont:dict, rw:bool) -> bool:
    ' A missing ``RW`` key is taken as read-only. '
    return bool(cont.get('RW')) == rw

def dent_shared(m:dict) -> bool:
    ''' `m` looks as if it was shared via a Dent -s/-S option: it's
        bind-mounted at the same path inside and outside the container.

        >>> dent_shared({ 'Type':'bind', 'Source':'/a', 'Destination':'/a' })
        True
        >>> dent_shared({ 'Type':'volume', 'Source':'/a', 'Destination':'/a' })
        False
        >>> dent_shared({ 'Type':'bind', 'Source':'/a', 'Destination':'/b' })
        False
    '''
    return is_bind(m) and m.get('Source') == m.get('Destination')
