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
from    sys import argv, stdin, stdout, stderr
from    tempfile import mkdtemp
from    textwrap import dedent
import  json, os, shutil, stat, string, time

#   We use some older typing stuff to maintain 3.8 compatibility.
from    typing  import Dict, Tuple


#   We use the older high-level API so we work on Python <3.5.
from    subprocess import call, check_output, DEVNULL, PIPE, CalledProcessError

PROGNAME    = os.path.basename(argv[0])
PWENT       = getpwuid(os.getuid())
ARGS        : Namespace
IMAGE_CONF  : Dict[str,str]

#   To maximize build speed via use of cache when rebuilding, we want
#   start with the layers that are largest and least likely to change
#   and work down towards the smaller/faster/more-likley-to-change
#   ones.
#
#   One thing to keep in mind is that the result produced by
#   `setup-pkg` is out of date as soon as the distro releases more
#   package updates, but `docker build` doesn't know this. So even
#   when building a new container instead of using an existing one you
#   should still update its packages.
#
DOCKERFILE = '''\
FROM %{base_image}

RUN %{presetup_command}
COPY setup-pkg /tmp/
RUN ["/bin/bash", "/tmp/setup-pkg"]
COPY setup-user /tmp/
RUN ["/bin/bash", "/tmp/setup-user"]

#   USER and WORKDIR are used by both `docker run` and `start`.
#   We don't care about CMD because we always specify a command
#   for `run` and it's ignored by `start`.
USER %{uname}
WORKDIR /home/%{uname}
'''

SETUP_HEADER = '''\
#!/usr/bin/env bash
set -e -o pipefail

die() {
    local exitcode="$1"; shift
    echo 1>&2 "$(basename "$0")" "$@"
    exit $exitcode
}
'''

SETUP_PKG = SETUP_HEADER + '''
UNIVERSAL_PKGS='sudo file curl wget git vim man-db'

packages() {
    echo '-- Package updates/installs'
    export LC_ALL=C
    if type apt 2>/dev/null; then
        packages_apt
        ( cd /etc \
            && sed -i -e '/en_US/s/^# //' -e '/ja_JP/s/^# //' /etc/locale.gen \
            && etckeeper commit -m 'Enable UTF-8 and other locales' \
            && locale-gen \
        )
    elif type yum 2>/dev/null; then
        packages_rpm
    elif type apk 2>/dev/null; then
        packages_apk
    else
        die 30 "Cannot find known package manager."
    fi
}

packages_apt() {
    export DEBIAN_FRONTEND=noninteractive
    #   If we fail to download some updates, e.g. due to no network
    #   connection or updates no longer being available for old systems,
    #   we'll live with that.
    apt-get update || true
    #   We must install git and set user.name/email before installing
    #   etckeeper or etckeeper will be unable to commit.
    apt-get -y install git
    git config --global user.name 'dent root user'
    git config --global user.email 'root@dent.nonexistent'
    #   Install etckeeper as early as posible so we have a record of
    #   the following installs.
    cat >> /etc/.gitignore << _____ # The Docker host owns these files
/hosts
/resolv.conf
_____
    apt-get -y install etckeeper
    #   ≤14.04 always configures bzr, even if git is installed instead
    sed -i -e '/^VCS=/s/.*/VCS="git"/' /etc/etckeeper/etckeeper.conf
    etckeeper init
    #   It's not worth the time to run dist-upgrade now so as to have
    #   the latest packages in the image because the image will be out
    #   of date in a week or two anyway and the user will still have
    #   to run dist-upgrade himself on new containers.
    #apt-get -y dist-upgrade
    #   Ubuntu images appear to turn off installation of manpages and
    #   other useful stuff.
    [ -f "/etc/dpkg/dpkg.cfg.d/excludes" ] && {
        cd /etc
        git rm -f /etc/dpkg/dpkg.cfg.d/excludes
        etckeeper commit -m 'Re-enable installs of manpages, etc.'
    }
    #   We install a minimal set of packages here because
    #   the user will use `distro` to install what he needs.
    apt-get -y install $UNIVERSAL_PKGS \
        locales manpages apt-file procps xz-utils
    apt-get clean
}

packages_rpm() {
    #   etckeeper not available in standard CentOS packages at least up to 7

    #   Ensure that man pages are installed with packages if that was disabled.
    sed -i -e '/tsflags=nodocs/s/^/#/' /etc/yum.conf /etc/dnf/dnf.conf || true
    yum -y update
    yum -y install $UNIVERSAL_PKGS man-pages
}

packages_apk() {
    #   XXX This should set up etckeeper.
    apk update
    apk add $UNIVERSAL_PKGS man-pages man-pages-posix
}

packages
'''

