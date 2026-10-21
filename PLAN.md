# Product development plan

Each round completes one feature or repair. Future items are planned, not implemented claims.

## Current round

sheet-metal-unfold-v1

## Roadmap

### sheet-metal-unfold-v1 — Sheet Metal Unfold Engine v1

Status: done

Acceptance:
- Detect constant thickness from parallel planar face pairs with opposite normals
- Identify bends from coaxial cylindrical face pairs with radius difference = thickness
- Compute bend allowance: BA = θ·(r + K·t) with configurable K-factor
- Generate flat profile via OCC union + kerf offset
- Output bend lines as open lines for DXF BEND layer
- Return per-bend records: angle, direction, radius, allowance, flange lengths, nearest cut/hole distance
- Refuse non-sheet solids, variable thickness, hems (r < t or sweep > 180°), conical bends, collisions
- Backend: 12+ pytest tests covering thickness vote, bend detection, allowance formula, volume conservation, refusals
- Frontend: STEP upload → unfold visualization → DXF download
- CI: backend pytest, frontend typecheck/build/test, Docker builds

Implementation: `backend/app/services/unfold_service.py`, `backend/app/api/unfold.py`, `backend/app/models/unfold.py`, `backend/tests/test_unfold.py`, `frontend/src/components/UnfoldWorkspace.tsx`, `frontend/src/api/client.ts`

Tests: `backend/tests/test_unfold.py`, `frontend/src/components/UnfoldWorkspace.test.tsx`

