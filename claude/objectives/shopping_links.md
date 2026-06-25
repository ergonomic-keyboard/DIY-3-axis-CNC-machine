SL-0.a You shall include (compact) links into the website where the user can buy the items.
SL-0.b. Per item you shall list the price per shop
SL-0.c. Per item you shall list whether it is available for shopping
SL-0.d. Per item if it is available for shipping you shall list in how many days.

SL-1.a You shall support different countries, however, start in the netherlands and only search for the links in the netherlands.
SL-1.b For each country you shall include different shops or shops that ship to the country.
SL-1.c You shall have one option all countries so the user can easily compare prices.

SL-2.a You shall allow the user to select which components it wants to buy (and only show/list the prices etc. of those items).
SL-2.b You shall automatically compute the costs of the combined order(s) including shipping, take into account free shipping thresholds.
SL-2.c You shall allow the user to override at which shop the purchase is done.
SL-2.d You shall allow the user to override separate items (with an ean or other exact specification (and at least 1 link to the product)).

SL-3.a The shop / price / availability / shipping data shall live as a static snapshot in the repo (YAML or JSON), so the site keeps working on GitHub Pages with no runtime backend.
SL-3.b The snapshot shall support both manual edits and an automated refresh path (e.g. a scheduled GitHub Action) — the schema must not assume one or the other.
SL-3.c The snapshot shall retain price history per item per shop (not just the latest price), so trends can be shown and used later. Each entry shall carry the timestamp it was captured at.
SL-3.d The UI shall surface the snapshot's last-updated time so users see how fresh the data is.

SL-4.a The shopping UI shall live on a dedicated "Shopping" page, separate from the Bill of Materials page. Existing thematic segregation of pages shall be preserved — do not bolt shopping data onto unrelated pages.

SL-5.a NL scope (first cut) shall cover at minimum: Conrad NL, Bol.com, and similar general/electronics marketplaces (e.g. Amazon.nl, AliExpress) where they carry the relevant items.
SL-5.b 3D-printed parts shall receive minimal coverage — include only 1–2 shops, and assume users will most likely source these from a friend rather than buy them. Do not over-invest in this category.
SL-5.c The data model shall not hardcode the shop list — new shops shall be addable by editing the snapshot, not the code.

SL-6.a The combined-order total (SL-2.b) shall be the sum of the user's per-item shop picks. Default pick per selected item shall be the cheapest in-stock shop; the user may override via SL-2.c.
SL-6.b Shipping shall be summed per shop, with each shop's free-shipping threshold applied to that shop's subtotal.
SL-6.c A "suggest cheapest mix" optimiser is explicitly out of scope for v1. The schema and UI shall leave room to add it later as an additional button, without restructuring the sum view.

SL-7.a Prices and totals in the NL view shall be displayed in EUR.
SL-7.b The schema shall nevertheless carry a `currency` field per shop (ISO-4217), so non-EUR shops (e.g. AliExpress in USD) and future non-EUR countries do not force a data-model change.

SL-8.a The shopping overview shall display the item image alongside each row, so the user can visually verify that the deeplink in the shop points at the correct article. The image source is the BOM image where one exists (single source of truth); when an item has no BOM image, the row shall degrade gracefully without breaking the layout.

SL-9.a An automated refresh path shall exist (scheduled GitHub Action) that attempts to fetch current price / stock / ETA per (item, shop) by parsing structured data (JSON-LD, Open Graph) on the linked product page, append a new observation when it succeeds, and leave the existing data intact when it fails.
SL-9.b The refresh shall be best-effort. Modern webshops are unreliable to scrape (anti-bot, CDN gating, JS-rendered pricing); shops that consistently fail shall be skipped without erroring the workflow, and the human reviewer shall fill those in manually via the existing snapshot.
SL-9.c The refresh shall open a pull request (never push directly to `main`), so the diff is reviewed before publishing.

SL-8.b The 3d printed parts will be at the bottom and deselected by default, the rest will be selected by default.
SL-8.c The site shall have a slider in top for thumbnail size.
SL-8.d The site shall have for each item the option to add an alternative item, the option to group alternative items (e.g. if you change the milling router, you will likely also have to change the milling router holder), these groups will be stored as separate configurations that are selectable on top.
SL-8.e For each item, and for each alternative item:one shall be able to add shoplink manually and add alternative product, both will have all questions on a single line (instead of Shop name / label
Product link
EAN (optional)
Price (EUR)
ETA (days)
distributed over multiple rows)
SL-8.f  For each item, and for each alternative item: it shall be clear whether the price was fetched automatically or manually (and when it was fetched (and a small graph shall pop up with historic price points if hovered over some icon)).
SL-8.g For each item, and for each alternative item: if the price was fetched by a bot, it will indicate which bot got the price, and if multiple bots got different values it shall indicate which bot got which price.
SL-8.h If a bot is not able to get the price of an article but is able to find the article, it shall provide the suggestion for the partially filled fields for the items (and ask the user to complete/correct them).
SL-8.i The user shall be able to click "validate" on a bot article dataset (link, price ean etc.).
SL-8.j The website shall be vimium friendly.

SL-9.d The top of the shopping page shall contain controls to manually run the price-fetching bots — one button per bot, each annotated with a suggested timeout / cooldown to prevent API rate-limiting. This local-trigger path is complementary to the scheduled SL-9.a action: a user running the site locally shall be able to fetch new prices and persist updates to `prices.json` without depending on the CI runner.
SL-9.e A "bot" is one fetcher per shop (e.g. `tinytronics-bot`, `conrad-bot`, `bol-bot`, `123-3d-bot`). Each observation a bot writes shall record the fetching technique it used (`jsonld` | `opengraph` | `affiliate-api` | `manual`) as a sub-field of the observation, so SL-8.f / SL-8.g can show which technique produced which value when multiple techniques are tried or multiple bots disagree.
