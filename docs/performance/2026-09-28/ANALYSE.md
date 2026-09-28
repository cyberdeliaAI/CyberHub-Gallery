# Gallery: analyse van selecteren, verwijderen en toevoegen

Datum: 28 september 2026. Dit is een analyse met geïsoleerde proeven; de voorgestelde optimalisaties zijn nog niet in Gallery ingebouwd.

**Conclusie.** De melding is technisch geloofwaardig en de huidige prestaties zijn geen harde limiet. In Gallery zitten aantoonbare oorzaken waardoor achtergrondwerk normale interactie blokkeert. De grootste verbeteringen zijn: mappen één keer per wijzigingsbatch uitlezen, zoekrecords gericht bijwerken, leesverzoeken losmaken van lange schrijfbewerkingen en de bestaande thumbnails gebruiken voor het kleine voorbeeld. Hiervoor is geen tweede thumbnailcache nodig en een volledige herscan is geen oplossing voor deze programmeerproblemen.

**Onderzochte bron.** `/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery`, versie 1.2.14, commit `5d062e0ad26e32f6e5b6b76687294fb8453a8d41`. De repository had bij aanvang geen lokale wijzigingen. Op GitHub wijzen `main` en de nieuwste gepubliceerde release nog naar deze versie; de release is stable, geen prerelease. Core is alleen als afhankelijkheid bekeken, lokaal versie 1.4.1. De oorspronkelijke ontwikkelmap is niet als actuele codebron gebruikt.

De precieze versies, aantallen, bestandsformaten en opslagindeling van de meldende gebruiker zijn onbekend. De gevonden knelpunten zijn ook aanwezig in de code van 1.2.13: ze zijn niet ontstaan door de recente Masonry-aanpassing. Een specifieke beta-installatie is hiermee niet afzonderlijk gediagnosticeerd.

## Wat er nu gebeurt

**Selecteren.** De browser markeert de kaart direct. Ook Ctrl/Cmd-selectie en Shift-selectie roepen voor de gekozen afbeelding `selectImage()` aan. Als metadata niet in de browsercache zit, volgt een verzoek naar `/api/metadata`. De server leest reeds opgeslagen metadata uit SQLite en verwerkt die tot het zijpaneel. Dit opent normaal niet opnieuw het oorspronkelijke beeld voor metadata. Het pad wordt wel op het bestandssysteem opgelost. De Civitai-verrijking is een lokale geheugenlookup, geen externe API-aanroep per selectie.

Pas na de metadatarespons wordt het zijpaneel opgebouwd. Het kleine voorbeeld daarin gebruikt `/image/...`: de volledige originele afbeelding. Daardoor kunnen snel achter elkaar aanklikken, grote PNG's, netwerktransport en het decoderen in de browser onnodig veel werk opleveren. Ctrl/Cmd- en Shift-selectie nemen dit werk mee. Alles selecteren op de pagina werkt anders en vraagt niet voor ieder geselecteerd bestand metadata op.

Er ontbreekt bovendien een controle dat een binnengekomen metadatarespons nog bij de huidige selectie hoort. Een oud verzoek kan een nieuwere selectie overschrijven. Dit is in een proef met de ongewijzigde JavaScript-functie gereproduceerd: afbeelding B bleef geselecteerd, terwijl het paneel uiteindelijk afbeelding A toonde. De verwijderknop in dat paneel is gekoppeld aan de daar gerenderde afbeelding. Dit verdient daarom ook als correctheidsprobleem prioriteit.

Bronnen: [selectImage en zijpaneel](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:4023), [selectiegedrag](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:4641), [metadata uit SQLite](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:1777).

**Verwijderen.** De interface start al een achtergrondtaak. De server verplaatst bestanden één voor één naar de systeemprullenbak, buiten de algemene databasevergrendeling. Vervolgens ruimt hij database- en zoekrecords op, verwijdert thumbnails en actualiseert mappen en tagtellingen. Die laatste fase houdt wel de algemene vergrendeling vast.

Het zoekveld `path` is `UNINDEXED` in FTS5. Een verwijderquery op dat veld doorloopt daarom de gehele zoekinhoud. De normale bulkverwijdering bundelt maximaal 500 paden per query, maar de bestandsbewaking doet dat niet: die roept de opruiming voor ieder verdwenen beeld apart aan. Er is een vertraging van 0,75 seconde om bestandsmeldingen te verzamelen, maar binnen die verzameling blijven het losse verwijderingen.

