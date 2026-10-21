# Changelog

## 1.0.0 — work-in-progress checkpoint

Partial code published for continued development. Known issues: STATUS.md.

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-21

### Added
- Sheet-metal unfold engine (`cadgen.unfold`) with deterministic geometric algorithm
- Thickness detection from parallel planar face pairs with opposite normals
- Bend detection from coaxial cylindrical face pairs (radius diff = thickness)
- Bend allowance calculation: K-factor formula `BA = θ·(r + K·t)` and bend table support
- Flat pattern generation via OCC Boolean union + kerf offset
- Bend line output for DXF BEND layer
- Per-bend records: angle, direction, inside radius, allowance, flange lengths, nearest cut distance
- Explicit refusals: non-sheet solids, variable thickness, hems, curls, conical bends, collisions
- FastAPI backend with `/api/unfold` endpoint (STEP upload → flat pattern + DXF)
- React + TypeScript + Vite frontend with drag-and-drop upload, SVG preview, bend details
- OIDC/Keycloak authentication with demo mode for local development
- Dockerfiles (backend/frontend) and docker-compose with Keycloak
- CI workflow: backend pytest, frontend typecheck/build/test, Docker builds
- Comprehensive test suite: 12+ backend tests, 3+ frontend tests
- Volume conservation validation (U-channel: 1.013 ratio)

### Security
- PKCE authorization code flow with state+nonce
- HttpOnly SameSite cookies with CSRF protection
- Demo mode binds localhost; refuses in production
- LLM keys server-side only; never logged
- File upload validation and size limits

### Documentation
- README with architecture diagram, API reference, AI/ML evaluation section
- Provider configuration table (OpenAI, LiteLLM, OpenRouter, Ollama, Anthropic, Gemini)
- SAML/Keycloak setup instructions
- MIT License