# Operating a local workspace

## Database location

By default, the CLI uses `instance/slotharbor.sqlite` relative to the working folder.
Use the global `--database` argument **before** the command to choose another file:

```powershell
.\.venv\Scripts\python.exe -m slotharbor --database C:\SlotHarborData\workspace.sqlite init
.\.venv\Scripts\python.exe -m slotharbor --database C:\SlotHarborData\workspace.sqlite serve
```

The web factory also accepts `SLOTHARBOR_DATABASE` when no explicit path is supplied.
The CLI always passes its explicit/default path. Do not rely on that environment
variable to override the CLI's `--database` setting.

Schema version 1 is initialized idempotently. There is no destructive reset command.
Future schema revisions require an explicit migration and backup procedure; no
unreleased upgrade path is claimed here.

## Create another account

Use the Team page, or run the local command with an existing administrator:

```powershell
.\.venv\Scripts\python.exe -m slotharbor create-user --username coordinator --role coordinator --actor owner
```

The CLI assumes the person running it has authorized operating-system access to
the database. It is not a substitute for filesystem access control.

## Recover access

```powershell
.\.venv\Scripts\python.exe -m slotharbor reset-password --username owner
```

This prompts for a replacement password and invalidates every existing session for
that account. It does not reactivate a disabled account or change its role. The
last active administrator cannot be disabled through supported application actions.

## Back up while the application is running

```powershell
.\.venv\Scripts\python.exe -m slotharbor backup C:\SlotHarborBackups\workspace-2026-10-03.sqlite
```

The command uses SQLite's online backup interface and runs an integrity check.
It refuses to overwrite an existing destination or the live database. Backup paths
are examples: choose a date and destination for your own installation.

A backup contains password hashes, team usernames, CSRF state and session digests.
Treat it as sensitive. Restrict file access and encrypt external storage. Backups,
SQLite files and the instance directory are excluded from Git by default.

## Restore carefully

Stop the server. Keep the current database and any associated `-wal` / `-shm` files
as a recovery set rather than deleting them. Copy the chosen verified backup to a
**new** directory and start with `--database` pointing to that file. Inspect resource
counts and several known reservations before making the restored copy authoritative.
Do not copy a live SQLite database file on its own instead of using the backup command.

## Network exposure

Loopback is the default. An intentional LAN or hosted setup needs a reviewed TLS
reverse proxy, explicit hostnames, secure cookies, firewall policy and backups.
Example settings for a hostname you control:

```powershell
$env:SLOTHARBOR_HOSTS = "schedule.example.internal"
$env:SLOTHARBOR_SECURE_COOKIE = "1"
.\.venv\Scripts\python.exe -m slotharbor serve --host 127.0.0.1 --port 8000
```

The example hostname is not a configured service. Preserve the original Host header
at the proxy. The default server command does not trust forwarded client headers.
Behind a proxy, login source throttling therefore sees the proxy address; account
throttling still applies. Configure additional proxy-level limits rather than
blindly trusting user-supplied forwarded headers.

`GET /health` returns a minimal health result. Access logging is disabled by the CLI
server command to avoid retaining unnecessary request metadata by default.

## Troubleshooting

A 403 form error usually means that the session changed, the token expired or a
new page was opened before another tab logged in/out. Reload the form. Keep a
reservation's request key when retrying an uncertain network result.

A 409 time conflict includes cleanup buffers and pending reservations, not just
confirmed session time. Check Maintenance and Approvals as well as Reservations.

An ambiguous local-time error requires an explicit first/second occurrence choice
under Clock-change options. A missing local time requires choosing a real time;
SlotHarbor will not guess which side of the change you intended.
