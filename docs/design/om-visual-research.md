# Offering Memorandum Visual Research

Reviewed 2026-09-29 to inform the Kingdom Realty PDF template. The examples are references for generic hierarchy and page sequencing only; no source text, photography, or layout assets are reused.

## Primary OM Examples

- [2483-2491 Whitney Drive Development Offering Memorandum](https://danmcgue.com/wp-content/uploads/2018/09/2483-2491-Whitney-Drive-Development-OM.pdf), hosted by listing agent Daniel K. McGue / Paragon Commercial Brokerage and identifying CBRE on the cover. The 30-page document opens with broker/property identity, followed by disclosures and a contents page, then executive summary, property description, area/market, offering and investment pages. Its contents explicitly call out location maps, aerial view, property photos, pro forma, rent roll, comparable sales, and market/demographic appendix.
- [Lund Pointe Apartments Multifamily Offering Memorandum](https://www.neilwalter.com/wp-content/uploads/2016/02/Lund-PointeApts_OfferingMemorandum.pdf), hosted by Neil Walter Company. The 17-page document places a property/offer identity on its cover, then a contents page. The opportunity summary precedes a property facts table; unit mix, amenities, demographics, local/regional maps, aerial view, property photos, pro forma, rent roll, comparable sales, and market overview receive distinct labeled sections.

## Applied Design Practices

- Lead with the property name and a single large property/context image, then put concise offering facts in a high-contrast stat strip.
- Separate executive overview, asset facts, location/market evidence, operating assumptions, and returns into clearly numbered pages with consistent running headers and page folios.
- Keep tables scannable: explicit labels, aligned numeric columns, restrained banding, and enough breathing room to avoid turning financial pages into prose.
- Give maps, aerials, property photos, unit mix, pro forma, and comparables distinct section labels. When inputs are unavailable, mark images and narrative as illustrative rather than presenting invented deal evidence.
- Use an editorial serif for display headings and a highly legible sans serif for dense tables and disclosures; embed the font files so layout does not depend on a workstation's installed fonts.
- Use a light paper ground, dark ink, and limited secondary accents for emphasis rather than large flat placeholder panels.

## Asset and Renderer Sources

- [WeasyPrint API reference](https://doc.courtbouillon.org/weasyprint/stable/api_reference.html): `HTML(..., base_url=...)` resolves relative local asset URLs; Pango fonts are embedded in generated PDFs; `@font-face`, images, and paged-media headers/footers are supported.
- [Unsplash License](https://unsplash.com/license): Unsplash grants a worldwide license to download, copy, modify, distribute, and use images, including commercially; attribution is not required but is appreciated. Downloaded images in this project are clearly captioned as illustrative stock/mock imagery, not photos of the actual subject property or Kingdom Realty personnel.
- [IBM Plex Serif source and OFL](https://github.com/google/fonts/tree/main/ofl/ibmplexserif) and [IBM Plex Sans source and OFL](https://github.com/google/fonts/tree/main/ofl/ibmplexsans): font binaries and OFL 1.1 licenses are bundled beside the report assets for local embedding.