Als de bewaking begint terwijl een verwijdertaak nog naar de prullenbak verplaatst, kan zij de database als eerste gaan opruimen. Dan volgen veel volledige zoekscans onder dezelfde vergrendeling. Dit is een timingafhankelijk knelpunt: bij een heel korte verwijdertaak kan de eigen bulkopruiming eerst klaar zijn, waarna de bewaking niets meer te verwijderen heeft. Ook externe verwijderingen gebruiken het trage bewakingspad.

De voortgangspoll vraagt behalve taakstatus ook `processing_status()` op. Dat wacht op dezelfde vergrendeling. Hierdoor kan zelfs de voortgangsaanduiding stilstaan terwijl de achtergrondtaak werkt. Na afloop wordt de volledige huidige galerijweergave opnieuw geladen, gevolgd door de mappenboom, collecties en tellers. Dit veroorzaakt extra zichtbare wachttijd. De pollinterval van 400 ms is bijkomende vertraging, niet de verklaring voor tientallen seconden.

Bronnen: [delete_files](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:2116), [zoekindex opruimen](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:1480), [bestandsbewaking verwerken](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:641), [voortgangsstatus](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:5580), [herladen na verwijderen](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:4809).

**Nieuwe afbeeldingen.** Gallery heeft al een scheiding tussen ontdekken en verwerken. Nieuwe bestanden krijgen eerst een record met `processing_state=0`; standaard twee achtergrondworkers lezen daarna de afbeelding, maken de thumbnail en verwerken metadata, tags en zoektekst. Het zware lezen en verkleinen in `_process_file()` gebeurt al buiten de algemene databasevergrendeling. Meer workers toevoegen is daarom geen oplossing voor de overige blokkades en kan opslag en geheugen juist extra belasten.

De bestandsbewaking houdt die vergrendeling echter vast tijdens de hele wijzigingsbatch, inclusief controles op schijf. Voor ieder nieuw of gewijzigd bestand roept zij `_ensure_folder_chain()` aan. Die leest de betreffende map én de bovenliggende mappen opnieuw uit, ook als dat voor andere bestanden in dezelfde batch al is gebeurd. Honderd nieuwe afbeeldingen in één submap veroorzaken zo tweehonderd mapscans. Grote mappen en trage toegang tot bestandsinformatie vergroten deze kosten.

Bij de normale opstartscan worden de workers vanuit `_start_index()` pas gestart nadat de ontdekscan is afgerond. Andere routes, zoals een metadata-aanvraag, kunnen ze tussentijds wel starten. De ontdekscan schrijft in batches van 500, maar verricht aan het eind aanvullende opruiming en aggregatie onder de vergrendeling. Een achtergrondthread op zichzelf garandeert dus geen bruikbare voorgrond.

Een ontbrekende thumbnail wordt bovendien ook direct in het HTTP-verzoek aangemaakt. De achtergrondworker kan diezelfde thumbnail daarna opnieuw maken. In de proef met één nieuw beeld gebeurde precies dat: twee WebP-coderingen, één uiteindelijk cachebestand. Er worden dus geen twee permanente thumbnails bewaard, maar wel onnodig twee keer berekeningen uitgevoerd. Meerdere thumbnailverzoeken worden niet door de limiet van twee achtergrondworkers begrensd.

De browser maakt het wachten extra zichtbaar: `loadGallery()` verbergt de bestaande kaarten direct en toont een laadmelding. Bij het openen van Gallery wacht hij eerst op mappen en collecties voordat de afbeeldingen worden opgevraagd. De vijfsecondenpoll werkt de voortgang en aantallen bij, maar vult nieuwe of inmiddels verwerkte kaarten niet automatisch aan. Een oplopende teller betekent dus nog geen bijgewerkte afbeeldingsweergave.

Bronnen: [map opnieuw uitlezen](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:598), [achtergrondverwerking](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:981), [thumbnailroute](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:5844), [laden en verbergen kaarten](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:3598), [opstartvolgorde browser](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:5264), [statuspoll](/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py:5178).

## Gemeten bewijs

Alle onderstaande metingen zijn uitgevoerd met tijdelijke, zelfgemaakte bestanden en databases. Er is geen productieafbeelding verwijderd of verplaatst. Er is geen bestaande CyberHub-database geopend of aangepast. De oorspronkelijke Gallery-methoden zijn rechtstreeks aangeroepen; voorstellen zijn uitsluitend in de testomgeving geprobeerd.

