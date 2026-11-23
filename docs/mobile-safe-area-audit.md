# Mobile reader and safe-area audit

Date: 2026-11-23

## Changes

The recipe reader uses one format selector: PDF, Images, and Text when available. At the beginning of a PDF/Text scroll area, the selector has icons and labels. Once it scrolls out of that area, a smaller fixed pill keeps the same choices available. The fixed version does not alter the reading layout. Images keep their expanded selector; image swipes and annotation gestures do not collapse it.

Text availability still comes from the existing AI-or-saved-text policy. AI review remains in Actions and existing review entry points. PDF repair moved into Actions. Download and project start details remain in Actions and Status respectively. No API, database, or saved-progress format changes are required.

The recipe mobile breakpoint now matches AppShell: below 900px. Inspection and browser checks found that 769–899px previously combined desktop recipe rows with mobile app navigation. This severely reduced landscape phone reading height. Desktop controls remain at 900px and above.

## Safe-area ownership

Shared values in src/safeAreas.css use WebKit's safe-area-inset-* environment variables, with zero fallbacks. No iPhone model table or fixed notch height is used. Insets respond to viewport/orientation changes; viewport-fit=cover is retained.

| Surface reviewed | Finding and treatment |
| --- | --- |
| Home | Existing top inset retained; add side protection. |
| Recipe/yarn libraries | Protect initial content and sticky controls; retain the existing inset-aware floating search pill. |
| Inventory and Statistics | Protect initial top content and side edges. |
| Settings, Help, Yarn viewer | Add page-owned insets and protect the sticky yarn image. |
| Login and first-admin setup | Shared login layout protects all four edges. |
| Recipe PDF, Images, Text | One height budget includes the top safe area and bottom app navigation; fitted images also reserve editing/thumbnail trays. |
| AI review | Retain existing inset-aware fixed controls and footer; remove duplicate top padding inside the already-inset review image pane. |
| Reader focus mode | Protect the fullscreen content and sticky reader controls, including section-navigation offsets. Suppress the floating recipe selector. |
| Knitting tools | Panel owns its outer insets; remove repeated header/tool-body inset padding. |
| Shared edit/delete/status/crop/upload/repair/reorder dialogs | Constrain the dialog viewport to safe top/bottom bounds; keep controls scrollable. |
| Import/help, feedback, announcement, taxonomy, image adjustment, branding crop | Protect overlay bounds and cap modal height; make long announcements/crop panels scrollable. |
| App menu and bottom navigation | Existing safe-area rules retained. |
| Wide layouts and fullscreen | Preserve desktop design; inset the shell/sidebar and independently positioned fullscreen readers when nonzero hardware insets are reported. |

## Verification

From app/frontend:

- npm run test:viewer — availability, state mapping, reader policy, and saved-position tests.
- npm run validate:locales — all six message dictionaries.
- npm run build — production bundle.
- npx playwright install chromium, then npm run test:viewer:browser — isolated RecipeViewer with mocked API responses; starts and stops its own local Vite server on port 5179.

Browser coverage includes widths 320, 375, 390, 430, 768, 844, 899, and 900px; synthetic top/side insets; expanded/compact transitions; direct PDF/Text/Images selection; image fullscreen; format/AI/text combinations; all six languages in light and dark themes. The fixtures contain synthetic pattern pages and never use household recipe data. QA_SCREENSHOT can optionally name a local screenshot output.

Other screens received a source/layout audit; the isolated viewer test does not exercise every application workflow. Chromium inset simulation is not physical iPhone PWA validation. Final device acceptance should check installed-PWA cold launch, resume, portrait/landscape rotation, Safari browser chrome, focus mode, AI review, tools, and tall dialogs on a notched/Dynamic Island iPhone and a device without a cutout.
