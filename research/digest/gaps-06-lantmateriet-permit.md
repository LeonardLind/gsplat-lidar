# gap: lantmateriet-permit

## Summary

Bottom line: plan to apply for a spridningstillstånd for the drone JPGs themselves. Don't submit a finished splat, and don't count on the forest exemption covering a splat. A model built only from ground data (BLK2GO plus Insta360) is outside §9 and needs no permit, as long as no drone-derived information is built into it.

Legal basis, checked 2026-10-07. Lag (2016:319) is amended up to SFS 2026:1378. That amendment changes 6 § (restriction areas during heightened readiness), not 9 §. 9 § forbids spreading "en sammanställning av geografisk information ... över andra delar av svenskt territorium, om informationen har inhämtats från luftfartyg genom fotografering eller liknande registrering". 2 § defines "fotografering eller liknande registrering" as "alla former av avbildningar eller mätningar". The penalty in 12 § is "böter eller fängelse i högst ett år". Förordning 2016:320 (amended up to SFS 2025:1147) makes Lantmäteriet the deciding authority and lets it issue exemptions. The regulation is LMFS 2016:1, amended by 2016:3, 2017:2 and 2019:3. Lantmäteriet's list of regulations shows no later amendment to 2016:1.

(1) Follow-on products (följdprodukter). Yes, after approval of the source images. Two Lantmäteriet pages agree:
- The FAQ: "Bifall med villkor: Du får enbart sprida materialet som vi skickat tillbaka samt skapa följdprodukter utifrån det. Den ursprungliga datamängden ... får inte spridas. Alla kopior av den ursprungliga datamängden bör raderas."
- The requirements page for larger image sets (Kravspecifikation för större mängder bildmaterial): "Följdprodukter som exempelvis ortofoton, 3D-modeller och ytmodeller ska genereras i efterhand från det godkända materialet. Dessa produkter behöver i så fall inte skickas in för spridningsgodkännande om inget annat framgår av beslutet."
So any number of splat or mesh versions trained only from approved (or returned) images from that flight can be published without a new application. Two limits apply. Each new flight needs a new application ("för varje gång som du samlar in material"), and you cannot apply in advance. If the decision is "with conditions", you must retrain from the retouched images Lantmäteriet sends back.

(2) Submitting a finished 3D model instead. Lantmäteriet says "Vi har inte möjlighet att retuschera i videofilmer, 3-D modeller, radardata och rådatafiler". For video it says "kan det bli nekande av vissa sekvenser". It also says "Vi kan bara ge spridningstillstånd för det material vi får skickat till oss". My inference from these: a submitted model gets approved, refused, or at most partly approved (delvis bifall) per file or part. It cannot be cleaned up by retouching. Each retrained version is new material Lantmäteriet has not reviewed, so it needs a new application, at roughly 65 working days each. The application form does list "3D-modeller" as a material type.

(3) Storage. Lantmäteriet's FAQ: "Spridning är när du tillgängliggör materialet för andra, till exempel skickar det med e-post, publicerar det på en webbplats eller sociala medier, lagrar det i molntjänster eller på servrar som du inte själv har fullständig kontroll över." My inference:
- A home NAS that only you administer and access is not spridning.
- A hosted private Git repo (GitHub/GitLab) or a personal cloud (OneDrive, Google Drive, iCloud) is spridning by Lantmäteriet's definition, even if private.
- The same applies to cloud GPU training, Leica/Hexagon cloud services, sending files to the Luciad team, or embedding drone outputs in a claude.ai page.
The government bill (prop. 2015/16:63, section 9.2) is narrower: "måste den ha gjorts tillgänglig inte endast för ett fåtal". But Lantmäteriet makes the decisions and says e-mail counts, so follow Lantmäteriet.

(4) Ground-only model. 9 § requires information "inhämtats från luftfartyg". Lantmäteriet's FAQ adds that from a height with "markkontakt ... behövs inget spridningstillstånd". So a BLK2GO plus Insta360 model is not covered (high confidence). If its frame or coordinates come from drone photogrammetry, it is a grey zone (my inference). The bill says position data in register form counts as a "sammanställning", and "mätningar" are included in the definition. Strictly, drone-derived target coordinates built into the model are aerial information. A pure scale factor probably isn't position-bound information. Design advice: take metric scale and frame from the BLK2GO (and ground GNSS if needed), and transform the drone layer into the LiDAR frame, never the other way.

