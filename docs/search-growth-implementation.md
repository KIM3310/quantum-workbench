# Search Growth Implementation - Quantum Workbench

This repository now exposes a search-readable service surface in addition to the system architecture. The implementation is designed to support organic discovery, AI answer surfaces, and a free-to-paid service path without committing to paid infrastructure first.

## Implemented Surface

| Surface | Path |
| --- | --- |
| Machine-readable offer | [docs/service-offer.json](./service-offer.json) |
| Revenue architecture | [docs/revenue-architecture.md](./revenue-architecture.md) |
| System architecture | [docs/system-architecture.md](./system-architecture.md) |
| Public canonical URL | https://kim3310.github.io/quantum-workbench/ |
| Lead capture URL | https://kim3310-doeon-kim-portfolio.pages.dev/?offer=quantum-workbench&inquiry=consumer-prototype-customization#private-inquiry |
| Repository resource route | https://kim3310-doeon-kim-portfolio.pages.dev/resources/quantum-workbench/ |
| Commercial route | https://kim3310-doeon-kim-portfolio.pages.dev/?offer=quantum-workbench#service-offers |

## Search Positioning

- Primary query: Quantum Workbench experiment provider adapters
- Secondary queries: Quantum Workbench demo; Quantum Workbench system architecture; Quantum Workbench educational tool; quantum experiment workbench with provider adapters, job inspection, and educational reports service
- Public entry point: free simulator-first demo and static architecture page
- Paid boundary: private prototype customization for simulator-first lab workspaces, course bundles, and provider-cost planning reports

## Conversion Boundary

The public surface stays crawlable and free. Paid value starts when a visitor wants private data, saved history, branded export packs, customer-specific connectors, recurring reports, or implementation support.

## Deployment Notes

- Keep the sitemap and robots file aligned with the final production domain.
- Submit the canonical URL and sitemap in Google Search Console after the domain is connected.
- The lead-capture path is the central private inquiry route for the `consumer-prototype-customization` lane; no self-serve checkout is configured.
- Public claims stay simulator-first. IBM Quantum and Braket hardware routes require provider credentials plus `QUANTUM_OPERATOR_TOKEN` and are not public hardware-access offers.
- Keep exact free-tier quotas out of public promises because provider limits change.
