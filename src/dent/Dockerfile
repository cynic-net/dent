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
