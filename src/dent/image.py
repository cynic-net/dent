''' dent.image - image configuration scripts, related files, and image build '''

from    collections import OrderedDict
from    collections.abc  import Callable
from    os.path import join as pjoin
from    tempfile import mkdtemp
import  os, shutil, stat, string

from    importlib_resources  import files as resfiles

from    dent  import docker
from    dent.configure  import Config, PrintFile
from    dent.util  import PROGNAME, PWENT, die, qprint

IMAGE_CONF  : dict[str,str]

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
#   ('debian:8',        {}),    # Archive package repos have issues
#   ('debian:9',        {}),    # Archive package repos have issues
    ('debian:10',       {}),
    ('debian:11',       {}),
    ('debian:12',       {}),
    ('debian:13',       {}),
#   ('ubuntu:14.04',    {}),
    ('ubuntu:16.04',    {}),
    ('ubuntu:18.04',    {}),
    ('ubuntu:20.04',    {}),
    ('ubuntu:22.04',    {}),
    ('ubuntu:24.04',    {}),
    ('ubuntu:26.04',    {}),
#   ('centos:6',        {}),    # But not with kernel ≥ 4.19 (works on 4.4).
#   ('centos:7',        {}),    # Package repos are gone.
#   ('centos:8',        {}),    # Package repos are gone.
    ('rockylinux:8',    {}),
#   ('rockylinux:9',    {}),    # FIXME: --allowerasing would do the trick,
                                # but that's not in CentOS 7.
    ('fedora:30',       {}),
    ('fedora:38',       {}),
    ('fedora:43',       {}),
))

def resource_text(name):
    return resfiles().joinpath(name).read_text()

DOCKERFILE      = resource_text('Dockerfile')
SETUP_HEADER    = resource_text('setup-header')
SETUP_PKG       = SETUP_HEADER + resource_text('setup-pkg')
SETUP_USER      = SETUP_HEADER + resource_text('setup-user')

class PTemplate(string.Template):
    delimiter = '%'

def dockerfile(conf:Config) -> str:
    ' Return the text of `DOCKERFILE` with template substitution done. '

    #   The pre-setup command is run before /tmp/setup-*
    #   This defaults to 'true' (a no-op), but can be set in the BASE_IMAGES
    #   config dict to e.g. install Bash so we can run the setup scripts.
    presetup_command = IMAGE_CONF.get('presetup') or 'true'
    dfargs = {
        'base_image':       conf.base_image,
        'presetup_command': presetup_command,
        'uname':            PWENT.pw_name,
    }
    return PTemplate(DOCKERFILE).substitute(dfargs)

def setup_pkg(conf:Config) -> str:
    ' Return the text of `SETUP_PKG` with template substitution done. '
    useradd = IMAGE_CONF.get('useradd') or 'generic'
    #   We avoid putting any user-related template arguments here so that
    #   this won't change based on user, thus letting us avoid regenerating
    #   this (fairly heavy) layer when user info changes.
    return PTemplate(SETUP_PKG).substitute({})

def setup_user(conf:Config) -> str:
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

#   Things we can print with -P and their functions producing the text.
#   The key type keeps these in sync with the -P choices in parseargs().
PRINT_FILE_ARGS : dict[PrintFile,Callable[[Config],str]] = {
    'dockerfile':   dockerfile,
    'setup-pkg':    setup_pkg,
    'setup-user':   setup_user,
}

####################################################################
#   Container image build

def build_image(conf:Config):
    perm_r   = stat.S_IRUSR
    perm_rx  = perm_r  | stat.S_IXUSR
    perm_rwx = perm_rx | stat.S_IWUSR
    if not conf.tmpdir:
        conf.tmpdir = tmpdir = mkdtemp(prefix=PROGNAME+'-build-')
    else:
        tmpdir = conf.tmpdir
        os.mkdir(tmpdir, perm_rwx)  # We want to die if it already exists
    qprint(conf.quiet, 'Setting up context for image build in {}'.format(tmpdir),
        force_print=conf.keep_tmpdir)

    with open(pjoin(tmpdir, 'Dockerfile'), 'w', encoding='UTF-8') as f:
        os.fchmod(f.fileno(), perm_r)
        print(dockerfile(conf), file=f)

    with open(pjoin(tmpdir, 'setup-pkg'), 'w', encoding='UTF-8') as f:
        os.fchmod(f.fileno(), perm_rx)
        print(setup_pkg(conf), file=f)

    with open(pjoin(tmpdir, 'setup-user'), 'w', encoding='UTF-8') as f:
        os.fchmod(f.fileno(), perm_rx)
        print(setup_user(conf), file=f)

    if conf.force_rebuild:
        qprint(conf.quiet, "Removing image '{}' and forcing full rebuild" \
            .format(image_alias(conf)))
        docker.drcall(conf,
            docker.DOCKER_COMMAND + ('rmi', '-f', image_alias(conf)))

    qprint(conf.quiet, "Building image '{}'".format(image_alias(conf)))
    command = docker.DOCKER_COMMAND + ('build',)
    if conf.progress:
        command += ('--progress=plain',)
    if conf.quiet:
        command += ('--quiet',)
    if conf.force_rebuild:
        command += ('--no-cache',)
    command += ('--tag', image_alias(conf), tmpdir)
    retcode = docker.drcall(conf, command)
    if retcode != 0:
        die("Error building image '{}' from '{}'"
            .format(image_alias(conf), conf.base_image))

    if not conf.keep_tmpdir:
        shutil.rmtree(tmpdir)

def image_alias(conf:Config) -> str:
    ' "Alias" is name plus tag '
    if conf.image:
        return conf.image
    else:
        if not conf.base_image:
            #   It would be nice to display the name of the image we would
            #   build here, but we can't because it wasn't specified and
            #   we can't generate it from the base image name.
            die('No such container; supply -B base-image to build.')
        if not conf.tag:
            conf.tag = PWENT.pw_name
        return '{}/{}:{}'.format(
            PROGNAME, conf.base_image.replace(':', '.'), conf.tag)
