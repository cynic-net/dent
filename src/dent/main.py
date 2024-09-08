''' dent - "Enter" a Docker container, with optional container/image creation

    For detailed documenation, see the README file. If you do not have
    the full repo, you can find it at <https://github.com/cynic-net/dent/>.
'''

from    argparse  import (
        ArgumentParser, REMAINDER, RawDescriptionHelpFormatter, Namespace)
from    importlib.metadata  import version
from    importlib.resources  import files as resfiles
from    os.path import basename, join as pjoin
from    pathlib import Path
from    platform import node
from    sys import argv, stdin, stdout, stderr
from    tempfile import mkdtemp
from    textwrap import dedent
import  json, os, shutil, stat, string, time

#   We were using some older typing stuff to maintain 3.8 compatibility.
#   This is no longer reqired now that we're at 3.9, and should be removed.
from    typing  import List

from    dent.config  import Config, BASE_IMAGES
import  dent.tmpl

#   We use the older high-level API so we work on Python <3.5.
from    subprocess import call, check_output, DEVNULL, CalledProcessError

####################################################################
#   Utility functions

def drcall(config:Config, command, **kwargs) -> int:
    ''' Execute the `command` with `**kwargs` just as `subprocess.call()`
        would unless we're doing a dry run, in which case just print
        `command` to `stderr` and return success.

        This uses stderr rather than stdout becuase user messages are
        already going to `stdout` and so this allows more easily separating
        the commands. (When all is well, nothing other than the commands
        should appear on stderr.)
    '''
    if not config.args.dry_run:
        return call(command, **kwargs)
    else:
        #   Ensure we're not coming out before stuff that's been buffered
        #   but not yet printed (many systems buffer stdout but not stderr).
        stdout.flush()
        print(' '.join(command), file=stderr)
        stderr.flush()
        return 0

####################################################################
#   Docker "API"

def docker_inspect(config:Config, thing, *container_names):
    ''' Run ``docker `thing` inspect`` on the arguments.

        This parses the returned JSON and returns it as a Python list
        of dictionaries containing the information about each
        container it finds.

        ``inspect`` will always produce at least an empty JSON array
        to stdout, regardless of error status, and since we've already
        confirmed we can run ``docker`` and talk to the daemon any
        other errors are highly unlikely. Therefore we simply ignore
        any return code (letting the error of the list being empty
        appear later) and let stderr pass through to the user to help
        debug any problems.

        This is not affected by ``--dry-run`` because this only queries
        existing configuration and state, and in many cases result of those
        queries determines what state-changing Docker commands will or
        would be executed.
    '''
    try:
        command = config.docker_command + (thing, 'inspect') + container_names
        #   Unfortunately, this produces `Error: No such ...` on stderr
        #   when the image or container doesn't exist. We suppress stdout
        #   to avoid this printing to the terminal, though this may make
        #   debugging errors in this program more difficult.
        output = check_output(command, stderr=DEVNULL)
    except CalledProcessError as failed:
        output = failed.output     # Still need to get stdout
    return json.loads(output.decode('UTF-8'))

def docker_container_start(config:Config, *container_names) -> None:
    ''' Run `docker container start` on the arguments.
    '''
    config.qprint(f"Starting container '{config.args.CONTANER_NAME}'")
    command = config.docker_command + ('container', 'start') + container_names
    #   Suppress stdout because `docker` prints the names
    #   of the containers it started.
    retcode = drcall(config, command, stdout=DEVNULL)
    if retcode != 0:
        config.die("Couldn't start container")

####################################################################
#   Image configuration scripts and related files

class PTemplate(string.Template):
    delimiter = '%'

def template(name:str) -> str:
    file = resfiles(dent.tmpl) / name
    with file.open("rt") as fd:     # type: ignore [call-overload]
        return fd.read()            # ↑ unclear what the type problem is

def dockerfile(config:Config) -> str:
    ' Return the text of `tmpl/Dockerfile` with template substitution done. '
    #   The pre-setup command is run before /tmp/setup-*
    #   This defaults to 'true' (a no-op), but can be set in the BASE_IMAGES
    #   config dict to e.g. install Bash so we can run the setup scripts.
    presetup_command = config.image_conf('presetup') or 'true'
    dfargs = {
        'base_image':       config.args.base_image,
        'presetup_command': presetup_command,
        'uname':            config.pwent.pw_name,
    }
    return PTemplate(template('Dockerfile')).substitute(dfargs)

