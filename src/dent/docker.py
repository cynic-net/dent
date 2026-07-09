''' dent.docker - Docker "API": execution of `docker` commands '''

from    argparse  import Namespace
#   We use the older high-level API so we work on Python <3.5.
from    subprocess  import call, check_output, DEVNULL, CalledProcessError
from    sys import stdout, stderr
#   We use some older typing stuff to maintain 3.8 compatibility.
from    typing  import Any, Dict, Optional, Tuple
import  json

from    dent.util  import die, qprint

DOCKER_COMMAND:Tuple[str,...] = ('docker',)
def docker_setup():
    ''' Determine whether we use ``docker`` or ``sudo docker``.

        This does not honour ``--dry-run`` because 'query-state' docker
        commands are always run; only 'change-state' docker commands are
        echoed instead of run in dry-run mode.
    '''
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

def docker_container_start(conf:Namespace):
    ''' Run `docker container start` on the arguments.
    '''
    qprint(conf, "Starting container '{}'".format(conf.CONTAINER_NAME))
    command = DOCKER_COMMAND + ('container', 'start', conf.CONTAINER_NAME)
    #   Suppress stdout because `docker` prints the names
    #   of the containers it started.
    retcode = drcall(conf, command, stdout=DEVNULL)
    if retcode != 0:
        die("Couldn't start container")
    return None

def drcall(conf, command, **kwargs):
    ''' Execute the `command` with `**kwargs` just as `subprocess.call()`
        would unless we're doing a ``--dry-run``, in which case just print
        `command` to `stderr` and return success. (Thus this should not be
        used for gathering information, only for changing state.)

        This uses stderr rather than stdout becuase user messages are
        already going to `stdout` and so this allows more easily separating
        the commands. (When all is well, nothing other than the commands
        should appear on stderr.)
    '''
    if not conf.dry_run:
        return call(command, **kwargs)
    else:
        #   Ensure we're not coming out before stuff that's been buffered
        #   but not yet printed (many systems buffer stdout but not stderr).
        stdout.flush()
        print(' '.join(command), file=stderr)
        stderr.flush()
        return 0
