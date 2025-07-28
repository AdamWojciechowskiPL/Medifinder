# START OF FILE: discover_specialties.py (Finalna Wersja z Globalną Pauzą)

import time
import json
import logging
from typing import Dict, Set

# Importujemy komponenty z działającej aplikacji
from medicover_client import MedicoverClient
from config import Config
from profile_manager import ProfileManager

# --- Konfiguracja ---
ID_RANGE_START = 727
ID_RANGE_END = 2000

# To jest teraz jedyna przerwa, którą skrypt sam zarządza
DELAY_BETWEEN_REQUESTS_SECONDS = 15.0
PENALTY_WAIT_SECONDS = 600 # 10 minut
# Pliki wyjściowe
RESULTS_FILE = "found_specialties.json"
RECHECK_FILE = "recheck_specialty_ids.txt"
# --- Koniec Konfiguracji ---

def discover():
    """
    Główna funkcja deweloperska, która poprawnie obsługuje 10-minutową pauzę
    zwracaną przez MedicoverClient jako None.
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("SpecialtyDiscoverer")

    logger.info("--- Rozpoczynam proces odkrywania specjalności ---")

    # 1. Inicjalizacja i logowanie
    config = Config("credentials.json")
    profile_manager = ProfileManager("profiles.json")
    
    default_profile = profile_manager.get_default_profile()
    if not default_profile:
        logger.error("Nie znaleziono domyślnego profilu w profiles.json. Przerwanie.")
        return

    credentials = profile_manager.get_credentials(default_profile.username)
    if not credentials:
        logger.error(f"Nie udało się pobrać danych logowania dla profilu {default_profile.username}.")
        return
        
    username, password = credentials
    logger.info(f"Używam profilu: {username} do zalogowania.")
    
    config_data_for_client = config.data.copy()
    config_data_for_client['username'] = username
    config_data_for_client['password'] = password
    
    client = MedicoverClient(config_data_for_client)

    logger.info("Próba zalogowania do systemu Medicover...")
    if not client.login(username, password):
        logger.error("Logowanie nie powiodło się. Sprawdź dane w profilu domyślnym.")
        return
    logger.info("Logowanie zakończone sukcesem. Sesja jest aktywna.")

    # 2. Przygotowanie danych
    found_specialties: Dict[str, str] = {}
    ids_to_recheck: Set[int] = set()

    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f: found_specialties = json.load(f)
        logger.info(f"Wczytano {len(found_specialties)} wcześniej znalezionych specjalności.")
    except (FileNotFoundError, json.JSONDecodeError): pass

    try:
        with open(RECHECK_FILE, 'r', encoding='utf-8') as f:
            ids_from_file = {int(line.strip()) for line in f if line.strip().isdigit()}
            ids_to_recheck.update(ids_from_file)
        logger.info(f"Wczytano {len(ids_to_recheck)} ID do ponownego sprawdzenia.")
    except FileNotFoundError: pass

    # Krok 1: Zbierz wszystkich możliwych kandydatów z zakresu i pliku recheck
    all_potential_ids = set(range(ID_RANGE_START, ID_RANGE_END + 1)) | ids_to_recheck

    # Krok 2: Odfiltruj tych, którzy są poza zadanym zakresem
    ids_in_range = {id for id in all_potential_ids if ID_RANGE_START <= id <= ID_RANGE_END}

    # Krok 3: Odfiltruj tych, których już znaleźliśmy (klucze w found_specialties są stringami)
    found_ids_as_int = {int(id_str) for id_str in found_specialties.keys() if id_str.isdigit()}

    # Krok 4: Ostateczna lista do przetworzenia to różnica zbiorów
    final_ids_to_process = sorted(list(ids_in_range - found_ids_as_int))

    total_count = len(final_ids_to_process)
    logger.info(f"Znaleziono {len(found_specialties)} istniejących specjalności.")
    logger.info(f"Łącznie do sprawdzenia (po odfiltrowaniu już znalezionych): {total_count} unikalnych ID.")

    # 3. Główna pętla
    try:
        for i, specialty_id in enumerate(final_ids_to_process):
            logger.info(f"[*] Sprawdzanie ID: {specialty_id} ({i + 1}/{total_count})...")
            
            succeeded = False
            while not succeeded:
                try:
                    search_params = {'SpecialtyIds': [specialty_id], 'page_size': 1}
                    appointments = client.search_appointments(search_params)

                    # KLUCZOWA ZMIANA: Sprawdzamy, czy klient nie zasygnalizował błędu 429
                    if appointments is None:
                        logger.critical(f"[!] Otrzymano sygnał o blokadzie API dla ID {specialty_id}.")
                        logger.critical(f"    Wprowadzam 10-minutową ({PENALTY_WAIT_SECONDS}s) przerwę...")
                        time.sleep(PENALTY_WAIT_SECONDS)
                        logger.info("    Przerwa zakończona. Ponawiam próbę dla tego samego ID...")
                        continue # Wróć na początek pętli while, aby spróbować ponownie

                    succeeded = True

                    if appointments:
                        specialty_info = appointments[0].get('specialty', {})
                        name, actual_id = specialty_info.get('name'), specialty_info.get('id')
                        if name and actual_id:
                            logger.info(f"[+] ZNALEZIONO: ID={actual_id}, Nazwa='{name}'")
                            found_specialties[str(actual_id)] = name
                            ids_to_recheck.discard(specialty_id)
                            ids_to_recheck.discard(actual_id)
                        else:
                            logger.warning(f"[!] Znaleziono wizytę dla ID {specialty_id}, ale brak w niej danych.")
                            ids_to_recheck.add(specialty_id)
                    else:
                        logger.info(f"[-] Brak wizyt dla ID: {specialty_id}. Dodaję do ponownego sprawdzenia.")
                        ids_to_recheck.add(specialty_id)
                
                except Exception as e:
                    logger.error(f"Wystąpił nieoczekiwany błąd podczas przetwarzania ID {specialty_id}: {e}", exc_info=True)
                    ids_to_recheck.add(specialty_id)
                    succeeded = True # Przerywamy próby dla tego ID i idziemy dalej

            time.sleep(DELAY_BETWEEN_REQUESTS_SECONDS)

    except KeyboardInterrupt:
        logger.warning("Przerwano przez użytkownika. Zapisuję dotychczasowe wyniki.")
    finally:
        # 4. Zapis wyników
        logger.info("--- Zapisywanie wyników ---")
        if found_specialties:
            with open(RESULTS_FILE, 'w', encoding='utf-8') as f: json.dump(found_specialties, f, indent=4, ensure_ascii=False)
            logger.info(f"Zapisano {len(found_specialties)} znalezionych specjalności do pliku: {RESULTS_FILE}")
        
        if ids_to_recheck:
            sorted_ids = sorted(list(ids_to_recheck))
            with open(RECHECK_FILE, 'w', encoding='utf-8') as f:
                for item_id in sorted_ids: f.write(f"{item_id}\n")
            logger.info(f"Zapisano {len(sorted_ids)} unikalnych ID do ponownego sprawdzenia do pliku: {RECHECK_FILE}")
        
        logger.info("--- Zakończono ---")


if __name__ == "__main__":
    discover()

# END OF FILE: discover_specialties.py