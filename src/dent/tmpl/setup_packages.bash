#
#   setup_packages.bash: Install "standard" system packages into the image
#

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
