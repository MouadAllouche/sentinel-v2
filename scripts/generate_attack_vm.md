# Generating real SSH failures safely (documentation only)

This file describes a **manual** procedure for a throwaway virtual machine you own. Sentinel never
runs it, never automates it, and never connects to another host. Do not use it on shared or
production systems.

1. Create a disposable VM with a fresh OS install and no real accounts or data.
2. Start only the SSH service. Set a strong password for a single test account.
3. From a second disposable machine on the private network, run a few failed SSH logins with an
   incorrect password, then one successful login. Ten to thirty failures over a minute is enough.
4. Optionally run `sudo -v` and `visudo` on the VM to generate sudo events, and change the
   permissions of a **copy** of a configuration file to generate drift evidence.
5. Point Sentinel's `[paths] auth_log` at that VM's exported auth log copy, and its drift monitor at
   exported copies of the changed files. Never point it at a production host.
6. Run `python cli.py collect` and `python cli.py analyze`, then inspect the dashboard. Destroy the
   VM when finished.

Expected evidence: `failed_login` events, a `successful_login`, a `sudo_command`, a `config_drift`
event, a threshold finding with its tier, an incident with a timeline, and a risk score with
explicit reasons. The wording is always "possible" or "suspicious" — a pattern is not proof of a
single actor.
