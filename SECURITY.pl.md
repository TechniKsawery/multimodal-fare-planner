Polski | English: [English version](SECURITY.md)

# Polityka bezpieczeństwa

To projekt portfolio/prototyp, a nie usługa produkcyjna. Jeśli znajdziesz problem bezpieczeństwa
(na przykład ujawniony sekret), zgłoś go prywatnie przez GitHub:

**Security tab -> „Report a vulnerability”** (prywatne zgłaszanie podatności), a nie w publicznym
zgłoszeniu issue.

- Sekrety (`.env`, tokeny) nigdy nie są commitowane; `.env.example` zawiera wyłącznie puste
  placeholdery.
- Nieoficjalna usługa cen DB została usunięta z tego repozytorium; opcjonalny kod klienta
  `UNOFFICIAL_PRICES` pozostaje domyślnie wyłączony.
- Nie wystawiaj aplikacji Streamlit ani API do internetu bez własnego uwierzytelniania
  i ograniczania liczby żądań.
