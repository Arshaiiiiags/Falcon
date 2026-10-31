# Persian Game Club

<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
Persian and English speakers choosing a classic card or board game to play against AI, on desktop or mobile web. This audience description is inferred from the shipped functionality and the user's requests, rather than a separate audience interview.

## Product Purpose
A small game hub for Hokm, backgammon and Pasur. Let people choose a game, set AI difficulty, play, resume a saved match, and review results.

## Capabilities and Constraints
Flask/SQLite backend and framework-free JavaScript frontend. Games are server authoritative. Hokm is one human and three AI players, in two teams. Existing rules, security, accounting, saved games, APIs, five selectable themes, Persian/RTL and English/LTR must remain functional.

An account starts with 100 virtual coins. A whole match costs five coins. These are not real-money stakes. AI strength is not benchmarked as expert level. No networked human multiplayer is implemented.

## Brand Commitments
The user requested clean online web game hub styling, rejected generic AI-looking marketing UI, requested real graphical assets, and accepted Papergames/Poki/Lichess as useful reference directions before requesting this redesign. Keep the Persian Game Club name and bundled card, board, checker and font assets. The current request explicitly replaces the old frontend appearance.

## Evidence on Hand
Working game engines, existing API and browser suites, 52 CC0 card faces, card back, wood/cloth textures, generated board artwork and checker images. Asset provenance and licenses are in ASSETS.md and the *LICENSE.txt files.

## Product Principles
- Show the playable games before decorative content.
- Name actions plainly and keep progress recoverable.
- Preserve readable Persian and English layouts.
- Use actual game artwork; never fabricate player counts, testimonials or online availability.
