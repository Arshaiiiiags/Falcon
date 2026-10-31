---
name: Persian Game Club
description: A compact bilingual hub for classic card and board games.
colors:
  primary: "#17644f"
  background: "#f6f7f8"
  surface: "#ffffff"
  ink: "#20282d"
  muted: "#626c74"
  line: "#dde2e5"
  selected: "#e8f2ed"
  gold: "#83652b"
  danger: "#aa333b"
  purple-primary: "#61447d"
  purple-selected: "#f0eaf5"
  turquoise-primary: "#126c70"
  turquoise-selected: "#e5f1f2"
  ivory-background: "#f7f5ef"
  ivory-surface: "#fffefb"
  ivory-primary: "#72542c"
  ivory-selected: "#f1eadc"
  ivory-line: "#e1dcd2"
  dark-background: "#181d22"
  dark-surface: "#22292f"
  dark-sidebar: "#1e242a"
  dark-ink: "#edf1f4"
  dark-muted: "#b2bec6"
  dark-line: "#3e4952"
  dark-primary: "#30785e"
  dark-primary-ink: "#a1dfc3"
  dark-selected: "#2c4038"
  dark-gold: "#dfc17f"
typography:
  headline:
    fontFamily: "Club, Arial, sans-serif"
    fontSize: "32px"
    fontWeight: 750
    lineHeight: 1.35
    letterSpacing: "-.025em"
  title:
    fontFamily: "Club, Arial, sans-serif"
    fontSize: "21px"
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: "-.025em"
  game-title:
    fontFamily: "Club, Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 750
    lineHeight: 1.35
    letterSpacing: "-.025em"
  body:
    fontFamily: "Club, Arial, sans-serif"
    fontSize: "15px"
    lineHeight: 1.7
  label:
    fontFamily: "Club, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.7
rounded:
  control: "7px"
  field: "8px"
  panel: "12px"
spacing:
  control-gap: "8px"
  tile-gap: "22px"
  panel-padding: "24px"
  desktop-gutter: "36px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "10px 17px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "10px 17px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "10px 12px"
  navigation-active:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.primary}"
    rounded: "{rounded.control}"
    padding: "10px 13px"
  badge:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.primary}"
    padding: "4px 9px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "24px"
---

# Design System: Persian Game Club

## Overview

**Creative North Star: "The Game Club"**

A clean, compact game hub with a permanent desktop sidebar, quiet account toolbar and artwork-led collection. The user selected Papergames, Poki and Lichess as useful reference directions. Real game materials give the interface its character; surrounding chrome stays restrained.

This is the implemented replacement system, October 29, 2026, in Operate mode. It was built directly in HTML, CSS and JavaScript from the user's selected direction. The three games lead the home view without a marketing hero.

**Key Characteristics:**
- Compact navigation and direct play actions.
- Real raster card, board and checker assets.
- Five persistent themes with readable Persian and English layouts.
- Flat hub surfaces surrounding tactile game materials.

## Colors

### Primary
The default primary is deep club green. It fills play and account actions; the pale selected color supports navigation and state feedback. Primary ink follows the accent in light themes and becomes a lighter green in dark mode.

### Secondary
Gold marks coins, selected theme controls and some game states. Danger marks destructive actions and form errors. Card-suit red and physical board colors remain gameplay materials rather than theme accents.

### Neutral
Cool pale gray surrounds white hub surfaces, with charcoal text, muted slate supporting text and fine gray borders. The dark theme separates background, surface and sidebar tones. Ivory warms the background and borders; purple and turquoise change primary and selected colors.

The five stored identifiers remain `royal-gold` (default), `midnight-purple`, `persian-turquoise`, `dark-minimal` and `light-ivory`. Their actual overrides are recorded in the frontmatter and implemented in `style.css`; the existing settings swatch illustrations are not the authoritative palette.

**The Material Boundary Rule.** Theme colors govern the hub and controls; physical cards, cloth, wood and checkers keep their own material colors.

## Typography

The locally bundled Vazirmatn face is registered as Club, with Arial and sans-serif fallbacks. One family supports both Persian and English. Headings use a compact line height and slight negative tracking; body copy has generous leading for bilingual reading.

The frontmatter records the desktop headline, section title, game title, base body and control label roles. Supporting text is generally 13–14px, and metadata 11–12px. Navigation is 14px. The brand subcaption stays at 11px across breakpoints; sidebar help is 12px. Game titles reduce to 19px on tablet, returning to 22px on mobile; page headings reduce to 26px on mobile and 24px below 371px. Scores, balances and history use tabular numerals where implemented. Physical suit symbols retain their gameplay typography.