def setup_pkg(config:Config) -> str:
    ''' Return the text of `tmpl/setup_package.bash` with standard
        Bash script header added and template substitution done.
    '''
    #   We avoid putting any user-related template arguments here so that
    #   this won't change based on user, thus letting us avoid regenerating
    #   this (fairly heavy) layer when user info changes.
    return PTemplate(
            template('setup_head.bash') + template('setup_packages.bash')) \
        .substitute({})

def setup_user(config:Config) -> str:
    ''' Return the text of `tmpl/setup_user.bash` with standard
        Bash script header added and template substitution done.
    '''
    useradd = config.image_conf('useradd') or 'generic'
    template_args = {
        'sudo':             '%sudo',    # Avoid having to escape
        'wheel':            '%wheel',   #    /etc/sudoers groups
        'uid':              config.pwent.pw_uid,
        'uname':            config.pwent.pw_name,
        'ugecos':           config.pwent.pw_gecos,
        'useradd':          useradd,
    }
    return PTemplate(
            template('setup_head.bash') + template('setup_user.bash')
        ).substitute(template_args)

####################################################################
#   Image and container creation

def build_image(config:Config) -> None:
    perm_r   = stat.S_IRUSR
    perm_rx  = perm_r  | stat.S_IXUSR
    perm_rwx = perm_rx | stat.S_IWUSR
    if not config.args.tmpdir:
        config.args.tmpdir = tmpdir = \
            mkdtemp(prefix=config.progname() + '-build-')
    else:
        tmpdir = config.args.tmpdir
        os.mkdir(tmpdir, perm_rwx)  # We want to die if it already exists
    config.qprint('Setting up context for image build in {}'.format(tmpdir),
        force_print=config.args.keep_tmpdir)

    with open(pjoin(tmpdir, 'Dockerfile'), 'w', encoding='UTF-8') as f:
        os.fchmod(f.fileno(), perm_r)
        print(dockerfile(config), file=f)

    with open(pjoin(tmpdir, 'setup-pkg'), 'w', encoding='UTF-8') as f:
        os.fchmod(f.fileno(), perm_rx)
        print(setup_pkg(config), file=f)

    with open(pjoin(tmpdir, 'setup-user'), 'w', encoding='UTF-8') as f:
        os.fchmod(f.fileno(), perm_rx)
        print(setup_user(config), file=f)

    if config.args.force_rebuild:
        config.qprint("Removing image '{}' and forcing full rebuild" \
            .format(config.image_alias()))
        drcall(config,
            config.docker_command + ('rmi', '-f', config.image_alias()))

    config.qprint("Building image '{}'".format(config.image_alias()))
    command = config.docker_command + ('build',)
    if config.args.progress:
        command += ('--progress=plain',)
    if config.args.quiet:
        command += ('--quiet',)
    if config.args.force_rebuild:
        command += ('--no-cache',)
    command += ('--tag', config.image_alias(), tmpdir)
    retcode = drcall(config, command)
    if retcode != 0:
        config.die("Error building image '{}' from '{}'"
            .format(config.image_alias(), config.args.base_image))

    if not config.args.keep_tmpdir:
        shutil.rmtree(tmpdir)

def share_args(args, opt) -> List[str]:
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

def create_container(config:Config) -> None:
    ''' Create a new container for persistent use.

        This is designed simply to exist, and may be stopped and restarted
        multiple times. After it's been created, we can't change the
        initial command run when a container is started so we always create
        it with an initial command of a long sleep (about 68 years, to
        avoid overflowing any old 32-bit systems) and run our actual
        commands or shells with ``docker exec`` in that existing container.
    '''
    shared_path_opts \
        = share_args(config.args.share_ro, 'ro') + share_args(config.args.share_rw, 'rw')

    images = docker_inspect(config, 'image', config.image_alias())
    if config.args.force_rebuild:
        build_image(config)
    elif images or config.args.image:
        #   If we found an image, use it. If we were explicitly requested
        #   to use a particular image, make sure we do not try to build it
        #   locally but let `docker run` try to download it.
        config.qprint("Using existing image '{}'".format(config.image_alias()))
    else:
        build_image(config)
    user = config.pwent.pw_name
    config.qprint("Creating new container '{}' from image '{}' for user {}" \
        .format(config.args.CONTANER_NAME, config.image_alias(), user))
    command = config.docker_command + ('run',
        '--name='+config.args.CONTANER_NAME, '--hostname='+config.args.CONTANER_NAME,
        '--env=HOST_HOSTNAME='+node(),
        '--env=LOGNAME='+user, '--env=USER='+user,
        '--rm=false', '--detach=true', '--tty=false',
        *shared_path_opts, *config.args.run_opt,
        config.image_alias(), '/bin/sleep', str(2**31-1) )
    retcode = drcall(config, command, stdout=DEVNULL)   # stdout prints container ID
    if retcode != 0:
        config.die('Failed to create container {} with command:\n{}' \
            .format(config.args.CONTANER_NAME, ' '.join(command)))

