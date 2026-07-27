''' dent.container - container creation, startup and entry '''

from    datetime  import datetime
from    pathlib  import Path
from    platform  import node
from    subprocess  import DEVNULL
from    sys  import stdin, stdout, stderr, argv
from    textwrap  import dedent
import  os, shlex, time

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
        or (conf.image is not None)
        or (len(conf.run_opt) > 0)
        or (len(conf.share_ro) > 0)
        or (len(conf.share_rw) > 0)
        )
    not_on_existing_msg \
        = '-B, -i, -r and -s options cannot affect existing containers'

    container = docker.docker_inspect('container', conf.CONTAINER_NAME)
    if container is None:
        create_container(conf)      # Also starts, with the shared dir
        has_share = True
    else:   # container exists (but might not be started yet)
        if not_on_existing:
            die(not_on_existing_msg)
        if not container['State']['Running']:
            docker.docker_container_start(conf)
        #   Only containers created with the shared dir get the startup-file
        #   launcher; a foreign container (possibly without even bash) is
        #   entered directly. The Dent share is identified by the ``Source``
        #   path (i.e. path on the host); the in-container path is taken
        #   care of by the in-container ``dent-share dir`` program.
        has_share = has_bind(container, source=dent_share(conf))

    waitforstart(conf)

    #   WARNING: The command below must NOT copy $XDG_STATE_DIR or $HOME
    #   into the container. The container was set up with a specifc
    #   $XDG_STATE_HOME (or default $HOME/.local/state) and mounted the
    #   Dent share based on that: different values will silently disable
    #   the entry script as $HOME/.local/bin/dent-share will no longer
    #   be able to find it.

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
    #   Containers created with the Dent share are entered via a launcher
    #   that sources a per-entry startup file then execs the requested
    #   command; the `[ -f ]` guard tolerates a missing file. Others are
    #   entered directly.
    if has_share:
        #   Write even on dry run so we can inspect its contents.
        esfname = write_entry_script(conf)
        contfile = '$HOME/.local/bin/dent-share'
        #   We pass a single command to `sh -c` run in the container, which:
        #   1. Checks to see if the entry script is present. (It was created
        #      on the host, but container config determines if it's actually
        #      shared into the container.)
        #   2. If it's present, sources it with the `.` command.
        #   3. exec's "$@", which will be conf.COMMAND, either the remaining
        #      arguments given on the `dent` command line or Dent's default
        #      `bash -l`. (XXX this really should be the user's shell, not
        #      hardcoded to bash.)
        cont_sh_c = f'[ -f "{contfile}" ]' \
            f' && eval "$({contfile} cat-entry-script {esfname})"; exec "$@"'
        command += ['sh', '-c', cont_sh_c, 'argv0'] + conf.COMMAND
    else:
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
#   Per-container shared dir and entry startup files.

#   Entry startup files retained per container; older ones are reaped, but
#   never any younger than STARTUP_MIN_AGE seconds (so a slow host starting
#   many entries at once can't reap one still in use).
STARTUP_KEEP    = 12
STARTUP_MIN_AGE = 120

def dent_share(conf:Config) -> Path:
    ''' For images/containers created by Dent, we create a *Dent share*: a
        directory used to pass information back and forth (entry
        initialisation code, copy/paste stuff, sockets, and anything the user
        wants to share). It is bind-mounted at the same path in host and
        container (which relies on their ``$HOME`` matching, as `share_args`
        also assumes) and lives at ``dent/<container>`` under the standard XDG
        state dir (``${XDG_STATE_HOME:-$HOME/.local/state}``); we use that
        instead of ``$XDG_RUNTIME_DIR`` because containers often outlive the
        session owning the runtime dir.

        This must agree with the `dent-share` script, which computes the
        same path for the user inside and outside the container.
    '''
    state = os.environ.get('XDG_STATE_HOME') or Path.home()/'.local'/'state'
    return Path(state) / 'dent' / conf.CONTAINER_NAME

def has_bind(inspect:dict, *, source:Path) -> bool:
    ''' Given the parsed ``docker inspect`` output for a container, return
        `True` if the container binds `source` on the host side into the
        container. (We don't check where in the container it is mounted.)
    '''
    #   Note that the ``Mounts`` entry may be absent or null.
    return any( m.get('Source') == str(source) and m.get('Type') == 'bind'
                for m in (inspect.get('Mounts') or []) )

def write_entry_script(conf:Config) -> str:
    ''' At each entry write a startup script to be executed inside the
        container before the user's shell. This is intended to carry
        context read *at entry time* from the host into the container
        (CWD, env vars, etc.).

        Returns the path of the startup file. The path is expected
        to be sourced in the container by the entry launcher. Note
        that it will be sourced by a POSIX `sh`, not `bash`, as bash
        is not always available in every container.

        The file is typically retained for debugging; this function
        will reap old files that are no longer needed by calling
        `reap_startup_files()`.
    '''
    scriptdir = dent_share(conf) / 'entry-script'
    scriptdir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    fname = f'startup.{now.strftime("%Y%m%dT%H%M%S")}.{os.getpid()}'
    f = scriptdir / fname
    f.write_text(startup_file_text(conf, now))
    reap_startup_files(scriptdir, STARTUP_KEEP, STARTUP_MIN_AGE)
    return fname

def startup_file_text(conf:Config, now:datetime, environ=None) -> str:
    Q = shlex.quote
    cwd = os.getcwd()
    if environ is None:  environ = os.environ

    nows = now.isoformat(timespec='seconds')
    head = dedent(f'''
        #   Dent entry {nows}  container={conf.CONTAINER_NAME}  host-pid={os.getpid()}
        #   host cwd: {cwd}
        #   argv: {argv}
        command cd {Q(cwd)} 2>/dev/null || true
    ''')
    envs = '\n'.join([
        f'export {var}={Q(environ[var])}'
        for var in conf.env_copy
        if var in environ ])
    return '\n'.join([head, envs])

def reap_startup_files(scriptdir:Path, keep:int, min_age:float):
    ''' Delete startup files in `scriptdir` beyond the newest `keep`, but never
        any younger than `min_age` seconds.
    '''
    try:
        now = time.time()
        fs = sorted(scriptdir.glob('startup.*'), key=lambda p: p.stat().st_mtime)
        for p in fs[:-keep]:
            if now - p.stat().st_mtime >= min_age:
                p.unlink(missing_ok=True)
    except OSError:
        pass    # best-effort; never fail entry over reaping

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

    share = dent_share(conf)
    (share / 'entry-script').mkdir(parents=True, exist_ok=True)
    dent_share_opt = '-v={0}:{0}'.format(share)

    #   Pass the host's XDG_* vars through at creation (not on entry) so the
    #   container's XDG layout — in particular XDG_STATE_HOME, which locates
    #   the Dent share — matches the host's. `docker exec` inherits these.
    xdg_env = tuple('--env=' + k
        for k in sorted(os.environ) if k.startswith('XDG_'))

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
        '--env=DENT_CONTAINER='+conf.CONTAINER_NAME,
        '--env=LOGNAME='+user, '--env=USER='+user,
        '--rm=false', '--detach=true', '--tty=false',
        *xdg_env, *shared_path_opts, dent_share_opt, *conf.run_opt,
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
