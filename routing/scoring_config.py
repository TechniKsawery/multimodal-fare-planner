"""Kary w scoringu "najlepszy stosunek cena/czas" (SZACUNEK, do strojenia) — patrz README.md.
"Najtańsza" i "najszybsza" ich NIE używają."""

VALUE_OF_TIME_PLN_PER_HOUR = 40    # ile PLN warta 1 godzina podróży (waga czasu względem ceny)
RISKY_TRANSFER_PENALTY_MIN = 60   # doliczane do czasu za każdą ryzykowną przesiadkę
RISKY_TRANSFER_PENALTY_PLN = 50   # doliczane do ceny za każdą ryzykowną przesiadkę
EXTRA_CARRIER_PENALTY_MIN = 20    # za każdego dodatkowego przewoźnika (osobny bilet, ryzyko połączenia)
EXTRA_CARRIER_PENALTY_PLN = 30