def waitforstart(config:Config, container_name) -> None:
    ''' Wait for a container to start, dieing if it exits immediately.

        The `Docker API`_ does not indicate whether it guarantees it won't
        return from a start call before the container is started. Regardless,
        we still need to check that it hasn't exited immediately.

        .. Docker API: https://docs.docker.com/engine/api/v1.30/#operation/ContainerStart
    '''
    if config.args.dry_run: return
    tries = 50
    while tries > 0:
        containers = docker_inspect(config, 'container', config.args.CONTANER_NAME)
        if not containers:
            config.die("Container '{}' was started but is no longer running" \
                .format(config.args.CONTANER_NAME))
        if containers[0]['State']['Running']:
            break
        else:
            time.sleep(0.1)
            tries -= 1
    if not tries > 0:
        config.die(f"Cannot start container '{config.args.CONTANER_NAME}'")

def enter_container(config:Config) -> None:
    ' Enter the container, doing any dependent actions necessary. '
    config.docker_setup()

    #   Any arguments that modify the `docker run` command are not
    #   compatible with existing containers where `docker run` has
    #   already been executed.
    not_on_existing = (config.args.base_image is not None)                     \
        or (len(config.args.run_opt) > 0)                                      \
        or (len(config.args.share_ro) > 0)                                     \
        or (len(config.args.share_rw) > 0)
    not_on_existing_msg =                                               \
         '-B, -r and -s options cannot affect existing containers'

    containers = docker_inspect(config, 'container', config.args.CONTANER_NAME)
    if not containers:
        create_container(config)      # Also starts
    elif not_on_existing:
        config.die(not_on_existing_msg)
    elif not containers[0]['State']['Running']:
        docker_container_start(config, config.args.CONTANER_NAME)

    waitforstart(config, config.args.CONTANER_NAME)

    #   Rather than using `container.exec_run() and then rewriting the same
    #   code to deal with the copying of stdin/out/err between what the
    #   Docker daemon is sending/receiving and our stdin/out/err, just use
    #   the existing code in the `docker` command to do this. We can also
    #   do a "process tail call optimization" here since all we would do is
    #   return the exit code anyway.
    command = list(config.docker_command) + ['exec']
    command.append('-i')
    command.append('--detach-keys=ctrl-@,ctrl-d')
    if stdin.isatty():
        command.append('-t')
    command.append(config.args.CONTANER_NAME)
    command += config.exec_command()
    stdout.flush(); stderr.flush()  # Ensure all our output is complete
                                    # before this process is replaced.
    if not config.args.dry_run:
        os.execvp(command[0], command)
        #   Never returns
    else:
        print(' '.join(command), file=stderr)
        exit(0)

####################################################################
#   Main

def main():
    p = ArgumentParser(formatter_class=RawDescriptionHelpFormatter,
        description=dedent('''
            Start a new process in a Docker container, creating the container
            and image if necessary. For detailed documentation, see:
                https://github.com/cynic-net/dent
        '''))

    #   Things we can print with -P and their functions producing the text.
    PRINT_FILE_ARGS =  {
        'dockerfile':   dockerfile,
        'setup-pkg':    setup_pkg,
        'setup-user':   setup_user,
    }

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
            " times. Use '-r -e=FOO=bar' syntax!")
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
    pe.add_argument('CONTANER_NAME', nargs='?',
        help='container name or ID (required)')
    pe.add_argument('-L', '--list-base-images', action='store_true',
        help='list base images this script knows how to configure')
    pe.add_argument('--version', action='store_true',
        help='show program version information')

    #   All remaining args are the command to run in the container.
    p.add_argument('COMMAND', nargs=REMAINDER, default='SEE BELOW',
        help='command to run in container (default: bash -l)')

    config = Config(p.parse_args())

    if config.args.list_base_images:
        for i in BASE_IMAGES.keys(): print(i)
    elif config.args.version:
        print(f'{p.prog} version {version(p.prog)}')

    elif config.args.print_file and config.args.CONTANER_NAME:
        print(PRINT_FILE_ARGS[config.args.print_file](config))
    elif config.args.CONTANER_NAME:
        return enter_container(config)
    else:
        config.die('Internal argument parsing error.')  # Should never happen.
