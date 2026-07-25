Dent Usage, Options and Configuration
=====================================

Reading the short [§"Operation Overview"][oper-ov] section in
`doc/operation.md` will make this document considerably easier to
understand.

#### Arguments

* `dent [options] CONTAINER_NAME [--] [COMMAND [arg ...]]`

Runs the given _COMMAND_ in container _CONTAINER_NAME_ using `docker
exec -it CONTAINER_NAME` or similar. If you supply any _arg_ values
that start with a hyphen, ensure you use the `--` after the container
name to avoid these being parsed as options to Dent.

_CONTAINER_NAME_ is a container name or ID. An existing container with
that name will always be used if present (it will be started if it's
stopped), otherwise it's the name of the container to be created. If
you share the host with other users, you may want to adopt a container
naming convention to avoid name collisions. Dent currently provides
no support for this; it uses the container name exactly as specified.

The default _COMMAND_ is `bash -l` to give an interactive login shell.
Curently _COMMAND_ is always run directly, without a login
environment. To run a single command in your login environment (e.g.,
to use a shell alias) use `-- bash -lc 'cmd arg ...'`.

The user and initial working directory within the container will be
the same as specified by the `docker run` command; this is specified
by the image if Dent created the container. There is currently no
way to override this.

Notes on `docker exec` options:
- The `-t` option (allocate a pseudo-TTY) will be used only if stdin
  is a terminal. There is currently no way to override this.
- The `-i` option (keep stdin open when detached) is always used;
  there seems to be no reason ever not to use it because Dent
  currently does not support `-d` (detached mode).

#### Options

No container command is run if either of the following two options are
given:
* `-h`, `--help`: Ignore all other arguments and print a usage
  summary.
* `-L`, `--list-base-images`: List base images Dent knows it can use
  to create working interactive images. For somewhat silly reasons,
  this still requires a _CNAME_ argument, which is ignored.

The following options control the behaviour of the command-line program:
* `-q, --quiet`: Do not print informational lines indicating what Docker
  image and container actions (remove/build/create) are being taken and use
  `docker build --quiet` when building an image.
* `-n, --dry-run`: For commands that would change or execute Docker images
  or containers (including `rmi`, `build`, `run` and `exec`), just print
  the command to stderr. (Unless you use `-q`, the usual user-oriented
  messages about actions to be taken will still appear on stdout.) Build
  configuration is still created, so `--keep-tmpdir` still works. As well
  as testing, this can also be useful to customize image and container
  creation by printing the command that would be executed and then
  executing it by hand with different options.

Options that configure Dent's images and containers are described below.


Options and Configuration
-------------------------

Most Dent configuration options may be specified as command-line options or
in a configuration file.

### Configuration File

`dent` reads configuration from `$XDG_CONFIG/dent/config.toml`, which
defaults to `$HOME/.config/dent/config.toml`. Each top-level section is a
named _configuration_ which can be selected via either the `-c CONFNAME`
option or automatically via pattern matching on the container name you
provide. The configuration file options are always applied before the
command-line options, which may override them.

Currently, each section is stand-alone. You may specify only one `-c
CONFNAME` argument; this will override any name matching (see below). All
command line arguments are applied after (and may update) the configuration
selected from the file.

### Configuration Directives and Command-line Options

- Directives marked __¹type__ are scalar values; subsequent specifications
  will overwrite the previous value.
- Directives marked __[type]__ are lists; scalars are treated as singleton
  lists and subsequent values are appended to the list. An empty list will
  clear any previous values in the list.
- Directives marked __{type:type}__ are dictionaries; these may also be
  specified in singleton form as `config_directive.NAME = VALUE`.

All configuration directives can be used as command-line options by
preceding them with `--`. Exact usage depends on the type:
- For bool values, specify just the option name and it will be set to true:
  `force-rebuild=true` → `--force-rebuild`.
- For other values, specify the value after an `=` sign or space:
  `base-image="foo"` → `--base-image=foo` or or `--base-image foo`.

Arguments specified multiple times:
- For scalers, override the previous use.
- For lists and dictionaries, append to the list/dictionary unless the
  option argument is empty, in which case it clears the list.

Command-line option

#### Non-option Directives

The following directives cannot appear on the command line; they work in
the configuration file only.

* `names-matching` [str]: A list of shell glob patterns (using `*`,
  `?` and `[…]` wildcards) that is matched against the given pattern. If
  exactly one configuration section matches the name of the container to be
  created/entered, that configuration will be used. Otherwise a warning
  will be emitted and you must use `-c` to specify a configuration.

