# gap: drone-procurement

## Summary

ANSWER (as of 2026-10-07; my web-search budget ran out partway through, so a few points rest on one source and are flagged).

Recommendation: buy a DJI Mini 5 Pro (EU C0, 249.9 g with the standard battery, 1-inch 50 MP sensor, electronic rolling shutter). It costs about 8,700-9,500 SEK with the RC-N3 controller, or 10,400-13,400 SEK as the Fly More Combo with the RC 2. Fly it with DJI Fly's built-in waypoint mode. Each waypoint can take a photo, hover for a set time, and set its own gimbal pitch and heading, with up to 200 waypoints per mission (DJI). That covers a nadir grid, a 45-degree oblique grid in four directions and orbits at several radii, all shot hover-and-shoot. Missions are loaded as KMZ files. You can get them from Pixpro Waypoints (about EUR 5/month billed yearly, EUR 10 monthly, free 14-day trial), from Litchi Hub plus the free Litchi Hub Bridge, from Dronelink's onboard KMZ export, from WaypointMap, or for free by generating DJI WPML/KMZ files in your own Python pipeline. The pipeline option is my suggestion and is not vendor-verified. DJI's Mobile SDK v5.18.0 (May 2026) does not support the Mini 5 Pro, the Air 3S or the Avata 360. A Litchi forum thread suggests Mini 5 Pro SDK support might arrive around 2027, judging by how long earlier models took. Shoot in 12 MP binned mode, which allows a 2 s minimum interval (50 MP needs 5 s). Hover-and-shoot also cancels most rolling-shutter distortion; DJI does not publish readout times for these sensors.

Runner-up / alternatives:
(a) DJI Mini 4 Pro with the RC-N2 controller (C0, 1/1.3-inch 48 MP). It is the only consumer DJI model that the current SDK supports, so Litchi Pilot, Dronelink (Android, RC-N2 or RC-N3, sideloaded APK) and UgCS (via Litchi) can fly it. The catch is that it appears to be end-of-life in Sweden: listed at 7,849 SEK but sold out, and gone from two other Swedish shops.
(b) DJI Matrice 4E. Only worth it if a mechanical shutter, 0.5 s interval, built-in RTK and DJI Pilot 2's full mapping suite matter more than about 52-57k SEK. That is overkill for a 10x10 m hobby plot that is already tied in locally with shared targets.
(c) DJI Lito X1 (2026, about EUR 419, 1/1.3-inch 48 MP, 249 g). A budget option that supports DJI Fly waypoints and Pixpro.
Not recommended:
- Air 3S: needs the A1/A3 test because it is C1, has no SDK, and its only extra over the Mini 5 Pro is the 70 mm camera.
- Autel EVO II Pro RTK V3: EUR 2,999, C2, 1-inch 20 MP, mapping modes built into its app, but the vendor's support outlook is uncertain.
- Parrot ANAFI Ai: about EUR 5.2k incl. VAT; Parrot now focuses on defence and government.
- Antigravity A1: about 16.2k SEK, flown only with goggles (so it needs an observer), and has no waypoints.
DJI Avata 360 (C1, 455 g, 8K60 360 video and 120 MP 360 photos, flyable with a normal RC 2, about 8k SEK) is the only 360 drone worth an experiment, because it could reuse your Insta360 360-video pipeline. It is not on DJI's waypoint list.

Sweden, private hobby use:
- You must register as a drone operator (camera drone, age 18+): 190 SEK once, then 250 SEK per year (Transportstyrelsen).
- C0 drones need no competency test. C1 needs the A1/A3 online test (600 SEK, valid 5 years). C2 needs A2 as well, but only for A2-subcategory flights; A3 needs just A1/A3.
- Insurance: Transportstyrelsen says liability insurance is not required for leisure-only use of drones under 20 kg. Home insurance often excludes drone liability, so check your own policy. Svedea sells a private open-category liability policy (price not found; 1,400 SEK/yr was reported in 2018).
- Publishing aerial images: Lantmäteriet requires a dissemination permit (spridningstillstånd) before you share aerial photos or video publicly, including on a website. It is free and currently takes about 65 working days. Whether a Gaussian splat derived from drone photos counts is not stated, but assume it does.
- Some nature reserves and national parks need a takeoff/landing permit from the county board (Länsstyrelsen).
- Penalties for breaking the drone rules were increased on 1 Jan 2026.