Omgeving: macOS ARM64, SQLite 3.53.4, lokale tijdelijke opslag. De grote proef bevatte 260.000 records, 20.000 tags en 2,6 miljoen tagkoppelingen. De synthetische metadata was 1.326 bytes per beeld; de door Gallery gemaakte zoektekst 4.943 bytes. De testdatabase was circa 2,5 GB. Tijden zijn onderdeelmetingen met grotendeels warme caches, geen voorspelling van de totale gebruikerservaring op Windows, NAS of een andere bibliotheek.

| Onderdeel | Bestaande code | Geïsoleerde proef / vergelijking |
|---|---:|---:|
| Metadata ophalen zonder achtergrondblokkade, 260k records | Mediaan 0,033 ms; p95 0,043 ms | Snelle padlookup is al aanwezig |
| Metadata ophalen terwijl bewaking 100 verwijderingen verwerkt | 25,92 s wachten | Wachten op Gallery-vergrendeling |
| Bewaking: 100 verwijdermeldingen bij circa 260k records | 25,95 s, 100 volledige zoekscans | Dezelfde bewakingsmethode met gebundelde opruiming: 0,395 s |
| Alleen zoekrecord van één afbeelding verwijderen, 260k records | Mediaan 233 ms | Met geïndexeerde pad→zoekrecord-koppeling: 0,059 ms |
| Alleen 100 zoekrecords verwijderen, 260k records | Mediaan 266 ms | Met die koppeling: 1,67 ms |
| 100 nieuwe afbeeldingen in een map van 10k bestanden verwerken in de bewaking | 1,283 s; 200 mapscans | Mapketen één keer: 0,0165 s; 2 mapscans |
| Metadata opvragen tijdens die toevoegbatch | 1.283 ms wachten | Rechtstreekse gelijktijdige SQLite-lezing zonder Gallery-lock: 0,020 ms |
| Gewone statistiekpoll, 260k records, zonder ander werk | Mediaan 4,01 ms | Op deze fixture geen hoofdoorzaak |
| Alle tagtellingen herberekenen, 2,6 miljoen koppelingen | Mediaan 42,8 ms | Bijkomend werk, kleiner dan zoekscans |

De directe verwijdermethode zonder concurrerende bewaking kostte bij één testbestand 305 ms en bij honderd 373 ms. Hierbij was de systeemprullenbak vervangen door het verwijderen van uitsluitend de aangemaakte testbestanden. Dit is **geen meting van de echte prullenbak**. De databasefase nam daarvan respectievelijk 304 en 368 ms in beslag. Het verschil met de bewakingsproef laat zien waarom het aantal wijzigingen en de timing zoveel uitmaken.

De batchproef van 0,395 seconde bevat ook de normale mapverversing en databasecommit van de bewakingsmethode. Alleen de honderd losse opruimingen werden verzameld en eenmaal uitgevoerd. De zuivere batchopruiming zonder die extra stappen nam in een aparte proef mediaan 268 ms in beslag. De opeenvolgende verwijderproeven gebruiken verschillende records in dezelfde synthetische bibliotheek; het aantal records bleef circa 260.000.

De geïndexeerde koppeltabel kon in deze fixture in 0,397 seconde uit de bestaande zoekindex worden opgebouwd. Dit vereist geen lezen van originele afbeeldingen. Een productieoplossing moet de koppeling ook bij invoegen, wijzigen, verwijderen en opnieuw opbouwen correct onderhouden; dit is nog geen voltooide migratie.

De proef met nieuwe bestanden mat alleen ontdekken en registreren, niet het decoderen van de honderd afbeeldingen. De oorspronkelijke functie is vergeleken met dezelfde functie waarbij de mapketen eenmaal per batch werd aangeroepen. De metadata-lezing zonder Gallery-lock demonstreert dat SQLite de gelijktijdige lezing aankon; het is geen voorstel om alle locks zonder verdere controle weg te halen.

De thumbnailproef gebruikte een gegenereerde PNG van ongeveer 4 MB. De thumbnail was circa 15 KB. Deze bestandsverhouding is slechts een voorbeeld. Aangetoond is dat een thumbnail die tijdens een HTTP-verzoek werd gemaakt vervolgens opnieuw door de worker werd gecodeerd. De eerste codering nam circa 127 ms in beslag, de daaropvolgende volledige verwerking circa 25 ms; door cache- en initialisatieverschillen zijn die twee tijden geen zuivere codecvergelijking.