(5) Forest exemption (LMFS 2017:2). It "gäller endast om det handlar om fotografier eller film och att detta material inte innehåller fordon, byggnader, anläggningar, verksamheter eller andra mänskliga aktiviteter förutom sådant som tillhör skogsbruket samt att det ska vara markägaren själv som beställt materialet eller själv agerat fotograf."
- A visible surveyor with an instrument, or survey targets, is human activity outside forestry, so the exemption most likely fails (inference).
- A forestry road might count as part of forestry. A car parked on it would not. A power line voids the exemption explicitly: "Om materialet exempelvis innehåller kraftledning gäller inte undantaget".
- Surroundings are not covered: "undantaget bara gäller för området. Kommer det med vybilder som sträcker sig utanför området blir dessa tillståndspliktiga".
- A splat is not "fotografier eller film", so the exemption probably does not cover the model even when the photos are exempt (inference).
- If you are not the landowner and the landowner did not order the material, the exemption does not apply at all.
- The vegetation exemption ("Vegetation") excludes flygfoto/laserdata "även om man bara registrerat skog". Only derived vegetation analyses, such as tree heights, are exempt.

(6) Practicalities.
- Application is free ("kostnadsfritt"). Private individuals use the same form with "Ansöker som: Privatperson".
- Processing time: "Vi handlägger just nu ärenden från vecka 29 ... ca 65 arbetsdagar". Cases are handled in order of arrival.
- File-transfer service: 5 GB per file, 250 GB or 5,000 files per upload. Larger amounts go on an external drive by tracked post.
- Lantmäteriet asks for originals or the highest-resolution JPGs. It cannot retouch DNG/RAW. The requirements page for large image sets asks for uncompressed TIFF.
- LiDAR in LAS/LAZ, split above 2 GB or 75 M points per file.

(7) Contact: spridningstillstand@lm.se (general phone 0771-63 63 63, weekdays 9–16). A draft question in Swedish is in the recommendations.

What this means for the plan:
- Make the drone layer optional and decoupled.
- Ship the ground-only viewer first.
- Keep all drone data and anything trained from it in a local, unsynced quarantine until approval.
- Submit all JPGs used for training immediately after the flight.
- Budget about 3 months before any drone-derived output can be shared.
- Keep the pipeline able to retrain from Lantmäteriet's returned images.

## Plan changes

- Phase ordering: release the ground-only viewer (BLK2GO plus Insta360 splat) first. Treat the drone or aerial layer as a later, optional phase gated on a permit decision about 65 working days (~3 months) after submission.
- Registration design: take metric scale and frame from the BLK2GO (and optional ground GNSS). Transform the drone layer into the LiDAR frame. Don't use drone photogrammetry or drone-measured targets to set the ground model's frame, scale or georeference.
- Data handling: add a 'drone_quarantine' folder outside every synced, backed-up or Git-tracked path, and add it to .gitignore. Allow no cloud training, cloud processing (Leica/Hexagon cloud), artifact embedding or e-mailing of drone images or drone-derived models before approval. Check whether a corporate laptop backup agent copies this folder.
- Capture protocol (drone): shoot JPG, not DNG-only. Keep GPS EXIF. Prefer nadir images and avoid obliques showing the surroundings. Keep people, survey targets, vehicles, roads and power lines out of drone frames where possible. Log the flight date. Each flight is a separate application.
- Submission step right after capture: upload every JPG used for training through the file-transfer service (≤5 GB/file, ≤250 GB or 5000 files per upload). Apply as 'Privatperson', consent to retouching, and describe the purpose as non-commercial web publication of 3D models. Keep the case number.
- Pipeline: support retraining from the image set Lantmäteriet returns (bifall med villkor) or from an approved subset (delvis bifall), keyed by filename. Don't assume returned images keep EXIF; keep the camera poses and intrinsics from the original SfM so you can re-attach them. Delete originals if the decision is bifall med villkor.
- Versioning policy: any number of splat or mesh versions may be published if trained only from approved images of approved flights. Adding images from a new flight needs a new approval first.
- Optional: derived vegetation-only products (tree heights, crowns, tree positions) from drone data may be exempt under the 'Vegetation' rule. A splat, mesh or orthophoto from drone images is not.
- Before any drone flight: send the drafted pre-capture question to spridningstillstand@lm.se and check for skyddsobjekt signs and restriction areas at the site. Drone flight rules (Transportstyrelsen/EASA, LFV airspace) are separate and not covered here.
- Tropical forest phase: Swedish 9 § covers only Swedish territory. Brazilian rules need separate research.