EASA Opinion 06/2026 (published 18 Sept 2026, still awaiting Commission adoption, no application date yet): it lowers the weight at which registration and Direct Remote ID become mandatory from 250 g to 100 g. Authorities must verify operators' identity before registering them. A trade press report adds that new C0-C4 drones would have a launch lock (no takeoff without a valid operator ID), that drones already on the market would be exempt, and that weight tolerances of 2-3% would be written into the rules. It changes little for one buyer: you register anyway because of the camera, and C1 drones already broadcast Remote ID.

FCC Covered List: foreign-made drones and drone components, DJI included, were added on 22-23 Dec 2025. New models get no FCC authorisation (the Avata 360 and Lito are not sold in the US); models authorised earlier, including the Mini 5 Pro and Air 3S, stay legal. DJI asked the FCC to reconsider (21 Jan 2026) and petitioned the Ninth Circuit (20 Feb 2026); both are still pending. One source says the firmware-update permission runs to 1 Jan 2029. There is no legal effect in the EU: products, firmware and apps keep working. The indirect risk is that DJI and US third-party app makers put less effort into SDK support for new models, which is one reason not to rely on the SDK.

## Plan changes

- Aerial layer hardware: default to the DJI Mini 5 Pro (C0, RC-N3) instead of the Mini 4 Pro. Treat the Mini 4 Pro with RC-N2 as a fallback only if SDK-driven control is needed. Drop Parrot and the Antigravity A1. Keep the Matrice 4E as a 'not for hobby budget' reference.
- Pipeline: add a Python module that writes DJI WPML/KMZ missions (nadir grid, 4 x 45-degree obliques, orbits at several radii with hover-and-shoot), split to stay under the per-mission waypoint limit. Field-test whether that limit is 200 or 101.
- Capture protocol: use 12 MP binned mode with a 2 s interval and hover at each photo; fly 15-25 m above the canopy; place shared registration targets in canopy gaps or plot edges visible from both the air and the BLK2GO. Use ICP on canopy-top LiDAR points as a fallback.
- Phase 0 admin tasks: Transportstyrelsen operator registration (190 SEK + 250 SEK/yr), optional A1/A3 test (600 SEK), confirm liability insurance, check the site against nature-reserve and zone rules, and file a Lantmäteriet dissemination permit (about 65 working days) well before any public sharing of aerial-derived splats.
- Budget line: about 9-13k SEK for the drone plus batteries; software 0 SEK (own KMZ generator) or about EUR 5-10/month (Pixpro); UgCS Open is free if Circlegrammetry is wanted.
- Risk register: no SDK for Mini 5 Pro or Air 3S (it may arrive around 2027); EASA Opinion 06/2026 (100 g Remote ID/registration, launch lock) is pending adoption; FCC Covered List has no EU effect but may slow US third-party app support for new DJI models.

## Recommendations

