''' dent.configure - program configuration from command-line arguments '''

from    argparse  import (
        ArgumentParser, REMAINDER, RawDescriptionHelpFormatter, Namespace)
from    importlib.metadata  import version
from    textwrap import dedent
from    typing  import List, Union

from    dent  import image

def parseargs(argv:Union[List[str],None]=None) -> Namespace:
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
    p.add_argument('-P', '--print-file', choices=image.PRINT_FILE_ARGS,
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

    conf = p.parse_args(argv)

    #   `default=` does not work with nargs=REMAINDER. We cannot use
    #   nargs='*' because that will cause options in the remainder to be
    #   interpreted as dent options unless the user adds `--` between,
    #   which is inconvenient.
    if not conf.COMMAND: conf.COMMAND = ['bash', '-l']

    #   We handle these simple options that don't actually run any real
    #   code here mainly because version needs access to the
    #   ArgumentParser, and we'd prefer to keep that local.
    if conf.version:
        print(f'{p.prog} version {version(p.prog)}')
        exit(0)
    elif conf.list_base_images:
        for i in image.BASE_IMAGES.keys(): print(i)
        exit(0)

    return conf
