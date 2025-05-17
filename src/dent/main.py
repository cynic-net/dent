''' dent - "Enter" a Docker container, with optional container/image creation

    For detailed documenation, see the README file. If you do not have
    the full repo, you can find it at <https://github.com/cynic-net/dent/>.
'''

from    argparse  import (
        ArgumentParser, REMAINDER, RawDescriptionHelpFormatter, Namespace)
from    collections import OrderedDict
from    importlib.metadata  import version
from    os.path import basename, join as pjoin
from    pathlib import Path
from    platform import node
from    pwd import getpwuid
#   We use the older high-level API so we work on Python <3.5.
from    subprocess  import call, check_output, DEVNULL, PIPE, CalledProcessError
from    sys import argv, stdin, stdout, stderr
from    tempfile import mkdtemp
from    textwrap import dedent
import  json, os, shutil, stat, string, time

from    importlib_resources  import files as resfiles

#   We use some older typing stuff to maintain 3.8 compatibility.
from    typing  import Any, Dict, List, Optional, Tuple, Union

PROGNAME    = os.path.basename(argv[0])
PWENT       = getpwuid(os.getuid())
IMAGE_CONF  : Dict[str,str]

####################################################################
#   Image configuration scripts and related files

#   These are the images we know we can build, because we've tested them.
#   Commented out entries we either used to be able to build but no longer
#   can (usually because they are old and the package servers are no longer
#   available) or have a comment explaining that we need to fix something.
BASE_IMAGES = OrderedDict((
    #   XXX Since we run the setup script that installs packages with bash,
    #   we use presetup on alpine:* to add bash _before_ we try to run the
    #   setup script. But this is annoying because we need to specify it
    #   by hand; probably we should fix this to allow matching alpine:*,
    #   while having our tested images list include :3.19 etc. (We don't
    #   want it including alpine:* or even alpine:latest below, because
    #   that's not tested any more once they release a new version.
    ('alpine:3.19',     { 'presetup': 'apk add bash', 'useradd': 'alpine' }),
    ('alpine:3.20',     { 'presetup': 'apk add bash', 'useradd': 'alpine' }),
    ('alpine:latest',   { 'presetup': 'apk add bash', 'useradd': 'alpine' }),
#   ('debian:8',        {}),
#   ('debian:9',        {}),
    ('debian:10',       {}),
    ('debian:11',       {}),
    ('debian:12',       {}),
#   ('ubuntu:14.04',    {}),
    ('ubuntu:16.04',    {}),
    ('ubuntu:18.04',    {}),
    ('ubuntu:20.04',    {}),
    ('ubuntu:22.04',    {}),
#   ('centos:6',        {}),    # But not with kernel ≥ 4.19 (works on 4.4).
#   ('centos:7',        {}),    # Package repos are gone.
#   ('centos:8',        {}),    # Package repos are gone.
    ('rockylinux:8',    {}),
#   ('rockylinux:9',    {}),    # FIXME: --allowerasing would do the trick,
                                # but that's not in CentOS 7.
    ('fedora:30',       {}),
    ('fedora:38',       {}),
))

def resource_text(name):
    return resfiles().joinpath(name).read_text()

DOCKERFILE      = resource_text('Dockerfile')
SETUP_HEADER    = resource_text('setup-header')
SETUP_PKG       = SETUP_HEADER + resource_text('setup-pkg')
SETUP_USER      = SETUP_HEADER + resource_text('setup-user')

class PTemplate(string.Template):
    delimiter = '%'

def dockerfile(config:Namespace):
    ' Return the text of `DOCKERFILE` with template substitution done. '

    #   The pre-setup command is run before /tmp/setup-*
    #   This defaults to 'true' (a no-op), but can be set in the BASE_IMAGES
    #   config dict to e.g. install Bash so we can run the setup scripts.
    presetup_command = IMAGE_CONF.get('presetup') or 'true'
    dfargs = {
        'base_image':       config.base_image,
        'presetup_command': presetup_command,
        'uname':            PWENT.pw_name,
    }
    return PTemplate(DOCKERFILE).substitute(dfargs)

def setup_pkg(config):
    ' Return the text of `SETUP_PKG` with template substitution done. '
    useradd = IMAGE_CONF.get('useradd') or 'generic'
    #   We avoid putting any user-related template arguments here so that
    #   this won't change based on user, thus letting us avoid regenerating
    #   this (fairly heavy) layer when user info changes.
    return PTemplate(SETUP_PKG).substitute({})