## Recommendations

- **Apply for a permit for the drone source images (every JPG actually used for training, full resolution, GPS EXIF kept, not DNG). Do this right after the flight, as a private individual. Tick 'Snedbilder'/'Lodbilder', consent to retouching, and describe the purpose as non-commercial publication of a 3D model on the web. Then publish any number of splat or mesh versions trained only from the approved or returned images.** — Two Lantmäteriet pages say follow-on products such as 3D models made from approved material need no new submission. Submitting a model instead risks refusal (it can't be retouched) and a new ~65-working-day review for every retrain. _Alt:_ Submit a finished 3D model (one-off, no retouching, likely a new application per version). Or rely on the forest exemption, which is fragile: photos or film only, landowner condition, no non-forestry activity or surroundings.
- **Build the core product (LiDAR plus Insta360 splat) entirely from ground sensors, with metric scale and frame from the BLK2GO and optionally ground GNSS or a tape. Register the drone layer into the LiDAR frame, never the other way.** — Ground-only data is outside 9 § ('inhämtats från luftfartyg'; Lantmäteriet: 'markkontakt ... behövs inget spridningstillstånd'). Drone-derived coordinates built into the ground model are arguably a 'sammanställning' from aircraft, which could tie the whole ground product to the permit. _Alt:_ Ask Lantmäteriet (question 5 of the draft) whether a drone-derived scale or frame triggers 9 §.
- **Until approval, keep raw drone images and anything trained from them in a local-only quarantine folder: not in Git remotes, OneDrive, Google Drive, cloud GPU services, Leica/Hexagon cloud, the Luciad team, claude.ai artifacts, or e-mail. A home NAS that only you control is acceptable (my inference).** — Lantmäteriet's definition of spridning includes 'lagrar det i molntjänster eller på servrar som du inte själv har fullständig kontroll över' and e-mail. _Alt:_ The bill's narrower 'fler än ett fåtal' test might allow sharing with one coworker, but Lantmäteriet's own FAQ is stricter and it decides permits.
- **Plan drone flights so the images show only forest. Prefer nadir images; avoid obliques that show the surroundings. Keep people, survey instruments, survey targets, vehicles, roads and power lines out of the drone frames where possible. Even so, apply rather than rely on the exemption.** — Lower risk of refusal or retouching. The forest exemption fails with non-forestry human activity, vehicles, power lines or surroundings, and probably does not cover a splat. _Alt:_ If you are the landowner and the frames are clean, the photos themselves may be exempt, but the splat would still be uncertain.
- **E-mail spridningstillstand@lm.se before capture, with this draft (fill in the brackets).

Ämne: Fråga inför drönarfotografering av skogsmark – underlag för 3D-modell (Gaussian splatting), privatperson

Hej,
Jag är privatperson och planerar ett icke-kommersiellt hobbyprojekt där jag vill dokumentera en liten skogsyta (ca 10 × 10 m inom en omgivande yta på ca 60 × 60 m) i [kommun], ungefärligt läge [N/E i SWEREF 99 TM]. Jag har inte flugit ännu och vill därför fråga innan jag samlar in materialet.

Planerad insamling: (a) drönarbilder i JPG (lodbilder och snedbilder utan horisont), ca [antal] bilder från ca [höjd] m; (b) markbaserade bilder med en 360-kamera och handhållen laserskanning inne i skogen. Av bilderna vill jag beräkna 3D-modeller (s.k. Gaussian splatting, ev. även mesh/punktmoln) som jag vill visa i en webbläsare, dela med kollegor och eventuellt publicera öppet. Modellerna kommer att räknas om i flera versioner.

1. Om jag skickar in samtliga drönarbilder i full upplösning och får bifall (eller bifall med villkor), får jag då sprida nya versioner av 3D-modeller som tagits fram enbart ur de godkända/återsända bilderna utan ny ansökan för varje version?
2. Om jag i stället skickar in en färdig 3D-modell – bedöms den som helhet, och krävs ny ansökan för varje ny version?
3. Omfattar undantaget för skogsmark (LMFS 2016:1, 2 kap. 3 § p. 13 i lydelse enligt LMFS 2017:2) även en 3D-modell framställd ur fotografierna, eller endast fotografier och film? Jag är [inte] markägare; markägaren har [inte] beställt materialet.
4. Gäller skogsundantaget om materialet visar en person med mätinstrument, utlagda mätsignaler (targets) eller en skogsbilväg, och omfattar det omgivande mark som syns i snedbilder?
5. Krävs spridningstillstånd för en modell som enbart bygger på markbaserade bilder och handhållen laserskanning, om modellens koordinatsystem eller skala har bestämts med hjälp av drönarbilder eller signaler inmätta i drönarbilder?
6. Räknas det som spridning att lagra drönarbilderna eller modellerna (a) på en egen NAS i hemmet som bara jag har åtkomst till, (b) i ett privat Git-repositorium hos en extern tjänst, (c) i en personlig molnlagring?
7. Föredrar ni något format eller urval för bilder som ska användas till 3D-modellering, och behåller återsända bilder sin EXIF-/GPS-information? Kan flera flygtillfällen samlas i en ansökan?

Tack på förhand!
Med vänliga hälsningar
[Namn, telefon]** — Questions 1, 3, 4, 5 and 6 rest partly on my inference. A written answer from Lantmäteriet removes the risk. Lantmäteriet names this address for questions, and permits cannot be applied for in advance, so a general question is the only pre-capture option. _Alt:_ Call 0771-63 63 63 (weekdays 9–16), but a written e-mail answer is better as documentation.

## Load-bearing findings

- [high] Once the source drone images are approved, 3D models (splat/mesh) and other follow-on products made from them can be published without a new application, unless the decision says otherwise. — https://www.lantmateriet.se/sv/spridningstillstand/forbered-ditt-material/kravspecifikation-for-storre-mangder-bildmaterial/ https://www.lantmateriet.se/sv/spridningstillstand/vanliga-fragor/ https://www.lantmateriet.se/en/dissemination-permit/faqs/
- [high] Each collection occasion (flight) needs its own application, and you cannot apply in advance. — https://www.lantmateriet.se/sv/spridningstillstand/vanliga-fragor/ https://www.lantmateriet.se/en/dissemination-permit/faqs/
- [medium] A submitted 3D model cannot be retouched. My inference is that it is approved or refused as submitted (at most partly approved per part), and each new version is new material needing its own application. — https://www.lantmateriet.se/sv/spridningstillstand/vanliga-fragor/ https://www.lantmateriet.se/sv/spridningstillstand/ansokan/
- [medium] Lantmäteriet defines dissemination (spridning) to include e-mail, web or social publishing, and storage in cloud services or on servers you do not fully control. The government bill (prop. 2015/16:63) is narrower. — https://www.lantmateriet.se/sv/spridningstillstand/vanliga-fragor/ https://www.riksdagen.se/sv/dokument-och-lagar/dokument/proposition/skydd-for-geografisk-information_h30363/html/
- [medium] A model built only from ground-based photos and handheld LiDAR is outside §9. A frame or coordinates taken from drone photogrammetry is a grey zone. — https://data.riksdagen.se/dokument/sfs-2016-319.text https://www.lantmateriet.se/sv/spridningstillstand/vanliga-fragor/ https://www.riksdagen.se/sv/dokument-och-lagar/dokument/proposition/skydd-for-geografisk-information_h30363/html/
- [high] The forest exemption applies only to photos or film. Visible vehicles, structures or non-forestry human activity void it, and the landowner must have ordered the material or taken it themselves. — https://www.lantmateriet.se/globalassets/om-lantmateriet/rattsinformation/foreskrifter/lmfs172.pdf https://www.lantmateriet.se/sv/spridningstillstand/undantag/ https://www.lantmateriet.se/globalassets/temawebbar/spridningstillstand/info_lag_foreskrifter_spridningstillstand.pdf
- [high] Area exemptions do not cover the surroundings. Views extending beyond the exempt area need a permit. — https://www.lantmateriet.se/globalassets/temawebbar/spridningstillstand/info_lag_foreskrifter_spridningstillstand.pdf https://www.lantmateriet.se/sv/spridningstillstand/undantag/
- [high] Processing time is about 65 working days, the backlog is at week 29, and applying is free. Private individuals use the same form. — https://www.lantmateriet.se/sv/spridningstillstand/ https://www.lantmateriet.se/sv/spridningstillstand/vanliga-fragor/ https://www.lantmateriet.se/sv/spridningstillstand/ansokan/

## Key numbers

- Estimated processing time: ca 65 arbetsdagar (~13 weeks) (https://www.lantmateriet.se/sv/spridningstillstand/vanliga-fragor/)
- Current backlog position (as fetched 2026-10-07): handling cases from week 29 (mid-July 2026) (https://www.lantmateriet.se/sv/spridningstillstand/)
- Application fee: 0 (kostnadsfritt) (https://www.lantmateriet.se/sv/spridningstillstand/)
- File-transfer max file size: 5 GB per file (https://www.lantmateriet.se/sv/spridningstillstand/forbered-ditt-material/)
- File-transfer max per upload: 250 GB or 5000 files (https://www.lantmateriet.se/sv/spridningstillstand/vanliga-fragor/)
- LiDAR per-file split threshold: 2 GB / 75 million points (uncompressed LAS) (https://www.lantmateriet.se/sv/spridningstillstand/forbered-ditt-material/kravspecifikation-for-lidar-data/)
- Orthophoto tiling threshold (large sets): >10 km² or >4 GB per uncompressed image (https://www.lantmateriet.se/sv/spridningstillstand/forbered-ditt-material/kravspecifikation-for-storre-mangder-bildmaterial/)
- Nadir image / orthophoto general exemption: resolution 0.5 m or coarser (https://www.lantmateriet.se/globalassets/temawebbar/spridningstillstand/info_lag_foreskrifter_spridningstillstand.pdf)
- Historic exemption: material acquired before 1950 (https://www.lantmateriet.se/globalassets/temawebbar/spridningstillstand/info_lag_foreskrifter_spridningstillstand.pdf)
- Maximum penalty, 12 § lag 2016:319: fines or up to 1 year imprisonment (https://data.riksdagen.se/dokument/sfs-2016-319.text)
- Forest exemption in force since: 2017-11-01 (LMFS 2017:2) (https://www.lantmateriet.se/globalassets/om-lantmateriet/rattsinformation/foreskrifter/lmfs172.pdf)
- Latest LMFS 2016:1 amendment: LMFS 2019:3, in force 2020-01-01 (https://www.lantmateriet.se/sv/om-lantmateriet/rattsinformation/foreskrifter/)
- Lantmäteriet general phone: 0771-63 63 63, weekdays 9–16 (https://www.lantmateriet.se/sv/om-lantmateriet/kontakta-oss/)

## Still unknown

- Whether Lantmäteriet treats a 3D model or splat made from exempt forest photos as covered by the forest exemption. The text says only 'fotografier eller film'.
- Whether a submitted single-file 3D model can be partly approved, and which 3D formats (.ply, .spz, mesh) Lantmäteriet can open and review.
- Whether drone-derived target coordinates or a scale factor built into a ground-only model trigger 9 §. No Lantmäteriet statement found.
- Whether a home NAS with remote access or a relay (e.g. vendor cloud relay) still counts as 'fullständig kontroll'.
- Whether Lantmäteriet would treat sharing with a single coworker as spridning, given the bill's 'fåtal' test versus the FAQ's 'skickar det med e-post'.
- Whether returned (retouched) images keep EXIF and GPS, filenames and full resolution. This matters for SfM and splat training.
- Whether one application can cover several flight occasions, and Lantmäteriet's turnaround on e-mailed questions.
- The JPEG-vs-TIFF conflict: the requirements page for large image sets asks for uncompressed TIFF, while the FAQ says JPG can be retouched. No threshold defines 'större mängder'.
- The exact text of SFS 2026:1378 (reported via a search summary as amending 6 §, in force 2026-08-01). Not verified against the primary PDF, though it does not appear to change 9 §.
- Whether the processing-time figure (week 29, ~65 working days) is current on the fetch date or a stale page value.
- Whether a forestry road, or a person doing forest inventory, counts as 'tillhör skogsbruket'.

## Questions for user

- Are you (or a family member) the landowner of the Swedish forest plot, or has the landowner 'ordered' the drone material? If not, the forest exemption cannot apply.
- Is the laptop personal or Hexagon-managed? Corporate backup or sync agents could put drone data on servers you don't fully control.
- Do you have a home NAS for raw data, or would data otherwise end up in GitHub or cloud storage?
- Will the drone images unavoidably show surroundings (lake, roads, power lines, buildings, other owners' land), or people and survey targets?
- Is it acceptable that drone-derived outputs can't be shared with coworkers until about 3 months after the flight?
- Roughly where is the site (municipality)? Is it near military areas or skyddsobjekt?
