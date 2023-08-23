`dent` Testing and Development
==============================

`Test` starts by sourcing `activate`, which builds a virtualenv using
the first `python3` or `python` found in the path. If you wish to test
under a different version of Python, you can create an appropriate
virtualenv manually before you start testing, e.g.:

    rm -rf .build/virtualenv/
    . ./activate --python=$(pythonz locate 3.7.3)

`Test` needs to send commands to the Docker daemon using the `docker`
command. If it can do this with just plain `docker` command it will
use that; otherwise it will use `sudo docker` instead. If neither of
these methods work you can set the `DOCKER_HOST` environment variable
to a socket you can use to access the daemon; in some cases the
`dockerd-proxy` command in the directory above this one may help with
this.

The tests consist of two parts:
1. The "non-build" tests that check `dent` functionality outside of
   building images (creating, starting and entering containers). These
   are run first and may be skipped by specifying `--skip-nonbuild`
   option.
2. The "build" tests that build images. Builds based on a default set
   of base images will be tested, but you can override this by
   specifying specific image names (e.g., `debian:9 centos:7`) as
   arguments after the options. The build tests may be skipped
   entirely with the `--skip-build` option.

`Test` options related to images are:
- `--no-force-rebuild`: Do not force a rebuild of layers that are
  already cached. This means the code to build those layers isn't
  tested, but speeds tests of other code (especially that which builds
  subsequent layers).
- `--keep-images`: Do not remove the images created by the build
  tests. (The test containers are always removed.)

When changing things related to the image build, use of the above two
options and careful management of cached layers can greatly speed
testing. In particular, changes to the container can be iteratively
tested and debugged by making them a separate layer at the end and
then after testing moved into an earlier layer. When doing this,
ensure you remove or invalidate the cached final layer (by changing
the Dockerfile line or a file it references).

### Test System Bugs

The build tests will re-use any existing image layers whose
`Dockerfile` command has not changed; this may or may not be what the
developer wants. Currently the only way to deal with this is to remove
any intermediate images you don't want to re-use, but this isn't possible
when those are used by other images you want to keep.

The container and image names are fixed. This means that existing
images and containers with those names will be wiped out during a test
run and that simultaneously running `Test` more than once on a host
will likely lead to collisions and bad test results for the build tests.

The tests send all image build information to stdout, which is quite
noisy. It would be better to send the detailed build information to a
logfile under `.build/` and print only progress and summary information.
