''' Configuration for a ``dent`` run. This comes from command line arguments
    and the user's environment, and includes information both on the
    container being built/run and how we run ``dent`` (quiet mode, etc.).
'''

from    argparse  import Namespace
from    collections import OrderedDict
from    os  import getuid
from    pwd import getpwuid, struct_passwd
from    subprocess import call, DEVNULL
from    sys import stderr
from    typing  import List, Optional, Tuple

####################################################################
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

####################################################################

class Config:

    args        :Namespace
    pwent       :struct_passwd

    def __init__(self, args:Namespace):
        self.args = args
        self.pwent = getpwuid(getuid())

    ####################################################################
    #   Internal configuration information

    def image_conf(self, key:str) -> Optional[str]:
        conf = BASE_IMAGES.get(self.args.base_image) or {}
        return conf.get(key)

    ####################################################################
    #   Program information and error reporting

    def qprint(self, *posargs, force_print=False, **kwargs) -> None:
        ''' Call `print()` on arguments unless quiet flag is set.

            `force_print` will print even if ARGS.quiet is set; this allows
            the caller to test on a second condition without having to use
            ``if`` and a duplicate call to `print()`.
        '''
        if force_print or not self.args.quiet:
            print('-----', *posargs, **kwargs)

    def die(self, msg) -> None:
        print(f'{self.progname()}: {msg}', file=stderr)
        exit(1)

    def progname(self) -> str:
        from sys        import  argv
        from os.path    import  basename
        return basename(argv[0])

    ####################################################################
    #   External command configuration and execution

    docker_command:Tuple[str,...]

    def docker_setup(self) -> None:
        ' Determine whether we use ``docker`` or ``sudo docker``. '

        self.docker_command = ('docker',)
        retcode = call(
            self.docker_command + ('info',), stdout=DEVNULL, stderr=DEVNULL)
        if retcode == 0:  return

        #   Before we do any further work, ensure user can sudo and has
        #   cached credentials.
        retcode = call(('sudo', '-v'))
        if retcode != 0:
            self.die('Cannot run `docker` as this user and cannot sudo.')
        self.docker_command = ('sudo',) + self.docker_command

    ####################################################################
    #   Container configuration.

    def image_alias(self) -> str:
        ' "Alias" is name plus tag '
        if self.args.image:
            return self.args.image
        else:
            if not self.args.base_image:
                #   It would be nice to display the name of the image we would
                #   build here, but we can't because it wasn't specified and
                #   we can't generate it from the base image name.
                raise KeyError('Needed a base image but none specified')
            if not self.args.tag:
                self.args.tag = self.pwent.pw_name   # XXX mutation!
            return '{}/{}:{}'.format(self.progname(),
                self.args.base_image.replace(':', '.'), self.args.tag)

    def exec_command(self) -> List[str]:
        ' The command we want to ``exec`` in the Docker container. '
        #   `default=` does not work with nargs=REMAINDER. We cannot use
        #   nargs='*' because that will cause options in the remainder to be
        #   interpreted as dent options unless the user adds `--` between,
        #   which is inconvenient.
        return (self.args.COMMAND or ['bash', '-l'])

