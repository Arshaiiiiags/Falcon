# Visual assets

All runtime assets are bundled locally in public/. No third-party image host or web-font service is needed while using the app.

| File | Purpose | Origin |
| --- | --- | --- |
| club-art.png | Lobby hero and backgammon cover | Original artwork generated with the built-in image generation tool for this project |
| card-*.webp | All 52 playable card faces and the Pasur cover fan | AustinGabriel CC0 illustrated deck; source commit in card-source.json; license in licenses/CARD-ASSET-LICENSE.txt |
| card-back-raster.webp | Detailed blue card back | Same CC0 deck |
| table-cloth.webp | Lobby cover and playable felt table | ambientCG Fabric075, CC0, photometric stereo material |
| board-wood.webp | Board, point inlays, rail and sidebar | ambientCG Wood049, CC0, procedural wood material |
| checker-ivory.webp, checker-ebony.webp | Playable checker sprites | Original transparent bitmap assets generated for this project |
| icon.svg | Club emblem and favicon | Original project SVG |
| icon-192.png, icon-512.png | Installable app icons | Rendered directly from the original SVG emblem in Chromium |
| icons.js | Interface symbols | Original inline SVG paths |
| games.js and style.css | Board geometry, dice and interface | Server state determines all positions and card identities; cards and checkers use the raster assets above |
| club-font.ttf | Local Persian/Latin typeface, Vazirmatn | The Vazirmatn Project Authors; SIL Open Font License 1.1, reproduced in licenses/FONT-LICENSE.txt |

Font source: [Google Fonts Vazirmatn](https://github.com/google/fonts/tree/main/ofl/vazirmatn). Font license: [FONT-LICENSE.txt](licenses/FONT-LICENSE.txt). The font has not been modified.

## Final artwork prompt

Mode: **built-in image generation**, not the CLI/API fallback. The generated image was copied into the project as `club-art.png`; the running app does not reference the generator's storage location.

> Use case: stylized-concept. Asset type: original artwork for a Persian card and backgammon game club web app, wide landscape 3:2 composition. Create a sophisticated editorial still life of a handcrafted Persian backgammon board with walnut and turquoise inlay, warm ivory and ebony checkers, two small ivory dice and a modest fan of ivory playing cards, on a deep midnight teal surface. Intricate restrained Persian geometric brass inlay, tactile wood grain and turquoise enamel, soft warm directional studio light, rich shadows, refined photorealistic 3D product photography. Arrange the board and playing objects toward the center-right with quieter dark teal negative space around edges so it crops well as website art. Color palette deep petrol teal, old gold, warm cream, walnut. It should feel like a real premium board game collection, calm and inviting, not a casino. No people, no lettering or words, no logos, no watermark, no UI, no buttons, no text, no chips, no money. This is a single finished scene intended for a real app asset.

The cover is decorative artwork. The playable board and cards are rendered from actual server state, with exact point and card identities.

## Raster upgrade — 2026-10-29

Deck: https://github.com/AustinGabriel/Public-Domain-and-CC0-Playing-Cards
Pinned commit: `3765067c32fcef42a30e87022332db729658e7cd`.
The publisher's PNG artwork is resized to 320px wide and encoded as WebP without changing the illustrations. The card back is 200px wide. Full deck, materials and checkers total approximately 1.43 MB. All runtime requests remain local.

Materials: https://ambientcg.com/view?id=Fabric075 and https://ambientcg.com/view?id=Wood049 . License: https://docs.ambientcg.com/license/ . Cloth uses photometric stereo; the wood is procedural, not a scanned photograph. Only the optimized runtime WebP exports (768px wide) are included in this source package. Unused original JPGs and retired SVG game artwork have been omitted.

Checker sprites were generated with the built-in image tool, transparent backgrounds, then copied into this project as 192px WebP exports preserving alpha. Source images remain in the generator's storage; the app uses only bundled exports.

Ivory prompt:
> A single premium backgammon checker made of warm antique ivory-colored resin, photorealistic product photograph directly overhead, exact orthographic top-down view of one round circular disk. Rich tactile polished material, softly beveled rim, shallow concentric engraved ring and subtle marbling, light patina. The entire checker fits in the square image with very narrow empty margins, fills 90% of the width. Flat top completely visible, no side perspective, no tilted ellipse. Warm soft light from upper left, realistic slight contact shadow underneath the rim. Isolated on genuinely transparent background. No other objects, no text, no symbols, no hands, no board, no outlines, no illustration. It is a game sprite for a real playable backgammon board.

Walnut prompt:
> A single premium backgammon checker made of very dark polished walnut wood, photorealistic product photograph directly overhead, exact orthographic top-down view of one round circular disk. Rich tactile black-brown wood material with clearly visible fine woodgrain, softly beveled rim, shallow concentric turned ring, satin varnish and slight patina. The entire checker fits in the square image with very narrow empty margins, fills 90% of the width. Flat top completely visible, no side perspective, no tilted ellipse. Warm soft light from upper left, realistic slight contact shadow underneath the rim. Isolated on genuinely transparent background. No other objects, no text, no symbols, no hands, no board, no outlines, no illustration. It is a game sprite for a real playable backgammon board.

## Hokm table

Hokm reuses the same licensed raster deck and bundled cloth/wood materials. Its four-ace lobby cover uses the existing card-SA, card-HA, card-CA and card-DA WebP files. No additional external assets or font requests are introduced.