#### Image-related Directives

The following options control which image is used and building of the
image.

* `base-image` ¹str, `-B BASE_IMAGE`: Base image from which to build
  container image if container image (default name or specified with
  `image`/`-i`) does not exist.

* `image` ¹str, `-i IMAGE`: Name of container image from which the
  container will be created, if necessary. Has a default value only if
  `base-image` is specified.

* `tag` ¹str, `-t TAG`: Tag for image if `image` is not specified. (With
  `image`, specify the tag with the image name in `name:tag` format.) The
  default tag used by `base-image` is the user's login name.

* `force-rebuild` ¹bool, `-R`: When building an image, ignore any existing
  layers that would be considered "cached" and reused, rebuilding every
  layer in the `Dockerfile` from scratch. (I.e., use `docker build
  --no-cache`.)

#### Container-related Directives

The following optons control container creation.

* `run-opt` [str], `-r RUN_OPT`: Add options to pass to `docker run` at
  container creation. These are _not_ split the way the shell does, so
  `run-opt="-e FOO=bar"` will not work; it will pass `-e FOO=bar` as a
  single argument rather than two arguments to `docker run`. Instead, use
  `run-opt="-e=FOO=bar"`.

  Note also that `-r` can be used _only_ when Dent is creating a new
  container. If it finds an existing container that it would use, it will
  generate an error explaining that the `-r` option would have no effect.

* `set-env` {name:value}: Set the given environment variables when the
  container is created.

* `share-ro` [str], `-s PATH`: Read-only bind mount the given _path_ to the
  same path inside the container. `~` is interpreted as the shell does.
  Relative paths are relative to $HOME.

* `share-rw` [str], `-S PATH`: As `share-ro`, except that the share is
  read-write.

#### Entry-related Directives

* `env-copy` [str], `-e NAME`: On entering the container, copy the
  environment variable named _name_ and its current value to the shell in
  the container.

#### Development and Debugging Directives

The following options are used mainly for development and debugging.

* `--tmpdir TMPDIR`: The directory to use for the Docker build context
  when building an image. Default is a `mkdtmp` name under `/tmp`.
* `--keep-tmpdir`: If a new image is built from a base image, do not
  remove the temporary directory containing the `Dockerfile` and the
  build context. The name of the directory is printed in a message at
  the start of the build. (This message is not suppressed by `-q`.)

### Example Configurations

    ["debian13"]
    names-matching = [ 'deb13*', '*-deb13' ]
    base-image = 'debian:13'
    share-ro = [    # only on same OS ver
        '.local/state/mise/',
        '~/.ghcup/',
    ]
    share-rw = '~/co/public/'
    set-env = { 'TERM' = 'xterm-256color', 'EDITOR' = 'vi' }
    copy-env = 'LC_*'

    ["someco"]
    names-matching = [ 'someco*', '[0-9]someco*' ]
    base-image = 'debian:13'
    share-ro = [    # only on same OS ver
        '~/.local/state/mise/',
        '~/.ghcup/',
    ]
    share-rw = [
        '~/co/public/',
        '~/co/sensitive/someco/'
    ]
    set-env.TERM = 'xterm'

    ["foo"]
    ["foo".set-env]
    BAR="baz"
    QUUX="I don't know what comes next."

### Future Work

* Consider if we need `-C x=y` to set arbitrary configuration directives.
  This overlaps with the specific command-line options (e.g. `-C
  basename=abc` vs. `--basename=abc`) and maybe isn't necessary? It also
  feels as if it may be a lot of work to implement and validate. On the
  other hand, perhaps it means we need fewer things passed to argparse.
  (Unless we can have `Config` build the ArgumentParser based on what it
  knows.)

* We are considering ways to combine different configuration entries,
  including:
  - Allowing multiple `-c` specifications.
  - Adding `-a` for additional specifications that are added even when
    using `names-matching` rather than `-c`.
  - `additional-match = true` to allow a particular entry to be an
    additional match against the name along with one `= false` entry.
  - `include.0 = NAME` to include from another entry.

* Do we need an option to print out the fully parsed config we end up
  using? I'm kinda feeling not, at least not until we have config fragments
  being combined.


<!-------------------------------------------------------------------->
[oper-ov]: ./doc/operation.md#operation-overview