SETUP_USER = SETUP_HEADER + '''
users_generic() {
    echo '-- Ensure UID 1000 does not exist'
    #   Ubuntu images (and perhaps others) have a pre-created user with
    #   UID 1000; if the dent user is also using Ubuntu with a default
    #   install, she will be UID 1000 as well and dent will not be able
    #   to create that user in the container because it already exists.
    #   So make sure it doesn't.
    uname1000=$(id -un 1000) || true
    [[ -n $uname1000 ]] && userdel --force --remove "$uname1000"

    echo '-- User creation'
    #   Note we do not add the user to the `sudo` group as that will
    #   introduce a PASSWD: entry even though it's overridden by the
    #   NOPASSWD: below, and that PASSWD entry will make `sudo -v`
    #   require a password.
    local -a groups=() allgroups=(wheel sudo systemd-journal)
    for group in ${allgroups[@]}; do
        grep -q "^$group:" /etc/group && groups+=("$group")
    done
    groups=$(IFS=, ; echo "${groups[*]}")

    useradd --shell /bin/bash \
        --create-home --home-dir /home/%{uname}  \
        --user-group --groups "$groups" \
        --uid %{uid} -c '%{ugecos}' %{uname}

    #   Since we have no password, we must let the user sudo without one.
    mkdir -p /etc/sudoers.d/    # In case we skipped sudo install
    cat << _____ > /etc/sudoers.d/50-%{uname}
#   We change verifypw from its default of 'all' to 'any' for the user so
#   that if NOPASSWD: is lacking on any entries in /etc/sudoers (as it is
#   for, e.g., %sudo group on Debian) the user can still `sudo -v` without
#   a password.
Defaults:%{uname} verifypw = any

#   We add explicit sudo for the user of this container for those systems
#   where adding the user to the wheel or sudo group doesn't do that.
%{uname} ALL=(ALL:ALL) NOPASSWD:ALL
_____
    chmod 0750 /etc/sudoers.d/[0-9]*
}

users_alpine() {
    echo '-- User creation (alpine)'

    #   Alpine `adduser` has no option to set the group, but unlike this
    #   command on some other systems, it automatically puts the user in
    #   her own group with the same name and id.
    #addgroup --gid %{uid} %{uname}

    #   -D avoids assigning a password
    adduser -D --uid %{uid} -g '%{ugecos}' \
        --shell /bin/bash --home /home/%{uname}   %{uname}

    #   XXX Should `adduser %{uname} $group` for any groups?

    #   Since we have no password, we must let the user sudo without one.
    mkdir -p /etc/sudoers.d/    # In case we skipped sudo install
    echo '%{uname} ALL=(ALL:ALL) NOPASSWD:ALL' > /etc/sudoers.d/50-%{uname}
}

dot_home() {
    echo '-- dot-home install'
    local url_prefix=https://raw.githubusercontent.com/dot-home/dot-home
    local url_branch=main
    local url="$url_prefix/$url_branch/bootstrap-user"
    export LOGNAME=%{uname} HOME=~%{uname}
    export DH_BOOTSTRAP_USERS="$url_prefix/$url_branch/dh/bootstrap-users"

    rm -f $HOME/.profile $HOME/.bash_profile $HOME/.bashrc

    if curl -sfL "$url" | sudo -E -u $LOGNAME bash; then
        echo "dot-home installed for user $LOGNAME"
    else
        echo "WARNING: dot-home install failure"
        sleep 3
    fi
}

users_%{useradd}
dot_home
'''

####################################################################
#   Utility functions

def qprint(*args, force_print=False, **kwargs):
    ''' Call `print()` on arguments unless quiet flag is set.

        `force_print` will print even if ARGS.quiet is set; this allows the
        caller to test on a second condition without having to use ``if``
        and a duplicate call to `print()`.
    '''
    if force_print or not ARGS.quiet:
        print('-----', *args, **kwargs)

def die(msg):
    print(PROGNAME + ':', msg, file=stderr)
    exit(1)

def drcall(command, **kwargs):
    ''' Execute the `command` with `**kwargs` just as `subprocess.call()`
        would unless we're doing a dry run, in which case just print
        `command` to `stderr` and return success.

        This uses stderr rather than stdout becuase user messages are
        already going to `stdout` and so this allows more easily separating
        the commands. (When all is well, nothing other than the commands
        should appear on stderr.)
    '''
    if not ARGS.dry_run:
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

def docker_inspect(thing, *container_names):
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
        command = DOCKER_COMMAND + (thing, 'inspect') + container_names
        #   Unfortunately, this produces `Error: No such ...` on stderr
        #   when the image or container doesn't exist. We suppress stdout
        #   to avoid this printing to the terminal, though this may make
        #   debugging errors in this program more difficult.
        output = check_output(command, stderr=DEVNULL)
    except CalledProcessError as failed:
        output = failed.output     # Still need to get stdout
    return json.loads(output.decode('UTF-8'))

