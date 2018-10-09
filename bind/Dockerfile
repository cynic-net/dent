FROM alpine:3.8
RUN    apk add bind \
    && mkdir -p /var/cache/bind
#   XXX don't forget control port!
EXPOSE 53 53/udp

#   External mounts: databases, maybe log files?

#   -g forces foreground run and logging to stderr
ENTRYPOINT ["named", "-g"]
