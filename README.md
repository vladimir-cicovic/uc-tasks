# task_1_too_many

Ansible playbook for services that log "Too many open files".

The playbook finds systemd services that hit their open files limit, raises
`LimitNOFILE` with a systemd drop-in, restarts the service and checks the new
limit. A service is picked up when:

- it logged "Too many open files" at least 5 times since it started, or
- one of its processes uses 80% or more of its limit right now.

Note: `/etc/security/limits.conf` does not apply to systemd services, so the
limit is set in the unit (`/etc/systemd/system/<service>.service.d/90-nofile.conf`).

Tested on Ubuntu 22.04 with ansible-core 2.17.

## Files

```
fix-open-files.yml        the playbook
ansible.cfg               ansible settings (user, key, inventory)
inventory.ini             target hosts
reset-lab.sh              puts the lab target back to the start
test/lab-nginx.yml        nginx with LimitNOFILE=32
test/lab-fd-hog.yml       second test service with LimitNOFILE=64
test/fd-hog.py            program used by lab-fd-hog.yml
test/hold-connections.py  opens many connections to nginx
test/reset-lab.yml        used by reset-lab.sh
```

## Before you start

On the control node (the machine that runs Ansible), install Ansible and
create a key:

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:ansible/ansible
sudo apt install -y ansible
ssh-keygen -t ed25519 -f ~/.ssh/ansible_ed25519 -C ansible
cat ~/.ssh/ansible_ed25519.pub
```

On the target, create the user `ansible` with key login and sudo. Put your
public key and the control node IP in the `echo` line:

```bash
sudo adduser --disabled-password --gecos "" ansible
sudo install -d -m 700 -o ansible -g ansible /home/ansible/.ssh
echo 'from="CONTROL_NODE_IP" ssh-ed25519 AAAA... ansible' | sudo tee /home/ansible/.ssh/authorized_keys
sudo chown ansible:ansible /home/ansible/.ssh/authorized_keys
sudo chmod 600 /home/ansible/.ssh/authorized_keys
echo 'ansible ALL=(ALL) NOPASSWD:ALL' > /tmp/90-ansible
sudo visudo -cf /tmp/90-ansible && sudo install -m 440 /tmp/90-ansible /etc/sudoers.d/90-ansible
```

Back on the control node, set the target IP in `inventory.ini` and check the
connection:

```bash
cd task_1_too_many
ansible app_servers -m ping
ansible app_servers -b -a whoami
```

## Running the playbook

Dry run first, then the real run:

```bash
ansible-playbook fix-open-files.yml --check --diff
ansible-playbook fix-open-files.yml
```

Options, passed with `-e`:

| Variable | Default | Meaning |
|---|---|---|
| `fix_target` | 65536 | soft limit to set (hard limit is never lowered) |
| `fix_max_limits` | {} | own limit per service, e.g. `{"nginx": 4096}` |
| `fix_auto_units` | all | `all` or a list of services that may be changed |
| `fix_protected_units` | ssh, journald, docker, ... | only reported, never restarted |
| `fix_units` | [] | always set the limit for these services |

Example:

```bash
ansible-playbook fix-open-files.yml -e '{"fix_max_limits": {"nginx": 4096}}'
```

Every change is written to `/var/log/fix-open-files.log` on the target and to
the journal (`journalctl -t fix-open-files`). A second run changes nothing.

## Lab test

```bash
./reset-lab.sh
python3 test/hold-connections.py 192.168.152.138 --count 200 --seconds 8
ansible-playbook fix-open-files.yml --check
ansible-playbook fix-open-files.yml -e '{"fix_max_limits": {"nginx": 4096}}'
ansible app_servers -b -a 'cat /var/log/fix-open-files.log'
```

Second service, no options needed:

```bash
ansible-playbook test/lab-fd-hog.yml
sleep 12
ansible-playbook fix-open-files.yml
```

Run `./reset-lab.sh` to start again.