De JavaScript-proef bevestigde los daarvan dat een late respons het verkeerde metadata-/voorbeeldpaneel kan tonen. Er is geen echte browsernetwerktrace van de meldende installatie opgenomen.

Ruwe resultaten en scripts staan naast dit rapport. De grote testdatabases worden niet in de repository opgenomen.

## Aanpak, in volgorde van prioriteit

1. **Houd Gallery bruikbaar tijdens import en verwijdering.** Lees mappen en bestandsinformatie buiten lange databasevergrendelingen. Verzamel per wijzigingsbatch unieke mappen en verdwenen bestanden. Sla veranderingen op in korte batches. Laat leesverzoeken een consistente SQLite-snapshot gebruiken zonder op een hele import- of verwijderbatch te wachten. Schrijvers blijven gecoördineerd; transacties, caches en foutafhandeling moeten daarbij expliciet worden gecontroleerd. Taakvoortgang moet uit snel toegankelijke status kunnen komen.

2. **Maak zoekindexupdates gericht.** Introduceer een betrouwbare geïndexeerde koppeling van pad naar zoekrecord, of een equivalente oplossing met stabiele record-ID's. Gebruik die bij wijzigingen en verwijderingen. Nieuwe beelden gebruiken in `_process_file()` normaal `replace=False` en veroorzaken daar niet standaard een scan per invoeging; vooral bestaande beelden en de verwijderpaden hebben voordeel. Bundel bestandsmeldingen en voorkom dat de eigen verwijdertaak en de bewaking dezelfde opruiming tegelijk uitvoeren. Bewaking van echte externe wijzigingen moet blijven werken.

3. **Maak selectie licht en correct.** Toon onmiddellijk de bestaande thumbnail in het kleine paneel. Vraag het origineel op wanneer de gebruiker de grote weergave opent. Dat houdt de bestaande cache van één thumbnail per beeld. Behoud desgewenst een bewuste optie voor een scherper paneelvoorbeeld. Laat alleen het antwoord voor de nog actuele selectie tekenen, bundel snelle opeenvolgende selecties en annuleer overbodige browserverzoeken. Verouderde serververzoeken kunnen ondanks annuleren al gestart zijn; de responscontrole blijft dus noodzakelijk. Multi-selectie moet bruikbaar blijven zonder voor iedere klik een origineel te laden.

4. **Gebruik één begrensde verwerkingswachtrij.** Laat thumbnailgeneratie en achtergrondverwerking per bestand samenwerken. Een ontbrekende thumbnail gaat met prioriteit in de wachtrij, zonder tegelijk in allerlei HTTP-threads dezelfde decodeerwerkzaamheden uit te voeren. Bestaande actuele thumbnails moeten worden hergebruikt. Nieuwe kaarten kunnen tijdelijk een duidelijke verwerkingstoestand tonen. Status en een versiekenmerk moeten voorkomen dat een tijdelijke of verouderde thumbnail permanent in de browsercache blijft hangen.

5. **Werk de pagina geleidelijk bij.** Laat bestaande kaarten staan terwijl aanvullingen worden geladen. Laad de eerste afbeeldingspagina onafhankelijk van niet noodzakelijke zijbalkgegevens. Voeg nieuwe/verwerkte kaarten gecontroleerd toe, met behoud van scrollpositie, selectie, filters en layout. Toon bij verwijderen meteen welke items in behandeling zijn; haal ze na bevestigde verwijdering weg en laat mislukte bestanden met foutmelding staan. Een volledige herlaadactie na iedere verwijderbatch is dan minder vaak nodig.

6. **Optimaliseer overige totalen daarna.** Werk tag- en maptellingen zo veel mogelijk voor de gewijzigde records bij. Coördineer of cache statuspolls zodat ze niet opstapelen. Beoordeel aanvullende sorteerindexen en tellerqueries met echte gebruiksmetingen. De metingen geven geen aanleiding deze kleinere optimalisaties vóór de locks, mapscans en zoekindex te plaatsen.

