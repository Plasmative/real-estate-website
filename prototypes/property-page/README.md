https://claude.ai/artifact/8nuttA8wKFPcqJB911gNbC
# Property page prototype

Property detail page for a land listing: gallery, key facts, description, land and infrastructure details, legal documents, location, inquiry form and similar listings.

| | |
| --- | --- |
| **Version** | v0.1 |
| **Status** | Draft: not yet approved by the client |
| **Approved by** | [Client name], [date], in [Client Session link] |
| **Design system** | Low Fidelity Prototype Design System, release v0.3.0 |
| **Fidelity** | Low: greyscale on purpose, so reviews focus on structure and flow, not colour |

## How to open it

Open `index.html` in any browser. Everything it needs is in this folder; only the Inter font loads from Google Fonts.

## Sample data

The property, price, distances and figures are **fictional**, for prototyping only. `[Brand name]` and `[Agent name]` are placeholders until discovery with the owner. Items marked `[to be confirmed]` need real data.

## What the developer can reuse

- **Reuse:** the content and copy, the section order, the component names (`Button`, `TextField`, `Badge`, `LanguageSwitch`, `PropertyCard`) and the design tokens (colours, spacing, radius, type scale) in `ds/tokens.json`.
- **Your call:** layout implementation, markup, styling approach, framework and architecture. The inline styles here exist only to make the prototype quick to build and edit.

## Folder contents

```
property-page/
├── index.html     The prototype
├── ds/            Copy of the design system used (tokens, component styles and scripts)
└── vendor/        React 18, bundled so the prototype works offline
```
