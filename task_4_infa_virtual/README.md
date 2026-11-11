# task_4_infa_virtual

## Infrastructure vision

The time-critical Java tier stays on bare metal and is treated as rebuildable.
The supporting services (CMDB, Jenkins, Nexus, GitLab) run as virtual machines.
Everything is defined as code and stored in GitLab/GitHub.

## Monitoring

Prometheus scrapes the metrics and Alertmanager routes the alerts and handles
on-call escalation. Pulling metrics keeps the overhead on the monitored hosts
very low, which matters on the time-critical tier.

On the Java side JMX Exporter or Micrometer exposes JVM internals (heap, GC
pauses, threads) and request latency histograms. Alerts use p99 latency and GC
pause time, because averages hide the slow requests.

Grafana is the single UI for metrics and logs. Dashboards are kept in Git.

## Provisioning

Physical servers are discovered and installed by Foreman (PXE and Redfish,
unattended OS installation). Foreman works with any distro and integrates with
configuration management.

Virtual machines are created by Terraform with cloud-init from versioned
templates.

Ansible configures both kinds of hosts. It is agentless, so nothing extra runs
on the latency-critical machines.

## De-provisioning

A GitLab CI pipeline runs an Ansible decommission playbook, which:

1. drains the host from the load balancer
2. removes it from monitoring and DNS
3. revokes its certificates and secrets
4. wipes the disks
5. marks the host as decommissioned in the CMDB

Virtual machines are removed with `terraform destroy`, which deletes the VM and
its resources in one step. With both paths automated there are no forgotten
hosts or stale CMDB records.

## Backup

VM backups go to Proxmox Backup Server. They are incremental, deduplicated and
verified, and the backup server is integrated with the hypervisor.

GitLab and Nexus also get their own backups (GitLab built-in backup, Nexus blob
store and database), so the application data is consistent when restored.

restic copies the backups to off-site S3-compatible storage with object lock.
That copy is encrypted and cannot be changed, which protects it against
ransomware. Restores are tested on a schedule.

The bare-metal Java nodes are stateless. They are rebuilt with the provisioning
tools and are not backed up.

## Hypervisor

Proxmox VE (KVM) runs the supporting services. It is open source with no
per-core licensing, has clustering, high availability and live migration built
in, and its API works with Terraform. Three nodes are enough for the supporting
services.

The Java tier runs without a hypervisor, to avoid virtualization overhead and
noisy-neighbour jitter.

## Log collecting

Grafana Alloy runs on every host and ships application, system and GC logs to
Loki. Loki indexes only labels, so it is cheap to run, and it uses the same
labels and Grafana UI as the metrics. That makes it easy to look at logs and
metrics side by side.

Java applications write structured JSON logs through asynchronous appenders.
Logging does not block request threads and the logs are easy to parse.
