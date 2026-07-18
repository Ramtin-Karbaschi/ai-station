# Portability Policy

## Supported contract

AI Station is portable at the repository and Docker Compose level, while using
a canonical installed application root:

~~~text
/opt/ai-station
~~~

Persistent data is stored separately:

~~~text
/srv/ai-station
~~~

This is an intentional installation contract, not arbitrary-path portability.

## Compose portability

The active Compose chain is repository-relative:

~~~text
COMPOSE_FILE=compose.yml:compose.hardening.yaml:compose.local-builds.yaml:compose.images.lock.yaml
~~~

Relative paths are resolved from the repository base.

## Repository exclusions

The following must never be committed:

- `.env`;
- secret values;
- model binaries;
- database files;
- Docker volume exports;
- backups;
- generated logs;
- uploads;
- Hugging Face caches;
- support bundles;
- timestamped archives.

## Canonical path allowlist

References to `/opt/ai-station` are allowed only in files that intentionally
define:

- installation;
- operations;
- local launchers;
- service definitions;
- diagnostics;
- current-state documentation.

Approved files are listed in:

~~~text
config/release-path-allowlist.txt
~~~

Any new canonical-path occurrence outside that list must be reviewed.

## Portable installer expectation

A clone may exist in an arbitrary temporary directory.

The supported installer must:

1. validate the source;
2. deploy application files into `/opt/ai-station`;
3. preserve `.env`;
4. preserve persistent data outside Git;
5. avoid embedding the temporary clone path into generated files;
6. complete the release verification after installation.

## Portability limitations

Portability does not imply that:

- the default model fits every GPU;
- Docker or NVIDIA drivers are installed automatically;
- native Windows execution is supported;
- the system is safe for direct internet exposure;
- all Linux distributions are equally supported.
