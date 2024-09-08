#
#   setup_user.bash: Create/configure calling user's account in the image
#

users_generic() {
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
#   We change verifypw from its default of `all` to `any` for the user so
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