- **Primary aerial drone: DJI Mini 5 Pro, standard RC-N3 bundle (about 8.7-9.5k SEK), plus 1-2 extra standard batteries (929 SEK each). Do not use Battery Plus if you want to stay C0.** — It has the largest sensor (1-inch 50 MP) in the C0 class, so no drönarkort is needed, and it fits in a pack for forest hikes and tropical trips. DJI Fly waypoints give per-waypoint photo, hover, gimbal and heading control, which is enough for grids, obliques and orbits with hover-and-shoot. Omnidirectional sensing plus forward LiDAR suits flying near trees. _Alt:_ DJI Lito X1 (about EUR 419) as a budget option with waypoint support. DJI Air 3S if the 70 mm camera or better wind handling matter (C1, so the A1/A3 test is needed).
- **Second choice: DJI Mini 4 Pro with RC-N2, bought used or from EU stock, only if you need SDK-driven missions (Litchi Pilot, Dronelink, UgCS via Litchi) on Android.** — It is the only consumer DJI drone the SDK supports today. The trade-offs are a smaller 1/1.3-inch sensor and apparent end-of-life in Swedish retail. _Alt:_ Matrice 4E (about 52-57k SEK) if a mechanical shutter, 0.5 s interval, RTK and DJI Pilot 2's full mapping suite become worth the cost.
- **Generate DJI Fly KMZ/WPML missions in the project's own Python pipeline: a nadir grid, 4 x 45-degree oblique grids and orbits at several radii, with 'take photo' plus hover at each waypoint, one mission per pattern. Load them by replacing a dummy mission (the method Litchi Hub Bridge uses). Use Pixpro (14-day trial) to cross-check.** — It costs nothing, keeps the capture geometry reproducible and in version control, and does not depend on SDK support for the Mini 5 Pro. _Alt:_ Pixpro Waypoints, Litchi Hub plus Bridge, Dronelink onboard KMZ export, WaypointMap.
- **Capture settings: 12 MP binned mode (2 s minimum interval), hover-and-shoot or at most about 2 m/s, fast shutter, and 15-25 m clearance above the canopy top.** — Shutter readout times are unpublished. Binned 12 MP gives better low-light SNR under Nordic overcast, and 50 MP quad-Bayer adds little real detail for splats while forcing a 5 s interval. _Alt:_ 50 MP for a few close nadir passes if detail tests justify it.
- **Admin before flying:
- Register as operator (190 SEK + 250 SEK/yr).
- Optionally take the A1/A3 test (600 SEK): not needed for C0, but it keeps C1 drones open.
- Check your home insurance for drone liability, or buy a private open-category liability policy (e.g. Svedea).
- Check nature-reserve rules and drone zones at the site.
- Apply to Lantmäteriet for a dissemination permit (free, about 65 working days) before publishing any aerial-derived splat.** — These are the legal requirements and the main risks for a private operator in Sweden. _Alt:_ Keep aerial layers private until the permit arrives.
- **Optional 360 experiment: DJI Avata 360 (C1, about 8k SEK with RC 2) rather than the Antigravity A1.** — It reuses your existing 360-video splat pipeline, flies with a normal controller, and has omnidirectional sensing plus LiDAR. The A1 is goggle-only (an observer is needed in the Open category), has no waypoints and costs about twice as much. _Alt:_ Skip 360 drones; perspective stills give higher per-pixel resolution for splats.

## Load-bearing findings