def docker_container_start(*container_names):
    ''' Run `docker container start` on the arguments.
    '''
    qprint("Starting container '{}'".format(ARGS.CONTANER_NAME))
    command = DOCKER_COMMAND + ('container', 'start') + container_names
    #   Suppress stdout because `docker` prints the names
    #   of the containers it started.
    retcode = drcall(command, stdout=DEVNULL)
    if retcode != 0:
        die("Couldn't start container")
    return None

####################################################################
#   Image configuration scripts and related files

class PTemplate(string.Template):
    delimiter = '%'

def dockerfile():
    ' Return the text of `DOCKERFILE` with template substitution done. '

    #   The pre-setup command is run before /tmp/setup-*
    #   This defaults to 'true' (a no-op), but can be set in the BASE_IMAGES
    #   config dict to e.g. install Bash so we can run the setup scripts.
    presetup_command = IMAGE_CONF.get('presetup') or 'true'
    dfargs = {
        'base_image':       ARGS.base_image,
        'presetup_command': presetup_command,
        'uname':            PWENT.pw_name,
    }
    return PTemplate(DOCKERFILE).substitute(dfargs)

def setup_pkg():
    ' Return the text of `SETUP_PKG` with template substitution done. '
    useradd = IMAGE_CONF.get('useradd') or 'generic'
    #   We avoid putting any user-related template arguments here so that
    #   this won't change based on user, thus letting us avoid regenerating
    #   this (fairly heavy) layer when user info changes.
    return PTemplate(SETUP_PKG).substitute({})

def setup_user():
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
#   Image and container creation

def build_image():
    perm_r   = stat.S_IRUSR
    perm_rx  = perm_r  | stat.S_IXUSR
    perm_rwx = perm_rx | stat.S_IWUSR
    if not ARGS.tmpdir:
        ARGS.tmpdir = tmpdir = mkdtemp(prefix=PROGNAME+'-build-')
    else:
        tmpdir = ARGS.tmpdir
        os.mkdir(tmpdir, perm_rwx)  # We want to die if it already exists
    qprint('Setting up context for image build in {}'.format(tmpdir),
        force_print=ARGS.keep_tmpdir)

    with open(pjoin(tmpdir, 'Dockerfile'), 'w', encoding='UTF-8') as f:
        os.fchmod(f.fileno(), perm_r)
        print(dockerfile(), file=f)

    with open(pjoin(tmpdir, 'setup-pkg'), 'w', encoding='UTF-8') as f:
        os.fchmod(f.fileno(), perm_rx)
        print(setup_pkg(), file=f)

    with open(pjoin(tmpdir, 'setup-user'), 'w', encoding='UTF-8') as f:
        os.fchmod(f.fileno(), perm_rx)
        print(setup_user(), file=f)

    if ARGS.force_rebuild:
        qprint("Removing image '{}' and forcing full rebuild" \
            .format(image_alias()))
        drcall(DOCKER_COMMAND + ('rmi', '-f', image_alias()))

    qprint("Building image '{}'".format(image_alias()))
    command = DOCKER_COMMAND + ('build',)
    if ARGS.progress:
        command += ('--progress=plain',)
    if ARGS.quiet:
        command += ('--quiet',)
    if ARGS.force_rebuild:
        command += ('--no-cache',)
    command += ('--tag', image_alias(), tmpdir)
    retcode = drcall(command)
    if retcode != 0:
        die("Error building image '{}' from '{}'"
            .format(image_alias(), ARGS.base_image))

    if not ARGS.keep_tmpdir:
        shutil.rmtree(tmpdir)

def image_alias():
    ' "Alias" is name plus tag '
    if ARGS.image:
        return ARGS.image
    else:
        if not ARGS.base_image:
            #   It would be nice to display the name of the image we would
            #   build here, but we can't because it wasn't specified and
            #   we can't generate it from the base image name.
            die('No such container; supply -B base-image to build.')
        if not ARGS.tag:
            ARGS.tag = PWENT.pw_name
        return '{}/{}:{}'.format(
            PROGNAME, ARGS.base_image.replace(':', '.'), ARGS.tag)

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

