import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)

class MedifinderScheduler:
    def __init__(self, medifinder_instance):
        self.medifinder = medifinder_instance
        self.scheduler = BackgroundScheduler(
            jobstores={'default': MemoryJobStore()},
            timezone='UTC'
        )
        self.active_tasks = {}  # task_id -> task_config
        self.task_status = {}   # task_id -> {last_run, runs_count, last_results, last_error, start_time}
        self.scheduler.start()
        logger.info("Medifinder Scheduler uruchomiony")

    def create_task_id(self, user_email, profile):
        """Tworzy unikalny ID zadania na podstawie email usera i profilu"""
        return f"{user_email}:{profile}"

    def start_task(self, user_email, profile, config):
        """
        Uruchamia cykliczne zadanie dla danego profilu
        config: {
            'specialty_ids': [...],
            'doctor_ids': [...],
            'clinic_ids': [...],
            'preferred_days': [...],
            'time_range': {'start': '08:00', 'end': '18:00'},
            'excluded_dates': [...],
            'interval_minutes': 5,
            'auto_book': False
        }
        """
        task_id = self.create_task_id(user_email, profile)
        
        # Usuń poprzednie zadanie jeśli istnieje
        if task_id in self.active_tasks:
            self.stop_task(user_email, profile)
        
        # Zapisz konfigurację zadania
        self.active_tasks[task_id] = config
        self.task_status[task_id] = {
            'last_run': None,
            'runs_count': 0,
            'last_results': None,
            'last_error': None,
            'start_time': datetime.utcnow().isoformat(),
            'stop_time': (datetime.utcnow() + timedelta(hours=24)).isoformat()  # Auto-stop po 24h
        }
        
        # Dodaj zadanie do schedulera
        interval = config.get('interval_minutes', 5)
        self.scheduler.add_job(
            func=self.execute_task,
            trigger='interval',
            minutes=interval,
            id=task_id,
            args=[user_email, profile],
            replace_existing=True
        )
        
        logger.info(f"Zadanie {task_id} zaplanowane co {interval} min (auto-stop po 24h)")
        return True

    def execute_task(self, user_email, profile):
        """Wykonuje pojedyncze sprawdzenie wizyt"""
        task_id = self.create_task_id(user_email, profile)
        
        # Sprawdź czy minęło 24h od uruchomienia
        if task_id in self.task_status:
            start_time = datetime.fromisoformat(self.task_status[task_id]['start_time'])
            elapsed = datetime.utcnow() - start_time
            
            if elapsed.total_seconds() >= 24 * 3600:  # 24 godziny
                logger.info(f"{task_id} ⏰ Automatyczne zatrzymanie po 24 godzinach pracy")
                self.stop_task(user_email, profile)
                return
        
        logger.info(f"{task_id} Rozpoczynam cykliczne sprawdzanie...")
        
        try:
            config = self.active_tasks.get(task_id, {})
            
            # Wykonaj wyszukiwanie wizyt
            results = self.medifinder.search_appointments(
                profile=profile,
                specialty_ids=config.get('specialty_ids', []),
                doctor_ids=config.get('doctor_ids', []),
                clinic_ids=config.get('clinic_ids', []),
                preferred_days=config.get('preferred_days', []),
                time_range=config.get('time_range', {}),
                excluded_dates=config.get('excluded_dates', [])
            )
            
            # Aktualizuj status
            if task_id in self.task_status:
                self.task_status[task_id]['last_run'] = datetime.utcnow().isoformat()
                self.task_status[task_id]['runs_count'] += 1
                self.task_status[task_id]['last_results'] = {
                    'count': len(results),
                    'timestamp': datetime.utcnow().isoformat(),
                    'appointments': results
                }
            
            logger.info(f"{task_id} Znaleziono {len(results)} wizyt")
            
            # Auto-booking jeśli włączone
            if config.get('auto_book', False) and len(results) > 0:
                first_apt = results[0]
                try:
                    self.medifinder.book_appointment(
                        profile=profile,
                        appointment_id=first_apt.get('appointmentId') or first_apt.get('id'),
                        booking_string=first_apt.get('bookingString')
                    )
                    logger.info(f"{task_id} ✅ Automatycznie zarezerwowano wizytę")
                except Exception as e:
                    logger.error(f"{task_id} ❌ Błąd auto-booking: {str(e)}")
            
        except Exception as e:
            logger.error(f"{task_id} Błąd podczas wykonywania zadania: {str(e)}")
            if task_id in self.task_status:
                self.task_status[task_id]['last_error'] = {
                    'error': str(e),
                    'timestamp': datetime.utcnow().isoformat()
                }

    def stop_task(self, user_email, profile):
        """Zatrzymuje cykliczne zadanie dla danego profilu"""
        task_id = self.create_task_id(user_email, profile)
        
        if task_id in self.active_tasks:
            try:
                self.scheduler.remove_job(task_id)
                logger.info(f"Zadanie {task_id} usunięte z schedulera")
            except:
                pass
            
            del self.active_tasks[task_id]
            # Zachowaj status dla historii, ale oznacz jako nieaktywny
            if task_id in self.task_status:
                self.task_status[task_id]['stopped_at'] = datetime.utcnow().isoformat()
            
            logger.info(f"Zadanie {task_id} zatrzymane")
            return True
        
        logger.warning(f"Zadanie {task_id} nie było aktywne")
        return False

    def get_task_status(self, user_email, profile):
        """Zwraca status zadania dla danego profilu"""
        task_id = self.create_task_id(user_email, profile)
        
        if task_id not in self.active_tasks:
            return {
                'active': False,
                'task_id': task_id
            }
        
        config = self.active_tasks[task_id]
        status = self.task_status.get(task_id, {})
        
        # Oblicz czas do następnego wykonania
        next_run = None
        try:
            job = self.scheduler.get_job(task_id)
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()
        except:
            pass
        
        return {
            'active': True,
            'task_id': task_id,
            'interval_minutes': config.get('interval_minutes', 5),
            'auto_book': config.get('auto_book', False),
            'next_run': next_run,
            'start_time': status.get('start_time'),
            'stop_time': status.get('stop_time'),
            'last_run': status.get('last_run'),
            'runs_count': status.get('runs_count', 0),
            'last_results': status.get('last_results'),
            'last_error': status.get('last_error')
        }

    def get_last_results(self, user_email, profile):
        """Zwraca ostatnie wyniki wyszukiwania"""
        task_id = self.create_task_id(user_email, profile)
        status = self.task_status.get(task_id, {})
        return status.get('last_results')

    def shutdown(self):
        """Wyłącza scheduler"""
        self.scheduler.shutdown()
        logger.info("Scheduler zatrzymany")