## Layout

Desktop uses a 212px sticky sidebar and a flexible content column. The toolbar is 76px high. Main content has 36px gutters and a maximum width of 1440px. Three equal game columns have 22px gaps; artwork and actions occupy separate regions. The collection order is Hokm, backgammon, Pasur, followed by saved-match content and a compact rules entry.

From 701px through 1150px, the sidebar becomes 188px, main and toolbar gutters become 24px, tile gaps 14px, artwork height 190px and tile-body padding 15px. Settings and rules become one column at 900px and below.

At 700px and below, the sidebar becomes a 244px overlay drawer, the toolbar is 66px, and games become one column. Main gutters are 18px, reducing to 12px below 371px. Onboarding and help stack. Cards use 210px artwork height, reducing to 195px below 371px; desktop artwork is 235px, rising to 270px from 1600px.

Logical spacing and borders mirror navigation in Persian. Physical board seating, card orientation and score order retain explicit LTR behavior. The implementation is exercised at widths 320, 390, 768, 1024 and 1440 in both locales; the wide-screen media query above is code-derived.

## Elevation & Depth

Hub panels and collection tiles rest flat with fine borders. Tile hover and focus-within change the border color rather than adding an outer shadow. Raster card fans carry a soft material shadow; game boards retain inset shading, textured cloth and wood. Dialogs use `0 20px 64px #0003` over a translucent backdrop without blur. A reusable shadow variable remains declared but is not the standard hub-card treatment.

State feedback uses short transitions: buttons change color over 160ms, tile borders over 180ms, and card fans move over 200ms. Reduced-motion preference disables animations and transitions. The mobile drawer animates only when opening.

## Shapes

Hub panels, tiles and dialogs use the panel radius; buttons and navigation use the control radius. Fields retain their own slightly softer radius. A one-pixel border defines most hub containers. Game tiles clip their artwork. Physical cards use small rounded corners; Hokm's table has broader rounded corners, reducing on mobile. These material shapes should not be generalized to ordinary forms.

## Components

### Buttons
Filled primary actions use the theme accent and white text. Secondary actions use the surface and border; text actions use accent ink. Standard buttons are at least 44px high, with 10px by 17px padding. Compact `.small` actions are 40px high. Primary hover darkens through a brightness filter; secondary hover uses the selected fill; active buttons move down one pixel. Disabled controls reduce opacity.

### Inputs / Fields
Inputs and selects use the surface, foreground and fine border, with 10px by 12px padding and a minimum height of 44px. Focus changes the border to the accent. Interactive controls and summaries use a 3px accent-ink focus outline with 3px offset. The scrollable history wrapper retains its gold focus outline.

### Navigation
Desktop navigation combines inline SVG icons with 14px labels. Active rows use the selected fill and accent ink; hover uses the page background. The compact profile sits at the sidebar foot. The mobile menu button opens the mirrored drawer and backdrop. Language remains visible in the mobile toolbar; appearance is available through settings.

### Badges
Small textual status badges use selected fill and accent ink, a 6px radius and compact padding. Loss uses a dedicated pale-red treatment. Use words alongside color for states.

### Cards / Containers
Hub panels use 24px padding. Collection tiles split fixed-height artwork from a padded body: desktop body padding is 21px, mobile 19px. Their full-width play action names the game. Descriptions use `text-wrap: pretty` to reduce awkward final lines where supported. Hokm shows four raster aces on a warm field; Pasur shows illustrated raster faces on a cool field; backgammon uses bundled board artwork. A small fan movement provides hover feedback. Artwork is decorative when the adjacent title and action identify the game.

### Dialogs and Game Materials
Play opens registration for guests and setup for signed-in players. Dialogs are native, scroll within a 90dvh maximum, and stay within the viewport. Preserve existing event and API contracts. Gameplay uses actual raster cards, board wood, cloth and checkers; selected cards rise and gain an outline. Physical game geometry remains separate from the responsive hub grid.

## Do's and Don'ts

### Do:
- **Do** show playable games before decorative content.
- **Do** use bundled real game artwork and the local bilingual font.
- **Do** preserve all five theme identifiers, both locale directions and visible keyboard focus.
- **Do** keep physical table geometry separate from mirrored navigation.

### Don't:
- **Don't** add a marketing hero, faux activity, fabricated player counts or decorative dashboard metrics.
- **Don't** turn the hub into wood wallpaper; reserve texture for actual game materials.
- **Don't** describe unbenchmarked AI strength as expert or imply human multiplayer.
