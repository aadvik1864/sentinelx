# Frontend interactions

SentinelX adapts four TypeScript components from [React Bits](https://reactbits.dev/get-started/index), using its copy-and-customize approach rather than a hosted runtime:

- [ShapeGrid](https://reactbits.dev/backgrounds/shape-grid): a restrained, reactive square grid on sign-in. Canvas resolution is capped, drawing is limited to 30 fps, and animation stops when offscreen, in a hidden tab, paused, or when reduced motion is requested. Unsupported canvas environments get a static CSS grid.
- [SpotlightCard](https://reactbits.dev/components/spotlight-card): a restrained pointer-driven highlight on the overview's review message. It does not add keyboard stops to a noninteractive card; interactive children retain their normal focus indicators.
- [CountUp](https://reactbits.dev/text-animations/count-up): brief transitions between real, server-provided metrics using Motion. Screen readers always receive the final number, not intermediate animation values. Reduced motion displays values immediately.
- [Stepper](https://reactbits.dev/components/stepper): short connection setup stages with controlled navigation, validation gates, a final review, focus management, and reduced-motion support. The one-time settings must be saved before proceeding; closing without them prompts a warning. Commands are instructions only and are never executed by the browser.

The forest-green surfaces, soft moss accents, warm light text, and IBM Plex typography stay consistent across sign-in, charts, tables, dialogs, and the evidence workspace. Priority colors remain distinct from the main accent. Motion is concentrated on sign-in, metric changes, and user-triggered step changes; investigation tables and timelines remain steady. The signal diagram on sign-in is illustrative, not a live feed.

These adaptations are in `frontend/src/components/react-bits/`. Their upstream source is the [React Bits repository](https://github.com/DavidHDev/react-bits). Copyright David Haz; **MIT + Commons Clause**, with the full notice in that directory's `LICENSE.md`. SentinelX's own code remains MIT; the adapted components retain their upstream terms.

The frontend build also ships these notices, together with Motion's MIT notices, at `/third-party-notices.txt`.

## Source setup and health

**Connected systems** is available to administrators and investigators (the API role is still `ANALYST`). Administrators can create a connection, select Linux/Nginx/Apache/application formats, download private source-only settings, pause collection, and explicitly confirm key replacement. Existing setup instructions never reveal stored keys or silently rotate them. File locations, heartbeat times, receipt counts, and technical errors are under **Connection details and settings**, instead of competing with each system's status.

The overview includes connection-health links, separate from the browser's **Live updates** indicator. **View activity** uses the connection ID, rather than only matching a hostname that multiple collectors might share. Setup copy explains server permissions, site-specific access logs, app JSON logging, and SSH/HTTPS connectivity. Pages and setup dialogs are checked for horizontal overflow at 320, 390, 760, and 1024 pixels; key replacement requires confirmation. See the [user guide](monitoring.md).

## A quieter workspace

The overview focuses on alerts to review, system connections, and recent activity. Less-used numbers are behind **More detail**. **Advanced tools** groups the device list, alert rules, and address checks. Original JSON, attack-pattern references, and manual imports remain available in expandable sections.

Display labels are centralized in `frontend/src/utils/labels.ts`; stored API values and permissions are unchanged. Critical/high/medium/low become **Urgent / Important / Moderate / Low priority**. Incidents are called **Investigations**. **Close investigation** records a decision; it does not fix a system. Assistant labels distinguish local generative AI, external AI, and deterministic offline summaries. Local output names its model and explains that selected evidence stays on the installation; configuration labels do not imply a successful readiness probe.

The sidebar's **How to use SentinelX** guide explains the workflow without requiring security terminology. Empty and disconnected states explain the next step instead of suggesting that a lack of alerts guarantees safety.

## Exploring without changing data

- The overview's totals link to activity, alerts, or investigations; read-only users do not get an activity link.
- The activity chart has native keyboard-accessible **6 / 12 / 24 hours** controls. It shows the selected recent hourly buckets and their sum; the overview totals keep their original 24-hour/persisted-state meaning. This does not change collection or imply every source is covered.
- **Connected systems** can be filtered by attention needed, recent receiving status, or paused state, and searched by system/computer name. Filters are stored in the URL, can be cleared, and never pause or modify a connection.
- **Go to** opens a page picker with **Ctrl/⌘ + K**. It searches page names, supports arrow keys/Enter/Escape, traps focus while open, restores focus when closed, and lists only pages available to the current role. It does not invoke assistant generation or execute actions.

Public previews: [overview](screenshots/overview-practice.png), [mobile overview](screenshots/overview-mobile.png), [investigation](screenshots/plain-language-investigation.png), and [sign-in](screenshots/login.png). Overview/investigation previews use browser-only practice data, not live records. Installation-specific captures and the older recording remain local and are excluded from Git.
