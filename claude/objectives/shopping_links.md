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


SL-10.a The shopping site shall contain a toc starting with electronics, followed by other, threaded rods, screws bolts washers nuts 3d printed stuff. You shall be able to fold unfold each category (both at its header and at the toc).
sl-10.B The line "No shops listed yet for O07. Use “Add your own” below." shall be replaced with a single icon (on the same line as the description and image). 
SL-10.C The alternatives dropdown shall be on the same line as the image as a dropdown.
SL-10.D The "Add your own EAN" shall be on the same line as the image.
SL-10.E 1 article/item shall just consume one line with all its features, at most the height of its thumbnail (so that it is a way shorter to scroll page).
SL-10.F The TOC shall be in the bottom left just like all the other TOCs of the page.
SL-10.G Each item, including e.g. E01, shall have its price at the right side of the line or a - if no price for the article has been found yet.
sl-10.H The shop shall be a dropdown (with price  and availablility and shipping duration and costs besides it, if that data is available).
SL-10.I A toggle shall be available on top to toggle: show all shops (which shows all shops, along with the price and shipping costs (and availability/shipping duration)) per item.
SL-10.J Each per-shop row in the "show all shops" list shall show a price placeholder when no price has been captured, matching the placeholder shown on the item's main row (instead of words like "Quote").
SL-10.K The user shall be able to set the price of an item at a specific shop (e.g. the bol.com price of E02) by double-clicking the price placeholder/value. This shall work both on the item's main row (for the shop currently selected in the dropdown) and on each per-shop row in the "show all shops" list (for that specific shop). The entered price persists in the user's browser and is treated as a manual observation.
SL-10.L There shall be no separate "Your override" row or option. Editing the price for a shop happens inline on the item's row for whichever shop is currently picked in the dropdown — selecting bol.com and editing the price sets the bol.com price for that item.
SL-10.M Each item shall consume exactly one row regardless of how many shops it has; the shop dropdown cycles through the shops slot-machine style (one shop's data visible on the row at a time). Switching to a different item shows that item's own set of shops in its dropdown.
SL-10.N Directly below an item's row, the only bar that may appear is the "add an alternative" form (with EAN / product link / shop / price / ETA fields), triggered by a single add/edit icon on the row.
SL-10.O Next to the add-alternative icon there shall be a separate add-shop icon. Clicking it opens a distinct form (visually different from add-alternative so the user knows which they are doing) that adds a shop for the current item, asking only for URL, shop name, availability/ETA, cost, and shipping cost. Shop name, cost, and URL are required; availability and shipping cost are optional. The new shop becomes selectable in the item's shop dropdown.
SL-10.P The user shall be able to specify the EAN for each (item, shop) pair via a small EAN button on the item row. The button opens a popover with an editable EAN field, Save and Clear buttons, and a quick-copy button that writes the EAN to the clipboard. The user-entered EAN persists in the browser and overrides any seeded EAN for that shop entry.
SL-10.Q The alternatives dropdown shall be the item's name display on the row — no separate name span, and no "Alt" badge. The dropdown sits between the code and the qty, and its currently-selected option text is the visible product name (parent name when default, alt name when an alt is picked).
SL-10.R Each item row shall have one "Visit article" link whose target URL depends on the currently-selected item (parent or alt via the alts dropdown) and the currently-selected shop (via the shop dropdown). It opens the shop's product page in a new tab; when no URL exists for that (item, shop) pair the link is omitted.
SL-10.S Clicking the item-code button on the row (e.g. "E14") shall copy the currently-displayed product name (the alts dropdown's selected option text) to the clipboard, with a brief on-screen "Copied!" flash so the user can see the action took effect. The code badge is therefore an interactive button, not a static label.

