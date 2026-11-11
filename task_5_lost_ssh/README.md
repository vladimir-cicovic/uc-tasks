# task_5_lost_ssh

## Question

At 4 a.m. Friday night you get a call from NOC member that one of the servers
on one of the locations is reported as down and that he has tried to ssh over
public network to it but it just times out. Since this is one of the "more
important" servers you have to check it yourself. You know that there are other
servers at the same location and that they are all interconnected through a
switch in a "private" network which you can access. SSH is not bound to any
interface. What would be your troubleshooting steps? Explain what are you
checking and why. Try to come up with the most elaborate "fail scenario".
(there is no "right" answer)

## Answer

First, I will run ping to see whether the server is reachable from the outside.
If the ping command returns a reply, then we can assume that there is a problem
on the switch, between the switch and the server, or on the server itself.

The second step is to run
`ssh -J user@public-nearserver user@private-ip-problemserver` to see whether
ssh works on the problematic server. If it works, then the problem is the
switch, which is not doing NAT as it should - the configuration or the port on
the switch needs to be checked (this applies if ping did not work in the first
step).

If I cannot log in to the problematic ssh server through a server on the same
network, I will access that nearest server over SSH and create a tunnel to the
IPMI/iDRAC/console.

Commands:

```
ssh -N -L 8443:SSH_PROBLEMATIC_IDRAC_IP:443 user@public-nearserver
```

or

```
ssh -t user@public-nearserver ipmitool -I lanplus -H SSH_PROBLEMATIC_IDRAC_IP -U root chassis status
```

I open `https://localhost:8443` and access the Linux console.

I check the ssh service, check nft/iptables, and check the network card.

There I can also see when the last SSH login happened, which can point to
possible problems, e.g. a config change, an update, or something else.

I can check the tickets related to work on the server - which of my colleagues
last touched it or made changes.

Next, we check whether the network interface on the private network is
reachable (iDRAC is usually on a separate network and is not used to access the
server, but exclusively for problem analysis, installation and similar tasks).
We will use the tools: `ethtool`, `ip`.

For example, with ethtool we can see whether AUTO, FULL DUPLEX and similar
modes are set for the card, as well as the state of the drivers and firmware.

Commands:

- `sudo ethtool eno1` - "Link detected: yes/no", speed, duplex
- `sudo ethtool -S eno1` - detailed card statistics (CRC errors, etc.)
- `sudo ethtool -i eno1` - driver and firmware

Here we could find problems with the link, the speed, errors when sending
Ethernet packets, driver problems and so on.

Through the console I can see whether ping to the switch works and whether
packets from my machine reach SSH directly (I use `tcpdump` to monitor port
22/ssh on the problematic server). For example, if the packet arrives and the
server replies, we can assume that the problem is with the switch.
