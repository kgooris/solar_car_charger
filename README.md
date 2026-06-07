# Solar Car Charger and Monitor — Custom Integration voor Home Assistant

Laad je auto automatisch op bij zonne-energie overschot.
Geïntegreerde wizard, live dashboard in de sidebar, en volledige energietracking.

---

## Installatie

### Stap 1 — Bestanden kopiëren

```
config/
└── custom_components/
    └── solar_car_charger/       ← kopieer deze volledige map
        ├── __init__.py
        ├── config_flow.py
        ├── const.py
        ├── manifest.json
        ├── strings.json
        ├── translations/
        │   └── nl.json
        └── www/
            └── panel.html
```

Kopieer ook het panel naar de www map van HA zodat het bereikbaar is:

```
config/
└── www/
    └── solar_car_charger/
        └── panel.html           ← zelfde bestand, kopieer hier ook
```

### Stap 2 — HA herstarten

Herstart Home Assistant volledig (niet alleen herladen).

### Stap 3 — Integratie toevoegen

Ga naar: **Instellingen → Integraties → + Integratie toevoegen → Solar Car Charger**

De wizard start automatisch en vraagt je sensoren op in 4 stappen:
1. P1 meter sensor (HomeWizard active power)
2. Zonnepanelen sensor (SonnyBoy omvormer)
3. Lader schakelaar + energiemeter (MQTT)
4. Drempelwaarden en vertragingen

### Stap 4 — Dashboard

Na de wizard verschijnt **Solar Car Charger** automatisch in de HA sidebar.

---

## Herinstellingen

Om sensoren of drempelwaarden te wijzigen:

**Instellingen → Integraties → Solar Car Charger → Opties**

De volledige wizard herstart met je huidige waarden vooringevuld.
Na opslaan herlaadt de integratie automatisch.

---

## Vereiste HA helpers (automatisch aangemaakt)

De integration maakt deze helpers aan bij eerste installatie:

| Entity | Omschrijving |
|--------|-------------|
| `input_number.solar_car_energy_today` | Geladen energie vandaag (kWh) |
| `input_number.solar_car_energy_in_battery_today` | Geschatte energie in accu vandaag |
| `input_number.solar_car_energy_total` | Totale geladen energie ooit |
| `input_number.solar_car_session_duration_minutes` | Duur laatste sessie |
| `input_text.solar_car_session_start` | Start tijdstip huidige sessie |
| `input_text.solar_car_session_stop` | Stop tijdstip laatste sessie |

---

## Dashboard functies

Het live panel toont:
- **Vier live meters**: zonnepanelen, huisverbruik (excl. auto), auto laden, teruglevering
- **Energiestroom balk**: verdeling van zonnepanelen over huis / auto / net
- **Grafiek**: vermogen laatste 30 minuten
- **Statistieken**: sessieduur, vandaag geladen, doel %, totaal ooit
- **Instellingen**: drempelwaarden aanpasbaar zonder wizard
- **Sensoren status**: overzicht van geconfigureerde entities

---

## Automatiseringen

De integration registreert drie automatiseringen:
- `Solar Car — inschakelen bij voldoende overschot`
- `Solar Car — uitschakelen bij onvoldoende overschot`
- `Solar Car — dagelijkse reset om middernacht`

Bij herinstellingen (options flow) worden de automatiseringen automatisch bijgewerkt.
