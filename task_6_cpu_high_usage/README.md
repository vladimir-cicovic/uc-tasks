# task_6_cpu_high_usage

## Question

6. (Bonus Question) Looking at the graphs of your monitoring solution one of
   your high-traffic servers has few of the cores on 100% and others running
   fairly low at 20%. Looking at top/htop output this load is not coming from
   "userland". What would your troubleshooting steps be? (there is no "right"
   answer)

## Answer

First we install sysstat:

```
sudo apt install sysstat
```

Then we run:

```
mpstat -P ALL 1
```

There we can see which CPU is busy. Let's say it is CPU-0. Then we run:

```
ps -eLo pid,tid,psr,pcpu,comm --sort=-pcpu | awk '$3==0' | head
```

This command lists all processes running on CPU-0. We can also use:

```
pidstat -u 1
```

which shows, for each application, its CPU usage and the CPU it runs on.

Here we can see, for example, nginx or a similar process that can be bound to
CPU-0 (through its settings, otherwise IRQ balancing moves it automatically).
Let's say this service is nginx. First we check the nginx log (error.log) for
errors, and then the other logs on Linux:

- `/var/log/syslog`
- `/var/log/kern.log`
- `/var/log/auth.log`
- `/var/log/dmesg`
- `/var/log/boot.log`
- `journalctl`

We also look at the package logs:

- `/var/log/apt/history.log`
- `/var/log/apt/term.log`
- `/var/log/dpkg.log`

This way we make sure there was no upgrade to a new version that does not work
with the old config, libraries or other things (security, IRQ balancing and so
on).

If none of this points to a service or an application, we check the drivers:

```
watch -n 1 -d cat /proc/interrupts
watch -n 1 -d cat /proc/softirqs
```

We look for the IRQ that grows fast and the device it belongs to. If the
counter is racing, we have an interrupt storm, and the device name tells us
which driver it is.

Then we need to find the exact function and module:

```
sudo perf top -g  # or -C 0 for a single core
sudo perf record -a -g -- sleep 10 && sudo perf report
```

Here we can see the entries marked with `[k]`, together with their names. From
there we can investigate further. We can also check:

```
dmesg -T | tail -100
journalctl -k -p warning
```

There should be a warning there that points to the current problem.

An example of this problem from my own experience: a laptop battery that
reports to the Linux driver how much charge is left, from 0 to 100 percent.
Because it returned a negative value, the kernel module started using 100% CPU,
since it got stuck in a loop.
