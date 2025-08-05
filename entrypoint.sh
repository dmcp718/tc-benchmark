#!/bin/bash
set -o errexit
set -o nounset

# shellcheck disable=SC1073
cat << "EOF"
__     __               _     _       ____  _
\ \   / /_ _ _ __ _ __ (_)___| |__   |  _ \| |_   _ ___
 \ \ / / _' | '__| '_ \| / __| '_ \  | |_) | | | | / __|
  \ V / (_| | |  | | | | \__ \ | | | |  __/| | |_| \__ \
   \_/ \__,_|_|  |_| |_|_|___/_| |_| |_|   |_|\__,_|___/

                www.varnish-software.com

EOF
varnishd -V 2>&1|head -n1

# Internal variable, only used to add params based on env
EXTRA=

if [ ! -f "${VARNISH_SECRET_FILE}" ]; then
  echo "Generating new secrets file: ${VARNISH_SECRET_FILE}"
  uuidgen > "${VARNISH_SECRET_FILE}"
  chmod 0600 "${VARNISH_SECRET_FILE}"
fi

# If not defined, use in-memory MSE3 by default
if [ -z "${VARNISH_STORAGE_BACKEND}" ]; then
  VARNISH_STORAGE_BACKEND="mse"
fi

if [ -f "${MSE_CONFIG}" ]; then
  echo "Creating and initializing Massive Storage Engine 3 data files and stores"
  EXTRA="${EXTRA} -s mse,${MSE_CONFIG}"
  mkfs.mse -c "${MSE_CONFIG}" || true
elif [ -f "${MSE4_CONFIG}" ]; then
  echo "Creating and initializing Massive Storage Engine 4 data files and stores"
  EXTRA="${EXTRA} -s mse4,${MSE4_CONFIG}"
  # Handle MSE4 persistent cache upgrade preservation behavior.
  if [ "$MSE4_CACHE_FORCE_PRESERVE" -eq 0 ]; then
    mkfs.mse4 -f -c "${MSE4_CONFIG}" configure || true
  else
    mkfs.mse4 -c "${MSE4_CONFIG}" configure || true
  fi
else
  EXTRA="${EXTRA} -s ${VARNISH_STORAGE_BACKEND}"
fi

# When running into a container which have resource limits defined
# we have to handle MSE_MEMORY_TARGET with % differently.
# We are going to use cgroups pseudo fs mounted in /sys/fs/cgroup and use memory subdirectory as references for now
# Only if we have %
if echo "${MSE_MEMORY_TARGET}" | grep -q "%"; then
  if grep -qw memory /sys/fs/cgroup/cgroup.controllers; then
    # cgroups v2; max is the default value if memory limit is not set
    if grep -qv max /sys/fs/cgroup/memory.max &>/dev/null; then
      MSE_MEMORY_TARGET=$(awk -v mmt=${MSE_MEMORY_TARGET%\%} '{ printf("%dk\n", int($1 * mmt / 100 / 1024));}' /sys/fs/cgroup/memory.max)
    fi
  else
    # cgroups v1; 2^63 -> 9223372036854771712 : default value if none are present on container creation
    if grep -qEv "^9223372036854771712$" /sys/fs/cgroup/memory/memory.limit_in_bytes &>/dev/null; then
      MSE_MEMORY_TARGET=$(awk -v mmt=${MSE_MEMORY_TARGET%\%} '{ printf("%dk\n", int($1 * mmt / 100 / 1024));}' /sys/fs/cgroup/memory/memory.limit_in_bytes)
    fi
  fi
fi

# Varnish in-core tls
# If VARNISH_TLS_CFG is set and is not a file, generate tlf.cfg and self-signed cert
# If VARNISH_TLS_CFG is set and is a file, use that file. The user is responsible to
# provide the certificate in the correct path as specified in the TLS config file.
if [ -n "${VARNISH_TLS_CFG}" ]; then
  echo "Enabling Varnish in-core TLS"
  if [ -f "${VARNISH_TLS_CFG}" ]; then
    EXTRA="${EXTRA} -A ${VARNISH_TLS_CFG}"
  else
    openssl req -x509 -nodes -days 365 \
      -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost" \
      -newkey rsa:2048 -keyout /dev/shm/varnish-selfsigned.key \
      -out /dev/shm/varnish-selfsigned.crt
    # Concatenate files
    cat /dev/shm/varnish-selfsigned.key /dev/shm/varnish-selfsigned.crt > /dev/shm/varnish-selfsigned.pem
    rm -f /dev/shm/varnish-selfsigned.key /dev/shm/varnish-selfsigned.crt
    # Generate varnishd tls file
    echo -e 'frontend = {\nhost = ""\nport = "6443"\n}\npem-file = "/dev/shm/varnish-selfsigned.pem"\n' \
    > /dev/shm/varnish-tls.cfg
    # Add -A argument with generated config to varnishd
    EXTRA="${EXTRA} -A /dev/shm/varnish-tls.cfg"
  fi
fi

# We need to take arguments for VARNISH_EXTRA.
# shellcheck disable=SC2086
exec varnishd -f "${VARNISH_VCL_CONF}" \
  -F -a "${VARNISH_LISTEN_ADDRESS}":"${VARNISH_LISTEN_PORT}" \
  -p thread_pool_min="${VARNISH_MIN_THREADS}" \
  -p thread_pool_max="${VARNISH_MAX_THREADS}" \
  -p thread_pool_timeout="${VARNISH_THREAD_TIMEOUT}" \
  -S "${VARNISH_SECRET_FILE}" \
  -t "${VARNISH_TTL}" \
  -T "${VARNISH_ADMIN_LISTEN_ADDRESS}:${VARNISH_ADMIN_LISTEN_PORT}" \
  -p memory_target="${MSE_MEMORY_TARGET}" ${VARNISH_EXTRA} ${EXTRA}
