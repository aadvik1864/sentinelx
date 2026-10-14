# SentinelX

SentinelX is a security monitoring prototype for reviewing activity from Linux computers, websites, and apps. It brings recorded activity, alerts, and investigations into one shared workspace.

## Try the demo

**[Open the interactive demo](https://aadvik1864.github.io/sentinelx/)** — no sign-in or setup needed.

Search activity, review an alert, and open an investigation to explore its timeline and evidence graph. You can add practice notes or change a status. Choose **Reset demo** to start again.

All records are fictional. Changes stay in your browser tab and disappear on reload. The assistant provides offline sample explanations, not live AI responses, and never takes actions. No real systems are connected to this demo.

## Features

The full monitoring application supports:

- Live overview with activity totals, alert priorities, and 6/12/24-hour charts.
- Searchable activity with time, system, and priority filters.
- Rule-based alerts and customizable detection rules.
- Investigations with timelines, linked evidence, relationship graphs, notes, and assignments.
- Connection-health indicators and searchable connected-system lists.
- Optional assistant that explains evidence and suggests investigation steps without executing actions.
- Administrator, investigator, and read-only access, with two-step sign-in, passkeys, and account security setup.
- Responsive graphite-and-copper interface with keyboard navigation and reduced-motion support.
- Browser-only interactive showcase with fictional activity and resettable investigation practice.

## A few useful terms

- **Log:** a record of something that happened on a computer, website, or app.
- **Collector:** a small helper that sends logs from a system you have permission to monitor.
- **Detection rule:** a check for patterns in those records that should raise an alert.
- **Investigation:** related alerts, activity, and notes grouped together for review.

An alert means something needs checking; it does not prove an attack. This project is a prototype, not a guarantee that a system is safe.

See the [showcase guide](docs/showcase.md) for build instructions and demo limits. SentinelX's own code is [MIT licensed](LICENSE); adapted components retain their [original licenses and credits](frontend/public/third-party-notices.txt).