def create_container():
    ''' Create a new container for persistent use.

        This is designed simply to exist, and may be stopped and restarted
        multiple times. After it's been created, we can't change the
        initial command run when a container is started so we always create
        it with an initial command of a long sleep (about 68 years, to
        avoid overflowing any old 32-bit systems) and run our actual
        commands or shells with ``docker exec`` in that existing container.
    '''
    shared_path_opts \
        = share_args(ARGS.share_ro, 'ro') + share_args(ARGS.share_rw, 'rw')

    images = docker_inspect('image', image_alias())
    if ARGS.force_rebuild:
        build_image()
    elif images or ARGS.image:
        #   If we found an image, use it. If we were explicitly requested
        #   to use a particular image, make sure we do not try to build it
        #   locally but let `docker run` try to download it.
        qprint("Using existing image '{}'".format(image_alias()))
    else:
        build_image()
    user = PWENT.pw_name
    qprint("Creating new container '{}' from image '{}' for user {}" \
        .format(ARGS.CONTANER_NAME, image_alias(), user))
    command = DOCKER_COMMAND + ('run',
        '--name='+ARGS.CONTANER_NAME, '--hostname='+ARGS.CONTANER_NAME,
        '--env=HOST_HOSTNAME='+node(),
        '--env=LOGNAME='+user, '--env=USER='+user,
        '--rm=false', '--detach=true', '--tty=false',
        *shared_path_opts, *ARGS.run_opt,
        image_alias(), '/bin/sleep', str(2**31-1) )
    retcode = drcall(command, stdout=DEVNULL)   # stdout prints container ID
    if retcode != 0:
        die('Failed to create container {} with command:\n{}' \
            .format(ARGS.CONTANER_NAME, ' '.join(command)))

def waitforstart(container_name):
    ''' Wait for a container to start, dieing if it exits immediately.

        The `Docker API`_ does not indicate whether it guarantees it won't
        return from a start call before the container is started. Regardless,
        we still need to check that it hasn't exited immediately.

        .. Docker API: https://docs.docker.com/engine/api/v1.30/#operation/ContainerStart
    '''
    if ARGS.dry_run: return
    tries = 50
    while tries > 0:
        containers = docker_inspect('container', ARGS.CONTANER_NAME)
        if not containers:
            die("Container '{}' was started but is no longer running" \
                .format(ARGS.CONTANER_NAME))
        if containers[0]['State']['Running']:
            break
        else:
            time.sleep(0.1)
            tries -= 1
    if not tries > 0:
        die("Cannot start container '{}'".format(ARGS.CONTANER_NAME))

def enter_container():
    ' Enter the container, doing any dependent actions necessary. '
    docker_setup()

    #   Any arguments that modify the `docker run` command are not
    #   compatible with existing containers where `docker run` has
    #   already been executed.
    not_on_existing = (ARGS.base_image is not None)                     \
        or (len(ARGS.run_opt) > 0)                                      \
        or (len(ARGS.share_ro) > 0)                                     \
        or (len(ARGS.share_rw) > 0)
    not_on_existing_msg =                                               \
         '-B, -r and -s options cannot affect existing containers'

    containers = docker_inspect('container', ARGS.CONTANER_NAME)
    if not containers:
        create_container()      # Also starts
    elif not_on_existing:
        die(not_on_existing_msg)
    elif not containers[0]['State']['Running']:
        docker_container_start(ARGS.CONTANER_NAME)

    waitforstart(ARGS.CONTANER_NAME)

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
    command.append(ARGS.CONTANER_NAME)
    command += ARGS.COMMAND
    stdout.flush(); stderr.flush()  # Ensure all our output is complete
                                    # before this process is replaced.
    if not ARGS.dry_run:
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
    pe.add_argument('CONTANER_NAME', nargs='?',
        help='container name or ID (required)')
    pe.add_argument('-L', '--list-base-images', action='store_true',
        help='list base images this script knows how to configure')
    pe.add_argument('--version', action='store_true',
        help='show program version information')

    #   All remaining args are the command to run in the container.
    p.add_argument('COMMAND', nargs=REMAINDER, default='SEE BELOW',
        help='command to run in container (default: bash -l)')

    global ARGS; ARGS = p.parse_args()

    #   `default=` does not work with nargs=REMAINDER. We cannot use
    #   nargs='*' because that will cause options in the remainder to be
    #   interpreted as dent options unless the user adds `--` between,
    #   which is inconvenient.
    if not ARGS.COMMAND: ARGS.COMMAND = ['bash', '-l']

    #   If we know the given base image name, get any special configuration
    #   for it. Otherwise we use a generic config.
    global IMAGE_CONF; IMAGE_CONF = BASE_IMAGES.get(ARGS.base_image) or {}

    if ARGS.list_base_images:
        for i in BASE_IMAGES.keys(): print(i)
    elif ARGS.version:
        print(f'{p.prog} version {version(p.prog)}')

    elif ARGS.print_file and ARGS.CONTANER_NAME:
        print(PRINT_FILE_ARGS[ARGS.print_file]())
    elif ARGS.CONTANER_NAME:
        return enter_container()
    else:
        die('Internal argument parsing error.')     # Should never happen.
