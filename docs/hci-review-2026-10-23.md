# Console HCI review — 23 October 2026

This review covers the nine console pages and the main read/write tasks. It
extends the earlier card review. It uses an isolated loopback fake API. It does
not operate the line, change supplier mappings, or change saved human results.
The sidebar, three write pages, native command/tank selectors, manual clear
controls and neutral Feedback card borders remain in place.

## Findings and changes

| Priority | Finding | Change and check |
| --- | --- | --- |
| High | A write-mode request can fail on a hidden Setpoints result, leaving no visible explanation on other pages. | A separate global alert shows the failure. Polling and canceled retries preserve it. Successful mode actions clear it. A failed disable still locks local writes. |
| High | Catalog polling removes the focused Select button before keyboard activation. | Value/health polls update cells in place. Filter or metadata changes still rebuild the rows. Each Select action names its signal. |
| High | Feedback Run can be disabled while the general write gate says writes are available. | The selected pair explains the blocker and next action. Row Run buttons have the same tooltip and accessible description. Existing gates are unchanged. |
| Medium | Page changes leave keyboard focus in the sidebar. The active route can also be outside the narrow navigation viewport. | Route changes focus the new heading. A Skip to content link bypasses repeated navigation. Narrow navigation reveals the active link. Scroll padding follows the sticky header height. |
| Medium | Catalog filters, log filter and batch JSON lack accessible names. The write dialog has no programmatic name. | All affected controls have names. The dialog references its title and equipment warning. Cancel still sends no command and restores focus. |
| Medium | Some status text and input-focus colors have low contrast. | Existing blue, amber and red palette colors were adjusted as measured below. Pass/Fail labels retain their text and icons. |
| Medium | Repeated assignment of unchanged human/API status text can cause unnecessary live-region mutations. | The shared text helper and human-result renderers keep identical text nodes. Timers remain outside live announcements. |
| Medium | A long expanded catalog-warning block can bury Overview workflow links. | A warning count opens the complete details. Polling preserves the user's expanded state. No warning is removed. |
| Low | Manual empty states say Value write, while the sidebar says Setpoints & batch. Setpoints mapping labels differ from Feedback. | Page names now match the sidebar. Mapping guidance uses Local pair / Mapping under test. API result enums remain unchanged. |

These priorities describe usability impact in this console. They do not assign
machine safety integrity or establish supplier operating procedures. The general
write gate does not guarantee that a particular test can start or that equipment
permissives are satisfied.

## Palette measurements

The calculation uses relative sRGB luminance. The W3C guidance requires at least
4.5:1 for ordinary text and 3:1 for relevant non-text state cues. See
[Contrast (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
and [Non-text Contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html).
Values below are rounded for display. Checks use the unrounded values.

| Element | Before | After | New foreground / background |
| --- | ---: | ---: | --- |
| Input focus on white | 2.17:1 | 7.30:1 | #155d7a / #ffffff |
| Amber status | 3.94:1 | 6.58:1 | #7a4b00 / #fff0d2 |
| Red status | 4.35:1 | 5.93:1 | #a52c32 / #fce8e5 |
| Locked gate | 4.37:1 | 5.95:1 | #a52c32 / #fbe9e6 |
| Neutral status | 4.19:1 | 6.28:1 | #475569 / #e4ebee |
| Sidebar group label | 4.11:1 | 4.84:1 | #7d939b / #14262f |
| Pass label | 5.00:1 | 5.00:1 | #167653 / #e8f5f0 |
| Fail label | 6.30:1 | 6.30:1 | #a52c32 / #fff0ee |

The review also used W3C guidance for
[visible keyboard focus](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html),
[status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html),
[modal dialogs](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/), and
[target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).
Nielsen's [usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/)
informed the checks for visible state, consistent labels and error recovery.
This is an applied review, not formal WCAG certification.

## Evidence and limits

Firefox screenshots and browser measurements cover all nine routes at actual
CSS viewport widths of 1440, 1024 and 500 pixels. The final 27 route/width checks
found no page-width overflow and no unnamed visible form controls. All 362 tags,
141 writable signals, 102 Bool commands and 50 local pairs remain accessible.
Table and navigation scrolling remain intentional. Manual and Feedback use the
page scrollbar. Separate checks exercise errors, stale data, command readback 1,
conflicting attempts, human-result persistence, dialog cancellation and keyboard
selection. Browser interactions and new regression checks use mock/loopback APIs.

The local artifacts folder is
`api_test/artifacts/full-hci-review-2026-10-23/`. It contains before/after
screenshots, measured viewport metadata and contrast calculations. Preview data
is simulated. Screenshots are not evidence of physical operation or supplier
confirmation. Files named zoom use a separate 2x display-scale browser profile.
Measured CSS viewport sizes, rather than requested window sizes, define coverage.

The affected regression suite passed **126 tests in 213.62 seconds**. It includes
22 new checks for global mode errors, blocked-run guidance, catalog keyboard
access and navigation/status behavior. JavaScript module syntax checks and
`git diff --check` also passed. The full earlier 556-test run was not repeated.

Additional preview runs measured 640 and 720 CSS-pixel widths. Requested smaller
window sizes were clamped by Firefox. Keyboard zoom did not change the measured
CSS scale. These runs do not establish 320/360-pixel reflow or 200% page zoom.

The review does not include a screen-reader listening session, other browser
engines, operator testing at the equipment, or physical viewing-distance checks.
PLC operating sequence and missing physical feedback remain separate supplier
investigation items. This pass sends no real PLC commands and adds no automatic
reset, retry, mode enable or inferred feedback mapping.
