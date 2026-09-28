# Gallery 1.2.15 — test op de andere pc

Gallery 1.2.15 is de stabiele release van de eerder geteste 1.2.15-beta.1.
Alleen Gallery verandert. CyberHub 1.3.0 of nieuwer is nodig. Installeren kan via
**Module Manager → Check for updates**, of handmatig met onderstaande stappen.

## Installeren

1. Sluit CyberHub en maak een kopie van de bestaande database in de CyberHub-datamap
   als herstelpunt. Kopieer de database terwijl CyberHub gesloten is.
2. Start CyberHub, importeer `cyberhub_module_gallery_v1.2.15.zip` via
   **Settings → Import ZIP** en herstart CyberHub.
3. Controleer bij Gallery dat de versie **1.2.15** is.
4. Gebruik de bestaande grote bibliotheek. Start geen geforceerde rescan en wis de
   thumbnailcache niet: die blijven bruikbaar. Laat een eventuele normale
   opstartscan lopen en controleer ondertussen of bladeren al lukt.

Er blijft één WebP-thumbnail per afbeelding. De zoekdatabase krijgt een aanvullende
opzoektabel, automatisch opgebouwd uit de aanwezige zoekindex. Er worden daarvoor
geen originele afbeeldingen geopend. Die tabel wordt bij opstarten bijgewerkt,
ook om teruggaan naar 1.2.14 en later opnieuw deze versie installeren te ondersteunen.

## Praktijktest

Gebruik voor toevoegen/verwijderen eerst kopieën van testafbeeldingen.

| Actie | Verwacht resultaat |
|---|---|
| Snel aanklikken, Ctrl/Cmd-selectie en Shift-selectie | Direct zichtbare selectie; het metadatapaneel hoort bij de laatst gekozen afbeelding. |
| Enkele afbeeldingen en daarna 100–500 testkopieën verwijderen | Direct voortgang; beelden gaan naar de systeemprullenbak; geslaagde verwijderingen verdwijnen, mislukte blijven beschikbaar. |
| 500–1.000 afbeeldingen toevoegen terwijl Gallery open is | Bestaande afbeeldingen blijven te bekijken; nieuwe verschijnen vanzelf en krijgen geleidelijk metadata/thumbnails. |
| Tijdens verwerking naar een andere map/pagina gaan, zoeken en een afbeelding openen | Geen wachten op de hele import; het origineel opent nog steeds in de grote viewer. |
| Verwerking pauzeren en hervatten | Bestaande thumbnails blijven zichtbaar; nieuwe/ontbrekende thumbnails gaan verder na hervatten. |
| Grid/Masonry, favorieten, collecties en metadatafilters | Selectie blijft kloppen en opgeslagen favorieten/collecties blijven behouden. |
| Afbeeldingen buiten CyberHub toevoegen/verwijderen | Gallery en de zichtbare mappenlijst werken zich automatisch bij. |
| Afsluiten en opnieuw starten | Versie, catalogus, favorieten en collecties blijven goed. |

De pagina kijkt ongeveer elke twee seconden of de catalogus gewijzigd is.
De eerste melding van een nieuwe afbeelding kan ook op de bestandsbewaking wachten.
Het verplaatsen naar de prullenbak en het lezen van originele bestanden blijven
gewoon afhankelijk van pc, NAS en verbinding. Ondersteunt de NAS geen veilige
prullenbakverplaatsing, dan meldt Gallery dat als fout; er is geen fallback naar
permanent verwijderen. Als achtergrondverwerking is uitgezet, moet die eerst
worden aangezet om nieuwe/ontbrekende thumbnails te laten maken.

## Handig om terug te melden

- Besturingssysteem, CyberHub-versie en aantal afbeeldingen.
- Waar afbeeldingen en CyberHub-database staan: lokale SSD, NAS of netwerkshare.
- Ongeveer hoeveel afbeeldingen in de grootste map staan.
- Tijd tot de eerste Gallery-pagina verschijnt, zowel bij normaal starten als bij import.
- Gevoel bij snel selecteren en tijd voor 100 verwijderingen; vooral of het wachten
  zit bij de prullenbakstap of bij het bijwerken van Gallery.
- Of bladeren/selecteren tijdens import blijft werken; eventuele foutmelding exact overnemen.

## Terug naar 1.2.14

Importeer de eerdere stabiele `cyberhub_module_gallery_v1.2.14.zip` via Settings en
herstart. De extra database-opzoektabel wordt door 1.2.14 genegeerd. Een volledige
herscan of het verwijderen van thumbnails is ook daarvoor niet nodig. De installer
maakt daarnaast een back-up van de vervangen modulebestanden.
