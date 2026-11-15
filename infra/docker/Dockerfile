# Nó do cluster em container: mesma pilha das VMs (Ubuntu 24.04, Open MPI, mpi4py),
# já instalada na imagem para o cluster subir em segundos. A configuração (conta
# mpi, chaves, hostfile, cópia do código) continua sendo feita pela role Ansible.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends ansible sudo acl ca-certificates \
        openssh-server openssh-client python3 python3-mpi4py openmpi-bin \
    && mkdir -p /run/sshd \
    && rm -f /etc/ssh/ssh_host_*
CMD ["/bin/sh", "-c", "ssh-keygen -A && exec /usr/sbin/sshd -D -e"]
