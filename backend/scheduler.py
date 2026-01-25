"""
Backend Scheduler for Medifinder
Manages background tasks for cyclic appointment checking and auto-booking
"""
import logging
import json
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.base import JobLookupError

logger = logging.getLogger(__name__)

class MedifinderScheduler:
    """
    Zarządza zadaniami w tle (background jobs) dla aplikacji Medifinder.
    Każdy użytkownik może mieć własne zadanie cyklicznego sprawdzania.
    """
    
    def __init__(self, config_dir: Path, med_app):
        self.config_dir = config_dir
        self.med_app = med_app
        self.scheduler = BackgroundScheduler(daemon=True)
        self.tasks_config_file = config_dir / "scheduler_tasks.json"
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self._load_tasks()
        self.scheduler.start()
        logger.info("🚀 Medifinder Scheduler uruchomiony")
        
    def _load_tasks(self):
        """Wczytuje zapisane zadania z pliku przy starcie aplikacji."""
        try:
            if self.tasks_config_file.exists():
                with open(self.tasks_config_file, 'r', encoding='utf-8') as f:
                    self.tasks = json.load(f)
                logger.info(f"Wczytano {len(self.tasks)} zadań z pliku konfiguracyjnego")
                
                # Odtwórz aktywne zadania
                for task_id, task_data in self.tasks.items():
                    if task_data.get('active', False):
                        self._schedule_task(task_id, task_data)
            else:
                logger.info("Brak zapisanych zadań - tworzenie nowego pliku")
                self.tasks = {}
        except Exception as e:
            logger.error(f"Błąd wczytywania zadań: {e}")
            self.tasks = {}
    
    def _save_tasks(self):
        """Zapisuje aktualne zadania do pliku."""
        try:
            with open(self.tasks_config_file, 'w', encoding='utf-8') as f:
                json.dump(self.tasks, f, indent=2, ensure_ascii=False)
            logger.debug("Zadania zapisane do pliku")
        except Exception as e:
            logger.error(f"Błąd zapisu zadań: {e}")
    
    def _generate_task_id(self, user_email: str, profile: str) -> str:
        """Generuje unikalny ID zadania dla użytkownika i profilu."""
        return f"{user_email}::{profile}"
    
    def _schedule_task(self, task_id: str, task_data: Dict[str, Any]):
        """Dodaje zadanie do schedulera APScheduler."""
        try:
            interval_minutes = task_data.get('interval_minutes', 5)
            
            self.scheduler.add_job(
                func=self._execute_task,
                trigger=IntervalTrigger(minutes=interval_minutes),
                id=task_id,
                args=[task_id],
                replace_existing=True,
                max_instances=1  # Zapobiega nakładaniu się wykonań
            )
            
            # Zapisz czas następnego wykonania
            self.tasks[task_id]['next_run'] = (datetime.now() + timedelta(minutes=interval_minutes)).isoformat()
            self.tasks[task_id]['last_run'] = None
            
            logger.info(f"✅ Zadanie {task_id} zaplanowane (co {interval_minutes} min)")
        except Exception as e:
            logger.error(f"Błąd planowania zadania {task_id}: {e}")
    
    def _execute_task(self, task_id: str):
        """Wykonuje zadanie cyklicznego sprawdzania."""
        if task_id not in self.tasks:
            logger.warning(f"Zadanie {task_id} nie istnieje w konfiguracji")
            return
        
        task_data = self.tasks[task_id]
        user_email = task_data['user_email']
        profile = task_data['profile']
        search_params = task_data['search_params']
        auto_book = task_data.get('auto_book', False)
        
        logger.info(f"🔍 [{task_id}] Rozpoczynam cykliczne sprawdzanie...")
        
        try:
            # Aktualizuj czas ostatniego uruchomienia
            self.tasks[task_id]['last_run'] = datetime.now().isoformat()
            
            # Wykonaj wyszukiwanie
            results = self.med_app.search_appointments(
                user_email=user_email,
                profile=profile,
                **search_params
            )
            
            logger.info(f"📊 [{task_id}] Znaleziono {len(results)} wizyt")
            
            # Jeśli auto-booking jest włączony i znaleziono wizyty
            if auto_book and results:
                first_appointment = results[0]
                logger.info(f"🎯 [{task_id}] Auto-booking: próba rezerwacji pierwszej wizyty...")
                
                booking_result = self.med_app.book_appointment(
                    user_email=user_email,
                    profile=profile,
                    appointment_id=first_appointment.get('appointmentId'),
                    booking_string=first_appointment.get('bookingString')
                )
                
                if booking_result.get('success'):
                    logger.info(f"✅ [{task_id}] AUTO-REZERWACJA UDANA! Zatrzymuję zadanie.")
                    # Zatrzymaj zadanie po udanej rezerwacji
                    self.stop_task(user_email, profile)
                    
                    # Zapisz informację o sukcesie
                    self.tasks[task_id]['last_booking'] = {
                        'timestamp': datetime.now().isoformat(),
                        'appointment': first_appointment
                    }
                    self._save_tasks()
                else:
                    logger.warning(f"⚠️ [{task_id}] Auto-rezerwacja nie powiodła się: {booking_result.get('message')}")
            
            # Zaktualizuj czas następnego uruchomienia
            interval = task_data.get('interval_minutes', 5)
            self.tasks[task_id]['next_run'] = (datetime.now() + timedelta(minutes=interval)).isoformat()
            self._save_tasks()
            
        except Exception as e:
            logger.error(f"❌ [{task_id}] Błąd wykonania zadania: {e}", exc_info=True)
    
    def start_task(self, user_email: str, profile: str, search_params: Dict[str, Any], 
                   interval_minutes: int = 5, auto_book: bool = False) -> Dict[str, Any]:
        """Uruchamia nowe zadanie cyklicznego sprawdzania."""
        task_id = self._generate_task_id(user_email, profile)
        
        task_data = {
            'user_email': user_email,
            'profile': profile,
            'search_params': search_params,
            'interval_minutes': interval_minutes,
            'auto_book': auto_book,
            'active': True,
            'created_at': datetime.now().isoformat()
        }
        
        self.tasks[task_id] = task_data
        self._schedule_task(task_id, task_data)
        self._save_tasks()
        
        return {
            'success': True,
            'message': f'Zadanie uruchomione (co {interval_minutes} min)',
            'task_id': task_id,
            'next_run': task_data.get('next_run')
        }
    
    def stop_task(self, user_email: str, profile: str) -> Dict[str, Any]:
        """Zatrzymuje zadanie dla danego użytkownika i profilu."""
        task_id = self._generate_task_id(user_email, profile)
        
        if task_id not in self.tasks:
            return {'success': False, 'message': 'Zadanie nie istnieje'}
        
        try:
            # Usuń z schedulera
            self.scheduler.remove_job(task_id)
            logger.info(f"🛑 Zadanie {task_id} zatrzymane")
        except JobLookupError:
            logger.warning(f"Zadanie {task_id} nie było aktywne w schedulerze")
        
        # Oznacz jako nieaktywne
        self.tasks[task_id]['active'] = False
        self.tasks[task_id]['stopped_at'] = datetime.now().isoformat()
        self._save_tasks()
        
        return {'success': True, 'message': 'Zadanie zatrzymane'}
    
    def get_task_status(self, user_email: str, profile: str) -> Optional[Dict[str, Any]]:
        """Zwraca status zadania dla użytkownika."""
        task_id = self._generate_task_id(user_email, profile)
        return self.tasks.get(task_id)
    
    def get_all_user_tasks(self, user_email: str) -> Dict[str, Dict[str, Any]]:
        """Zwraca wszystkie zadania danego użytkownika."""
        return {tid: data for tid, data in self.tasks.items() if data.get('user_email') == user_email}
    
    def shutdown(self):
        """Zamyka scheduler przy wyłączaniu aplikacji."""
        logger.info("Zamykanie schedulera...")
        self.scheduler.shutdown(wait=True)
        logger.info("Scheduler zamknięty")