def setup_user(config:Namespace):
    ' Return the text of `SETUP_USER` with template substitution done. '
    useradd = IMAGE_CONF.get('useradd') or 'generic'
    template_args = {
        'sudo':             '%sudo',    # Avoid having to escape
        'wheel':            '%wheel',   #    /etc/sudoers groups
        'uid':              PWENT.pw_uid,
        'uname':            PWENT.pw_name,
        'ugecos':           PWENT.pw_gecos,
        'useradd':          useradd,
    }
    return PTemplate(SETUP_USER).substitute(template_args)

####################################################################
#   Main and argument handling.

def main():
    config = parseargs()

    #   If we know the given base image name, get any special configuration
    #   for it. Otherwise we use a generic config.
    global IMAGE_CONF; IMAGE_CONF = BASE_IMAGES.get(config.base_image) or {}

    if config.print_file and config.CONTAINER_NAME:
        print(PRINT_FILE_ARGS[config.print_file](config))
    elif config.CONTAINER_NAME:
        return enter_container(config)
    else:
        die('Internal argument parsing error.')     # Should never happen.

#   Things we can print with -P and their functions producing the text.
PRINT_FILE_ARGS =  {
    'dockerfile':   dockerfile,
    'setup-pkg':    setup_pkg,
    'setup-user':   setup_user,
}

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
    p.add_argument('-P', '--print-file', choices=PRINT_FILE_ARGS,
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

    config = p.parse_args(argv)

    #   `default=` does not work with nargs=REMAINDER. We cannot use
    #   nargs='*' because that will cause options in the remainder to be
    #   interpreted as dent options unless the user adds `--` between,
    #   which is inconvenient.
    if not config.COMMAND: config.COMMAND = ['bash', '-l']

    #   We handle these simple options that don't actually run any real
    #   code here mainly because version needs access to the
    #   ArgumentParser, and we'd prefer to keep that local.
    if config.version:
        print(f'{p.prog} version {version(p.prog)}')
        exit(0)
    elif config.list_base_images:
        for i in BASE_IMAGES.keys(): print(i)
        exit(0)

    return config

####################################################################
#   Container entry.

def enter_container(config:Namespace):
    ' Enter the container, doing any dependent actions necessary. '
    docker_setup()

    #   Any arguments that modify the `docker run` command are not
    #   compatible with existing containers where `docker run` has
    #   already been executed.
    not_on_existing = (config.base_image is not None)                   \
        or (len(config.run_opt) > 0)                                    \
        or (len(config.share_ro) > 0)                                   \
        or (len(config.share_rw) > 0)
    not_on_existing_msg =                                               \
         '-B, -r and -s options cannot affect existing containers'

    container = docker_inspect('container', config.CONTAINER_NAME)
    if container is None:
        create_container(config)      # Also starts
    elif not_on_existing:
        die(not_on_existing_msg)
    elif not container['State']['Running']:
        docker_container_start(config)

    waitforstart(config)

    #   Rather than using `container.exec_run() and then rewriting the same
    #   code to deal with the copying of stdin/out/err between what the
    #   Docker daemon is sending/receiving and our stdin/out/err, just use
    #   the existing code in the `docker` command to do this. We can also
    #   do a "process tail call optimization" here since all we would do is
    #   return the exit code anyway.
    command = list(DOCKER_COMMAND) + ['exec']
    command.append('-i')
    command.append('--detach-keys=ctrl-@,ctrl-d')
    if stdin.isatty():
        command.append('-t')
    command.append(config.CONTAINER_NAME)
    command += config.COMMAND
    stdout.flush(); stderr.flush()  # Ensure all our output is complete
                                    # before this process is replaced.
    if not config.dry_run:
        os.execvp(command[0], command)
        #   Never returns
    else:
        print(' '.join(command), file=stderr)
        exit(0)

def waitforstart(config:Namespace):
    ''' Wait for a container to start, dieing if it exits immediately.

        The `Docker API`_ does not indicate whether it guarantees it won't
        return from a start call before the container is started. Regardless,
        we still need to check that it hasn't exited immediately.

        .. Docker API: https://docs.docker.com/engine/api/v1.30/#operation/ContainerStart
    '''
    if config.dry_run: return
    tries = 50
    while tries > 0:
        container = docker_inspect('container', config.CONTAINER_NAME)
        if container is None:
            die("Container '{}' was started but is no longer running" \
                .format(config.CONTAINER_NAME))
        elif container['State']['Running']:
            break
        else:
            time.sleep(0.1)
            tries -= 1
    if not tries > 0:
        die("Cannot start container '{}'".format(config.CONTAINER_NAME))

####################################################################
#   Container setup.

def create_container(config:Namespace):
    ''' Create a new container for persistent use.

        This is designed simply to exist, and may be stopped and restarted
        multiple times. After it's been created, we can't change the
        initial command run when a container is started so we always create
        it with an initial command of a long sleep (about 68 years, to
        avoid overflowing any old 32-bit systems) and run our actual
        commands or shells with ``docker exec`` in that existing container.
    '''
    shared_path_opts \
        = share_args(config.share_ro, 'ro') + share_args(config.share_rw, 'rw')

    images = docker_inspect('image', image_alias(config))
    if config.force_rebuild:
        build_image(config)
    elif images or config.image:
        #   If we found an image, use it. If we were explicitly requested
        #   to use a particular image, make sure we do not try to build it
        #   locally but let `docker run` try to download it.
        qprint(config, "Using existing image '{}'".format(image_alias(config)))
    else:
        build_image(config)
    user = PWENT.pw_name
    qprint(config, "Creating new container '{}' from image '{}' for user {}" \
        .format(config.CONTAINER_NAME, image_alias(config), user))
    command = DOCKER_COMMAND + ('run',
        '--name='+config.CONTAINER_NAME, '--hostname='+config.CONTAINER_NAME,
        '--env=HOST_HOSTNAME='+node(),
        '--env=LOGNAME='+user, '--env=USER='+user,
        '--rm=false', '--detach=true', '--tty=false',
        *shared_path_opts, *config.run_opt,
        image_alias(config), '/bin/sleep', str(2**31-1) )
    retcode = drcall(config, command, stdout=DEVNULL)   # stdout prints container ID
    if retcode != 0:
        die('Failed to create container {} with command:\n{}' \
            .format(config.CONTAINER_NAME, ' '.join(command)))

def share_args(args, opt):
    ''' Given an iterable of paths, return a list of ``-v`` options for
        ``docker run`` that will mount them at the same path in the
        container. Relative paths are taken as relative to ``$HOME`` and
        converted to absolute paths.
    '''
    vs = []
    for s in args:
        p = Path.home().joinpath(s)     # if relative, make absolute
        vs += ['-v={}:{}:{}'.format(p, p, opt)]
    return vs

def image_alias(config:Namespace):
    ' "Alias" is name plus tag '
    if config.image:
        return config.image
    else:
        if not config.base_image:
            #   It would be nice to display the name of the image we would
            #   build here, but we can't because it wasn't specified and
            #   we can't generate it from the base image name.
            die('No such container; supply -B base-image to build.')
        if not config.tag:
            config.tag = PWENT.pw_name
        return '{}/{}:{}'.format(
            PROGNAME, config.base_image.replace(':', '.'), config.tag)

####################################################################
#   Container image build

def build_image(config:Namespace):
    perm_r   = stat.S_IRUSR
    perm_rx  = perm_r  | stat.S_IXUSR
    perm_rwx = perm_rx | stat.S_IWUSR
    if not config.tmpdir:
        config.tmpdir = tmpdir = mkdtemp(prefix=PROGNAME+'-build-')
    else:
        tmpdir = config.tmpdir
        os.mkdir(tmpdir, perm_rwx)  # We want to die if it already exists
    qprint(config, 'Setting up context for image build in {}'.format(tmpdir),
        force_print=config.keep_tmpdir)

    with open(pjoin(tmpdir, 'Dockerfile'), 'w', encoding='UTF-8') as f:
        os.fchmod(f.fileno(), perm_r)
        print(dockerfile(config), file=f)

    with open(pjoin(tmpdir, 'setup-pkg'), 'w', encoding='UTF-8') as f:
        os.fchmod(f.fileno(), perm_rx)
        print(setup_pkg(config), file=f)

    with open(pjoin(tmpdir, 'setup-user'), 'w', encoding='UTF-8') as f:
        os.fchmod(f.fileno(), perm_rx)
        print(setup_user(config), file=f)

    if config.force_rebuild:
        qprint(config, "Removing image '{}' and forcing full rebuild" \
            .format(image_alias(config)))
        drcall(config, DOCKER_COMMAND + ('rmi', '-f', image_alias(config)))

    qprint(config, "Building image '{}'".format(image_alias(config)))
    command = DOCKER_COMMAND + ('build',)
    if config.progress:
        command += ('--progress=plain',)
    if config.quiet:
        command += ('--quiet',)
    if config.force_rebuild:
        command += ('--no-cache',)
    command += ('--tag', image_alias(config), tmpdir)
    retcode = drcall(config, command)
    if retcode != 0:
        die("Error building image '{}' from '{}'"
            .format(image_alias(config), config.base_image))

    if not config.keep_tmpdir:
        shutil.rmtree(tmpdir)

####################################################################
#   Docker "API"

DOCKER_COMMAND:Tuple[str,...] = ('docker',)
def docker_setup():
    ' Determine whether we use ``docker`` or ``sudo docker``. '
    global DOCKER_COMMAND

    retcode = call(DOCKER_COMMAND + ('info',), stdout=DEVNULL, stderr=DEVNULL)
    if retcode == 0:
        return

    #   Before we do any further work, ensure user can sudo and has
    #   cached credentials.
    retcode = call(('sudo', '-v'))
    if retcode != 0:
        die('Cannot run `docker` as this user and cannot sudo.')
    DOCKER_COMMAND = ('sudo',) + DOCKER_COMMAND

def docker_inspect(object:str, name:str) -> Optional[Dict[Any, Any]]:
    ''' Run ``docker `object` inspect `name```, where `object` is usually
        ``image`` or ``container``.

        This parses the returned JSON into a Python dictionary, or
        `None` if `object` doesn't exist.

        ``docker inspect`` will always produce at least an empty JSON array
        to stdout, regardless of error status, and since we've already
        confirmed we can run ``docker`` and talk to the daemon any other
        errors are highly unlikely. Therefore we simply ignore any return
        code (letting the error of the list being empty appear later) and
        let stderr pass through to the user to help debug any problems.

        This is not affected by ``--dry-run`` because this only queries
        existing configuration and state, and in many cases result of those
        queries determines what state-changing Docker commands will or
        would be executed.
    '''
    try:
        command = DOCKER_COMMAND + (object, 'inspect', name)
        #   Unfortunately, this produces `Error: No such ...` on stderr
        #   when the image or container doesn't exist. We suppress stdout
        #   to avoid this printing to the terminal, though this may make
        #   debugging errors in this program more difficult.
        output = check_output(command, stderr=DEVNULL)
    except CalledProcessError as failed:
        output = failed.output     # Still need to get stdout
    l = json.loads(output.decode('UTF-8'))
    if len(l) == 0: return None
    else:           return l[0]

def docker_container_start(config:Namespace):
    ''' Run `docker container start` on the arguments.
    '''
    qprint(config, "Starting container '{}'".format(config.CONTAINER_NAME))
    command = DOCKER_COMMAND + ('container', 'start', config.CONTAINER_NAME)
    #   Suppress stdout because `docker` prints the names
    #   of the containers it started.
    retcode = drcall(config, command, stdout=DEVNULL)
    if retcode != 0:
        die("Couldn't start container")
    return None

####################################################################
#   Utility functions

def qprint(config:Namespace, *args, force_print=False, **kwargs):
    ''' Call `print()` on arguments unless quiet flag is set.

        `force_print` will print even if args.quiet is set; this allows the
        caller to test on a second condition without having to use ``if``
        and a duplicate call to `print()`.
    '''
    if force_print or not config.quiet:
        print('-----', *args, **kwargs)

def die(msg):
    print(PROGNAME + ':', msg, file=stderr)
    exit(1)

def drcall(config, command, **kwargs):
    ''' Execute the `command` with `**kwargs` just as `subprocess.call()`
        would unless we're doing a dry run, in which case just print
        `command` to `stderr` and return success.

        This uses stderr rather than stdout becuase user messages are
        already going to `stdout` and so this allows more easily separating
        the commands. (When all is well, nothing other than the commands
        should appear on stderr.)
    '''
    if not config.dry_run:
        return call(command, **kwargs)
    else:
        #   Ensure we're not coming out before stuff that's been buffered
        #   but not yet printed (many systems buffer stdout but not stderr).
        stdout.flush()
        print(' '.join(command), file=stderr)
        stderr.flush()
        return 0
