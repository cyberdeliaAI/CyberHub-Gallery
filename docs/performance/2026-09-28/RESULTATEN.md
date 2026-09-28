# Resultaat van de optimalisaties — 28 september 2026

Bron: Gallery 1.2.14 → testbuild 1.2.15-beta.1, vrijgegeven als stabiele versie
1.2.15 met dezelfde functionaliteit. Geen Core-wijzigingen.
Alle metingen en functionele tests gebruikten afzonderlijke, gegenereerde data.
Geen bestaande gebruikerscatalogus is voor de tests geopend of veranderd.

## Synthetische prestatietest

260.000 afbeeldingenrecords, 20.000 tags, 2,6 miljoen tagkoppelingen, circa 2,5 GB
SQLite-data. Zelfde metadata/searchtekst en machine als de eerdere analyse.
De meting gebruikt de daadwerkelijke gewijzigde Gallery-methoden.

| Onderdeel | 1.2.14 | 1.2.15-beta.1 |
|---|---:|---:|
| Bestandsbewaking: administratie van 100 verwijderde paden | 25,95 s | 0,068 s |
| Metadata opvragen tijdens die verwijderbatch | 25,92 s | 0,144 ms |
| 100 zoekindexregels verwijderen (mediaan) | 266 ms | 1,818 ms |
| Gallery-pagina opvragen tijdens verwijderbatch | niet gemeten | 4,385 ms |
| 100 nieuwe paden registreren in grote catalogus | niet rechtstreeks vergelijkbaar | 4,857 ms; 0 mapinventarisaties |
| Opstarten: bestaande index/opzoektabel controleren | niet gemeten | 544 ms |

De winst betreft de database en bestandsbewaking. Dit is **geen** belofte over
het daadwerkelijk lezen van 260.000 afbeeldingen of de prullenbak op een NAS.
De volledige verwijdermethode met 100 tijdelijke sentinels duurde 60 ms, waarbij
de echte systeemprullenbak bewust was vervangen door uitsluitend testbestand-I/O.
De oude en nieuwe proeven zijn geen herhaalde hardwarebenchmark over meerdere pc's.

De precieze uitkomsten staan in `optimized-measurements.json`; de oude resultaten
staan in de overige meetbestanden bij `ANALYSE.md`. De nieuwe proef is opnieuw te
draaien met `tests/benchmark_gallery.py` uit deze repository.

## Controles

- 19 Python-regressietests: gelijktijdige snapshotlezers en schrijvers,
  gebundelde bestandsbewaking, zoekindexmigratie, behoud van favorieten/collecties,
  gedeeltelijk mislukte verwijderingen, meer dan 500 verwijderresultaten,
  thumbnailhergebruik/reparatie, bronwijziging tijdens verwerking, tijdelijke
  leesfouten tijdens kopiëren, pauzeren/hervatten en vrije transacties tijdens discovery.
- 12 JavaScript-tests: late antwoorden, coalescing van selectie, behoud van
  DOM-kaarten/scroll/selectie en bestaande Grid/Masonry-geometrie/navigatie.
- Geïsoleerde browserproef: 45 gegenereerde afbeeldingen, 3 naar een tijdelijke
  testprullenbak verplaatst, vervolgens 60 afbeeldingen toegevoegd. De open pagina
  ging automatisch naar 102 afbeeldingen met metadata; de bestaande selectie bleef
  behouden. Geen browserwaarschuwingen of fouten. Kleine metadata-preview gebruikt
  `/thumb/`; de volledige viewer behoudt `/image/`.
- Pakketimport wordt met de echte Settings-installer gecontroleerd in een tijdelijke
  installatie, inclusief back-up van bestaande Gallery-bestanden en manifestregistratie.

## Implementatie en grenzen

Lezers gebruiken korte, aparte SQLite-WAL-snapshots. Schrijvers blijven onderling
geordend. FTS-verwijderingen gebruiken een geïndexeerde koppeltabel; alleen gewijzigde
tags worden geteld. Bestandsbewaking bundelt maximaal 100 waarnemingen zonder per
bestand de hele map uit te lezen. Ontdekking en verwerking kunnen tegelijk lopen.

Thumbnailgeneratie gebeurt op de achtergrond en schrijft atomair naar dezelfde
cache. Een begrensde prioriteitswachtrij helpt zichtbare afbeeldingen eerder aan
bod te komen. Verouderde antwoorden overschrijven geen nieuwere selectie. De
browser hergebruikt kaarten en werkt een gewijzigde pagina geleidelijk bij.

Een grote zoekopdracht, volledige onderhoudsactie, trage NAS of zwaar afbeeldingsformaat
kan nog steeds tijd kosten. De externe praktijktest moet vooral de respons onder
werkelijke I/O-belasting beoordelen. Zie `TESTEN.md`.
