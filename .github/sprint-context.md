# Current Sprint context

## Completed Sprints
- Sprint 0: INFRA-01, BE-01 ✓
- Sprint 1: BE-02, BE-03, BE-04, DS-01 ✓

## Current Sprint focus
Sprint 2 — BE-05: File notify → upload endpoints

## Decisions taken from Sprint 1
- PathResolver: stub con TODO, non hardcodare logica path
- JWT RS256 keypair generata a startup in backend/app/core/security.py
- bcrypt in asyncio.to_thread confermato
- Token blacklist in Redis: key pattern blacklist:{jti}

## Open stub
- YAMLRecycler: no-op stub in backend/app/services/yaml_recycler.py
- §8.5 folder naming: PathResolver interface con TODO
- LDAP: stub in backend/app/core/security.py