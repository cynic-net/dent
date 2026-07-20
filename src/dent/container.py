''' dent.container - container creation, startup and entry '''

from    pathlib import Path
from    platform import node
from    subprocess  import DEVNULL
from    sys import stdin, stdout, stderr
import  os, time

from    dent  import docker, image
from    dent.configure  import Config
from    dent.util  import PWENT, die, qprint

####################################################################
#   Container entry.

def enter_container(conf:Config):
    ' Enter the container, doing any dependent actions necessary. '
    docker.docker_setup()

    #   Any arguments that modify the `docker run` command are not
    #   compatible with existing containers where `docker run` has
    #   already been executed.
    #
    #   XXX This wants to move into configure.py. And also once we have
    #   configuration files, we need to allow config specification of
    #   e.g. base_image even for existing containers, and know that we
    #   don't need to rebuild if base_image is the same now as when it
    #   was when it was built. (Otherwise query user about rebuild?)
    #
    not_on_existing = (
           (conf.base_image is not None)
        or (len(conf.run_opt) > 0)
        or (len(conf.share_ro) > 0)
        or (len(conf.share_rw) > 0)
        )
    not_on_existing_msg \
        = '-B, -r and -s options cannot affect existing containers'

    container = docker.docker_inspect('container', conf.CONTAINER_NAME)
    if container is None:
        create_container(conf)      # Also starts
    elif not_on_existing:
        die(not_on_existing_msg)
    elif not container['State']['Running']:
        docker.docker_container_start(conf)

    waitforstart(conf)

    #   Rather than using `container.exec_run() and then rewriting the same
    #   code to deal with the copying of stdin/out/err between what the
    #   Docker daemon is sending/receiving and our stdin/out/err, just use
    #   the existing code in the `docker` command to do this. We can also
    #   do a "process tail call optimization" here since all we would do is
    #   return the exit code anyway.
    command = list(docker.DOCKER_COMMAND) + ['exec']
    command.append('-i')
    command.append('--detach-keys=ctrl-@,ctrl-d')
    if stdin.isatty():
        command.append('-t')
    command.append(conf.CONTAINER_NAME)
    command += conf.COMMAND
    stdout.flush(); stderr.flush()  # Ensure all our output is complete
                                    # before this process is replaced.
    if not conf.dry_run:
        os.execvp(command[0], command)
        #   Never returns
    else:
        print(' '.join(command), file=stderr)
        exit(0)

def waitforstart(conf:Config):
    ''' Wait for a container to start, dieing if it exits immediately.

        The `Docker API`_ does not indicate whether it guarantees it won't
        return from a start call before the container is started. Regardless,
        we still need to check that it hasn't exited immediately.

        .. Docker API: https://docs.docker.com/engine/api/v1.30/#operation/ContainerStart
    '''
    if conf.dry_run: return
    tries = 50
    while tries > 0:
        container = docker.docker_inspect('container', conf.CONTAINER_NAME)
        if container is None:
            die("Container '{}' was started but is no longer running" \
                .format(conf.CONTAINER_NAME))
        elif container['State']['Running']:
            break
        else:
            time.sleep(0.1)
            tries -= 1
    if not tries > 0:
        die("Cannot start container '{}'".format(conf.CONTAINER_NAME))

####################################################################
#   Container setup.

def create_container(conf:Config):
    ''' Create a new container for persistent use.

        This is designed simply to exist, and may be stopped and restarted
        multiple times. After it's been created, we can't change the
        initial command run when a container is started so we always create
        it with an initial command of a long sleep (about 68 years, to
        avoid overflowing any old 32-bit systems) and run our actual
        commands or shells with ``docker exec`` in that existing container.
    '''
    shared_path_opts \
        = share_args(conf.share_ro, 'ro') + share_args(conf.share_rw, 'rw')

    images = docker.docker_inspect('image', image.image_alias(conf))
    if conf.force_rebuild:
        image.build_image(conf)
    elif images or conf.image:
        #   If we found an image, use it. If we were explicitly requested
        #   to use a particular image, make sure we do not try to build it
        #   locally but let `docker run` try to download it.
        qprint(conf.quiet,
            "Using existing image '{}'".format(image.image_alias(conf)))
    else:
        image.build_image(conf)
    user = PWENT.pw_name
    qprint(conf.quiet, "Creating new container '{}' from image '{}' for user {}" \
        .format(conf.CONTAINER_NAME, image.image_alias(conf), user))
    command = docker.DOCKER_COMMAND + ('run',
        '--name='+conf.CONTAINER_NAME, '--hostname='+conf.CONTAINER_NAME,
        '--env=HOST_HOSTNAME='+node(),
        '--env=LOGNAME='+user, '--env=USER='+user,
        '--rm=false', '--detach=true', '--tty=false',
        *shared_path_opts, *conf.run_opt,
        image.image_alias(conf), 'tail', '-f', '/dev/null' )
    retcode = docker.drcall(conf, command, stdout=DEVNULL)
                                            # stdout prints container ID
    if retcode != 0:
        die('Failed to create container {} with command:\n{}' \
            .format(conf.CONTAINER_NAME, ' '.join(command)))

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