- [high] DJI Mini 5 Pro: EU C0 at 249.9 g (+/-4 g) with the standard battery. The Fly More Combo Plus (Battery Plus) is C1 and must not be flown as C0. Specs: 1-inch 50 MP CMOS, 24 mm f/1.8, electronic shutter; timed shots 2/3/5... s at 12 MP and 5/7/10... s at 50 MP; works with the RC-N3 and RC 2 only. — https://www.dji.com/mini-5-pro/specs https://dronexl.co/2025/09/23/easa-dji-mini-5-pro-c0-status-weight/ https://www.heliguy.com/blogs/knowledge-base/what-is-the-certification-level-of-the-dji-mini-5-pro-in-europe/
- [medium] DJI Fly waypoints: up to 200 waypoints per mission. Each waypoint can take a photo or start/stop recording, hover for a set time, and set its own gimbal pitch, heading and zoom; points of interest are supported. Supported models include Mini 5 Pro, Air 3/3S, Mavic 3/4 Pro and Lito X1; Mini 4 Pro also has waypoint flight. KML route import is not supported, so third-party missions arrive as replacement KMZ files. — https://support.dji.com/help/content?customId=en-us03400007343&spaceId=34&re=US&lang=en&documentType=artical&paperDocType=paper https://www.pix-pro.com/blog/waypoints-faq-2 https://www.pix-pro.com/blog/overlapping-orbits
- [high] DJI Mobile SDK v5.18.0 (released 2026-05-22) supports Mini 3, Mini 3 Pro, Mini 4 Pro, Mavic 3 Enterprise, Mavic 3TA, M30, M300, M350, the Matrice 4 series, M400 and H30. It does not support Air 3, Air 3S, Mini 5 Pro or Avata 360. — https://github.com/dji-sdk/Mobile-SDK-Android-V5 https://github.com/dji-sdk/Mobile-SDK-Android-V5/issues/692 https://forum.flylitchi.com/t/dji-released-the-api-for-mini-5-pro/28370
- [high] Mini 4 Pro third-party control through the SDK needs the RC-N2 (or RC-N3) and an Android phone; the RC 2 screen controller cannot run third-party apps. Apps: Litchi Pilot (separate from classic Litchi), Dronelink (sideloaded APK, not from Google Play) and UgCS (via KML into Litchi Pilot). — https://manuals-ugcs.sphengineering.com/docs/using-dji-mini-with-ugcs https://www.dronelink.com/supported-drones https://dronedj.com/2025/03/21/dji-mini-4-pro-msdk/
- [medium] DJI Mini 4 Pro: EU C0 at under 249 g; Battery Plus is not sold in Europe. Specs: 1/1.3-inch 48 MP, 24 mm f/1.7, electronic shutter; timed shots from 2 s at 12 MP and from 5 s at 48 MP; works with the RC-N2 and RC 2. The RC-N2 version looks end-of-life in Swedish retail. — https://www.dji.com/mini-4-pro/specs https://djistoresverige.se/en/products/dji-mini-4-pro https://dronarbutiken.se/collections/alla-produkter-dronare-dji-mini
- [medium] Mission-app costs: DJI Fly is free. Pixpro Waypoints is included with a Pixpro subscription (about EUR 5/month yearly, EUR 10 monthly, free 14-day trial) and supports Mavic 3, Air 3, Air 3S, Mini 4 Pro, Mini 5 Pro, Mavic 4 Pro and Lito X1. UgCS Open is free and includes Circlegrammetry; UgCS PRO is USD 109/month or USD 1,090 perpetual. PIX4Dcapture Pro has reached end of support. DJI Pilot 2 comes free with enterprise drones. — https://www.pix-pro.com/pixpro-waypoints https://www.pix-pro.com/blog/waypoints-faq-2 https://shop.sphengineering.com/pages/ugcs-license-types-pricing
- [high] Sweden, private operator: registration is mandatory for drones of 250 g or more, or any drone with a camera; private persons must be 18+ and resident in Sweden. Fees: 190 SEK application plus 250 SEK per year. C0: no drönarkort needed. C1-C4: the A1/A3 online test (600 SEK, 40 questions, 75% pass mark, valid 5 years). C2 in the A2 subcategory additionally needs the A2 CofC. — https://www.transportstyrelsen.se/sv/om-oss/avgifter/avgifter-inom-luftfart/obemannade-luftfartygssystem---dronare/dronaroperatorer/ https://www.transportstyrelsen.se/sv/luftfart/luftfartyg-och-luftvardighet/dronare/dronarflygguiden/ https://www.dronarlabbet.se/flyg-lagligt/registrering
- [high] Insurance: Transportstyrelsen says insurance is not required for operators who use drones under 20 kg for leisure only; other uses fall under EU Regulation 785/2004. Home insurance often does not cover drone liability. — https://www.transportstyrelsen.se/sv/luftfart/luftfartyg-och-luftvardighet/dronare/dronarflygguiden/ https://www.svedea.se/dronarforsakring https://swedron.se/blogg/aer-din-droenare-raett-foersaekrad
- [high] Lantmäteriet requires a dissemination permit (spridningstillstånd) before aerial photos, video or laser/elevation data of Swedish land are shared with others, including on websites and social media, whether or not the use is commercial. Applying is free; processing currently takes about 65 working days. — https://www.lantmateriet.se/sv/spridningstillstand/ https://www.lantmateriet.se/sv/spridningstillstand/vanliga-fragor/ https://www.transportstyrelsen.se/sv/luftfart/luftfartyg-och-luftvardighet/dronare/dronarflygguiden/

## Key numbers

