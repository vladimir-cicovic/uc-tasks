## Tasks

1. If we assume running some of the services causes "Too many open files"
   errors in logs write Ansible (preferred) or Puppet or Chef "playbook" which
   sets this limit to the higher value.

   Solution: branch `task_1_too_many`.

2. Create simple Python script which will fetch current IP geoip info from
   `http://www.geoplugin.net/json.gp?ip=<current_ip>` API and store it into
   SQLite database along with all geoip info that is available through API.
   Each record needs to be timestamped. Script has to loop and fetch results
   every minute. You have to use requests library in your script. You may not
   install requests as python global package. Script should be PEP8 compliant
   (or rather pass pylint check with flying colors).

   Solution: branch `task_2_geoip_loop`.

3. Package the said script into Docker container and ensure that script runs
   when container is started and that sqlite database is created on host
   machine (not inside the container). Bonus points for doing this with
   smallest possible docker image.

   Solution: branch `task_3_docker_sqlite`.

4. Given that you have complex time-critical high-traffic bare-metal
   java-powered infrastructure and also lighter virtualized services (cmdb,
   jenkins, nexus, gitlab, etc) describe your vision for monitoring,
   provisioning, de-provisioning, back-up-ing, hypervisor-ing, log collecting?
   This question is aimed more at technologies / products that you would use
   so giving a list of technologies and brief reason for them (1 or 2
   sentences per tech is enough). (there is no "right" answer)

   Solution: branch `task_4_infa_virtual`.