Deze wijzigingen kunnen hoofdzakelijk binnen Gallery blijven. Een ander databasetype, tweede thumbnailcache of volledige herverwerking van 260.000 afbeeldingen is hiervoor niet nodig. SQLite WAL ondersteunt gelijktijdige lezers en een schrijver; Gallery schakelt WAL al in, maar beperkt de gelijktijdigheid zelf met de brede lock. Zie [SQLite: Write-Ahead Logging](https://www.sqlite.org/wal.html#concurrency). De queryplannen in de meetresultaten bevestigen de scan op het niet geïndexeerde pad; zie ook [SQLite FTS5](https://www.sqlite.org/fts5.html#the_unindexed_column_option).

## Herscan en installatieadvies

Een volledige herscan verandert deze algoritmes niet. Een geforceerde scan wist de zoekindex en zet beelden opnieuw klaar voor verwerking. Dat voegt juist lees-, decodeer- en schrijfwerk toe. Een herscan is nuttig voor werkelijk ontbrekende of achterhaalde gegevens, niet als algemene remedie tegen de aangetoonde blokkades. Alleen de zoekindex opnieuw opbouwen voegt evenmin een ontbrekende padindex toe.

Als tijdelijke diagnose kan verwerking worden gepauzeerd om te vergelijken of normale selectie dan vlot is. Die pauze stopt de metadataworkers, maar niet de bestandsbewaking of een lopende ontdekscan. Een blijvend trage Gallery na pauzeren sluit achtergrondblokkades dus niet uit. Het aantal workers verhogen is geen goede eerste ingreep.

Voor de installatie zelf zijn nog relevant: Gallery- en Hub-versie, aantal bestanden in de grootste map, gemiddelde bestandsgrootte, of de vertraging de selectierand of het paneel betreft, en waar `cyberdelia.db` en `.thumbs` staan. Een server die op de NAS met lokale volumes draait is een andere situatie dan een database op een via SMB/NFS aangekoppelde share. SQLite geeft voor WAL een beperking op netwerkbestandssystemen aan; controleer dit alleen als de database werkelijk op zo'n share staat. Zie [SQLite WAL: voorwaarden](https://www.sqlite.org/wal.html#overview). Dat is niet aangetoond als oorzaak van deze melding.

## Acceptatie voor een toekomstige implementatie

- Bestaande afbeeldingen, metadata en navigatie blijven reageren tijdens het toevoegen of verwijderen van honderden bestanden bij een catalogus van 260.000 records. Meet hiervoor de responstijden tijdens belasting, niet alleen de totale importtijd.
- Per batch wordt iedere betrokken map hoogstens eenmaal uitgelezen. Verwijderen van een klein aantal beelden veroorzaakt geen herhaalde scan van alle zoekrecords.
- Snelle selectie A→B kan nooit meer metadata, voorbeeld of verwijderactie voor A tonen nadat B actief is geworden.
- Er blijft één permanente thumbnail per beeld. Ieder verwerkt bestand wordt voor dezelfde inhoud niet gelijktijdig door meerdere paden verkleind.
- Nieuwe kaarten en afgeronde verwerking verschijnen zonder dat de hele pagina verdwijnt, de scrollpositie verspringt of de selectie verloren gaat.
- Test ook een volle of niet beschikbare prullenbak, gedeeltelijk mislukte verwijderingen, tegelijkertijd externe wijzigingen, beschadigde beelden, herstart tijdens verwerking en migratie van een bestaande zoekindex. Behoud favorieten, collecties en tags.
- Meet echte prullenbak- en opslagkosten apart op de gemelde NAS en op SSD. De prototypes bewijzen verbeterpotentieel in Gallery, maar geven daarvoor geen eind-tot-eindgarantie.

## Reproduceren

De scripts gebruiken de hierboven genoemde actuele repository als bron en importeren Core zonder Hub te starten. Ze starten geen watcher-service en gebruiken geen gebruikersafbeeldingen. `benchmark.py` en `add_images.py` roepen de bestaande bewakingsmethode gecontroleerd aan; een eventuele OS-prullenbakhandeling wordt uitsluitend in de benchmark vervangen voor eigen testbestanden.

Kopieer voor elke nieuwe run de scripts naar een lege tijdelijke directory. Gebruik Python met Pillow en SQLite FTS5 en voer achtereenvolgens `benchmark.py`, `batch_delete_prototype.py`, `add_images.py`, `thumbnail_pipeline.py` en `node selection_race.cjs` uit. Reserveer circa 3 GB tijdelijke ruimte voor de grote database. De scripts weigeren bestaande fixtures te overschrijven of verwijderen van reeds gebruikte records te herhalen. De databasepaden en bronlocaties zijn zichtbaar in de scripts; pas de bronlocaties alleen aan naar de gecontroleerde checkout van dezelfde commit.

Er is voor deze analyse geen productcode, versienummer of release gewijzigd en niets gecommit of gepusht.
