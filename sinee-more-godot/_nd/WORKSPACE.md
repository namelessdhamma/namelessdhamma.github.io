# Синее море — Godot Development Workspace

Status: CURRENT
Engine: Godot 4.7.2 Mono
Updated: 2026-09-25

## Authority
1. Google Drive Product StateHead is the upper product/content authority.
2. GitHub is the versioned implementation repository for Godot source.
3. Railway Direct MCP and GitHub Actions are execution/verification surfaces.
4. Linear is updated LAST after accepted state converges.
5. Ephemeral MCP writes are not durable until accepted source is persisted and verified.

## Current direction
Main game: cinematic narrative adventure, landscape 16:9.
Frontier: Pirate Sea opening.
Rhythm: authored cinematic scene -> rare decision -> authored reaction -> next scene.
No free 3D walking and no player-controlled camera.
D2 / 3×3 remains an in-world minigame and standalone Free Play component.

## Directory contract
- core/ — genuinely shared runtime primitives.
- campaign/pirate_sea/ — active opening implementation.
- minigames/d2/ — preserved D2 integration surface.
- ui/ — reusable choice/interface presentation.
- data/narrative/ — structured branching/dialogue/beat data.
- data/localization/ — localization data.
- assets/keyframes/, assets/video/, assets/audio/, assets/ui/ — runtime-ready derivatives.
- tests/smoke/, tests/regression/ — launch and behavior verification.
- tools/ — project-local developer utilities.
- _nd/ — agent workspace metadata; ignored by Godot importer.

## Agent loop
Recover current pointers -> inspect state.json -> read only relevant canon -> implement smallest coherent delta -> validate with Godot -> inspect live state/screenshots as needed -> persist accepted source -> update Drive when consequential -> Linear LAST.

Do not reconstruct canon from memory when current Drive authority exists.
Do not treat an ephemeral Railway edit as durable.
Do not create a second competing gameplay codebase.
Do not reorganize main.tscn only for cosmetic folder tidiness.