- DJI Mini 5 Pro (RC-N3) Sweden price: 8,690-9,499 SEK (https://www.scandinavianphoto.se/dji/mini-5-pro-1103839 ; https://dronestore.se/dji-mini-5-pro)
- DJI Mini 5 Pro Fly More Combo (RC 2) Sweden: 10,359-13,399 SEK; Fly More Combo Plus (C1) 13,599 SEK (https://dronarbutiken.se/collections/alla-produkter-dronare-dji-mini)
- DJI Mini 4 Pro (RC-N2) Sweden: 7,849 SEK list, sold out (Denmark about 5,295 DKK) (https://djistoresverige.se/en/products/dji-mini-4-pro)
- DJI Air 3S (RC-N3) Sweden: 12,495-13,199 SEK (https://dronestore.se/dji-air-3s-dji-rc-n3)
- DJI Matrice 4E Sweden: 52,200-56,530 SEK (https://dronarbutiken.se/products/dji-matrice-4e)
- DJI Avata 360 (RC 2): EUR 719; about 7,999 SEK (https://www.thedronegirl.com/2026/03/26/dji-avata-360/)
- Antigravity A1 Standard bundle Sweden: 16,189 SEK (about EUR 1,399) (https://www.scandinavianphoto.se/antigravity)
- Autel EVO II Pro RTK V3 EU: EUR 2,999 (from EUR 5,999) (https://www.autelpilot.eu/products/autel-robotics-evo-ii-pro-rtk-v3-rugged-bundle)
- DJI Lito X1 / Lito 1: about EUR 419 / EUR 339 (https://dronedj.com/2026/04/23/dji-new-lito-drone-us/)
- Minimum photo interval Mini 4 Pro / Mini 5 Pro / Air 3S: 2 s at 12 MP binned; 5 s at 48/50 MP (https://www.dji.com/mini-5-pro/specs)
- Matrice 4E minimum photo interval: 0.5 s, mechanical shutter (https://enterprise.dji.com/matrice-4-series/specs)
- DJI Fly max waypoints per mission: 200 (Pixpro claims 101 per file) (https://support.dji.com/help/content?customId=en-us03400007343)
- Transportstyrelsen operator registration: 190 SEK once + 250 SEK per year (https://www.transportstyrelsen.se/sv/om-oss/avgifter/avgifter-inom-luftfart/obemannade-luftfartygssystem---dronare/dronaroperatorer/)
- A1/A3 online test (drönarkort): 600 SEK, valid 5 years (https://www.dronarlabbet.se/flyg-lagligt/dronarkort-sverige)
- Lantmäteriet dissemination permit processing: free; about 65 working days (https://www.lantmateriet.se/sv/spridningstillstand/)
- UgCS PRO: USD 109/month or USD 1,090 perpetual; UgCS Open free (https://shop.sphengineering.com/pages/ugcs-license-types-pricing)
- Pixpro subscription (includes Waypoints): about EUR 5/month yearly, EUR 10 monthly (https://www.pix-pro.com/pixpro-waypoints)
- EASA Opinion 06/2026 proposed registration / Remote ID threshold: 100 g (from 250 g) (https://www.easa.europa.eu/en/document-library/opinions/opinion-no-062026)

## Still unknown

- Sensor readout times in photo mode for the Mini 4 Pro, Mini 5 Pro and Air 3S (unpublished; no lab measurement found).
- The real waypoint limit for KMZ files imported into DJI Fly: DJI says 200, Pixpro says 101.
- Whether DJI Fly's waypoint 'take photo' action on the Mini 5 Pro respects the 50 MP vs 12 MP setting, and how much delay it adds per hover-and-shoot.
- Whether Lantmäteriet's dissemination permit explicitly covers derived 3D models and Gaussian splats (assumed yes).
- The final Opinion 06/2026 text: whether existing C0 drones without Remote ID can still be flown once the 100 g rule applies, and the application or transition dates (the PDF could not be parsed).
- Dronelink and Litchi Pilot current prices; whether Litchi Pilot has left beta.
- Whether Swedish Matrice 4E kits include the RTK module; the ANAFI Ai's EU class label; Autel's long-term EU support plans for the EVO II V3.
- The 600 SEK A1/A3 fee and the 2029 FCC firmware-waiver date are each confirmed by secondary sources only.
- Current price of Svedea's private drone liability policy, and which Swedish home insurers (Folksam, If, Länsförsäkringar, Trygg-Hansa) include drone liability.
- Whether the Avata 360 will get DJI Fly waypoint support in a firmware update.

## Questions for user

- What budget ceiling should the aerial drone have: about 10k SEK (Mini 5 Pro or Lito X1) or more (Air 3S, Matrice 4E)?
- Do you want SDK-level automation on an Android phone (which pushes you to a used Mini 4 Pro with RC-N2), or is DJI Fly onboard waypoints with KMZ generated by our pipeline enough?
- Will the aerial-derived splats be published publicly from Sweden? If so, should we file the Lantmäteriet dissemination permit now, given the roughly 65 working-day queue?
- Does your home insurance policy include liability cover for drones? If not, are you OK with a separate private liability policy?
- Is the forest test site inside a nature reserve, national park or restricted drone zone?
