Dent Testing and Development
============================

`Test` starts by sourcing `pactivate`, which builds a virtualenv using
the first `python3` or `python` found in the path. If you wish to test
under a different version of Python, you can symlink `.python` to it
before you start testing, e.g.:

    rm -rf .build/virtualenv/
    ln -s $(pythonz locate 3.7.17) .python
    ./Test

`Test` (excepting the typecheck and unit tests) needs to send commands to
the Docker daemon using the `docker` command. If it can do this with just
plain `docker` command it will use that; otherwise it will use `sudo
docker` instead. If neither of these methods work you can set the
`DOCKER_HOST` environment variable to a socket you can use to access the
daemon; in some cases the `dockerd-proxy` command included in this package
may help with this.

General options for `Test` include:
- `-h`/`--help`: Print usage hints.
- `-v`/`--verbose`
- `-c`/`--small-clean`
- `--`: Pass all args after this to `pytest`.

The tests consist of several parts. All of these are run (in the following
order) by default, but you can specify a subset to run using the `--test
part` or `-t part` options; this will run only the parts specified. (The
option may be given multiple times.)
- `typecheck`: Type checking with `mypy`.
- `unittest`: Unit tests in `src/**/*.pt` files, run with `pytest`.
- `dryrun`: Dry run tests that check `dent --dry-run` functionality. This
  avoids running `docker` commands that change state (creating containers,
  etc.), instead printing the command lines, but it does need to run
  `docker` commands that check state.
- `nonbuild`: Tests that check Dent functionality outside of building
  images (i.e., just creating, starting and entering containers).
- `build`: Tests that build images. Builds based on a default set of
   base images will be tested, but you can override this by specifying one
   or more specific image names using the `-B` option, e.g., `.Test -B
   debian:9 -B centos:7`)

Additional `Test` options related to images are:
- `-B imgname`: Instead of the default list of base images, test with
  _imagename._ (This may be specified multiple times.)
- `-f`/`--no-force-rebuild`: Do not force a rebuild of layers that are
  already cached. This means the code to build those layers isn't tested,
  but speeds tests of other code (especially that which builds subsequent
  layers).
- `--keep-images`: Do not remove the images created by the build tests,
  allowing you to examine them after the tests have been completed. (The
  test containers are always removed.)

When changing things related to the image build, use of the
`--no-force-rebuild` and `--keep-images` options and careful management of
cached layers can greatly speed testing. In particular, changes to the
container can be iteratively tested and debugged by making them a separate
layer at the end and then after testing moved into an earlier layer. When
doing this, ensure you remove or invalidate the cached final layer (by
changing the Dockerfile line or a file it references).

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
