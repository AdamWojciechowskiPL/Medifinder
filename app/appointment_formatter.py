"""
Uniwersalny formatter wizyt lekarskich, w pełni dostosowany do nowej,
zagnieżdżonej struktury danych z API Medicover.
Wersja z uproszczonym i niezawodnym formatowaniem szczegółów wizyty.
"""

from typing import Dict, List, Any
from datetime import datetime

class AppointmentFormatter:
    """
    Uniwersalna, bezstanowa klasa narzędziowa do formatowania wizyt lekarskich.
    """

    # --- GŁÓWNA METODA FORMATUJĄCA (Z NOWĄ, PROSTĄ LOGIKĄ) ---

    @staticmethod
    def format_details(appointment: Dict[str, Any]) -> str:
        """
        Formatuje szczegóły pojedynczej wizyty w formie prostej, czytelnej listy.
        """
        try:
            # Pobranie wszystkich potrzebnych danych
            date, time = AppointmentFormatter._extract_datetime(appointment)
            doctor = AppointmentFormatter._get_doctor_name(appointment)
            specialty = AppointmentFormatter._get_specialty_name(appointment)
            clinic = AppointmentFormatter._get_clinic_name(appointment)
            languages = AppointmentFormatter._format_languages(appointment)
            services = AppointmentFormatter._format_services(appointment)
            visit_type = AppointmentFormatter._get_nested_val(appointment, ['visitType'], 'Standardowa')

            # Budowanie prostej listy f-stringów, co gwarantuje poprawne formatowanie
            details = [
                "--- 🏥 SZCZEGÓŁY WIZYTY ---",
                f"📅 Data i godzina: {date} {time}",
                f"👨‍⚕️ Lekarz:         {doctor}",
                f"🔬 Specjalność:     {specialty}",
                f"🏥 Klinika:         {clinic}",
                f"🗣️ Języki:          {languages}",
                f"📋 Typ wizyty:      {visit_type}",
                f"🛍️ Usługi:          {services}",
                "---------------------------------"
            ]
            return '\n'.join(details)
        except Exception as e:
            return f"❌ Błąd formatowania szczegółów wizyty: {e}"

    # ... (reszta metod, takich jak format_summary, format_table, etc. pozostaje bez zmian) ...
    # Poniżej wklejam resztę pliku dla kompletności.

    @staticmethod
    def format_summary(appointments: List[Dict[str, Any]]) -> str:
        if not appointments:
            return "🔍 Brak dostępnych wizyt do podsumowania."
        grouped_by_specialty: Dict[str, int] = {}
        grouped_by_clinic: Dict[str, int] = {}
        for apt in appointments:
            specialty = AppointmentFormatter._get_specialty_name(apt)
            clinic = AppointmentFormatter._get_clinic_name(apt)
            grouped_by_specialty[specialty] = grouped_by_specialty.get(specialty, 0) + 1
            grouped_by_clinic[clinic] = grouped_by_clinic.get(clinic, 0) + 1
        summary = [f"📊 PODSUMOWANIE: Znaleziono {len(appointments)} wizyt.", "\n🔬 Dostępne specjalności:"]
        for specialty, count in grouped_by_specialty.items():
            summary.append(f"  • {specialty}: {count} wizyt")
        summary.append("\n🏥 Dostępne kliniki:")
        for clinic, count in grouped_by_clinic.items():
            summary.append(f"  • {clinic}: {count} wizyt")
        return '\n'.join(summary)

    @staticmethod
    def format_table(appointments: List[Dict[str, Any]], max_rows: int = 20) -> str:
        if not appointments:
            return "🔍 Brak dostępnych wizyt do wyświetlenia w tabeli."
        display_appointments = appointments[:max_rows]
        header = f"{'Nr':<3} | {'Data':<10} | {'Czas':<5} | {'Lekarz':<25} | {'Specjalność':<20} | {'Klinika':<30}"
        separator = "─" * len(header)
        table = [f"🏥 Tabela wizyt (wyświetlono {len(display_appointments)} z {len(appointments)}):", separator, header, separator]
        for i, apt in enumerate(display_appointments, 1):
            date, time = AppointmentFormatter._extract_datetime(apt)
            doctor = AppointmentFormatter._truncate(AppointmentFormatter._get_doctor_name(apt), 23)
            specialty = AppointmentFormatter._truncate(AppointmentFormatter._get_specialty_name(apt), 18)
            clinic = AppointmentFormatter._truncate(AppointmentFormatter._get_clinic_name(apt), 28)
            row = f"{i:<3} | {date:<10} | {time:<5} | {doctor:<25} | {specialty:<20} | {clinic:<30}"
            table.append(row)
        if len(appointments) > max_rows:
            table.append(f"\n... i {len(appointments) - max_rows} więcej.")
        return '\n'.join(table)

    @staticmethod
    def format_compact_line(appointment: Dict[str, Any], width: int = 80) -> str:
        date, time = AppointmentFormatter._extract_datetime(appointment)
        doctor = AppointmentFormatter._get_doctor_name(appointment)
        specialty = AppointmentFormatter._get_specialty_name(appointment)
        clinic = AppointmentFormatter._get_clinic_name(appointment)
        line = f"{date} {time} | {doctor:<28} | {specialty:<20} | {clinic}"
        return AppointmentFormatter._truncate(line, width)

    @staticmethod
    def _get_nested_val(data: Dict, path: List[str], default: Any = 'N/A') -> Any:
        temp = data
        for key in path:
            if isinstance(temp, dict):
                temp = temp.get(key)
            else:
                return default
        return temp if temp is not None else default

    @staticmethod
    def _get_doctor_name(appointment: Dict[str, Any]) -> str:
        return AppointmentFormatter._get_nested_val(appointment, ['doctor', 'name'], 'Nieznany lekarz')

    @staticmethod
    def _get_specialty_name(appointment: Dict[str, Any]) -> str:
        return AppointmentFormatter._get_nested_val(appointment, ['specialty', 'name'], 'Nieznana specjalność')

    @staticmethod
    def _get_clinic_name(appointment: Dict[str, Any]) -> str:
        return AppointmentFormatter._get_nested_val(appointment, ['clinic', 'name'], 'Nieznana klinika')

    @staticmethod
    def _extract_datetime(appointment: Dict[str, Any]) -> tuple[str, str]:
        iso_date = AppointmentFormatter._get_nested_val(appointment, ['appointmentDate'])
        if iso_date == 'N/A':
            return 'Brak daty', '--:--'
        try:
            dt_obj = datetime.fromisoformat(iso_date)
            return dt_obj.strftime('%Y-%m-%d'), dt_obj.strftime('%H:%M')
        except (ValueError, TypeError):
            return str(iso_date)[:10], str(iso_date)[11:16]

    @staticmethod
    def _format_languages(appointment: Dict[str, Any]) -> str:
        languages = AppointmentFormatter._get_nested_val(appointment, ['doctorLanguages'], [])
        if not isinstance(languages, list) or not languages:
            return 'Brak informacji'
        names = [lang.get('name') for lang in languages if lang.get('name')]
        return ', '.join(names) if names else 'Brak informacji'

    @staticmethod
    def _format_services(appointment: Dict[str, Any]) -> str:
        services = []
        if AppointmentFormatter._get_nested_val(appointment, ['isOpticsAvailable'], False):
            services.append('👓 Optyka')
        if AppointmentFormatter._get_nested_val(appointment, ['isPharmaAvailable'], False):
            services.append('💊 Apteka')
        if AppointmentFormatter._get_nested_val(appointment, ['isOverbooking'], False):
            services.append('⚡ Overbooking')
        return ' | '.join(services) if services else 'Brak'

    @staticmethod
    def _truncate(text: str, max_length: int) -> str:
        if not isinstance(text, str) or len(text) <= max_length:
            return text
        return text[:max_length - 2] + '..'